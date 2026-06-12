package price_inspection

import (
	"strings"
	"testing"
	"time"

	"github.com/QuantumNous/new-api/constant"
	"github.com/QuantumNous/new-api/model"
	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
)

func TestInspectGenericLogExactBillingCost(t *testing.T) {
	logRow := model.Log{
		Id:               1,
		CreatedAt:        100,
		ChannelId:        24,
		ModelName:        "gemini-2.5-pro",
		Quota:            1200,
		PromptTokens:     1000,
		CompletionTokens: 100,
		Other: `{
			"billing": {
				"source_provider": "google",
				"provider_model_id": "google/gemini-2.5-pro",
				"provider_usage_cost": "0.0024",
				"group_ratio": 1,
				"cond_multiplier": 1,
				"scenario": "text_token"
			}
		}`,
	}

	item, ok := inspectGenericLog(9, logRow, constant.ChannelTypeGemini, RunRequest{SourceProvider: "google"})

	if !ok {
		t.Fatal("inspectGenericLog skipped log")
	}
	if item.SupportLevel != SupportExact {
		t.Fatalf("SupportLevel = %q, want exact", item.SupportLevel)
	}
	if item.ExpectedQuota != 1200 {
		t.Fatalf("ExpectedQuota = %d, want 1200", item.ExpectedQuota)
	}
	if item.Status != StatusNormal {
		t.Fatalf("Status = %q, want normal", item.Status)
	}
	if item.SourceProvider != "google" || item.SourceModelID != "google/gemini-2.5-pro" {
		t.Fatalf("provider/model not copied: %#v", item)
	}
}

func TestInspectGenericLogExactOpenRouterCostWithoutBilling(t *testing.T) {
	logRow := model.Log{
		Id:           26,
		CreatedAt:    100,
		ChannelId:    99,
		ModelName:    "gpt-5-mini",
		Quota:        225,
		Other:        `{"openrouter_model_id":"openai/gpt-5-mini","openrouter_cost":0.00045,"group_ratio":1}`,
		PromptTokens: 1000,
	}

	item, ok := inspectGenericLog(9, logRow, constant.ChannelTypeOpenRouter, RunRequest{SourceProvider: "openrouter"})

	if !ok {
		t.Fatal("inspectGenericLog should not skip exact openrouter_cost log")
	}
	if item.SupportLevel != SupportExact {
		t.Fatalf("SupportLevel = %q, want exact", item.SupportLevel)
	}
	if item.ExpectedQuota != 225 {
		t.Fatalf("ExpectedQuota = %d, want 225", item.ExpectedQuota)
	}
	if item.SourceModelID != "openai/gpt-5-mini" {
		t.Fatalf("SourceModelID = %q", item.SourceModelID)
	}
	if item.Status != StatusNormal {
		t.Fatalf("Status = %q, want normal", item.Status)
	}
}

func TestInspectGenericLogStandardModelRatioBilling(t *testing.T) {
	logRow := model.Log{
		Id:        2,
		CreatedAt: 100,
		ChannelId: 1,
		ModelName: "gpt-5",
		Quota:     260,
		Other: `{
			"billing": {
				"source_provider": "openai",
				"provider_model_id": "gpt-5",
				"scenario": "text_token",
				"input_total_tokens": 100,
				"input_tool_use_tokens": 25,
				"output_total_tokens": 10,
				"model_ratio": 2,
				"completion_ratio": 3,
				"group_ratio": 1,
				"cond_multiplier": 1
			}
		}`,
	}

	item, ok := inspectGenericLog(9, logRow, constant.ChannelTypeOpenAI, RunRequest{SourceProvider: "openai"})

	if !ok {
		t.Fatal("inspectGenericLog skipped log")
	}
	if item.SupportLevel != SupportStandard {
		t.Fatalf("SupportLevel = %q, want standard", item.SupportLevel)
	}
	if item.ExpectedQuota != 260 {
		t.Fatalf("ExpectedQuota = %d, want 260", item.ExpectedQuota)
	}
	if item.Status != StatusNormal {
		t.Fatalf("Status = %q, want normal", item.Status)
	}
	if !strings.Contains(item.CalculatorTraceJSON, `"input_tool_use_tokens":25`) {
		t.Fatalf("CalculatorTraceJSON should include input_tool_use_tokens: %s", item.CalculatorTraceJSON)
	}
}

