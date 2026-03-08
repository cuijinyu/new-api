package model

import (
	"fmt"
	"time"

	"github.com/QuantumNous/new-api/common"
	"gorm.io/gorm"
)

// ReconDiscount 渠道+模型级折扣配置
type ReconDiscount struct {
	ID           int64   `json:"id" gorm:"primaryKey;autoIncrement"`
	ChannelId    int     `json:"channel_id" gorm:"uniqueIndex:idx_channel_model"`
	Model        string  `json:"model" gorm:"type:varchar(100);uniqueIndex:idx_channel_model"`
	DiscountRate float64 `json:"discount_rate" gorm:"type:decimal(5,4);default:1.0"`
	Note         string  `json:"note" gorm:"type:varchar(255)"`
	CreatedAt    int64   `json:"created_at" gorm:"autoCreateTime"`
	UpdatedAt    int64   `json:"updated_at" gorm:"autoUpdateTime"`
}

func (ReconDiscount) TableName() string { return "recon_discounts" }

// ReconUpstream 上游账单汇总
type ReconUpstream struct {
	ID                    int64  `json:"id" gorm:"primaryKey;autoIncrement"`
	ReconDate             string `json:"recon_date" gorm:"type:varchar(10);index:idx_recon_upstream,priority:1"`
	ChannelId             int    `json:"channel_id" gorm:"index:idx_recon_upstream,priority:2"`
	Source                string `json:"source" gorm:"type:varchar(50)"`
	Model                 string `json:"model" gorm:"type:varchar(100);index:idx_recon_upstream,priority:3"`
	TotalRequests         int    `json:"total_requests" gorm:"default:0"`
	TotalPromptTokens     int64  `json:"total_prompt_tokens" gorm:"default:0"`
	TotalCompletionTokens int64  `json:"total_completion_tokens" gorm:"default:0"`
	TotalAmountCent       int64  `json:"total_amount_cent" gorm:"default:0"`
	Currency              string `json:"currency" gorm:"type:varchar(10);default:'USD'"`
	CreatedAt             int64  `json:"created_at" gorm:"autoCreateTime"`
}

func (ReconUpstream) TableName() string { return "recon_upstreams" }

// ReconResult 对账结果
type ReconResult struct {
	ID                       int64   `json:"id" gorm:"primaryKey;autoIncrement"`
	ReconDate                string  `json:"recon_date" gorm:"type:varchar(10);index:idx_recon_result,priority:1"`
	ChannelId                int     `json:"channel_id" gorm:"index:idx_recon_result,priority:2"`
	ChannelName              string  `json:"channel_name" gorm:"->"`
	Source                   string  `json:"source" gorm:"type:varchar(50)"`
	Model                    string  `json:"model" gorm:"type:varchar(100)"`
	SystemRequests           int     `json:"system_requests" gorm:"default:0"`
	UpstreamRequests         int     `json:"upstream_requests" gorm:"default:0"`
	SystemPromptTokens       int64   `json:"system_prompt_tokens" gorm:"default:0"`
	UpstreamPromptTokens     int64   `json:"upstream_prompt_tokens" gorm:"default:0"`
	SystemCompletionTokens   int64   `json:"system_completion_tokens" gorm:"default:0"`
	UpstreamCompletionTokens int64   `json:"upstream_completion_tokens" gorm:"default:0"`
	SystemQuota              int64   `json:"system_quota" gorm:"default:0"`
	UpstreamAmountCent       int64   `json:"upstream_amount_cent" gorm:"default:0"`
	DiscountRate             float64 `json:"discount_rate" gorm:"type:decimal(5,4);default:1.0"`
	ExpectedAmountCent       int64   `json:"expected_amount_cent" gorm:"default:0"`
	AmountDiffCent           int64   `json:"amount_diff_cent" gorm:"default:0"`
	TokenDiffRate            float64 `json:"token_diff_rate" gorm:"type:decimal(10,6);default:0"`
	AmountDiffRate           float64 `json:"amount_diff_rate" gorm:"type:decimal(10,6);default:0"`
	Status                   string  `json:"status" gorm:"type:varchar(20);index;default:'pending'"`
	Remark                   string  `json:"remark" gorm:"type:text"`
	CreatedAt                int64   `json:"created_at" gorm:"autoCreateTime"`
}

func (ReconResult) TableName() string { return "recon_results" }

// SystemSummaryRow 系统侧汇总行
type SystemSummaryRow struct {
	ReconDate             string `json:"recon_date"`
	ChannelId             int    `json:"channel_id"`
	Model                 string `json:"model"`
	TotalRequests         int    `json:"total_requests"`
	TotalPromptTokens     int64  `json:"total_prompt_tokens"`
	TotalCompletionTokens int64  `json:"total_completion_tokens"`
	TotalQuota            int64  `json:"total_quota"`
}

// GetSystemSummary 从 logs 按天+模型+渠道汇总，支持日期范围
func GetSystemSummary(startDate, endDate string, channelId int) ([]SystemSummaryRow, error) {
	var rows []SystemSummaryRow

	dateFunc := "DATE(FROM_UNIXTIME(created_at))"
	if common.UsingPostgreSQL {
		dateFunc = "TO_CHAR(TO_TIMESTAMP(created_at), 'YYYY-MM-DD')"
	}

	tx := LOG_DB.Table("logs").
		Select(dateFunc+" AS recon_date, channel_id, model_name AS model, "+
			"COUNT(*) AS total_requests, "+
			"SUM(prompt_tokens) AS total_prompt_tokens, "+
			"SUM(completion_tokens) AS total_completion_tokens, "+
			"SUM(quota) AS total_quota").
		Where("type = ?", LogTypeConsume).
		Where(dateFunc+" >= ? AND "+dateFunc+" <= ?", startDate, endDate)

	if channelId > 0 {
		tx = tx.Where("channel_id = ?", channelId)
	}

	err := tx.Group(dateFunc + ", channel_id, model_name").Scan(&rows).Error
	return rows, err
}

