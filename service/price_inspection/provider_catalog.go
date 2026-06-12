package price_inspection

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/model"
)

const (
	pricePerMillionDivisor = 1000000
	builtInCatalogVersion  = "2026-06-09"
)

type catalogSnapshotPayload struct {
	CatalogVersion string                    `json:"catalog_version"`
	SourceURL      string                    `json:"source_url"`
	Snapshots      []SnapshotMutationRequest `json:"snapshots"`
}

type catalogSnapshotBundle struct {
	Requests []SnapshotMutationRequest
	Source   catalogMetadata
}

type catalogMetadata struct {
	Kind    string `json:"catalog_source_kind"`
	URL     string `json:"catalog_source_url,omitempty"`
	Version string `json:"catalog_version,omitempty"`
}

func FetchCatalogSourcePrices(ctx context.Context, provider string) (*FetchSourcePricesResult, error) {
	provider = normalizeProvider(provider)
	if provider == "" {
		return nil, fmt.Errorf("source_provider is required")
	}
	if !isCatalogPriceProvider(provider) {
		return nil, fmt.Errorf("%w for provider %s", ErrPriceSourceUnsupported, provider)
	}
	fetchedAt := time.Now().Unix()
	bundle, err := loadCatalogSnapshotRequests(ctx, provider)
	if err != nil {
		return nil, err
	}
	rows := make([]model.PriceSourceSnapshot, 0, len(bundle.Requests))
	for i, req := range bundle.Requests {
		req.SourceProvider = provider
		req.FetchedAt = fetchedAt
		req.RawJSON = mergeCatalogRawJSON(req.RawJSON, provider, fetchedAt, bundle.Source)
		if err := validateCatalogSnapshotRequest(req); err != nil {
			return nil, fmt.Errorf("catalog snapshot[%d]: %w", i, err)
		}
		snapshot, err := buildPriceSnapshot(req)
		if err != nil {
			return nil, fmt.Errorf("catalog snapshot[%d]: %w", i, err)
		}
		snapshot.Manual = false
		rows = append(rows, *snapshot)
	}
	if err := model.InsertPriceSourceSnapshots(rows); err != nil {
		return nil, err
	}
	return &FetchSourcePricesResult{
		Provider:  provider,
		FetchedAt: fetchedAt,
		Count:     len(rows),
	}, nil
}

func isCatalogPriceProvider(provider string) bool {
	switch normalizeProvider(provider) {
	case "openai", "anthropic", "google":
		return true
	default:
		return false
	}
}

func loadCatalogSnapshotRequests(ctx context.Context, provider string) (*catalogSnapshotBundle, error) {
	if url := strings.TrimSpace(os.Getenv(catalogURLEnvName(provider))); url != "" {
		return fetchCatalogSnapshotRequests(ctx, provider, url)
	}
	return &catalogSnapshotBundle{
		Requests: builtInCatalogSnapshotRequests(provider),
		Source: catalogMetadata{
			Kind:    "builtin_common_model_catalog",
			Version: builtInCatalogVersion,
		},
	}, nil
}

func catalogURLEnvName(provider string) string {
	switch normalizeProvider(provider) {
	case "openai":
		return "PRICE_INSPECTION_OPENAI_PRICE_CATALOG_URL"
	case "anthropic":
		return "PRICE_INSPECTION_ANTHROPIC_PRICE_CATALOG_URL"
	case "google":
		return "PRICE_INSPECTION_GOOGLE_PRICE_CATALOG_URL"
	default:
		return "PRICE_INSPECTION_PRICE_CATALOG_URL"
	}
}

