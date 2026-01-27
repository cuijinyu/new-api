package openai

import (
	"testing"

	"github.com/QuantumNous/new-api/constant"
	"github.com/QuantumNous/new-api/dto"
	relaycommon "github.com/QuantumNous/new-api/relay/common"
)

func TestApplyUsagePostProcessing_Moonshot(t *testing.T) {
	tests := []struct {
		name                 string
		channelType          int
		cachedTokens         int
		promptDetailsCached  int
		expectedPromptCached int
	}{
		{
			name:                 "Moonshot with cached_tokens should set PromptTokensDetails.CachedTokens",
			channelType:          constant.ChannelTypeMoonshot,
			cachedTokens:         10,
			promptDetailsCached:  0,
			expectedPromptCached: 10,
		},
		{
			name:                 "Moonshot without cached_tokens should not change PromptTokensDetails.CachedTokens",
			channelType:          constant.ChannelTypeMoonshot,
			cachedTokens:         0,
			promptDetailsCached:  0,
			expectedPromptCached: 0,
		},
		{
			name:                 "Moonshot should not override existing PromptTokensDetails.CachedTokens",
			channelType:          constant.ChannelTypeMoonshot,
			cachedTokens:         10,
			promptDetailsCached:  5,
			expectedPromptCached: 5,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			info := &relaycommon.RelayInfo{
				ChannelMeta: &relaycommon.ChannelMeta{
					ChannelType: tt.channelType,
				},
			}
			usage := &dto.Usage{
				PromptTokens:     100,
				CompletionTokens: 50,
				TotalTokens:      150,
				CachedTokens:     tt.cachedTokens,
				PromptTokensDetails: dto.InputTokenDetails{
					CachedTokens: tt.promptDetailsCached,
				},
			}

			applyUsagePostProcessing(info, usage, nil)

			if usage.PromptTokensDetails.CachedTokens != tt.expectedPromptCached {
				t.Errorf("PromptTokensDetails.CachedTokens = %d, want %d",
					usage.PromptTokensDetails.CachedTokens, tt.expectedPromptCached)
			}
		})
	}
}

func TestApplyUsagePostProcessing_DeepSeek(t *testing.T) {
	tests := []struct {
		name                 string
		promptCacheHitTokens int
		promptDetailsCached  int
		expectedPromptCached int
	}{
		{
			name:                 "DeepSeek with PromptCacheHitTokens should set PromptTokensDetails.CachedTokens",
			promptCacheHitTokens: 20,
			promptDetailsCached:  0,
			expectedPromptCached: 20,
		},
		{
			name:                 "DeepSeek should not override existing PromptTokensDetails.CachedTokens",
			promptCacheHitTokens: 20,
			promptDetailsCached:  15,
			expectedPromptCached: 15,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			info := &relaycommon.RelayInfo{
				ChannelMeta: &relaycommon.ChannelMeta{
					ChannelType: constant.ChannelTypeDeepSeek,
				},
			}
			usage := &dto.Usage{
				PromptTokens:         100,
				CompletionTokens:     50,
				TotalTokens:          150,
				PromptCacheHitTokens: tt.promptCacheHitTokens,
				PromptTokensDetails: dto.InputTokenDetails{
					CachedTokens: tt.promptDetailsCached,
				},
			}

			applyUsagePostProcessing(info, usage, nil)

			if usage.PromptTokensDetails.CachedTokens != tt.expectedPromptCached {
				t.Errorf("PromptTokensDetails.CachedTokens = %d, want %d",
					usage.PromptTokensDetails.CachedTokens, tt.expectedPromptCached)
			}
		})
	}
}

func TestApplyUsagePostProcessing_NilInputs(t *testing.T) {
	// Test with nil info
	usage := &dto.Usage{}
	applyUsagePostProcessing(nil, usage, nil)
	// Should not panic

	// Test with nil usage
	info := &relaycommon.RelayInfo{
		ChannelMeta: &relaycommon.ChannelMeta{
			ChannelType: constant.ChannelTypeMoonshot,
		},
	}
	applyUsagePostProcessing(info, nil, nil)
	// Should not panic
}

func TestExtractCachedTokensFromBody(t *testing.T) {
	tests := []struct {
		name          string
		body          string
		expectedValue int
		expectedOk    bool
	}{
		{
			name:          "Extract from prompt_tokens_details.cached_tokens",
			body:          `{"usage":{"prompt_tokens_details":{"cached_tokens":15}}}`,
			expectedValue: 15,
			expectedOk:    true,
		},
		{
			name:          "Extract from usage.cached_tokens (Moonshot format)",
			body:          `{"usage":{"cached_tokens":10}}`,
			expectedValue: 10,
			expectedOk:    true,
		},
		{
			name:          "Extract from usage.prompt_cache_hit_tokens",
			body:          `{"usage":{"prompt_cache_hit_tokens":25}}`,
			expectedValue: 25,
			expectedOk:    true,
		},
		{
			name:          "Priority: prompt_tokens_details.cached_tokens over usage.cached_tokens",
			body:          `{"usage":{"prompt_tokens_details":{"cached_tokens":15},"cached_tokens":10}}`,
			expectedValue: 15,
			expectedOk:    true,
		},
		{
			name:          "Empty body returns false",
			body:          "",
			expectedValue: 0,
			expectedOk:    false,
		},
		{
			name:          "Invalid JSON returns false",
			body:          "invalid json",
			expectedValue: 0,
			expectedOk:    false,
		},
		{
			name:          "No cached tokens returns false",
			body:          `{"usage":{"prompt_tokens":100}}`,
			expectedValue: 0,
			expectedOk:    false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			value, ok := extractCachedTokensFromBody([]byte(tt.body))
			if ok != tt.expectedOk {
				t.Errorf("extractCachedTokensFromBody() ok = %v, want %v", ok, tt.expectedOk)
			}
			if value != tt.expectedValue {
				t.Errorf("extractCachedTokensFromBody() value = %d, want %d", value, tt.expectedValue)
			}
		})
	}
}
