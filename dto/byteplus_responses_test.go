package dto

import (
	"encoding/json"
	"testing"
)

func TestBytePlusInputTokensDetails_Unmarshal(t *testing.T) {
	tests := []struct {
		name                         string
		jsonStr                      string
		expectedCachedTokens         int
		expectedCacheCreationTokens  int
	}{
		{
			name:                         "Parse cached_tokens only",
			jsonStr:                      `{"cached_tokens": 100}`,
			expectedCachedTokens:         100,
			expectedCacheCreationTokens:  0,
		},
		{
			name:                         "Parse cache_creation_input_tokens only",
			jsonStr:                      `{"cache_creation_input_tokens": 200}`,
			expectedCachedTokens:         0,
			expectedCacheCreationTokens:  200,
		},
		{
			name:                         "Parse both cached_tokens and cache_creation_input_tokens",
			jsonStr:                      `{"cached_tokens": 100, "cache_creation_input_tokens": 200}`,
			expectedCachedTokens:         100,
			expectedCacheCreationTokens:  200,
		},
		{
			name:                         "Parse empty object",
			jsonStr:                      `{}`,
			expectedCachedTokens:         0,
			expectedCacheCreationTokens:  0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var details BytePlusInputTokensDetails
			err := json.Unmarshal([]byte(tt.jsonStr), &details)
			if err != nil {
				t.Fatalf("Failed to unmarshal: %v", err)
			}

			if details.CachedTokens != tt.expectedCachedTokens {
				t.Errorf("CachedTokens = %d, want %d", details.CachedTokens, tt.expectedCachedTokens)
			}
			if details.CacheCreationInputTokens != tt.expectedCacheCreationTokens {
				t.Errorf("CacheCreationInputTokens = %d, want %d", details.CacheCreationInputTokens, tt.expectedCacheCreationTokens)
			}
		})
	}
}

func TestBytePlusResponsesUsage_ToUsage(t *testing.T) {
	tests := []struct {
		name                                string
		usage                               *BytePlusResponsesUsage
		expectedPromptTokens                int
		expectedCompletionTokens            int
		expectedTotalTokens                 int
		expectedCachedTokens                int
		expectedCachedCreationTokens        int
	}{
		{
			name:  "Nil usage returns nil",
			usage: nil,
		},
		{
			name: "Basic usage without details",
			usage: &BytePlusResponsesUsage{
				InputTokens:  100,
				OutputTokens: 50,
				TotalTokens:  150,
			},
			expectedPromptTokens:     100,
			expectedCompletionTokens: 50,
			expectedTotalTokens:      150,
		},
		{
			name: "Usage with cached tokens only",
			usage: &BytePlusResponsesUsage{
				InputTokens:  100,
				OutputTokens: 50,
				TotalTokens:  150,
				InputTokensDetails: &BytePlusInputTokensDetails{
					CachedTokens: 30,
				},
			},
			expectedPromptTokens:     100,
			expectedCompletionTokens: 50,
			expectedTotalTokens:      150,
			expectedCachedTokens:     30,
		},
		{
			name: "Usage with cache creation tokens only",
			usage: &BytePlusResponsesUsage{
				InputTokens:  100,
				OutputTokens: 50,
				TotalTokens:  150,
				InputTokensDetails: &BytePlusInputTokensDetails{
					CacheCreationInputTokens: 80,
				},
			},
			expectedPromptTokens:         100,
			expectedCompletionTokens:     50,
			expectedTotalTokens:          150,
			expectedCachedCreationTokens: 80,
		},
		{
			name: "Usage with both cached and cache creation tokens",
			usage: &BytePlusResponsesUsage{
				InputTokens:  100,
				OutputTokens: 50,
				TotalTokens:  150,
				InputTokensDetails: &BytePlusInputTokensDetails{
					CachedTokens:             30,
					CacheCreationInputTokens: 80,
				},
			},
			expectedPromptTokens:         100,
			expectedCompletionTokens:     50,
			expectedTotalTokens:          150,
			expectedCachedTokens:         30,
			expectedCachedCreationTokens: 80,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := tt.usage.ToUsage()

			if tt.usage == nil {
				if result != nil {
					t.Errorf("ToUsage() = %v, want nil", result)
				}
				return
			}

			if result == nil {
				t.Fatal("ToUsage() returned nil for non-nil input")
			}

			if result.PromptTokens != tt.expectedPromptTokens {
				t.Errorf("PromptTokens = %d, want %d", result.PromptTokens, tt.expectedPromptTokens)
			}
			if result.CompletionTokens != tt.expectedCompletionTokens {
				t.Errorf("CompletionTokens = %d, want %d", result.CompletionTokens, tt.expectedCompletionTokens)
			}
			if result.TotalTokens != tt.expectedTotalTokens {
				t.Errorf("TotalTokens = %d, want %d", result.TotalTokens, tt.expectedTotalTokens)
			}
			if result.PromptTokensDetails.CachedTokens != tt.expectedCachedTokens {
				t.Errorf("PromptTokensDetails.CachedTokens = %d, want %d",
					result.PromptTokensDetails.CachedTokens, tt.expectedCachedTokens)
			}
			if result.PromptTokensDetails.CachedCreationTokens != tt.expectedCachedCreationTokens {
				t.Errorf("PromptTokensDetails.CachedCreationTokens = %d, want %d",
					result.PromptTokensDetails.CachedCreationTokens, tt.expectedCachedCreationTokens)
			}
		})
	}
}

