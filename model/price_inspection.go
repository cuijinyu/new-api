package model

import (
	"errors"
	"strconv"
	"strings"

	"github.com/QuantumNous/new-api/common"

	"gorm.io/gorm"
)

type PriceModelMapping struct {
	ID               int64  `json:"id" gorm:"primaryKey;autoIncrement"`
	ChannelID        int    `json:"channel_id" gorm:"index:idx_price_model_mapping,priority:1;default:0"`
	ChannelType      int    `json:"channel_type" gorm:"index:idx_price_model_mapping,priority:2;default:0"`
	LocalModelName   string `json:"local_model_name" gorm:"type:varchar(255);index:idx_price_model_mapping,priority:3"`
	SourceProvider   string `json:"source_provider" gorm:"type:varchar(64);index:idx_price_model_mapping,priority:4"`
	SourceModelID    string `json:"source_model_id" gorm:"type:varchar(255)"`
	CanonicalModelID string `json:"canonical_model_id" gorm:"type:varchar(255)"`
	Scenario         string `json:"scenario" gorm:"type:varchar(64);index"`
	Priority         int    `json:"priority" gorm:"default:0"`
	Enabled          bool   `json:"enabled" gorm:"default:true;index"`
	Confidence       string `json:"confidence" gorm:"type:varchar(32);default:'manual'"`
	Note             string `json:"note" gorm:"type:varchar(255)"`
	CreatedAt        int64  `json:"created_at" gorm:"autoCreateTime"`
	UpdatedAt        int64  `json:"updated_at" gorm:"autoUpdateTime"`
}

func (PriceModelMapping) TableName() string {
	return "price_model_mappings"
}

type PriceSourceSnapshot struct {
	ID                        int64   `json:"id" gorm:"primaryKey;autoIncrement"`
	SourceProvider            string  `json:"source_provider" gorm:"type:varchar(64);index:idx_price_source_snapshot_provider_time,priority:1;index:idx_price_source_snapshot_model,priority:1"`
	FetchedAt                 int64   `json:"fetched_at" gorm:"index:idx_price_source_snapshot_provider_time,priority:2;index"`
	ModelID                   string  `json:"model_id" gorm:"type:varchar(255);index:idx_price_source_snapshot_model,priority:2"`
	CanonicalModelID          string  `json:"canonical_model_id" gorm:"type:varchar(255);index"`
	LocalModelName            string  `json:"local_model_name" gorm:"type:varchar(255);index"`
	Scenario                  string  `json:"scenario" gorm:"type:varchar(64);index"`
	PricingScheme             string  `json:"pricing_scheme" gorm:"type:varchar(64);index"`
	Currency                  string  `json:"currency" gorm:"type:varchar(16);default:'USD'"`
	Unit                      string  `json:"unit" gorm:"type:varchar(64)"`
	InputPricePerToken        float64 `json:"input_price_per_token" gorm:"type:decimal(24,18);default:0"`
	OutputPricePerToken       float64 `json:"output_price_per_token" gorm:"type:decimal(24,18);default:0"`
	CacheReadPricePerToken    float64 `json:"cache_read_price_per_token" gorm:"type:decimal(24,18);default:0"`
	CacheWritePricePerToken   float64 `json:"cache_write_price_per_token" gorm:"type:decimal(24,18);default:0"`
	CacheWrite5mPricePerToken float64 `json:"cache_write_5m_price_per_token" gorm:"type:decimal(24,18);default:0"`
	CacheWrite1hPricePerToken float64 `json:"cache_write_1h_price_per_token" gorm:"type:decimal(24,18);default:0"`
	InputImagePricePerToken   float64 `json:"input_image_price_per_token" gorm:"type:decimal(24,18);default:0"`
	OutputImagePricePerToken  float64 `json:"output_image_price_per_token" gorm:"type:decimal(24,18);default:0"`
	InputAudioPricePerToken   float64 `json:"input_audio_price_per_token" gorm:"type:decimal(24,18);default:0"`
	OutputAudioPricePerToken  float64 `json:"output_audio_price_per_token" gorm:"type:decimal(24,18);default:0"`
	ImagePrice                float64 `json:"image_price" gorm:"type:decimal(24,18);default:0"`
	RequestPrice              float64 `json:"request_price" gorm:"type:decimal(24,18);default:0"`
	PricePerSecond            float64 `json:"price_per_second" gorm:"type:decimal(24,18);default:0"`
	IsFree                    bool    `json:"is_free" gorm:"default:false"`
	Manual                    bool    `json:"manual" gorm:"default:false;index"`
	RawJSON                   string  `json:"raw_json" gorm:"type:text"`
	CreatedAt                 int64   `json:"created_at" gorm:"autoCreateTime"`
}

