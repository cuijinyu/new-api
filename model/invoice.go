package model

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/QuantumNous/new-api/common"
)

// Invoice 账单表，用于管理员为指定用户生成消费账单
type Invoice struct {
	Id             int     `json:"id" gorm:"primaryKey"`
	InvoiceNo      string  `json:"invoice_no" gorm:"uniqueIndex;type:varchar(64)"` // 账单编号，格式：INV-YYYYMM-XXXX
	UserId         int     `json:"user_id" gorm:"index"`                           // 账单所属用户
	Username       string  `json:"username" gorm:"index;type:varchar(64)"`
	StartTimestamp int64   `json:"start_timestamp"` // 账单周期开始时间（Unix 秒）
	EndTimestamp   int64   `json:"end_timestamp"`   // 账单周期结束时间（Unix 秒）
	TotalQuota     int     `json:"total_quota"`     // 总消耗额度
	TotalAmount    float64 `json:"total_amount"`    // 总金额（USD）
	Currency       string  `json:"currency" gorm:"type:varchar(10);default:'USD'"`
	Items          string  `json:"items" gorm:"type:text"` // 按模型分组的消费明细，JSON 序列化的 []InvoiceItem
	Note           string  `json:"note" gorm:"type:text"`  // 备注
	CreatedAt      int64   `json:"created_at" gorm:"bigint;index"`
	CreatedBy      int     `json:"created_by"` // 创建者（管理员）用户 ID
}

// InvoiceItem 账单明细项，按模型分组汇总的消费数据
type InvoiceItem struct {
	ModelName        string  `json:"model_name"`
	RequestCount     int     `json:"request_count"`
	PromptTokens     int     `json:"prompt_tokens"`
	CompletionTokens int     `json:"completion_tokens"`
	Quota            int     `json:"quota"`
	Amount           float64 `json:"amount"` // 金额（USD），由 quota / QuotaPerUnit 换算
}

// InvoiceLogDetail 账单逐条消费明细，用于导出详细账单
type InvoiceLogDetail struct {
	Id               int    `json:"id" gorm:"column:id"`
	CreatedAt        int64  `json:"created_at" gorm:"column:created_at"`
	ModelName        string `json:"model_name" gorm:"column:model_name"`
	TokenName        string `json:"token_name" gorm:"column:token_name"`
	PromptTokens     int    `json:"prompt_tokens" gorm:"column:prompt_tokens"`
	CompletionTokens int    `json:"completion_tokens" gorm:"column:completion_tokens"`
	Quota            int    `json:"quota" gorm:"column:quota"`
	Content          string `json:"content" gorm:"column:content"`
	Other            string `json:"-" gorm:"column:other"`
	RequestId        string `json:"request_id" gorm:"-"`
}

// GenerateInvoiceNo 生成唯一的账单编号，格式为 INV-YYYYMM-XXXX
func GenerateInvoiceNo() (string, error) {
	now := time.Now()
	prefix := fmt.Sprintf("INV-%s", now.Format("200601"))

	var count int64
	err := DB.Model(&Invoice{}).Where("invoice_no LIKE ?", prefix+"%").Count(&count).Error
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%s-%04d", prefix, count+1), nil
}

// GetInvoiceItemsFromLogs 从日志表中聚合指定用户在指定时间段内的消费数据，按模型分组汇总
// 返回明细列表、总消耗额度和错误信息
func GetInvoiceItemsFromLogs(userId int, startTimestamp int64, endTimestamp int64) ([]InvoiceItem, int, error) {
	type AggResult struct {
		ModelName        string `gorm:"column:model_name"`
		RequestCount     int    `gorm:"column:request_count"`
		PromptTokens     int    `gorm:"column:prompt_tokens"`
		CompletionTokens int    `gorm:"column:completion_tokens"`
		Quota            int    `gorm:"column:quota"`
	}

	var results []AggResult
	err := LOG_DB.Table("logs").
		Select("model_name, COUNT(*) as request_count, COALESCE(SUM(prompt_tokens), 0) as prompt_tokens, COALESCE(SUM(completion_tokens), 0) as completion_tokens, COALESCE(SUM(quota), 0) as quota").
		Where("user_id = ? AND type = ? AND created_at >= ? AND created_at <= ?", userId, LogTypeConsume, startTimestamp, endTimestamp).
		Group("model_name").
		Order("quota DESC").
		Find(&results).Error
	if err != nil {
		return nil, 0, err
	}

	totalQuota := 0
	items := make([]InvoiceItem, 0, len(results))
	for _, r := range results {
		totalQuota += r.Quota
		items = append(items, InvoiceItem{
			ModelName:        r.ModelName,
			RequestCount:     r.RequestCount,
			PromptTokens:     r.PromptTokens,
			CompletionTokens: r.CompletionTokens,
			Quota:            r.Quota,
			Amount:           float64(r.Quota) / common.QuotaPerUnit,
		})
	}
	return items, totalQuota, nil
}

