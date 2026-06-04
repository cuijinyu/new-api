package ratio_setting

import "testing"

func TestGeminiImageDefaultRatios(t *testing.T) {
	InitRatioSettings()

	tests := []struct {
		model               string
		wantModelRatio      float64
		wantCompletionRatio float64
		wantImageCompletion float64
	}{
		{"gemini-2.5-flash-image", 0.15, 2.5 / 0.3, 30 / 0.3},
		{"gemini-3.1-flash-image", 0.25, 6, 60 / 0.5},
		{"gemini-3.1-flash-image-preview", 0.25, 6, 60 / 0.5},
		{"gemini-3-pro-image", 1, 6, 120 / 2.0},
		{"gemini-3-pro-image-preview", 1, 6, 120 / 2.0},
		{"nano-banana", 0.15, 2.5 / 0.3, 30 / 0.3},
		{"nano-banana-pro", 1, 6, 120 / 2.0},
	}

	for _, tt := range tests {
		t.Run(tt.model, func(t *testing.T) {
			modelRatio, ok, _ := GetModelRatio(tt.model)
			if !ok || modelRatio != tt.wantModelRatio {
				t.Fatalf("GetModelRatio(%q) = %v, %v; want %v, true", tt.model, modelRatio, ok, tt.wantModelRatio)
			}
			if got := GetCompletionRatio(tt.model); got != tt.wantCompletionRatio {
				t.Fatalf("GetCompletionRatio(%q) = %v, want %v", tt.model, got, tt.wantCompletionRatio)
			}
			imageCompletion, ok := GetImageCompletionRatio(tt.model)
			if !ok || imageCompletion != tt.wantImageCompletion {
				t.Fatalf("GetImageCompletionRatio(%q) = %v, %v; want %v, true", tt.model, imageCompletion, ok, tt.wantImageCompletion)
			}
		})
	}
}

func TestGeminiImageCompletionFallsBackToDefaults(t *testing.T) {
	if err := UpdateImageCompletionRatioByJSONString(`{}`); err != nil {
		t.Fatalf("UpdateImageCompletionRatioByJSONString() error = %v", err)
	}

	imageCompletion, ok := GetImageCompletionRatio("gemini-2.5-flash-image")
	if !ok || imageCompletion != 30/0.3 {
		t.Fatalf("GetImageCompletionRatio() = %v, %v; want %v, true", imageCompletion, ok, 30/0.3)
	}
}

func TestGeminiImageModelRatioFallsBackToDefaults(t *testing.T) {
	InitRatioSettings()
	defer InitRatioSettings()

	if err := UpdateModelRatioByJSONString(`{}`); err != nil {
		t.Fatalf("UpdateModelRatioByJSONString() error = %v", err)
	}

	modelRatio, ok, _ := GetModelRatio("gemini-3-pro-image")
	if !ok || modelRatio != 1 {
		t.Fatalf("GetModelRatio() = %v, %v; want 1, true", modelRatio, ok)
	}
}

func TestGeminiImageTextCompletionIgnoresStaleImageRatioOverride(t *testing.T) {
	InitRatioSettings()
	defer InitRatioSettings()

	if err := UpdateCompletionRatioByJSONString(`{
		"gemini-2.5-flash-image": 100,
		"gemini-3.1-flash-image-preview": 120,
		"gemini-3-pro-image-preview": 60
	}`); err != nil {
		t.Fatalf("UpdateCompletionRatioByJSONString() error = %v", err)
	}

	tests := []struct {
		model string
		want  float64
	}{
		{"gemini-2.5-flash-image", 2.5 / 0.3},
		{"gemini-3.1-flash-image", 6},
		{"gemini-3.1-flash-image-preview", 6},
		{"gemini-3-pro-image", 6},
		{"gemini-3-pro-image-preview", 6},
	}

	for _, tt := range tests {
		t.Run(tt.model, func(t *testing.T) {
			if got := GetCompletionRatio(tt.model); got != tt.want {
				t.Fatalf("GetCompletionRatio(%q) = %v, want %v", tt.model, got, tt.want)
			}
		})
	}
}
