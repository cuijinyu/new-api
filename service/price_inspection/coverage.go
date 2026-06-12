package price_inspection

import (
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/constant"
	"github.com/QuantumNous/new-api/model"

	"gorm.io/gorm"
)

const (
	ProviderOpenRouter = "openrouter"

	MappingExplicit       = "explicit_mapping"
	MappingDirectModel    = "direct_source_model"
	MappingDirectLocal    = "direct_local_model"
	MappingNormalized     = "normalized_local_model"
	MappingMissing        = "missing_mapping"
	MappingNotRequired    = "not_required"
	MappingUnsupportedSrc = "unsupported_price_source"

	CalculatorSupported   = "supported"
	CalculatorUnsupported = "unsupported"
	CalculatorMissing     = "missing"
	CalculatorOutOfScope  = "out_of_scope"

	LogContextAvailable = "available"
	LogContextNoSamples = "no_recent_samples"
	LogContextUnknown   = "unknown"

	SupportStandard    = "standard"
	SupportEstimated   = "estimated"
	SupportUnsupported = "unsupported"
	SupportOutOfScope  = "out_of_scope"
)

type GenerateCoverageRequest struct {
	SourceProvider string `json:"source_provider"`
	ChannelType    int    `json:"channel_type"`
	ModelName      string `json:"model_name"`
	LogWindowDays  int    `json:"log_window_days"`
}

type GenerateCoverageResult struct {
	GeneratedAt       int64          `json:"generated_at"`
	SourceProvider    string         `json:"source_provider"`
	TotalModels       int            `json:"total_models"`
	StandardCount     int            `json:"standard_count"`
	EstimatedCount    int            `json:"estimated_count"`
	UnsupportedCount  int            `json:"unsupported_count"`
	MissingCount      int            `json:"missing_count"`
	OutOfScopeCount   int            `json:"out_of_scope_count"`
	ByReasonCode      map[string]int `json:"by_reason_code"`
	ByScenario        map[string]int `json:"by_scenario"`
	ByChannelTypeName map[string]int `json:"by_channel_type_name"`
}

type channelModelAggregate struct {
	ChannelType int
	ModelName   string
	ChannelIDs  []int
}

type snapshotIndex struct {
	byModelID        map[string]model.PriceSourceSnapshot
	byLocalModelName map[string]model.PriceSourceSnapshot
	byNormalizedName map[string]model.PriceSourceSnapshot
}

type logAggregate struct {
	Count               int64
	BillingContextCount int64
	ProviderCostCount   int64
	LastSeenAt          int64
}

func GenerateCoverage(req GenerateCoverageRequest) (*GenerateCoverageResult, error) {
	req.SourceProvider = normalizeProvider(req.SourceProvider)
	if req.SourceProvider == "" {
		req.SourceProvider = ProviderOpenRouter
	}
	if req.LogWindowDays <= 0 {
		req.LogWindowDays = 30
	}

	aggregates, err := loadChannelModelAggregates(req)
	if err != nil {
		return nil, err
	}
	logStats := loadLogAggregates(aggregates, req.LogWindowDays)

	var idx snapshotIndex
	if req.SourceProvider == ProviderOpenRouter {
		idx, err = loadOpenRouterSnapshotIndex()
		if err != nil {
			return nil, err
		}
	} else {
		idx, err = loadPriceSourceSnapshotIndex(req.SourceProvider)
		if err != nil {
			return nil, err
		}
	}

	generatedAt := time.Now().Unix()
	rows := make([]model.PriceInspectionCoverageReport, 0, len(aggregates))
	result := &GenerateCoverageResult{
		GeneratedAt:       generatedAt,
		SourceProvider:    req.SourceProvider,
		ByReasonCode:      map[string]int{},
		ByScenario:        map[string]int{},
		ByChannelTypeName: map[string]int{},
	}

	for _, aggregate := range aggregates {
		row := buildCoverageRow(generatedAt, req.SourceProvider, aggregate, idx, logStats[coverageKey(aggregate.ChannelType, aggregate.ModelName)])
		rows = append(rows, row)
		result.TotalModels++
		result.ByReasonCode[row.ReasonCode]++
		result.ByScenario[row.Scenario]++
		result.ByChannelTypeName[row.ChannelTypeName]++
		switch row.SupportLevel {
		case SupportStandard:
			result.StandardCount++
		case SupportEstimated:
			result.EstimatedCount++
		case SupportUnsupported:
			if row.MappingStatus == MappingMissing || row.CalculatorStatus == CalculatorMissing {
				result.MissingCount++
			} else {
				result.UnsupportedCount++
			}
		case SupportOutOfScope:
			result.OutOfScopeCount++
		}
	}

	if err := model.InsertPriceInspectionCoverageReports(rows); err != nil {
		return nil, err
	}
	return result, nil
}

