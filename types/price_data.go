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
	// Claude 专用：支持分段下 5m/1h 缓存写入独立价格
	// 为 0 时回退到 CacheStorePrice
	CacheStorePrice5m float64 // 当前区间 5m 缓存写入价格 USD/M tokens
	CacheStorePrice1h float64 // 当前区间 1h 缓存写入价格 USD/M tokens
	TierMinTokens     int     // 当前区间最小 tokens（千）
	TierMaxTokens     int     // 当前区间最大 tokens（千）
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
	ImageCompletionRatio float64
	AudioRatio           float64
	AudioCompletionRatio float64
	OtherRatios          map[string]float64
	UsePrice             bool
	QuotaToPreConsume    int // 预消耗额度
	GroupRatioInfo       GroupRatioInfo
	UseTieredPricing     bool               // 是否使用分段价格
	TieredPricingData    *TieredPricingInfo // 分段价格数据（如果启用）
	// ConditionalPricing 条件计费乘数（时段 / 请求头 / 请求体）。
	// 预扣费与结算两处共用同一份求值结果，保证一致并写入对账快照。
	// 为 nil 或 Multiplier<=0 时表示未命中，乘数视为 1.0。
	ConditionalPricing *ConditionalPricingInfo
}

// ConditionalPricingInfo 条件计费命中快照。
type ConditionalPricingInfo struct {
	Multiplier   float64           // 命中乘数（未命中为 1.0）
	Matched      bool              // 是否命中
	MatchedRules []string          // 命中规则标识
	FieldValues  map[string]string // 被引用 header/param 字段的实际取值
}

// CondMultiplier 返回有效的条件乘数（nil / 非法时回退 1.0）。
func (p PriceData) CondMultiplier() float64 {
	if p.ConditionalPricing == nil || p.ConditionalPricing.Multiplier <= 0 {
		return 1.0
	}
	return p.ConditionalPricing.Multiplier
}

type PerCallPriceData struct {
	ModelPrice     float64
	Quota          int
	GroupRatioInfo GroupRatioInfo
}

func (p PriceData) ToSetting() string {
	baseStr := fmt.Sprintf("ModelPrice: %f, ModelRatio: %f, CompletionRatio: %f, CacheRatio: %f, GroupRatio: %f, UsePrice: %t, CacheCreationRatio: %f, CacheCreation5mRatio: %f, CacheCreation1hRatio: %f, QuotaToPreConsume: %d, ImageRatio: %f, ImageCompletionRatio: %f, AudioRatio: %f, AudioCompletionRatio: %f, UseTieredPricing: %t", p.ModelPrice, p.ModelRatio, p.CompletionRatio, p.CacheRatio, p.GroupRatioInfo.GroupRatio, p.UsePrice, p.CacheCreationRatio, p.CacheCreation5mRatio, p.CacheCreation1hRatio, p.QuotaToPreConsume, p.ImageRatio, p.ImageCompletionRatio, p.AudioRatio, p.AudioCompletionRatio, p.UseTieredPricing)

	if p.UseTieredPricing && p.TieredPricingData != nil {
		tieredStr := fmt.Sprintf(", TieredPricingData: InputPrice: %f, OutputPrice: %f, CacheHitPrice: %f, CacheStorePrice: %f, CacheStorePrice5m: %f, CacheStorePrice1h: %f, TierMinTokens: %d, TierMaxTokens: %d",
			p.TieredPricingData.InputPrice,
			p.TieredPricingData.OutputPrice,
			p.TieredPricingData.CacheHitPrice,
			p.TieredPricingData.CacheStorePrice,
			p.TieredPricingData.CacheStorePrice5m,
			p.TieredPricingData.CacheStorePrice1h,
			p.TieredPricingData.TierMinTokens,
			p.TieredPricingData.TierMaxTokens)
		return baseStr + tieredStr
	}

	return baseStr
}
