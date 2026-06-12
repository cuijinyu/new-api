package price_inspection

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/model"
	openrouterinspection "github.com/QuantumNous/new-api/service/openrouter_inspection"
)

var ErrPriceSourceUnsupported = errors.New("price source adapter is not implemented")

type PriceSourceInfo struct {
	Provider                  string `json:"provider"`
	DisplayName               string `json:"display_name"`
	Status                    string `json:"status"`
	HealthStatus              string `json:"health_status"`
	FetchSupported            bool   `json:"fetch_supported"`
	SnapshotSupported         bool   `json:"snapshot_supported"`
	ExactLogCostSupported     bool   `json:"exact_log_cost_supported"`
	StandardBillingSupported  bool   `json:"standard_billing_supported"`
	SnapshotCount             int64  `json:"snapshot_count"`
	LatestSnapshotAt          int64  `json:"latest_snapshot_at"`
	SnapshotAgeSeconds        int64  `json:"snapshot_age_seconds"`
	SnapshotStaleAfterSeconds int64  `json:"snapshot_stale_after_seconds"`
	SnapshotStale             bool   `json:"snapshot_stale"`
	DefaultScheduledProvider  bool   `json:"default_scheduled_provider"`
	Note                      string `json:"note"`
}

type FetchSourcePricesResult struct {
	Provider  string `json:"provider"`
	FetchedAt int64  `json:"fetched_at"`
	Count     int    `json:"count"`
}

type PriceFetchScheduleOptions struct {
	IntervalHours   int
	SourceProviders []string
	RetentionDays   int
}

type SnapshotQuery struct {
	SourceProvider string
	ModelID        string
	LocalModelName string
	FetchedStart   int64
	FetchedEnd     int64
	Page           int
	PageSize       int
}

type SnapshotMutationRequest struct {
	SourceProvider            string  `json:"source_provider"`
	FetchedAt                 int64   `json:"fetched_at"`
	ModelID                   string  `json:"model_id"`
	CanonicalModelID          string  `json:"canonical_model_id"`
	LocalModelName            string  `json:"local_model_name"`
	Scenario                  string  `json:"scenario"`
	PricingScheme             string  `json:"pricing_scheme"`
	Currency                  string  `json:"currency"`
	Unit                      string  `json:"unit"`
	InputPricePerToken        float64 `json:"input_price_per_token"`
	OutputPricePerToken       float64 `json:"output_price_per_token"`
	CacheReadPricePerToken    float64 `json:"cache_read_price_per_token"`
	CacheWritePricePerToken   float64 `json:"cache_write_price_per_token"`
	CacheWrite5mPricePerToken float64 `json:"cache_write_5m_price_per_token"`
	CacheWrite1hPricePerToken float64 `json:"cache_write_1h_price_per_token"`
	InputImagePricePerToken   float64 `json:"input_image_price_per_token"`
	OutputImagePricePerToken  float64 `json:"output_image_price_per_token"`
	InputAudioPricePerToken   float64 `json:"input_audio_price_per_token"`
	OutputAudioPricePerToken  float64 `json:"output_audio_price_per_token"`
	ImagePrice                float64 `json:"image_price"`
	RequestPrice              float64 `json:"request_price"`
	PricePerSecond            float64 `json:"price_per_second"`
	IsFree                    bool    `json:"is_free"`
	RawJSON                   string  `json:"raw_json"`
}

type SnapshotBatchRequest struct {
	SourceProvider string                    `json:"source_provider"`
	Snapshots      []SnapshotMutationRequest `json:"snapshots"`
}

type SnapshotBatchResult struct {
	Count     int                         `json:"count"`
	Snapshots []model.PriceSourceSnapshot `json:"snapshots"`
}