func TestScanInspectionLogsIncludesExactCostWithoutBilling(t *testing.T) {
	setupInspectionScanDB(t)
	now := time.Now().Unix()
	if err := model.DB.Create(&model.Channel{
		Id:     99,
		Type:   constant.ChannelTypeOpenRouter,
		Key:    "sk-test",
		Name:   "openrouter-test",
		Models: "gpt-5-mini",
	}).Error; err != nil {
		t.Fatalf("create channel: %v", err)
	}
	if err := model.LOG_DB.Create(&model.Log{
		CreatedAt: now,
		Type:      model.LogTypeConsume,
		ChannelId: 99,
		ModelName: "gpt-5-mini",
		Quota:     225,
		Other:     `{"openrouter_model_id":"openai/gpt-5-mini","openrouter_cost":0.00045}`,
	}).Error; err != nil {
		t.Fatalf("create log: %v", err)
	}

	logs, channelTypes, err := scanInspectionLogs(RunRequest{
		WindowStart:    now - 60,
		WindowEnd:      now + 60,
		SourceProvider: ProviderOpenRouter,
		Limit:          10,
	})
	if err != nil {
		t.Fatalf("scanInspectionLogs: %v", err)
	}
	if len(logs) != 1 {
		t.Fatalf("len(logs) = %d, want 1", len(logs))
	}
	if channelTypes[99] != constant.ChannelTypeOpenRouter {
		t.Fatalf("channelTypes[99] = %d", channelTypes[99])
	}
}

func setupInspectionScanDB(t *testing.T) {
	t.Helper()
	previousDB := model.DB
	previousLogDB := model.LOG_DB
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open db sqlite: %v", err)
	}
	logDB, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open log sqlite: %v", err)
	}
	model.DB = db
	model.LOG_DB = logDB
	t.Cleanup(func() {
		model.DB = previousDB
		model.LOG_DB = previousLogDB
	})
	if err := model.DB.AutoMigrate(&model.Channel{}); err != nil {
		t.Fatalf("AutoMigrate channel: %v", err)
	}
	if err := model.LOG_DB.AutoMigrate(&model.Log{}); err != nil {
		t.Fatalf("AutoMigrate log: %v", err)
	}
}

func TestInspectGenericLogStandardModelPriceBilling(t *testing.T) {
	logRow := model.Log{
		Id:        20,
		CreatedAt: 100,
		ChannelId: 1,
		ModelName: "gpt-5",
		Quota:     1200,
		Other: `{
			"billing": {
				"source_provider": "openai",
				"provider_model_id": "gpt-5",
				"scenario": "text_token",
				"model_price": 0.0024,
				"group_ratio": 1,
				"cond_multiplier": 1
			}
		}`,
	}

	item, ok := inspectGenericLog(9, logRow, constant.ChannelTypeOpenAI, RunRequest{SourceProvider: "openai"})

	if !ok {
		t.Fatal("inspectGenericLog skipped log")
	}
	if item.SupportLevel != SupportStandard {
		t.Fatalf("SupportLevel = %q, want standard", item.SupportLevel)
	}
	if item.ExpectedQuota != 1200 {
		t.Fatalf("ExpectedQuota = %d, want 1200", item.ExpectedQuota)
	}
	if item.Status != StatusNormal {
		t.Fatalf("Status = %q, want normal", item.Status)
	}
}