func buildCoverageRow(generatedAt int64, sourceProvider string, aggregate channelModelAggregate, idx snapshotIndex, logs logAggregate) model.PriceInspectionCoverageReport {
	scenario := detectScenario(aggregate.ChannelType, aggregate.ModelName)
	channelTypeName := constant.GetChannelTypeName(aggregate.ChannelType)
	row := model.PriceInspectionCoverageReport{
		GeneratedAt:      generatedAt,
		SourceProvider:   sourceProvider,
		ChannelType:      aggregate.ChannelType,
		ChannelTypeName:  channelTypeName,
		ModelName:        aggregate.ModelName,
		Scenario:         scenario,
		ChannelCount:     len(aggregate.ChannelIDs),
		SampleLogCount:   logs.Count,
		LastSeenAt:       logs.LastSeenAt,
		LogContextStatus: LogContextNoSamples,
		RawJSON: common.MapToJsonStr(map[string]any{
			"channel_ids": aggregate.ChannelIDs,
		}),
	}
	if logs.Count > 0 {
		row.LogContextStatus = LogContextAvailable
	}

	if isScenarioOutOfScope(scenario) {
		row.MappingStatus = MappingNotRequired
		row.CalculatorStatus = CalculatorOutOfScope
		row.SupportLevel = SupportOutOfScope
		row.ReasonCode = reasonForOutOfScopeScenario(scenario)
		row.Suggestion = suggestionForOutOfScopeScenario(scenario)
		return row
	}

	sourceModelID, canonicalModelID, mappingStatus := resolveSourceModel(aggregate, sourceProvider, idx)
	row.SourceModelID = sourceModelID
	row.CanonicalModelID = canonicalModelID
	row.MappingStatus = mappingStatus

	if mappingStatus == MappingMissing {
		row.CalculatorStatus = CalculatorMissing
		row.SupportLevel = SupportUnsupported
		row.ReasonCode = "missing_model_mapping"
		row.Suggestion = "补充 price_model_mappings 或 openrouter_model_mappings，将本地模型名映射到 OpenRouter model id。"
		return row
	}

	if !isScenarioSupportedByRuntimeCalculator(scenario) {
		row.CalculatorStatus = CalculatorUnsupported
		row.SupportLevel = SupportUnsupported
		row.ReasonCode = reasonForUnsupportedScenario(scenario)
		row.Suggestion = suggestionForScenario(scenario)
		return row
	}

	priceSnapshot, snapshotMatchType, hasPriceSnapshot := findCoverageSnapshot(aggregate, sourceModelID, idx)
	row.RawJSON = coverageRawJSON(aggregate, logs, sourceProvider, priceSnapshot, snapshotMatchType, hasPriceSnapshot)
	applyRuntimeCoverageSupport(&row, logs, hasPriceSnapshot)
	return row
}

func coverageRawJSON(aggregate channelModelAggregate, logs logAggregate, priceSourceAdapter string, priceSnapshot model.PriceSourceSnapshot, snapshotMatchType string, hasPriceSnapshot bool) string {
	raw := map[string]any{
		"channel_ids":           aggregate.ChannelIDs,
		"billing_context_count": logs.BillingContextCount,
		"provider_cost_count":   logs.ProviderCostCount,
		"price_source_adapter":  priceSourceAdapter,
		"price_snapshot":        hasPriceSnapshot,
	}
	if hasPriceSnapshot {
		raw["price_snapshot_id"] = priceSnapshot.ID
		raw["price_snapshot_model_id"] = priceSnapshot.ModelID
		raw["price_snapshot_match_type"] = snapshotMatchType
		raw["price_snapshot_pricing_scheme"] = priceSnapshot.PricingScheme
	}
	return common.MapToJsonStr(raw)
}

