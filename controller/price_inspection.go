package controller

import (
	"context"
	"encoding/csv"
	"errors"
	"fmt"
	"strconv"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/model"
	priceinspection "github.com/QuantumNous/new-api/service/price_inspection"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

func PriceInspectionGetSources(c *gin.Context) {
	sources, err := priceinspection.ListPriceSources()
	if err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, gin.H{
		"count":   len(sources),
		"sources": sources,
	})
}

func PriceInspectionFetchSourcePrices(c *gin.Context) {
	provider := c.Param("provider")
	if provider == "" {
		provider = c.Query("source_provider")
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 30*time.Second)
	defer cancel()
	result, err := priceinspection.FetchSourcePrices(ctx, provider)
	if err != nil {
		if errors.Is(err, priceinspection.ErrPriceSourceUnsupported) {
			common.ApiErrorMsg(c, err.Error())
			return
		}
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, result)
}

func PriceInspectionGetSnapshots(c *gin.Context) {
	pageInfo := common.GetPageQuery(c)
	fetchedStart, _ := strconv.ParseInt(c.Query("fetched_start"), 10, 64)
	fetchedEnd, _ := strconv.ParseInt(c.Query("fetched_end"), 10, 64)
	rows, total, err := priceinspection.GetPriceSnapshots(priceinspection.SnapshotQuery{
		SourceProvider: c.DefaultQuery("source_provider", priceinspection.ProviderOpenRouter),
		ModelID:        c.Query("model_id"),
		LocalModelName: c.Query("local_model_name"),
		FetchedStart:   fetchedStart,
		FetchedEnd:     fetchedEnd,
		Page:           pageInfo.GetPage(),
		PageSize:       pageInfo.GetPageSize(),
	})
	if err != nil {
		if errors.Is(err, priceinspection.ErrPriceSourceUnsupported) {
			common.ApiErrorMsg(c, err.Error())
			return
		}
		common.ApiError(c, err)
		return
	}
	pageInfo.SetTotal(int(total))
	pageInfo.SetItems(rows)
	common.ApiSuccess(c, pageInfo)
}

func PriceInspectionCreateSnapshot(c *gin.Context) {
	var req priceinspection.SnapshotMutationRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "invalid request: "+err.Error())
		return
	}
	snapshot, err := priceinspection.CreatePriceSnapshot(req)
	if err != nil {
		common.ApiErrorMsg(c, err.Error())
		return
	}
	common.ApiSuccess(c, snapshot)
}

func PriceInspectionCreateSnapshots(c *gin.Context) {
	var req priceinspection.SnapshotBatchRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "invalid request: "+err.Error())
		return
	}
	result, err := priceinspection.CreatePriceSnapshots(req)
	if err != nil {
		common.ApiErrorMsg(c, err.Error())
		return
	}
	common.ApiSuccess(c, result)
}

func PriceInspectionDeleteSnapshot(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	if err := priceinspection.DeletePriceSnapshot(id); err != nil {
		common.ApiErrorMsg(c, err.Error())
		return
	}
	common.ApiSuccess(c, gin.H{"id": id})
}

func PriceInspectionGenerateCoverage(c *gin.Context) {
	var req priceinspection.GenerateCoverageRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "invalid request: "+err.Error())
		return
	}
	result, err := priceinspection.GenerateCoverage(req)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, result)
}

func PriceInspectionRun(c *gin.Context) {
	var req priceinspection.RunRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "invalid request: "+err.Error())
		return
	}
	result, err := priceinspection.RunInspection(req)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, result)
}

func PriceInspectionGetCoverage(c *gin.Context) {
	pageInfo := common.GetPageQuery(c)
	sourceProvider := c.DefaultQuery("source_provider", priceinspection.ProviderOpenRouter)
	channelType, _ := strconv.Atoi(c.Query("channel_type"))
	generatedAt, _ := strconv.ParseInt(c.Query("generated_at"), 10, 64)
	if generatedAt == 0 {
		var err error
		generatedAt, err = model.GetLatestPriceInspectionCoverageGeneratedAt(sourceProvider)
		if err != nil {
			common.ApiError(c, err)
			return
		}
	}
	rows, total, err := model.GetPriceInspectionCoverageReports(
		sourceProvider,
		c.Query("mapping_status"),
		c.Query("calculator_status"),
		c.Query("support_level"),
		c.Query("reason_code"),
		c.Query("model_name"),
		channelType,
		generatedAt,
		pageInfo.GetPage(),
		pageInfo.GetPageSize(),
	)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	pageInfo.SetTotal(int(total))
	pageInfo.SetItems(rows)
	common.ApiSuccess(c, gin.H{
		"generated_at": generatedAt,
		"page":         pageInfo,
	})
}