func ListPriceSources() ([]PriceSourceInfo, error) {
	now := time.Now().Unix()
	staleAfterSeconds := int64(common.GetEnvOrDefault("PRICE_INSPECTION_PRICE_SOURCE_STALE_HOURS", 24) * 3600)
	if staleAfterSeconds < 0 {
		staleAfterSeconds = 0
	}
	sources := []PriceSourceInfo{
		{
			Provider:                 ProviderOpenRouter,
			DisplayName:              "OpenRouter",
			Status:                   "implemented",
			FetchSupported:           true,
			SnapshotSupported:        true,
			ExactLogCostSupported:    true,
			StandardBillingSupported: true,
			DefaultScheduledProvider: true,
			Note:                     "支持价格快照拉取，也支持基于日志 provider_usage_cost 的 exact 巡检。",
		},
		{
			Provider:                 "openai",
			DisplayName:              "OpenAI",
			Status:                   "implemented",
			FetchSupported:           true,
			SnapshotSupported:        true,
			ExactLogCostSupported:    true,
			StandardBillingSupported: true,
			DefaultScheduledProvider: true,
			Note:                     "支持内置官方价格 catalog，也支持通过外部 JSON catalog 覆盖；新日志包含 provider_usage_cost 时可做 exact 巡检。",
		},
		{
			Provider:                 "anthropic",
			DisplayName:              "Anthropic / Claude",
			Status:                   "implemented",
			FetchSupported:           true,
			SnapshotSupported:        true,
			ExactLogCostSupported:    true,
			StandardBillingSupported: true,
			DefaultScheduledProvider: true,
			Note:                     "支持内置 Claude token/cache 官方价格 catalog，也支持通过外部 JSON catalog 覆盖。",
		},
		{
			Provider:                 "google",
			DisplayName:              "Google / Gemini / VertexAI",
			Status:                   "implemented",
			FetchSupported:           true,
			SnapshotSupported:        true,
			ExactLogCostSupported:    true,
			StandardBillingSupported: true,
			DefaultScheduledProvider: true,
			Note:                     "支持内置 Gemini token/image 官方价格 catalog，也支持通过外部 JSON catalog 覆盖。",
		},
		{
			Provider:                 "azure",
			DisplayName:              "Azure OpenAI",
			Status:                   "pending_adapter",
			SnapshotSupported:        true,
			ExactLogCostSupported:    true,
			StandardBillingSupported: true,
			DefaultScheduledProvider: false,
			Note:                     "Azure 区域价格源 adapter 尚未实现；可维护手工价格快照，新日志包含 provider_usage_cost 时可做 exact 巡检。",
		},
	}
	for i := range sources {
		genericCount, genericLatest, err := model.GetPriceSourceSnapshotStats(sources[i].Provider)
		if err != nil {
			return nil, err
		}
		sources[i].SnapshotCount = genericCount
		sources[i].LatestSnapshotAt = genericLatest
		if sources[i].Provider == ProviderOpenRouter && genericCount == 0 {
			legacyCount, legacyLatest, err := model.GetOpenRouterPriceSnapshotStats()
			if err != nil {
				return nil, err
			}
			sources[i].SnapshotCount = legacyCount
			sources[i].LatestSnapshotAt = legacyLatest
		}
		applyPriceSourceHealth(&sources[i], now, staleAfterSeconds)
	}
	return sources, nil
}

func applyPriceSourceHealth(source *PriceSourceInfo, now int64, staleAfterSeconds int64) {
	source.SnapshotStaleAfterSeconds = staleAfterSeconds
	if source.SnapshotCount <= 0 || source.LatestSnapshotAt <= 0 {
		if source.SnapshotSupported {
			source.HealthStatus = "no_snapshot"
		} else {
			source.HealthStatus = "unsupported"
		}
		return
	}
	age := now - source.LatestSnapshotAt
	if age < 0 {
		age = 0
	}
	source.SnapshotAgeSeconds = age
	if staleAfterSeconds > 0 && age > staleAfterSeconds {
		source.SnapshotStale = true
		source.HealthStatus = "stale"
		return
	}
	source.HealthStatus = "ok"
}

func FetchSourcePrices(ctx context.Context, provider string) (*FetchSourcePricesResult, error) {
	provider = normalizeProvider(provider)
	switch provider {
	case ProviderOpenRouter:
		result, err := openrouterinspection.FetchAndStorePriceSnapshots(ctx)
		if err != nil {
			return nil, err
		}
		if err := syncOpenRouterSnapshotsToGeneric(result.FetchedAt); err != nil {
			return nil, err
		}
		return &FetchSourcePricesResult{
			Provider:  ProviderOpenRouter,
			FetchedAt: result.FetchedAt,
			Count:     result.Count,
		}, nil
	case "openai", "anthropic", "google":
		return FetchCatalogSourcePrices(ctx, provider)
	case "":
		return nil, fmt.Errorf("source_provider is required")
	default:
		return nil, fmt.Errorf("%w for provider %s", ErrPriceSourceUnsupported, provider)
	}
}