func (PriceSourceSnapshot) TableName() string {
	return "price_source_snapshots"
}

type PriceInspectionCoverageReport struct {
	ID               int64  `json:"id" gorm:"primaryKey;autoIncrement"`
	GeneratedAt      int64  `json:"generated_at" gorm:"index:idx_price_coverage_provider_generated,priority:2;index"`
	SourceProvider   string `json:"source_provider" gorm:"type:varchar(64);index:idx_price_coverage_provider_generated,priority:1;index"`
	ChannelType      int    `json:"channel_type" gorm:"index"`
	ChannelTypeName  string `json:"channel_type_name" gorm:"type:varchar(64)"`
	ModelName        string `json:"model_name" gorm:"type:varchar(255);index"`
	Scenario         string `json:"scenario" gorm:"type:varchar(64);index"`
	MappingStatus    string `json:"mapping_status" gorm:"type:varchar(64);index"`
	CalculatorStatus string `json:"calculator_status" gorm:"type:varchar(64);index"`
	LogContextStatus string `json:"log_context_status" gorm:"type:varchar(64);index"`
	SupportLevel     string `json:"support_level" gorm:"type:varchar(32);index"`
	ReasonCode       string `json:"reason_code" gorm:"type:varchar(64);index"`
	SourceModelID    string `json:"source_model_id" gorm:"type:varchar(255)"`
	CanonicalModelID string `json:"canonical_model_id" gorm:"type:varchar(255)"`
	ChannelCount     int    `json:"channel_count" gorm:"default:0"`
	SampleLogCount   int64  `json:"sample_log_count" gorm:"default:0"`
	LastSeenAt       int64  `json:"last_seen_at" gorm:"default:0;index"`
	Suggestion       string `json:"suggestion" gorm:"type:text"`
	RawJSON          string `json:"raw_json" gorm:"type:text"`
	CreatedAt        int64  `json:"created_at" gorm:"autoCreateTime"`
}

func (PriceInspectionCoverageReport) TableName() string {
	return "price_inspection_coverage_reports"
}

type PriceInspectionRun struct {
	ID               int64  `json:"id" gorm:"primaryKey;autoIncrement"`
	SourceProvider   string `json:"source_provider" gorm:"type:varchar(64);index:idx_price_run_provider_time,priority:1;index"`
	SourceRunID      int64  `json:"source_run_id" gorm:"default:0;index"`
	Status           string `json:"status" gorm:"type:varchar(32);index"`
	TriggerType      string `json:"trigger_type" gorm:"type:varchar(32)"`
	ChannelID        int    `json:"channel_id" gorm:"default:0;index"`
	ChannelType      int    `json:"channel_type" gorm:"default:0;index"`
	ModelName        string `json:"model_name" gorm:"type:varchar(255);index"`
	WindowStart      int64  `json:"window_start" gorm:"index"`
	WindowEnd        int64  `json:"window_end" gorm:"index"`
	StartedAt        int64  `json:"started_at" gorm:"index:idx_price_run_provider_time,priority:2"`
	FinishedAt       int64  `json:"finished_at"`
	TotalLogs        int    `json:"total_logs" gorm:"default:0"`
	CheckedLogs      int    `json:"checked_logs" gorm:"default:0"`
	NormalCount      int    `json:"normal_count" gorm:"default:0"`
	WarningCount     int    `json:"warning_count" gorm:"default:0"`
	AbnormalCount    int    `json:"abnormal_count" gorm:"default:0"`
	CriticalCount    int    `json:"critical_count" gorm:"default:0"`
	MissingCount     int    `json:"missing_count" gorm:"default:0"`
	UnsupportedCount int    `json:"unsupported_count" gorm:"default:0"`
	OutOfScopeCount  int    `json:"out_of_scope_count" gorm:"default:0"`
	FailedCount      int    `json:"failed_count" gorm:"default:0"`
	SummaryJSON      string `json:"summary_json" gorm:"type:text"`
	CreatedAt        int64  `json:"created_at" gorm:"autoCreateTime"`
}

func (PriceInspectionRun) TableName() string {
	return "price_inspection_runs"
}

