package dto

import (
	"encoding/json"
	"testing"
)

func TestGeminiUsageMetadata_CachedContentTokenCount(t *testing.T) {
	tests := []struct {
		name                        string
		jsonStr                     string
		expectedPromptTokens        int
		expectedCandidatesTokens    int
		expectedTotalTokens         int
		expectedThoughtsTokens      int
		expectedCachedContentTokens int
	}{
		{
			name: "With cachedContentTokenCount",
			jsonStr: `{
				"promptTokenCount": 5000,
				"candidatesTokenCount": 200,
				"totalTokenCount": 5200,
				"thoughtsTokenCount": 50,
				"cachedContentTokenCount": 3000
			}`,
			expectedPromptTokens:        5000,
			expectedCandidatesTokens:    200,
			expectedTotalTokens:         5200,
			expectedThoughtsTokens:      50,
			expectedCachedContentTokens: 3000,
		},
		{
			name: "Without cachedContentTokenCount",
			jsonStr: `{
				"promptTokenCount": 1000,
				"candidatesTokenCount": 100,
				"totalTokenCount": 1100,
				"thoughtsTokenCount": 0
			}`,
			expectedPromptTokens:        1000,
			expectedCandidatesTokens:    100,
			expectedTotalTokens:         1100,
			expectedThoughtsTokens:      0,
			expectedCachedContentTokens: 0,
		},
		{
			name: "Zero cachedContentTokenCount",
			jsonStr: `{
				"promptTokenCount": 2000,
				"candidatesTokenCount": 300,
				"totalTokenCount": 2300,
				"thoughtsTokenCount": 100,
				"cachedContentTokenCount": 0
			}`,
			expectedPromptTokens:        2000,
			expectedCandidatesTokens:    300,
			expectedTotalTokens:         2300,
			expectedThoughtsTokens:      100,
			expectedCachedContentTokens: 0,
		},
		{
			name: "Large cachedContentTokenCount for long context",
			jsonStr: `{
				"promptTokenCount": 250000,
				"candidatesTokenCount": 500,
				"totalTokenCount": 250500,
				"thoughtsTokenCount": 200,
				"cachedContentTokenCount": 200000
			}`,
			expectedPromptTokens:        250000,
			expectedCandidatesTokens:    500,
			expectedTotalTokens:         250500,
			expectedThoughtsTokens:      200,
			expectedCachedContentTokens: 200000,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var metadata GeminiUsageMetadata
			if err := json.Unmarshal([]byte(tt.jsonStr), &metadata); err != nil {
				t.Fatalf("Failed to unmarshal: %v", err)
			}

			if metadata.PromptTokenCount != tt.expectedPromptTokens {
				t.Errorf("PromptTokenCount = %d, want %d", metadata.PromptTokenCount, tt.expectedPromptTokens)
			}
			if metadata.CandidatesTokenCount != tt.expectedCandidatesTokens {
				t.Errorf("CandidatesTokenCount = %d, want %d", metadata.CandidatesTokenCount, tt.expectedCandidatesTokens)
			}
			if metadata.TotalTokenCount != tt.expectedTotalTokens {
				t.Errorf("TotalTokenCount = %d, want %d", metadata.TotalTokenCount, tt.expectedTotalTokens)
			}
			if metadata.ThoughtsTokenCount != tt.expectedThoughtsTokens {
				t.Errorf("ThoughtsTokenCount = %d, want %d", metadata.ThoughtsTokenCount, tt.expectedThoughtsTokens)
			}
			if metadata.CachedContentTokenCount != tt.expectedCachedContentTokens {
				t.Errorf("CachedContentTokenCount = %d, want %d", metadata.CachedContentTokenCount, tt.expectedCachedContentTokens)
			}
		})
	}
}

func TestGeminiUsageMetadata_JSONRoundTrip(t *testing.T) {
	original := GeminiUsageMetadata{
		PromptTokenCount:        10000,
		CandidatesTokenCount:    500,
		TotalTokenCount:         10500,
		ThoughtsTokenCount:      150,
		CachedContentTokenCount: 8000,
		PromptTokensDetails: []GeminiPromptTokensDetails{
			{Modality: "TEXT", TokenCount: 9000},
			{Modality: "AUDIO", TokenCount: 1000},
		},
	}

	data, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("Failed to marshal: %v", err)
	}

	var decoded GeminiUsageMetadata
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Failed to unmarshal: %v", err)
	}

	if decoded.CachedContentTokenCount != original.CachedContentTokenCount {
		t.Errorf("CachedContentTokenCount = %d, want %d", decoded.CachedContentTokenCount, original.CachedContentTokenCount)
	}
	if decoded.PromptTokenCount != original.PromptTokenCount {
		t.Errorf("PromptTokenCount = %d, want %d", decoded.PromptTokenCount, original.PromptTokenCount)
	}
	if decoded.ThoughtsTokenCount != original.ThoughtsTokenCount {
		t.Errorf("ThoughtsTokenCount = %d, want %d", decoded.ThoughtsTokenCount, original.ThoughtsTokenCount)
	}
	if len(decoded.PromptTokensDetails) != len(original.PromptTokensDetails) {
		t.Errorf("PromptTokensDetails length = %d, want %d", len(decoded.PromptTokensDetails), len(original.PromptTokensDetails))
	}
}

