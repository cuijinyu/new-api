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