type PriceInspectionItem struct {
	ID                  int64   `json:"id" gorm:"primaryKey;autoIncrement"`
	RunID               int64   `json:"run_id" gorm:"uniqueIndex:idx_price_inspection_log_run,priority:1;index"`
	SourceRunID         int64   `json:"source_run_id" gorm:"default:0;index"`
	LogID               int64   `json:"log_id" gorm:"uniqueIndex:idx_price_inspection_log_run,priority:2;index"`
	LogCreatedAt        int64   `json:"created_at" gorm:"index:idx_price_inspection_channel_time,priority:2;index:idx_price_inspection_model_time,priority:2"`
	ChannelID           int     `json:"channel_id" gorm:"index:idx_price_inspection_channel_time,priority:1"`
	ChannelType         int     `json:"channel_type" gorm:"default:0;index"`
	SourceProvider      string  `json:"source_provider" gorm:"type:varchar(64);index"`
	ModelName           string  `json:"model_name" gorm:"type:varchar(255);index:idx_price_inspection_model_time,priority:1"`
	SourceModelID       string  `json:"source_model_id" gorm:"type:varchar(255)"`
	CanonicalModelID    string  `json:"canonical_model_id" gorm:"type:varchar(255)"`
	Scenario            string  `json:"scenario" gorm:"type:varchar(64);index"`
	PriceSnapshotID     int64   `json:"price_snapshot_id" gorm:"default:0"`
	ActualQuota         int64   `json:"actual_quota"`
	ExpectedQuota       int64   `json:"expected_quota"`
	DeltaQuota          int64   `json:"delta_quota"`
	DiffRate            float64 `json:"diff_rate" gorm:"type:decimal(12,8);default:0;index"`
	ExpectedUSD         float64 `json:"expected_usd" gorm:"type:decimal(24,12);default:0"`
	ActualUSD           float64 `json:"actual_usd" gorm:"type:decimal(24,12);default:0"`
	SupportLevel        string  `json:"support_level" gorm:"type:varchar(32);index"`
	Status              string  `json:"status" gorm:"type:varchar(32);index"`
	ReasonCode          string  `json:"reason_code" gorm:"type:varchar(64);index"`
	ReasonDetail        string  `json:"reason_detail" gorm:"type:text"`
	BillingContextJSON  string  `json:"billing_context_json" gorm:"type:text"`
	CalculatorTraceJSON string  `json:"calculator_trace_json" gorm:"type:text"`
	CreatedRecordAt     int64   `json:"created_record_at" gorm:"autoCreateTime"`
}

func (PriceInspectionItem) TableName() string {
	return "price_inspection_items"
}

type PriceInspectionIssueGroup struct {
	SourceProvider      string  `json:"source_provider"`
	ModelName           string  `json:"model_name"`
	ChannelID           int     `json:"channel_id"`
	ChannelType         int     `json:"channel_type"`
	Status              string  `json:"status"`
	SupportLevel        string  `json:"support_level"`
	ReasonCode          string  `json:"reason_code"`
	Count               int64   `json:"count"`
	SampleLogID         int64   `json:"sample_log_id"`
	LatestLogAt         int64   `json:"latest_log_at"`
	TotalActualQuota    int64   `json:"total_actual_quota"`
	TotalExpectedQuota  int64   `json:"total_expected_quota"`
	TotalDeltaQuota     int64   `json:"total_delta_quota"`
	MaxAbsDeltaQuota    int64   `json:"max_abs_delta_quota"`
	MaxDiffRate         float64 `json:"max_diff_rate"`
	ResolutionStatus    string  `json:"resolution_status"`
	ResolutionNote      string  `json:"resolution_note"`
	ResolutionUpdatedAt int64   `json:"resolution_updated_at"`
	ResolutionUpdatedBy string  `json:"resolution_updated_by"`
	ResolutionOwner     string  `json:"resolution_owner"`
	ResolutionExpireAt  int64   `json:"resolution_expire_at"`
}

type PriceInspectionIssueResolution struct {
	ID               int64  `json:"id" gorm:"primaryKey;autoIncrement"`
	SourceProvider   string `json:"source_provider" gorm:"type:varchar(64);uniqueIndex:idx_price_issue_resolution_key,priority:1;index"`
	ModelName        string `json:"model_name" gorm:"type:varchar(255);uniqueIndex:idx_price_issue_resolution_key,priority:2;index"`
	ChannelID        int    `json:"channel_id" gorm:"uniqueIndex:idx_price_issue_resolution_key,priority:3;default:0;index"`
	ChannelType      int    `json:"channel_type" gorm:"uniqueIndex:idx_price_issue_resolution_key,priority:4;default:0;index"`
	Status           string `json:"status" gorm:"type:varchar(32);uniqueIndex:idx_price_issue_resolution_key,priority:5;index"`
	SupportLevel     string `json:"support_level" gorm:"type:varchar(32);uniqueIndex:idx_price_issue_resolution_key,priority:6;index"`
	ReasonCode       string `json:"reason_code" gorm:"type:varchar(64);uniqueIndex:idx_price_issue_resolution_key,priority:7;index"`
	ResolutionStatus string `json:"resolution_status" gorm:"type:varchar(32);default:'open';index"`
	Note             string `json:"note" gorm:"type:text"`
	Owner            string `json:"owner" gorm:"type:varchar(64)"`
	ExpireAt         int64  `json:"expire_at" gorm:"default:0;index"`
	UpdatedBy        string `json:"updated_by" gorm:"type:varchar(64)"`
	CreatedAt        int64  `json:"created_at" gorm:"autoCreateTime"`
	UpdatedAt        int64  `json:"updated_at" gorm:"autoUpdateTime"`
}

