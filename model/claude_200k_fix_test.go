package model

import (
	"encoding/json"
	"math"
	"testing"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/setting/ratio_setting"
	"github.com/shopspring/decimal"
)

// referenceNativeTieredBilling mirrors simulateNativeTieredBilling from
// setting/ratio_setting/tiered_pricing_claude_test.go exactly.
// It serves as the ground truth for native Claude API tiered billing.
func referenceNativeTieredBilling(
	modelName string,
	promptTokens int,
	cacheTokens int,
	cacheCreationTokens5m int,
	cacheCreationTokens1h int,
	cacheCreationTokensRemaining int,
	completionTokens int,
	groupRatio float64,
) float64 {
	totalInputForClaude := promptTokens + cacheTokens + cacheCreationTokens5m + cacheCreationTokens1h + cacheCreationTokensRemaining
	inputTokensK := totalInputForClaude / 1000
	priceTier, found := ratio_setting.GetPriceTierForTokens(modelName, inputTokensK)
	if !found {
		return 0
	}

	cacheStorePrice5m := priceTier.CacheStorePrice5m
	if cacheStorePrice5m <= 0 {
		cacheStorePrice5m = priceTier.CacheStorePrice
	}
	cacheStorePrice1h := priceTier.CacheStorePrice1h
	if cacheStorePrice1h <= 0 {
		cacheStorePrice1h = priceTier.CacheStorePrice
	}

	dActualPromptTokens := decimal.NewFromInt(int64(promptTokens))
	dCacheTokens := decimal.NewFromInt(int64(cacheTokens))
	dCacheCreationTokens5m := decimal.NewFromInt(int64(cacheCreationTokens5m))
	dCacheCreationTokens1h := decimal.NewFromInt(int64(cacheCreationTokens1h))
	dCacheCreationTokensRemaining := decimal.NewFromInt(int64(cacheCreationTokensRemaining))
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
	return quotaDecimal.InexactFloat64()
}

// referenceCompatibleTieredBilling mirrors simulateCompatibleTieredBilling from
// setting/ratio_setting/tiered_pricing_claude_test.go exactly.
func referenceCompatibleTieredBilling(
	modelName string,
	promptTokens int,
	cacheTokens int,
	cacheCreationTokens5m int,
	cacheCreationTokens1h int,
	cacheCreationTokensRemaining int,
	completionTokens int,
	groupRatio float64,
) float64 {
	inputTokensK := promptTokens / 1000
	priceTier, found := ratio_setting.GetPriceTierForTokens(modelName, inputTokensK)
	if !found {
		return 0
	}

	actualPromptTokens := promptTokens - cacheTokens - cacheCreationTokens5m - cacheCreationTokens1h - cacheCreationTokensRemaining
	if actualPromptTokens < 0 {
		actualPromptTokens = 0
	}

	cacheStorePrice5m := priceTier.CacheStorePrice5m
	if cacheStorePrice5m <= 0 {
		cacheStorePrice5m = priceTier.CacheStorePrice
	}
	cacheStorePrice1h := priceTier.CacheStorePrice1h
	if cacheStorePrice1h <= 0 {
		cacheStorePrice1h = priceTier.CacheStorePrice
	}

	dActualPromptTokens := decimal.NewFromInt(int64(actualPromptTokens))
	dCacheTokens := decimal.NewFromInt(int64(cacheTokens))
	dCacheCreationTokens5m := decimal.NewFromInt(int64(cacheCreationTokens5m))
	dCacheCreationTokens1h := decimal.NewFromInt(int64(cacheCreationTokens1h))
	dCacheCreationTokensRemaining := decimal.NewFromInt(int64(cacheCreationTokensRemaining))
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
	return quotaDecimal.InexactFloat64()
}

func setupTestTieredPricing(t *testing.T, modelName string) {
	t.Helper()
	ratio_setting.InitTieredPricingSettings()
	config := map[string]interface{}{
		modelName: map[string]interface{}{
			"enabled": true,
			"tiers": []map[string]interface{}{
				{
					"min_tokens":        0,
					"max_tokens":        200,
					"input_price":       3.0,
					"output_price":      15.0,
					"cache_hit_price":   0.3,
					"cache_store_price": 3.75,
				},
				{
					"min_tokens":          200,
					"max_tokens":          -1,
					"input_price":         6.0,
					"output_price":        22.5,
					"cache_hit_price":     0.6,
					"cache_store_price":   7.5,
					"cache_store_price_5m": 9.0,
				},
			},
		},
	}
	jsonBytes, _ := json.Marshal(config)
	if err := ratio_setting.UpdateTieredPricingByJSONString(string(jsonBytes)); err != nil {
		t.Fatalf("failed to setup tiered pricing: %v", err)
	}
}

