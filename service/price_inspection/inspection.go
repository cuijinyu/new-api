package price_inspection

import (
	"context"
	"encoding/json"
	"errors"
	"math"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/constant"
	"github.com/QuantumNous/new-api/model"
)

const (
	StatusNormal      = "normal"
	StatusWarning     = "warning"
	StatusAbnormal    = "abnormal"
	StatusCritical    = "critical"
	StatusMissing     = "missing"
	StatusUnsupported = "unsupported"
	StatusOutOfScope  = "out_of_scope"
	StatusFailed      = "failed"

	SupportExact = "exact"
)

type RunRequest struct {
	WindowStart    int64  `json:"window_start"`
	WindowEnd      int64  `json:"window_end"`
	SourceProvider string `json:"source_provider"`
	ChannelID      int    `json:"channel_id"`
	ChannelType    int    `json:"channel_type"`
	ModelName      string `json:"model_name"`
	Limit          int    `json:"limit"`
	TriggerType    string `json:"trigger_type"`
	IncludeLegacy  bool   `json:"include_legacy"`
}

type RunResult struct {
	RunID                   int64 `json:"run_id"`
	TotalLogs               int   `json:"total_logs"`
	CheckedLogs             int   `json:"checked_logs"`
	NormalCount             int   `json:"normal_count"`
	WarningCount            int   `json:"warning_count"`
	AbnormalCount           int   `json:"abnormal_count"`
	CriticalCount           int   `json:"critical_count"`
	MissingCount            int   `json:"missing_count"`
	UnsupportedCount        int   `json:"unsupported_count"`
	OutOfScopeCount         int   `json:"out_of_scope_count"`
	FailedCount             int   `json:"failed_count"`
	SkippedNoBillingContext int   `json:"skipped_no_billing_context"`
}

type ScheduleOptions struct {
	IntervalMinutes int
	WindowMinutes   int
	DelayMinutes    int
	Limit           int
	SourceProviders []string
	IncludeLegacy   bool
}

type quotaClassificationThresholds struct {
	AbsoluteToleranceQuota  int64
	SmallExpectedQuota      int64
	SmallExpectedTolerance  int64
	MediumExpectedQuota     int64
	MediumExpectedTolerance int64
	NormalDiffRate          float64
	WarningDiffRate         float64
	AbnormalDiffRate        float64
}

func RunInspection(req RunRequest) (*RunResult, error) {
	req.SourceProvider = normalizeProvider(req.SourceProvider)
	if req.WindowEnd <= 0 {
		req.WindowEnd = time.Now().Add(-5 * time.Minute).Unix()
	}
	if req.WindowStart <= 0 {
		req.WindowStart = req.WindowEnd - 30*60
	}
	if req.WindowEnd < req.WindowStart {
		return nil, errors.New("window_end cannot be earlier than window_start")
	}
	if req.Limit <= 0 {
		req.Limit = 1000
	}
	if req.TriggerType == "" {
		req.TriggerType = "manual"
	}

	run := &model.PriceInspectionRun{
		SourceProvider: runSourceProvider(req.SourceProvider),
		Status:         "running",
		TriggerType:    req.TriggerType,
		ChannelID:      req.ChannelID,
		ChannelType:    req.ChannelType,
		ModelName:      req.ModelName,
		WindowStart:    req.WindowStart,
		WindowEnd:      req.WindowEnd,
		StartedAt:      time.Now().Unix(),
	}
	if err := model.CreatePriceInspectionRun(run); err != nil {
		return nil, err
	}

	logs, channelTypes, err := scanInspectionLogs(req)
	if err != nil {
		run.Status = StatusFailed
		run.FinishedAt = time.Now().Unix()
		run.SummaryJSON = common.GetJsonString(map[string]any{"error": err.Error()})
		_ = model.UpdatePriceInspectionRun(run)
		return nil, err
	}

	result := &RunResult{RunID: run.ID}
	items := make([]model.PriceInspectionItem, 0, len(logs))
	for _, logRow := range logs {
		item, ok := inspectGenericLog(run.ID, logRow, channelTypes[logRow.ChannelId], req)
		if !ok {
			result.SkippedNoBillingContext++
			continue
		}
		items = append(items, item)
		result.TotalLogs++
		accumulateRunResult(result, item.Status)
		if item.Status != StatusFailed {
			result.CheckedLogs++
		}
	}
	if err := model.InsertPriceInspectionItems(items); err != nil {
		run.Status = StatusFailed
		run.FinishedAt = time.Now().Unix()
		run.SummaryJSON = common.GetJsonString(map[string]any{"error": err.Error()})
		_ = model.UpdatePriceInspectionRun(run)
		return nil, err
	}

	run.Status = runStatusFromResult(result)
	run.FinishedAt = time.Now().Unix()
	run.TotalLogs = result.TotalLogs
	run.CheckedLogs = result.CheckedLogs
	run.NormalCount = result.NormalCount
	run.WarningCount = result.WarningCount
	run.AbnormalCount = result.AbnormalCount
	run.CriticalCount = result.CriticalCount
	run.MissingCount = result.MissingCount
	run.UnsupportedCount = result.UnsupportedCount
	run.OutOfScopeCount = result.OutOfScopeCount
	run.FailedCount = result.FailedCount
	run.SummaryJSON = common.GetJsonString(result)
	if err := model.UpdatePriceInspectionRun(run); err != nil {
		return nil, err
	}
	return result, nil
}

func StartScheduledWorker(ctx context.Context, opts ScheduleOptions) {
	if opts.IntervalMinutes <= 0 {
		opts.IntervalMinutes = 15
	}
	if opts.WindowMinutes <= 0 {
		opts.WindowMinutes = 30
	}
	if opts.DelayMinutes < 0 {
		opts.DelayMinutes = 5
	}
	if opts.Limit <= 0 {
		opts.Limit = 5000
	}
	if len(opts.SourceProviders) == 0 {
		opts.SourceProviders = DefaultScheduledSourceProviders()
	}
	ticker := time.NewTicker(time.Duration(opts.IntervalMinutes) * time.Minute)
	go func() {
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				runScheduledInspection(opts)
			}
		}
	}()
}