func applyRuntimeCoverageSupport(row *model.PriceInspectionCoverageReport, logs logAggregate, hasPriceSnapshot bool) {
	if !isScenarioSupportedByRuntimeCalculator(row.Scenario) {
		row.CalculatorStatus = CalculatorUnsupported
		row.SupportLevel = SupportUnsupported
		row.ReasonCode = reasonForUnsupportedScenario(row.Scenario)
		row.Suggestion = suggestionForScenario(row.Scenario)
		return
	}
	row.CalculatorStatus = CalculatorSupported
	if logs.ProviderCostCount > 0 {
		row.SupportLevel = SupportStandard
		row.ReasonCode = "provider_usage_cost_available"
		row.Suggestion = "recent logs include provider_usage_cost, so exact inspection can compare expected quota with logs.quota"
		return
	}
	if hasPriceSnapshot && logs.Count > 0 {
		row.SupportLevel = SupportStandard
		row.ReasonCode = "price_snapshot_available"
		row.Suggestion = "price snapshot is available, so inspection can recompute expected quota from token details and compare logs.quota"
		return
	}
	if logs.BillingContextCount > 0 {
		row.SupportLevel = SupportStandard
		row.ReasonCode = "billing_context_available"
		row.Suggestion = "recent logs include billing context, so standard inspection can recompute expected quota and compare logs.quota"
		return
	}
	if logs.Count > 0 {
		row.SupportLevel = SupportUnsupported
		row.ReasonCode = "missing_billing_context"
		row.Suggestion = "recent consume logs exist but logs.other.billing is missing; inspect only newer logs or enrich billing context first"
		return
	}
	if hasPriceSnapshot {
		row.SupportLevel = SupportEstimated
		row.ReasonCode = "price_snapshot_available_no_recent_logs"
		row.Suggestion = "price snapshot is available, but recent sample logs are not available yet"
		return
	}
	row.SupportLevel = SupportEstimated
	row.ReasonCode = "no_recent_consume_logs"
	row.Suggestion = "calculator covers this scenario, but recent sample logs are not available yet"
}

func loadChannelModelAggregates(req GenerateCoverageRequest) ([]channelModelAggregate, error) {
	var channels []model.Channel
	tx := model.DB.Model(&model.Channel{}).Select("id, type, models")
	if req.ChannelType > 0 {
		tx = tx.Where("type = ?", req.ChannelType)
	} else if types := channelTypesForProvider(req.SourceProvider); len(types) > 0 {
		tx = tx.Where("type IN ?", types)
	}
	if err := tx.Find(&channels).Error; err != nil {
		return nil, err
	}

	byKey := map[string]*channelModelAggregate{}
	for _, ch := range channels {
		for _, modelName := range splitModels(ch.Models) {
			if req.ModelName != "" && modelName != req.ModelName {
				continue
			}
			key := coverageKey(ch.Type, modelName)
			item := byKey[key]
			if item == nil {
				item = &channelModelAggregate{ChannelType: ch.Type, ModelName: modelName}
				byKey[key] = item
			}
			item.ChannelIDs = append(item.ChannelIDs, ch.Id)
		}
	}

	rows := make([]channelModelAggregate, 0, len(byKey))
	for _, item := range byKey {
		sort.Ints(item.ChannelIDs)
		rows = append(rows, *item)
	}
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].ChannelType == rows[j].ChannelType {
			return rows[i].ModelName < rows[j].ModelName
		}
		return rows[i].ChannelType < rows[j].ChannelType
	})
	return rows, nil
}

func loadLogAggregates(aggregates []channelModelAggregate, windowDays int) map[string]logAggregate {
	out := map[string]logAggregate{}
	if len(aggregates) == 0 || model.LOG_DB == nil {
		return out
	}

	channelIDToType := map[int]int{}
	modelSet := map[string]bool{}
	channelIDs := make([]int, 0)
	for _, aggregate := range aggregates {
		modelSet[aggregate.ModelName] = true
		for _, channelID := range aggregate.ChannelIDs {
			if _, ok := channelIDToType[channelID]; !ok {
				channelIDs = append(channelIDs, channelID)
			}
			channelIDToType[channelID] = aggregate.ChannelType
		}
	}
	modelNames := make([]string, 0, len(modelSet))
	for modelName := range modelSet {
		modelNames = append(modelNames, modelName)
	}
	if len(channelIDs) == 0 || len(modelNames) == 0 {
		return out
	}

	type row struct {
		ChannelID           int
		ModelName           string
		Count               int64
		BillingContextCount int64
		ProviderCostCount   int64
		LastSeen            int64
	}
	var rows []row
	startAt := time.Now().Add(-time.Duration(windowDays) * 24 * time.Hour).Unix()
	err := model.LOG_DB.Model(&model.Log{}).
		Select(`channel_id, model_name, COUNT(*) AS count,
			SUM(CASE WHEN other LIKE ? THEN 1 ELSE 0 END) AS billing_context_count,
			SUM(CASE WHEN other LIKE ? OR other LIKE ? THEN 1 ELSE 0 END) AS provider_cost_count,
			MAX(created_at) AS last_seen`, "%\"billing\"%", "%\"provider_usage_cost\"%", "%\"openrouter_cost\"%").
		Where("type = ? AND created_at >= ? AND channel_id IN ? AND model_name IN ?", model.LogTypeConsume, startAt, channelIDs, modelNames).
		Group("channel_id, model_name").
		Scan(&rows).Error
	if err != nil {
		return out
	}

	for _, row := range rows {
		channelType, ok := channelIDToType[row.ChannelID]
		if !ok {
			continue
		}
		key := coverageKey(channelType, row.ModelName)
		current := out[key]
		current.Count += row.Count
		current.BillingContextCount += row.BillingContextCount
		current.ProviderCostCount += row.ProviderCostCount
		if row.LastSeen > current.LastSeenAt {
			current.LastSeenAt = row.LastSeen
		}
		out[key] = current
	}
	return out
}