func (PriceInspectionIssueResolution) TableName() string {
	return "price_inspection_issue_resolutions"
}

func InsertPriceInspectionCoverageReports(rows []PriceInspectionCoverageReport) error {
	if len(rows) == 0 {
		return nil
	}
	return DB.CreateInBatches(rows, 100).Error
}

func InsertPriceSourceSnapshots(rows []PriceSourceSnapshot) error {
	if len(rows) == 0 {
		return nil
	}
	return DB.CreateInBatches(rows, 100).Error
}

func CreatePriceSourceSnapshot(snapshot *PriceSourceSnapshot) error {
	return DB.Create(snapshot).Error
}

func DeletePriceSourceSnapshot(id int64) error {
	return DB.Delete(&PriceSourceSnapshot{}, id).Error
}

func GetPriceSourceSnapshotByID(id int64) (*PriceSourceSnapshot, error) {
	var snapshot PriceSourceSnapshot
	if err := DB.First(&snapshot, id).Error; err != nil {
		return nil, err
	}
	return &snapshot, nil
}

func DeleteAutomaticPriceSourceSnapshotsBefore(sourceProvider string, beforeFetchedAt int64) (int64, error) {
	if beforeFetchedAt <= 0 {
		return 0, nil
	}
	tx := DB.Where("manual = ? AND fetched_at < ?", false, beforeFetchedAt)
	if sourceProvider != "" {
		tx = tx.Where("source_provider = ?", sourceProvider)
	}
	result := tx.Delete(&PriceSourceSnapshot{})
	return result.RowsAffected, result.Error
}

func GetPriceSourceSnapshotStats(sourceProvider string) (int64, int64, error) {
	var count int64
	tx := DB.Model(&PriceSourceSnapshot{})
	if sourceProvider != "" {
		tx = tx.Where("source_provider = ?", sourceProvider)
	}
	if err := tx.Count(&count).Error; err != nil {
		return 0, 0, err
	}
	var latest int64
	if count > 0 {
		latestTx := DB.Model(&PriceSourceSnapshot{})
		if sourceProvider != "" {
			latestTx = latestTx.Where("source_provider = ?", sourceProvider)
		}
		if err := latestTx.Select("COALESCE(MAX(fetched_at), 0)").Scan(&latest).Error; err != nil {
			return 0, 0, err
		}
	}
	return count, latest, nil
}

func GetPriceSourceSnapshots(sourceProvider, modelID, localModelName string, fetchedStart, fetchedEnd int64, page, pageSize int) ([]PriceSourceSnapshot, int64, error) {
	var rows []PriceSourceSnapshot
	var total int64
	tx := DB.Model(&PriceSourceSnapshot{})
	if sourceProvider != "" {
		tx = tx.Where("source_provider = ?", sourceProvider)
	}
	if modelID != "" {
		tx = tx.Where("model_id = ? OR canonical_model_id = ?", modelID, modelID)
	}
	if localModelName != "" {
		tx = tx.Where("local_model_name = ?", localModelName)
	}
	if fetchedStart > 0 {
		tx = tx.Where("fetched_at >= ?", fetchedStart)
	}
	if fetchedEnd > 0 {
		tx = tx.Where("fetched_at <= ?", fetchedEnd)
	}
	if err := tx.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	err := tx.Order("fetched_at DESC, id DESC").Offset((page - 1) * pageSize).Limit(pageSize).Find(&rows).Error
	return rows, total, err
}

