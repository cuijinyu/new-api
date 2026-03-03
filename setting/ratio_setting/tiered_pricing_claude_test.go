package ratio_setting

import (
	"math"
	"testing"

	"github.com/QuantumNous/new-api/common"
	"github.com/shopspring/decimal"
)

func resolveTieredCacheStorePrices(tier *PriceTier) (price5m float64, price1h float64) {
	price5m = tier.CacheStorePrice5m
	if price5m <= 0 {
		price5m = tier.CacheStorePrice
	}
	price1h = tier.CacheStorePrice1h
	if price1h <= 0 {
		price1h = tier.CacheStorePrice
	}
	return price5m, price1h
}

// 模拟 compatible_handler.go 中分段计费逻辑
func simulateCompatibleTieredBilling(
	modelName string,
	promptTokens int, // compatible 路径中，promptTokens 包含缓存和缓存创建
	cacheTokens int,
	cacheCreationTokens5m int,
	cacheCreationTokens1h int,
	cacheCreationTokensRemaining int,
	completionTokens int,
	groupRatio float64,
	initialTier *PriceTier,
) float64 {
	inputTokensK := promptTokens / 1000
	tier := initialTier
	if matchedTier, found := GetPriceTierForTokens(modelName, inputTokensK); found {
		tier = matchedTier
	}

	actualPromptTokens := promptTokens - cacheTokens - cacheCreationTokens5m - cacheCreationTokens1h - cacheCreationTokensRemaining
	if actualPromptTokens < 0 {
		actualPromptTokens = 0
	}

	price5m, price1h := resolveTieredCacheStorePrices(tier)

	dActualPromptTokens := decimal.NewFromInt(int64(actualPromptTokens))
	dCacheTokens := decimal.NewFromInt(int64(cacheTokens))
	dCacheCreationTokens5m := decimal.NewFromInt(int64(cacheCreationTokens5m))
	dCacheCreationTokens1h := decimal.NewFromInt(int64(cacheCreationTokens1h))
	dCacheCreationTokensRemaining := decimal.NewFromInt(int64(cacheCreationTokensRemaining))
	dCompletionTokens := decimal.NewFromInt(int64(completionTokens))

	dInputPrice := decimal.NewFromFloat(tier.InputPrice)
	dOutputPrice := decimal.NewFromFloat(tier.OutputPrice)
	dCacheHitPrice := decimal.NewFromFloat(tier.CacheHitPrice)
	dCacheStorePrice := decimal.NewFromFloat(tier.CacheStorePrice)
	dCacheStorePrice5m := decimal.NewFromFloat(price5m)
	dCacheStorePrice1h := decimal.NewFromFloat(price1h)

	dMillion := decimal.NewFromInt(1000000)
	dQuotaPerUnit := decimal.NewFromFloat(common.QuotaPerUnit)
	dGroupRatio := decimal.NewFromFloat(groupRatio)

	inputQuota := dActualPromptTokens.Mul(dInputPrice).Div(dMillion)
	outputQuota := dCompletionTokens.Mul(dOutputPrice).Div(dMillion)
	cacheQuota := dCacheTokens.Mul(dCacheHitPrice).Div(dMillion)
	cacheCreationQuota := dCacheCreationTokensRemaining.Mul(dCacheStorePrice).Div(dMillion).
		Add(dCacheCreationTokens5m.Mul(dCacheStorePrice5m).Div(dMillion)).
		Add(dCacheCreationTokens1h.Mul(dCacheStorePrice1h).Div(dMillion))

	quotaCalculateDecimal := inputQuota.Add(outputQuota).Add(cacheQuota).Add(cacheCreationQuota).Mul(dQuotaPerUnit).Mul(dGroupRatio)
	return quotaCalculateDecimal.InexactFloat64()
}