func TestGeminiChatResponse_UsageWithCache(t *testing.T) {
	responseJSON := `{
		"candidates": [
			{
				"content": {
					"parts": [{"text": "Hello!"}],
					"role": "model"
				},
				"finishReason": "STOP",
				"index": 0
			}
		],
		"usageMetadata": {
			"promptTokenCount": 50000,
			"candidatesTokenCount": 100,
			"totalTokenCount": 50100,
			"thoughtsTokenCount": 0,
			"cachedContentTokenCount": 45000,
			"promptTokensDetails": [
				{"modality": "TEXT", "tokenCount": 50000}
			]
		}
	}`

	var response GeminiChatResponse
	if err := json.Unmarshal([]byte(responseJSON), &response); err != nil {
		t.Fatalf("Failed to unmarshal GeminiChatResponse: %v", err)
	}

	if response.UsageMetadata.CachedContentTokenCount != 45000 {
		t.Errorf("CachedContentTokenCount = %d, want 45000", response.UsageMetadata.CachedContentTokenCount)
	}
	if response.UsageMetadata.PromptTokenCount != 50000 {
		t.Errorf("PromptTokenCount = %d, want 50000", response.UsageMetadata.PromptTokenCount)
	}
}

func TestGeminiUsageMetadataToOpenAIUsage(t *testing.T) {
	tests := []struct {
		name                 string
		metadata             GeminiUsageMetadata
		expectedCachedTokens int
		expectedAudioTokens  int
		expectedTextTokens   int
	}{
		{
			name: "Cache tokens mapped correctly",
			metadata: GeminiUsageMetadata{
				PromptTokenCount:        100000,
				CandidatesTokenCount:    500,
				TotalTokenCount:         100500,
				CachedContentTokenCount: 80000,
				PromptTokensDetails: []GeminiPromptTokensDetails{
					{Modality: "TEXT", TokenCount: 100000},
				},
			},
			expectedCachedTokens: 80000,
			expectedAudioTokens:  0,
			expectedTextTokens:   100000,
		},
		{
			name: "No cache tokens",
			metadata: GeminiUsageMetadata{
				PromptTokenCount:        5000,
				CandidatesTokenCount:    200,
				TotalTokenCount:         5200,
				CachedContentTokenCount: 0,
				PromptTokensDetails: []GeminiPromptTokensDetails{
					{Modality: "TEXT", TokenCount: 5000},
				},
			},
			expectedCachedTokens: 0,
			expectedAudioTokens:  0,
			expectedTextTokens:   5000,
		},
		{
			name: "Cache with audio tokens",
			metadata: GeminiUsageMetadata{
				PromptTokenCount:        30000,
				CandidatesTokenCount:    100,
				TotalTokenCount:         30100,
				CachedContentTokenCount: 20000,
				PromptTokensDetails: []GeminiPromptTokensDetails{
					{Modality: "TEXT", TokenCount: 25000},
					{Modality: "AUDIO", TokenCount: 5000},
				},
			},
			expectedCachedTokens: 20000,
			expectedAudioTokens:  5000,
			expectedTextTokens:   25000,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			usage := mapGeminiUsageToOpenAI(tt.metadata)

			if usage.PromptTokensDetails.CachedTokens != tt.expectedCachedTokens {
				t.Errorf("CachedTokens = %d, want %d", usage.PromptTokensDetails.CachedTokens, tt.expectedCachedTokens)
			}
			if usage.PromptTokensDetails.AudioTokens != tt.expectedAudioTokens {
				t.Errorf("AudioTokens = %d, want %d", usage.PromptTokensDetails.AudioTokens, tt.expectedAudioTokens)
			}
			if usage.PromptTokensDetails.TextTokens != tt.expectedTextTokens {
				t.Errorf("TextTokens = %d, want %d", usage.PromptTokensDetails.TextTokens, tt.expectedTextTokens)
			}
			if usage.PromptTokens != tt.metadata.PromptTokenCount {
				t.Errorf("PromptTokens = %d, want %d", usage.PromptTokens, tt.metadata.PromptTokenCount)
			}
			if usage.CompletionTokenDetails.ReasoningTokens != tt.metadata.ThoughtsTokenCount {
				t.Errorf("ReasoningTokens = %d, want %d", usage.CompletionTokenDetails.ReasoningTokens, tt.metadata.ThoughtsTokenCount)
			}
		})
	}
}

// mapGeminiUsageToOpenAI simulates the mapping logic used in relay-gemini.go handlers
func mapGeminiUsageToOpenAI(metadata GeminiUsageMetadata) Usage {
	usage := Usage{
		PromptTokens:     metadata.PromptTokenCount,
		CompletionTokens: metadata.CandidatesTokenCount,
		TotalTokens:      metadata.TotalTokenCount,
	}
	usage.CompletionTokenDetails.ReasoningTokens = metadata.ThoughtsTokenCount
	usage.CompletionTokens = usage.TotalTokens - usage.PromptTokens
	usage.PromptTokensDetails.CachedTokens = metadata.CachedContentTokenCount

	for _, detail := range metadata.PromptTokensDetails {
		if detail.Modality == "AUDIO" {
			usage.PromptTokensDetails.AudioTokens = detail.TokenCount
		} else if detail.Modality == "TEXT" {
			usage.PromptTokensDetails.TextTokens = detail.TokenCount
		}
	}

	return usage
}