// GetUpstreamByDateRange 获取日期范围内的上游账单
func GetUpstreamByDateRange(startDate, endDate string, channelId int) ([]ReconUpstream, error) {
	var rows []ReconUpstream
	tx := DB.Where("recon_date >= ? AND recon_date <= ?", startDate, endDate)
	if channelId > 0 {
		tx = tx.Where("channel_id = ?", channelId)
	}
	err := tx.Find(&rows).Error
	return rows, err
}

// DeleteUpstreamByDateRangeAndChannel 幂等删除（支持日期范围）
func DeleteUpstreamByDateRangeAndChannel(startDate, endDate string, channelId int, source string) error {
	tx := DB.Where("recon_date >= ? AND recon_date <= ? AND channel_id = ? AND source = ?", startDate, endDate, channelId, source)
	return tx.Delete(&ReconUpstream{}).Error
}

// InsertUpstreamBatch 批量插入上游账单
func InsertUpstreamBatch(rows []ReconUpstream) error {
	if len(rows) == 0 {
		return nil
	}
	return DB.CreateInBatches(rows, 100).Error
}

// DeleteResultsByDateRange 删除日期范围内的对账结果
func DeleteResultsByDateRange(startDate, endDate string, channelId int) error {
	tx := DB.Where("recon_date >= ? AND recon_date <= ?", startDate, endDate)
	if channelId > 0 {
		tx = tx.Where("channel_id = ?", channelId)
	}
	return tx.Delete(&ReconResult{}).Error
}

// InsertResultsBatch 批量插入对账结果
func InsertResultsBatch(rows []ReconResult) error {
	if len(rows) == 0 {
		return nil
	}
	return DB.CreateInBatches(rows, 100).Error
}

// GetReconResults 分页查询对账结果（支持日期范围）
func GetReconResults(startDate, endDate string, channelId int, status string, page, pageSize int) ([]ReconResult, int64, error) {
	var results []ReconResult
	var total int64

	tx := DB.Model(&ReconResult{})
	if startDate != "" && endDate != "" {
		tx = tx.Where("recon_results.recon_date >= ? AND recon_results.recon_date <= ?", startDate, endDate)
	} else if startDate != "" {
		tx = tx.Where("recon_results.recon_date >= ?", startDate)
	} else if endDate != "" {
		tx = tx.Where("recon_results.recon_date <= ?", endDate)
	}
	if channelId > 0 {
		tx = tx.Where("recon_results.channel_id = ?", channelId)
	}
	if status != "" {
		tx = tx.Where("recon_results.status = ?", status)
	}

	if err := tx.Count(&total).Error; err != nil {
		return nil, 0, err
	}

	channelSelect := "(SELECT name FROM channels WHERE channels.id = recon_results.channel_id) AS channel_name"
	err := tx.Select("recon_results.*, "+channelSelect).
		Order("recon_results.recon_date DESC, recon_results.id DESC").
		Offset((page - 1) * pageSize).
		Limit(pageSize).
		Find(&results).Error

	return results, total, err
}

// GetDiscount 获取折扣比例，无配置返回 1.0
func GetDiscount(channelId int, model string) float64 {
	var d ReconDiscount
	err := DB.Where("channel_id = ? AND model = ?", channelId, model).First(&d).Error
	if err != nil {
		return 1.0
	}
	if d.DiscountRate <= 0 {
		return 1.0
	}
	return d.DiscountRate
}

// GetDiscountMap 批量获取折扣，返回 "channelId:model" -> rate
func GetDiscountMap() map[string]float64 {
	var discounts []ReconDiscount
	DB.Find(&discounts)
	m := make(map[string]float64, len(discounts))
	for _, d := range discounts {
		key := discountKey(d.ChannelId, d.Model)
		m[key] = d.DiscountRate
	}
	return m
}

func discountKey(channelId int, model string) string {
	return fmt.Sprintf("%d:%s", channelId, model)
}

// UpsertDiscount 创建或更新折扣配置
func UpsertDiscount(d *ReconDiscount) error {
	var existing ReconDiscount
	err := DB.Where("channel_id = ? AND model = ?", d.ChannelId, d.Model).First(&existing).Error
	if err != nil {
		if err == gorm.ErrRecordNotFound {
			return DB.Create(d).Error
		}
		return err
	}
	existing.DiscountRate = d.DiscountRate
	existing.Note = d.Note
	existing.UpdatedAt = time.Now().Unix()
	return DB.Save(&existing).Error
}

// GetAllDiscounts 获取所有折扣配置
func GetAllDiscounts() ([]ReconDiscount, error) {
	var discounts []ReconDiscount
	err := DB.Order("id DESC").Find(&discounts).Error
	return discounts, err
}

// DeleteDiscountById 删除折扣配置
func DeleteDiscountById(id int64) error {
	return DB.Delete(&ReconDiscount{}, id).Error
}
