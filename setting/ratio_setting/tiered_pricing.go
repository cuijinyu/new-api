package ratio_setting

import (
	"encoding/json"
	"sort"
	"strings"
	"sync"

	"github.com/QuantumNous/new-api/common"
)

// PriceTier 单个价格区间
type PriceTier struct {
	MinTokens       int     `json:"min_tokens"`        // 区间最小值（千 tokens）
	MaxTokens       int     `json:"max_tokens"`        // 区间最大值（千 tokens），-1 表示无上限
	InputPrice      float64 `json:"input_price"`       // 输入价格 USD/M tokens
	OutputPrice     float64 `json:"output_price"`      // 输出价格 USD/M tokens
	CacheHitPrice   float64 `json:"cache_hit_price"`   // 缓存命中价格 USD/M tokens
	CacheStorePrice float64 `json:"cache_store_price"` // 缓存存储价格 USD/M tokens/hour
}

// TieredPricing 模型的分段价格配置
type TieredPricing struct {
	Enabled bool        `json:"enabled"`
	Tiers   []PriceTier `json:"tiers"`
}

var (
	tieredPricingMap      map[string]*TieredPricing = nil
	tieredPricingMapMutex                           = sync.RWMutex{}
)

// InitTieredPricingSettings initializes the tiered pricing map
func InitTieredPricingSettings() {
	tieredPricingMapMutex.Lock()
	defer tieredPricingMapMutex.Unlock()
	if tieredPricingMap == nil {
		tieredPricingMap = make(map[string]*TieredPricing)
	}
}

// GetTieredPricingMap returns the tiered pricing map
func GetTieredPricingMap() map[string]*TieredPricing {
	tieredPricingMapMutex.RLock()
	defer tieredPricingMapMutex.RUnlock()
	return tieredPricingMap
}

// GetTieredPricingCopy returns a deep copy of the tiered pricing map
func GetTieredPricingCopy() map[string]*TieredPricing {
	tieredPricingMapMutex.RLock()
	defer tieredPricingMapMutex.RUnlock()
	copyMap := make(map[string]*TieredPricing, len(tieredPricingMap))
	for k, v := range tieredPricingMap {
		if v == nil {
			copyMap[k] = nil
			continue
		}
		// Deep copy the TieredPricing struct
		tiersCopy := make([]PriceTier, len(v.Tiers))
		copy(tiersCopy, v.Tiers)
		copyMap[k] = &TieredPricing{
			Enabled: v.Enabled,
			Tiers:   tiersCopy,
		}
	}
	return copyMap
}

// TieredPricing2JSONString converts the tiered pricing map to a JSON string
func TieredPricing2JSONString() string {
	tieredPricingMapMutex.RLock()
	defer tieredPricingMapMutex.RUnlock()
	jsonBytes, err := json.Marshal(tieredPricingMap)
	if err != nil {
		common.SysLog("error marshalling tiered pricing: " + err.Error())
		return "{}"
	}
	return string(jsonBytes)
}

// UpdateTieredPricingByJSONString updates the tiered pricing map from a JSON string
func UpdateTieredPricingByJSONString(jsonStr string) error {
	tieredPricingMapMutex.Lock()
	defer tieredPricingMapMutex.Unlock()

	newMap := make(map[string]*TieredPricing)
	err := json.Unmarshal([]byte(jsonStr), &newMap)
	if err != nil {
		return err
	}

	// Sort tiers by MinTokens for each model
	for _, pricing := range newMap {
		if pricing != nil && len(pricing.Tiers) > 0 {
			sort.Slice(pricing.Tiers, func(i, j int) bool {
				return pricing.Tiers[i].MinTokens < pricing.Tiers[j].MinTokens
			})
		}
	}

	tieredPricingMap = newMap
	InvalidateExposedDataCache()
	return nil
}

// GetTieredPricing returns the tiered pricing configuration for a model
// Supports wildcard matching (e.g., "doubao-seed-*" matches "doubao-seed-1.6")
func GetTieredPricing(modelName string) (*TieredPricing, bool) {
	tieredPricingMapMutex.RLock()
	defer tieredPricingMapMutex.RUnlock()

	// First try exact match
	if pricing, ok := tieredPricingMap[modelName]; ok && pricing != nil {
		return pricing, true
	}

	// Then try wildcard match
	for pattern, pricing := range tieredPricingMap {
		if pricing == nil || !pricing.Enabled {
			continue
		}
		if matchWildcard(pattern, modelName) {
			return pricing, true
		}
	}

	return nil, false
}

// GetPriceTierForTokens returns the price tier for a given input token count (in thousands)
// inputTokensK is the input token count in thousands (e.g., 100 means 100K tokens)
func GetPriceTierForTokens(modelName string, inputTokensK int) (*PriceTier, bool) {
	pricing, ok := GetTieredPricing(modelName)
	if !ok || !pricing.Enabled || len(pricing.Tiers) == 0 {
		return nil, false
	}

	// Find the appropriate tier for the given token count
	// Tiers are sorted by MinTokens in ascending order
	var matchedTier *PriceTier
	for i := range pricing.Tiers {
		tier := &pricing.Tiers[i]
		// Check if inputTokensK falls within this tier's range
		if inputTokensK >= tier.MinTokens {
			// Check upper bound: -1 means no upper limit
			if tier.MaxTokens == -1 || inputTokensK < tier.MaxTokens {
				matchedTier = tier
				break
			}
			// If inputTokensK equals MaxTokens, it belongs to the next tier
			// So we continue to check the next tier
			if inputTokensK >= tier.MaxTokens {
				continue
			}
		}
	}

	// If no tier matched but we have tiers, use the last tier (highest range)
	if matchedTier == nil && len(pricing.Tiers) > 0 {
		// Find the tier with MaxTokens == -1 (unlimited) or the highest range
		for i := len(pricing.Tiers) - 1; i >= 0; i-- {
			if pricing.Tiers[i].MaxTokens == -1 {
				matchedTier = &pricing.Tiers[i]
				break
			}
		}
		// If still no match, use the last tier
		if matchedTier == nil {
			matchedTier = &pricing.Tiers[len(pricing.Tiers)-1]
		}
	}

	if matchedTier != nil {
		return matchedTier, true
	}
	return nil, false
}

// matchWildcard checks if a model name matches a wildcard pattern
// Pattern ending with "*" matches any model name starting with the prefix
// e.g., "doubao-seed-*" matches "doubao-seed-1.6", "doubao-seed-2.0", etc.
func matchWildcard(pattern, modelName string) bool {
	if pattern == modelName {
		return true
	}

	// Check for wildcard pattern (ending with *)
	if strings.HasSuffix(pattern, "*") {
		prefix := strings.TrimSuffix(pattern, "*")
		return strings.HasPrefix(modelName, prefix)
	}

	return false
}

// IsTieredPricingEnabled checks if tiered pricing is enabled for a model
func IsTieredPricingEnabled(modelName string) bool {
	pricing, ok := GetTieredPricing(modelName)
	return ok && pricing != nil && pricing.Enabled
}
