package service

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/QuantumNous/new-api/constant"
	"github.com/QuantumNous/new-api/dto"
	relaycommon "github.com/QuantumNous/new-api/relay/common"
)

func TestAppendBillingContextOtherOpenRouter(t *testing.T) {
	other := map[string]interface{}{
		"group_ratio":        1.2,
		"completion_ratio":   6.0,
		"cache_tokens":       10,
		"input_text_tokens":  100,
		"output_text_tokens": 20,
	}
	usage := &dto.Usage{
		PromptTokens:     110,
		CompletionTokens: 20,
		Cost:             "0.00123",
	}
	usage.PromptTokensDetails.CachedTokens = 10
	info := &relaycommon.RelayInfo{
		OriginModelName: "gpt-5.4-mini",
		ChannelMeta: &relaycommon.ChannelMeta{
			ChannelType:       constant.ChannelTypeOpenRouter,
			UpstreamModelName: "openai/gpt-5.4-mini",
		},
	}

	AppendBillingContextOther(other, info, usage, 615)

	if other["openrouter_model_id"] != "openai/gpt-5.4-mini" {
		t.Fatalf("openrouter_model_id = %#v", other["openrouter_model_id"])
	}
	if other["openrouter_cost"] != 0.00123 {
		t.Fatalf("openrouter_cost = %#v", other["openrouter_cost"])
	}
	billing, ok := other["billing"].(map[string]interface{})
	if !ok {
		t.Fatalf("billing missing or wrong type: %#v", other["billing"])
	}
	if billing["source_provider"] != "openrouter" {
		t.Fatalf("source_provider = %#v", billing["source_provider"])
	}
	if billing["provider_model_id"] != "openai/gpt-5.4-mini" {
		t.Fatalf("provider_model_id = %#v", billing["provider_model_id"])
	}
	if billing["input_text_tokens"] != 100 {
		t.Fatalf("input_text_tokens = %#v", billing["input_text_tokens"])
	}
	if billing["input_total_tokens"] != 110 {
		t.Fatalf("input_total_tokens = %#v", billing["input_total_tokens"])
	}
	if billing["output_total_tokens"] != 20 {
		t.Fatalf("output_total_tokens = %#v", billing["output_total_tokens"])
	}
	if billing["cache_read_tokens"] != 10 {
		t.Fatalf("cache_read_tokens = %#v", billing["cache_read_tokens"])
	}
	if billing["provider_usage_cost"] != 0.00123 {
		t.Fatalf("provider_usage_cost = %#v", billing["provider_usage_cost"])
	}
	if billing["scenario"] != "text_token" {
		t.Fatalf("scenario = %#v", billing["scenario"])
	}
}

func TestAppendBillingContextOtherImageScenario(t *testing.T) {
	other := map[string]interface{}{
		"output_image_tokens":         1409,
		"image_completion_ratio":      2.0,
		"image_generation_call":       true,
		"image_generation_call_price": 0.04,
	}
	info := &relaycommon.RelayInfo{
		OriginModelName: "gemini-2.5-flash-image",
		ChannelMeta: &relaycommon.ChannelMeta{
			ChannelType:       constant.ChannelTypeGemini,
			UpstreamModelName: "gemini-2.5-flash-image",
		},
	}

	AppendBillingContextOther(other, info, &dto.Usage{}, 1000)

	billing := other["billing"].(map[string]interface{})
	if billing["source_provider"] != "google" {
		t.Fatalf("source_provider = %#v", billing["source_provider"])
	}
	if billing["scenario"] != "image_generation" {
		t.Fatalf("scenario = %#v", billing["scenario"])
	}
	if billing["output_image_tokens"] != 1409 {
		t.Fatalf("output_image_tokens = %#v", billing["output_image_tokens"])
	}
	if billing["image_completion_ratio"] != 2.0 {
		t.Fatalf("image_completion_ratio = %#v", billing["image_completion_ratio"])
	}
	if billing["image_generation_call_price"] != 0.04 {
		t.Fatalf("image_generation_call_price = %#v", billing["image_generation_call_price"])
	}
}

func TestAppendBillingContextOtherGeminiToolUseTokens(t *testing.T) {
	other := map[string]interface{}{
		"group_ratio":      1.0,
		"completion_ratio": 1.0,
	}
	usage := &dto.Usage{
		PromptTokens:        125,
		CompletionTokens:    55,
		TotalTokens:         180,
		ToolUsePromptTokens: 25,
	}
	usage.CompletionTokenDetails.ReasoningTokens = 15
	info := &relaycommon.RelayInfo{
		OriginModelName: "gemini-2.5-pro",
		ChannelMeta: &relaycommon.ChannelMeta{
			ChannelType:       constant.ChannelTypeGemini,
			UpstreamModelName: "gemini-2.5-pro",
		},
	}

	AppendBillingContextOther(other, info, usage, 180)

	billing := other["billing"].(map[string]interface{})
	if billing["input_total_tokens"] != 125 {
		t.Fatalf("input_total_tokens = %#v", billing["input_total_tokens"])
	}
	if billing["input_tool_use_tokens"] != 25 {
		t.Fatalf("input_tool_use_tokens = %#v", billing["input_tool_use_tokens"])
	}
	if billing["output_reasoning_tokens"] != 15 {
		t.Fatalf("output_reasoning_tokens = %#v", billing["output_reasoning_tokens"])
	}

	body, err := json.Marshal(usage)
	if err != nil {
		t.Fatalf("marshal usage: %v", err)
	}
	if strings.Contains(string(body), "tool_use") {
		t.Fatalf("internal tool-use tokens leaked to usage JSON: %s", string(body))
	}
}
