package common

import (
	"testing"

	"github.com/shopspring/decimal"
)

func TestQuotaFromDecimalSaturatesBeforeIntPart(t *testing.T) {
	if got := QuotaFromDecimal(decimal.RequireFromString("123.9")); got != 123 {
		t.Fatalf("QuotaFromDecimal normal value = %d, want 123", got)
	}
	if got := QuotaFromDecimal(decimal.RequireFromString("999999999999999999999999")); got != MaxQuota {
		t.Fatalf("QuotaFromDecimal overflow = %d, want %d", got, MaxQuota)
	}
	if got := QuotaFromDecimal(decimal.RequireFromString("-999999999999999999999999")); got != MinQuota {
		t.Fatalf("QuotaFromDecimal underflow = %d, want %d", got, MinQuota)
	}
}
