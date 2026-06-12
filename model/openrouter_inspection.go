package model

import (
	"fmt"
	"time"

	"gorm.io/gorm"
)

type OpenRouterPriceSnapshot struct {
	ID                      int64   `json:"id" gorm:"primaryKey;autoIncrement"`
	FetchedAt               int64   `json:"fetched_at" gorm:"index:idx_or_price_model_time,priority:2;index:idx_or_price_local_time,priority:2;index"`
	ModelID                 string  `json:"model_id" gorm:"type:varchar(255);index:idx_or_price_model_time,priority:1"`
	CanonicalSlug           string  `json:"canonical_slug" gorm:"type:varchar(255)"`
	LocalModelName          string  `json:"local_model_name" gorm:"type:varchar(255);index:idx_or_price_local_time,priority:1"`
	PromptPricePerToken     float64 `json:"prompt_price_per_token" gorm:"type:decimal(24,18);default:0"`
	CompletionPricePerToken float64 `json:"completion_price_per_token" gorm:"type:decimal(24,18);default:0"`
	CacheReadPricePerToken  float64 `json:"cache_read_price_per_token" gorm:"type:decimal(24,18);default:0"`
	CacheWritePricePerToken float64 `json:"cache_write_price_per_token" gorm:"type:decimal(24,18);default:0"`
	ImagePrice              float64 `json:"image_price" gorm:"type:decimal(24,18);default:0"`
	RequestPrice            float64 `json:"request_price" gorm:"type:decimal(24,18);default:0"`
	IsFree                  bool    `json:"is_free" gorm:"default:false"`
	RawJSON                 string  `json:"raw_json" gorm:"type:text"`
	CreatedAt               int64   `json:"created_at" gorm:"autoCreateTime"`
}

func (OpenRouterPriceSnapshot) TableName() string {
	return "openrouter_price_snapshots"
}

type OpenRouterModelMapping struct {
	ID              int64  `json:"id" gorm:"primaryKey;autoIncrement"`
	ChannelID       int    `json:"channel_id" gorm:"index:idx_or_model_mapping,priority:1;default:0"`
	LocalModelName  string `json:"local_model_name" gorm:"type:varchar(255);index:idx_or_model_mapping,priority:2"`
	OpenRouterModel string `json:"openrouter_model_id" gorm:"type:varchar(255)"`
	Priority        int    `json:"priority" gorm:"default:0"`
	Enabled         bool   `json:"enabled" gorm:"default:true;index"`
	Note            string `json:"note" gorm:"type:varchar(255)"`
	CreatedAt       int64  `json:"created_at" gorm:"autoCreateTime"`
	UpdatedAt       int64  `json:"updated_at" gorm:"autoUpdateTime"`
}

func (OpenRouterModelMapping) TableName() string {
	return "openrouter_model_mappings"
}

type OpenRouterInspectionRun struct {
	ID               int64  `json:"id" gorm:"primaryKey;autoIncrement"`
	Status           string `json:"status" gorm:"type:varchar(32);index"`
	TriggerType      string `json:"trigger_type" gorm:"type:varchar(32)"`
	WindowStart      int64  `json:"window_start" gorm:"index"`
	WindowEnd        int64  `json:"window_end" gorm:"index"`
	StartedAt        int64  `json:"started_at"`
	FinishedAt       int64  `json:"finished_at"`
	TotalLogs        int    `json:"total_logs" gorm:"default:0"`
	CheckedLogs      int    `json:"checked_logs" gorm:"default:0"`
	NormalCount      int    `json:"normal_count" gorm:"default:0"`
	WarningCount     int    `json:"warning_count" gorm:"default:0"`
	AbnormalCount    int    `json:"abnormal_count" gorm:"default:0"`
	CriticalCount    int    `json:"critical_count" gorm:"default:0"`
	MissingCount     int    `json:"missing_count" gorm:"default:0"`
	UnsupportedCount int    `json:"unsupported_count" gorm:"default:0"`
	FailedCount      int    `json:"failed_count" gorm:"default:0"`
	SummaryJSON      string `json:"summary_json" gorm:"type:text"`
	CreatedAt        int64  `json:"created_at" gorm:"autoCreateTime"`
}