// IterateInvoiceLogDetails 分批遍历账单时间窗口内的逐条消费明细，避免一次性加载大量数据
func IterateInvoiceLogDetails(userId int, startTimestamp int64, endTimestamp int64, batchSize int, handler func(batch []InvoiceLogDetail) error) error {
	if batchSize <= 0 {
		batchSize = 1000
	}

	lastID := 0
	for {
		batch := make([]InvoiceLogDetail, 0, batchSize)
		err := LOG_DB.Table("logs").
			Select("id, created_at, model_name, token_name, prompt_tokens, completion_tokens, quota, content, other").
			Where("user_id = ? AND type = ? AND created_at >= ? AND created_at <= ? AND id > ?", userId, LogTypeConsume, startTimestamp, endTimestamp, lastID).
			Order("id ASC").
			Limit(batchSize).
			Find(&batch).Error
		if err != nil {
			return err
		}
		if len(batch) == 0 {
			return nil
		}

		for i := range batch {
			if batch[i].Other == "" {
				continue
			}
			otherMap, parseErr := common.StrToMap(batch[i].Other)
			if parseErr != nil || otherMap == nil {
				continue
			}
			if requestID, ok := otherMap["request_id"].(string); ok {
				batch[i].RequestId = requestID
			}
		}

		if err := handler(batch); err != nil {
			return err
		}

		lastID = batch[len(batch)-1].Id
	}
}

// CreateInvoice 创建账单记录
func CreateInvoice(invoice *Invoice) error {
	return DB.Create(invoice).Error
}

// GetInvoiceById 根据 ID 获取账单
func GetInvoiceById(id int) (*Invoice, error) {
	var invoice Invoice
	err := DB.Where("id = ?", id).First(&invoice).Error
	if err != nil {
		return nil, err
	}
	return &invoice, nil
}

// GetAllInvoices 获取所有账单列表，支持按用户名和时间范围筛选（管理员使用）
func GetAllInvoices(username string, startTimestamp int64, endTimestamp int64, startIdx int, num int) (invoices []*Invoice, total int64, err error) {
	tx := DB.Model(&Invoice{})
	if username != "" {
		tx = tx.Where("username = ?", username)
	}
	if startTimestamp != 0 {
		tx = tx.Where("created_at >= ?", startTimestamp)
	}
	if endTimestamp != 0 {
		tx = tx.Where("created_at <= ?", endTimestamp)
	}
	err = tx.Count(&total).Error
	if err != nil {
		return nil, 0, err
	}
	err = tx.Order("id DESC").Limit(num).Offset(startIdx).Find(&invoices).Error
	if err != nil {
		return nil, 0, err
	}
	return invoices, total, nil
}

// DeleteInvoice 根据 ID 删除账单
func DeleteInvoice(id int) error {
	return DB.Where("id = ?", id).Delete(&Invoice{}).Error
}

// GetItems 解析账单的 Items JSON 字段，返回按模型分组的明细列表
func (invoice *Invoice) GetItems() ([]InvoiceItem, error) {
	var items []InvoiceItem
	if invoice.Items == "" || invoice.Items == "null" {
		return items, nil
	}
	err := json.Unmarshal([]byte(invoice.Items), &items)
	return items, err
}