// 模拟 service/quota.go 中 PostClaudeConsumeQuota 的分段计费逻辑
func simulateNativeTieredBilling(
	modelName string,
	promptTokens int, // Claude 原生 input_tokens（不含缓存和缓存创建）
	cacheTokens int,
	cacheCreationTokens5m int,
	cacheCreationTokens1h int,
	cacheCreationTokensRemaining int,
	completionTokens int,
	groupRatio float64,
	initialTier *PriceTier,
) float64 {
	totalInputForClaude := promptTokens + cacheTokens + cacheCreationTokens5m + cacheCreationTokens1h + cacheCreationTokensRemaining
	inputTokensK := totalInputForClaude / 1000
	tier := initialTier
	if matchedTier, found := GetPriceTierForTokens(modelName, inputTokensK); found {
		tier = matchedTier
	}

	price5m, price1h := resolveTieredCacheStorePrices(tier)

	dActualPromptTokens := decimal.NewFromInt(int64(promptTokens))
	dCacheTokens := decimal.NewFromInt(int64(cacheTokens))
	dCacheCreationTokens5m := decimal.NewFromInt(int64(cacheCreationTokens5m))
	dCacheCreationTokens1h := decimal.NewFromInt(int64(cacheCreationTokens1h))
	dCacheCreationTokensRemaining := decimal.NewFromInt(int64(cacheCreationTokensRemaining))
	dCompletionTokens := decimal.NewFromInt(int64(completionTokens))

	dInputPrice := decimal.NewFromFloat(tier.InputPrice)
	dOutputPrice := decimal.NewFromFloat(tier.OutputPrice)
	dCacheHitPrice := decimal.NewFromFloat(tier.CacheHitPrice)
	dCacheStorePrice := decimal.NewFromFloat(tier.CacheStorePrice)
	dCacheStorePrice5m := decimal.NewFromFloat(price5m)
	dCacheStorePrice1h := decimal.NewFromFloat(price1h)

	dMillion := decimal.NewFromInt(1000000)
	dQuotaPerUnit := decimal.NewFromFloat(common.QuotaPerUnit)
	dGroupRatio := decimal.NewFromFloat(groupRatio)

	inputQuota := dActualPromptTokens.Mul(dInputPrice).Div(dMillion)
	outputQuota := dCompletionTokens.Mul(dOutputPrice).Div(dMillion)
	cacheQuota := dCacheTokens.Mul(dCacheHitPrice).Div(dMillion)
	cacheCreationQuota := dCacheCreationTokensRemaining.Mul(dCacheStorePrice).Div(dMillion).
		Add(dCacheCreationTokens5m.Mul(dCacheStorePrice5m).Div(dMillion)).
		Add(dCacheCreationTokens1h.Mul(dCacheStorePrice1h).Div(dMillion))

	quotaCalculateDecimal := inputQuota.Add(outputQuota).Add(cacheQuota).Add(cacheCreationQuota).Mul(dQuotaPerUnit).Mul(dGroupRatio)
	return quotaCalculateDecimal.InexactFloat64()
}

func TestClaudeTieredCacheStorePriceFallback(t *testing.T) {
	tier := &PriceTier{
		CacheStorePrice:   3.75,
		CacheStorePrice5m: 0,
		CacheStorePrice1h: 0,
	}
	price5m, price1h := resolveTieredCacheStorePrices(tier)
	if price5m != 3.75 || price1h != 3.75 {
		t.Fatalf("fallback failed, got 5m=%v 1h=%v", price5m, price1h)
	}

	tier = &PriceTier{
		CacheStorePrice:   7.5,
		CacheStorePrice5m: 9.0,
		CacheStorePrice1h: 0,
	}
	price5m, price1h = resolveTieredCacheStorePrices(tier)
	if price5m != 9.0 || price1h != 7.5 {
		t.Fatalf("partial fallback failed, got 5m=%v 1h=%v", price5m, price1h)
	}
}

