package model

import (
	"encoding/json"
	"fmt"
	"math"
	"strings"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/setting/ratio_setting"
	"github.com/shopspring/decimal"
)

type Claude200KFixRecord struct {
	Log            *Log    `json:"log"`
	CorrectQuota   int     `json:"correct_quota"`
	QuotaDiff      int     `json:"quota_diff"`
	TotalInput     int     `json:"total_input"`
	TierRange      string  `json:"tier_range"`
	IsNativeAPI    bool    `json:"is_native_api"`
	CanRecalc      bool    `json:"can_recalc"`
	SkipReason     string  `json:"skip_reason,omitempty"`
	GroupRatio     float64 `json:"group_ratio"`
	InputPrice     float64 `json:"input_price"`
	OutputPrice    float64 `json:"output_price"`
	CacheHitPrice  float64 `json:"cache_hit_price"`
	CacheTokens    int     `json:"cache_tokens"`
	CacheCreation  int     `json:"cache_creation_tokens"`
	CacheCreation5m int    `json:"cache_creation_tokens_5m"`
	CacheCreation1h int    `json:"cache_creation_tokens_1h"`
}

type Claude200KFixSummary struct {
	TotalRecords    int                       `json:"total_records"`
	AffectedRecords int                       `json:"affected_records"`
	TotalDiff       int64                     `json:"total_diff"`
	UserDiffs       []Claude200KFixUserDiff   `json:"user_diffs"`
	ModelDiffs      []Claude200KFixModelDiff  `json:"model_diffs"`
}

type Claude200KFixUserDiff struct {
	UserId   int    `json:"user_id"`
	Username string `json:"username"`
	Count    int    `json:"count"`
	Diff     int64  `json:"diff"`
}

type Claude200KFixModelDiff struct {
	ModelName string `json:"model_name"`
	Count     int    `json:"count"`
	Diff      int64  `json:"diff"`
}

type LogOtherParsed struct {
	Claude               bool    `json:"claude"`
	GroupRatio           float64 `json:"group_ratio"`
	ModelRatio           float64 `json:"model_ratio"`
	CompletionRatio      float64 `json:"completion_ratio"`
	CacheTokens          int     `json:"cache_tokens"`
	CacheRatio           float64 `json:"cache_ratio"`
	CacheCreationTokens  int     `json:"cache_creation_tokens"`
	CacheCreationRatio   float64 `json:"cache_creation_ratio"`
	CacheCreationTokens5m  int     `json:"cache_creation_tokens_5m"`
	CacheCreationRatio5m   float64 `json:"cache_creation_ratio_5m"`
	CacheCreationTokens1h  int     `json:"cache_creation_tokens_1h"`
	CacheCreationRatio1h   float64 `json:"cache_creation_ratio_1h"`
	ModelPrice           float64 `json:"model_price"`
	Claude200K           bool    `json:"claude_200k"`
	TieredPricing        bool    `json:"tiered_pricing"`
	Claude200KReviewed   bool    `json:"claude_200k_reviewed"`
}

func ParseLogOther(otherStr string) LogOtherParsed {
	var parsed LogOtherParsed
	if otherStr == "" {
		return parsed
	}
	var raw map[string]interface{}
	if err := json.Unmarshal([]byte(otherStr), &raw); err != nil {
		return parsed
	}

	parsed.Claude = getJsonBool(raw, "claude")
	parsed.GroupRatio = getJsonFloat(raw, "group_ratio")
	parsed.ModelRatio = getJsonFloat(raw, "model_ratio")
	parsed.CompletionRatio = getJsonFloat(raw, "completion_ratio")
	parsed.CacheTokens = getJsonInt(raw, "cache_tokens")
	parsed.CacheRatio = getJsonFloat(raw, "cache_ratio")
	parsed.CacheCreationTokens = getJsonInt(raw, "cache_creation_tokens")
	parsed.CacheCreationRatio = getJsonFloat(raw, "cache_creation_ratio")
	parsed.CacheCreationTokens5m = getJsonInt(raw, "cache_creation_tokens_5m")
	parsed.CacheCreationRatio5m = getJsonFloat(raw, "cache_creation_ratio_5m")
	parsed.CacheCreationTokens1h = getJsonInt(raw, "cache_creation_tokens_1h")
	parsed.CacheCreationRatio1h = getJsonFloat(raw, "cache_creation_ratio_1h")
	parsed.ModelPrice = getJsonFloat(raw, "model_price")
	parsed.Claude200K = getJsonBool(raw, "claude_200k")
	parsed.TieredPricing = getJsonBool(raw, "tiered_pricing")
	parsed.Claude200KReviewed = getJsonBool(raw, "claude_200k_reviewed")

	return parsed
}