func TestInspectGenericLogSnapshotBilling(t *testing.T) {
	previousDB := model.DB
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	model.DB = db
	t.Cleanup(func() {
		model.DB = previousDB
	})
	if err := model.DB.AutoMigrate(&model.PriceSourceSnapshot{}, &model.PriceModelMapping{}); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}
	if err := model.CreatePriceModelMapping(&model.PriceModelMapping{
		ChannelID:        1,
		ChannelType:      constant.ChannelTypeOpenAI,
		LocalModelName:   "gpt-alias",
		SourceProvider:   "openai",
		SourceModelID:    "gpt-5-mini",
		CanonicalModelID: "gpt-5-mini",
		Scenario:         "text_token",
		Enabled:          true,
	}); err != nil {
		t.Fatalf("CreatePriceModelMapping: %v", err)
	}
	if err := model.InsertPriceSourceSnapshots([]model.PriceSourceSnapshot{
		{
			SourceProvider:      "openai",
			FetchedAt:           90,
			ModelID:             "gpt-5-mini",
			CanonicalModelID:    "gpt-5-mini",
			LocalModelName:      "gpt-5-mini",
			Scenario:            "text_token",
			PricingScheme:       "per_token",
			InputPricePerToken:  0.00000025,
			OutputPricePerToken: 0.000002,
			Manual:              true,
		},
	}); err != nil {
		t.Fatalf("InsertPriceSourceSnapshots: %v", err)
	}
	logRow := model.Log{
		Id:               24,
		CreatedAt:        100,
		ChannelId:        1,
		ModelName:        "gpt-alias",
		Quota:            225,
		PromptTokens:     1000,
		CompletionTokens: 100,
		Other: `{
			"billing": {
				"source_provider": "openai",
				"scenario": "text_token"
			}
		}`,
	}

	item, ok := inspectGenericLog(9, logRow, constant.ChannelTypeOpenAI, RunRequest{SourceProvider: "openai"})

	if !ok {
		t.Fatal("inspectGenericLog skipped log")
	}
	if item.SupportLevel != SupportStandard {
		t.Fatalf("SupportLevel = %q, want standard", item.SupportLevel)
	}
	if item.ExpectedQuota != 225 {
		t.Fatalf("ExpectedQuota = %d, want 225", item.ExpectedQuota)
	}
	if item.PriceSnapshotID == 0 {
		t.Fatal("PriceSnapshotID should be set")
	}
	if item.SourceModelID != "gpt-5-mini" {
		t.Fatalf("SourceModelID = %q, want gpt-5-mini", item.SourceModelID)
	}
	if item.Status != StatusNormal {
		t.Fatalf("Status = %q, want normal", item.Status)
	}
	if !strings.Contains(item.CalculatorTraceJSON, "price_source_snapshot") {
		t.Fatalf("CalculatorTraceJSON = %s", item.CalculatorTraceJSON)
	}
}

func TestInspectGenericLogSnapshotBillingManualSnapshotAfterLog(t *testing.T) {
	previousDB := model.DB
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	model.DB = db
	t.Cleanup(func() {
		model.DB = previousDB
	})
	if err := model.DB.AutoMigrate(&model.PriceSourceSnapshot{}, &model.PriceModelMapping{}); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}
	if err := model.InsertPriceSourceSnapshots([]model.PriceSourceSnapshot{
		{
			SourceProvider:      "openai",
			FetchedAt:           200,
			ModelID:             "gpt-5-mini",
			CanonicalModelID:    "gpt-5-mini",
			LocalModelName:      "gpt-5-mini",
			Scenario:            "text_token",
			PricingScheme:       "per_token",
			InputPricePerToken:  0.00000025,
			OutputPricePerToken: 0.000002,
			Manual:              true,
		},
	}); err != nil {
		t.Fatalf("InsertPriceSourceSnapshots: %v", err)
	}
	logRow := model.Log{
		Id:               29,
		CreatedAt:        100,
		ChannelId:        1,
		ModelName:        "gpt-5-mini",
		Quota:            225,
		PromptTokens:     1000,
		CompletionTokens: 100,
		Other: `{
			"billing": {
				"source_provider": "openai",
				"provider_model_id": "gpt-5-mini",
				"scenario": "text_token"
			}
		}`,
	}

	item, ok := inspectGenericLog(9, logRow, constant.ChannelTypeOpenAI, RunRequest{SourceProvider: "openai"})

	if !ok {
		t.Fatal("inspectGenericLog skipped log")
	}
	if item.ExpectedQuota != 225 || item.Status != StatusNormal {
		t.Fatalf("item = %#v", item)
	}
	if !strings.Contains(item.CalculatorTraceJSON, "model_manual_latest_after_log") {
		t.Fatalf("CalculatorTraceJSON = %s", item.CalculatorTraceJSON)
	}
}