func syncOpenRouterSnapshotsToGeneric(fetchedAt int64) error {
	if fetchedAt <= 0 {
		return nil
	}
	var rows []model.OpenRouterPriceSnapshot
	if err := model.DB.Where("fetched_at = ?", fetchedAt).Order("id ASC").Find(&rows).Error; err != nil {
		return err
	}
	if len(rows) == 0 {
		return nil
	}
	modelIDs := make([]string, 0, len(rows))
	for _, row := range rows {
		if strings.TrimSpace(row.ModelID) != "" {
			modelIDs = append(modelIDs, row.ModelID)
		}
	}
	existing := map[string]bool{}
	if len(modelIDs) > 0 {
		var existingRows []model.PriceSourceSnapshot
		if err := model.DB.Model(&model.PriceSourceSnapshot{}).
			Select("model_id").
			Where("source_provider = ? AND fetched_at = ? AND model_id IN ?", ProviderOpenRouter, fetchedAt, modelIDs).
			Find(&existingRows).Error; err != nil {
			return err
		}
		for _, row := range existingRows {
			existing[row.ModelID] = true
		}
	}
	genericRows := make([]model.PriceSourceSnapshot, 0, len(rows))
	for _, row := range rows {
		if row.ModelID == "" || existing[row.ModelID] {
			continue
		}
		snapshot := priceSourceSnapshotFromOpenRouter(row)
		snapshot.ID = 0
		snapshot.CreatedAt = 0
		snapshot.Manual = false
		genericRows = append(genericRows, snapshot)
	}
	return model.InsertPriceSourceSnapshots(genericRows)
}

func DefaultScheduledPriceSourceProviders() []string {
	return []string{ProviderOpenRouter, "openai", "anthropic", "google"}
}

func StartScheduledPriceSourceFetcher(ctx context.Context, opts PriceFetchScheduleOptions) {
	if opts.IntervalHours <= 0 {
		opts.IntervalHours = 6
	}
	if len(opts.SourceProviders) == 0 {
		opts.SourceProviders = DefaultScheduledPriceSourceProviders()
	}
	ticker := time.NewTicker(time.Duration(opts.IntervalHours) * time.Hour)
	go func() {
		defer ticker.Stop()
		runScheduledPriceSourceFetch(ctx, opts.SourceProviders, opts.RetentionDays)
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				runScheduledPriceSourceFetch(ctx, opts.SourceProviders, opts.RetentionDays)
			}
		}
	}()
}

func runScheduledPriceSourceFetch(ctx context.Context, providers []string, retentionDays int) {
	for _, provider := range scheduledPriceSourceProviders(providers) {
		result, err := FetchSourcePrices(ctx, provider)
		if err != nil {
			if errors.Is(err, ErrPriceSourceUnsupported) {
				continue
			}
			common.SysError("price source fetch failed for " + provider + ": " + err.Error())
			continue
		}
		common.SysLog(fmt.Sprintf("price source fetched for %s: count=%d fetched_at=%d", result.Provider, result.Count, result.FetchedAt))
	}
	cleanupAutomaticPriceSourceSnapshots(retentionDays)
}

func scheduledPriceSourceProviders(providers []string) []string {
	if len(providers) == 0 {
		providers = DefaultScheduledPriceSourceProviders()
	}
	out := make([]string, 0, len(providers))
	seen := map[string]bool{}
	for _, provider := range providers {
		provider = normalizeProvider(provider)
		if provider == "" || seen[provider] {
			continue
		}
		seen[provider] = true
		out = append(out, provider)
	}
	return out
}

func cleanupAutomaticPriceSourceSnapshots(retentionDays int) {
	if retentionDays <= 0 {
		return
	}
	before := time.Now().Add(-time.Duration(retentionDays) * 24 * time.Hour).Unix()
	rows, err := model.DeleteAutomaticPriceSourceSnapshotsBefore("", before)
	if err != nil {
		common.SysError("price source snapshot cleanup failed: " + err.Error())
		return
	}
	if rows > 0 {
		common.SysLog(fmt.Sprintf("price source snapshot cleanup deleted %d automatic snapshots before %d", rows, before))
	}
}