func DefaultScheduledSourceProviders() []string {
	return []string{ProviderOpenRouter, "openai", "anthropic", "google", "azure"}
}

func runScheduledInspection(opts ScheduleOptions) {
	windowEnd := time.Now().Add(-time.Duration(opts.DelayMinutes) * time.Minute).Unix()
	windowStart := windowEnd - int64(opts.WindowMinutes*60)
	for _, provider := range opts.SourceProviders {
		provider = normalizeProvider(provider)
		if provider == "" {
			continue
		}
		_, err := RunInspection(RunRequest{
			WindowStart:    windowStart,
			WindowEnd:      windowEnd,
			SourceProvider: provider,
			Limit:          opts.Limit,
			TriggerType:    "scheduled",
			IncludeLegacy:  opts.IncludeLegacy,
		})
		if err != nil {
			common.SysError("price inspection failed for " + provider + ": " + err.Error())
		}
	}
}

func scanInspectionLogs(req RunRequest) ([]model.Log, map[int]int, error) {
	tx := model.LOG_DB.Where("type = ? AND created_at >= ? AND created_at <= ?", model.LogTypeConsume, req.WindowStart, req.WindowEnd)
	if !req.IncludeLegacy {
		tx = tx.Where("(other LIKE ? OR other LIKE ? OR other LIKE ?)", "%\"billing\"%", "%\"provider_usage_cost\"%", "%\"openrouter_cost\"%")
	}
	if req.ChannelID > 0 {
		tx = tx.Where("channel_id = ?", req.ChannelID)
	} else {
		channelIDs, err := channelIDsForRun(req)
		if err != nil {
			return nil, nil, err
		}
		if len(channelIDs) > 0 {
			tx = tx.Where("channel_id IN ?", channelIDs)
		}
	}
	if req.ModelName != "" {
		tx = tx.Where("model_name = ?", req.ModelName)
	}
	var logs []model.Log
	if err := tx.Order("created_at ASC, id ASC").Limit(req.Limit).Find(&logs).Error; err != nil {
		return nil, nil, err
	}
	channelTypes, err := loadChannelTypes(logs)
	return logs, channelTypes, err
}

func channelIDsForRun(req RunRequest) ([]int, error) {
	tx := model.DB.Model(&model.Channel{})
	if req.ChannelType > 0 {
		tx = tx.Where("type = ?", req.ChannelType)
	} else if req.SourceProvider != "" {
		types := channelTypesForProvider(req.SourceProvider)
		if len(types) > 0 {
			tx = tx.Where("type IN ?", types)
		}
	}
	var ids []int
	if err := tx.Pluck("id", &ids).Error; err != nil {
		return nil, err
	}
	return ids, nil
}

func loadChannelTypes(logs []model.Log) (map[int]int, error) {
	out := map[int]int{}
	if len(logs) == 0 {
		return out, nil
	}
	idsSet := map[int]bool{}
	var ids []int
	for _, logRow := range logs {
		if logRow.ChannelId > 0 && !idsSet[logRow.ChannelId] {
			idsSet[logRow.ChannelId] = true
			ids = append(ids, logRow.ChannelId)
		}
	}
	if len(ids) == 0 {
		return out, nil
	}
	var rows []struct {
		ID   int `gorm:"column:id"`
		Type int `gorm:"column:type"`
	}
	if err := model.DB.Model(&model.Channel{}).Select("id, type").Where("id IN ?", ids).Scan(&rows).Error; err != nil {
		return nil, err
	}
	for _, row := range rows {
		out[row.ID] = row.Type
	}
	return out, nil
}

