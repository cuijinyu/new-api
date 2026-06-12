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

func TestDetectScenario(t *testing.T) {
	cases := []struct {
		name        string
		channelType int
		modelName   string
		want        string
	}{
		{name: "text", channelType: constant.ChannelTypeOpenAI, modelName: "gpt-5.4-mini", want: "text_token"},
		{name: "gemini image", channelType: constant.ChannelTypeGemini, modelName: "gemini-2.5-flash-image", want: "image_generation"},
		{name: "openai image", channelType: constant.ChannelTypeOpenAI, modelName: "gpt-image-2", want: "image_generation"},
		{name: "embedding", channelType: constant.ChannelTypeGemini, modelName: "text-embedding-004", want: "embedding"},
		{name: "video channel", channelType: constant.ChannelTypeKling, modelName: "kling-v2-6", want: "video_task"},
		{name: "video name", channelType: constant.ChannelTypeOpenAI, modelName: "sora-2", want: "video_task"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := detectScenario(tc.channelType, tc.modelName); got != tc.want {
				t.Fatalf("detectScenario(%d, %q) = %q, want %q", tc.channelType, tc.modelName, got, tc.want)
			}
		})
	}
}

func TestNormalizeModelName(t *testing.T) {
	got := normalizeModelName("Gemini 3.1-Pro_Preview")
	want := "gemini31propreview"
	if got != want {
		t.Fatalf("normalizeModelName = %q, want %q", got, want)
	}
}

func TestSplitModels(t *testing.T) {
	got := splitModels("gpt-5,, gpt-5, gemini-2.5-pro,")
	if len(got) != 2 {
		t.Fatalf("len(splitModels) = %d, want 2: %#v", len(got), got)
	}
	if got[0] != "gpt-5" || got[1] != "gemini-2.5-pro" {
		t.Fatalf("splitModels = %#v", got)
	}
}

func TestFirstPhaseSupportedScenarios(t *testing.T) {
	if !isScenarioSupportedForFirstPhase("text_token") {
		t.Fatal("text_token should be supported in first phase")
	}
	for _, scenario := range []string{"image_generation", "video_task", "embedding"} {
		if isScenarioSupportedForFirstPhase(scenario) {
			t.Fatalf("%s should not be supported in first phase", scenario)
		}
	}
}

func TestRuntimeCalculatorSupportedScenarios(t *testing.T) {
	for _, scenario := range []string{"text_token", "vision_input", "image_generation", "tool_call", "audio"} {
		if !isScenarioSupportedByRuntimeCalculator(scenario) {
			t.Fatalf("%s should be supported by runtime calculator", scenario)
		}
	}
	for _, scenario := range []string{"embedding", "rerank", "video_task", "audio_task"} {
		if isScenarioSupportedByRuntimeCalculator(scenario) {
			t.Fatalf("%s should not be supported by runtime calculator", scenario)
		}
	}
}

func TestOutOfScopeScenarios(t *testing.T) {
	if !isScenarioOutOfScope("video_task") {
		t.Fatal("video_task should be out of scope")
	}
	if isScenarioOutOfScope("image_generation") {
		t.Fatal("image_generation should remain in future support scope")
	}
}

func TestBuildCoverageRowVideoTaskOutOfScope(t *testing.T) {
	row := buildCoverageRow(
		123,
		ProviderOpenRouter,
		channelModelAggregate{ChannelType: constant.ChannelTypeKling, ModelName: "kling-v2-6", ChannelIDs: []int{1}},
		snapshotIndex{},
		logAggregate{Count: 10, LastSeenAt: 100},
	)
	if row.SupportLevel != SupportOutOfScope {
		t.Fatalf("SupportLevel = %q, want %q", row.SupportLevel, SupportOutOfScope)
	}
	if row.MappingStatus != MappingNotRequired {
		t.Fatalf("MappingStatus = %q, want %q", row.MappingStatus, MappingNotRequired)
	}
	if row.CalculatorStatus != CalculatorOutOfScope {
		t.Fatalf("CalculatorStatus = %q, want %q", row.CalculatorStatus, CalculatorOutOfScope)
	}
	if row.ReasonCode != "out_of_scope_video_task" {
		t.Fatalf("ReasonCode = %q", row.ReasonCode)
	}
}

