package openrouter_inspection

import (
	"testing"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/model"
)

func TestExtractTokensTextAndCache(t *testing.T) {
	logRow := model.Log{
		PromptTokens:     1300,
		CompletionTokens: 200,
	}
	other := map[string]any{
		"cache_tokens":          float64(100),
		"cache_creation_tokens": float64(50),
	}

	got := extractTokens(logRow, other)

	if got.InputTextTokens != 1150 {
		t.Fatalf("InputTextTokens = %d, want 1150", got.InputTextTokens)
	}
	if got.OutputTextTokens != 200 {
		t.Fatalf("OutputTextTokens = %d, want 200", got.OutputTextTokens)
	}
	if got.CacheReadTokens != 100 {
		t.Fatalf("CacheReadTokens = %d, want 100", got.CacheReadTokens)
	}
	if got.CacheWriteTokens != 50 {
		t.Fatalf("CacheWriteTokens = %d, want 50", got.CacheWriteTokens)
	}
}

func TestClassifyRoundingTolerance(t *testing.T) {
	status, reason, _ := classify(104, 100)
	if status != StatusNormal || reason != "rounding_tolerance" {
		t.Fatalf("classify returned status=%s reason=%s, want normal rounding_tolerance", status, reason)
	}
}

func TestClassifyExactMatch(t *testing.T) {
	status, reason, diff := classify(600, 600)
	if status != StatusNormal || reason != "ok" || diff != 0 {
		t.Fatalf("classify returned status=%s reason=%s diff=%f, want normal ok 0", status, reason, diff)
	}
}

func TestClassifyOverchargedCritical(t *testing.T) {
	status, reason, diff := classify(1500, 1000)
	if status != StatusCritical || reason != "overcharged" {
		t.Fatalf("classify returned status=%s reason=%s, want critical overcharged", status, reason)
	}
	if diff < 0.33 {
		t.Fatalf("diff = %f, want large diff", diff)
	}
}

func TestUnsupportedReasonImageAndTool(t *testing.T) {
	if reason := unsupportedReason(map[string]any{"image_generation_call": true}, tokenBreakdown{}); reason != "unsupported_tool_charge" {
		t.Fatalf("reason = %s, want unsupported_tool_charge", reason)
	}
	if reason := unsupportedReason(map[string]any{}, tokenBreakdown{OutputImageTokens: 100}); reason != "unsupported_image_tokens" {
		t.Fatalf("reason = %s, want unsupported_image_tokens", reason)
	}
}

func TestExpectedQuotaExample(t *testing.T) {
	inputPrice := 0.000002
	outputPrice := 0.00001
	expectedUSD := float64(1000)*inputPrice + float64(100)*outputPrice
	expectedQuota := int64(expectedUSD * common.QuotaPerUnit)

	if expectedUSD != 0.003 {
		t.Fatalf("expectedUSD = %f, want 0.003", expectedUSD)
	}
	if expectedQuota != 1500 {
		t.Fatalf("expectedQuota = %d, want 1500", expectedQuota)
	}
}

func TestConvertOpenRouterItem(t *testing.T) {
	item := model.OpenRouterInspectionItem{
		LogID:             123,
		LogCreatedAt:      456,
		ChannelID:         20,
		ModelName:         "gpt-5.4-mini",
		OpenRouterModelID: "openai/gpt-5.4-mini",
		PriceSnapshotID:   7,
		ActualQuota:       600,
		ExpectedQuota:     590,
		DiffRate:          0.016,
		ExpectedUSD:       0.00118,
		ActualUSD:         0.0012,
		SupportLevel:      SupportStandard,
		Status:            StatusWarning,
		ReasonCode:        "overcharged",
		RawContextJSON:    `{"group_ratio":1}`,
		InputTokens:       1000,
		OutputTokens:      100,
	}

	got := convertOpenRouterItem(9, 3, item)

	if got.RunID != 9 || got.SourceRunID != 3 {
		t.Fatalf("run ids = %d/%d, want 9/3", got.RunID, got.SourceRunID)
	}
	if got.SourceProvider != ProviderOpenRouter {
		t.Fatalf("SourceProvider = %q, want %q", got.SourceProvider, ProviderOpenRouter)
	}
	if got.SourceModelID != item.OpenRouterModelID || got.CanonicalModelID != item.OpenRouterModelID {
		t.Fatalf("model ids not copied: %#v", got)
	}
	if got.DeltaQuota != 10 {
		t.Fatalf("DeltaQuota = %d, want 10", got.DeltaQuota)
	}
	if got.Scenario != "text_token" {
		t.Fatalf("Scenario = %q, want text_token", got.Scenario)
	}
	if got.BillingContextJSON != item.RawContextJSON {
		t.Fatalf("BillingContextJSON = %q", got.BillingContextJSON)
	}
}

func TestInspectLogUsesNestedBillingCost(t *testing.T) {
	logRow := model.Log{
		Id:               1,
		CreatedAt:        100,
		ChannelId:        20,
		ModelName:        "gpt-5.4-mini",
		Quota:            600,
		PromptTokens:     1000,
		CompletionTokens: 100,
		Other: `{
			"billing": {
				"provider_model_id": "openai/gpt-5.4-mini",
				"provider_usage_cost": "0.0012",
				"group_ratio": 1,
				"cond_multiplier": 1,
				"input_text_tokens": 1000,
				"output_text_tokens": 100
			}
		}`,
	}

	item := inspectLog(nil, 1, logRow)

	if item.SupportLevel != SupportExact {
		t.Fatalf("SupportLevel = %q, want %q", item.SupportLevel, SupportExact)
	}
	if item.ExpectedQuota != 600 {
		t.Fatalf("ExpectedQuota = %d, want 600", item.ExpectedQuota)
	}
	if item.OpenRouterModelID != "openai/gpt-5.4-mini" {
		t.Fatalf("OpenRouterModelID = %q", item.OpenRouterModelID)
	}
	if item.Status != StatusNormal {
		t.Fatalf("Status = %q", item.Status)
	}
}
