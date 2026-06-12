package openrouter_inspection

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/constant"
	"github.com/QuantumNous/new-api/model"
)

const (
	OpenRouterModelsURL = "https://openrouter.ai/api/v1/models"
	ProviderOpenRouter  = "openrouter"

	StatusNormal      = "normal"
	StatusWarning     = "warning"
	StatusAbnormal    = "abnormal"
	StatusCritical    = "critical"
	StatusMissing     = "missing"
	StatusUnsupported = "unsupported"
	StatusFailed      = "failed"

	SupportExact       = "exact"
	SupportStandard    = "standard"
	SupportEstimated   = "estimated"
	SupportUnsupported = "unsupported"
)

type FetchPriceSnapshotsResult struct {
	FetchedAt int64 `json:"fetched_at"`
	Count     int   `json:"count"`
}

type RunRequest struct {
	WindowStart int64  `json:"window_start"`
	WindowEnd   int64  `json:"window_end"`
	ChannelID   int    `json:"channel_id"`
	ModelName   string `json:"model_name"`
	Limit       int    `json:"limit"`
	TriggerType string `json:"trigger_type"`
}

type RunResult struct {
	RunID            int64 `json:"run_id"`
	TotalLogs        int   `json:"total_logs"`
	CheckedLogs      int   `json:"checked_logs"`
	NormalCount      int   `json:"normal_count"`
	WarningCount     int   `json:"warning_count"`
	AbnormalCount    int   `json:"abnormal_count"`
	CriticalCount    int   `json:"critical_count"`
	MissingCount     int   `json:"missing_count"`
	UnsupportedCount int   `json:"unsupported_count"`
	FailedCount      int   `json:"failed_count"`
}

type Summary struct {
	Total       int `json:"total"`
	Normal      int `json:"normal"`
	Warning     int `json:"warning"`
	Abnormal    int `json:"abnormal"`
	Critical    int `json:"critical"`
	Missing     int `json:"missing"`
	Unsupported int `json:"unsupported"`
	Failed      int `json:"failed"`
}

type openRouterModelsResponse struct {
	Data []openRouterModel `json:"data"`
}

type openRouterModel struct {
	ID            string         `json:"id"`
	CanonicalSlug string         `json:"canonical_slug"`
	Architecture  map[string]any `json:"architecture"`
	Pricing       map[string]any `json:"pricing"`
}

type tokenBreakdown struct {
	InputTextTokens   int
	OutputTextTokens  int
	CacheReadTokens   int
	CacheWriteTokens  int
	InputImageTokens  int
	OutputImageTokens int
	InputAudioTokens  int
	OutputAudioTokens int
	UnsupportedReason string
}

func FetchAndStorePriceSnapshots(ctx context.Context) (*FetchPriceSnapshotsResult, error) {
	client := &http.Client{Timeout: 20 * time.Second}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, OpenRouterModelsURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("openrouter models returned %s", resp.Status)
	}

	limited := io.LimitReader(resp.Body, 64<<20)
	var body openRouterModelsResponse
	if err := json.NewDecoder(limited).Decode(&body); err != nil {
		return nil, err
	}

	fetchedAt := time.Now().Unix()
	rows := make([]model.OpenRouterPriceSnapshot, 0, len(body.Data))
	for _, item := range body.Data {
		raw, _ := json.Marshal(item)
		prompt := priceField(item.Pricing, "prompt")
		completion := priceField(item.Pricing, "completion")
		cacheRead := firstPriceField(item.Pricing, "input_cache_read", "cache_read", "cache")
		cacheWrite := firstPriceField(item.Pricing, "input_cache_write", "input_cache_creation", "cache_write")
		image := firstPriceField(item.Pricing, "image", "image_output")
		requestPrice := firstPriceField(item.Pricing, "request", "per_request")
		rows = append(rows, model.OpenRouterPriceSnapshot{
			FetchedAt:               fetchedAt,
			ModelID:                 item.ID,
			CanonicalSlug:           item.CanonicalSlug,
			LocalModelName:          localModelName(item.ID),
			PromptPricePerToken:     prompt,
			CompletionPricePerToken: completion,
			CacheReadPricePerToken:  cacheRead,
			CacheWritePricePerToken: cacheWrite,
			ImagePrice:              image,
			RequestPrice:            requestPrice,
			IsFree:                  prompt == 0 && completion == 0 && cacheRead == 0 && cacheWrite == 0 && image == 0 && requestPrice == 0,
			RawJSON:                 string(raw),
		})
	}
	if err := model.InsertOpenRouterPriceSnapshots(rows); err != nil {
		return nil, err
	}
	return &FetchPriceSnapshotsResult{FetchedAt: fetchedAt, Count: len(rows)}, nil
}

