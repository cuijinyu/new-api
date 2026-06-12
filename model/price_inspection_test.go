package model

import (
	"testing"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
)

func TestNormalizePriceInspectionResolutionStatus(t *testing.T) {
	cases := map[string]string{
		"":             "open",
		"open":         "open",
		"ACK":          "acknowledged",
		"acknowledged": "acknowledged",
		"ignore":       "ignored",
		"ignored":      "ignored",
		"done":         "resolved",
		"resolved":     "resolved",
		"bad":          "",
	}
	for input, want := range cases {
		if got := NormalizePriceInspectionResolutionStatus(input); got != want {
			t.Fatalf("NormalizePriceInspectionResolutionStatus(%q) = %q, want %q", input, got, want)
		}
	}
}

func TestFindPriceSourceSnapshotFallsBackToManualLatestAfterLog(t *testing.T) {
	previousDB := DB
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	DB = db
	t.Cleanup(func() {
		DB = previousDB
	})
	if err := DB.AutoMigrate(&PriceSourceSnapshot{}); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}
	if err := InsertPriceSourceSnapshots([]PriceSourceSnapshot{
		{
			SourceProvider:     "openai",
			FetchedAt:          200,
			ModelID:            "gpt-5-mini",
			CanonicalModelID:   "gpt-5-mini",
			LocalModelName:     "gpt-5-mini",
			InputPricePerToken: 0.00000025,
			Manual:             true,
		},
	}); err != nil {
		t.Fatalf("InsertPriceSourceSnapshots: %v", err)
	}

	snapshot, matchType, err := FindPriceSourceSnapshot("openai", "gpt-5-mini", "", 100)
	if err != nil {
		t.Fatalf("FindPriceSourceSnapshot: %v", err)
	}
	if snapshot.ModelID != "gpt-5-mini" {
		t.Fatalf("snapshot = %#v", snapshot)
	}
	if matchType != "model_manual_latest_after_log" {
		t.Fatalf("matchType = %q", matchType)
	}
}

func TestFindPriceSourceSnapshotDoesNotFallbackToAutomaticAfterLog(t *testing.T) {
	previousDB := DB
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	DB = db
	t.Cleanup(func() {
		DB = previousDB
	})
	if err := DB.AutoMigrate(&PriceSourceSnapshot{}); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}
	if err := InsertPriceSourceSnapshots([]PriceSourceSnapshot{
		{
			SourceProvider:     "openrouter",
			FetchedAt:          200,
			ModelID:            "openai/gpt-5-mini",
			CanonicalModelID:   "openai/gpt-5-mini",
			LocalModelName:     "gpt-5-mini",
			InputPricePerToken: 0.00000025,
			Manual:             false,
		},
	}); err != nil {
		t.Fatalf("InsertPriceSourceSnapshots: %v", err)
	}

	if _, _, err := FindPriceSourceSnapshot("openrouter", "openai/gpt-5-mini", "gpt-5-mini", 100); err != gorm.ErrRecordNotFound {
		t.Fatalf("FindPriceSourceSnapshot err = %v, want record not found", err)
	}
}

func TestDeleteAutomaticPriceSourceSnapshotsBeforePreservesManual(t *testing.T) {
	previousDB := DB
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	DB = db
	t.Cleanup(func() {
		DB = previousDB
	})
	if err := DB.AutoMigrate(&PriceSourceSnapshot{}); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}
	if err := InsertPriceSourceSnapshots([]PriceSourceSnapshot{
		{SourceProvider: "openai", FetchedAt: 100, ModelID: "old-auto", InputPricePerToken: 1, Manual: false},
		{SourceProvider: "openai", FetchedAt: 100, ModelID: "old-manual", InputPricePerToken: 1, Manual: true},
		{SourceProvider: "openai", FetchedAt: 300, ModelID: "new-auto", InputPricePerToken: 1, Manual: false},
		{SourceProvider: "google", FetchedAt: 100, ModelID: "old-google-auto", InputPricePerToken: 1, Manual: false},
	}); err != nil {
		t.Fatalf("InsertPriceSourceSnapshots: %v", err)
	}

	deleted, err := DeleteAutomaticPriceSourceSnapshotsBefore("openai", 200)
	if err != nil {
		t.Fatalf("DeleteAutomaticPriceSourceSnapshotsBefore: %v", err)
	}
	if deleted != 1 {
		t.Fatalf("deleted = %d, want 1", deleted)
	}

	var rows []PriceSourceSnapshot
	if err := DB.Order("model_id ASC").Find(&rows).Error; err != nil {
		t.Fatalf("Find snapshots: %v", err)
	}
	got := map[string]bool{}
	for _, row := range rows {
		got[row.ModelID] = true
	}
	for _, want := range []string{"old-manual", "new-auto", "old-google-auto"} {
		if !got[want] {
			t.Fatalf("snapshot %q should remain, got %#v", want, got)
		}
	}
	if got["old-auto"] {
		t.Fatalf("old-auto should have been deleted, got %#v", got)
	}
}

