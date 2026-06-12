package price_inspection

import (
	"testing"

	"github.com/QuantumNous/new-api/model"
	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
)

func TestTokenizeModelName(t *testing.T) {
	got := tokenizeModelName("Claude 4.5 Sonnet")
	want := []string{"claude", "4", "5", "sonnet"}
	if len(got) != len(want) {
		t.Fatalf("token count = %d, want %d: %#v", len(got), len(want), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("token[%d] = %q, want %q: %#v", i, got[i], want[i], got)
		}
	}
}

func TestModelSimilarityClaudeAlias(t *testing.T) {
	candidate := snapshotCandidate{
		ModelID:        "anthropic/claude-sonnet-4.5",
		LocalModelName: "claude-sonnet-4.5",
		Normalized:     normalizeModelName("anthropic/claude-sonnet-4.5 claude-sonnet-4.5"),
		Tokens:         tokenizeModelName("anthropic/claude-sonnet-4.5 claude-sonnet-4.5"),
	}
	score, _ := modelSimilarity(normalizeModelName("Claude 4.5 Sonnet"), tokenizeModelName("Claude 4.5 Sonnet"), candidate)
	if score < 0.72 {
		t.Fatalf("score = %f, want >= 0.72", score)
	}
}

func TestMappingFromRequestDefaults(t *testing.T) {
	enabled := true
	mapping, err := mappingFromRequest(MappingRequest{
		ChannelType:    14,
		LocalModelName: "Claude 4.5 Sonnet",
		SourceModelID:  "anthropic/claude-sonnet-4.5",
		Enabled:        &enabled,
	}, nil)
	if err != nil {
		t.Fatalf("mappingFromRequest returned error: %v", err)
	}
	if mapping.SourceProvider != ProviderOpenRouter {
		t.Fatalf("SourceProvider = %q, want %q", mapping.SourceProvider, ProviderOpenRouter)
	}
	if mapping.CanonicalModelID != "anthropic/claude-sonnet-4.5" {
		t.Fatalf("CanonicalModelID = %q", mapping.CanonicalModelID)
	}
	if mapping.Scenario != "text_token" {
		t.Fatalf("Scenario = %q, want text_token", mapping.Scenario)
	}
	if !mapping.Enabled {
		t.Fatal("mapping should be enabled")
	}
}

func TestSuggestMappingsUsesGenericSnapshots(t *testing.T) {
	previousDB := model.DB
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	model.DB = db
	t.Cleanup(func() {
		model.DB = previousDB
	})
	if err := model.DB.AutoMigrate(&model.PriceSourceSnapshot{}, &model.PriceInspectionCoverageReport{}); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}
	if err := model.InsertPriceSourceSnapshots([]model.PriceSourceSnapshot{
		{
			SourceProvider: "google",
			FetchedAt:      1700000000,
			ModelID:        "gemini-2.5-flash-image",
			LocalModelName: "Gemini 2.5 Flash Image",
			Scenario:       "image_generation",
			PricingScheme:  "per_image",
		},
	}); err != nil {
		t.Fatalf("InsertPriceSourceSnapshots: %v", err)
	}
	if err := model.InsertPriceInspectionCoverageReports([]model.PriceInspectionCoverageReport{
		{
			GeneratedAt:    1700000010,
			SourceProvider: "google",
			ChannelType:    24,
			ModelName:      "gemini-2.5-flash-image",
			Scenario:       "image_generation",
			ReasonCode:     "missing_model_mapping",
			SampleLogCount: 3,
		},
	}); err != nil {
		t.Fatalf("InsertPriceInspectionCoverageReports: %v", err)
	}

	rows, err := SuggestMappings(SuggestMappingsRequest{
		SourceProvider: "google",
		GeneratedAt:    1700000010,
		MinScore:       0.5,
	})
	if err != nil {
		t.Fatalf("SuggestMappings: %v", err)
	}
	if len(rows) != 1 {
		t.Fatalf("len(rows) = %d, want 1: %#v", len(rows), rows)
	}
	if rows[0].SuggestedSourceModelID != "gemini-2.5-flash-image" {
		t.Fatalf("suggestion = %#v", rows[0])
	}
}
