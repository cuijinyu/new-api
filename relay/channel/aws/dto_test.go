package aws

import (
	"testing"

	"github.com/QuantumNous/new-api/dto"
)

func TestSanitizeCacheControlForBedrock(t *testing.T) {
	tests := []struct {
		name    string
		content any
		check   func(t *testing.T, content any)
	}{
		{
			name:    "nil content",
			content: nil,
			check:   func(t *testing.T, _ any) {},
		},
		{
			name:    "string content (no-op)",
			content: "hello",
			check:   func(t *testing.T, _ any) {},
		},
		{
			name: "scope removed from cache_control",
			content: []any{
				map[string]any{
					"type": "text",
					"text": "Be concise.",
					"cache_control": map[string]any{
						"type":  "ephemeral",
						"scope": "turn",
					},
				},
			},
			check: func(t *testing.T, content any) {
				blocks := content.([]any)
				cc := blocks[0].(map[string]any)["cache_control"].(map[string]any)
				if _, ok := cc["scope"]; ok {
					t.Error("scope should have been removed")
				}
				if cc["type"] != "ephemeral" {
					t.Error("type should be preserved")
				}
			},
		},
		{
			name: "valid ttl preserved, invalid ttl removed",
			content: []any{
				map[string]any{
					"type": "text",
					"text": "block1",
					"cache_control": map[string]any{
						"type": "ephemeral",
						"ttl":  "5m",
					},
				},
				map[string]any{
					"type": "text",
					"text": "block2",
					"cache_control": map[string]any{
						"type": "ephemeral",
						"ttl":  "10m",
					},
				},
				map[string]any{
					"type": "text",
					"text": "block3",
					"cache_control": map[string]any{
						"type": "ephemeral",
						"ttl":  "1h",
					},
				},
			},
			check: func(t *testing.T, content any) {
				blocks := content.([]any)
				cc0 := blocks[0].(map[string]any)["cache_control"].(map[string]any)
				if cc0["ttl"] != "5m" {
					t.Error("5m should be preserved")
				}
				cc1 := blocks[1].(map[string]any)["cache_control"].(map[string]any)
				if _, ok := cc1["ttl"]; ok {
					t.Error("10m should have been removed")
				}
				cc2 := blocks[2].(map[string]any)["cache_control"].(map[string]any)
				if cc2["ttl"] != "1h" {
					t.Error("1h should be preserved")
				}
			},
		},
		{
			name: "scope and invalid ttl both removed",
			content: []any{
				map[string]any{
					"type": "text",
					"text": "system prompt",
					"cache_control": map[string]any{
						"type":  "ephemeral",
						"scope": "turn",
						"ttl":   "30m",
					},
				},
			},
			check: func(t *testing.T, content any) {
				blocks := content.([]any)
				cc := blocks[0].(map[string]any)["cache_control"].(map[string]any)
				if _, ok := cc["scope"]; ok {
					t.Error("scope should have been removed")
				}
				if _, ok := cc["ttl"]; ok {
					t.Error("30m should have been removed")
				}
				if cc["type"] != "ephemeral" {
					t.Error("type should be preserved")
				}
			},
		},
		{
			name: "blocks without cache_control untouched",
			content: []any{
				map[string]any{
					"type": "text",
					"text": "no cache control here",
				},
			},
			check: func(t *testing.T, content any) {
				blocks := content.([]any)
				if _, ok := blocks[0].(map[string]any)["cache_control"]; ok {
					t.Error("should not have cache_control")
				}
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			sanitizeCacheControlForBedrock(tt.content)
			tt.check(t, tt.content)
		})
	}
}

func TestStripThinkingBlocksForBedrock(t *testing.T) {
	tests := []struct {
		name     string
		msg      dto.ClaudeMessage
		wantLen  int
		wantText string
	}{
		{
			name: "user message untouched",
			msg: dto.ClaudeMessage{
				Role: "user",
				Content: []any{
					map[string]any{"type": "text", "text": "hello"},
				},
			},
			wantLen:  1,
			wantText: "hello",
		},
		{
			name: "assistant: thinking + text → only text remains",
			msg: dto.ClaudeMessage{
				Role: "assistant",
				Content: []any{
					map[string]any{"type": "thinking", "thinking": "let me think...", "signature": "abc123"},
					map[string]any{"type": "text", "text": "the answer is 42"},
				},
			},
			wantLen:  1,
			wantText: "the answer is 42",
		},
		{
			name: "assistant: redacted_thinking + text → only text remains",
			msg: dto.ClaudeMessage{
				Role: "assistant",
				Content: []any{
					map[string]any{"type": "redacted_thinking", "data": "encrypted"},
					map[string]any{"type": "text", "text": "result"},
				},
			},
			wantLen:  1,
			wantText: "result",
		},
		{
			name: "assistant: only thinking → content becomes empty string",
			msg: dto.ClaudeMessage{
				Role: "assistant",
				Content: []any{
					map[string]any{"type": "thinking", "thinking": "hmm", "signature": "sig"},
				},
			},
			wantLen: -1, // special: content should be ""
		},
		{
			name: "assistant: text + tool_use preserved, thinking stripped",
			msg: dto.ClaudeMessage{
				Role: "assistant",
				Content: []any{
					map[string]any{"type": "thinking", "thinking": "plan", "signature": "sig"},
					map[string]any{"type": "text", "text": "calling tool"},
					map[string]any{"type": "tool_use", "id": "t1", "name": "search"},
				},
			},
			wantLen: 2,
		},
		{
			name: "assistant: string content untouched",
			msg: dto.ClaudeMessage{
				Role:    "assistant",
				Content: "simple text",
			},
			wantLen: -2, // special: remains string
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			stripThinkingBlocksForBedrock(&tt.msg)
			switch tt.wantLen {
			case -1:
				if tt.msg.Content != "" {
					t.Errorf("expected empty string content, got %v", tt.msg.Content)
				}
			case -2:
				if _, ok := tt.msg.Content.(string); !ok {
					t.Errorf("expected string content, got %T", tt.msg.Content)
				}
			default:
				blocks, ok := tt.msg.Content.([]any)
				if !ok {
					t.Fatalf("expected []any content, got %T", tt.msg.Content)
				}
				if len(blocks) != tt.wantLen {
					t.Errorf("expected %d blocks, got %d", tt.wantLen, len(blocks))
				}
				if tt.wantText != "" && len(blocks) > 0 {
					text, _ := blocks[0].(map[string]any)["text"].(string)
					if text != tt.wantText {
						t.Errorf("expected text %q, got %q", tt.wantText, text)
					}
				}
				for _, b := range blocks {
					bm, ok := b.(map[string]any)
					if !ok {
						continue
					}
					bt, _ := bm["type"].(string)
					if bt == "thinking" || bt == "redacted_thinking" {
						t.Errorf("thinking block should have been stripped, found type=%s", bt)
					}
				}
			}
		})
	}
}