func RunInspection(ctx context.Context, req RunRequest) (*RunResult, error) {
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

	run := &model.OpenRouterInspectionRun{
		Status:      "running",
		TriggerType: req.TriggerType,
		WindowStart: req.WindowStart,
		WindowEnd:   req.WindowEnd,
		StartedAt:   time.Now().Unix(),
	}
	if err := model.CreateOpenRouterInspectionRun(run); err != nil {
		return nil, err
	}
	genericRun := &model.PriceInspectionRun{
		SourceProvider: ProviderOpenRouter,
		SourceRunID:    run.ID,
		Status:         "running",
		TriggerType:    req.TriggerType,
		ChannelID:      req.ChannelID,
		ChannelType:    constant.ChannelTypeOpenRouter,
		ModelName:      req.ModelName,
		WindowStart:    req.WindowStart,
		WindowEnd:      req.WindowEnd,
		StartedAt:      run.StartedAt,
	}
	if err := model.CreatePriceInspectionRun(genericRun); err != nil {
		run.Status = StatusFailed
		run.FinishedAt = time.Now().Unix()
		run.SummaryJSON = common.GetJsonString(map[string]any{"error": err.Error()})
		_ = model.UpdateOpenRouterInspectionRun(run)
		return nil, err
	}

	logs, err := scanLogs(req)
	if err != nil {
		run.Status = StatusFailed
		run.FinishedAt = time.Now().Unix()
		run.SummaryJSON = common.GetJsonString(map[string]any{"error": err.Error()})
		_ = model.UpdateOpenRouterInspectionRun(run)
		genericRun.Status = StatusFailed
		genericRun.FinishedAt = run.FinishedAt
		genericRun.SummaryJSON = run.SummaryJSON
		_ = model.UpdatePriceInspectionRun(genericRun)
		return nil, err
	}

	items := make([]model.OpenRouterInspectionItem, 0, len(logs))
	result := &RunResult{RunID: run.ID, TotalLogs: len(logs)}
	for _, logRow := range logs {
		item := inspectLog(ctx, run.ID, logRow)
		items = append(items, item)
		accumulate(result, item.Status)
		if item.Status != StatusFailed {
			result.CheckedLogs++
		}
	}

	if err := model.InsertOpenRouterInspectionItems(items); err != nil {
		run.Status = StatusFailed
		run.FinishedAt = time.Now().Unix()
		run.SummaryJSON = common.GetJsonString(map[string]any{"error": err.Error()})
		_ = model.UpdateOpenRouterInspectionRun(run)
		genericRun.Status = StatusFailed
		genericRun.FinishedAt = run.FinishedAt
		genericRun.SummaryJSON = run.SummaryJSON
		_ = model.UpdatePriceInspectionRun(genericRun)
		return nil, err
	}
	if err := model.InsertPriceInspectionItems(convertOpenRouterItems(genericRun.ID, run.ID, items)); err != nil {
		run.Status = StatusFailed
		run.FinishedAt = time.Now().Unix()
		run.SummaryJSON = common.GetJsonString(map[string]any{"error": err.Error()})
		_ = model.UpdateOpenRouterInspectionRun(run)
		genericRun.Status = StatusFailed
		genericRun.FinishedAt = run.FinishedAt
		genericRun.SummaryJSON = run.SummaryJSON
		_ = model.UpdatePriceInspectionRun(genericRun)
		return nil, err
	}

	run.Status = StatusNormal
	if result.CriticalCount > 0 {
		run.Status = StatusCritical
	} else if result.AbnormalCount > 0 {
		run.Status = StatusAbnormal
	} else if result.WarningCount > 0 {
		run.Status = StatusWarning
	} else if result.FailedCount > 0 {
		run.Status = StatusFailed
	}
	run.FinishedAt = time.Now().Unix()
	run.TotalLogs = result.TotalLogs
	run.CheckedLogs = result.CheckedLogs
	run.NormalCount = result.NormalCount
	run.WarningCount = result.WarningCount
	run.AbnormalCount = result.AbnormalCount
	run.CriticalCount = result.CriticalCount
	run.MissingCount = result.MissingCount
	run.UnsupportedCount = result.UnsupportedCount
	run.FailedCount = result.FailedCount
	run.SummaryJSON = common.GetJsonString(result)
	if err := model.UpdateOpenRouterInspectionRun(run); err != nil {
		return nil, err
	}
	copyOpenRouterRunStatsToGeneric(genericRun, run)
	if err := model.UpdatePriceInspectionRun(genericRun); err != nil {
		return nil, err
	}
	return result, nil
}

