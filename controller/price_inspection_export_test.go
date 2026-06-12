package controller

import (
	"encoding/csv"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/QuantumNous/new-api/model"

	"github.com/gin-gonic/gin"
)

func TestWritePriceInspectionItemsCSVIncludesTraceFields(t *testing.T) {
	gin.SetMode(gin.TestMode)
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	writePriceInspectionItemsCSV(c, []model.PriceInspectionItem{
		{
			LogID:               1001,
			RunID:               7,
			LogCreatedAt:        1700000000,
			SourceProvider:      "anthropic",
			ChannelID:           24,
			ChannelType:         33,
			ModelName:           "claude-sonnet-4.5",
			SourceModelID:       "claude-sonnet-4.5",
			CanonicalModelID:    "claude-sonnet-4.5",
			Scenario:            "text_token",
			SupportLevel:        "standard",
			Status:              "abnormal",
			ReasonCode:          "overcharged",
			ReasonDetail:        "actual quota is higher than expected provider price",
			ActualQuota:         1200,
			ExpectedQuota:       1000,
			DeltaQuota:          200,
			DiffRate:            0.2,
			ActualUSD:           0.12,
			ExpectedUSD:         0.1,
			PriceSnapshotID:     42,
			BillingContextJSON:  `{"provider_usage_cost":0.1}`,
			CalculatorTraceJSON: `{"calculator":"price_source_snapshot","snapshot_id":42}`,
		},
	})

	if contentType := w.Header().Get("Content-Type"); !strings.Contains(contentType, "text/csv") {
		t.Fatalf("Content-Type = %q, want text/csv", contentType)
	}
	body := w.Body.String()
	if !strings.HasPrefix(body, "\ufeff") {
		t.Fatal("CSV output missing UTF-8 BOM")
	}

	reader := csv.NewReader(strings.NewReader(strings.TrimPrefix(body, "\ufeff")))
	records, err := reader.ReadAll()
	if err != nil {
		t.Fatalf("read csv: %v\n%s", err, body)
	}
	if len(records) != 2 {
		t.Fatalf("records length = %d, want 2: %#v", len(records), records)
	}

	headerIndex := map[string]int{}
	for i, name := range records[0] {
		headerIndex[name] = i
	}
	for _, column := range []string{"price_snapshot_id", "reason_detail", "billing_context_json", "calculator_trace_json"} {
		if _, ok := headerIndex[column]; !ok {
			t.Fatalf("CSV header missing %q: %#v", column, records[0])
		}
	}

	row := records[1]
	assertColumn := func(column, want string) {
		t.Helper()
		got := row[headerIndex[column]]
		if got != want {
			t.Fatalf("%s = %q, want %q", column, got, want)
		}
	}
	assertColumn("price_snapshot_id", "42")
	assertColumn("reason_detail", "actual quota is higher than expected provider price")
	assertColumn("billing_context_json", `{"provider_usage_cost":0.1}`)
	assertColumn("calculator_trace_json", `{"calculator":"price_source_snapshot","snapshot_id":42}`)
}

func TestWritePriceInspectionIssuesCSV(t *testing.T) {
	gin.SetMode(gin.TestMode)
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	writePriceInspectionIssuesCSV(c, []model.PriceInspectionIssueGroup{
		{
			SourceProvider:      "google",
			ModelName:           "gemini-2.5-pro",
			ChannelID:           24,
			ChannelType:         8,
			Status:              "critical",
			SupportLevel:        "standard",
			ReasonCode:          "overcharged",
			ResolutionStatus:    "acknowledged",
			ResolutionOwner:     "ops",
			ResolutionUpdatedBy: "admin",
			Count:               2,
			SampleLogID:         1001,
			LatestLogAt:         1700000000,
			TotalActualQuota:    1200,
			TotalExpectedQuota:  1000,
			TotalDeltaQuota:     200,
			MaxAbsDeltaQuota:    120,
			MaxDiffRate:         0.1,
		},
	})

	if contentType := w.Header().Get("Content-Type"); !strings.Contains(contentType, "text/csv") {
		t.Fatalf("Content-Type = %q, want text/csv", contentType)
	}
	body := w.Body.String()
	if !strings.HasPrefix(body, "\ufeff") {
		t.Fatal("CSV output missing UTF-8 BOM")
	}
	for _, want := range []string{"resolution_status", "gemini-2.5-pro", "acknowledged", "overcharged"} {
		if !strings.Contains(body, want) {
			t.Fatalf("CSV body missing %q: %s", want, body)
		}
	}
}

func TestWritePriceInspectionCoverageCSV(t *testing.T) {
	gin.SetMode(gin.TestMode)
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	writePriceInspectionCoverageCSV(c, []model.PriceInspectionCoverageReport{
		{
			GeneratedAt:      1700000000,
			SourceProvider:   "google",
			ChannelType:      24,
			ChannelTypeName:  "Gemini",
			ModelName:        "gemini-2.5-flash-image",
			Scenario:         "image_generation",
			MappingStatus:    "direct_local_model",
			CalculatorStatus: "supported",
			LogContextStatus: "available",
			SupportLevel:     "standard",
			ReasonCode:       "price_snapshot_available",
			SourceModelID:    "gemini-2.5-flash-image",
			ChannelCount:     2,
			SampleLogCount:   3,
			LastSeenAt:       1700000100,
			Suggestion:       "ok",
			RawJSON:          `{"price_snapshot":true}`,
		},
	})

	if contentType := w.Header().Get("Content-Type"); !strings.Contains(contentType, "text/csv") {
		t.Fatalf("Content-Type = %q, want text/csv", contentType)
	}
	body := w.Body.String()
	if !strings.HasPrefix(body, "\ufeff") {
		t.Fatal("CSV output missing UTF-8 BOM")
	}
	for _, want := range []string{"source_provider", "gemini-2.5-flash-image", "price_snapshot_available", "image_generation"} {
		if !strings.Contains(body, want) {
			t.Fatalf("CSV body missing %q: %s", want, body)
		}
	}
}