func FindPriceSourceSnapshot(sourceProvider, modelID, localModelName string, createdAt int64) (*PriceSourceSnapshot, string, error) {
	var snapshot PriceSourceSnapshot
	if modelID != "" {
		tx := DB.Where("source_provider = ? AND (model_id = ? OR canonical_model_id = ?)", sourceProvider, modelID, modelID)
		if createdAt > 0 {
			tx = tx.Where("fetched_at <= ?", createdAt)
		}
		err := tx.Order("fetched_at DESC, id DESC").First(&snapshot).Error
		if err == nil {
			return &snapshot, "model_history", nil
		}
		if err != gorm.ErrRecordNotFound {
			return nil, "", err
		}
	}
	if localModelName != "" {
		tx := DB.Where("source_provider = ? AND local_model_name = ?", sourceProvider, localModelName)
		if createdAt > 0 {
			tx = tx.Where("fetched_at <= ?", createdAt)
		}
		err := tx.Order("fetched_at DESC, id DESC").First(&snapshot).Error
		if err == nil {
			return &snapshot, "local_history", nil
		}
		if err != gorm.ErrRecordNotFound {
			return nil, "", err
		}
	}
	if createdAt > 0 {
		if modelID != "" {
			err := DB.Where(
				"source_provider = ? AND manual = ? AND (model_id = ? OR canonical_model_id = ?)",
				sourceProvider, true, modelID, modelID,
			).Order("fetched_at DESC, id DESC").First(&snapshot).Error
			if err == nil {
				return &snapshot, "model_manual_latest_after_log", nil
			}
			if err != gorm.ErrRecordNotFound {
				return nil, "", err
			}
		}
		if localModelName != "" {
			err := DB.Where(
				"source_provider = ? AND manual = ? AND local_model_name = ?",
				sourceProvider, true, localModelName,
			).Order("fetched_at DESC, id DESC").First(&snapshot).Error
			if err == nil {
				return &snapshot, "local_manual_latest_after_log", nil
			}
			if err != gorm.ErrRecordNotFound {
				return nil, "", err
			}
		}
	}
	return nil, "", gorm.ErrRecordNotFound
}

func CreatePriceInspectionRun(run *PriceInspectionRun) error {
	return DB.Create(run).Error
}

func UpdatePriceInspectionRun(run *PriceInspectionRun) error {
	return DB.Save(run).Error
}

func InsertPriceInspectionItems(rows []PriceInspectionItem) error {
	if len(rows) == 0 {
		return nil
	}
	return DB.CreateInBatches(rows, 100).Error
}

func NormalizePriceInspectionResolutionStatus(status string) string {
	switch strings.ToLower(strings.TrimSpace(status)) {
	case "", "open":
		return "open"
	case "acknowledged", "ack":
		return "acknowledged"
	case "ignored", "ignore":
		return "ignored"
	case "resolved", "done":
		return "resolved"
	default:
		return ""
	}
}

func UpsertPriceInspectionIssueResolution(resolution *PriceInspectionIssueResolution) error {
	if resolution == nil {
		return nil
	}
	resolution.ResolutionStatus = NormalizePriceInspectionResolutionStatus(resolution.ResolutionStatus)
	var existing PriceInspectionIssueResolution
	err := DB.Where(
		"source_provider = ? AND model_name = ? AND channel_id = ? AND channel_type = ? AND status = ? AND support_level = ? AND reason_code = ?",
		resolution.SourceProvider,
		resolution.ModelName,
		resolution.ChannelID,
		resolution.ChannelType,
		resolution.Status,
		resolution.SupportLevel,
		resolution.ReasonCode,
	).First(&existing).Error
	if err == nil {
		existing.ResolutionStatus = resolution.ResolutionStatus
		existing.Note = resolution.Note
		existing.Owner = resolution.Owner
		existing.ExpireAt = resolution.ExpireAt
		existing.UpdatedBy = resolution.UpdatedBy
		return DB.Save(&existing).Error
	}
	if err != nil && !errors.Is(err, gorm.ErrRecordNotFound) {
		return err
	}
	return DB.Create(resolution).Error
}

func GetPriceInspectionRuns(sourceProvider, status, modelName string, channelID, channelType int, startTime, endTime int64, page, pageSize int) ([]PriceInspectionRun, int64, error) {
	var rows []PriceInspectionRun
	var total int64
	tx := DB.Model(&PriceInspectionRun{})
	if sourceProvider != "" {
		tx = tx.Where("source_provider = ?", sourceProvider)
	}
	if status != "" {
		tx = tx.Where("status = ?", status)
	}
	if modelName != "" {
		tx = tx.Where("model_name = ?", modelName)
	}
	if channelID > 0 {
		tx = tx.Where("channel_id = ?", channelID)
	}
	if channelType > 0 {
		tx = tx.Where("channel_type = ?", channelType)
	}
	if startTime > 0 {
		tx = tx.Where("started_at >= ?", startTime)
	}
	if endTime > 0 {
		tx = tx.Where("started_at <= ?", endTime)
	}
	if err := tx.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	err := tx.Order("id DESC").Offset((page - 1) * pageSize).Limit(pageSize).Find(&rows).Error
	return rows, total, err
}