func inspectGenericLog(runID int64, logRow model.Log, channelType int, req RunRequest) (model.PriceInspectionItem, bool) {
	other := parseJSONMap(logRow.Other)
	billing := nestedMap(other, "billing")
	if len(billing) == 0 && !req.IncludeLegacy && !hasProviderCostContext(billing, other) {
		return model.PriceInspectionItem{}, false
	}
	sourceProvider := stringFromMaps("source_provider", billing, other)
	sourceProvider = normalizeProvider(sourceProvider)
	if sourceProvider == "" {
		sourceProvider = req.SourceProvider
	}
	if req.SourceProvider != "" && sourceProvider != "" && sourceProvider != req.SourceProvider {
		return model.PriceInspectionItem{}, false
	}
	scenario := stringFromMaps("scenario", billing, other)
	if scenario == "" {
		scenario = detectScenario(channelType, logRow.ModelName)
	}
	item := model.PriceInspectionItem{
		RunID:              runID,
		LogID:              int64(logRow.Id),
		LogCreatedAt:       logRow.CreatedAt,
		ChannelID:          logRow.ChannelId,
		ChannelType:        channelType,
		SourceProvider:     sourceProvider,
		ModelName:          logRow.ModelName,
		SourceModelID:      stringFromMaps("provider_model_id", billing, other),
		CanonicalModelID:   stringFromMaps("canonical_model_id", billing, other),
		Scenario:           scenario,
		ActualQuota:        int64(logRow.Quota),
		ActualUSD:          float64(logRow.Quota) / common.QuotaPerUnit,
		BillingContextJSON: common.MapToJsonStr(billingContextForItem(other, billing)),
	}
	if item.SourceProvider == "" {
		item.SourceProvider = "unknown"
	}
	if item.CanonicalModelID == "" {
		item.CanonicalModelID = item.SourceModelID
	}
	if item.SourceModelID == "" {
		item.SourceModelID = stringFromMaps("openrouter_model_id", billing, other)
	}
	if isScenarioOutOfScope(scenario) {
		item.Status = StatusOutOfScope
		item.SupportLevel = SupportOutOfScope
		item.ReasonCode = reasonForOutOfScopeScenario(scenario)
		return item, true
	}
	cost, ok := optionalFloatFromMaps("provider_usage_cost", billing, other)
	if !ok {
		cost, ok = optionalFloatFromMaps("openrouter_cost", billing, other)
	}
	if !ok {
		if snapshot, reason, detail := calculateSnapshotBillingQuota(logRow, channelType, item, billing, other); reason == "" {
			item.PriceSnapshotID = snapshot.snapshotID
			item.SourceModelID = firstNonEmpty(item.SourceModelID, snapshot.sourceModelID)
			item.CanonicalModelID = firstNonEmpty(item.CanonicalModelID, snapshot.canonicalModelID)
			item.ExpectedQuota = snapshot.expectedQuota
			item.ExpectedUSD = float64(snapshot.expectedQuota) / common.QuotaPerUnit
			item.DeltaQuota = item.ActualQuota - item.ExpectedQuota
			item.Status, item.ReasonCode, item.DiffRate = classifyQuota(item.ActualQuota, item.ExpectedQuota)
			item.SupportLevel = SupportStandard
			item.CalculatorTraceJSON = common.MapToJsonStr(snapshot.trace)
			return item, true
		} else if reason != "missing_price_snapshot" {
			item.CalculatorTraceJSON = common.MapToJsonStr(map[string]any{
				"calculator": "price_source_snapshot",
				"reason":     reason,
				"detail":     detail,
			})
		}
		standard, reason, detail := calculateStandardBillingQuota(logRow, billing, other)
		if reason != "" {
			item.Status = StatusMissing
			item.SupportLevel = SupportUnsupported
			item.ReasonCode = reason
			item.ReasonDetail = detail
			return item, true
		}
		item.ExpectedQuota = standard.expectedQuota
		item.ExpectedUSD = float64(standard.expectedQuota) / common.QuotaPerUnit
		item.DeltaQuota = item.ActualQuota - item.ExpectedQuota
		item.Status, item.ReasonCode, item.DiffRate = classifyQuota(item.ActualQuota, item.ExpectedQuota)
		item.SupportLevel = SupportStandard
		item.CalculatorTraceJSON = common.MapToJsonStr(standard.trace)
		return item, true
	}
	groupRatio := floatFromMapsDefault("group_ratio", 1, billing, other)
	condMultiplier := floatFromMapsDefault("cond_multiplier", 1, billing, other)
	if groupRatio <= 0 {
		groupRatio = 1
	}
	if condMultiplier <= 0 {
		condMultiplier = 1
	}
	item.ExpectedUSD = cost * groupRatio * condMultiplier
	item.ExpectedQuota = int64(math.Round(item.ExpectedUSD * common.QuotaPerUnit))
	item.DeltaQuota = item.ActualQuota - item.ExpectedQuota
	item.Status, item.ReasonCode, item.DiffRate = classifyQuota(item.ActualQuota, item.ExpectedQuota)
	item.SupportLevel = SupportExact
	item.CalculatorTraceJSON = common.MapToJsonStr(map[string]any{
		"provider_usage_cost": cost,
		"group_ratio":         groupRatio,
		"cond_multiplier":     condMultiplier,
		"calculator":          "provider_usage_cost",
	})
	return item, true
}

func hasProviderCostContext(billing, other map[string]any) bool {
	if _, ok := optionalFloatFromMaps("provider_usage_cost", billing, other); ok {
		return true
	}
	if _, ok := optionalFloatFromMaps("openrouter_cost", billing, other); ok {
		return true
	}
	return false
}

func firstPositiveFloat(values ...float64) float64 {
	for _, value := range values {
		if value > 0 {
			return value
		}
	}
	return 0
}

type standardBillingCalculation struct {
	expectedQuota int64
	trace         map[string]any
}

type snapshotBillingCalculation struct {
	expectedQuota    int64
	snapshotID       int64
	sourceModelID    string
	canonicalModelID string
	trace            map[string]any
}

