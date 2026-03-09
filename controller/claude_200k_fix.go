package controller

import (
	"encoding/csv"
	"fmt"
	"strconv"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/model"

	"github.com/gin-gonic/gin"
)

func Claude200KFixScan(c *gin.Context) {
	page, _ := strconv.Atoi(c.DefaultQuery("p", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))
	startTimestamp, _ := strconv.ParseInt(c.Query("start_timestamp"), 10, 64)
	endTimestamp, _ := strconv.ParseInt(c.Query("end_timestamp"), 10, 64)
	username := c.Query("username")
	modelName := c.Query("model_name")
	channel, _ := strconv.Atoi(c.Query("channel"))

	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}

	logs, total, err := model.ScanClaudeLogs(startTimestamp, endTimestamp, username, modelName, channel, page, pageSize)
	if err != nil {
		common.ApiError(c, err)
		return
	}

	records := make([]*model.Claude200KFixRecord, 0, len(logs))
	for _, log := range logs {
		record := model.RecalcLogRecord(log)
		records = append(records, record)
	}

	common.ApiSuccess(c, gin.H{
		"records":   records,
		"total":     total,
		"page":      page,
		"page_size": pageSize,
	})
}

func Claude200KFixSummary(c *gin.Context) {
	startTimestamp, _ := strconv.ParseInt(c.Query("start_timestamp"), 10, 64)
	endTimestamp, _ := strconv.ParseInt(c.Query("end_timestamp"), 10, 64)
	username := c.Query("username")
	modelName := c.Query("model_name")
	channel, _ := strconv.Atoi(c.Query("channel"))

	batchSize := 500
	page := 1
	summary := &model.Claude200KFixSummary{
		UserDiffs:  make([]model.Claude200KFixUserDiff, 0),
		ModelDiffs: make([]model.Claude200KFixModelDiff, 0),
	}
	userDiffMap := make(map[int]*model.Claude200KFixUserDiff)
	modelDiffMap := make(map[string]*model.Claude200KFixModelDiff)

	for {
		logs, _, err := model.ScanClaudeLogs(startTimestamp, endTimestamp, username, modelName, channel, page, batchSize)
		if err != nil {
			common.ApiError(c, err)
			return
		}
		if len(logs) == 0 {
			break
		}

		for _, log := range logs {
			record := model.RecalcLogRecord(log)
			summary.TotalRecords++

			if !record.CanRecalc || record.QuotaDiff <= 0 {
				continue
			}

			summary.AffectedRecords++
			summary.TotalDiff += int64(record.QuotaDiff)

			if ud, ok := userDiffMap[log.UserId]; ok {
				ud.Count++
				ud.Diff += int64(record.QuotaDiff)
			} else {
				ud := &model.Claude200KFixUserDiff{
					UserId:   log.UserId,
					Username: log.Username,
					Count:    1,
					Diff:     int64(record.QuotaDiff),
				}
				userDiffMap[log.UserId] = ud
			}

			if md, ok := modelDiffMap[log.ModelName]; ok {
				md.Count++
				md.Diff += int64(record.QuotaDiff)
			} else {
				md := &model.Claude200KFixModelDiff{
					ModelName: log.ModelName,
					Count:     1,
					Diff:      int64(record.QuotaDiff),
				}
				modelDiffMap[log.ModelName] = md
			}
		}

		if len(logs) < batchSize {
			break
		}
		page++
	}

	for _, ud := range userDiffMap {
		summary.UserDiffs = append(summary.UserDiffs, *ud)
	}
	for _, md := range modelDiffMap {
		summary.ModelDiffs = append(summary.ModelDiffs, *md)
	}

	common.ApiSuccess(c, summary)
}

type claude200KFixApplyRequest struct {
	LogIds []int `json:"log_ids" binding:"required"`
}

func Claude200KFixApply(c *gin.Context) {
	var req claude200KFixApplyRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "invalid request: "+err.Error())
		return
	}

	if len(req.LogIds) == 0 {
		common.ApiErrorMsg(c, "no log IDs provided")
		return
	}

	if len(req.LogIds) > 1000 {
		common.ApiErrorMsg(c, "too many log IDs, max 1000")
		return
	}

	appliedCount, totalDiff, err := model.ApplyClaude200KFix(req.LogIds)
	if err != nil {
		common.ApiError(c, err)
		return
	}

	common.ApiSuccess(c, gin.H{
		"applied_count": appliedCount,
		"total_diff":    totalDiff,
	})
}

type claude200KFixIgnoreRequest struct {
	LogIds []int `json:"log_ids" binding:"required"`
}

func Claude200KFixIgnore(c *gin.Context) {
	var req claude200KFixIgnoreRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "invalid request: "+err.Error())
		return
	}

	if len(req.LogIds) == 0 {
		common.ApiErrorMsg(c, "no log IDs provided")
		return
	}

	if err := model.MarkLogsReviewed(req.LogIds); err != nil {
		common.ApiError(c, err)
		return
	}

	common.ApiSuccess(c, gin.H{
		"ignored_count": len(req.LogIds),
	})
}

func Claude200KFixExport(c *gin.Context) {
	startTimestamp, _ := strconv.ParseInt(c.Query("start_timestamp"), 10, 64)
	endTimestamp, _ := strconv.ParseInt(c.Query("end_timestamp"), 10, 64)
	username := c.Query("username")
	modelName := c.Query("model_name")
	channel, _ := strconv.Atoi(c.Query("channel"))

	c.Header("Content-Type", "text/csv; charset=utf-8")
	c.Header("Content-Disposition", "attachment; filename=claude_200k_fix_export.csv")
	c.Writer.Write([]byte{0xEF, 0xBB, 0xBF}) // UTF-8 BOM

	writer := csv.NewWriter(c.Writer)
	defer writer.Flush()

	writer.Write([]string{
		"Log ID", "User ID", "Username", "Model", "Prompt Tokens", "Completion Tokens",
		"Total Input", "Original Quota", "Correct Quota", "Diff",
		"Group Ratio", "Tier Range", "Native API", "Can Recalc", "Skip Reason",
		"Cache Tokens", "Cache Creation", "Cache Creation 5m", "Cache Creation 1h",
		"Created At",
	})

	batchSize := 500
	page := 1
	for {
		logs, _, err := model.ScanClaudeLogs(startTimestamp, endTimestamp, username, modelName, channel, page, batchSize)
		if err != nil {
			break
		}
		if len(logs) == 0 {
			break
		}

		for _, log := range logs {
			record := model.RecalcLogRecord(log)
			writer.Write([]string{
				strconv.Itoa(log.Id),
				strconv.Itoa(log.UserId),
				log.Username,
				log.ModelName,
				strconv.Itoa(log.PromptTokens),
				strconv.Itoa(log.CompletionTokens),
				strconv.Itoa(record.TotalInput),
				strconv.Itoa(log.Quota),
				strconv.Itoa(record.CorrectQuota),
				strconv.Itoa(record.QuotaDiff),
				fmt.Sprintf("%.2f", record.GroupRatio),
				record.TierRange,
				strconv.FormatBool(record.IsNativeAPI),
				strconv.FormatBool(record.CanRecalc),
				record.SkipReason,
				strconv.Itoa(record.CacheTokens),
				strconv.Itoa(record.CacheCreation),
				strconv.Itoa(record.CacheCreation5m),
				strconv.Itoa(record.CacheCreation1h),
				strconv.FormatInt(log.CreatedAt, 10),
			})
		}

		if len(logs) < batchSize {
			break
		}
		page++
	}
}
