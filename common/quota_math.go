package common

import (
	"fmt"
	"math"

	"github.com/shopspring/decimal"
)

// This file centralizes every quota -> int conversion on the billing path.
//
// Why this exists: quota columns persisted to the database (users.quota,
// tokens.remain_quota, logs.quota) are 32-bit signed integers, and the in-memory
// quota arithmetic multiplies prices, ratios, and user-controlled multipliers
// (image n, video duration/seconds, max_tokens). A sufficiently large product
// overflows a plain int(float64(...)) / int(uint) cast: on amd64 the CVTTSD2SI
// instruction returns the sentinel MinInt64 for any out-of-range input, and a
// uint->int cast reinterprets the high bit as a sign bit. Either way the result
// is a *negative* quota, and the billing refund branch treats a non-positive
// value as a credit (IncreaseUserQuota(-quota)) — turning a charge into free
// balance. See SECURITY_quota_overflow_audit.md.
//
// Fix: saturate to the int32 policy range instead of wrapping, and log every
// clamp because a single legitimate request never approaches these bounds.

const (
	// MaxQuota is the upper bound for a persisted quota value. The DB columns
	// are 32-bit signed INT, so clamp at MaxInt32 rather than MaxInt64.
	MaxQuota = math.MaxInt32
	// MinQuota is the lower bound. A genuinely negative quota is never
	// legitimate (usage cannot be negative), so callers should additionally
	// guard quota < 0 -> 0 on actual-charge paths.
	MinQuota = math.MinInt32
)

// QuotaClamp records a single saturation event so callers can attach it to
// consume/task logs for admin auditing. It is nil for in-range conversions.
type QuotaClamp struct {
	Op       string  `json:"op"`       // calling site, e.g. "image_pre_consume"
	Kind     string  `json:"kind"`     // "overflow" | "underflow" | "nan"
	Original float64 `json:"original"` // best-effort pre-clamp value
	Clamped  int     `json:"clamped"`  // the saturated result actually used
}

// AuditMap renders the clamp as the marker stored under a log's admin_info.
func (c *QuotaClamp) AuditMap() map[string]interface{} {
	if c == nil {
		return nil
	}
	return map[string]interface{}{
		"op":       c.Op,
		"kind":     c.Kind,
		"original": c.Original,
		"clamped":  c.Clamped,
	}
}

// saturateQuota converts a float quota to int, clamping to the int32 range.
// Truncation toward zero matches the previous int(float64(...)) behavior for
// in-range values, so billing amounts are unchanged for legitimate requests.
func saturateQuota(value float64, op string) (int, *QuotaClamp) {
	switch {
	case math.IsNaN(value):
		SysError(fmt.Sprintf("quota conversion (%s) received NaN, falling back to 0", op))
		return 0, &QuotaClamp{Op: op, Kind: "nan", Original: value, Clamped: 0}
	case value >= MaxQuota:
		SysError(fmt.Sprintf("quota conversion (%s) overflow: %g exceeds max quota, clamped to %d", op, value, MaxQuota))
		return MaxQuota, &QuotaClamp{Op: op, Kind: "overflow", Original: value, Clamped: MaxQuota}
	case value <= MinQuota:
		SysError(fmt.Sprintf("quota conversion (%s) underflow: %g below min quota, clamped to %d", op, value, MinQuota))
		return MinQuota, &QuotaClamp{Op: op, Kind: "underflow", Original: value, Clamped: MinQuota}
	default:
		return int(value), nil
	}
}

// QuotaFromFloat converts a computed quota value to int, truncating toward zero
// with saturation. Use this everywhere a billing path previously wrote
// int(float64(...)) over prices, ratios, and user-controlled multipliers
// (image n, video seconds, resolution/max_tokens ratios).
func QuotaFromFloat(value float64) int {
	quota, _ := QuotaFromFloatChecked(value, "QuotaFromFloat")
	return quota
}

// QuotaFromFloatChecked is QuotaFromFloat but also returns a non-nil *QuotaClamp
// when the value was clamped, so the caller can record the event on a log.
func QuotaFromFloatChecked(value float64, op string) (int, *QuotaClamp) {
	return saturateQuota(value, op)
}

// QuotaFromDecimal converts a decimal quota to int with the same int32
// saturation policy as QuotaFromFloat. Callers may pass value.Round(0) first
// when they need the historical rounded behavior.
func QuotaFromDecimal(value decimal.Decimal) int {
	quota, _ := QuotaFromDecimalChecked(value, "QuotaFromDecimal")
	return quota
}

// QuotaFromDecimalChecked is QuotaFromDecimal but also returns clamp metadata.
// It compares as decimal before calling IntPart so very large coefficients never
// reach big.Int.Int64(), whose overflow behavior is undefined for this purpose.
func QuotaFromDecimalChecked(value decimal.Decimal, op string) (int, *QuotaClamp) {
	maxQuota := decimal.NewFromInt(int64(MaxQuota))
	minQuota := decimal.NewFromInt(int64(MinQuota))
	switch {
	case value.GreaterThan(maxQuota):
		SysError(fmt.Sprintf("quota conversion (%s) overflow: %s exceeds max quota, clamped to %d", op, value.String(), MaxQuota))
		return MaxQuota, &QuotaClamp{Op: op, Kind: "overflow", Original: value.InexactFloat64(), Clamped: MaxQuota}
	case value.LessThan(minQuota):
		SysError(fmt.Sprintf("quota conversion (%s) underflow: %s below min quota, clamped to %d", op, value.String(), MinQuota))
		return MinQuota, &QuotaClamp{Op: op, Kind: "underflow", Original: value.InexactFloat64(), Clamped: MinQuota}
	default:
		return int(value.IntPart()), nil
	}
}

// QuotaFromUint converts an unsigned user-controlled multiplier (e.g. image n,
// which arrives as uint) to a non-negative int with saturation. This closes the
// uint->int sign-wrap attack where n >= 2^63 reinterprets as a negative int.
// Returns the clamped value and true if the input exceeded the safe range.
func QuotaFromUint(n uint, op string) (int, *QuotaClamp) {
	if n > uint(MaxQuota) {
		v := uint64(n)
		SysError(fmt.Sprintf("quota conversion (%s) uint overflow: %d exceeds max quota, clamped to %d", op, v, MaxQuota))
		return MaxQuota, &QuotaClamp{Op: op, Kind: "overflow", Original: float64(v), Clamped: MaxQuota}
	}
	return int(n), nil
}