func calculateSnapshotBillingQuota(logRow model.Log, channelType int, item model.PriceInspectionItem, billing, other map[string]any) (snapshotBillingCalculation, string, string) {
	if model.DB == nil {
		return snapshotBillingCalculation{}, "missing_price_snapshot", "database is not initialized"
	}
	sourceProvider := normalizeProvider(item.SourceProvider)
	if sourceProvider == "" || sourceProvider == "unknown" {
		return snapshotBillingCalculation{}, "missing_price_snapshot", "source_provider is missing"
	}
	sourceModelID := firstNonEmpty(item.SourceModelID, stringFromMaps("provider_model_id", billing, other), item.ModelName)
	canonicalModelID := firstNonEmpty(item.CanonicalModelID, sourceModelID)
	if mapping, err := model.FindPriceModelMapping([]int{logRow.ChannelId}, channelType, item.ModelName, sourceProvider); err == nil {
		sourceModelID = firstNonEmpty(mapping.SourceModelID, sourceModelID)
		canonicalModelID = firstNonEmpty(mapping.CanonicalModelID, sourceModelID)
	}
	snapshot, matchType, err := findInspectionPriceSnapshot(sourceProvider, sourceModelID, item.ModelName, logRow.CreatedAt)
	if err != nil {
		return snapshotBillingCalculation{}, "missing_price_snapshot", "no price snapshot found for source model"
	}
	inputTotal := intFromMapsDefault("input_total_tokens", logRow.PromptTokens, billing, other)
	outputTotal := intFromMapsDefault("output_total_tokens", logRow.CompletionTokens, billing, other)
	cacheRead := intFromMapsDefault("cache_read_tokens", 0, billing, other)
	cacheWrite := intFromMapsDefault("cache_write_tokens", 0, billing, other)
	cacheWrite5m := intFromMapsDefault("cache_write_5m_tokens", 0, billing, other)
	cacheWrite1h := intFromMapsDefault("cache_write_1h_tokens", 0, billing, other)
	inputImage := intFromMapsDefault("input_image_tokens", 0, billing, other)
	outputImage := intFromMapsDefault("output_image_tokens", 0, billing, other)
	inputAudio := intFromMapsDefault("input_audio_tokens", 0, billing, other)
	outputAudio := intFromMapsDefault("output_audio_tokens", 0, billing, other)
	inputToolUse := intFromMapsDefault("input_tool_use_tokens", 0, billing, other)
	imageCount := intFromMapsDefault("image_count", intFromMapsDefault("image_output_count", 0, billing, other), billing, other)
	requestCount := intFromMapsDefault("request_count", 1, billing, other)
	if inputTotal <= 0 {
		inputTotal = intFromMapsDefault("input_text_tokens", 0, billing, other) + cacheRead + cacheWrite + inputImage + inputAudio
	}
	if outputTotal <= 0 {
		outputTotal = intFromMapsDefault("output_text_tokens", 0, billing, other) + outputImage + outputAudio
	}
	cacheWriteRemaining := cacheWrite - cacheWrite5m - cacheWrite1h
	if cacheWriteRemaining < 0 {
		cacheWriteRemaining = 0
	}
	textInput := inputTotal - cacheRead - cacheWrite - inputImage - inputAudio
	if textInput < 0 {
		textInput = 0
	}
	textOutput := outputTotal - outputImage - outputAudio
	if textOutput < 0 {
		textOutput = 0
	}
	hasAnyPrice := snapshot.InputPricePerToken > 0 ||
		snapshot.OutputPricePerToken > 0 ||
		snapshot.CacheReadPricePerToken > 0 ||
		snapshot.CacheWritePricePerToken > 0 ||
		snapshot.CacheWrite5mPricePerToken > 0 ||
		snapshot.CacheWrite1hPricePerToken > 0 ||
		snapshot.InputImagePricePerToken > 0 ||
		snapshot.OutputImagePricePerToken > 0 ||
		snapshot.InputAudioPricePerToken > 0 ||
		snapshot.OutputAudioPricePerToken > 0 ||
		snapshot.ImagePrice > 0 ||
		snapshot.RequestPrice > 0
	if !hasAnyPrice {
		return snapshotBillingCalculation{}, "missing_snapshot_price", "price snapshot does not contain supported price fields"
	}
	cacheWrite5mPrice := firstPositiveFloat(snapshot.CacheWrite5mPricePerToken, snapshot.CacheWritePricePerToken)
	cacheWrite1hPrice := firstPositiveFloat(snapshot.CacheWrite1hPricePerToken, snapshot.CacheWritePricePerToken)
	usd := float64(textInput)*snapshot.InputPricePerToken +
		float64(textOutput)*snapshot.OutputPricePerToken +
		float64(cacheRead)*snapshot.CacheReadPricePerToken +
		float64(cacheWriteRemaining)*snapshot.CacheWritePricePerToken +
		float64(cacheWrite5m)*cacheWrite5mPrice +
		float64(cacheWrite1h)*cacheWrite1hPrice +
		float64(inputImage)*snapshot.InputImagePricePerToken +
		float64(outputImage)*snapshot.OutputImagePricePerToken +
		float64(inputAudio)*snapshot.InputAudioPricePerToken +
		float64(outputAudio)*snapshot.OutputAudioPricePerToken +
		float64(imageCount)*snapshot.ImagePrice +
		float64(requestCount)*snapshot.RequestPrice
	groupRatio := floatFromMapsDefault("group_ratio", 1, billing, other)
	condMultiplier := floatFromMapsDefault("cond_multiplier", 1, billing, other)
	if groupRatio <= 0 {
		groupRatio = 1
	}
	if condMultiplier <= 0 {
		condMultiplier = 1
	}
	quota := usd * groupRatio * condMultiplier * common.QuotaPerUnit
	trace := map[string]any{
		"calculator":                     "price_source_snapshot",
		"snapshot_id":                    snapshot.ID,
		"snapshot_match_type":            matchType,
		"source_provider":                sourceProvider,
		"source_model_id":                sourceModelID,
		"canonical_model_id":             firstNonEmpty(snapshot.CanonicalModelID, canonicalModelID),
		"pricing_scheme":                 snapshot.PricingScheme,
		"group_ratio":                    groupRatio,
		"cond_multiplier":                condMultiplier,
		"input_total_tokens":             inputTotal,
		"output_total_tokens":            outputTotal,
		"text_input_tokens":              textInput,
		"text_output_tokens":             textOutput,
		"cache_read_tokens":              cacheRead,
		"cache_write_tokens":             cacheWrite,
		"cache_write_remaining_tokens":   cacheWriteRemaining,
		"cache_write_5m_tokens":          cacheWrite5m,
		"cache_write_1h_tokens":          cacheWrite1h,
		"input_image_tokens":             inputImage,
		"output_image_tokens":            outputImage,
		"input_audio_tokens":             inputAudio,
		"output_audio_tokens":            outputAudio,
		"input_tool_use_tokens":          inputToolUse,
		"image_count":                    imageCount,
		"request_count":                  requestCount,
		"input_price_per_token":          snapshot.InputPricePerToken,
		"output_price_per_token":         snapshot.OutputPricePerToken,
		"cache_read_price_per_token":     snapshot.CacheReadPricePerToken,
		"cache_write_price_per_token":    snapshot.CacheWritePricePerToken,
		"cache_write_5m_price_per_token": cacheWrite5mPrice,
		"cache_write_1h_price_per_token": cacheWrite1hPrice,
		"input_image_price_per_token":    snapshot.InputImagePricePerToken,
		"output_image_price_per_token":   snapshot.OutputImagePricePerToken,
		"input_audio_price_per_token":    snapshot.InputAudioPricePerToken,
		"output_audio_price_per_token":   snapshot.OutputAudioPricePerToken,
		"image_price":                    snapshot.ImagePrice,
		"request_price":                  snapshot.RequestPrice,
		"snapshot_usage_usd":             usd,
	}
	return snapshotBillingCalculation{
		expectedQuota:    int64(math.Round(quota)),
		snapshotID:       snapshot.ID,
		sourceModelID:    snapshot.ModelID,
		canonicalModelID: firstNonEmpty(snapshot.CanonicalModelID, snapshot.ModelID),
		trace:            trace,
	}, "", ""
}