func TestInspectGenericLogSnapshotBillingCacheWriteTiers(t *testing.T) {
	previousDB := model.DB
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	model.DB = db
	t.Cleanup(func() {
		model.DB = previousDB
	})
	if err := model.DB.AutoMigrate(&model.PriceSourceSnapshot{}, &model.PriceModelMapping{}); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}
	if err := model.InsertPriceSourceSnapshots([]model.PriceSourceSnapshot{
		{
			SourceProvider:            "anthropic",
			FetchedAt:                 90,
			ModelID:                   "claude-sonnet-4",
			CanonicalModelID:          "claude-sonnet-4",
			LocalModelName:            "claude-sonnet-4",
			Scenario:                  "text_token",
			PricingScheme:             "per_token",
			CacheWritePricePerToken:   0.000001,
			CacheWrite5mPricePerToken: 0.00000125,
			CacheWrite1hPricePerToken: 0.000002,
			Manual:                    true,
		},
	}); err != nil {
		t.Fatalf("InsertPriceSourceSnapshots: %v", err)
	}
	logRow := model.Log{
		Id:        27,
		CreatedAt: 100,
		ChannelId: 3,
		ModelName: "claude-sonnet-4",
		Quota:     73,
		Other: `{
			"billing": {
				"source_provider": "anthropic",
				"provider_model_id": "claude-sonnet-4",
				"scenario": "text_token",
				"input_total_tokens": 100,
				"cache_write_tokens": 100,
				"cache_write_5m_tokens": 60,
				"cache_write_1h_tokens": 30,
				"group_ratio": 1,
				"cond_multiplier": 1
			}
		}`,
	}

	item, ok := inspectGenericLog(9, logRow, constant.ChannelTypeAnthropic, RunRequest{SourceProvider: "anthropic"})

	if !ok {
		t.Fatal("inspectGenericLog skipped log")
	}
	if item.ExpectedQuota != 73 {
		t.Fatalf("ExpectedQuota = %d, want 73", item.ExpectedQuota)
	}
	if item.Status != StatusNormal || item.SupportLevel != SupportStandard {
		t.Fatalf("item = %#v", item)
	}
	if !strings.Contains(item.CalculatorTraceJSON, "cache_write_5m_price_per_token") {
		t.Fatalf("CalculatorTraceJSON = %s", item.CalculatorTraceJSON)
	}
}

func TestInspectGenericLogSnapshotBillingMediaTokenPrices(t *testing.T) {
	previousDB := model.DB
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	model.DB = db
	t.Cleanup(func() {
		model.DB = previousDB
	})
	if err := model.DB.AutoMigrate(&model.PriceSourceSnapshot{}, &model.PriceModelMapping{}); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}
	if err := model.InsertPriceSourceSnapshots([]model.PriceSourceSnapshot{
		{
			SourceProvider:           "google",
			FetchedAt:                90,
			ModelID:                  "gemini-2.5-flash-image",
			CanonicalModelID:         "gemini-2.5-flash-image",
			LocalModelName:           "gemini-2.5-flash-image",
			Scenario:                 "image_generation",
			PricingScheme:            "per_token",
			InputImagePricePerToken:  0.000001,
			OutputImagePricePerToken: 0.000002,
			InputAudioPricePerToken:  0.000003,
			OutputAudioPricePerToken: 0.000004,
			Manual:                   true,
		},
	}); err != nil {
		t.Fatalf("InsertPriceSourceSnapshots: %v", err)
	}
	logRow := model.Log{
		Id:        28,
		CreatedAt: 100,
		ChannelId: 24,
		ModelName: "gemini-2.5-flash-image",
		Quota:     150,
		Other: `{
			"billing": {
				"source_provider": "google",
				"provider_model_id": "gemini-2.5-flash-image",
				"scenario": "image_generation",
				"input_image_tokens": 100,
				"output_image_tokens": 50,
				"input_audio_tokens": 20,
				"output_audio_tokens": 10,
				"group_ratio": 1,
				"cond_multiplier": 1
			}
		}`,
	}

	item, ok := inspectGenericLog(9, logRow, constant.ChannelTypeGemini, RunRequest{SourceProvider: "google"})

	if !ok {
		t.Fatal("inspectGenericLog skipped log")
	}
	if item.ExpectedQuota != 150 {
		t.Fatalf("ExpectedQuota = %d, want 150", item.ExpectedQuota)
	}
	if item.Status != StatusNormal || item.SupportLevel != SupportStandard {
		t.Fatalf("item = %#v", item)
	}
	if !strings.Contains(item.CalculatorTraceJSON, "output_audio_tokens") {
		t.Fatalf("CalculatorTraceJSON = %s", item.CalculatorTraceJSON)
	}
}