func (OpenRouterInspectionRun) TableName() string {
	return "openrouter_billing_inspection_runs"
}

type OpenRouterInspectionItem struct {
	ID                int64   `json:"id" gorm:"primaryKey;autoIncrement"`
	RunID             int64   `json:"run_id" gorm:"uniqueIndex:idx_or_inspection_log_run,priority:1;index"`
	LogID             int64   `json:"log_id" gorm:"uniqueIndex:idx_or_inspection_log_run,priority:2;index"`
	LogCreatedAt      int64   `json:"created_at" gorm:"index:idx_or_inspection_channel_time,priority:2;index:idx_or_inspection_model_time,priority:2"`
	ChannelID         int     `json:"channel_id" gorm:"index:idx_or_inspection_channel_time,priority:1"`
	ModelName         string  `json:"model_name" gorm:"type:varchar(255);index:idx_or_inspection_model_time,priority:1"`
	OpenRouterModelID string  `json:"openrouter_model_id" gorm:"type:varchar(255)"`
	PriceSnapshotID   int64   `json:"price_snapshot_id" gorm:"default:0"`
	ActualQuota       int64   `json:"actual_quota"`
	ExpectedQuota     int64   `json:"expected_quota"`
	DeltaQuota        int64   `json:"delta_quota"`
	DiffRate          float64 `json:"diff_rate" gorm:"type:decimal(12,8);default:0;index"`
	ExpectedUSD       float64 `json:"expected_usd" gorm:"type:decimal(24,12);default:0"`
	ActualUSD         float64 `json:"actual_usd" gorm:"type:decimal(24,12);default:0"`
	InputTokens       int     `json:"input_tokens" gorm:"default:0"`
	OutputTokens      int     `json:"output_tokens" gorm:"default:0"`
	CacheReadTokens   int     `json:"cache_read_tokens" gorm:"default:0"`
	CacheWriteTokens  int     `json:"cache_write_tokens" gorm:"default:0"`
	GroupRatio        float64 `json:"group_ratio" gorm:"type:decimal(12,6);default:1"`
	CondMultiplier    float64 `json:"cond_multiplier" gorm:"type:decimal(12,6);default:1"`
	Status            string  `json:"status" gorm:"type:varchar(32);index"`
	SupportLevel      string  `json:"support_level" gorm:"type:varchar(32);index"`
	ReasonCode        string  `json:"reason_code" gorm:"type:varchar(64);index"`
	ReasonDetail      string  `json:"reason_detail" gorm:"type:text"`
	RawContextJSON    string  `json:"raw_context_json" gorm:"type:text"`
	CreatedRecordAt   int64   `json:"created_record_at" gorm:"autoCreateTime"`
}

func (OpenRouterInspectionItem) TableName() string {
	return "openrouter_billing_inspection_items"
}

func InsertOpenRouterPriceSnapshots(rows []OpenRouterPriceSnapshot) error {
	if len(rows) == 0 {
		return nil
	}
	return DB.CreateInBatches(rows, 100).Error
}

func GetOpenRouterPriceSnapshotStats() (int64, int64, error) {
	var count int64
	if err := DB.Model(&OpenRouterPriceSnapshot{}).Count(&count).Error; err != nil {
		return 0, 0, err
	}
	var latest int64
	if count > 0 {
		if err := DB.Model(&OpenRouterPriceSnapshot{}).Select("COALESCE(MAX(fetched_at), 0)").Scan(&latest).Error; err != nil {
			return 0, 0, err
		}
	}
	return count, latest, nil
}