func findInspectionPriceSnapshot(sourceProvider, sourceModelID, localModelName string, createdAt int64) (*model.PriceSourceSnapshot, string, error) {
	snapshot, matchType, err := model.FindPriceSourceSnapshot(sourceProvider, sourceModelID, localModelName, createdAt)
	if err == nil {
		return snapshot, matchType, nil
	}
	if sourceProvider != ProviderOpenRouter {
		return nil, "", err
	}
	openRouterSnapshot, openRouterMatchType, openRouterErr := model.FindOpenRouterPriceSnapshot(sourceModelID, localModelName, createdAt)
	if openRouterErr != nil {
		return nil, "", err
	}
	converted := priceSourceSnapshotFromOpenRouter(*openRouterSnapshot)
	return &converted, "openrouter_" + openRouterMatchType, nil
}

func calculateStandardBillingQuota(logRow model.Log, billing, other map[string]any) (standardBillingCalculation, string, string) {
	groupRatio := floatFromMapsDefault("group_ratio", 1, billing, other)
	condMultiplier := floatFromMapsDefault("cond_multiplier", 1, billing, other)
	if groupRatio <= 0 {
		groupRatio = 1
	}
	if condMultiplier <= 0 {
		condMultiplier = 1
	}

	trace := map[string]any{
		"calculator":      "standard_billing_context",
		"group_ratio":     groupRatio,
		"cond_multiplier": condMultiplier,
	}

	modelPrice := floatFromMapsDefault("model_price", 0, billing, other)
	if modelPrice > 0 {
		quota := modelPrice * common.QuotaPerUnit * groupRatio * condMultiplier
		quota += fixedAddonQuota(billing, other, groupRatio, trace)
		expected := int64(math.Round(quota))
		trace["model_price"] = modelPrice
		trace["pricing_mode"] = "model_price"
		return standardBillingCalculation{expectedQuota: expected, trace: trace}, "", ""
	}

	if boolFromMaps("tiered_pricing", billing, other) {
		return calculateTieredStandardBilling(logRow, billing, other, groupRatio, condMultiplier, trace)
	}

	modelRatio, ok := optionalFloatFromMaps("model_ratio", billing, other)
	if !ok || modelRatio <= 0 {
		return standardBillingCalculation{}, "missing_standard_pricing_context", "provider_usage_cost is missing and model_ratio/model_price is not available"
	}
	completionRatio := floatFromMapsDefault("completion_ratio", 1, billing, other)
	cacheRatio := floatFromMapsDefault("cache_ratio", 1, billing, other)
	cacheCreationRatio := floatFromMapsDefault("cache_creation_ratio", 1, billing, other)
	cacheCreationRatio5m := floatFromMapsDefault("cache_creation_ratio_5m", cacheCreationRatio, billing, other)
	cacheCreationRatio1h := floatFromMapsDefault("cache_creation_ratio_1h", cacheCreationRatio, billing, other)
	imageRatio := floatFromMapsDefault("image_ratio", 1, billing, other)
	imageCompletionRatio := floatFromMapsDefault("image_completion_ratio", completionRatio, billing, other)
	audioRatio, hasAudioRatio := optionalFloatFromMaps("audio_ratio", billing, other)
	audioCompletionRatio := floatFromMapsDefault("audio_completion_ratio", completionRatio, billing, other)
	if !hasAudioRatio {
		audioRatio = 0
	}

	inputTotal := intFromMapsDefault("input_total_tokens", logRow.PromptTokens, billing, other)
	outputTotal := intFromMapsDefault("output_total_tokens", logRow.CompletionTokens, billing, other)
	inputText := intFromMapsDefault("input_text_tokens", 0, billing, other)
	outputText := intFromMapsDefault("output_text_tokens", 0, billing, other)
	cacheRead := intFromMapsDefault("cache_read_tokens", 0, billing, other)
	cacheWrite := intFromMapsDefault("cache_write_tokens", 0, billing, other)
	cacheWrite5m := intFromMapsDefault("cache_write_5m_tokens", 0, billing, other)
	cacheWrite1h := intFromMapsDefault("cache_write_1h_tokens", 0, billing, other)
	inputImage := intFromMapsDefault("input_image_tokens", 0, billing, other)
	outputImage := intFromMapsDefault("output_image_tokens", 0, billing, other)
	inputAudio := intFromMapsDefault("input_audio_tokens", 0, billing, other)
	outputAudio := intFromMapsDefault("output_audio_tokens", 0, billing, other)
	inputToolUse := intFromMapsDefault("input_tool_use_tokens", 0, billing, other)

	if inputTotal <= 0 {
		inputTotal = inputText + cacheRead + cacheWrite + inputImage + inputAudio
	}
	if outputTotal <= 0 {
		outputTotal = outputText + outputImage + outputAudio
	}
	if (inputAudio > 0 || outputAudio > 0) && !hasAudioRatio && floatFromMapsDefault("audio_input_price", 0, billing, other) <= 0 {
		return standardBillingCalculation{}, "missing_audio_pricing_context", "audio tokens exist but neither audio_ratio nor audio_input_price is available"
	}

	tokenUnits := 0.0
	if boolFromMaps("claude", billing, other) {
		remainingCacheWrite := cacheWrite - cacheWrite5m - cacheWrite1h
		if remainingCacheWrite < 0 {
			remainingCacheWrite = 0
		}
		claudeInputMult := floatFromMapsDefault("claude_200k_input_multiplier", 1, billing, other)
		claudeOutputMult := floatFromMapsDefault("claude_200k_output_multiplier", 1, billing, other)
		promptUnits := float64(inputTotal)*claudeInputMult +
			float64(cacheRead)*cacheRatio +
			float64(remainingCacheWrite)*cacheCreationRatio +
			float64(cacheWrite5m)*cacheCreationRatio5m +
			float64(cacheWrite1h)*cacheCreationRatio1h
		completionUnits := float64(outputTotal) * completionRatio
		tokenUnits = promptUnits + completionUnits*claudeOutputMult
		trace["native_claude"] = true
		trace["claude_200k_input_multiplier"] = claudeInputMult
		trace["claude_200k_output_multiplier"] = claudeOutputMult
	} else {
		baseInput := inputTotal - cacheRead - cacheWrite - inputImage - inputAudio
		if baseInput < 0 {
			baseInput = 0
		}
		remainingCacheWrite := cacheWrite - cacheWrite5m - cacheWrite1h
		if remainingCacheWrite < 0 {
			remainingCacheWrite = 0
		}
		promptUnits := float64(baseInput) +
			float64(cacheRead)*cacheRatio +
			float64(remainingCacheWrite)*cacheCreationRatio +
			float64(cacheWrite5m)*cacheCreationRatio5m +
			float64(cacheWrite1h)*cacheCreationRatio1h +
			float64(inputImage)*imageRatio
		if inputAudio > 0 && hasAudioRatio {
			promptUnits += float64(inputAudio) * audioRatio
		}
		textOutput := outputTotal - outputImage - outputAudio
		if textOutput < 0 {
			textOutput = 0
		}
		completionUnits := float64(textOutput)*completionRatio + float64(outputImage)*imageCompletionRatio
		if outputAudio > 0 && hasAudioRatio {
			completionUnits += float64(outputAudio) * audioRatio * audioCompletionRatio
		}
		claudeInputMult := floatFromMapsDefault("claude_200k_input_multiplier", 1, billing, other)
		claudeOutputMult := floatFromMapsDefault("claude_200k_output_multiplier", 1, billing, other)
		tokenUnits = promptUnits*claudeInputMult + completionUnits*claudeOutputMult
		if claudeInputMult != 1 || claudeOutputMult != 1 {
			trace["claude_200k_input_multiplier"] = claudeInputMult
			trace["claude_200k_output_multiplier"] = claudeOutputMult
		}
		trace["base_input_tokens"] = baseInput
	}

	tokenQuota := tokenUnits * modelRatio * groupRatio * condMultiplier
	if modelRatio != 0 && tokenQuota <= 0 && (inputTotal+outputTotal) > 0 {
		tokenQuota = 1
	}
	quota := tokenQuota + fixedAddonQuota(billing, other, groupRatio, trace)
	expected := int64(math.Round(quota))
	trace["pricing_mode"] = "model_ratio"
	trace["model_ratio"] = modelRatio
	trace["completion_ratio"] = completionRatio
	trace["cache_ratio"] = cacheRatio
	trace["cache_creation_ratio"] = cacheCreationRatio
	trace["image_ratio"] = imageRatio
	trace["image_completion_ratio"] = imageCompletionRatio
	trace["input_total_tokens"] = inputTotal
	trace["output_total_tokens"] = outputTotal
	trace["input_tool_use_tokens"] = inputToolUse
	trace["token_units"] = tokenUnits
	trace["token_quota"] = tokenQuota
	return standardBillingCalculation{expectedQuota: expected, trace: trace}, "", ""
}