func getJsonFloat(m map[string]interface{}, key string) float64 {
	if v, ok := m[key]; ok {
		switch val := v.(type) {
		case float64:
			return val
		case int:
			return float64(val)
		case json.Number:
			f, _ := val.Float64()
			return f
		}
	}
	return 0
}

func getJsonInt(m map[string]interface{}, key string) int {
	if v, ok := m[key]; ok {
		switch val := v.(type) {
		case float64:
			return int(val)
		case int:
			return val
		case json.Number:
			i, _ := val.Int64()
			return int(i)
		}
	}
	return 0
}

func getJsonBool(m map[string]interface{}, key string) bool {
	if v, ok := m[key]; ok {
		if b, ok := v.(bool); ok {
			return b
		}
	}
	return false
}

// RecalcClaudeQuotaWithTieredPricing recalculates quota using current tiered pricing.
// This mirrors the tiered pricing path in service/quota.go PostClaudeConsumeQuota (lines 282-341).
func RecalcClaudeQuotaWithTieredPricing(
	modelName string,
	promptTokens int,
	completionTokens int,
	isNativeAPI bool,
	cacheTokens int,
	cacheCreationTokens int,
	cacheCreationTokens5m int,
	cacheCreationTokens1h int,
	groupRatio float64,
) (quota float64, tierFound bool, tierRange string) {
	var totalInput int
	var actualPromptTokens int

	if isNativeAPI {
		// Claude native API: prompt_tokens does NOT include cache
		totalInput = promptTokens + cacheTokens + cacheCreationTokens
		actualPromptTokens = promptTokens
	} else {
		// Compatible handler: prompt_tokens already includes cache
		totalInput = promptTokens
		actualPromptTokens = promptTokens - cacheTokens - cacheCreationTokens5m - cacheCreationTokens1h
		remaining := cacheCreationTokens - cacheCreationTokens5m - cacheCreationTokens1h
		if remaining > 0 {
			actualPromptTokens -= remaining
		}
		if actualPromptTokens < 0 {
			actualPromptTokens = 0
		}
	}

	inputTokensK := totalInput / 1000
	priceTier, found := ratio_setting.GetPriceTierForTokens(modelName, inputTokensK)
	if !found {
		return 0, false, ""
	}

	cacheStorePrice5m := priceTier.CacheStorePrice5m
	if cacheStorePrice5m <= 0 {
		cacheStorePrice5m = priceTier.CacheStorePrice
	}
	cacheStorePrice1h := priceTier.CacheStorePrice1h
	if cacheStorePrice1h <= 0 {
		cacheStorePrice1h = priceTier.CacheStorePrice
	}

	remainingCreation := cacheCreationTokens - cacheCreationTokens5m - cacheCreationTokens1h
	if remainingCreation < 0 {
		remainingCreation = 0
	}

	dActualPromptTokens := decimal.NewFromInt(int64(actualPromptTokens))
	dCacheTokens := decimal.NewFromInt(int64(cacheTokens))
	dCacheCreationTokensRemaining := decimal.NewFromInt(int64(remainingCreation))
	dCacheCreationTokens5m := decimal.NewFromInt(int64(cacheCreationTokens5m))
	dCacheCreationTokens1h := decimal.NewFromInt(int64(cacheCreationTokens1h))
	dCompletionTokens := decimal.NewFromInt(int64(completionTokens))

	dInputPrice := decimal.NewFromFloat(priceTier.InputPrice)
	dOutputPrice := decimal.NewFromFloat(priceTier.OutputPrice)
	dCacheHitPrice := decimal.NewFromFloat(priceTier.CacheHitPrice)
	dCacheStorePrice := decimal.NewFromFloat(priceTier.CacheStorePrice)
	dCacheStorePrice5m := decimal.NewFromFloat(cacheStorePrice5m)
	dCacheStorePrice1h := decimal.NewFromFloat(cacheStorePrice1h)

	dMillion := decimal.NewFromInt(1000000)
	dQuotaPerUnit := decimal.NewFromFloat(common.QuotaPerUnit)
	dGroupRatio := decimal.NewFromFloat(groupRatio)

	inputQuota := dActualPromptTokens.Mul(dInputPrice).Div(dMillion)
	outputQuota := dCompletionTokens.Mul(dOutputPrice).Div(dMillion)
	cacheQuota := dCacheTokens.Mul(dCacheHitPrice).Div(dMillion)
	cacheCreationQuota := dCacheCreationTokensRemaining.Mul(dCacheStorePrice).Div(dMillion).
		Add(dCacheCreationTokens5m.Mul(dCacheStorePrice5m).Div(dMillion)).
		Add(dCacheCreationTokens1h.Mul(dCacheStorePrice1h).Div(dMillion))

	quotaDecimal := inputQuota.Add(outputQuota).Add(cacheQuota).Add(cacheCreationQuota).Mul(dQuotaPerUnit).Mul(dGroupRatio)

	tierRange = fmt.Sprintf("%d-%d", priceTier.MinTokens, priceTier.MaxTokens)
	return quotaDecimal.InexactFloat64(), true, tierRange
}