func TestClaudeTieredPricingWithSplitCacheStorePrices(t *testing.T) {
	modelName := "claude-3-5-sonnet-20240620"

	InitTieredPricingSettings()
	tieredPricingMapMutex.Lock()
	tieredPricingMap[modelName] = &TieredPricing{
		Enabled: true,
		Tiers: []PriceTier{
			{
				MinTokens:       0,
				MaxTokens:       200, // 0-200K
				InputPrice:      3.0,
				OutputPrice:     15.0,
				CacheHitPrice:   0.3,
				CacheStorePrice: 3.75, // 5m/1h 均回退到此值
			},
			{
				MinTokens:         200,
				MaxTokens:         -1, // >200K
				InputPrice:        6.0,
				OutputPrice:       22.5,
				CacheHitPrice:     0.6,
				CacheStorePrice:   7.5,
				CacheStorePrice5m: 9.0, // 显式 5m 价格
				// 1h 不配置，回退到 7.5
			},
		},
	}
	tieredPricingMapMutex.Unlock()

	defer func() {
		tieredPricingMapMutex.Lock()
		delete(tieredPricingMap, modelName)
		tieredPricingMapMutex.Unlock()
	}()

	tests := []struct {
		name                         string
		isNative                     bool
		promptTokens                 int
		cacheTokens                  int
		cacheCreationTokens5m        int
		cacheCreationTokens1h        int
		cacheCreationTokensRemaining int
		completionTokens             int
		groupRatio                   float64
		expectedCostUSD              float64
	}{
		{
			name:                         "compatible <=200K fallback to cache_store_price",
			isNative:                     false,
			promptTokens:                 180000,
			cacheTokens:                  60000,
			cacheCreationTokens5m:        10000,
			cacheCreationTokens1h:        5000,
			cacheCreationTokensRemaining: 5000,
			completionTokens:             10000,
			groupRatio:                   1.0,
			// input 100k*3 + cache_read 60k*0.3 + creation(20k*3.75) + output 10k*15
			expectedCostUSD: 0.543,
		},
		{
			name:                         "compatible >200K with 5m explicit and 1h fallback",
			isNative:                     false,
			promptTokens:                 260000,
			cacheTokens:                  120000,
			cacheCreationTokens5m:        20000,
			cacheCreationTokens1h:        10000,
			cacheCreationTokensRemaining: 10000,
			completionTokens:             20000,
			groupRatio:                   1.0,
			// input 100k*6 + cache_read 120k*0.6 + creation(20k*9 + 10k*7.5 + 10k*7.5) + output 20k*22.5
			expectedCostUSD: 1.452,
		},
		{
			name:                         "native <=200K fallback to cache_store_price",
			isNative:                     true,
			promptTokens:                 100000, // 原生 input_tokens 不包含缓存
			cacheTokens:                  60000,
			cacheCreationTokens5m:        10000,
			cacheCreationTokens1h:        5000,
			cacheCreationTokensRemaining: 5000,
			completionTokens:             10000,
			groupRatio:                   1.0,
			expectedCostUSD:              0.543,
		},
		{
			name:                         "native >200K with 5m explicit and 1h fallback",
			isNative:                     true,
			promptTokens:                 100000, // 总输入 260k，命中第二档
			cacheTokens:                  120000,
			cacheCreationTokens5m:        20000,
			cacheCreationTokens1h:        10000,
			cacheCreationTokensRemaining: 10000,
			completionTokens:             20000,
			groupRatio:                   1.0,
			expectedCostUSD:              1.452,
		},
	}

	initialTier := &PriceTier{
		InputPrice:      3.0,
		OutputPrice:     15.0,
		CacheHitPrice:   0.3,
		CacheStorePrice: 3.75,
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var quota float64
			if tt.isNative {
				quota = simulateNativeTieredBilling(
					modelName,
					tt.promptTokens,
					tt.cacheTokens,
					tt.cacheCreationTokens5m,
					tt.cacheCreationTokens1h,
					tt.cacheCreationTokensRemaining,
					tt.completionTokens,
					tt.groupRatio,
					initialTier,
				)
			} else {
				quota = simulateCompatibleTieredBilling(
					modelName,
					tt.promptTokens,
					tt.cacheTokens,
					tt.cacheCreationTokens5m,
					tt.cacheCreationTokens1h,
					tt.cacheCreationTokensRemaining,
					tt.completionTokens,
					tt.groupRatio,
					initialTier,
				)
			}

			expectedQuota := tt.expectedCostUSD * common.QuotaPerUnit * tt.groupRatio
			if math.Abs(quota-expectedQuota) > 1.0 {
				t.Fatalf("expected quota %f, got %f", expectedQuota, quota)
			}
		})
	}
}