func CreatePriceSnapshot(req SnapshotMutationRequest) (*model.PriceSourceSnapshot, error) {
	snapshot, err := buildPriceSnapshot(req)
	if err != nil {
		return nil, err
	}
	if err := model.CreatePriceSourceSnapshot(snapshot); err != nil {
		return nil, err
	}
	return snapshot, nil
}

func CreatePriceSnapshots(req SnapshotBatchRequest) (*SnapshotBatchResult, error) {
	provider := normalizeProvider(req.SourceProvider)
	if len(req.Snapshots) == 0 {
		return nil, fmt.Errorf("snapshots is required")
	}
	if len(req.Snapshots) > 500 {
		return nil, fmt.Errorf("snapshots limit is 500")
	}
	rows := make([]model.PriceSourceSnapshot, 0, len(req.Snapshots))
	for i, item := range req.Snapshots {
		if strings.TrimSpace(item.SourceProvider) == "" {
			item.SourceProvider = provider
		}
		snapshot, err := buildPriceSnapshot(item)
		if err != nil {
			return nil, fmt.Errorf("snapshot[%d]: %w", i, err)
		}
		rows = append(rows, *snapshot)
	}
	if err := model.InsertPriceSourceSnapshots(rows); err != nil {
		return nil, err
	}
	return &SnapshotBatchResult{
		Count:     len(rows),
		Snapshots: rows,
	}, nil
}

func buildPriceSnapshot(req SnapshotMutationRequest) (*model.PriceSourceSnapshot, error) {
	provider := normalizeProvider(req.SourceProvider)
	if provider == "" {
		return nil, fmt.Errorf("source_provider is required")
	}
	modelID := strings.TrimSpace(req.ModelID)
	localModelName := strings.TrimSpace(req.LocalModelName)
	if modelID == "" && localModelName == "" {
		return nil, fmt.Errorf("model_id or local_model_name is required")
	}
	if err := validateSnapshotMutationRequest(req, "manual price snapshot"); err != nil {
		return nil, err
	}
	fetchedAt := req.FetchedAt
	if fetchedAt <= 0 {
		fetchedAt = time.Now().Unix()
	}
	currency := strings.ToUpper(strings.TrimSpace(req.Currency))
	if currency == "" {
		currency = "USD"
	}
	scenario := strings.TrimSpace(req.Scenario)
	if scenario == "" {
		scenario = detectScenario(0, firstNonEmpty(modelID, localModelName))
	}
	pricingScheme := strings.TrimSpace(req.PricingScheme)
	if pricingScheme == "" {
		pricingScheme = inferPricingScheme(req)
	}
	unit := strings.TrimSpace(req.Unit)
	if unit == "" {
		unit = defaultUnitForPricingScheme(pricingScheme)
	}
	snapshot := &model.PriceSourceSnapshot{
		SourceProvider:            provider,
		FetchedAt:                 fetchedAt,
		ModelID:                   modelID,
		CanonicalModelID:          strings.TrimSpace(req.CanonicalModelID),
		LocalModelName:            localModelName,
		Scenario:                  scenario,
		PricingScheme:             pricingScheme,
		Currency:                  currency,
		Unit:                      unit,
		InputPricePerToken:        req.InputPricePerToken,
		OutputPricePerToken:       req.OutputPricePerToken,
		CacheReadPricePerToken:    req.CacheReadPricePerToken,
		CacheWritePricePerToken:   req.CacheWritePricePerToken,
		CacheWrite5mPricePerToken: req.CacheWrite5mPricePerToken,
		CacheWrite1hPricePerToken: req.CacheWrite1hPricePerToken,
		InputImagePricePerToken:   req.InputImagePricePerToken,
		OutputImagePricePerToken:  req.OutputImagePricePerToken,
		InputAudioPricePerToken:   req.InputAudioPricePerToken,
		OutputAudioPricePerToken:  req.OutputAudioPricePerToken,
		ImagePrice:                req.ImagePrice,
		RequestPrice:              req.RequestPrice,
		PricePerSecond:            req.PricePerSecond,
		IsFree:                    req.IsFree,
		Manual:                    true,
		RawJSON:                   strings.TrimSpace(req.RawJSON),
	}
	if snapshot.CanonicalModelID == "" {
		snapshot.CanonicalModelID = snapshot.ModelID
	}
	return snapshot, nil
}

