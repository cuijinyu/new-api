package aws

import (
	"testing"
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