func PriceInspectionExportCoverage(c *gin.Context) {
	sourceProvider := c.DefaultQuery("source_provider", priceinspection.ProviderOpenRouter)
	channelType, _ := strconv.Atoi(c.Query("channel_type"))
	generatedAt, _ := strconv.ParseInt(c.Query("generated_at"), 10, 64)
	if generatedAt == 0 {
		var err error
		generatedAt, err = model.GetLatestPriceInspectionCoverageGeneratedAt(sourceProvider)
		if err != nil {
			common.ApiError(c, err)
			return
		}
	}
	limit := priceInspectionExportLimit(c)
	rows, _, err := model.GetPriceInspectionCoverageReports(
		sourceProvider,
		c.Query("mapping_status"),
		c.Query("calculator_status"),
		c.Query("support_level"),
		c.Query("reason_code"),
		c.Query("model_name"),
		channelType,
		generatedAt,
		1,
		limit,
	)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	writePriceInspectionCoverageCSV(c, rows)
}

func PriceInspectionCoverageSummary(c *gin.Context) {
	sourceProvider := c.DefaultQuery("source_provider", priceinspection.ProviderOpenRouter)
	generatedAt, _ := strconv.ParseInt(c.Query("generated_at"), 10, 64)
	if generatedAt == 0 {
		var err error
		generatedAt, err = model.GetLatestPriceInspectionCoverageGeneratedAt(sourceProvider)
		if err != nil {
			common.ApiError(c, err)
			return
		}
	}
	type countRow struct {
		Key   string `json:"key" gorm:"column:item_key"`
		Count int    `json:"count"`
	}
	summary := gin.H{
		"generated_at": generatedAt,
		"total":        0,
		"by_support":   []countRow{},
		"by_reason":    []countRow{},
		"by_scenario":  []countRow{},
	}
	base := func() *gorm.DB {
		return model.DB.Model(&model.PriceInspectionCoverageReport{}).Where("source_provider = ? AND generated_at = ?", sourceProvider, generatedAt)
	}
	var total int64
	if err := base().Count(&total).Error; err != nil {
		common.ApiError(c, err)
		return
	}
	summary["total"] = total

	var supportRows []countRow
	if err := base().Select("support_level AS item_key, COUNT(*) AS count").Group("support_level").Scan(&supportRows).Error; err != nil {
		common.ApiError(c, err)
		return
	}
	var reasonRows []countRow
	if err := base().Select("reason_code AS item_key, COUNT(*) AS count").Group("reason_code").Scan(&reasonRows).Error; err != nil {
		common.ApiError(c, err)
		return
	}
	var scenarioRows []countRow
	if err := base().Select("scenario AS item_key, COUNT(*) AS count").Group("scenario").Scan(&scenarioRows).Error; err != nil {
		common.ApiError(c, err)
		return
	}
	summary["by_support"] = supportRows
	summary["by_reason"] = reasonRows
	summary["by_scenario"] = scenarioRows
	common.ApiSuccess(c, summary)
}