func TestBuildCoverageRowNonOpenRouterWithBillingContext(t *testing.T) {
	row := buildCoverageRow(
		123,
		"google",
		channelModelAggregate{ChannelType: constant.ChannelTypeGemini, ModelName: "gemini-2.5-flash-image", ChannelIDs: []int{24}},
		snapshotIndex{},
		logAggregate{Count: 10, BillingContextCount: 8, LastSeenAt: 100},
	)
	if row.MappingStatus != MappingDirectLocal {
		t.Fatalf("MappingStatus = %q, want %q", row.MappingStatus, MappingDirectLocal)
	}
	if row.CalculatorStatus != CalculatorSupported {
		t.Fatalf("CalculatorStatus = %q, want %q", row.CalculatorStatus, CalculatorSupported)
	}
	if row.SupportLevel != SupportStandard {
		t.Fatalf("SupportLevel = %q, want %q", row.SupportLevel, SupportStandard)
	}
	if row.ReasonCode != "billing_context_available" {
		t.Fatalf("ReasonCode = %q", row.ReasonCode)
	}
	if row.SourceModelID != "gemini-2.5-flash-image" {
		t.Fatalf("SourceModelID = %q", row.SourceModelID)
	}
}

func TestBuildCoverageRowUsesGenericSnapshotForNonOpenRouter(t *testing.T) {
	idx := snapshotIndex{
		byModelID:        map[string]model.PriceSourceSnapshot{},
		byLocalModelName: map[string]model.PriceSourceSnapshot{},
		byNormalizedName: map[string]model.PriceSourceSnapshot{},
	}
	indexPriceSourceSnapshot(idx, model.PriceSourceSnapshot{
		SourceProvider:   "google",
		ModelID:          "gemini-2.5-flash-image-preview",
		CanonicalModelID: "gemini-2.5-flash-image",
		LocalModelName:   "Gemini Flash Image",
		Scenario:         "image_generation",
	})
	row := buildCoverageRow(
		123,
		"google",
		channelModelAggregate{ChannelType: constant.ChannelTypeGemini, ModelName: "Gemini Flash Image", ChannelIDs: []int{24}},
		idx,
		logAggregate{Count: 1, ProviderCostCount: 1, LastSeenAt: 100},
	)
	if row.SourceModelID != "gemini-2.5-flash-image-preview" {
		t.Fatalf("SourceModelID = %q", row.SourceModelID)
	}
	if row.CanonicalModelID != "gemini-2.5-flash-image" {
		t.Fatalf("CanonicalModelID = %q", row.CanonicalModelID)
	}
	if row.MappingStatus != MappingDirectLocal {
		t.Fatalf("MappingStatus = %q", row.MappingStatus)
	}
}

func TestBuildCoverageRowNonOpenRouterMissingBillingContext(t *testing.T) {
	row := buildCoverageRow(
		123,
		"openai",
		channelModelAggregate{ChannelType: constant.ChannelTypeOpenAI, ModelName: "gpt-5", ChannelIDs: []int{1}},
		snapshotIndex{},
		logAggregate{Count: 5, LastSeenAt: 100},
	)
	if row.CalculatorStatus != CalculatorSupported {
		t.Fatalf("CalculatorStatus = %q, want %q", row.CalculatorStatus, CalculatorSupported)
	}
	if row.SupportLevel != SupportUnsupported {
		t.Fatalf("SupportLevel = %q, want %q", row.SupportLevel, SupportUnsupported)
	}
	if row.ReasonCode != "missing_billing_context" {
		t.Fatalf("ReasonCode = %q", row.ReasonCode)
	}
}

func TestBuildCoverageRowSnapshotAvailableWithoutBillingContext(t *testing.T) {
	idx := snapshotIndex{
		byModelID:        map[string]model.PriceSourceSnapshot{},
		byLocalModelName: map[string]model.PriceSourceSnapshot{},
		byNormalizedName: map[string]model.PriceSourceSnapshot{},
	}
	indexPriceSourceSnapshot(idx, model.PriceSourceSnapshot{
		ID:             17,
		SourceProvider: "openai",
		ModelID:        "gpt-5",
		LocalModelName: "gpt-5",
		Scenario:       "text_token",
		PricingScheme:  "per_token",
	})
	row := buildCoverageRow(
		123,
		"openai",
		channelModelAggregate{ChannelType: constant.ChannelTypeOpenAI, ModelName: "gpt-5", ChannelIDs: []int{1}},
		idx,
		logAggregate{Count: 5, LastSeenAt: 100},
	)
	if row.SupportLevel != SupportStandard {
		t.Fatalf("SupportLevel = %q, want %q", row.SupportLevel, SupportStandard)
	}
	if row.ReasonCode != "price_snapshot_available" {
		t.Fatalf("ReasonCode = %q", row.ReasonCode)
	}
	if !strings.Contains(row.RawJSON, `"price_snapshot":true`) {
		t.Fatalf("RawJSON should include price_snapshot=true: %s", row.RawJSON)
	}
}