func DeletePriceSnapshot(id int64) error {
	if id <= 0 {
		return fmt.Errorf("snapshot id is required")
	}
	snapshot, err := model.GetPriceSourceSnapshotByID(id)
	if err != nil {
		return err
	}
	if !snapshot.Manual {
		return fmt.Errorf("only manual price snapshots can be deleted")
	}
	return model.DeletePriceSourceSnapshot(id)
}

func GetPriceSnapshots(query SnapshotQuery) ([]model.PriceSourceSnapshot, int64, error) {
	provider := normalizeProvider(query.SourceProvider)
	if provider == "" {
		provider = ProviderOpenRouter
	}
	if query.Page <= 0 {
		query.Page = 1
	}
	if query.PageSize <= 0 {
		query.PageSize = 10
	}
	if provider != ProviderOpenRouter {
		return model.GetPriceSourceSnapshots(
			provider,
			query.ModelID,
			query.LocalModelName,
			query.FetchedStart,
			query.FetchedEnd,
			query.Page,
			query.PageSize,
		)
	}
	genericRows, genericTotal, err := model.GetPriceSourceSnapshots(
		provider,
		query.ModelID,
		query.LocalModelName,
		query.FetchedStart,
		query.FetchedEnd,
		query.Page,
		query.PageSize,
	)
	if err != nil {
		return nil, 0, err
	}
	if genericTotal > 0 {
		return genericRows, genericTotal, nil
	}
	openRouterRows, total, err := model.GetOpenRouterPriceSnapshots(
		query.ModelID,
		query.LocalModelName,
		query.FetchedStart,
		query.FetchedEnd,
		query.Page,
		query.PageSize,
	)
	if err != nil {
		return nil, 0, err
	}
	rows := make([]model.PriceSourceSnapshot, 0, len(openRouterRows))
	for _, row := range openRouterRows {
		rows = append(rows, priceSourceSnapshotFromOpenRouter(row))
	}
	return rows, total, nil
}

func inferPricingScheme(req SnapshotMutationRequest) string {
	if req.PricePerSecond > 0 {
		return "per_second"
	}
	if req.RequestPrice > 0 {
		return "per_request"
	}
	if req.ImagePrice > 0 {
		return "per_image"
	}
	return "per_token"
}

func defaultUnitForPricingScheme(pricingScheme string) string {
	switch pricingScheme {
	case "per_second":
		return "second"
	case "per_request":
		return "request"
	case "per_image":
		return "image"
	default:
		return "token"
	}
}

func priceSourceSnapshotFromOpenRouter(row model.OpenRouterPriceSnapshot) model.PriceSourceSnapshot {
	scenario := detectScenario(0, row.ModelID)
	if scenario == "text_token" && row.ImagePrice > 0 {
		scenario = "image_generation"
	}
	pricingScheme := "per_token"
	if row.RequestPrice > 0 {
		pricingScheme = "per_request"
	}
	if row.ImagePrice > 0 {
		pricingScheme = "per_image"
	}
	return model.PriceSourceSnapshot{
		ID:                      row.ID,
		SourceProvider:          ProviderOpenRouter,
		FetchedAt:               row.FetchedAt,
		ModelID:                 row.ModelID,
		CanonicalModelID:        row.CanonicalSlug,
		LocalModelName:          row.LocalModelName,
		Scenario:                scenario,
		PricingScheme:           pricingScheme,
		Currency:                "USD",
		Unit:                    "token",
		InputPricePerToken:      row.PromptPricePerToken,
		OutputPricePerToken:     row.CompletionPricePerToken,
		CacheReadPricePerToken:  row.CacheReadPricePerToken,
		CacheWritePricePerToken: row.CacheWritePricePerToken,
		ImagePrice:              row.ImagePrice,
		RequestPrice:            row.RequestPrice,
		IsFree:                  row.IsFree,
		RawJSON:                 row.RawJSON,
		CreatedAt:               row.CreatedAt,
	}
}