func cleanupTestTieredPricing(t *testing.T) {
	t.Helper()
	ratio_setting.UpdateTieredPricingByJSONString("{}")
}

// TestRecalcMatchesNativeTieredBilling verifies that RecalcClaudeQuotaWithTieredPricing
// produces identical results to the reference native tiered billing implementation
// (which mirrors PostClaudeConsumeQuota's tiered pricing path).
func TestRecalcMatchesNativeTieredBilling(t *testing.T) {
	modelName := "claude-3-5-sonnet-20240620"
	setupTestTieredPricing(t, modelName)
	defer cleanupTestTieredPricing(t)

	tests := []struct {
		name                         string
		promptTokens                 int
		cacheTokens                  int
		cacheCreationTokens5m        int
		cacheCreationTokens1h        int
		cacheCreationTokensRemaining int
		completionTokens             int
		groupRatio                   float64
	}{
		{
			name:                         "native <=200K fallback to cache_store_price",
			promptTokens:                 100000,
			cacheTokens:                  60000,
			cacheCreationTokens5m:        10000,
			cacheCreationTokens1h:        5000,
			cacheCreationTokensRemaining: 5000,
			completionTokens:             10000,
			groupRatio:                   1.0,
		},
		{
			name:                         "native >200K with 5m explicit and 1h fallback",
			promptTokens:                 100000,
			cacheTokens:                  120000,
			cacheCreationTokens5m:        20000,
			cacheCreationTokens1h:        10000,
			cacheCreationTokensRemaining: 10000,
			completionTokens:             20000,
			groupRatio:                   1.0,
		},
		{
			name:             "native simple no cache <=200K",
			promptTokens:     50000,
			completionTokens: 5000,
			groupRatio:       1.0,
		},
		{
			name:             "native simple no cache >200K",
			promptTokens:     250000,
			completionTokens: 5000,
			groupRatio:       1.0,
		},
		{
			name:                         "native with groupRatio 1.5",
			promptTokens:                 100000,
			cacheTokens:                  120000,
			cacheCreationTokens5m:        20000,
			cacheCreationTokens1h:        10000,
			cacheCreationTokensRemaining: 10000,
			completionTokens:             20000,
			groupRatio:                   1.5,
		},
		{
			name:             "native boundary exactly 200K (200*1000 tokens)",
			promptTokens:     200000,
			completionTokens: 1000,
			groupRatio:       1.0,
		},
		{
			name:             "native boundary 200001 tokens",
			promptTokens:     200001,
			completionTokens: 1000,
			groupRatio:       1.0,
		},
		{
			name:                         "native only cache tokens >200K",
			promptTokens:                 0,
			cacheTokens:                  210000,
			cacheCreationTokens5m:        0,
			cacheCreationTokens1h:        0,
			cacheCreationTokensRemaining: 0,
			completionTokens:             100,
			groupRatio:                   1.0,
		},
		{
			name:                         "native only cache creation >200K",
			promptTokens:                 0,
			cacheTokens:                  0,
			cacheCreationTokens5m:        120000,
			cacheCreationTokens1h:        50000,
			cacheCreationTokensRemaining: 40000,
			completionTokens:             100,
			groupRatio:                   1.0,
		},
		{
			name:                         "native zero tokens",
			promptTokens:                 0,
			cacheTokens:                  0,
			cacheCreationTokens5m:        0,
			cacheCreationTokens1h:        0,
			cacheCreationTokensRemaining: 0,
			completionTokens:             0,
			groupRatio:                   1.0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			totalCacheCreation := tt.cacheCreationTokens5m + tt.cacheCreationTokens1h + tt.cacheCreationTokensRemaining

			referenceQuota := referenceNativeTieredBilling(
				modelName,
				tt.promptTokens,
				tt.cacheTokens,
				tt.cacheCreationTokens5m,
				tt.cacheCreationTokens1h,
				tt.cacheCreationTokensRemaining,
				tt.completionTokens,
				tt.groupRatio,
			)

			recalcQuota, tierFound, _ := RecalcClaudeQuotaWithTieredPricing(
				modelName,
				tt.promptTokens,
				tt.completionTokens,
				true, // isNativeAPI
				tt.cacheTokens,
				totalCacheCreation,
				tt.cacheCreationTokens5m,
				tt.cacheCreationTokens1h,
				tt.groupRatio,
			)

			if !tierFound {
				t.Fatalf("tier not found for model %s", modelName)
			}

			if math.Abs(referenceQuota-recalcQuota) > 1.0 {
				t.Errorf("mismatch: reference=%f, recalc=%f, diff=%f",
					referenceQuota, recalcQuota, referenceQuota-recalcQuota)
			}
		})
	}
}

