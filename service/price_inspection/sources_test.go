package price_inspection

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/QuantumNous/new-api/model"
	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
)

func TestFetchSourcePricesUnsupportedProvider(t *testing.T) {
	_, err := FetchSourcePrices(context.Background(), "unknown-provider")
	if !errors.Is(err, ErrPriceSourceUnsupported) {
		t.Fatalf("FetchSourcePrices error = %v, want ErrPriceSourceUnsupported", err)
	}
}

func TestListPriceSourcesCatalogProvidersImplemented(t *testing.T) {
	setupSnapshotTestDB(t)
	sources, err := ListPriceSources()
	if err != nil {
		t.Fatalf("ListPriceSources: %v", err)
	}
	implemented := map[string]bool{}
	for _, source := range sources {
		if source.FetchSupported && source.SnapshotSupported && source.Status == "implemented" {
			implemented[source.Provider] = true
		}
	}
	for _, provider := range []string{"openai", "anthropic", "google"} {
		if !implemented[provider] {
			t.Fatalf("%s was not implemented in sources: %#v", provider, sources)
		}
	}
	for _, source := range sources {
		if source.Provider == "azure" && source.DefaultScheduledProvider {
			t.Fatalf("azure should not be a default scheduled price source: %#v", source)
		}
		if source.Provider == "azure" {
			if source.FetchSupported {
				t.Fatalf("azure should not support automatic fetch: %#v", source)
			}
			if !source.SnapshotSupported {
				t.Fatalf("azure should support manual/generic snapshots: %#v", source)
			}
			if source.HealthStatus != "no_snapshot" {
				t.Fatalf("azure health = %q, want no_snapshot", source.HealthStatus)
			}
		}
	}
}

func TestListPriceSourcesReportsSnapshotHealth(t *testing.T) {
	setupSnapshotTestDB(t)
	now := time.Now().Unix()
	if err := model.InsertPriceSourceSnapshots([]model.PriceSourceSnapshot{
		{
			SourceProvider:      "openai",
			FetchedAt:           now - 2*3600,
			ModelID:             "gpt-5-mini",
			InputPricePerToken:  0.00000025,
			OutputPricePerToken: 0.000002,
			Manual:              false,
		},
		{
			SourceProvider:      "google",
			FetchedAt:           now - 72*3600,
			ModelID:             "gemini-2.5-pro",
			InputPricePerToken:  0.00000125,
			OutputPricePerToken: 0.00001,
			Manual:              false,
		},
	}); err != nil {
		t.Fatalf("InsertPriceSourceSnapshots: %v", err)
	}
	t.Setenv("PRICE_INSPECTION_PRICE_SOURCE_STALE_HOURS", "24")

	sources, err := ListPriceSources()
	if err != nil {
		t.Fatalf("ListPriceSources: %v", err)
	}
	byProvider := map[string]PriceSourceInfo{}
	for _, source := range sources {
		byProvider[source.Provider] = source
	}
	if byProvider["openai"].HealthStatus != "ok" || byProvider["openai"].SnapshotStale {
		t.Fatalf("openai health = %#v, want ok/non-stale", byProvider["openai"])
	}
	if byProvider["google"].HealthStatus != "stale" || !byProvider["google"].SnapshotStale {
		t.Fatalf("google health = %#v, want stale", byProvider["google"])
	}
	if byProvider["anthropic"].HealthStatus != "no_snapshot" {
		t.Fatalf("anthropic health = %#v, want no_snapshot", byProvider["anthropic"])
	}
	if byProvider["google"].SnapshotStaleAfterSeconds != 24*3600 {
		t.Fatalf("stale threshold = %d", byProvider["google"].SnapshotStaleAfterSeconds)
	}
}

func TestFetchCatalogSourcePricesGoogle(t *testing.T) {
	setupSnapshotTestDB(t)
	result, err := FetchSourcePrices(context.Background(), "google")
	if err != nil {
		t.Fatalf("FetchSourcePrices google: %v", err)
	}
	if result.Provider != "google" || result.Count == 0 || result.FetchedAt == 0 {
		t.Fatalf("result = %#v", result)
	}
	rows, total, err := GetPriceSnapshots(SnapshotQuery{SourceProvider: "google", Page: 1, PageSize: 20})
	if err != nil {
		t.Fatalf("GetPriceSnapshots: %v", err)
	}
	if total != int64(result.Count) || len(rows) == 0 {
		t.Fatalf("total=%d len=%d result=%#v", total, len(rows), result)
	}
	foundImage := false
	for _, row := range rows {
		if row.ModelID == "gemini-2.5-flash-image" && row.OutputImagePricePerToken > 0 {
			foundImage = true
		}
	}
	if !foundImage {
		t.Fatalf("google catalog did not include image generation snapshot: %#v", rows)
	}
}