func fetchCatalogSnapshotRequests(ctx context.Context, provider, url string) (*catalogSnapshotBundle, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("price catalog fetch for %s returned HTTP %d", provider, resp.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if err != nil {
		return nil, err
	}
	bundle, err := decodeCatalogSnapshotRequests(body)
	if err != nil {
		return nil, err
	}
	if len(bundle.Requests) == 0 {
		return nil, fmt.Errorf("price catalog for %s is empty", provider)
	}
	bundle.Source.Kind = "external_json_catalog"
	if bundle.Source.URL == "" {
		bundle.Source.URL = url
	}
	return bundle, nil
}

func decodeCatalogSnapshotRequests(body []byte) (*catalogSnapshotBundle, error) {
	var payload catalogSnapshotPayload
	if err := json.Unmarshal(body, &payload); err == nil && len(payload.Snapshots) > 0 {
		return &catalogSnapshotBundle{
			Requests: payload.Snapshots,
			Source: catalogMetadata{
				Version: strings.TrimSpace(payload.CatalogVersion),
				URL:     strings.TrimSpace(payload.SourceURL),
			},
		}, nil
	}
	var requests []SnapshotMutationRequest
	if err := json.Unmarshal(body, &requests); err != nil {
		return nil, err
	}
	return &catalogSnapshotBundle{Requests: requests}, nil
}

func validateCatalogSnapshotRequest(req SnapshotMutationRequest) error {
	if err := validateSnapshotMutationRequest(req, "price inspection catalog"); err != nil {
		return err
	}
	return nil
}

func validateSnapshotMutationRequest(req SnapshotMutationRequest, scope string) error {
	scenario := strings.TrimSpace(req.Scenario)
	if scenario == "" {
		scenario = detectScenario(0, firstNonEmpty(req.ModelID, req.LocalModelName, req.CanonicalModelID))
	}
	if isScenarioOutOfScope(scenario) {
		if scope == "" {
			scope = "price inspection snapshot"
		}
		return fmt.Errorf("scenario %s is out of scope for %s", scenario, scope)
	}
	prices := []float64{
		req.InputPricePerToken,
		req.OutputPricePerToken,
		req.CacheReadPricePerToken,
		req.CacheWritePricePerToken,
		req.CacheWrite5mPricePerToken,
		req.CacheWrite1hPricePerToken,
		req.InputImagePricePerToken,
		req.OutputImagePricePerToken,
		req.InputAudioPricePerToken,
		req.OutputAudioPricePerToken,
		req.ImagePrice,
		req.RequestPrice,
		req.PricePerSecond,
	}
	hasPrice := false
	for _, price := range prices {
		if price < 0 {
			return fmt.Errorf("price fields cannot be negative")
		}
		if price > 0 {
			hasPrice = true
		}
	}
	if !hasPrice && !req.IsFree {
		return fmt.Errorf("at least one positive price or is_free=true is required")
	}
	return nil
}

func mergeCatalogRawJSON(raw string, provider string, fetchedAt int64, source catalogMetadata) string {
	metadata := map[string]any{
		"source_provider":     provider,
		"catalog_source_kind": source.Kind,
		"catalog_fetched_at":  fetchedAt,
		"catalog_version":     source.Version,
		"catalog_source_url":  source.URL,
		"catalog_schema":      "price_source_snapshot.v1",
		"catalog_prices_unit": "USD per token unless unit/pricing_scheme says otherwise",
		"catalog_maintenance": "external catalog URL is preferred for production price changes",
	}
	if strings.TrimSpace(raw) == "" {
		body, _ := json.Marshal(metadata)
		return string(body)
	}
	var obj map[string]any
	if err := json.Unmarshal([]byte(raw), &obj); err != nil {
		obj = map[string]any{"raw": raw}
	}
	for key, value := range metadata {
		if value == "" || value == int64(0) {
			continue
		}
		if _, ok := obj[key]; !ok {
			obj[key] = value
		}
	}
	body, _ := json.Marshal(obj)
	return string(body)
}

func builtInCatalogSnapshotRequests(provider string) []SnapshotMutationRequest {
	switch normalizeProvider(provider) {
	case "openai":
		return openAICatalogSnapshotRequests()
	case "anthropic":
		return anthropicCatalogSnapshotRequests()
	case "google":
		return googleCatalogSnapshotRequests()
	default:
		return nil
	}
}

func openAICatalogSnapshotRequests() []SnapshotMutationRequest {
	return []SnapshotMutationRequest{
		textCatalogSnapshot("gpt-5.5", "gpt-5.5", 5, 30, 0.5, officialRaw("https://openai.com/api/pricing/", "builtin official catalog; verify before relying on historical back-pricing")),
		textCatalogSnapshot("gpt-5.4", "gpt-5.4", 2.5, 15, 0.25, officialRaw("https://openai.com/api/pricing/", "builtin official catalog; verify before relying on historical back-pricing")),
		textCatalogSnapshot("gpt-5.4-mini", "gpt-5.4-mini", 0.75, 4.5, 0.075, officialRaw("https://openai.com/api/pricing/", "builtin official catalog; verify before relying on historical back-pricing")),
		textCatalogSnapshot("gpt-5.1", "gpt-5.1", 1.25, 10, 0.125, officialRaw("https://openai.com/api/pricing/", "builtin official catalog; verify before relying on historical back-pricing")),
		textCatalogSnapshot("gpt-5", "gpt-5", 1.25, 10, 0.125, officialRaw("https://openai.com/api/pricing/", "builtin official catalog; verify before relying on historical back-pricing")),
		textCatalogSnapshot("gpt-5-mini", "gpt-5-mini", 0.25, 2, 0.025, officialRaw("https://openai.com/api/pricing/", "builtin official catalog; verify before relying on historical back-pricing")),
		textCatalogSnapshot("gpt-4.1", "gpt-4.1", 2, 8, 0.5, officialRaw("https://openai.com/api/pricing/", "builtin official catalog; verify before relying on historical back-pricing")),
		textCatalogSnapshot("gpt-4.1-mini", "gpt-4.1-mini", 0.4, 1.6, 0.1, officialRaw("https://openai.com/api/pricing/", "builtin official catalog; verify before relying on historical back-pricing")),
		textCatalogSnapshot("gpt-4.1-nano", "gpt-4.1-nano", 0.1, 0.4, 0.025, officialRaw("https://openai.com/api/pricing/", "builtin official catalog; verify before relying on historical back-pricing")),
		{
			ModelID:                  "gpt-image-2",
			CanonicalModelID:         "gpt-image-2",
			LocalModelName:           "gpt-image-2",
			Scenario:                 "image_generation",
			PricingScheme:            "per_token",
			Currency:                 "USD",
			Unit:                     "token",
			InputPricePerToken:       perMillion(5),
			CacheReadPricePerToken:   perMillion(1.25),
			InputImagePricePerToken:  perMillion(8),
			OutputImagePricePerToken: perMillion(30),
			RawJSON:                  officialRaw("https://openai.com/api/pricing/", "text/image token pricing"),
		},
		{
			ModelID:                  "gpt-realtime-2",
			CanonicalModelID:         "gpt-realtime-2",
			LocalModelName:           "gpt-realtime-2",
			Scenario:                 "multimodal_realtime",
			PricingScheme:            "per_token",
			Currency:                 "USD",
			Unit:                     "token",
			InputPricePerToken:       perMillion(4),
			OutputPricePerToken:      perMillion(24),
			CacheReadPricePerToken:   perMillion(0.4),
			InputImagePricePerToken:  perMillion(5),
			InputAudioPricePerToken:  perMillion(32),
			OutputAudioPricePerToken: perMillion(64),
			RawJSON:                  officialRaw("https://openai.com/api/pricing/", "text/image/audio token pricing"),
		},
	}
}

func anthropicCatalogSnapshotRequests() []SnapshotMutationRequest {
	return []SnapshotMutationRequest{
		anthropicTextCatalogSnapshot("claude-opus-4.1", "claude-opus-4-1", 15, 75, 1.5, 18.75, 30),
		anthropicTextCatalogSnapshot("claude-sonnet-4.5", "claude-sonnet-4-5", 3, 15, 0.3, 3.75, 6),
		anthropicTextCatalogSnapshot("claude-haiku-4.5", "claude-haiku-4-5", 1, 5, 0.1, 1.25, 2),
		anthropicTextCatalogSnapshot("claude-3.5-haiku", "claude-3-5-haiku", 0.8, 4, 0.08, 1, 1.6),
	}
}

func googleCatalogSnapshotRequests() []SnapshotMutationRequest {
	return []SnapshotMutationRequest{
		textCatalogSnapshot("gemini-2.5-pro", "gemini-2.5-pro", 1.25, 10, 0.31, officialRaw("https://ai.google.dev/gemini-api/docs/pricing", "builtin official catalog; verify tiering and grounding costs")),
		textCatalogSnapshot("gemini-2.5-flash", "gemini-2.5-flash", 0.3, 2.5, 0.075, officialRaw("https://ai.google.dev/gemini-api/docs/pricing", "builtin official catalog; verify modality-specific rows")),
		textCatalogSnapshot("gemini-2.5-flash-lite", "gemini-2.5-flash-lite", 0.1, 0.4, 0.025, officialRaw("https://ai.google.dev/gemini-api/docs/pricing", "builtin official catalog; verify modality-specific rows")),
		{
			ModelID:                  "gemini-2.5-flash-image",
			CanonicalModelID:         "gemini-2.5-flash-image",
			LocalModelName:           "gemini-2.5-flash-image",
			Scenario:                 "image_generation",
			PricingScheme:            "per_token",
			Currency:                 "USD",
			Unit:                     "token",
			InputPricePerToken:       perMillion(0.3),
			OutputPricePerToken:      perMillion(30),
			InputImagePricePerToken:  perMillion(0.3),
			OutputImagePricePerToken: perMillion(30),
			RawJSON:                  officialRaw("https://ai.google.dev/gemini-api/docs/pricing", "image output tokens commonly map to generated image cost"),
		},
	}
}

func textCatalogSnapshot(modelID, localModelName string, inputPerMillion, outputPerMillion, cacheReadPerMillion float64, rawJSON string) SnapshotMutationRequest {
	return SnapshotMutationRequest{
		ModelID:                modelID,
		CanonicalModelID:       modelID,
		LocalModelName:         localModelName,
		Scenario:               "text_token",
		PricingScheme:          "per_token",
		Currency:               "USD",
		Unit:                   "token",
		InputPricePerToken:     perMillion(inputPerMillion),
		OutputPricePerToken:    perMillion(outputPerMillion),
		CacheReadPricePerToken: perMillion(cacheReadPerMillion),
		RawJSON:                rawJSON,
	}
}

func anthropicTextCatalogSnapshot(modelID, localModelName string, inputPerMillion, outputPerMillion, cacheReadPerMillion, cacheWrite5mPerMillion, cacheWrite1hPerMillion float64) SnapshotMutationRequest {
	req := textCatalogSnapshot(modelID, localModelName, inputPerMillion, outputPerMillion, cacheReadPerMillion, officialRaw("https://www.claude.com/platform/api", "builtin official catalog; includes 5m/1h prompt cache tiers"))
	req.CacheWritePricePerToken = perMillion(cacheWrite5mPerMillion)
	req.CacheWrite5mPricePerToken = perMillion(cacheWrite5mPerMillion)
	req.CacheWrite1hPricePerToken = perMillion(cacheWrite1hPerMillion)
	return req
}

func perMillion(value float64) float64 {
	return value / pricePerMillionDivisor
}

func officialRaw(sourceURL, note string) string {
	body, _ := json.Marshal(map[string]string{
		"source_url": sourceURL,
		"note":       note,
	})
	return string(body)
}