func loadOpenRouterSnapshotIndex() (snapshotIndex, error) {
	idx := snapshotIndex{
		byModelID:        map[string]model.PriceSourceSnapshot{},
		byLocalModelName: map[string]model.PriceSourceSnapshot{},
		byNormalizedName: map[string]model.PriceSourceSnapshot{},
	}
	var genericSnapshots []model.PriceSourceSnapshot
	if err := model.DB.Where("source_provider = ?", ProviderOpenRouter).Order("fetched_at DESC, id DESC").Find(&genericSnapshots).Error; err != nil {
		return idx, err
	}
	for _, snapshot := range genericSnapshots {
		indexPriceSourceSnapshot(idx, snapshot)
	}
	var snapshots []model.OpenRouterPriceSnapshot
	if err := model.DB.Order("fetched_at DESC, id DESC").Find(&snapshots).Error; err != nil {
		return idx, err
	}
	for _, snapshot := range snapshots {
		priceSnapshot := priceSourceSnapshotFromOpenRouter(snapshot)
		indexPriceSourceSnapshot(idx, priceSnapshot)
	}
	return idx, nil
}

func loadPriceSourceSnapshotIndex(sourceProvider string) (snapshotIndex, error) {
	idx := snapshotIndex{
		byModelID:        map[string]model.PriceSourceSnapshot{},
		byLocalModelName: map[string]model.PriceSourceSnapshot{},
		byNormalizedName: map[string]model.PriceSourceSnapshot{},
	}
	var snapshots []model.PriceSourceSnapshot
	if err := model.DB.Where("source_provider = ?", sourceProvider).Order("fetched_at DESC, id DESC").Find(&snapshots).Error; err != nil {
		return idx, err
	}
	for _, snapshot := range snapshots {
		indexPriceSourceSnapshot(idx, snapshot)
	}
	return idx, nil
}

func indexPriceSourceSnapshot(idx snapshotIndex, snapshot model.PriceSourceSnapshot) {
	if snapshot.ModelID != "" {
		if _, ok := idx.byModelID[snapshot.ModelID]; !ok {
			idx.byModelID[snapshot.ModelID] = snapshot
		}
	}
	if snapshot.CanonicalModelID != "" {
		if _, ok := idx.byModelID[snapshot.CanonicalModelID]; !ok {
			idx.byModelID[snapshot.CanonicalModelID] = snapshot
		}
	}
	if snapshot.LocalModelName != "" {
		if _, ok := idx.byLocalModelName[snapshot.LocalModelName]; !ok {
			idx.byLocalModelName[snapshot.LocalModelName] = snapshot
		}
		normalized := normalizeModelName(snapshot.LocalModelName)
		if normalized != "" {
			if _, ok := idx.byNormalizedName[normalized]; !ok {
				idx.byNormalizedName[normalized] = snapshot
			}
		}
	}
}

func findCoverageSnapshot(aggregate channelModelAggregate, sourceModelID string, idx snapshotIndex) (model.PriceSourceSnapshot, string, bool) {
	if sourceModelID != "" {
		if snapshot, ok := idx.byModelID[sourceModelID]; ok {
			return snapshot, "source_model_id", true
		}
	}
	if aggregate.ModelName == "" {
		return model.PriceSourceSnapshot{}, "", false
	}
	if snapshot, ok := idx.byModelID[aggregate.ModelName]; ok {
		return snapshot, "model_id", true
	}
	if snapshot, ok := idx.byLocalModelName[aggregate.ModelName]; ok {
		return snapshot, "local_model_name", true
	}
	if snapshot, ok := idx.byNormalizedName[normalizeModelName(aggregate.ModelName)]; ok {
		return snapshot, "normalized_model_name", true
	}
	return model.PriceSourceSnapshot{}, "", false
}