// TestRecalcMatchesCompatibleTieredBilling verifies alignment with the compatible handler path.
func TestRecalcMatchesCompatibleTieredBilling(t *testing.T) {
	modelName := "claude-3-5-sonnet-20240620"
	setupTestTieredPricing(t, modelName)
	defer cleanupTestTieredPricing(t)

	tests := []struct {
		name                         string
		promptTokens                 int // includes cache in compatible path
		cacheTokens                  int
		cacheCreationTokens5m        int
		cacheCreationTokens1h        int
		cacheCreationTokensRemaining int
		completionTokens             int
		groupRatio                   float64
	}{
		{
			name:                         "compatible <=200K fallback to cache_store_price",
			promptTokens:                 180000,
			cacheTokens:                  60000,
			cacheCreationTokens5m:        10000,
			cacheCreationTokens1h:        5000,
			cacheCreationTokensRemaining: 5000,
			completionTokens:             10000,
			groupRatio:                   1.0,
		},
		{
			name:                         "compatible >200K with 5m explicit and 1h fallback",
			promptTokens:                 260000,
			cacheTokens:                  120000,
			cacheCreationTokens5m:        20000,
			cacheCreationTokens1h:        10000,
			cacheCreationTokensRemaining: 10000,
			completionTokens:             20000,
			groupRatio:                   1.0,
		},
		{
			name:             "compatible simple no cache <=200K",
			promptTokens:     150000,
			completionTokens: 5000,
			groupRatio:       1.0,
		},
		{
			name:             "compatible simple no cache >200K",
			promptTokens:     250000,
			completionTokens: 5000,
			groupRatio:       1.0,
		},
		{
			name:                         "compatible with groupRatio 2.0",
			promptTokens:                 260000,
			cacheTokens:                  120000,
			cacheCreationTokens5m:        20000,
			cacheCreationTokens1h:        10000,
			cacheCreationTokensRemaining: 10000,
			completionTokens:             20000,
			groupRatio:                   2.0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			totalCacheCreation := tt.cacheCreationTokens5m + tt.cacheCreationTokens1h + tt.cacheCreationTokensRemaining

			referenceQuota := referenceCompatibleTieredBilling(
				modelName,
				tt.promptTokens,
				tt.cacheTokens,
				tt.cacheCreationTokens5m,
				tt.cacheCreationTokens1h,
				tt.cacheCreationTokensRemaining,
				tt.completionTokens,
				tt.groupRatio,
			)

			recalcQuota, tierFound, _ := RecalcClaudeQuotaWithTieredPricing(
				modelName,
				tt.promptTokens,
				tt.completionTokens,
				false, // isNativeAPI = false for compatible
				tt.cacheTokens,
				totalCacheCreation,
				tt.cacheCreationTokens5m,
				tt.cacheCreationTokens1h,
				tt.groupRatio,
			)

			if !tierFound {
				t.Fatalf("tier not found for model %s", modelName)
			}

			if math.Abs(referenceQuota-recalcQuota) > 1.0 {
				t.Errorf("mismatch: reference=%f, recalc=%f, diff=%f",
					referenceQuota, recalcQuota, referenceQuota-recalcQuota)
			}
		})
	}
}