func GetOpenRouterPriceSnapshots(modelID, localModelName string, fetchedStart, fetchedEnd int64, page, pageSize int) ([]OpenRouterPriceSnapshot, int64, error) {
	var rows []OpenRouterPriceSnapshot
	var total int64
	tx := DB.Model(&OpenRouterPriceSnapshot{})
	if modelID != "" {
		tx = tx.Where("model_id = ?", modelID)
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

func CreateOpenRouterInspectionRun(run *OpenRouterInspectionRun) error {
	if run.StartedAt == 0 {
		run.StartedAt = time.Now().Unix()
	}
	if run.Status == "" {
		run.Status = "running"
	}
	return DB.Create(run).Error
}

func UpdateOpenRouterInspectionRun(run *OpenRouterInspectionRun) error {
	return DB.Save(run).Error
}

func InsertOpenRouterInspectionItems(rows []OpenRouterInspectionItem) error {
	if len(rows) == 0 {
		return nil
	}
	return DB.CreateInBatches(rows, 100).Error
}

func FindOpenRouterModelMapping(channelID int, localModel string) (*OpenRouterModelMapping, error) {
	var mapping OpenRouterModelMapping
	err := DB.Where("enabled = ? AND local_model_name = ? AND (channel_id = ? OR channel_id = 0)", true, localModel, channelID).
		Order("channel_id DESC, priority DESC, id DESC").
		First(&mapping).Error
	if err != nil {
		return nil, err
	}
	return &mapping, nil
}

func FindOpenRouterPriceSnapshot(modelID, localModel string, createdAt int64) (*OpenRouterPriceSnapshot, string, error) {
	var snapshot OpenRouterPriceSnapshot
	if modelID != "" {
		err := DB.Where("model_id = ? AND fetched_at <= ?", modelID, createdAt).
			Order("fetched_at DESC, id DESC").
			First(&snapshot).Error
		if err == nil {
			return &snapshot, "exact_history", nil
		}
		if err != gorm.ErrRecordNotFound {
			return nil, "", err
		}
	}
	if localModel != "" {
		err := DB.Where("local_model_name = ? AND fetched_at <= ?", localModel, createdAt).
			Order("fetched_at DESC, id DESC").
			First(&snapshot).Error
		if err == nil {
			return &snapshot, "local_history", nil
		}
		if err != gorm.ErrRecordNotFound {
			return nil, "", err
		}
	}
	if modelID != "" {
		err := DB.Where("model_id = ?", modelID).
			Order("fetched_at DESC, id DESC").
			First(&snapshot).Error
		if err == nil {
			return &snapshot, "exact_latest", nil
		}
		if err != gorm.ErrRecordNotFound {
			return nil, "", err
		}
	}
	if localModel != "" {
		err := DB.Where("local_model_name = ?", localModel).
			Order("fetched_at DESC, id DESC").
			First(&snapshot).Error
		if err == nil {
			return &snapshot, "local_latest", nil
		}
		if err != gorm.ErrRecordNotFound {
			return nil, "", err
		}
	}
	return nil, "", fmt.Errorf("openrouter price snapshot not found for model_id=%s local_model=%s", modelID, localModel)
}

func GetOpenRouterInspectionRuns(startTime, endTime int64, status string, page, pageSize int) ([]OpenRouterInspectionRun, int64, error) {
	var rows []OpenRouterInspectionRun
	var total int64
	tx := DB.Model(&OpenRouterInspectionRun{})
	if startTime > 0 {
		tx = tx.Where("started_at >= ?", startTime)
	}
	if endTime > 0 {
		tx = tx.Where("started_at <= ?", endTime)
	}
	if status != "" {
		tx = tx.Where("status = ?", status)
	}
	if err := tx.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	err := tx.Order("id DESC").Offset((page - 1) * pageSize).Limit(pageSize).Find(&rows).Error
	return rows, total, err
}

func GetOpenRouterInspectionItems(runID int64, channelID int, modelName, status, reasonCode string, minDiffRate float64, page, pageSize int) ([]OpenRouterInspectionItem, int64, error) {
	var rows []OpenRouterInspectionItem
	var total int64
	tx := DB.Model(&OpenRouterInspectionItem{})
	if runID > 0 {
		tx = tx.Where("run_id = ?", runID)
	}
	if channelID > 0 {
		tx = tx.Where("channel_id = ?", channelID)
	}
	if modelName != "" {
		tx = tx.Where("model_name = ?", modelName)
	}
	if status != "" {
		tx = tx.Where("status = ?", status)
	}
	if reasonCode != "" {
		tx = tx.Where("reason_code = ?", reasonCode)
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
