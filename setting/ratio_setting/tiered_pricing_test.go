package ratio_setting

import (
	"testing"
)

func TestGetPriceTierForTokens(t *testing.T) {
	// 初始化测试数据
	testConfig := `{
        "test-model": {
            "enabled": true,
            "tiers": [
                {"min_tokens": 0, "max_tokens": 128, "input_price": 0.25, "output_price": 2.00, "cache_hit_price": 0.05},
                {"min_tokens": 128, "max_tokens": 256, "input_price": 0.50, "output_price": 4.00, "cache_hit_price": 0.05},
                {"min_tokens": 256, "max_tokens": -1, "input_price": 1.00, "output_price": 8.00, "cache_hit_price": 0.10}
            ]
        }
    }`

	err := UpdateTieredPricingByJSONString(testConfig)
	if err != nil {
		t.Fatalf("Failed to update tiered pricing: %v", err)
	}

	tests := []struct {
		name           string
		modelName      string
		inputTokensK   int
		expectedInput  float64
		expectedOutput float64
		expectedFound  bool
	}{
		{"First tier - 0 tokens", "test-model", 0, 0.25, 2.00, true},
		{"First tier - 50 tokens", "test-model", 50, 0.25, 2.00, true},
		{"First tier - 127 tokens", "test-model", 127, 0.25, 2.00, true},
		{"Second tier - 128 tokens", "test-model", 128, 0.50, 4.00, true},
		{"Second tier - 200 tokens", "test-model", 200, 0.50, 4.00, true},
		{"Third tier - 256 tokens", "test-model", 256, 1.00, 8.00, true},
		{"Third tier - 1000 tokens", "test-model", 1000, 1.00, 8.00, true},
		{"Unknown model", "unknown-model", 100, 0, 0, false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			tier, found := GetPriceTierForTokens(tt.modelName, tt.inputTokensK)
			if found != tt.expectedFound {
				t.Errorf("GetPriceTierForTokens() found = %v, want %v", found, tt.expectedFound)
			}
			if found && tier.InputPrice != tt.expectedInput {
				t.Errorf("GetPriceTierForTokens() InputPrice = %v, want %v", tier.InputPrice, tt.expectedInput)
			}
			if found && tier.OutputPrice != tt.expectedOutput {
				t.Errorf("GetPriceTierForTokens() OutputPrice = %v, want %v", tier.OutputPrice, tt.expectedOutput)
			}
		})
	}
}

func TestWildcardMatching(t *testing.T) {
	// 测试通配符匹配
	testConfig := `{
        "doubao-seed-*": {
            "enabled": true,
            "tiers": [
                {"min_tokens": 0, "max_tokens": -1, "input_price": 0.25, "output_price": 2.00, "cache_hit_price": 0.05}
            ]
        }
    }`

	err := UpdateTieredPricingByJSONString(testConfig)
	if err != nil {
		t.Fatalf("Failed to update tiered pricing: %v", err)
	}

	tests := []struct {
		name      string
		modelName string
		expected  bool
	}{
		{"Exact wildcard match", "doubao-seed-1.6", true},
		{"Another wildcard match", "doubao-seed-2.0", true},
		{"No match", "gpt-4", false},
		{"Partial no match", "doubao-other", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, found := GetTieredPricing(tt.modelName)
			if found != tt.expected {
				t.Errorf("GetTieredPricing(%s) found = %v, want %v", tt.modelName, found, tt.expected)
			}
		})
	}
}

func TestIsTieredPricingEnabled(t *testing.T) {
	testConfig := `{
        "enabled-model": {"enabled": true, "tiers": [{"min_tokens": 0, "max_tokens": -1, "input_price": 0.25, "output_price": 2.00, "cache_hit_price": 0.05}]},
        "disabled-model": {"enabled": false, "tiers": [{"min_tokens": 0, "max_tokens": -1, "input_price": 0.25, "output_price": 2.00, "cache_hit_price": 0.05}]}
    }`

	err := UpdateTieredPricingByJSONString(testConfig)
	if err != nil {
		t.Fatalf("Failed to update tiered pricing: %v", err)
	}

	if !IsTieredPricingEnabled("enabled-model") {
		t.Error("IsTieredPricingEnabled(enabled-model) should return true")
	}

	if IsTieredPricingEnabled("disabled-model") {
		t.Error("IsTieredPricingEnabled(disabled-model) should return false")
	}

	if IsTieredPricingEnabled("unknown-model") {
		t.Error("IsTieredPricingEnabled(unknown-model) should return false")
	}
}

func TestTieredPricing2JSONString(t *testing.T) {
	testConfig := `{"test-model":{"enabled":true,"tiers":[{"min_tokens":0,"max_tokens":128,"input_price":0.25,"output_price":2,"cache_hit_price":0.05,"cache_store_price":0}]}}`

	err := UpdateTieredPricingByJSONString(testConfig)
	if err != nil {
		t.Fatalf("Failed to update tiered pricing: %v", err)
	}

	jsonStr := TieredPricing2JSONString()
	if jsonStr == "" || jsonStr == "{}" {
		t.Error("TieredPricing2JSONString() should not return empty")
	}
}