func TestBuildCoverageRowSnapshotAvailableWithoutRecentLogs(t *testing.T) {
	idx := snapshotIndex{
		byModelID:        map[string]model.PriceSourceSnapshot{},
		byLocalModelName: map[string]model.PriceSourceSnapshot{},
		byNormalizedName: map[string]model.PriceSourceSnapshot{},
	}
	indexPriceSourceSnapshot(idx, model.PriceSourceSnapshot{
		ID:             18,
		SourceProvider: "anthropic",
		ModelID:        "claude-sonnet-4",
		LocalModelName: "claude-sonnet-4",
		Scenario:       "text_token",
		PricingScheme:  "per_token",
	})
	row := buildCoverageRow(
		123,
		"anthropic",
		channelModelAggregate{ChannelType: constant.ChannelTypeAnthropic, ModelName: "claude-sonnet-4", ChannelIDs: []int{3}},
		idx,
		logAggregate{},
	)
	if row.SupportLevel != SupportEstimated {
		t.Fatalf("SupportLevel = %q, want %q", row.SupportLevel, SupportEstimated)
	}
	if row.ReasonCode != "price_snapshot_available_no_recent_logs" {
		t.Fatalf("ReasonCode = %q", row.ReasonCode)
	}
}

func TestLoadLogAggregatesCountsOpenRouterCostAsProviderCost(t *testing.T) {
	setupCoverageLogDB(t)
	now := time.Now().Unix()
	if err := model.LOG_DB.Create(&model.Log{
		CreatedAt:    now,
		Type:         model.LogTypeConsume,
		ChannelId:    9,
		ModelName:    "gpt-5",
		Quota:        20,
		Other:        `{"openrouter_cost":0.0002}`,
		RequestId:    "req-openrouter-cost",
		PromptTokens: 10,
	}).Error; err != nil {
		t.Fatalf("create log: %v", err)
	}

	stats := loadLogAggregates([]channelModelAggregate{
		{ChannelType: constant.ChannelTypeOpenRouter, ModelName: "gpt-5", ChannelIDs: []int{9}},
	}, 1)
	row := stats[coverageKey(constant.ChannelTypeOpenRouter, "gpt-5")]
	if row.Count != 1 {
		t.Fatalf("Count = %d, want 1", row.Count)
	}
	if row.ProviderCostCount != 1 {
		t.Fatalf("ProviderCostCount = %d, want 1", row.ProviderCostCount)
	}
	if row.BillingContextCount != 0 {
		t.Fatalf("BillingContextCount = %d, want 0", row.BillingContextCount)
	}
}

func TestLoadChannelModelAggregatesFiltersByProviderChannelTypes(t *testing.T) {
	setupCoverageChannelDB(t)
	channels := []model.Channel{
		{Id: 1, Type: constant.ChannelTypeOpenAI, Models: "gpt-5"},
		{Id: 2, Type: constant.ChannelTypeOpenAIMax, Models: "gpt-5-mini"},
		{Id: 3, Type: constant.ChannelTypeAnthropic, Models: "claude-sonnet-4.5"},
		{Id: 4, Type: constant.ChannelTypeGemini, Models: "gemini-2.5-pro"},
	}
	if err := model.DB.Create(&channels).Error; err != nil {
		t.Fatalf("create channels: %v", err)
	}

	rows, err := loadChannelModelAggregates(GenerateCoverageRequest{SourceProvider: "openai"})
	if err != nil {
		t.Fatalf("load openai aggregates: %v", err)
	}
	if len(rows) != 2 {
		t.Fatalf("len(openai rows) = %d, want 2: %#v", len(rows), rows)
	}
	for _, row := range rows {
		if row.ChannelType != constant.ChannelTypeOpenAI && row.ChannelType != constant.ChannelTypeOpenAIMax {
			t.Fatalf("openai coverage included unrelated channel type %d: %#v", row.ChannelType, rows)
		}
	}

	rows, err = loadChannelModelAggregates(GenerateCoverageRequest{SourceProvider: "openai", ChannelType: constant.ChannelTypeGemini})
	if err != nil {
		t.Fatalf("load explicit channel aggregates: %v", err)
	}
	if len(rows) != 1 || rows[0].ChannelType != constant.ChannelTypeGemini || rows[0].ModelName != "gemini-2.5-pro" {
		t.Fatalf("explicit channel_type should override provider defaults: %#v", rows)
	}
}

func setupCoverageLogDB(t *testing.T) {
	t.Helper()
	previousLogDB := model.LOG_DB
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	model.LOG_DB = db
	t.Cleanup(func() {
		model.LOG_DB = previousLogDB
	})
	if err := model.LOG_DB.AutoMigrate(&model.Log{}); err != nil {
		t.Fatalf("AutoMigrate log: %v", err)
	}
}

func setupCoverageChannelDB(t *testing.T) {
	t.Helper()
	previousDB := model.DB
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	model.DB = db
	t.Cleanup(func() {
		model.DB = previousDB
	})
	if err := model.DB.AutoMigrate(&model.Channel{}); err != nil {
		t.Fatalf("AutoMigrate channel: %v", err)
	}
}