// TestRecalcExpectedCostUSD verifies against known USD cost expectations
// (same test data as TestClaudeTieredPricingWithSplitCacheStorePrices).
func TestRecalcExpectedCostUSD(t *testing.T) {
	modelName := "claude-3-5-sonnet-20240620"
	setupTestTieredPricing(t, modelName)
	defer cleanupTestTieredPricing(t)

	tests := []struct {
		name             string
		isNative         bool
		promptTokens     int
		cacheTokens      int
		cacheCreation5m  int
		cacheCreation1h  int
		cacheCreationRem int
		completionTokens int
		groupRatio       float64
		expectedCostUSD  float64
	}{
		{
			name:             "compatible <=200K",
			isNative:         false,
			promptTokens:     180000,
			cacheTokens:      60000,
			cacheCreation5m:  10000,
			cacheCreation1h:  5000,
			cacheCreationRem: 5000,
			completionTokens: 10000,
			groupRatio:       1.0,
			expectedCostUSD:  0.543,
		},
		{
			name:             "compatible >200K",
			isNative:         false,
			promptTokens:     260000,
			cacheTokens:      120000,
			cacheCreation5m:  20000,
			cacheCreation1h:  10000,
			cacheCreationRem: 10000,
			completionTokens: 20000,
			groupRatio:       1.0,
			expectedCostUSD:  1.452,
		},
		{
			name:             "native <=200K",
			isNative:         true,
			promptTokens:     100000,
			cacheTokens:      60000,
			cacheCreation5m:  10000,
			cacheCreation1h:  5000,
			cacheCreationRem: 5000,
			completionTokens: 10000,
			groupRatio:       1.0,
			expectedCostUSD:  0.543,
		},
		{
			name:             "native >200K",
			isNative:         true,
			promptTokens:     100000,
			cacheTokens:      120000,
			cacheCreation5m:  20000,
			cacheCreation1h:  10000,
			cacheCreationRem: 10000,
			completionTokens: 20000,
			groupRatio:       1.0,
			expectedCostUSD:  1.452,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			totalCacheCreation := tt.cacheCreation5m + tt.cacheCreation1h + tt.cacheCreationRem

			recalcQuota, tierFound, _ := RecalcClaudeQuotaWithTieredPricing(
				modelName,
				tt.promptTokens,
				tt.completionTokens,
				tt.isNative,
				tt.cacheTokens,
				totalCacheCreation,
				tt.cacheCreation5m,
				tt.cacheCreation1h,
				tt.groupRatio,
			)

			if !tierFound {
				t.Fatalf("tier not found")
			}

			expectedQuota := tt.expectedCostUSD * common.QuotaPerUnit * tt.groupRatio
			if math.Abs(recalcQuota-expectedQuota) > 1.0 {
				t.Errorf("expected quota %f (USD $%f), got %f (USD $%f), diff=%f",
					expectedQuota, tt.expectedCostUSD,
					recalcQuota, recalcQuota/common.QuotaPerUnit,
					recalcQuota-expectedQuota)
			}
		})
	}
}

