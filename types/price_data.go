package types

import "fmt"

type GroupRatioInfo struct {
	GroupRatio        float64
	GroupSpecialRatio float64
	HasSpecialRatio   bool
}

type TieredPricingInfo struct {
	InputPrice      float64 // 当前区间的输入价格 USD/M tokens
	OutputPrice     float64 // 当前区间的输出价格 USD/M tokens
	CacheHitPrice   float64 // 当前区间的缓存命中价格 USD/M tokens
	CacheStorePrice float64 // 当前区间的缓存存储价格 USD/M tokens/hour
	TierMinTokens   int     // 当前区间最小 tokens（千）
	TierMaxTokens   int     // 当前区间最大 tokens（千）
}

type PriceData struct {
	FreeModel            bool
	ModelPrice           float64
	ModelRatio           float64
	CompletionRatio      float64
	CacheRatio           float64
	CacheCreationRatio   float64
	CacheCreation5mRatio float64
	CacheCreation1hRatio float64
	ImageRatio           float64
	AudioRatio           float64
	AudioCompletionRatio float64
	OtherRatios          map[string]float64
	UsePrice             bool
	QuotaToPreConsume    int // 预消耗额度
	GroupRatioInfo       GroupRatioInfo
	UseTieredPricing     bool                // 是否使用分段价格
	TieredPricingData    *TieredPricingInfo  // 分段价格数据（如果启用）
}

type PerCallPriceData struct {
	ModelPrice     float64
	Quota          int
	GroupRatioInfo GroupRatioInfo
}

func (p PriceData) ToSetting() string {
	baseStr := fmt.Sprintf("ModelPrice: %f, ModelRatio: %f, CompletionRatio: %f, CacheRatio: %f, GroupRatio: %f, UsePrice: %t, CacheCreationRatio: %f, CacheCreation5mRatio: %f, CacheCreation1hRatio: %f, QuotaToPreConsume: %d, ImageRatio: %f, AudioRatio: %f, AudioCompletionRatio: %f, UseTieredPricing: %t", p.ModelPrice, p.ModelRatio, p.CompletionRatio, p.CacheRatio, p.GroupRatioInfo.GroupRatio, p.UsePrice, p.CacheCreationRatio, p.CacheCreation5mRatio, p.CacheCreation1hRatio, p.QuotaToPreConsume, p.ImageRatio, p.AudioRatio, p.AudioCompletionRatio, p.UseTieredPricing)
	
	if p.UseTieredPricing && p.TieredPricingData != nil {
		tieredStr := fmt.Sprintf(", TieredPricingData: InputPrice: %f, OutputPrice: %f, CacheHitPrice: %f, CacheStorePrice: %f, TierMinTokens: %d, TierMaxTokens: %d", 
			p.TieredPricingData.InputPrice, 
			p.TieredPricingData.OutputPrice, 
			p.TieredPricingData.CacheHitPrice, 
			p.TieredPricingData.CacheStorePrice, 
			p.TieredPricingData.TierMinTokens, 
			p.TieredPricingData.TierMaxTokens)
		return baseStr + tieredStr
	}
	
	return baseStr
}