func PriceInspectionGetRuns(c *gin.Context) {
	pageInfo := common.GetPageQuery(c)
	channelID, _ := strconv.Atoi(c.Query("channel_id"))
	channelType, _ := strconv.Atoi(c.Query("channel_type"))
	startTime, _ := strconv.ParseInt(c.Query("start_time"), 10, 64)
	endTime, _ := strconv.ParseInt(c.Query("end_time"), 10, 64)
	rows, total, err := model.GetPriceInspectionRuns(
		c.Query("source_provider"),
		c.Query("status"),
		c.Query("model_name"),
		channelID,
		channelType,
		startTime,
		endTime,
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

func PriceInspectionGetItems(c *gin.Context) {
	pageInfo := common.GetPageQuery(c)
	runID, _ := strconv.ParseInt(c.Query("run_id"), 10, 64)
	channelID, _ := strconv.Atoi(c.Query("channel_id"))
	channelType, _ := strconv.Atoi(c.Query("channel_type"))
	minDiffRate, _ := strconv.ParseFloat(c.Query("min_diff_rate"), 64)
	rows, total, err := model.GetPriceInspectionItems(
		runID,
		c.Query("source_provider"),
		c.Query("model_name"),
		c.Query("status"),
		c.Query("support_level"),
		c.Query("reason_code"),
		channelID,
		channelType,
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

func PriceInspectionExportItems(c *gin.Context) {
	runID, _ := strconv.ParseInt(c.Query("run_id"), 10, 64)
	channelID, _ := strconv.Atoi(c.Query("channel_id"))
	channelType, _ := strconv.Atoi(c.Query("channel_type"))
	minDiffRate, _ := strconv.ParseFloat(c.Query("min_diff_rate"), 64)
	limit := priceInspectionExportLimit(c)
	rows, _, err := model.GetPriceInspectionItems(
		runID,
		c.Query("source_provider"),
		c.Query("model_name"),
		c.Query("status"),
		c.Query("support_level"),
		c.Query("reason_code"),
		channelID,
		channelType,
		minDiffRate,
		1,
		limit,
	)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	writePriceInspectionItemsCSV(c, rows)
}

func PriceInspectionGetIssues(c *gin.Context) {
	pageInfo := common.GetPageQuery(c)
	channelID, _ := strconv.Atoi(c.Query("channel_id"))
	channelType, _ := strconv.Atoi(c.Query("channel_type"))
	minDiffRate, _ := strconv.ParseFloat(c.Query("min_diff_rate"), 64)
	startTime, _ := strconv.ParseInt(c.Query("start_time"), 10, 64)
	endTime, _ := strconv.ParseInt(c.Query("end_time"), 10, 64)
	rows, total, err := model.GetPriceInspectionIssueGroups(
		c.Query("source_provider"),
		c.Query("model_name"),
		c.Query("status"),
		c.Query("support_level"),
		c.Query("reason_code"),
		c.DefaultQuery("resolution_status", "active"),
		channelID,
		channelType,
		minDiffRate,
		startTime,
		endTime,
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

func PriceInspectionExportIssues(c *gin.Context) {
	channelID, _ := strconv.Atoi(c.Query("channel_id"))
	channelType, _ := strconv.Atoi(c.Query("channel_type"))
	minDiffRate, _ := strconv.ParseFloat(c.Query("min_diff_rate"), 64)
	startTime, _ := strconv.ParseInt(c.Query("start_time"), 10, 64)
	endTime, _ := strconv.ParseInt(c.Query("end_time"), 10, 64)
	limit := priceInspectionExportLimit(c)
	rows, _, err := model.GetPriceInspectionIssueGroups(
		c.Query("source_provider"),
		c.Query("model_name"),
		c.Query("status"),
		c.Query("support_level"),
		c.Query("reason_code"),
		c.DefaultQuery("resolution_status", "active"),
		channelID,
		channelType,
		minDiffRate,
		startTime,
		endTime,
		1,
		limit,
	)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	writePriceInspectionIssuesCSV(c, rows)
}

func priceInspectionExportLimit(c *gin.Context) int {
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "10000"))
	if limit <= 0 {
		return 10000
	}
	if limit > 50000 {
		return 50000
	}
	return limit
}

func writePriceInspectionItemsCSV(c *gin.Context, rows []model.PriceInspectionItem) {
	priceInspectionCSVHeader(c, "price_inspection_items")
	writer := csv.NewWriter(c.Writer)
	_, _ = c.Writer.Write([]byte{0xEF, 0xBB, 0xBF})
	_ = writer.Write([]string{
		"log_id",
		"run_id",
		"log_created_at",
		"source_provider",
		"channel_id",
		"channel_type",
		"model_name",
		"source_model_id",
		"canonical_model_id",
		"scenario",
		"support_level",
		"status",
		"reason_code",
		"actual_quota",
		"expected_quota",
		"delta_quota",
		"diff_rate",
		"actual_usd",
		"expected_usd",
		"price_snapshot_id",
		"reason_detail",
		"billing_context_json",
		"calculator_trace_json",
	})
	for _, row := range rows {
		_ = writer.Write([]string{
			strconv.FormatInt(row.LogID, 10),
			strconv.FormatInt(row.RunID, 10),
			strconv.FormatInt(row.LogCreatedAt, 10),
			row.SourceProvider,
			strconv.Itoa(row.ChannelID),
			strconv.Itoa(row.ChannelType),
			row.ModelName,
			row.SourceModelID,
			row.CanonicalModelID,
			row.Scenario,
			row.SupportLevel,
			row.Status,
			row.ReasonCode,
			strconv.FormatInt(row.ActualQuota, 10),
			strconv.FormatInt(row.ExpectedQuota, 10),
			strconv.FormatInt(row.DeltaQuota, 10),
			strconv.FormatFloat(row.DiffRate, 'f', 8, 64),
			strconv.FormatFloat(row.ActualUSD, 'f', 12, 64),
			strconv.FormatFloat(row.ExpectedUSD, 'f', 12, 64),
			strconv.FormatInt(row.PriceSnapshotID, 10),
			row.ReasonDetail,
			row.BillingContextJSON,
			row.CalculatorTraceJSON,
		})
	}
	writer.Flush()
}

func writePriceInspectionCoverageCSV(c *gin.Context, rows []model.PriceInspectionCoverageReport) {
	priceInspectionCSVHeader(c, "price_inspection_coverage")
	writer := csv.NewWriter(c.Writer)
	_, _ = c.Writer.Write([]byte{0xEF, 0xBB, 0xBF})
	_ = writer.Write([]string{
		"generated_at",
		"source_provider",
		"channel_type",
		"channel_type_name",
		"model_name",
		"scenario",
		"mapping_status",
		"calculator_status",
		"log_context_status",
		"support_level",
		"reason_code",
		"source_model_id",
		"canonical_model_id",
		"channel_count",
		"sample_log_count",
		"last_seen_at",
		"suggestion",
		"raw_json",
	})
	for _, row := range rows {
		_ = writer.Write([]string{
			strconv.FormatInt(row.GeneratedAt, 10),
			row.SourceProvider,
			strconv.Itoa(row.ChannelType),
			row.ChannelTypeName,
			row.ModelName,
			row.Scenario,
			row.MappingStatus,
			row.CalculatorStatus,
			row.LogContextStatus,
			row.SupportLevel,
			row.ReasonCode,
			row.SourceModelID,
			row.CanonicalModelID,
			strconv.Itoa(row.ChannelCount),
			strconv.FormatInt(row.SampleLogCount, 10),
			strconv.FormatInt(row.LastSeenAt, 10),
			row.Suggestion,
			row.RawJSON,
		})
	}
	writer.Flush()
}

func writePriceInspectionIssuesCSV(c *gin.Context, rows []model.PriceInspectionIssueGroup) {
	priceInspectionCSVHeader(c, "price_inspection_issues")
	writer := csv.NewWriter(c.Writer)
	_, _ = c.Writer.Write([]byte{0xEF, 0xBB, 0xBF})
	_ = writer.Write([]string{
		"source_provider",
		"model_name",
		"channel_id",
		"channel_type",
		"status",
		"support_level",
		"reason_code",
		"resolution_status",
		"resolution_owner",
		"resolution_updated_by",
		"resolution_updated_at",
		"count",
		"sample_log_id",
		"latest_log_at",
		"total_actual_quota",
		"total_expected_quota",
		"total_delta_quota",
		"max_abs_delta_quota",
		"max_diff_rate",
	})
	for _, row := range rows {
		_ = writer.Write([]string{
			row.SourceProvider,
			row.ModelName,
			strconv.Itoa(row.ChannelID),
			strconv.Itoa(row.ChannelType),
			row.Status,
			row.SupportLevel,
			row.ReasonCode,
			row.ResolutionStatus,
			row.ResolutionOwner,
			row.ResolutionUpdatedBy,
			strconv.FormatInt(row.ResolutionUpdatedAt, 10),
			strconv.FormatInt(row.Count, 10),
			strconv.FormatInt(row.SampleLogID, 10),
			strconv.FormatInt(row.LatestLogAt, 10),
			strconv.FormatInt(row.TotalActualQuota, 10),
			strconv.FormatInt(row.TotalExpectedQuota, 10),
			strconv.FormatInt(row.TotalDeltaQuota, 10),
			strconv.FormatInt(row.MaxAbsDeltaQuota, 10),
			strconv.FormatFloat(row.MaxDiffRate, 'f', 8, 64),
		})
	}
	writer.Flush()
}

func priceInspectionCSVHeader(c *gin.Context, prefix string) {
	filename := fmt.Sprintf("%s_%d.csv", prefix, time.Now().Unix())
	c.Header("Content-Type", "text/csv; charset=utf-8")
	c.Header("Content-Disposition", fmt.Sprintf("attachment; filename=%s", filename))
}

type priceInspectionIssueResolutionRequest struct {
	SourceProvider   string `json:"source_provider"`
	ModelName        string `json:"model_name"`
	ChannelID        int    `json:"channel_id"`
	ChannelType      int    `json:"channel_type"`
	Status           string `json:"status"`
	SupportLevel     string `json:"support_level"`
	ReasonCode       string `json:"reason_code"`
	ResolutionStatus string `json:"resolution_status"`
	Note             string `json:"note"`
	Owner            string `json:"owner"`
	ExpireAt         int64  `json:"expire_at"`
}

func PriceInspectionUpdateIssueResolution(c *gin.Context) {
	var req priceInspectionIssueResolutionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "invalid request: "+err.Error())
		return
	}
	resolutionStatus := model.NormalizePriceInspectionResolutionStatus(req.ResolutionStatus)
	if resolutionStatus == "" {
		common.ApiErrorMsg(c, "invalid resolution_status")
		return
	}
	if req.SourceProvider == "" || req.ModelName == "" || req.Status == "" || req.SupportLevel == "" || req.ReasonCode == "" {
		common.ApiErrorMsg(c, "source_provider, model_name, status, support_level and reason_code are required")
		return
	}
	resolution := &model.PriceInspectionIssueResolution{
		SourceProvider:   req.SourceProvider,
		ModelName:        req.ModelName,
		ChannelID:        req.ChannelID,
		ChannelType:      req.ChannelType,
		Status:           req.Status,
		SupportLevel:     req.SupportLevel,
		ReasonCode:       req.ReasonCode,
		ResolutionStatus: resolutionStatus,
		Note:             req.Note,
		Owner:            req.Owner,
		ExpireAt:         req.ExpireAt,
		UpdatedBy:        c.GetString("username"),
	}
	if err := model.UpsertPriceInspectionIssueResolution(resolution); err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, resolution)
}

func PriceInspectionSummary(c *gin.Context) {
	runID, _ := strconv.ParseInt(c.Query("run_id"), 10, 64)
	sourceProvider := c.Query("source_provider")
	type countRow struct {
		Key   string `json:"key"`
		Count int    `json:"count"`
	}
	base := func() *gorm.DB {
		tx := model.DB.Model(&model.PriceInspectionItem{})
		if runID > 0 {
			tx = tx.Where("run_id = ?", runID)
		}
		if sourceProvider != "" {
			tx = tx.Where("source_provider = ?", sourceProvider)
		}
		return tx
	}
	summary := gin.H{
		"total":      0,
		"by_status":  []countRow{},
		"by_reason":  []countRow{},
		"by_support": []countRow{},
	}
	var total int64
	if err := base().Count(&total).Error; err != nil {
		common.ApiError(c, err)
		return
	}
	summary["total"] = total
	var statusRows []countRow
	if err := base().Select("status AS `key`, COUNT(*) AS count").Group("status").Scan(&statusRows).Error; err != nil {
		common.ApiError(c, err)
		return
	}
	var reasonRows []countRow
	if err := base().Select("reason_code AS `key`, COUNT(*) AS count").Group("reason_code").Scan(&reasonRows).Error; err != nil {
		common.ApiError(c, err)
		return
	}
	var supportRows []countRow
	if err := base().Select("support_level AS `key`, COUNT(*) AS count").Group("support_level").Scan(&supportRows).Error; err != nil {
		common.ApiError(c, err)
		return
	}
	summary["by_status"] = statusRows
	summary["by_reason"] = reasonRows
	summary["by_support"] = supportRows
	common.ApiSuccess(c, summary)
}

func PriceInspectionGetModelMappings(c *gin.Context) {
	pageInfo := common.GetPageQuery(c)
	channelType, _ := strconv.Atoi(c.Query("channel_type"))
	var enabled *bool
	if c.Query("enabled") != "" {
		value, err := strconv.ParseBool(c.Query("enabled"))
		if err != nil {
			common.ApiErrorMsg(c, "invalid enabled value")
			return
		}
		enabled = &value
	}
	rows, total, err := model.GetPriceModelMappings(
		c.DefaultQuery("source_provider", priceinspection.ProviderOpenRouter),
		c.Query("local_model_name"),
		channelType,
		enabled,
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

func PriceInspectionCreateModelMapping(c *gin.Context) {
	var req priceinspection.MappingRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "invalid request: "+err.Error())
		return
	}
	mapping, err := priceinspection.CreateMapping(req)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, mapping)
}

func PriceInspectionUpdateModelMapping(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil || id <= 0 {
		common.ApiErrorMsg(c, "invalid mapping id")
		return
	}
	var req priceinspection.MappingRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "invalid request: "+err.Error())
		return
	}
	mapping, err := priceinspection.UpdateMapping(id, req)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, mapping)
}

func PriceInspectionSuggestModelMappings(c *gin.Context) {
	var req priceinspection.SuggestMappingsRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "invalid request: "+err.Error())
		return
	}
	suggestions, err := priceinspection.SuggestMappings(req)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, gin.H{
		"count":       len(suggestions),
		"suggestions": suggestions,
	})
}