// TestRecalcLogRecordFromOtherJSON tests the full pipeline: parse other JSON -> recalc.
func TestRecalcLogRecordFromOtherJSON(t *testing.T) {
	modelName := "claude-3-5-sonnet-20240620"
	setupTestTieredPricing(t, modelName)
	defer cleanupTestTieredPricing(t)

	tests := []struct {
		name             string
		log              *Log
		other            map[string]interface{}
		expectCanRecalc  bool
		expectSkipReason string
		expectedCostUSD  float64
	}{
		{
			name: "native Claude record <=200K",
			log: &Log{
				Id:               1,
				UserId:           100,
				Username:         "testuser",
				ModelName:        modelName,
				PromptTokens:     100000,
				CompletionTokens: 10000,
				Quota:            100000, // old incorrect quota
			},
			other: map[string]interface{}{
				"claude":                true,
				"group_ratio":          1.0,
				"cache_tokens":         60000,
				"cache_creation_tokens": 20000,
				"cache_creation_tokens_5m": 10000,
				"cache_creation_tokens_1h": 5000,
			},
			expectCanRecalc: true,
			expectedCostUSD: 0.543,
		},
		{
			name: "non-Claude model skipped",
			log: &Log{
				Id:               2,
				ModelName:        "gpt-4o",
				PromptTokens:     300000,
				CompletionTokens: 1000,
				Quota:            100000,
			},
			other:            map[string]interface{}{},
			expectCanRecalc:  false,
			expectSkipReason: "not_claude",
		},
		{
			name: "fixed price model skipped",
			log: &Log{
				Id:               3,
				ModelName:        modelName,
				PromptTokens:     100000,
				CompletionTokens: 1000,
				Quota:            50000,
			},
			other: map[string]interface{}{
				"claude":      true,
				"model_price": 0.05,
				"group_ratio": 1.0,
			},
			expectCanRecalc:  false,
			expectSkipReason: "fixed_price",
		},
		{
			name: "already reviewed skipped",
			log: &Log{
				Id:               4,
				ModelName:        modelName,
				PromptTokens:     100000,
				CompletionTokens: 1000,
				Quota:            50000,
			},
			other: map[string]interface{}{
				"claude":               true,
				"group_ratio":          1.0,
				"claude_200k_reviewed": true,
			},
			expectCanRecalc:  false,
			expectSkipReason: "already_reviewed",
		},
		{
			name: "model without tiered pricing config",
			log: &Log{
				Id:               5,
				ModelName:        "claude-unknown-model",
				PromptTokens:     100000,
				CompletionTokens: 1000,
				Quota:            50000,
			},
			other: map[string]interface{}{
				"claude":      true,
				"group_ratio": 1.0,
			},
			expectCanRecalc:  false,
			expectSkipReason: "no_tiered_pricing",
		},
		{
			name: "missing group_ratio defaults to 1.0",
			log: &Log{
				Id:               6,
				ModelName:        modelName,
				PromptTokens:     100000,
				CompletionTokens: 10000,
				Quota:            100000,
			},
			other: map[string]interface{}{
				"claude":                true,
				"cache_tokens":         60000,
				"cache_creation_tokens": 20000,
				"cache_creation_tokens_5m": 10000,
				"cache_creation_tokens_1h": 5000,
			},
			expectCanRecalc: true,
			expectedCostUSD: 0.543,
		},
		{
			name: "compatible handler (no claude flag)",
			log: &Log{
				Id:               7,
				ModelName:        modelName,
				PromptTokens:     180000, // includes cache in compatible
				CompletionTokens: 10000,
				Quota:            100000,
			},
			other: map[string]interface{}{
				"group_ratio":          1.0,
				"cache_tokens":         60000,
				"cache_creation_tokens": 20000,
				"cache_creation_tokens_5m": 10000,
				"cache_creation_tokens_1h": 5000,
			},
			expectCanRecalc: true,
			expectedCostUSD: 0.543,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			otherBytes, _ := json.Marshal(tt.other)
			tt.log.Other = string(otherBytes)

			record := RecalcLogRecord(tt.log)

			if record.CanRecalc != tt.expectCanRecalc {
				t.Errorf("CanRecalc = %v, want %v (skip_reason=%s)",
					record.CanRecalc, tt.expectCanRecalc, record.SkipReason)
			}

			if !tt.expectCanRecalc {
				if record.SkipReason != tt.expectSkipReason {
					t.Errorf("SkipReason = %q, want %q", record.SkipReason, tt.expectSkipReason)
				}
				return
			}

			if tt.expectedCostUSD > 0 {
				expectedQuota := tt.expectedCostUSD * common.QuotaPerUnit
				if math.Abs(float64(record.CorrectQuota)-expectedQuota) > 2.0 {
					t.Errorf("CorrectQuota = %d (USD $%.6f), want ~%f (USD $%.6f)",
						record.CorrectQuota, float64(record.CorrectQuota)/common.QuotaPerUnit,
						expectedQuota, tt.expectedCostUSD)
				}
			}
		})
	}
}

// TestRecalcDiffCalculation verifies the diff (correctQuota - originalQuota) is computed correctly.
func TestRecalcDiffCalculation(t *testing.T) {
	modelName := "claude-3-5-sonnet-20240620"
	setupTestTieredPricing(t, modelName)
	defer cleanupTestTieredPricing(t)

	// A record that was billed at a lower rate (old system) but should be billed higher (tiered pricing)
	other := map[string]interface{}{
		"claude":      true,
		"group_ratio": 1.0,
	}
	otherBytes, _ := json.Marshal(other)

	log := &Log{
		Id:               100,
		UserId:           1,
		Username:         "testuser",
		ModelName:        modelName,
		PromptTokens:     250000, // >200K, should hit high tier
		CompletionTokens: 10000,
		Quota:            100000, // artificially low original quota
		Other:            string(otherBytes),
	}

	record := RecalcLogRecord(log)

	if !record.CanRecalc {
		t.Fatalf("expected CanRecalc=true, got false (reason=%s)", record.SkipReason)
	}

	// >200K tier: input $6/M, output $22.5/M
	// correctQuota = (250000 * 6 / 1M + 10000 * 22.5 / 1M) * QuotaPerUnit * 1.0
	//             = (1.5 + 0.225) * 500000 = 862500
	expectedCorrectQuota := (250000.0*6.0/1000000.0 + 10000.0*22.5/1000000.0) * common.QuotaPerUnit
	if math.Abs(float64(record.CorrectQuota)-expectedCorrectQuota) > 2.0 {
		t.Errorf("CorrectQuota = %d, want ~%f", record.CorrectQuota, expectedCorrectQuota)
	}

	expectedDiff := int(math.Round(expectedCorrectQuota)) - 100000
	if record.QuotaDiff != expectedDiff {
		t.Errorf("QuotaDiff = %d, want %d", record.QuotaDiff, expectedDiff)
	}

	if record.QuotaDiff <= 0 {
		t.Errorf("expected positive diff (underbilled), got %d", record.QuotaDiff)
	}
}