func calculateTieredStandardBilling(logRow model.Log, billing, other map[string]any, groupRatio, condMultiplier float64, trace map[string]any) (standardBillingCalculation, string, string) {
	inputPrice, okInput := optionalFloatFromMaps("tiered_input_price", billing, other)
	outputPrice, okOutput := optionalFloatFromMaps("tiered_output_price", billing, other)
	cacheHitPrice := floatFromMapsDefault("tiered_cache_hit_price", 0, billing, other)
	cacheStorePrice := floatFromMapsDefault("tiered_cache_store_price", 0, billing, other)
	cacheStorePrice5m := floatFromMapsDefault("tiered_cache_store_price_5m", cacheStorePrice, billing, other)
	cacheStorePrice1h := floatFromMapsDefault("tiered_cache_store_price_1h", cacheStorePrice, billing, other)
	if !okInput || !okOutput {
		return standardBillingCalculation{}, "missing_tiered_pricing_context", "tiered pricing is enabled but tiered input/output price is missing"
	}
	inputTotal := intFromMapsDefault("input_total_tokens", logRow.PromptTokens, billing, other)
	outputTotal := intFromMapsDefault("output_total_tokens", logRow.CompletionTokens, billing, other)
	inputToolUse := intFromMapsDefault("input_tool_use_tokens", 0, billing, other)
	cacheRead := intFromMapsDefault("cache_read_tokens", 0, billing, other)
	cacheWrite := intFromMapsDefault("cache_write_tokens", 0, billing, other)
	cacheWrite5m := intFromMapsDefault("tiered_cache_creation_tokens_5m", intFromMapsDefault("cache_write_5m_tokens", 0, billing, other), billing, other)
	cacheWrite1h := intFromMapsDefault("tiered_cache_creation_tokens_1h", intFromMapsDefault("cache_write_1h_tokens", 0, billing, other), billing, other)
	cacheWriteRemaining := intFromMapsDefault("tiered_cache_creation_tokens_remaining", cacheWrite-cacheWrite5m-cacheWrite1h, billing, other)
	if cacheWriteRemaining < 0 {
		cacheWriteRemaining = 0
	}
	actualInput := inputTotal
	if boolFromMaps("tiered_prompt_tokens_include_cache", billing, other) {
		actualInput = inputTotal - cacheRead - cacheWrite
		if actualInput < 0 {
			actualInput = 0
		}
	}

	usd := (float64(actualInput)*inputPrice +
		float64(outputTotal)*outputPrice +
		float64(cacheRead)*cacheHitPrice +
		float64(cacheWriteRemaining)*cacheStorePrice +
		float64(cacheWrite5m)*cacheStorePrice5m +
		float64(cacheWrite1h)*cacheStorePrice1h) / 1000000
	quota := usd*common.QuotaPerUnit*groupRatio*condMultiplier + fixedAddonQuota(billing, other, groupRatio, trace)
	expected := int64(math.Round(quota))
	trace["pricing_mode"] = "tiered_pricing"
	trace["input_total_tokens"] = inputTotal
	trace["actual_input_tokens"] = actualInput
	trace["output_total_tokens"] = outputTotal
	trace["input_tool_use_tokens"] = inputToolUse
	trace["tiered_input_price"] = inputPrice
	trace["tiered_output_price"] = outputPrice
	trace["tiered_cache_hit_price"] = cacheHitPrice
	trace["tiered_cache_store_price"] = cacheStorePrice
	trace["tiered_usage_usd"] = usd
	return standardBillingCalculation{expectedQuota: expected, trace: trace}, "", ""
}