func TestFetchCatalogSourcePricesExternalURL(t *testing.T) {
	setupSnapshotTestDB(t)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"catalog_version":"ops-2026-06-09","source_url":"https://prices.example.test/openai.json","snapshots":[{"model_id":"gpt-test-catalog","local_model_name":"gpt-test-catalog","input_price_per_token":0.000001,"output_price_per_token":0.000002}]}`))
	}))
	defer server.Close()
	t.Setenv("PRICE_INSPECTION_OPENAI_PRICE_CATALOG_URL", server.URL)
	t.Setenv("PRICE_INSPECTION_ANTHROPIC_PRICE_CATALOG_URL", "")
	t.Setenv("PRICE_INSPECTION_GOOGLE_PRICE_CATALOG_URL", "")

	result, err := FetchSourcePrices(context.Background(), "openai")
	if err != nil {
		t.Fatalf("FetchSourcePrices openai: %v", err)
	}
	if result.Count != 1 {
		t.Fatalf("result.Count = %d, want 1", result.Count)
	}
	rows, total, err := GetPriceSnapshots(SnapshotQuery{SourceProvider: "openai", Page: 1, PageSize: 10})
	if err != nil {
		t.Fatalf("GetPriceSnapshots: %v", err)
	}
	if total != 1 || rows[0].ModelID != "gpt-test-catalog" || rows[0].Manual {
		t.Fatalf("rows = %#v total=%d", rows, total)
	}
	var raw map[string]any
	if err := json.Unmarshal([]byte(rows[0].RawJSON), &raw); err != nil {
		t.Fatalf("RawJSON is not valid JSON: %v", err)
	}
	if raw["catalog_source_kind"] != "external_json_catalog" || raw["catalog_version"] != "ops-2026-06-09" {
		t.Fatalf("catalog metadata missing from RawJSON: %#v", raw)
	}
	if raw["catalog_source_url"] != "https://prices.example.test/openai.json" {
		t.Fatalf("catalog_source_url = %#v", raw["catalog_source_url"])
	}
}

func TestFetchCatalogSourcePricesRejectsInvalidExternalCatalog(t *testing.T) {
	cases := []struct {
		name string
		body string
	}{
		{
			name: "negative price",
			body: `{"snapshots":[{"model_id":"bad-price","input_price_per_token":-0.1}]}`,
		},
		{
			name: "no price",
			body: `{"snapshots":[{"model_id":"empty-price"}]}`,
		},
		{
			name: "video task",
			body: `{"snapshots":[{"model_id":"kling-v2-6","scenario":"video_task","request_price":0.1}]}`,
		},
		{
			name: "detected video task",
			body: `{"snapshots":[{"model_id":"kling-v2-6","request_price":0.1}]}`,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			setupSnapshotTestDB(t)
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				_, _ = w.Write([]byte(tc.body))
			}))
			defer server.Close()
			t.Setenv("PRICE_INSPECTION_OPENAI_PRICE_CATALOG_URL", server.URL)
			if _, err := FetchSourcePrices(context.Background(), "openai"); err == nil {
				t.Fatal("FetchSourcePrices should reject invalid external catalog")
			}
		})
	}
}

func TestScheduledPriceSourceProviders(t *testing.T) {
	defaults := scheduledPriceSourceProviders(nil)
	wantDefaults := []string{ProviderOpenRouter, "openai", "anthropic", "google"}
	if len(defaults) != len(wantDefaults) {
		t.Fatalf("defaults = %#v, want %#v", defaults, wantDefaults)
	}
	for i := range wantDefaults {
		if defaults[i] != wantDefaults[i] {
			t.Fatalf("defaults = %#v, want %#v", defaults, wantDefaults)
		}
	}

	got := scheduledPriceSourceProviders([]string{" OpenRouter ", "gemini", "google", "", "Claude", "anthropic"})
	want := []string{ProviderOpenRouter, "google", "anthropic"}
	if len(got) != len(want) {
		t.Fatalf("len = %d, want %d: %#v", len(got), len(want), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("providers[%d] = %q, want %q: %#v", i, got[i], want[i], got)
		}
	}
}

func TestCleanupAutomaticPriceSourceSnapshotsDisabledByDefault(t *testing.T) {
	setupSnapshotTestDB(t)
	if err := model.InsertPriceSourceSnapshots([]model.PriceSourceSnapshot{
		{
			SourceProvider:      "openai",
			FetchedAt:           100,
			ModelID:             "old-auto",
			InputPricePerToken:  0.000001,
			OutputPricePerToken: 0.000002,
			Manual:              false,
		},
	}); err != nil {
		t.Fatalf("InsertPriceSourceSnapshots: %v", err)
	}

	cleanupAutomaticPriceSourceSnapshots(0)

	rows, total, err := GetPriceSnapshots(SnapshotQuery{SourceProvider: "openai", Page: 1, PageSize: 10})
	if err != nil {
		t.Fatalf("GetPriceSnapshots: %v", err)
	}
	if total != 1 || len(rows) != 1 {
		t.Fatalf("total=%d len=%d, want 1", total, len(rows))
	}
}

func TestGetPriceSnapshotsGenericProvider(t *testing.T) {
	setupSnapshotTestDB(t)
	if err := model.InsertPriceSourceSnapshots([]model.PriceSourceSnapshot{
		{
			SourceProvider:      "anthropic",
			FetchedAt:           1700000000,
			ModelID:             "claude-sonnet-4.5",
			CanonicalModelID:    "claude-sonnet-4.5-20250929",
			LocalModelName:      "Claude 4.5 Sonnet",
			Scenario:            "text_token",
			PricingScheme:       "per_token",
			InputPricePerToken:  0.000000003,
			OutputPricePerToken: 0.000000015,
		},
	}); err != nil {
		t.Fatalf("InsertPriceSourceSnapshots: %v", err)
	}

	rows, total, err := GetPriceSnapshots(SnapshotQuery{SourceProvider: "claude", Page: 1, PageSize: 10})
	if err != nil {
		t.Fatalf("GetPriceSnapshots: %v", err)
	}
	if total != 1 || len(rows) != 1 {
		t.Fatalf("total=%d len=%d, want 1", total, len(rows))
	}
	if rows[0].SourceProvider != "anthropic" || rows[0].ModelID != "claude-sonnet-4.5" {
		t.Fatalf("row = %#v", rows[0])
	}
}

func TestCreateAndDeletePriceSnapshot(t *testing.T) {
	setupSnapshotTestDB(t)
	created, err := CreatePriceSnapshot(SnapshotMutationRequest{
		SourceProvider:            "gemini",
		ModelID:                   "gemini-2.5-flash-image",
		LocalModelName:            "Gemini Flash Image",
		ImagePrice:                0.000039,
		OutputPricePerToken:       0.00000003,
		CacheWrite5mPricePerToken: 0.00000005,
		CacheWrite1hPricePerToken: 0.00000008,
		InputImagePricePerToken:   0.00000011,
		OutputImagePricePerToken:  0.00000012,
		InputAudioPricePerToken:   0.00000013,
		OutputAudioPricePerToken:  0.00000014,
	})
	if err != nil {
		t.Fatalf("CreatePriceSnapshot: %v", err)
	}
	if created.SourceProvider != "google" {
		t.Fatalf("SourceProvider = %q, want google", created.SourceProvider)
	}
	if !created.Manual {
		t.Fatal("created snapshot should be manual")
	}
	if created.PricingScheme != "per_image" || created.Unit != "image" {
		t.Fatalf("pricing scheme/unit = %q/%q", created.PricingScheme, created.Unit)
	}
	if created.CacheWrite5mPricePerToken != 0.00000005 || created.CacheWrite1hPricePerToken != 0.00000008 {
		t.Fatalf("cache write tier prices were not saved: %#v", created)
	}
	if created.InputImagePricePerToken != 0.00000011 || created.OutputImagePricePerToken != 0.00000012 ||
		created.InputAudioPricePerToken != 0.00000013 || created.OutputAudioPricePerToken != 0.00000014 {
		t.Fatalf("media token prices were not saved: %#v", created)
	}

	rows, total, err := GetPriceSnapshots(SnapshotQuery{SourceProvider: "google", Page: 1, PageSize: 10})
	if err != nil {
		t.Fatalf("GetPriceSnapshots: %v", err)
	}
	if total != 1 || len(rows) != 1 {
		t.Fatalf("total=%d len=%d, want 1", total, len(rows))
	}
	if err := DeletePriceSnapshot(created.ID); err != nil {
		t.Fatalf("DeletePriceSnapshot: %v", err)
	}
	rows, total, err = GetPriceSnapshots(SnapshotQuery{SourceProvider: "google", Page: 1, PageSize: 10})
	if err != nil {
		t.Fatalf("GetPriceSnapshots after delete: %v", err)
	}
	if total != 0 || len(rows) != 0 {
		t.Fatalf("after delete total=%d len=%d, want 0", total, len(rows))
	}
}

func TestCreatePriceSnapshotRejectsInvalidManualSnapshot(t *testing.T) {
	cases := []struct {
		name string
		req  SnapshotMutationRequest
	}{
		{
			name: "negative price",
			req: SnapshotMutationRequest{
				SourceProvider:      "openai",
				ModelID:             "gpt-bad-price",
				InputPricePerToken:  -0.000001,
				OutputPricePerToken: 0.000002,
			},
		},
		{
			name: "no price",
			req: SnapshotMutationRequest{
				SourceProvider: "openai",
				ModelID:        "gpt-empty-price",
			},
		},
		{
			name: "video task",
			req: SnapshotMutationRequest{
				SourceProvider: "openai",
				ModelID:        "kling-v2-6",
				RequestPrice:   0.1,
			},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			setupSnapshotTestDB(t)
			if _, err := CreatePriceSnapshot(tc.req); err == nil {
				t.Fatal("CreatePriceSnapshot should reject invalid manual snapshot")
			}
			rows, total, err := GetPriceSnapshots(SnapshotQuery{SourceProvider: "openai", Page: 1, PageSize: 10})
			if err != nil {
				t.Fatalf("GetPriceSnapshots: %v", err)
			}
			if total != 0 || len(rows) != 0 {
				t.Fatalf("invalid snapshot should not be inserted, total=%d len=%d rows=%#v", total, len(rows), rows)
			}
		})
	}
}

func TestDeletePriceSnapshotRejectsAutomaticSnapshot(t *testing.T) {
	setupSnapshotTestDB(t)
	if err := model.InsertPriceSourceSnapshots([]model.PriceSourceSnapshot{
		{
			SourceProvider:      "openai",
			FetchedAt:           1700000000,
			ModelID:             "gpt-5-mini",
			InputPricePerToken:  0.00000025,
			OutputPricePerToken: 0.000002,
			Manual:              false,
		},
	}); err != nil {
		t.Fatalf("InsertPriceSourceSnapshots: %v", err)
	}
	rows, total, err := GetPriceSnapshots(SnapshotQuery{SourceProvider: "openai", Page: 1, PageSize: 10})
	if err != nil {
		t.Fatalf("GetPriceSnapshots: %v", err)
	}
	if total != 1 || len(rows) != 1 {
		t.Fatalf("total=%d len=%d, want 1", total, len(rows))
	}
	if err := DeletePriceSnapshot(rows[0].ID); err == nil {
		t.Fatal("DeletePriceSnapshot should reject automatic snapshots")
	}
	rows, total, err = GetPriceSnapshots(SnapshotQuery{SourceProvider: "openai", Page: 1, PageSize: 10})
	if err != nil {
		t.Fatalf("GetPriceSnapshots after delete attempt: %v", err)
	}
	if total != 1 || len(rows) != 1 {
		t.Fatalf("automatic snapshot should remain, total=%d len=%d", total, len(rows))
	}
}

func TestCreatePriceSnapshotsBatchRejectsInvalidSnapshot(t *testing.T) {
	setupSnapshotTestDB(t)
	_, err := CreatePriceSnapshots(SnapshotBatchRequest{
		SourceProvider: "openai",
		Snapshots: []SnapshotMutationRequest{
			{
				ModelID:             "gpt-5-mini",
				LocalModelName:      "gpt-5-mini",
				InputPricePerToken:  0.00000025,
				OutputPricePerToken: 0.000002,
			},
			{
				ModelID:      "kling-v2-6",
				RequestPrice: 0.1,
			},
		},
	})
	if err == nil {
		t.Fatal("CreatePriceSnapshots should reject invalid batch snapshot")
	}
	if !strings.Contains(err.Error(), "snapshot[1]") {
		t.Fatalf("batch error should include failing index, got %v", err)
	}
	rows, total, err := GetPriceSnapshots(SnapshotQuery{SourceProvider: "openai", Page: 1, PageSize: 10})
	if err != nil {
		t.Fatalf("GetPriceSnapshots: %v", err)
	}
	if total != 0 || len(rows) != 0 {
		t.Fatalf("batch should be all-or-nothing before insert, total=%d len=%d rows=%#v", total, len(rows), rows)
	}
}

func TestCreatePriceSnapshotsBatch(t *testing.T) {
	setupSnapshotTestDB(t)
	result, err := CreatePriceSnapshots(SnapshotBatchRequest{
		SourceProvider: "openai",
		Snapshots: []SnapshotMutationRequest{
			{
				ModelID:             "gpt-5-mini",
				LocalModelName:      "gpt-5-mini",
				InputPricePerToken:  0.00000025,
				OutputPricePerToken: 0.000002,
			},
			{
				SourceProvider: "claude",
				ModelID:        "claude-sonnet-4.5",
				LocalModelName: "Claude 4.5 Sonnet",
				RequestPrice:   0.001,
			},
		},
	})
	if err != nil {
		t.Fatalf("CreatePriceSnapshots: %v", err)
	}
	if result.Count != 2 || len(result.Snapshots) != 2 {
		t.Fatalf("result = %#v", result)
	}
	if result.Snapshots[0].SourceProvider != "openai" {
		t.Fatalf("first provider = %q", result.Snapshots[0].SourceProvider)
	}
	if result.Snapshots[1].SourceProvider != "anthropic" {
		t.Fatalf("second provider = %q", result.Snapshots[1].SourceProvider)
	}

	openAIRows, total, err := GetPriceSnapshots(SnapshotQuery{SourceProvider: "openai", Page: 1, PageSize: 10})
	if err != nil {
		t.Fatalf("GetPriceSnapshots openai: %v", err)
	}
	if total != 1 || len(openAIRows) != 1 {
		t.Fatalf("openai total=%d len=%d, want 1", total, len(openAIRows))
	}
	anthropicRows, total, err := GetPriceSnapshots(SnapshotQuery{SourceProvider: "anthropic", Page: 1, PageSize: 10})
	if err != nil {
		t.Fatalf("GetPriceSnapshots anthropic: %v", err)
	}
	if total != 1 || len(anthropicRows) != 1 {
		t.Fatalf("anthropic total=%d len=%d, want 1", total, len(anthropicRows))
	}
}

func TestSyncOpenRouterSnapshotsToGeneric(t *testing.T) {
	setupSnapshotTestDB(t)
	if err := model.InsertOpenRouterPriceSnapshots([]model.OpenRouterPriceSnapshot{
		{
			FetchedAt:               1700000000,
			ModelID:                 "openai/gpt-5-mini",
			CanonicalSlug:           "openai/gpt-5-mini",
			LocalModelName:          "gpt-5-mini",
			PromptPricePerToken:     0.00000025,
			CompletionPricePerToken: 0.000002,
			CacheReadPricePerToken:  0.000000025,
			CacheWritePricePerToken: 0.0000003,
			RequestPrice:            0.00001,
			RawJSON:                 `{"id":"openai/gpt-5-mini"}`,
		},
	}); err != nil {
		t.Fatalf("InsertOpenRouterPriceSnapshots: %v", err)
	}

	if err := syncOpenRouterSnapshotsToGeneric(1700000000); err != nil {
		t.Fatalf("syncOpenRouterSnapshotsToGeneric: %v", err)
	}
	if err := syncOpenRouterSnapshotsToGeneric(1700000000); err != nil {
		t.Fatalf("syncOpenRouterSnapshotsToGeneric second run: %v", err)
	}

	rows, total, err := GetPriceSnapshots(SnapshotQuery{SourceProvider: ProviderOpenRouter, Page: 1, PageSize: 10})
	if err != nil {
		t.Fatalf("GetPriceSnapshots: %v", err)
	}
	if total != 1 || len(rows) != 1 {
		t.Fatalf("total=%d len=%d, want 1", total, len(rows))
	}
	got := rows[0]
	if got.SourceProvider != ProviderOpenRouter || got.ModelID != "openai/gpt-5-mini" {
		t.Fatalf("synced snapshot = %#v", got)
	}
	if got.ID == 0 {
		t.Fatal("synced snapshot should have a generic table ID")
	}
	if got.InputPricePerToken != 0.00000025 || got.OutputPricePerToken != 0.000002 || got.RequestPrice != 0.00001 {
		t.Fatalf("prices were not converted: %#v", got)
	}
	if got.Manual {
		t.Fatal("synced snapshot should not be manual")
	}
}

func setupSnapshotTestDB(t *testing.T) {
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
	if err := model.DB.AutoMigrate(&model.PriceSourceSnapshot{}, &model.OpenRouterPriceSnapshot{}); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}
}