func TestBytePlusResponsesResponse_Unmarshal(t *testing.T) {
	tests := []struct {
		name                         string
		jsonStr                      string
		expectedInputTokens          int
		expectedOutputTokens         int
		expectedCachedTokens         int
		expectedCacheCreationTokens  int
	}{
		{
			name: "Full response with cache creation tokens",
			jsonStr: `{
				"id": "resp_123",
				"status": "completed",
				"usage": {
					"input_tokens": 1000,
					"output_tokens": 500,
					"total_tokens": 1500,
					"input_tokens_details": {
						"cached_tokens": 200,
						"cache_creation_input_tokens": 800
					}
				}
			}`,
			expectedInputTokens:         1000,
			expectedOutputTokens:        500,
			expectedCachedTokens:        200,
			expectedCacheCreationTokens: 800,
		},
		{
			name: "Response with only cached tokens (cache hit scenario)",
			jsonStr: `{
				"id": "resp_456",
				"status": "completed",
				"usage": {
					"input_tokens": 500,
					"output_tokens": 200,
					"total_tokens": 700,
					"input_tokens_details": {
						"cached_tokens": 450
					}
				}
			}`,
			expectedInputTokens:  500,
			expectedOutputTokens: 200,
			expectedCachedTokens: 450,
		},
		{
			name: "Response without input_tokens_details",
			jsonStr: `{
				"id": "resp_789",
				"status": "completed",
				"usage": {
					"input_tokens": 300,
					"output_tokens": 100,
					"total_tokens": 400
				}
			}`,
			expectedInputTokens:  300,
			expectedOutputTokens: 100,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var response BytePlusResponsesResponse
			err := json.Unmarshal([]byte(tt.jsonStr), &response)
			if err != nil {
				t.Fatalf("Failed to unmarshal: %v", err)
			}

			if response.Usage == nil {
				t.Fatal("Usage is nil")
			}

			if response.Usage.InputTokens != tt.expectedInputTokens {
				t.Errorf("InputTokens = %d, want %d", response.Usage.InputTokens, tt.expectedInputTokens)
			}
			if response.Usage.OutputTokens != tt.expectedOutputTokens {
				t.Errorf("OutputTokens = %d, want %d", response.Usage.OutputTokens, tt.expectedOutputTokens)
			}

			if tt.expectedCachedTokens > 0 || tt.expectedCacheCreationTokens > 0 {
				if response.Usage.InputTokensDetails == nil {
					t.Fatal("InputTokensDetails is nil")
				}
				if response.Usage.InputTokensDetails.CachedTokens != tt.expectedCachedTokens {
					t.Errorf("CachedTokens = %d, want %d",
						response.Usage.InputTokensDetails.CachedTokens, tt.expectedCachedTokens)
				}
				if response.Usage.InputTokensDetails.CacheCreationInputTokens != tt.expectedCacheCreationTokens {
					t.Errorf("CacheCreationInputTokens = %d, want %d",
						response.Usage.InputTokensDetails.CacheCreationInputTokens, tt.expectedCacheCreationTokens)
				}
			}
		})
	}
}