func scanLogs(req RunRequest) ([]model.Log, error) {
	var channelIDs []int
	if req.ChannelID > 0 {
		var ch model.Channel
		if err := model.DB.Select("id, type").Where("id = ?", req.ChannelID).First(&ch).Error; err != nil {
			return nil, err
		}
		if ch.Type != constant.ChannelTypeOpenRouter {
			return nil, fmt.Errorf("channel %d is not OpenRouter", req.ChannelID)
		}
		channelIDs = []int{req.ChannelID}
	} else {
		if err := model.DB.Model(&model.Channel{}).Where("type = ?", constant.ChannelTypeOpenRouter).Pluck("id", &channelIDs).Error; err != nil {
			return nil, err
		}
	}
	if len(channelIDs) == 0 {
		return []model.Log{}, nil
	}

	tx := model.LOG_DB.Where("type = ? AND channel_id IN ? AND created_at >= ? AND created_at <= ?",
		model.LogTypeConsume, channelIDs, req.WindowStart, req.WindowEnd)
	if req.ModelName != "" {
		tx = tx.Where("model_name = ?", req.ModelName)
	}
	var logs []model.Log
	err := tx.Order("created_at ASC, id ASC").Limit(req.Limit).Find(&logs).Error
	return logs, err
}

func inspectLog(ctx context.Context, runID int64, logRow model.Log) model.OpenRouterInspectionItem {
	other := parseOther(logRow.Other)
	breakdown := extractTokens(logRow, other)
	item := model.OpenRouterInspectionItem{
		RunID:            runID,
		LogID:            int64(logRow.Id),
		LogCreatedAt:     logRow.CreatedAt,
		ChannelID:        logRow.ChannelId,
		ModelName:        logRow.ModelName,
		ActualQuota:      int64(logRow.Quota),
		ActualUSD:        float64(logRow.Quota) / common.QuotaPerUnit,
		InputTokens:      breakdown.InputTextTokens,
		OutputTokens:     breakdown.OutputTextTokens,
		CacheReadTokens:  breakdown.CacheReadTokens,
		CacheWriteTokens: breakdown.CacheWriteTokens,
		GroupRatio:       floatFieldDefault(other, "group_ratio", 1),
		CondMultiplier:   floatFieldDefault(other, "billing_cond_multiplier", 1),
		RawContextJSON:   common.MapToJsonStr(other),
	}
	if item.GroupRatio <= 0 {
		item.GroupRatio = 1
	}
	if item.CondMultiplier <= 0 {
		item.CondMultiplier = 1
	}

	if cost, ok := optionalFloatField(other, "openrouter_cost", "cost", "provider_usage_cost"); ok && cost >= 0 {
		item.OpenRouterModelID = stringField(other, "openrouter_model_id", "upstream_model_name", "provider_model_id")
		item.ExpectedUSD = cost * item.GroupRatio * item.CondMultiplier
		item.ExpectedQuota = int64(math.Round(item.ExpectedUSD * common.QuotaPerUnit))
		item.SupportLevel = SupportExact
		item.Status, item.ReasonCode, item.DiffRate = classify(item.ActualQuota, item.ExpectedQuota)
		return item
	}

	if unsupported := unsupportedReason(other, breakdown); unsupported != "" {
		item.Status = StatusUnsupported
		item.SupportLevel = SupportUnsupported
		item.ReasonCode = unsupported
		item.ReasonDetail = "log contains billing fields that need a dedicated calculator or OpenRouter usage.cost"
		return item
	}

	openRouterModelID := stringField(other, "openrouter_model_id", "upstream_model_name", "provider_model_id")
	if openRouterModelID == "" {
		if mapping, err := model.FindOpenRouterModelMapping(logRow.ChannelId, logRow.ModelName); err == nil {
			openRouterModelID = mapping.OpenRouterModel
		}
	}
	snapshot, matchMode, err := model.FindOpenRouterPriceSnapshot(openRouterModelID, logRow.ModelName, logRow.CreatedAt)
	if err != nil {
		item.Status = StatusMissing
		item.SupportLevel = SupportUnsupported
		item.ReasonCode = "missing_openrouter_price"
		item.ReasonDetail = err.Error()
		return item
	}
	item.OpenRouterModelID = snapshot.ModelID
	item.PriceSnapshotID = snapshot.ID

	if matchMode == "exact_latest" || matchMode == "local_latest" {
		item.SupportLevel = SupportEstimated
		item.ReasonCode = "price_snapshot_after_log"
	} else {
		item.SupportLevel = SupportStandard
	}

	if item.CacheWriteTokens > 0 && snapshot.CacheWritePricePerToken <= 0 {
		item.Status = StatusUnsupported
		item.SupportLevel = SupportUnsupported
		item.ReasonCode = "unsupported_cache_write"
		item.ReasonDetail = "cache write tokens are present but OpenRouter snapshot has no cache write price"
		return item
	}

	rawUSD := float64(item.InputTokens)*snapshot.PromptPricePerToken +
		float64(item.OutputTokens)*snapshot.CompletionPricePerToken +
		float64(item.CacheReadTokens)*snapshot.CacheReadPricePerToken +
		float64(item.CacheWriteTokens)*snapshot.CacheWritePricePerToken
	item.ExpectedUSD = rawUSD * item.GroupRatio * item.CondMultiplier
	item.ExpectedQuota = int64(math.Round(item.ExpectedUSD * common.QuotaPerUnit))
	item.Status, item.ReasonCode, item.DiffRate = classify(item.ActualQuota, item.ExpectedQuota)
	if item.ReasonCode == "ok" && item.SupportLevel == SupportEstimated {
		item.ReasonCode = "price_snapshot_after_log"
	}
	_ = ctx
	return item
}

