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

// TestGPT55TierBoundary272K verifies tier selection around the 272K boundary.
// Tier units are in thousands of tokens (inputTokensK = totalTokens / 1000).
// With max_tokens=272 on the low tier, the boundary in the billing code is:
//   271999 tokens → 271K → low tier ($5/$30)
//   272000 tokens → 272K → high tier ($10/$45)  ← exact boundary, >=272
//   272001 tokens → 272K → high tier ($10/$45)
func TestGPT55TierBoundary272K(t *testing.T) {
	InitTieredPricingSettings()

	tests := []struct {
		name           string
		totalTokens    int
		expectedInput  float64
		expectedOutput float64
		description    string
	}{
		{
			name:           "271999 tokens → 271K → low tier",
			totalTokens:    271999,
			expectedInput:  5,
			expectedOutput: 30,
			description:    "Just under 272K, should use standard pricing",
		},
		{
			name:           "272000 tokens → 272K → high tier",
			totalTokens:    272000,
			expectedInput:  10,
			expectedOutput: 45,
			description:    "Exactly 272K, enters high tier (>=272)",
		},
		{
			name:           "272001 tokens → 272K → high tier",
			totalTokens:    272001,
			expectedInput:  10,
			expectedOutput: 45,
			description:    "Just over 272K, should use long-context pricing",
		},
		{
			name:           "200000 tokens → 200K → low tier",
			totalTokens:    200000,
			expectedInput:  5,
			expectedOutput: 30,
			description:    "Well under 272K",
		},
		{
			name:           "500000 tokens → 500K → high tier",
			totalTokens:    500000,
			expectedInput:  10,
			expectedOutput: 45,
			description:    "Well over 272K",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			inputTokensK := tt.totalTokens / 1000
			tier, found := GetPriceTierForTokens("gpt-5.5", inputTokensK)
			if !found {
				t.Fatalf("GetPriceTierForTokens(gpt-5.5, %d) not found, but gpt-5.5 should have default tiered pricing", inputTokensK)
			}
			if tier.InputPrice != tt.expectedInput {
				t.Errorf("%s: InputPrice = %v, want %v (inputTokensK=%d)",
					tt.description, tier.InputPrice, tt.expectedInput, inputTokensK)
			}
			if tier.OutputPrice != tt.expectedOutput {
				t.Errorf("%s: OutputPrice = %v, want %v (inputTokensK=%d)",
					tt.description, tier.OutputPrice, tt.expectedOutput, inputTokensK)
			}
		})
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
