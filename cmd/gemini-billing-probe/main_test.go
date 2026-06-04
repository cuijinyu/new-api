package main

import "testing"

func TestCalculateExpectedQuotaGeminiImageOutput(t *testing.T) {
	logRow := consumeLog{
		PromptTokens:     29,
		CompletionTokens: 1290,
		Quota:            19354,
	}
	other := map[string]interface{}{
		"model_ratio":             0.15,
		"group_ratio":             1.0,
		"completion_ratio":        8.333333333333334,
		"cache_tokens":            0,
		"cache_ratio":             1.0,
		"input_text_tokens":       29,
		"output_image_tokens":     1290,
		"image_completion_ratio":  100.0,
		"image_completion_tokens": 1290,
	}

	got, err := calculateExpectedQuota(logRow, other)
	if err != nil {
		t.Fatalf("calculateExpectedQuota returned error: %v", err)
	}
	if got != logRow.Quota {
		t.Fatalf("expected %d, got %d", logRow.Quota, got)
	}
}

func TestCalculateExpectedQuotaGeminiImageInputAndMixedOutput(t *testing.T) {
	logRow := consumeLog{
		PromptTokens:     28,
		CompletionTokens: 1552,
		Quota:            34255,
	}
	other := map[string]interface{}{
		"model_ratio":             0.25,
		"group_ratio":             1.0,
		"completion_ratio":        6.0,
		"cache_tokens":            0,
		"cache_ratio":             1.0,
		"input_text_tokens":       28,
		"output_text_tokens":      432,
		"output_image_tokens":     1120,
		"image_completion_ratio":  120.0,
		"image_completion_tokens": 1120,
	}

	got, err := calculateExpectedQuota(logRow, other)
	if err != nil {
		t.Fatalf("calculateExpectedQuota returned error: %v", err)
	}
	if got != logRow.Quota {
		t.Fatalf("expected %d, got %d", logRow.Quota, got)
	}
}

func TestCalculateExpectedQuotaWithInputImage(t *testing.T) {
	logRow := consumeLog{
		PromptTokens:     293,
		CompletionTokens: 1290,
		Quota:            19394,
	}
	other := map[string]interface{}{
		"model_ratio":             0.15,
		"group_ratio":             1.0,
		"completion_ratio":        8.333333333333334,
		"cache_tokens":            0,
		"cache_ratio":             1.0,
		"input_text_tokens":       35,
		"input_image_tokens":      258,
		"image_ratio":             1.0,
		"output_image_tokens":     1290,
		"image_completion_ratio":  100.0,
		"image_completion_tokens": 1290,
	}

	got, err := calculateExpectedQuota(logRow, other)
	if err != nil {
		t.Fatalf("calculateExpectedQuota returned error: %v", err)
	}
	if got != logRow.Quota {
		t.Fatalf("expected %d, got %d", logRow.Quota, got)
	}
}