func fixedAddonQuota(billing, other map[string]any, groupRatio float64, trace map[string]any) float64 {
	quota := 0.0
	if calls := intFromMapsDefault("web_search_call_count", 0, billing, other); calls > 0 {
		price := floatFromMapsDefault("web_search_price", 0, billing, other)
		addon := price * float64(calls) / 1000 * groupRatio * common.QuotaPerUnit
		quota += addon
		trace["web_search_call_count"] = calls
		trace["web_search_price"] = price
		trace["web_search_quota"] = addon
	}
	if calls := intFromMapsDefault("file_search_call_count", 0, billing, other); calls > 0 {
		price := floatFromMapsDefault("file_search_price", 0, billing, other)
		addon := price * float64(calls) / 1000 * groupRatio * common.QuotaPerUnit
		quota += addon
		trace["file_search_call_count"] = calls
		trace["file_search_price"] = price
		trace["file_search_quota"] = addon
	}
	if price := floatFromMapsDefault("image_generation_call_price", 0, billing, other); price > 0 {
		addon := price * groupRatio * common.QuotaPerUnit
		quota += addon
		trace["image_generation_call_price"] = price
		trace["image_generation_call_quota"] = addon
	}
	if inputAudio := intFromMapsDefault("input_audio_tokens", 0, billing, other); inputAudio > 0 {
		if price := floatFromMapsDefault("audio_input_price", 0, billing, other); price > 0 {
			addon := price * float64(inputAudio) / 1000000 * groupRatio * common.QuotaPerUnit
			quota += addon
			trace["audio_input_price"] = price
			trace["audio_input_quota"] = addon
		}
	}
	if quota > 0 {
		trace["fixed_addon_quota"] = quota
	}
	return quota
}

func parseJSONMap(raw string) map[string]any {
	if strings.TrimSpace(raw) == "" {
		return map[string]any{}
	}
	var out map[string]any
	if err := json.Unmarshal([]byte(raw), &out); err != nil || out == nil {
		return map[string]any{}
	}
	return out
}

func nestedMap(m map[string]any, key string) map[string]any {
	value, ok := m[key]
	if !ok {
		return map[string]any{}
	}
	if typed, ok := value.(map[string]any); ok {
		return typed
	}
	return map[string]any{}
}

func billingContextForItem(other, billing map[string]any) map[string]any {
	if len(billing) > 0 {
		return billing
	}
	return other
}

func stringFromMaps(key string, maps ...map[string]any) string {
	for _, m := range maps {
		if value, ok := m[key]; ok {
			if str, ok := value.(string); ok {
				return strings.TrimSpace(str)
			}
		}
	}
	return ""
}

func optionalFloatFromMaps(key string, maps ...map[string]any) (float64, bool) {
	for _, m := range maps {
		if value, ok := m[key]; ok {
			return parseFloatValue(value)
		}
	}
	return 0, false
}

func floatFromMapsDefault(key string, def float64, maps ...map[string]any) float64 {
	if value, ok := optionalFloatFromMaps(key, maps...); ok {
		return value
	}
	return def
}

func intFromMapsDefault(key string, def int, maps ...map[string]any) int {
	for _, m := range maps {
		if value, ok := m[key]; ok {
			if parsed, ok := parseFloatValue(value); ok {
				return int(math.Round(parsed))
			}
		}
	}
	return def
}

func boolFromMaps(key string, maps ...map[string]any) bool {
	for _, m := range maps {
		value, ok := m[key]
		if !ok {
			continue
		}
		switch typed := value.(type) {
		case bool:
			return typed
		case string:
			raw := strings.ToLower(strings.TrimSpace(typed))
			return raw == "true" || raw == "1" || raw == "yes"
		case int:
			return typed != 0
		case int64:
			return typed != 0
		case float64:
			return typed != 0
		case json.Number:
			i, err := typed.Int64()
			return err == nil && i != 0
		}
	}
	return false
}

func parseFloatValue(value any) (float64, bool) {
	switch typed := value.(type) {
	case nil:
		return 0, false
	case float64:
		return typed, true
	case float32:
		return float64(typed), true
	case int:
		return float64(typed), true
	case int64:
		return float64(typed), true
	case json.Number:
		f, err := typed.Float64()
		return f, err == nil
	case string:
		raw := strings.TrimSpace(typed)
		if raw == "" {
			return 0, false
		}
		f, err := strconv.ParseFloat(raw, 64)
		return f, err == nil
	default:
		return 0, false
	}
}