func resolveSourceModel(aggregate channelModelAggregate, sourceProvider string, idx snapshotIndex) (string, string, string) {
	if sourceProvider != ProviderOpenRouter {
		if mapping, err := findGenericMapping(aggregate, sourceProvider); err == nil {
			return mapping.SourceModelID, firstNonEmpty(mapping.CanonicalModelID, mapping.SourceModelID), MappingExplicit
		}
		if snapshot, ok := idx.byModelID[aggregate.ModelName]; ok {
			return snapshot.ModelID, firstNonEmpty(snapshot.CanonicalModelID, snapshot.ModelID), MappingDirectModel
		}
		if snapshot, ok := idx.byLocalModelName[aggregate.ModelName]; ok {
			return snapshot.ModelID, firstNonEmpty(snapshot.CanonicalModelID, snapshot.ModelID), MappingDirectLocal
		}
		if snapshot, ok := idx.byNormalizedName[normalizeModelName(aggregate.ModelName)]; ok {
			return snapshot.ModelID, firstNonEmpty(snapshot.CanonicalModelID, snapshot.ModelID), MappingNormalized
		}
		return aggregate.ModelName, aggregate.ModelName, MappingDirectLocal
	}

	if mapping, err := findGenericMapping(aggregate, sourceProvider); err == nil {
		return mapping.SourceModelID, firstNonEmpty(mapping.CanonicalModelID, mapping.SourceModelID), MappingExplicit
	}
	if mapping, err := findOpenRouterMapping(aggregate); err == nil {
		return mapping.OpenRouterModel, mapping.OpenRouterModel, MappingExplicit
	}
	if snapshot, ok := idx.byModelID[aggregate.ModelName]; ok {
		return snapshot.ModelID, firstNonEmpty(snapshot.CanonicalModelID, snapshot.ModelID), MappingDirectModel
	}
	if snapshot, ok := idx.byLocalModelName[aggregate.ModelName]; ok {
		return snapshot.ModelID, firstNonEmpty(snapshot.CanonicalModelID, snapshot.ModelID), MappingDirectLocal
	}
	if snapshot, ok := idx.byNormalizedName[normalizeModelName(aggregate.ModelName)]; ok {
		return snapshot.ModelID, firstNonEmpty(snapshot.CanonicalModelID, snapshot.ModelID), MappingNormalized
	}
	return "", "", MappingMissing
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func findGenericMapping(aggregate channelModelAggregate, sourceProvider string) (*model.PriceModelMapping, error) {
	if model.DB == nil {
		return nil, gorm.ErrRecordNotFound
	}
	var mapping model.PriceModelMapping
	err := model.DB.Where(
		"enabled = ? AND source_provider = ? AND local_model_name = ? AND (channel_id IN ? OR channel_id = 0) AND (channel_type = ? OR channel_type = 0)",
		true, sourceProvider, aggregate.ModelName, aggregate.ChannelIDs, aggregate.ChannelType,
	).Order("channel_id DESC, channel_type DESC, priority DESC, id DESC").First(&mapping).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, err
	}
	return &mapping, err
}

func findOpenRouterMapping(aggregate channelModelAggregate) (*model.OpenRouterModelMapping, error) {
	if model.DB == nil {
		return nil, gorm.ErrRecordNotFound
	}
	var mapping model.OpenRouterModelMapping
	err := model.DB.Where(
		"enabled = ? AND local_model_name = ? AND (channel_id IN ? OR channel_id = 0)",
		true, aggregate.ModelName, aggregate.ChannelIDs,
	).Order("channel_id DESC, priority DESC, id DESC").First(&mapping).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, err
	}
	return &mapping, err
}