func TestInspectGenericLogOpenRouterLegacySnapshotBilling(t *testing.T) {
	previousDB := model.DB
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	model.DB = db
	t.Cleanup(func() {
		model.DB = previousDB
	})
	if err := model.DB.AutoMigrate(&model.PriceSourceSnapshot{}, &model.OpenRouterPriceSnapshot{}); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}
	if err := model.InsertOpenRouterPriceSnapshots([]model.OpenRouterPriceSnapshot{
		{
			FetchedAt:               90,
			ModelID:                 "openai/gpt-5-mini",
			CanonicalSlug:           "openai/gpt-5-mini",
			LocalModelName:          "gpt-5-mini",
			PromptPricePerToken:     0.00000025,
			CompletionPricePerToken: 0.000002,
		},
	}); err != nil {
		t.Fatalf("InsertOpenRouterPriceSnapshots: %v", err)
	}
	logRow := model.Log{
		Id:               25,
		CreatedAt:        100,
		ChannelId:        99,
		ModelName:        "gpt-5-mini",
		Quota:            225,
		PromptTokens:     1000,
		CompletionTokens: 100,
		Other: `{
			"billing": {
				"source_provider": "openrouter",
				"provider_model_id": "openai/gpt-5-mini",
				"scenario": "text_token"
			}
		}`,
	}

	item, ok := inspectGenericLog(9, logRow, constant.ChannelTypeOpenRouter, RunRequest{SourceProvider: "openrouter"})

	if !ok {
		t.Fatal("inspectGenericLog skipped log")
	}
	if item.ExpectedQuota != 225 {
		t.Fatalf("ExpectedQuota = %d, want 225", item.ExpectedQuota)
	}
	if item.PriceSnapshotID == 0 {
		t.Fatal("PriceSnapshotID should be set from legacy OpenRouter snapshot")
	}
	if item.SupportLevel != SupportStandard || item.Status != StatusNormal {
		t.Fatalf("item = %#v", item)
	}
	if !strings.Contains(item.CalculatorTraceJSON, "openrouter_exact_history") {
		t.Fatalf("CalculatorTraceJSON = %s", item.CalculatorTraceJSON)
	}
}

func TestInspectGenericLogStandardImageTokenBilling(t *testing.T) {
	logRow := model.Log{
		Id:        21,
		CreatedAt: 100,
		ChannelId: 24,
		ModelName: "gemini-2.5-flash-image",
		Quota:     640,
		Other: `{
			"billing": {
				"source_provider": "google",
				"provider_model_id": "gemini-2.5-flash-image",
				"scenario": "image_generation",
				"input_total_tokens": 100,
				"input_image_tokens": 40,
				"output_total_tokens": 100,
				"output_image_tokens": 100,
				"model_ratio": 2,
				"completion_ratio": 3,
				"image_ratio": 1.5,
				"image_completion_ratio": 2,
				"group_ratio": 1,
				"cond_multiplier": 1
			}
		}`,
	}

	item, ok := inspectGenericLog(9, logRow, constant.ChannelTypeGemini, RunRequest{SourceProvider: "google"})

	if !ok {
		t.Fatal("inspectGenericLog skipped log")
	}
	if item.SupportLevel != SupportStandard {
		t.Fatalf("SupportLevel = %q, want standard", item.SupportLevel)
	}
	if item.ExpectedQuota != 640 {
		t.Fatalf("ExpectedQuota = %d, want 640", item.ExpectedQuota)
	}
	if item.Status != StatusNormal {
		t.Fatalf("Status = %q, want normal", item.Status)
	}
}

func TestInspectGenericLogMissingCostAndStandardContext(t *testing.T) {
	logRow := model.Log{
		Id:        22,
		CreatedAt: 100,
		ChannelId: 1,
		ModelName: "gpt-5",
		Quota:     100,
		Other: `{
			"billing": {
				"source_provider": "openai",
				"provider_model_id": "gpt-5",
				"scenario": "text_token"
			}
		}`,
	}

	item, ok := inspectGenericLog(9, logRow, constant.ChannelTypeOpenAI, RunRequest{SourceProvider: "openai"})

	if !ok {
		t.Fatal("inspectGenericLog skipped log")
	}
	if item.Status != StatusMissing {
		t.Fatalf("Status = %q, want missing", item.Status)
	}
	if item.ReasonCode != "missing_standard_pricing_context" {
		t.Fatalf("ReasonCode = %q", item.ReasonCode)
	}
}