func classifyQuota(actual, expected int64) (status, reason string, diffRate float64) {
	thresholds := loadQuotaClassificationThresholds()
	delta := actual - expected
	absDelta := absInt64(delta)
	maxQuota := maxInt64(absInt64(actual), absInt64(expected), 1)
	diffRate = float64(absDelta) / float64(maxQuota)
	if absDelta == 0 {
		return StatusNormal, "ok", diffRate
	}
	if expected < thresholds.SmallExpectedQuota && absDelta <= thresholds.SmallExpectedTolerance {
		return StatusNormal, "rounding_tolerance", diffRate
	}
	if expected < thresholds.MediumExpectedQuota && absDelta <= thresholds.MediumExpectedTolerance {
		return StatusNormal, "rounding_tolerance", diffRate
	}
	if absDelta <= thresholds.AbsoluteToleranceQuota || diffRate <= thresholds.NormalDiffRate {
		return StatusNormal, "ok", diffRate
	}
	if diffRate <= thresholds.WarningDiffRate {
		if delta > 0 {
			return StatusWarning, "overcharged", diffRate
		}
		return StatusWarning, "undercharged", diffRate
	}
	if diffRate <= thresholds.AbnormalDiffRate {
		if delta > 0 {
			return StatusAbnormal, "overcharged", diffRate
		}
		return StatusAbnormal, "undercharged", diffRate
	}
	if delta > 0 {
		return StatusCritical, "overcharged", diffRate
	}
	return StatusCritical, "undercharged", diffRate
}

func loadQuotaClassificationThresholds() quotaClassificationThresholds {
	thresholds := quotaClassificationThresholds{
		AbsoluteToleranceQuota:  2,
		SmallExpectedQuota:      100,
		SmallExpectedTolerance:  5,
		MediumExpectedQuota:     1000,
		MediumExpectedTolerance: 10,
		NormalDiffRate:          0.005,
		WarningDiffRate:         0.02,
		AbnormalDiffRate:        0.05,
	}
	thresholds.AbsoluteToleranceQuota = envInt64("PRICE_INSPECTION_ABS_TOLERANCE_QUOTA", thresholds.AbsoluteToleranceQuota)
	thresholds.SmallExpectedQuota = envInt64("PRICE_INSPECTION_SMALL_EXPECTED_QUOTA", thresholds.SmallExpectedQuota)
	thresholds.SmallExpectedTolerance = envInt64("PRICE_INSPECTION_SMALL_EXPECTED_TOLERANCE_QUOTA", thresholds.SmallExpectedTolerance)
	thresholds.MediumExpectedQuota = envInt64("PRICE_INSPECTION_MEDIUM_EXPECTED_QUOTA", thresholds.MediumExpectedQuota)
	thresholds.MediumExpectedTolerance = envInt64("PRICE_INSPECTION_MEDIUM_EXPECTED_TOLERANCE_QUOTA", thresholds.MediumExpectedTolerance)
	thresholds.NormalDiffRate = envFloat64("PRICE_INSPECTION_NORMAL_DIFF_RATE", thresholds.NormalDiffRate)
	thresholds.WarningDiffRate = envFloat64("PRICE_INSPECTION_WARNING_DIFF_RATE", thresholds.WarningDiffRate)
	thresholds.AbnormalDiffRate = envFloat64("PRICE_INSPECTION_ABNORMAL_DIFF_RATE", thresholds.AbnormalDiffRate)
	if thresholds.NormalDiffRate < 0 {
		thresholds.NormalDiffRate = 0
	}
	if thresholds.WarningDiffRate < thresholds.NormalDiffRate {
		thresholds.WarningDiffRate = thresholds.NormalDiffRate
	}
	if thresholds.AbnormalDiffRate < thresholds.WarningDiffRate {
		thresholds.AbnormalDiffRate = thresholds.WarningDiffRate
	}
	return thresholds
}

func envInt64(name string, fallback int64) int64 {
	value := strings.TrimSpace(os.Getenv(name))
	if value == "" {
		return fallback
	}
	parsed, err := strconv.ParseInt(value, 10, 64)
	if err != nil || parsed < 0 {
		return fallback
	}
	return parsed
}

func envFloat64(name string, fallback float64) float64 {
	value := strings.TrimSpace(os.Getenv(name))
	if value == "" {
		return fallback
	}
	parsed, err := strconv.ParseFloat(value, 64)
	if err != nil {
		return fallback
	}
	return parsed
}

func accumulateRunResult(result *RunResult, status string) {
	switch status {
	case StatusNormal:
		result.NormalCount++
	case StatusWarning:
		result.WarningCount++
	case StatusAbnormal:
		result.AbnormalCount++
	case StatusCritical:
		result.CriticalCount++
	case StatusMissing:
		result.MissingCount++
	case StatusUnsupported:
		result.UnsupportedCount++
	case StatusOutOfScope:
		result.OutOfScopeCount++
	default:
		result.FailedCount++
	}
}

func runStatusFromResult(result *RunResult) string {
	if result.CriticalCount > 0 {
		return StatusCritical
	}
	if result.AbnormalCount > 0 {
		return StatusAbnormal
	}
	if result.WarningCount > 0 {
		return StatusWarning
	}
	if result.FailedCount > 0 {
		return StatusFailed
	}
	return StatusNormal
}

func runSourceProvider(sourceProvider string) string {
	if sourceProvider == "" {
		return "all"
	}
	return sourceProvider
}

func channelTypesForProvider(sourceProvider string) []int {
	switch sourceProvider {
	case ProviderOpenRouter:
		return []int{constant.ChannelTypeOpenRouter}
	case "openai":
		return []int{constant.ChannelTypeOpenAI, constant.ChannelTypeOpenAIMax}
	case "azure":
		return []int{constant.ChannelTypeAzure}
	case "anthropic":
		return []int{constant.ChannelTypeAnthropic}
	case "google":
		return []int{constant.ChannelTypeGemini, constant.ChannelTypeVertexAi}
	default:
		return nil
	}
}

func absInt64(v int64) int64 {
	if v < 0 {
		return -v
	}
	return v
}

func maxInt64(values ...int64) int64 {
	max := values[0]
	for _, v := range values[1:] {
		if v > max {
			max = v
		}
	}
	return max
}