func detectScenario(channelType int, modelName string) string {
	name := normalizeModelName(modelName)
	switch channelType {
	case constant.ChannelTypeKling, constant.ChannelTypeVidu, constant.ChannelTypeDoubaoVideo, constant.ChannelTypeSora:
		return "video_task"
	case constant.ChannelTypeMidjourney, constant.ChannelTypeMidjourneyPlus, constant.ChannelTypeJimeng:
		return "image_generation"
	case constant.ChannelTypeSunoAPI:
		return "audio_task"
	}
	if strings.Contains(name, "embedding") || strings.Contains(name, "embed") || strings.Contains(name, "text004") {
		return "embedding"
	}
	if strings.Contains(name, "rerank") {
		return "rerank"
	}
	if strings.Contains(name, "kling") || strings.Contains(name, "vidu") || strings.Contains(name, "sora") || strings.Contains(name, "video") {
		return "video_task"
	}
	if strings.Contains(name, "image") || strings.Contains(name, "imagen") || strings.Contains(name, "dalle") || strings.Contains(name, "gptimage") {
		return "image_generation"
	}
	if strings.Contains(name, "audio") || strings.Contains(name, "tts") || strings.Contains(name, "speech") || strings.Contains(name, "suno") {
		return "audio_task"
	}
	return "text_token"
}

func isScenarioSupportedForFirstPhase(scenario string) bool {
	return scenario == "text_token"
}

func isScenarioSupportedByRuntimeCalculator(scenario string) bool {
	switch scenario {
	case "text_token", "vision_input", "image_generation", "tool_call", "audio":
		return true
	default:
		return false
	}
}

func isScenarioOutOfScope(scenario string) bool {
	return scenario == "video_task"
}

func reasonForOutOfScopeScenario(scenario string) string {
	switch scenario {
	case "video_task":
		return "out_of_scope_video_task"
	default:
		return "out_of_scope"
	}
}

func suggestionForOutOfScopeScenario(scenario string) string {
	switch scenario {
	case "video_task":
		return "可灵、Vidu、Sora、DoubaoVideo 等视频/任务型模型当前不纳入价格巡检支持范围。"
	default:
		return "该场景当前不纳入价格巡检支持范围。"
	}
}

func reasonForUnsupportedScenario(scenario string) string {
	switch scenario {
	case "image_generation":
		return "unsupported_image_tokens"
	case "video_task":
		return "unsupported_video_task_pricing"
	case "audio_task":
		return "unsupported_audio_tokens"
	case "embedding":
		return "unsupported_embedding_pricing"
	case "rerank":
		return "unsupported_rerank_pricing"
	default:
		return "unsupported_calculator"
	}
}

func suggestionForScenario(scenario string) string {
	switch scenario {
	case "image_generation":
		return "补充图像输入/输出 token、图片数量/尺寸/质量或 provider usage cost 后，再接入 image calculator。"
	case "video_task":
		return "补充任务参数和 provider 价格源，按秒数、清晰度、模式、生成数量实现 video_task calculator。"
	case "audio_task":
		return "补充音频输入/输出 token、时长或按次价格后，再接入 audio calculator。"
	case "embedding":
		return "接入 embedding 独立价格字段和 embedding_input_tokens。"
	case "rerank":
		return "接入 rerank 独立价格字段和请求文档数量/token 明细。"
	default:
		return "实现对应场景的 Calculator，并补齐日志计费上下文。"
	}
}

func splitModels(raw string) []string {
	parts := strings.Split(strings.Trim(raw, ","), ",")
	out := make([]string, 0, len(parts))
	seen := map[string]bool{}
	for _, part := range parts {
		modelName := strings.TrimSpace(part)
		if modelName == "" || seen[modelName] {
			continue
		}
		seen[modelName] = true
		out = append(out, modelName)
	}
	return out
}

func normalizeProvider(provider string) string {
	normalized := strings.ToLower(strings.TrimSpace(provider))
	normalized = strings.ReplaceAll(normalized, "_", "")
	normalized = strings.ReplaceAll(normalized, "-", "")
	switch normalized {
	case "openrouter":
		return ProviderOpenRouter
	case "openai", "openaimax":
		return "openai"
	case "azure", "azureopenai":
		return "azure"
	case "anthropic", "claude":
		return "anthropic"
	case "google", "gemini", "vertex", "vertexai":
		return "google"
	default:
		return strings.ToLower(strings.TrimSpace(provider))
	}
}

func normalizeModelName(modelName string) string {
	normalized := strings.ToLower(strings.TrimSpace(modelName))
	replacer := strings.NewReplacer(" ", "", "_", "", "-", "", ".", "", "/", "", ":", "")
	return replacer.Replace(normalized)
}

func coverageKey(channelType int, modelName string) string {
	return fmt.Sprintf("%d:%s", channelType, modelName)
}