func GetPriceInspectionItems(runID int64, sourceProvider, modelName, status, supportLevel, reasonCode string, channelID, channelType int, minDiffRate float64, page, pageSize int) ([]PriceInspectionItem, int64, error) {
	var rows []PriceInspectionItem
	var total int64
	tx := DB.Model(&PriceInspectionItem{})
	if runID > 0 {
		tx = tx.Where("run_id = ?", runID)
	}
	if sourceProvider != "" {
		tx = tx.Where("source_provider = ?", sourceProvider)
	}
	if modelName != "" {
		tx = tx.Where("model_name = ?", modelName)
	}
	if status != "" {
		tx = tx.Where("status = ?", status)
	}
	if supportLevel != "" {
		tx = tx.Where("support_level = ?", supportLevel)
	}
	if reasonCode != "" {
		tx = tx.Where("reason_code = ?", reasonCode)
	}
	if channelID > 0 {
		tx = tx.Where("channel_id = ?", channelID)
	}
	if channelType > 0 {
		tx = tx.Where("channel_type = ?", channelType)
	}
	if minDiffRate > 0 {
		tx = tx.Where("diff_rate >= ?", minDiffRate)
	}
	if err := tx.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	err := tx.Order("id DESC").Offset((page - 1) * pageSize).Limit(pageSize).Find(&rows).Error
	return rows, total, err
}

func GetPriceInspectionIssueGroups(sourceProvider, modelName, status, supportLevel, reasonCode, resolutionStatus string, channelID, channelType int, minDiffRate float64, startTime, endTime int64, page, pageSize int) ([]PriceInspectionIssueGroup, int64, error) {
	var rows []PriceInspectionIssueGroup
	var total int64
	base := DB.Model(&PriceInspectionItem{})
	if sourceProvider != "" {
		base = base.Where("source_provider = ?", sourceProvider)
	}
	if modelName != "" {
		base = base.Where("model_name = ?", modelName)
	}
	if status != "" {
		base = base.Where("status = ?", status)
	} else {
		base = base.Where("status IN ?", []string{"warning", "abnormal", "critical", "missing", "failed"})
	}
	if supportLevel != "" {
		base = base.Where("support_level = ?", supportLevel)
	}
	if reasonCode != "" {
		base = base.Where("reason_code = ?", reasonCode)
	}
	if channelID > 0 {
		base = base.Where("channel_id = ?", channelID)
	}
	if channelType > 0 {
		base = base.Where("channel_type = ?", channelType)
	}
	if minDiffRate > 0 {
		base = base.Where("diff_rate >= ?", minDiffRate)
	}
	if startTime > 0 {
		base = base.Where("log_created_at >= ?", startTime)
	}
	if endTime > 0 {
		base = base.Where("log_created_at <= ?", endTime)
	}
	groupExpr := "source_provider, model_name, channel_id, channel_type, status, support_level, reason_code"
	grouped := base.Select(`
		source_provider,
		model_name,
		channel_id,
		channel_type,
		status,
		support_level,
		reason_code,
		COUNT(*) AS count,
		MAX(log_id) AS sample_log_id,
		MAX(log_created_at) AS latest_log_at,
		SUM(actual_quota) AS total_actual_quota,
		SUM(expected_quota) AS total_expected_quota,
		SUM(delta_quota) AS total_delta_quota,
		MAX(ABS(delta_quota)) AS max_abs_delta_quota,
		MAX(diff_rate) AS max_diff_rate`).
		Group(groupExpr)
	joined := priceInspectionIssueResolutionJoin(DB.Table("(?) AS grouped", grouped))
	joined = applyPriceInspectionResolutionFilter(joined, resolutionStatus)
	if err := joined.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	err := joined.Select(`
		grouped.source_provider,
		grouped.model_name,
		grouped.channel_id,
		grouped.channel_type,
		grouped.status,
		grouped.support_level,
		grouped.reason_code,
		grouped.count,
		grouped.sample_log_id,
		grouped.latest_log_at,
		grouped.total_actual_quota,
		grouped.total_expected_quota,
		grouped.total_delta_quota,
		grouped.max_abs_delta_quota,
		grouped.max_diff_rate,
		COALESCE(resolutions.resolution_status, 'open') AS resolution_status,
		COALESCE(resolutions.note, '') AS resolution_note,
		COALESCE(resolutions.updated_at, 0) AS resolution_updated_at,
		COALESCE(resolutions.updated_by, '') AS resolution_updated_by,
		COALESCE(resolutions.owner, '') AS resolution_owner,
		COALESCE(resolutions.expire_at, 0) AS resolution_expire_at`).
		Order(`CASE grouped.status
			WHEN 'critical' THEN 5
			WHEN 'abnormal' THEN 4
			WHEN 'warning' THEN 3
			WHEN 'failed' THEN 2
			WHEN 'missing' THEN 1
			ELSE 0
		END DESC, grouped.max_abs_delta_quota DESC, grouped.max_diff_rate DESC, grouped.count DESC, grouped.latest_log_at DESC`).
		Offset((page - 1) * pageSize).
		Limit(pageSize).
		Scan(&rows).Error
	return rows, total, err
}

