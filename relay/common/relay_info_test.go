package common

import (
	"encoding/json"
	"testing"

	"github.com/QuantumNous/new-api/dto"
	"github.com/QuantumNous/new-api/setting/model_setting"
)

// buildClaudeRequestWithProblematicFields 构造一个带有 context_management 和 cache_control.scope 的
// Claude 风格请求，涵盖 system 数组与 messages 数组两处嵌套 cache_control.scope 位置。
func buildClaudeRequestWithProblematicFields(t *testing.T) []byte {
	t.Helper()
	raw := map[string]interface{}{
		"model":              "claude-sonnet-4-5",
		"max_tokens":         1024,
		"context_management": map[string]interface{}{"auto_truncate": true},
		"system": []interface{}{
			map[string]interface{}{
				"type": "text",
				"text": "you are helpful",
				"cache_control": map[string]interface{}{
					"type":  "ephemeral",
					"ttl":   "5m",
					"scope": "session",
				},
			},
		},
		"messages": []interface{}{
			map[string]interface{}{
				"role": "user",
				"content": []interface{}{
					map[string]interface{}{
						"type": "text",
						"text": "hello",
						"cache_control": map[string]interface{}{
							"type":  "ephemeral",
							"scope": "session",
						},
					},
				},
			},
		},
	}
	b, err := json.Marshal(raw)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return b
}

// unmarshalOrFail 解析 JSON 到通用 map，失败即中断测试。
func unmarshalOrFail(t *testing.T, data []byte) map[string]interface{} {
	t.Helper()
	var m map[string]interface{}
	if err := json.Unmarshal(data, &m); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	return m
}

// firstBlockCacheControl 提取第 i 个 content block 里的 cache_control map；不存在则返回 nil。
func firstBlockCacheControl(t *testing.T, blocks interface{}) map[string]interface{} {
	t.Helper()
	arr, ok := blocks.([]interface{})
	if !ok || len(arr) == 0 {
		return nil
	}
	block, ok := arr[0].(map[string]interface{})
	if !ok {
		return nil
	}
	cc, _ := block["cache_control"].(map[string]interface{})
	return cc
}

func TestRemoveDisabledFields_DefaultStripsContextManagementAndCacheControlScope(t *testing.T) {
	input := buildClaudeRequestWithProblematicFields(t)

	out, err := RemoveDisabledFields(input, dto.ChannelOtherSettings{}, false)
	if err != nil {
		t.Fatalf("RemoveDisabledFields: %v", err)
	}

	m := unmarshalOrFail(t, out)

	if _, ok := m["context_management"]; ok {
		t.Errorf("expected context_management to be stripped, still present: %#v", m["context_management"])
	}

	sysCC := firstBlockCacheControl(t, m["system"])
	if sysCC == nil {
		t.Fatalf("system cache_control missing after sanitize: %#v", m["system"])
	}
	if _, ok := sysCC["scope"]; ok {
		t.Errorf("expected system cache_control.scope to be stripped, still present: %#v", sysCC)
	}
	if _, ok := sysCC["type"]; !ok {
		t.Errorf("expected system cache_control.type preserved, got: %#v", sysCC)
	}
	if _, ok := sysCC["ttl"]; !ok {
		t.Errorf("expected system cache_control.ttl preserved, got: %#v", sysCC)
	}

	msgs, _ := m["messages"].([]interface{})
	if len(msgs) == 0 {
		t.Fatalf("messages missing after sanitize: %#v", m["messages"])
	}
	firstMsg, _ := msgs[0].(map[string]interface{})
	msgCC := firstBlockCacheControl(t, firstMsg["content"])
	if msgCC == nil {
		t.Fatalf("messages[0].content cache_control missing after sanitize: %#v", firstMsg["content"])
	}
	if _, ok := msgCC["scope"]; ok {
		t.Errorf("expected messages[0].content cache_control.scope to be stripped, still present: %#v", msgCC)
	}
}

func TestRemoveDisabledFields_AllowFlagsPreserveFields(t *testing.T) {
	input := buildClaudeRequestWithProblematicFields(t)

	out, err := RemoveDisabledFields(input, dto.ChannelOtherSettings{
		AllowContextManagement: true,
		AllowCacheControlScope: true,
	}, false)
	if err != nil {
		t.Fatalf("RemoveDisabledFields: %v", err)
	}

	m := unmarshalOrFail(t, out)

	if _, ok := m["context_management"]; !ok {
		t.Errorf("expected context_management preserved when AllowContextManagement=true, got: %#v", m)
	}

	sysCC := firstBlockCacheControl(t, m["system"])
	if sysCC == nil || sysCC["scope"] != "session" {
		t.Errorf("expected system cache_control.scope preserved, got: %#v", sysCC)
	}

	msgs, _ := m["messages"].([]interface{})
	firstMsg, _ := msgs[0].(map[string]interface{})
	msgCC := firstBlockCacheControl(t, firstMsg["content"])
	if msgCC == nil || msgCC["scope"] != "session" {
		t.Errorf("expected messages[0].content cache_control.scope preserved, got: %#v", msgCC)
	}
}

func TestRemoveDisabledFields_ChannelPassThroughReturnsRaw(t *testing.T) {
	input := buildClaudeRequestWithProblematicFields(t)

	out, err := RemoveDisabledFields(input, dto.ChannelOtherSettings{}, true)
	if err != nil {
		t.Fatalf("RemoveDisabledFields: %v", err)
	}

	if string(out) != string(input) {
		t.Errorf("expected raw body to be returned when channelPassThroughEnabled=true")
	}
}

func TestRemoveDisabledFields_GlobalPassThroughReturnsRaw(t *testing.T) {
	input := buildClaudeRequestWithProblematicFields(t)

	gs := model_setting.GetGlobalSettings()
	original := gs.PassThroughRequestEnabled
	gs.PassThroughRequestEnabled = true
	defer func() { gs.PassThroughRequestEnabled = original }()

	out, err := RemoveDisabledFields(input, dto.ChannelOtherSettings{}, false)
	if err != nil {
		t.Fatalf("RemoveDisabledFields: %v", err)
	}

	if string(out) != string(input) {
		t.Errorf("expected raw body to be returned when global PassThroughRequestEnabled=true")
	}
}

func TestRemoveDisabledFields_StringSystemAndStringContentAreUnaffected(t *testing.T) {
	raw := map[string]interface{}{
		"model":              "claude-sonnet-4-5",
		"context_management": map[string]interface{}{"auto_truncate": true},
		"system":             "you are helpful",
		"messages": []interface{}{
			map[string]interface{}{"role": "user", "content": "hello"},
		},
	}
	input, err := json.Marshal(raw)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	out, err := RemoveDisabledFields(input, dto.ChannelOtherSettings{}, false)
	if err != nil {
		t.Fatalf("RemoveDisabledFields: %v", err)
	}

	m := unmarshalOrFail(t, out)

	if _, ok := m["context_management"]; ok {
		t.Errorf("expected context_management to be stripped with string system/content, got: %#v", m)
	}
	if s, _ := m["system"].(string); s != "you are helpful" {
		t.Errorf("expected string system preserved, got: %#v", m["system"])
	}
	msgs, _ := m["messages"].([]interface{})
	if len(msgs) != 1 {
		t.Fatalf("unexpected messages shape: %#v", m["messages"])
	}
	firstMsg, _ := msgs[0].(map[string]interface{})
	if c, _ := firstMsg["content"].(string); c != "hello" {
		t.Errorf("expected string content preserved, got: %#v", firstMsg["content"])
	}
}
