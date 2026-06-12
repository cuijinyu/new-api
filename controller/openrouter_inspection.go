package controller

import (
	"context"
	"strconv"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/model"
	openrouterinspection "github.com/QuantumNous/new-api/service/openrouter_inspection"

	"github.com/gin-gonic/gin"
)

func OpenRouterInspectionFetchPrices(c *gin.Context) {
	ctx, cancel := context.WithTimeout(c.Request.Context(), 30*time.Second)
	defer cancel()
	result, err := openrouterinspection.FetchAndStorePriceSnapshots(ctx)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, result)
}

func OpenRouterInspectionRun(c *gin.Context) {
	var req openrouterinspection.RunRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "invalid request: "+err.Error())
		return
	}
	if req.TriggerType == "" {
		req.TriggerType = "manual"
	}
	result, err := openrouterinspection.RunInspection(c.Request.Context(), req)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, result)
}

func OpenRouterInspectionGetRuns(c *gin.Context) {
	pageInfo := common.GetPageQuery(c)
	startTime, _ := strconv.ParseInt(c.Query("start_time"), 10, 64)
	endTime, _ := strconv.ParseInt(c.Query("end_time"), 10, 64)
	status := c.Query("status")
	rows, total, err := model.GetOpenRouterInspectionRuns(startTime, endTime, status, pageInfo.GetPage(), pageInfo.GetPageSize())
	if err != nil {
		common.ApiError(c, err)
		return
	}
	pageInfo.SetTotal(int(total))
	pageInfo.SetItems(rows)
	common.ApiSuccess(c, pageInfo)
}

func OpenRouterInspectionGetItems(c *gin.Context) {
	pageInfo := common.GetPageQuery(c)
	runID, _ := strconv.ParseInt(c.Query("run_id"), 10, 64)
	channelID, _ := strconv.Atoi(c.Query("channel_id"))
	minDiffRate, _ := strconv.ParseFloat(c.Query("min_diff_rate"), 64)
	rows, total, err := model.GetOpenRouterInspectionItems(
		runID,
		channelID,
		c.Query("model_name"),
		c.Query("status"),
		c.Query("reason_code"),
		minDiffRate,
		pageInfo.GetPage(),
		pageInfo.GetPageSize(),
	)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	pageInfo.SetTotal(int(total))
	pageInfo.SetItems(rows)
	common.ApiSuccess(c, pageInfo)
}

func OpenRouterInspectionSummary(c *gin.Context) {
	var summary openrouterinspection.Summary
	runID, _ := strconv.ParseInt(c.Query("run_id"), 10, 64)
	tx := model.DB.Model(&model.OpenRouterInspectionItem{})
	if runID > 0 {
		tx = tx.Where("run_id = ?", runID)
	}
	var rows []struct {
		Status string
		Count  int
	}
	if err := tx.Select("status, COUNT(*) AS count").Group("status").Scan(&rows).Error; err != nil {
		common.ApiError(c, err)
		return
	}
	for _, row := range rows {
		summary.Total += row.Count
		switch row.Status {
		case openrouterinspection.StatusNormal:
			summary.Normal = row.Count
		case openrouterinspection.StatusWarning:
			summary.Warning = row.Count
		case openrouterinspection.StatusAbnormal:
			summary.Abnormal = row.Count
		case openrouterinspection.StatusCritical:
			summary.Critical = row.Count
		case openrouterinspection.StatusMissing:
			summary.Missing = row.Count
		case openrouterinspection.StatusUnsupported:
			summary.Unsupported = row.Count
		case openrouterinspection.StatusFailed:
			summary.Failed = row.Count
		}
	}
	common.ApiSuccess(c, summary)
}