func priceInspectionIssueResolutionJoin(tx *gorm.DB) *gorm.DB {
	if common.UsingMySQL {
		return tx.Joins(`LEFT JOIN price_inspection_issue_resolutions AS resolutions
		ON resolutions.source_provider COLLATE utf8mb4_general_ci = grouped.source_provider COLLATE utf8mb4_general_ci
		AND resolutions.model_name COLLATE utf8mb4_general_ci = grouped.model_name COLLATE utf8mb4_general_ci
		AND resolutions.channel_id = grouped.channel_id
		AND resolutions.channel_type = grouped.channel_type
		AND resolutions.status COLLATE utf8mb4_general_ci = grouped.status COLLATE utf8mb4_general_ci
		AND resolutions.support_level COLLATE utf8mb4_general_ci = grouped.support_level COLLATE utf8mb4_general_ci
		AND resolutions.reason_code COLLATE utf8mb4_general_ci = grouped.reason_code COLLATE utf8mb4_general_ci`)
	}
	return tx.Joins(`LEFT JOIN price_inspection_issue_resolutions AS resolutions
		ON resolutions.source_provider = grouped.source_provider
		AND resolutions.model_name = grouped.model_name
		AND resolutions.channel_id = grouped.channel_id
		AND resolutions.channel_type = grouped.channel_type
		AND resolutions.status = grouped.status
		AND resolutions.support_level = grouped.support_level
		AND resolutions.reason_code = grouped.reason_code`)
}

func applyPriceInspectionResolutionFilter(tx *gorm.DB, resolutionStatus string) *gorm.DB {
	normalizedStatus := strings.ToLower(strings.TrimSpace(resolutionStatus))
	switch normalizedStatus {
	case "", "all":
		return tx
	case "active":
		return tx.Where("(resolutions.id IS NULL OR resolutions.resolution_status IN ?)", []string{"open", "acknowledged"})
	case "open":
		return tx.Where("(resolutions.id IS NULL OR resolutions.resolution_status = ?)", "open")
	case "acknowledged", "ignored", "resolved":
		return tx.Where("resolutions.resolution_status = ?", normalizedStatus)
	default:
		return tx
	}
}

func attachPriceInspectionIssueResolutions(rows []PriceInspectionIssueGroup) error {
	if len(rows) == 0 {
		return nil
	}
	orParts := make([]string, 0, len(rows))
	args := make([]any, 0, len(rows)*7)
	for _, row := range rows {
		orParts = append(orParts, "(source_provider = ? AND model_name = ? AND channel_id = ? AND channel_type = ? AND status = ? AND support_level = ? AND reason_code = ?)")
		args = append(args,
			row.SourceProvider,
			row.ModelName,
			row.ChannelID,
			row.ChannelType,
			row.Status,
			row.SupportLevel,
			row.ReasonCode,
		)
	}
	var resolutions []PriceInspectionIssueResolution
	if err := DB.Model(&PriceInspectionIssueResolution{}).Where(strings.Join(orParts, " OR "), args...).Find(&resolutions).Error; err != nil {
		return err
	}
	byKey := map[string]PriceInspectionIssueResolution{}
	for _, resolution := range resolutions {
		byKey[priceInspectionIssueResolutionKey(
			resolution.SourceProvider,
			resolution.ModelName,
			resolution.ChannelID,
			resolution.ChannelType,
			resolution.Status,
			resolution.SupportLevel,
			resolution.ReasonCode,
		)] = resolution
	}
	for i := range rows {
		rows[i].ResolutionStatus = "open"
		if resolution, ok := byKey[priceInspectionIssueResolutionKey(
			rows[i].SourceProvider,
			rows[i].ModelName,
			rows[i].ChannelID,
			rows[i].ChannelType,
			rows[i].Status,
			rows[i].SupportLevel,
			rows[i].ReasonCode,
		)]; ok {
			rows[i].ResolutionStatus = resolution.ResolutionStatus
			rows[i].ResolutionNote = resolution.Note
			rows[i].ResolutionUpdatedAt = resolution.UpdatedAt
			rows[i].ResolutionUpdatedBy = resolution.UpdatedBy
			rows[i].ResolutionOwner = resolution.Owner
			rows[i].ResolutionExpireAt = resolution.ExpireAt
		}
	}
	return nil
}