func TestInspectGenericLogInvalidCostFallsBackToStandard(t *testing.T) {
	logRow := model.Log{
		Id:        23,
		CreatedAt: 100,
		ChannelId: 1,
		ModelName: "gpt-5",
		Quota:     120,
		Other: `{
			"billing": {
				"source_provider": "openai",
				"provider_model_id": "gpt-5",
				"provider_usage_cost": "not-a-number",
				"scenario": "text_token",
				"input_total_tokens": 100,
				"output_total_tokens": 20,
				"model_ratio": 1,
				"completion_ratio": 1
			}
		}`,
	}

	item, ok := inspectGenericLog(9, logRow, constant.ChannelTypeOpenAI, RunRequest{SourceProvider: "openai"})

	if !ok {
		t.Fatal("inspectGenericLog skipped log")
	}
	if item.ExpectedQuota != 120 || item.SupportLevel != SupportStandard {
		t.Fatalf("invalid provider cost should fall back to standard billing: %#v", item)
	}
}

func TestInspectGenericLogOutOfScopeVideoTask(t *testing.T) {
	logRow := model.Log{
		Id:        3,
		CreatedAt: 100,
		ChannelId: 50,
		ModelName: "kling-v2-6",
		Quota:     100,
		Other: `{
			"billing": {
				"source_provider": "kling",
				"provider_model_id": "kling-v2-6",
				"provider_usage_cost": "0.1",
				"scenario": "video_task"
			}
		}`,
	}

	item, ok := inspectGenericLog(9, logRow, constant.ChannelTypeKling, RunRequest{SourceProvider: "kling"})

	if !ok {
		t.Fatal("inspectGenericLog skipped log")
	}
	if item.Status != StatusOutOfScope {
		t.Fatalf("Status = %q, want out_of_scope", item.Status)
	}
	if item.SupportLevel != SupportOutOfScope {
		t.Fatalf("SupportLevel = %q, want out_of_scope", item.SupportLevel)
	}
}

func TestInspectGenericLogSkipsProviderMismatch(t *testing.T) {
	logRow := model.Log{
		Id:        4,
		CreatedAt: 100,
		ChannelId: 24,
		ModelName: "gemini-2.5-pro",
		Quota:     1200,
		Other: `{
			"billing": {
				"source_provider": "google",
				"provider_usage_cost": "0.0024"
			}
		}`,
	}

	_, ok := inspectGenericLog(9, logRow, constant.ChannelTypeGemini, RunRequest{SourceProvider: "openai"})

	if ok {
		t.Fatal("inspectGenericLog should skip provider mismatch")
	}
}

func TestNormalizeProviderAliases(t *testing.T) {
	cases := map[string]string{
		"Gemini":       "google",
		"vertex_ai":    "google",
		"Claude":       "anthropic",
		"Azure-OpenAI": "azure",
		"OpenAI-Max":   "openai",
		"OpenRouter":   ProviderOpenRouter,
	}
	for input, want := range cases {
		if got := normalizeProvider(input); got != want {
			t.Fatalf("normalizeProvider(%q) = %q, want %q", input, got, want)
		}
	}
}

func TestClassifyQuotaUsesConfigurableThresholds(t *testing.T) {
	status, reason, _ := classifyQuota(1030, 1000)
	if status != StatusAbnormal || reason != "overcharged" {
		t.Fatalf("default classifyQuota status=%q reason=%q, want abnormal overcharged", status, reason)
	}

	t.Setenv("PRICE_INSPECTION_WARNING_DIFF_RATE", "0.04")
	t.Setenv("PRICE_INSPECTION_ABNORMAL_DIFF_RATE", "0.08")
	status, reason, _ = classifyQuota(1030, 1000)
	if status != StatusWarning || reason != "overcharged" {
		t.Fatalf("configured classifyQuota status=%q reason=%q, want warning overcharged", status, reason)
	}
}

func TestClassifyQuotaUsesConfigurableAbsoluteTolerance(t *testing.T) {
	t.Setenv("PRICE_INSPECTION_ABS_TOLERANCE_QUOTA", "20")
	status, reason, _ := classifyQuota(1015, 1000)
	if status != StatusNormal || reason != "ok" {
		t.Fatalf("classifyQuota status=%q reason=%q, want normal ok", status, reason)
	}
}