// TestRecalcNoTieredPricing verifies behavior when no tiered pricing is configured.
func TestRecalcNoTieredPricing(t *testing.T) {
	cleanupTestTieredPricing(t)

	other := map[string]interface{}{
		"claude":      true,
		"group_ratio": 1.0,
	}
	otherBytes, _ := json.Marshal(other)

	log := &Log{
		Id:               200,
		ModelName:        "claude-some-unknown-model",
		PromptTokens:     100000,
		CompletionTokens: 1000,
		Quota:            50000,
		Other:            string(otherBytes),
	}

	record := RecalcLogRecord(log)
	if record.CanRecalc {
		t.Errorf("expected CanRecalc=false when no tiered pricing configured")
	}
	if record.SkipReason != "no_tiered_pricing" {
		t.Errorf("SkipReason = %q, want %q", record.SkipReason, "no_tiered_pricing")
	}
}

// TestParseLogOther verifies JSON parsing of the other field.
func TestParseLogOther(t *testing.T) {
	tests := []struct {
		name   string
		input  string
		check  func(t *testing.T, p LogOtherParsed)
	}{
		{
			name:  "empty string",
			input: "",
			check: func(t *testing.T, p LogOtherParsed) {
				if p.Claude || p.GroupRatio != 0 {
					t.Error("expected zero values for empty string")
				}
			},
		},
		{
			name:  "full Claude record",
			input: `{"claude":true,"group_ratio":1.5,"model_ratio":2.5,"completion_ratio":5.0,"cache_tokens":60000,"cache_ratio":0.1,"cache_creation_tokens":20000,"cache_creation_ratio":1.25,"cache_creation_tokens_5m":10000,"cache_creation_ratio_5m":1.25,"cache_creation_tokens_1h":5000,"cache_creation_ratio_1h":2.0,"model_price":0,"claude_200k":true,"tiered_pricing":false}`,
			check: func(t *testing.T, p LogOtherParsed) {
				if !p.Claude {
					t.Error("expected Claude=true")
				}
				if p.GroupRatio != 1.5 {
					t.Errorf("GroupRatio = %f, want 1.5", p.GroupRatio)
				}
				if p.CacheTokens != 60000 {
					t.Errorf("CacheTokens = %d, want 60000", p.CacheTokens)
				}
				if p.CacheCreationTokens != 20000 {
					t.Errorf("CacheCreationTokens = %d, want 20000", p.CacheCreationTokens)
				}
				if p.CacheCreationTokens5m != 10000 {
					t.Errorf("CacheCreationTokens5m = %d, want 10000", p.CacheCreationTokens5m)
				}
				if p.CacheCreationTokens1h != 5000 {
					t.Errorf("CacheCreationTokens1h = %d, want 5000", p.CacheCreationTokens1h)
				}
				if !p.Claude200K {
					t.Error("expected Claude200K=true")
				}
			},
		},
		{
			name:  "invalid JSON",
			input: "not json",
			check: func(t *testing.T, p LogOtherParsed) {
				if p.Claude || p.GroupRatio != 0 {
					t.Error("expected zero values for invalid JSON")
				}
			},
		},
		{
			name:  "missing optional fields",
			input: `{"claude":true,"group_ratio":1.0}`,
			check: func(t *testing.T, p LogOtherParsed) {
				if !p.Claude {
					t.Error("expected Claude=true")
				}
				if p.CacheTokens != 0 {
					t.Errorf("CacheTokens = %d, want 0", p.CacheTokens)
				}
				if p.CacheCreationTokens5m != 0 {
					t.Errorf("CacheCreationTokens5m = %d, want 0", p.CacheCreationTokens5m)
				}
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			parsed := ParseLogOther(tt.input)
			tt.check(t, parsed)
		})
	}
}