func TestAttachPriceInspectionIssueResolutions(t *testing.T) {
	previousDB := DB
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	DB = db
	t.Cleanup(func() {
		DB = previousDB
	})
	if err := DB.AutoMigrate(&PriceInspectionIssueResolution{}); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}

	resolution := &PriceInspectionIssueResolution{
		SourceProvider:   "google",
		ModelName:        "gemini-2.5-pro",
		ChannelID:        24,
		ChannelType:      8,
		Status:           "critical",
		SupportLevel:     "standard",
		ReasonCode:       "overcharged",
		ResolutionStatus: "ack",
		Note:             "known issue",
		UpdatedBy:        "admin",
	}
	if err := UpsertPriceInspectionIssueResolution(resolution); err != nil {
		t.Fatalf("UpsertPriceInspectionIssueResolution: %v", err)
	}

	rows := []PriceInspectionIssueGroup{
		{
			SourceProvider: "google",
			ModelName:      "gemini-2.5-pro",
			ChannelID:      24,
			ChannelType:    8,
			Status:         "critical",
			SupportLevel:   "standard",
			ReasonCode:     "overcharged",
		},
		{
			SourceProvider: "openai",
			ModelName:      "gpt-5",
			ChannelID:      1,
			ChannelType:    1,
			Status:         "missing",
			SupportLevel:   "unsupported",
			ReasonCode:     "missing_billing_context",
		},
	}
	if err := attachPriceInspectionIssueResolutions(rows); err != nil {
		t.Fatalf("attachPriceInspectionIssueResolutions: %v", err)
	}
	if rows[0].ResolutionStatus != "acknowledged" || rows[0].ResolutionNote != "known issue" {
		t.Fatalf("first row resolution not attached: %#v", rows[0])
	}
	if rows[1].ResolutionStatus != "open" {
		t.Fatalf("second row default resolution = %q, want open", rows[1].ResolutionStatus)
	}
}

func TestGetPriceInspectionIssueGroupsResolutionFilter(t *testing.T) {
	previousDB := DB
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	DB = db
	t.Cleanup(func() {
		DB = previousDB
	})
	if err := DB.AutoMigrate(&PriceInspectionItem{}, &PriceInspectionIssueResolution{}); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}

	items := []PriceInspectionItem{
		{
			RunID:          1,
			LogID:          101,
			LogCreatedAt:   1700000000,
			ChannelID:      24,
			ChannelType:    8,
			SourceProvider: "google",
			ModelName:      "gemini-2.5-pro",
			ActualQuota:    130,
			ExpectedQuota:  100,
			DeltaQuota:     30,
			DiffRate:       0.3,
			Status:         "critical",
			SupportLevel:   "standard",
			ReasonCode:     "overcharged",
		},
		{
			RunID:          1,
			LogID:          102,
			LogCreatedAt:   1700000100,
			ChannelID:      1,
			ChannelType:    1,
			SourceProvider: "openai",
			ModelName:      "gpt-5",
			ActualQuota:    10,
			ExpectedQuota:  0,
			DeltaQuota:     10,
			DiffRate:       1,
			Status:         "missing",
			SupportLevel:   "unsupported",
			ReasonCode:     "missing_billing_context",
		},
	}
	if err := DB.Create(&items).Error; err != nil {
		t.Fatalf("create items: %v", err)
	}
	if err := UpsertPriceInspectionIssueResolution(&PriceInspectionIssueResolution{
		SourceProvider:   "google",
		ModelName:        "gemini-2.5-pro",
		ChannelID:        24,
		ChannelType:      8,
		Status:           "critical",
		SupportLevel:     "standard",
		ReasonCode:       "overcharged",
		ResolutionStatus: "ignored",
		Note:             "known unsupported provider quirk",
	}); err != nil {
		t.Fatalf("UpsertPriceInspectionIssueResolution: %v", err)
	}

	activeRows, activeTotal, err := GetPriceInspectionIssueGroups("", "", "", "", "", "active", 0, 0, 0, 0, 0, 1, 20)
	if err != nil {
		t.Fatalf("GetPriceInspectionIssueGroups active: %v", err)
	}
	if activeTotal != 1 || len(activeRows) != 1 {
		t.Fatalf("active rows total=%d len=%d, want 1", activeTotal, len(activeRows))
	}
	if activeRows[0].SourceProvider != "openai" || activeRows[0].ResolutionStatus != "open" {
		t.Fatalf("active row = %#v, want openai open row", activeRows[0])
	}

	ignoredRows, ignoredTotal, err := GetPriceInspectionIssueGroups("", "", "", "", "", "ignored", 0, 0, 0, 0, 0, 1, 20)
	if err != nil {
		t.Fatalf("GetPriceInspectionIssueGroups ignored: %v", err)
	}
	if ignoredTotal != 1 || len(ignoredRows) != 1 {
		t.Fatalf("ignored rows total=%d len=%d, want 1", ignoredTotal, len(ignoredRows))
	}
	if ignoredRows[0].SourceProvider != "google" || ignoredRows[0].ResolutionStatus != "ignored" {
		t.Fatalf("ignored row = %#v, want google ignored row", ignoredRows[0])
	}
}