func unsupportedReason(other map[string]any, breakdown tokenBreakdown) string {
	if breakdown.UnsupportedReason != "" {
		return breakdown.UnsupportedReason
	}
	if boolField(other, "image_generation_call") {
		return "unsupported_tool_charge"
	}
	if intField(other, "web_search_call_count") > 0 || intField(other, "file_search_call_count") > 0 {
		return "unsupported_tool_charge"
	}
	if boolField(other, "tiered_pricing") {
		return "unsupported_tiered_pricing"
	}
	if floatFieldDefault(other, "model_price", 0) > 0 {
		return "unsupported_model_price"
	}
	if breakdown.InputImageTokens > 0 || breakdown.OutputImageTokens > 0 {
		return "unsupported_image_tokens"
	}
	if breakdown.InputAudioTokens > 0 || breakdown.OutputAudioTokens > 0 {
		return "unsupported_audio_tokens"
	}
	return ""
}

func classify(actual, expected int64) (status, reason string, diffRate float64) {
	delta := actual - expected
	absDelta := absInt64(delta)
	maxQuota := maxInt64(absInt64(actual), absInt64(expected), 1)
	diffRate = float64(absDelta) / float64(maxQuota)

	if absDelta == 0 {
		return StatusNormal, "ok", diffRate
	}
	if expected < 100 && absDelta <= 5 {
		return StatusNormal, "rounding_tolerance", diffRate
	}
	if expected < 1000 && absDelta <= 10 {
		return StatusNormal, "rounding_tolerance", diffRate
	}
	if absDelta <= 2 || diffRate <= 0.005 {
		return StatusNormal, "ok", diffRate
	}
	if diffRate <= 0.02 {
		if delta > 0 {
			return StatusWarning, "overcharged", diffRate
		}
		return StatusWarning, "undercharged", diffRate
	}
	if diffRate <= 0.05 {
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

func accumulate(result *RunResult, status string) {
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
	default:
		result.FailedCount++
	}
}

func copyOpenRouterRunStatsToGeneric(genericRun *model.PriceInspectionRun, run *model.OpenRouterInspectionRun) {
	genericRun.Status = run.Status
	genericRun.FinishedAt = run.FinishedAt
	genericRun.TotalLogs = run.TotalLogs
	genericRun.CheckedLogs = run.CheckedLogs
	genericRun.NormalCount = run.NormalCount
	genericRun.WarningCount = run.WarningCount
	genericRun.AbnormalCount = run.AbnormalCount
	genericRun.CriticalCount = run.CriticalCount
	genericRun.MissingCount = run.MissingCount
	genericRun.UnsupportedCount = run.UnsupportedCount
	genericRun.FailedCount = run.FailedCount
	genericRun.SummaryJSON = run.SummaryJSON
}

func convertOpenRouterItems(genericRunID, sourceRunID int64, items []model.OpenRouterInspectionItem) []model.PriceInspectionItem {
	rows := make([]model.PriceInspectionItem, 0, len(items))
	for _, item := range items {
		rows = append(rows, convertOpenRouterItem(genericRunID, sourceRunID, item))
	}
	return rows
}

func convertOpenRouterItem(genericRunID, sourceRunID int64, item model.OpenRouterInspectionItem) model.PriceInspectionItem {
	trace := map[string]any{
		"input_tokens":       item.InputTokens,
		"output_tokens":      item.OutputTokens,
		"cache_read_tokens":  item.CacheReadTokens,
		"cache_write_tokens": item.CacheWriteTokens,
		"group_ratio":        item.GroupRatio,
		"cond_multiplier":    item.CondMultiplier,
	}
	return model.PriceInspectionItem{
		RunID:               genericRunID,
		SourceRunID:         sourceRunID,
		LogID:               item.LogID,
		LogCreatedAt:        item.LogCreatedAt,
		ChannelID:           item.ChannelID,
		ChannelType:         constant.ChannelTypeOpenRouter,
		SourceProvider:      ProviderOpenRouter,
		ModelName:           item.ModelName,
		SourceModelID:       item.OpenRouterModelID,
		CanonicalModelID:    item.OpenRouterModelID,
		Scenario:            scenarioForOpenRouterItem(item),
		PriceSnapshotID:     item.PriceSnapshotID,
		ActualQuota:         item.ActualQuota,
		ExpectedQuota:       item.ExpectedQuota,
		DeltaQuota:          item.ActualQuota - item.ExpectedQuota,
		DiffRate:            item.DiffRate,
		ExpectedUSD:         item.ExpectedUSD,
		ActualUSD:           item.ActualUSD,
		SupportLevel:        item.SupportLevel,
		Status:              item.Status,
		ReasonCode:          item.ReasonCode,
		ReasonDetail:        item.ReasonDetail,
		BillingContextJSON:  item.RawContextJSON,
		CalculatorTraceJSON: common.MapToJsonStr(trace),
	}
}

func scenarioForOpenRouterItem(item model.OpenRouterInspectionItem) string {
	switch item.ReasonCode {
	case "unsupported_image_tokens":
		return "image_generation"
	case "unsupported_audio_tokens":
		return "audio_task"
	case "unsupported_tool_charge":
		return "tool_call"
	default:
		return "text_token"
	}
}

func extractTokens(logRow model.Log, other map[string]any) tokenBreakdown {
	b := tokenBreakdown{}
	b.CacheReadTokens = intField(other, "cache_tokens")
	b.CacheWriteTokens = firstIntField(other, "cache_creation_tokens", "tiered_cache_creation_tokens_remaining")
	b.InputImageTokens = firstIntField(other, "input_image_tokens", "image_output")
	b.OutputImageTokens = firstIntField(other, "output_image_tokens", "image_completion_tokens")
	b.InputAudioTokens = firstIntField(other, "input_audio_tokens", "audio_input_token_count", "audio_input")
	b.OutputAudioTokens = firstIntField(other, "output_audio_tokens", "audio_output")

	b.InputTextTokens = firstIntField(other, "input_text_tokens", "text_input")
	if b.InputTextTokens == 0 {
		b.InputTextTokens = logRow.PromptTokens - b.CacheReadTokens - b.CacheWriteTokens - b.InputImageTokens - b.InputAudioTokens
		if b.InputTextTokens < 0 {
			b.UnsupportedReason = "unsupported_token_breakdown"
			b.InputTextTokens = 0
		}
	}
	b.OutputTextTokens = firstIntField(other, "output_text_tokens", "output_non_image_tokens", "text_output")
	if b.OutputTextTokens == 0 {
		b.OutputTextTokens = logRow.CompletionTokens - b.OutputImageTokens - b.OutputAudioTokens
		if b.OutputTextTokens < 0 {
			b.UnsupportedReason = "unsupported_token_breakdown"
			b.OutputTextTokens = 0
		}
	}
	return b
}

func parseOther(raw string) map[string]any {
	if strings.TrimSpace(raw) == "" {
		return map[string]any{}
	}
	var out map[string]any
	if err := json.Unmarshal([]byte(raw), &out); err != nil || out == nil {
		return map[string]any{}
	}
	return out
}

func localModelName(modelID string) string {
	name := strings.TrimPrefix(strings.TrimSpace(modelID), "~")
	if idx := strings.LastIndex(name, "/"); idx >= 0 {
		name = name[idx+1:]
	}
	return name
}

func priceField(pricing map[string]any, key string) float64 {
	if pricing == nil {
		return 0
	}
	return parseFloatAny(pricing[key])
}

func firstPriceField(pricing map[string]any, keys ...string) float64 {
	for _, key := range keys {
		if value := priceField(pricing, key); value != 0 {
			return value
		}
	}
	return 0
}

func stringField(m map[string]any, keys ...string) string {
	for _, key := range keys {
		if v, ok := lookupField(m, key); ok {
			if s, ok := v.(string); ok && strings.TrimSpace(s) != "" {
				return strings.TrimSpace(s)
			}
		}
	}
	return ""
}

func optionalFloatField(m map[string]any, keys ...string) (float64, bool) {
	for _, key := range keys {
		if v, ok := lookupField(m, key); ok {
			return parseFloatAny(v), true
		}
	}
	return 0, false
}

func floatFieldDefault(m map[string]any, key string, def float64) float64 {
	if v, ok := lookupField(m, key); ok {
		return parseFloatAny(v)
	}
	return def
}

func intField(m map[string]any, key string) int {
	if v, ok := lookupField(m, key); ok {
		return int(math.Round(parseFloatAny(v)))
	}
	return 0
}

func firstIntField(m map[string]any, keys ...string) int {
	for _, key := range keys {
		if v := intField(m, key); v != 0 {
			return v
		}
	}
	return 0
}

func boolField(m map[string]any, key string) bool {
	if v, ok := lookupField(m, key); ok {
		switch typed := v.(type) {
		case bool:
			return typed
		case string:
			return typed == "true" || typed == "1"
		case float64:
			return typed != 0
		}
	}
	return false
}

func lookupField(m map[string]any, key string) (any, bool) {
	if v, ok := m[key]; ok {
		return v, true
	}
	if billingRaw, ok := m["billing"]; ok {
		switch billing := billingRaw.(type) {
		case map[string]any:
			v, ok := billing[key]
			return v, ok
		}
	}
	return nil, false
}

func parseFloatAny(value any) float64 {
	switch typed := value.(type) {
	case nil:
		return 0
	case float64:
		return typed
	case float32:
		return float64(typed)
	case int:
		return float64(typed)
	case int64:
		return float64(typed)
	case json.Number:
		f, _ := typed.Float64()
		return f
	case string:
		f, _ := strconv.ParseFloat(strings.TrimSpace(typed), 64)
		return f
	default:
		return 0
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

func StartScheduledWorker(ctx context.Context, intervalMinutes int) {
	if intervalMinutes <= 0 {
		intervalMinutes = 15
	}
	ticker := time.NewTicker(time.Duration(intervalMinutes) * time.Minute)
	go func() {
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if _, err := RunInspection(ctx, RunRequest{TriggerType: "scheduled"}); err != nil {
					common.SysError("openrouter billing inspection failed: " + err.Error())
				}
			}
		}
	}()
}

func StartScheduledPriceFetcher(ctx context.Context, intervalHours int) {
	if intervalHours <= 0 {
		intervalHours = 6
	}
	ticker := time.NewTicker(time.Duration(intervalHours) * time.Hour)
	go func() {
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if _, err := FetchAndStorePriceSnapshots(ctx); err != nil {
					common.SysError("openrouter price snapshot fetch failed: " + err.Error())
				}
			}
		}
	}()
}