func priceInspectionIssueResolutionKey(sourceProvider, modelName string, channelID, channelType int, status, supportLevel, reasonCode string) string {
	return strings.Join([]string{
		sourceProvider,
		modelName,
		strconv.Itoa(channelID),
		strconv.Itoa(channelType),
		strings.TrimSpace(strings.ToLower(status)),
		supportLevel,
		reasonCode,
	}, "\x1f")
}

func GetLatestPriceInspectionCoverageGeneratedAt(sourceProvider string) (int64, error) {
	var generatedAt int64
	tx := DB.Model(&PriceInspectionCoverageReport{})
	if sourceProvider != "" {
		tx = tx.Where("source_provider = ?", sourceProvider)
	}
	err := tx.Select("COALESCE(MAX(generated_at), 0)").Scan(&generatedAt).Error
	return generatedAt, err
}

func GetPriceInspectionCoverageReports(sourceProvider, mappingStatus, calculatorStatus, supportLevel, reasonCode, modelName string, channelType int, generatedAt int64, page, pageSize int) ([]PriceInspectionCoverageReport, int64, error) {
	var rows []PriceInspectionCoverageReport
	var total int64
	tx := DB.Model(&PriceInspectionCoverageReport{})
	if sourceProvider != "" {
		tx = tx.Where("source_provider = ?", sourceProvider)
	}
	if generatedAt > 0 {
		tx = tx.Where("generated_at = ?", generatedAt)
	}
	if channelType > 0 {
		tx = tx.Where("channel_type = ?", channelType)
	}
	if modelName != "" {
		tx = tx.Where("model_name = ?", modelName)
	}
	if mappingStatus != "" {
		tx = tx.Where("mapping_status = ?", mappingStatus)
	}
	if calculatorStatus != "" {
		tx = tx.Where("calculator_status = ?", calculatorStatus)
	}
	if supportLevel != "" {
		tx = tx.Where("support_level = ?", supportLevel)
	}
	if reasonCode != "" {
		tx = tx.Where("reason_code = ?", reasonCode)
	}
	if err := tx.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	err := tx.Order("sample_log_count DESC, channel_count DESC, id DESC").Offset((page - 1) * pageSize).Limit(pageSize).Find(&rows).Error
	return rows, total, err
}

func CreatePriceModelMapping(mapping *PriceModelMapping) error {
	return DB.Create(mapping).Error
}

func UpdatePriceModelMapping(mapping *PriceModelMapping) error {
	return DB.Save(mapping).Error
}

func GetPriceModelMappingByID(id int64) (*PriceModelMapping, error) {
	var mapping PriceModelMapping
	if err := DB.First(&mapping, id).Error; err != nil {
		return nil, err
	}
	return &mapping, nil
}

func GetPriceModelMappings(sourceProvider, localModelName string, channelType int, enabled *bool, page, pageSize int) ([]PriceModelMapping, int64, error) {
	var rows []PriceModelMapping
	var total int64
	tx := DB.Model(&PriceModelMapping{})
	if sourceProvider != "" {
		tx = tx.Where("source_provider = ?", sourceProvider)
	}
	if localModelName != "" {
		tx = tx.Where("local_model_name = ?", localModelName)
	}
	if channelType > 0 {
		tx = tx.Where("channel_type = ?", channelType)
	}
	if enabled != nil {
		tx = tx.Where("enabled = ?", *enabled)
	}
	if err := tx.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	err := tx.Order("source_provider ASC, local_model_name ASC, priority DESC, id DESC").Offset((page - 1) * pageSize).Limit(pageSize).Find(&rows).Error
	return rows, total, err
}

func FindPriceModelMapping(channelIDs []int, channelType int, localModelName, sourceProvider string) (*PriceModelMapping, error) {
	var mapping PriceModelMapping
	err := DB.Where(
		"enabled = ? AND source_provider = ? AND local_model_name = ? AND (channel_id IN ? OR channel_id = 0) AND (channel_type = ? OR channel_type = 0)",
		true, sourceProvider, localModelName, channelIDs, channelType,
	).Order("channel_id DESC, channel_type DESC, priority DESC, id DESC").First(&mapping).Error
	if err == gorm.ErrRecordNotFound {
		return nil, err
	}
	return &mapping, err
}