func RecalcLogRecord(log *Log) *Claude200KFixRecord {
	record := &Claude200KFixRecord{
		Log: log,
	}

	if !strings.Contains(strings.ToLower(log.ModelName), "claude") {
		record.CanRecalc = false
		record.SkipReason = "not_claude"
		return record
	}

	other := ParseLogOther(log.Other)

	if other.Claude200KReviewed {
		record.CanRecalc = false
		record.SkipReason = "already_reviewed"
		return record
	}

	if other.ModelPrice > 0 {
		record.CanRecalc = false
		record.SkipReason = "fixed_price"
		return record
	}

	groupRatio := other.GroupRatio
	if groupRatio <= 0 {
		groupRatio = 1.0
	}

	isNativeAPI := other.Claude
	cacheTokens := other.CacheTokens
	cacheCreationTokens := other.CacheCreationTokens
	cacheCreationTokens5m := other.CacheCreationTokens5m
	cacheCreationTokens1h := other.CacheCreationTokens1h

	correctQuota, tierFound, tierRange := RecalcClaudeQuotaWithTieredPricing(
		log.ModelName,
		log.PromptTokens,
		log.CompletionTokens,
		isNativeAPI,
		cacheTokens,
		cacheCreationTokens,
		cacheCreationTokens5m,
		cacheCreationTokens1h,
		groupRatio,
	)

	if !tierFound {
		record.CanRecalc = false
		record.SkipReason = "no_tiered_pricing"
		return record
	}

	correctQuotaInt := int(math.Round(correctQuota))

	var totalInput int
	if isNativeAPI {
		totalInput = log.PromptTokens + cacheTokens + cacheCreationTokens
	} else {
		totalInput = log.PromptTokens
	}

	// Look up tier to get prices for display
	inputTokensK := totalInput / 1000
	priceTier, _ := ratio_setting.GetPriceTierForTokens(log.ModelName, inputTokensK)

	record.CanRecalc = true
	record.CorrectQuota = correctQuotaInt
	record.QuotaDiff = correctQuotaInt - log.Quota
	record.TotalInput = totalInput
	record.TierRange = tierRange
	record.IsNativeAPI = isNativeAPI
	record.GroupRatio = groupRatio
	record.CacheTokens = cacheTokens
	record.CacheCreation = cacheCreationTokens
	record.CacheCreation5m = cacheCreationTokens5m
	record.CacheCreation1h = cacheCreationTokens1h
	if priceTier != nil {
		record.InputPrice = priceTier.InputPrice
		record.OutputPrice = priceTier.OutputPrice
		record.CacheHitPrice = priceTier.CacheHitPrice
	}

	return record
}

