package dto

import "testing"

func TestGeneralOpenAIRequestGetSystemRoleName(t *testing.T) {
	tests := []struct {
		name  string
		model string
		want  string
	}{
		{name: "o1 uses developer", model: "o1", want: "developer"},
		{name: "o3 uses developer", model: "o3-mini", want: "developer"},
		{name: "o4 uses developer", model: "o4-mini", want: "developer"},
		{name: "gpt5 uses developer", model: "gpt-5.1", want: "developer"},
		{name: "o1 mini keeps system", model: "o1-mini", want: "system"},
		{name: "o1 preview keeps system", model: "o1-preview", want: "system"},
		{name: "omni is not an OpenAI o reasoning model", model: "omni-large", want: "system"},
		{name: "openrouter is not an OpenAI o reasoning model", model: "openrouter/auto", want: "system"},
		{name: "ollama is not an OpenAI o reasoning model", model: "ollama/llama3", want: "system"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := GeneralOpenAIRequest{Model: tt.model}
			if got := req.GetSystemRoleName(); got != tt.want {
				t.Fatalf("GetSystemRoleName() = %q, want %q", got, tt.want)
			}
		})
	}
}