func TestInputTokenDetails_Unmarshal(t *testing.T) {
	tests := []struct {
		name                         string
		jsonStr                      string
		expectedCachedTokens         int
		expectedCachedCreationTokens int
		expectedTextTokens           int
		expectedAudioTokens          int
		expectedImageTokens          int
	}{
		{
			name:                         "Parse all fields",
			jsonStr:                      `{"cached_tokens": 100, "cache_creation_input_tokens": 200, "text_tokens": 50, "audio_tokens": 30, "image_tokens": 20}`,
			expectedCachedTokens:         100,
			expectedCachedCreationTokens: 200,
			expectedTextTokens:           50,
			expectedAudioTokens:          30,
			expectedImageTokens:          20,
		},
		{
			name:                         "Parse cache_creation_input_tokens only",
			jsonStr:                      `{"cache_creation_input_tokens": 500}`,
			expectedCachedCreationTokens: 500,
		},
		{
			name:                 "Parse cached_tokens only",
			jsonStr:              `{"cached_tokens": 300}`,
			expectedCachedTokens: 300,
		},
		{
			name:    "Parse empty object",
			jsonStr: `{}`,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var details InputTokenDetails
			err := json.Unmarshal([]byte(tt.jsonStr), &details)
			if err != nil {
				t.Fatalf("Failed to unmarshal: %v", err)
			}

			if details.CachedTokens != tt.expectedCachedTokens {
				t.Errorf("CachedTokens = %d, want %d", details.CachedTokens, tt.expectedCachedTokens)
			}
			if details.CachedCreationTokens != tt.expectedCachedCreationTokens {
				t.Errorf("CachedCreationTokens = %d, want %d", details.CachedCreationTokens, tt.expectedCachedCreationTokens)
			}
			if details.TextTokens != tt.expectedTextTokens {
				t.Errorf("TextTokens = %d, want %d", details.TextTokens, tt.expectedTextTokens)
			}
			if details.AudioTokens != tt.expectedAudioTokens {
				t.Errorf("AudioTokens = %d, want %d", details.AudioTokens, tt.expectedAudioTokens)
			}
			if details.ImageTokens != tt.expectedImageTokens {
				t.Errorf("ImageTokens = %d, want %d", details.ImageTokens, tt.expectedImageTokens)
			}
		})
	}
}

func TestBytePlusResponsesStreamResponse_Unmarshal(t *testing.T) {
	jsonStr := `{
		"type": "response.completed",
		"response": {
			"id": "resp_stream_123",
			"status": "completed",
			"usage": {
				"input_tokens": 2000,
				"output_tokens": 800,
				"total_tokens": 2800,
				"input_tokens_details": {
					"cached_tokens": 500,
					"cache_creation_input_tokens": 1500
				}
			}
		}
	}`

	var streamResponse BytePlusResponsesStreamResponse
	err := json.Unmarshal([]byte(jsonStr), &streamResponse)
	if err != nil {
		t.Fatalf("Failed to unmarshal: %v", err)
	}

	if streamResponse.Type != "response.completed" {
		t.Errorf("Type = %s, want response.completed", streamResponse.Type)
	}

	if streamResponse.Response == nil {
		t.Fatal("Response is nil")
	}

	if streamResponse.Response.Usage == nil {
		t.Fatal("Usage is nil")
	}

	usage := streamResponse.Response.Usage
	if usage.InputTokens != 2000 {
		t.Errorf("InputTokens = %d, want 2000", usage.InputTokens)
	}
	if usage.OutputTokens != 800 {
		t.Errorf("OutputTokens = %d, want 800", usage.OutputTokens)
	}

	if usage.InputTokensDetails == nil {
		t.Fatal("InputTokensDetails is nil")
	}

	if usage.InputTokensDetails.CachedTokens != 500 {
		t.Errorf("CachedTokens = %d, want 500", usage.InputTokensDetails.CachedTokens)
	}
	if usage.InputTokensDetails.CacheCreationInputTokens != 1500 {
		t.Errorf("CacheCreationInputTokens = %d, want 1500", usage.InputTokensDetails.CacheCreationInputTokens)
	}
}
