package ratio_setting

import (
	"testing"
)

func TestIsClaudeModel(t *testing.T) {
	tests := []struct {
		name     string
		model    string
		expected bool
	}{
		// Claude 模型 - 应返回 true
		{"Claude 3 Haiku", "claude-3-haiku-20240307", true},
		{"Claude 3.5 Sonnet", "claude-3-5-sonnet-20241022", true},
		{"Claude 3.7 Sonnet thinking", "claude-3-7-sonnet-20250219-thinking", true},
		{"Claude Sonnet 4", "claude-sonnet-4-20250514", true},
		{"Claude Opus 4", "claude-opus-4-20250514", true},
		{"Claude Opus 4.1", "claude-opus-4-1-20250805", true},
		{"Claude Opus 4.5", "claude-opus-4-5-20251101", true},
		{"Claude Opus 4.6", "claude-opus-4-6-20260120", true},
		{"Claude Opus 4.6 thinking", "claude-opus-4-6-20260120-thinking", true},
		{"Claude instant", "claude-instant-1", true},
		{"Claude 2", "claude-2.1", true},
		// 包含 claude 的其他格式
		{"Uppercase Claude", "Claude-3-opus", true},
		{"Mixed case", "CLAUDE-opus-4", true},

		// 非 Claude 模型 - 应返回 false
		{"GPT-4", "gpt-4", false},
		{"GPT-4o", "gpt-4o-2024-05-13", false},
		{"Gemini", "gemini-2.5-pro", false},
		{"DeepSeek", "deepseek-chat", false},
		{"Llama", "llama-3-70b", false},
		{"Empty string", "", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := IsClaudeModel(tt.model)
			if result != tt.expected {
				t.Errorf("IsClaudeModel(%q) = %v, want %v", tt.model, result, tt.expected)
			}
		})
	}
}

func TestGetClaude200KMultipliers(t *testing.T) {
	tests := []struct {
		name               string
		modelName          string
		totalInputTokens   int
		expectedInputMult  float64
		expectedOutputMult float64
	}{
		// ========== Claude 模型，≤ 200K tokens ==========
		{
			name:               "Claude Opus 4.6 - 0 tokens",
			modelName:          "claude-opus-4-6-20260120",
			totalInputTokens:   0,
			expectedInputMult:  1.0,
			expectedOutputMult: 1.0,
		},
		{
			name:               "Claude Opus 4.6 - 100K tokens",
			modelName:          "claude-opus-4-6-20260120",
			totalInputTokens:   100000,
			expectedInputMult:  1.0,
			expectedOutputMult: 1.0,
		},
		{
			name:               "Claude Opus 4.6 - exactly 200K tokens (boundary)",
			modelName:          "claude-opus-4-6-20260120",
			totalInputTokens:   200000,
			expectedInputMult:  1.0,
			expectedOutputMult: 1.0,
		},
		{
			name:               "Claude Opus 4.5 - 199999 tokens",
			modelName:          "claude-opus-4-5-20251101",
			totalInputTokens:   199999,
			expectedInputMult:  1.0,
			expectedOutputMult: 1.0,
		},

		// ========== Claude 模型，> 200K tokens ==========
		{
			name:               "Claude Opus 4.6 - 200001 tokens (just over threshold)",
			modelName:          "claude-opus-4-6-20260120",
			totalInputTokens:   200001,
			expectedInputMult:  2.0,
			expectedOutputMult: 1.5,
		},
		{
			name:               "Claude Opus 4.6 thinking - 300K tokens",
			modelName:          "claude-opus-4-6-20260120-thinking",
			totalInputTokens:   300000,
			expectedInputMult:  2.0,
			expectedOutputMult: 1.5,
		},
		{
			name:               "Claude Opus 4.5 - 500K tokens",
			modelName:          "claude-opus-4-5-20251101",
			totalInputTokens:   500000,
			expectedInputMult:  2.0,
			expectedOutputMult: 1.5,
		},
		{
			name:               "Claude Sonnet 4 - 250K tokens",
			modelName:          "claude-sonnet-4-20250514",
			totalInputTokens:   250000,
			expectedInputMult:  2.0,
			expectedOutputMult: 1.5,
		},
		{
			name:               "Claude 3.7 Sonnet thinking - 201K tokens",
			modelName:          "claude-3-7-sonnet-20250219-thinking",
			totalInputTokens:   201000,
			expectedInputMult:  2.0,
			expectedOutputMult: 1.5,
		},
		{
			name:               "Claude 3 Opus - 1M tokens",
			modelName:          "claude-3-opus-20240229",
			totalInputTokens:   1000000,
			expectedInputMult:  2.0,
			expectedOutputMult: 1.5,
		},

		// ========== 非 Claude 模型 - 永远不应用倍率 ==========
		{
			name:               "GPT-4 - 300K tokens (non-Claude, over threshold)",
			modelName:          "gpt-4",
			totalInputTokens:   300000,
			expectedInputMult:  1.0,
			expectedOutputMult: 1.0,
		},
		{
			name:               "Gemini - 500K tokens (non-Claude, over threshold)",
			modelName:          "gemini-2.5-pro",
			totalInputTokens:   500000,
			expectedInputMult:  1.0,
			expectedOutputMult: 1.0,
		},
		{
			name:               "DeepSeek - 400K tokens (non-Claude, over threshold)",
			modelName:          "deepseek-chat",
			totalInputTokens:   400000,
			expectedInputMult:  1.0,
			expectedOutputMult: 1.0,
		},
		{
			name:               "Empty model - 300K tokens",
			modelName:          "",
			totalInputTokens:   300000,
			expectedInputMult:  1.0,
			expectedOutputMult: 1.0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			inputMult, outputMult := GetClaude200KMultipliers(tt.modelName, tt.totalInputTokens)
			if inputMult != tt.expectedInputMult {
				t.Errorf("GetClaude200KMultipliers(%q, %d) inputMultiplier = %v, want %v",
					tt.modelName, tt.totalInputTokens, inputMult, tt.expectedInputMult)
			}
			if outputMult != tt.expectedOutputMult {
				t.Errorf("GetClaude200KMultipliers(%q, %d) outputMultiplier = %v, want %v",
					tt.modelName, tt.totalInputTokens, outputMult, tt.expectedOutputMult)
			}
		})
	}
}

func TestClaude200KConstants(t *testing.T) {
	// 验证常量值正确
	if Claude200KThreshold != 200000 {
		t.Errorf("Claude200KThreshold = %d, want 200000", Claude200KThreshold)
	}
	if Claude200KInputMultiplier != 2.0 {
		t.Errorf("Claude200KInputMultiplier = %f, want 2.0", Claude200KInputMultiplier)
	}
	if Claude200KOutputMultiplier != 1.5 {
		t.Errorf("Claude200KOutputMultiplier = %f, want 1.5", Claude200KOutputMultiplier)
	}
}
