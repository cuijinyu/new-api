package gemini

import (
	"testing"

	"github.com/QuantumNous/new-api/dto"
)

func TestGeminiUsageImageFallbackUsesCandidateTokens(t *testing.T) {
	response := dto.GeminiChatResponse{
		Candidates: []dto.GeminiChatCandidate{
			{
				Content: dto.GeminiChatContent{
					Parts: []dto.GeminiPart{
						{InlineData: &dto.GeminiInlineData{MimeType: "image/png", Data: "abc"}},
					},
				},
			},
		},
		UsageMetadata: dto.GeminiUsageMetadata{
			PromptTokenCount:     10,
			CandidatesTokenCount: 1290,
			TotalTokenCount:      1300,
		},
	}

	usage := geminiUsageFromMetadata(response.UsageMetadata)
	source := applyGeminiImageOutputFallback(&usage, countGeminiInlineImages(&response))

	if usage.CompletionTokens != 1290 {
		t.Fatalf("CompletionTokens = %d, want 1290", usage.CompletionTokens)
	}
	if usage.CompletionTokenDetails.ImageTokens != 1290 {
		t.Fatalf("ImageTokens = %d, want 1290", usage.CompletionTokenDetails.ImageTokens)
	}
	if source != geminiImageTokenSourceCandidateFallback {
		t.Fatalf("source = %q, want %q", source, geminiImageTokenSourceCandidateFallback)
	}
}

func TestGeminiUsageKeepsOfficialImageTokenDetails(t *testing.T) {
	usage := geminiUsageFromMetadata(dto.GeminiUsageMetadata{
		PromptTokenCount:     10,
		CandidatesTokenCount: 1320,
		TotalTokenCount:      1330,
		CandidatesTokensDetails: []dto.GeminiPromptTokensDetails{
			{Modality: "IMAGE", TokenCount: 1290},
		},
	})
	source := applyGeminiImageOutputFallback(&usage, 1)

	if usage.CompletionTokenDetails.ImageTokens != 1290 {
		t.Fatalf("ImageTokens = %d, want 1290", usage.CompletionTokenDetails.ImageTokens)
	}
	if source != geminiImageTokenSourceMetadata {
		t.Fatalf("source = %q, want %q", source, geminiImageTokenSourceMetadata)
	}
}

func TestGeminiUsageWithoutNewMetadataKeepsLegacyBillingTokens(t *testing.T) {
	usage := geminiUsageFromMetadata(dto.GeminiUsageMetadata{
		PromptTokenCount:        100,
		CandidatesTokenCount:    40,
		CachedContentTokenCount: 20,
		TotalTokenCount:         140,
		PromptTokensDetails: []dto.GeminiPromptTokensDetails{
			{Modality: "TEXT", TokenCount: 100},
		},
		CandidatesTokensDetails: []dto.GeminiPromptTokensDetails{
			{Modality: "TEXT", TokenCount: 40},
		},
	})

	if usage.PromptTokens != 100 {
		t.Fatalf("PromptTokens = %d, want 100", usage.PromptTokens)
	}
	if usage.CompletionTokens != 40 {
		t.Fatalf("CompletionTokens = %d, want 40", usage.CompletionTokens)
	}
	if usage.TotalTokens != 140 {
		t.Fatalf("TotalTokens = %d, want 140", usage.TotalTokens)
	}
	if usage.PromptTokensDetails.CachedTokens != 20 {
		t.Fatalf("CachedTokens = %d, want 20", usage.PromptTokensDetails.CachedTokens)
	}
	if usage.PromptTokensDetails.TextTokens != 100 {
		t.Fatalf("Prompt text tokens = %d, want 100", usage.PromptTokensDetails.TextTokens)
	}
	if usage.CompletionTokenDetails.TextTokens != 40 {
		t.Fatalf("Completion text tokens = %d, want 40", usage.CompletionTokenDetails.TextTokens)
	}
	if usage.CompletionTokenDetails.ReasoningTokens != 0 {
		t.Fatalf("ReasoningTokens = %d, want 0", usage.CompletionTokenDetails.ReasoningTokens)
	}
	if usage.ToolUsePromptTokens != 0 {
		t.Fatalf("ToolUsePromptTokens = %d, want 0", usage.ToolUsePromptTokens)
	}
}

func TestGeminiUsageIncludesToolUseThoughtsAndCacheTokens(t *testing.T) {
	usage := geminiUsageFromMetadata(dto.GeminiUsageMetadata{
		PromptTokenCount:        100,
		ToolUsePromptTokenCount: 25,
		CandidatesTokenCount:    40,
		ThoughtsTokenCount:      15,
		CachedContentTokenCount: 80,
		TotalTokenCount:         180,
		PromptTokensDetails: []dto.GeminiPromptTokensDetails{
			{Modality: "TEXT", TokenCount: 90},
			{Modality: "AUDIO", TokenCount: 10},
		},
		ToolUsePromptTokensDetails: []dto.GeminiPromptTokensDetails{
			{Modality: "TEXT", TokenCount: 25},
		},
		CandidatesTokensDetails: []dto.GeminiPromptTokensDetails{
			{Modality: "TEXT", TokenCount: 40},
		},
	})

	if usage.PromptTokens != 125 {
		t.Fatalf("PromptTokens = %d, want 125", usage.PromptTokens)
	}
	if usage.ToolUsePromptTokens != 25 {
		t.Fatalf("ToolUsePromptTokens = %d, want 25", usage.ToolUsePromptTokens)
	}
	if usage.CompletionTokens != 55 {
		t.Fatalf("CompletionTokens = %d, want 55", usage.CompletionTokens)
	}
	if usage.TotalTokens != 180 {
		t.Fatalf("TotalTokens = %d, want 180", usage.TotalTokens)
	}
	if usage.CompletionTokenDetails.ReasoningTokens != 15 {
		t.Fatalf("ReasoningTokens = %d, want 15", usage.CompletionTokenDetails.ReasoningTokens)
	}
	if usage.PromptTokensDetails.CachedTokens != 80 {
		t.Fatalf("CachedTokens = %d, want 80", usage.PromptTokensDetails.CachedTokens)
	}
	if usage.PromptTokensDetails.TextTokens != 115 {
		t.Fatalf("Prompt text tokens = %d, want 115", usage.PromptTokensDetails.TextTokens)
	}
	if usage.PromptTokensDetails.AudioTokens != 10 {
		t.Fatalf("Prompt audio tokens = %d, want 10", usage.PromptTokensDetails.AudioTokens)
	}
	if usage.CompletionTokenDetails.TextTokens != 40 {
		t.Fatalf("Completion text tokens = %d, want 40", usage.CompletionTokenDetails.TextTokens)
	}
}