func TestGetPriceInspectionIssueGroupsOrdersBySeverityAndQuotaImpact(t *testing.T) {
	previousDB := DB
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	DB = db
	t.Cleanup(func() {
		DB = previousDB
	})
	if err := DB.AutoMigrate(&PriceInspectionItem{}, &PriceInspectionIssueResolution{}); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}

	items := []PriceInspectionItem{
		{
			RunID:          1,
			LogID:          201,
			LogCreatedAt:   1700000000,
			ChannelID:      1,
			ChannelType:    1,
			SourceProvider: "openai",
			ModelName:      "tiny-ratio",
			ActualQuota:    2,
			ExpectedQuota:  1,
			DeltaQuota:     1,
			DiffRate:       0.5,
			Status:         "warning",
			SupportLevel:   "standard",
			ReasonCode:     "overcharged",
		},
		{
			RunID:          1,
			LogID:          202,
			LogCreatedAt:   1700000100,
			ChannelID:      2,
			ChannelType:    1,
			SourceProvider: "openai",
			ModelName:      "large-critical",
			ActualQuota:    1200,
			ExpectedQuota:  1000,
			DeltaQuota:     200,
			DiffRate:       0.1667,
			Status:         "critical",
			SupportLevel:   "standard",
			ReasonCode:     "overcharged",
		},
		{
			RunID:          1,
			LogID:          203,
			LogCreatedAt:   1700000200,
			ChannelID:      3,
			ChannelType:    1,
			SourceProvider: "openai",
			ModelName:      "larger-abnormal",
			ActualQuota:    1100,
			ExpectedQuota:  1000,
			DeltaQuota:     100,
			DiffRate:       0.0909,
			Status:         "abnormal",
			SupportLevel:   "standard",
			ReasonCode:     "overcharged",
		},
	}
	if err := DB.Create(&items).Error; err != nil {
		t.Fatalf("create items: %v", err)
	}

	rows, total, err := GetPriceInspectionIssueGroups("", "", "", "", "", "active", 0, 0, 0, 0, 0, 1, 20)
	if err != nil {
		t.Fatalf("GetPriceInspectionIssueGroups: %v", err)
	}
	if total != 3 || len(rows) != 3 {
		t.Fatalf("rows total=%d len=%d, want 3", total, len(rows))
	}
	if rows[0].ModelName != "large-critical" {
		t.Fatalf("first row = %#v, want large-critical first", rows[0])
	}
	if rows[1].ModelName != "larger-abnormal" {
		t.Fatalf("second row = %#v, want larger-abnormal second", rows[1])
	}
	if rows[2].ModelName != "tiny-ratio" {
		t.Fatalf("third row = %#v, want tiny-ratio last", rows[2])
	}
}