func ScanClaudeLogs(startTimestamp, endTimestamp int64, username, modelName string, channel int, page, pageSize int) ([]*Log, int64, error) {
	tx := LOG_DB.Where("type = ?", LogTypeConsume).
		Where("LOWER(model_name) LIKE ?", "%claude%")

	if startTimestamp > 0 {
		tx = tx.Where("created_at >= ?", startTimestamp)
	}
	if endTimestamp > 0 {
		tx = tx.Where("created_at <= ?", endTimestamp)
	}
	if username != "" {
		tx = tx.Where("username = ?", username)
	}
	if modelName != "" {
		tx = tx.Where("model_name LIKE ?", modelName)
	}
	if channel > 0 {
		tx = tx.Where("channel_id = ?", channel)
	}

	// Exclude already reviewed
	tx = tx.Where("other NOT LIKE ?", "%claude_200k_reviewed%")

	var total int64
	if err := tx.Model(&Log{}).Count(&total).Error; err != nil {
		return nil, 0, err
	}

	var logs []*Log
	offset := (page - 1) * pageSize
	if err := tx.Order("id desc").Limit(pageSize).Offset(offset).Find(&logs).Error; err != nil {
		return nil, 0, err
	}

	return logs, total, nil
}

func MarkLogsReviewed(logIds []int) error {
	if len(logIds) == 0 {
		return nil
	}

	var logs []*Log
	if err := LOG_DB.Where("id IN ?", logIds).Find(&logs).Error; err != nil {
		return err
	}

	for _, log := range logs {
		var otherMap map[string]interface{}
		if log.Other != "" {
			otherMap, _ = common.StrToMap(log.Other)
		}
		if otherMap == nil {
			otherMap = make(map[string]interface{})
		}
		otherMap["claude_200k_reviewed"] = true
		log.Other = common.MapToJsonStr(otherMap)
		if err := LOG_DB.Model(log).Update("other", log.Other).Error; err != nil {
			return fmt.Errorf("failed to update log %d: %w", log.Id, err)
		}
	}

	return nil
}

func ApplyClaude200KFix(logIds []int) (int, int64, error) {
	if len(logIds) == 0 {
		return 0, 0, nil
	}

	var logs []*Log
	if err := LOG_DB.Where("id IN ?", logIds).Find(&logs).Error; err != nil {
		return 0, 0, err
	}

	appliedCount := 0
	var totalDiff int64

	for _, log := range logs {
		record := RecalcLogRecord(log)
		if !record.CanRecalc || record.QuotaDiff <= 0 {
			continue
		}

		diff := record.QuotaDiff

		if err := DecreaseUserQuota(log.UserId, diff); err != nil {
			common.SysLog(fmt.Sprintf("claude_200k_fix: failed to decrease quota for user %d: %s", log.UserId, err.Error()))
			continue
		}

		// Mark as reviewed
		var otherMap map[string]interface{}
		if log.Other != "" {
			otherMap, _ = common.StrToMap(log.Other)
		}
		if otherMap == nil {
			otherMap = make(map[string]interface{})
		}
		otherMap["claude_200k_reviewed"] = true
		otherMap["claude_200k_fix_diff"] = diff
		log.Other = common.MapToJsonStr(otherMap)
		LOG_DB.Model(log).Update("other", log.Other)

		// Write a manage log for audit
		manageLog := &Log{
			UserId:    log.UserId,
			Username:  log.Username,
			CreatedAt: common.GetTimestamp(),
			Type:      LogTypeManage,
			Content:   fmt.Sprintf("Claude 200K 计费修复：补扣 %s，原始日志 ID %d，原始扣费 %s，应收 %s", formatQuota(diff), log.Id, formatQuota(log.Quota), formatQuota(record.CorrectQuota)),
			ModelName: log.ModelName,
			Quota:     -diff,
		}
		LOG_DB.Create(manageLog)

		appliedCount++
		totalDiff += int64(diff)
	}

	return appliedCount, totalDiff, nil
}

func formatQuota(quota int) string {
	return fmt.Sprintf("$%.4f", float64(quota)/common.QuotaPerUnit)
}

func GetClaudeLogs(logIds []int) ([]*Log, error) {
	var logs []*Log
	if err := LOG_DB.Where("id IN ?", logIds).Find(&logs).Error; err != nil {
		return nil, err
	}
	return logs, nil
}
