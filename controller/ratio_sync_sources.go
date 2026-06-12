package controller

// External price source sync adapters.
import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/dto"
	"github.com/QuantumNous/new-api/logger"
	"github.com/QuantumNous/new-api/setting/ratio_setting"

	"github.com/gin-gonic/gin"
)

const (
	sourceChannel    = ""
	sourceModelsDev  = "models.dev"
	sourceOpenRouter = "openrouter"
	sourceLiteLLM    = "litellm"
	sourceTiered     = "tiered"

	modelsDevURL  = "https://models.dev/api.json"
	openRouterURL = "https://openrouter.ai/api/v1/models"
	liteLLMURL    = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"

	maxExternalBytes = 64 << 20
	categoryText     = "text"
	categoryTiered   = "tiered"
	categoryImage    = "image"
	categoryOnce     = "once"
)

var imageModelNameKeywords = []string{
	"dall-e", "dalle", "gpt-image", "stable-diffusion", "sdxl", "flux",
	"midjourney", "imagen", "ideogram", "recraft", "playground-v",
	"kolors", "seedream", "seededit", "hunyuan-image", "nano-banana",
	"qwen-image", "wan2", "wan-",
}

func normalizeSource(s string) string {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "", "channel", "channels", "newapi":
		return sourceChannel
	case "models.dev", "modelsdev", "models_dev", "models-dev":
		return sourceModelsDev
	case "openrouter", "open_router", "open-router":
		return sourceOpenRouter
	case "litellm", "lite_llm", "lite-llm":
		return sourceLiteLLM
	case "tiered", "tiered_pricing", "models.dev+litellm", "modelsdev+litellm", "models.dev,litellm":
		return sourceTiered
	default:
		return strings.ToLower(strings.TrimSpace(s))
	}
}

func handleExternalSource(c *gin.Context, req *dto.UpstreamRequest, source string) {
	client := newExternalHTTPClient(req.Timeout)
	ctx, cancel := context.WithTimeout(c.Request.Context(), time.Duration(req.Timeout)*time.Second)
	defer cancel()

	var (
		data    map[string]any
		err     error
		srcName string
	)
	switch source {
	case sourceModelsDev:
		srcName = "models.dev"
		data, err = fetchModelsDev(ctx, client)
	case sourceOpenRouter:
		srcName = "OpenRouter"
		data, err = fetchOpenRouter(ctx, client)
	case sourceLiteLLM:
		srcName = "LiteLLM"
		data, err = fetchLiteLLM(ctx, client)
	case sourceTiered:
		srcName = "models.dev + LiteLLM"
		data, err = fetchTieredSources(ctx, client)
	default:
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "unknown price source"})
		return
	}

	if err != nil {
		logger.LogWarn(c.Request.Context(), "fetch external price source failed ("+srcName+"): "+err.Error())
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": fmt.Sprintf("failed to fetch %s price catalog: %s", srcName, err.Error()),
			"data": gin.H{
				"test_results": []dto.TestResult{{Name: srcName, Status: "error", Error: err.Error()}},
			},
		})
		return
	}

	include := buildModelFilter(req)
	exclude := buildExcludeFilter(req)
	filterSourceData(data, include, exclude)

	localData := ratio_setting.GetExposedData()
	successfulChannels := []struct {
		name string
		data map[string]any
	}{{name: srcName, data: data}}

	differences := buildDifferences(localData, successfulChannels)

	responseData := gin.H{
		"differences":  differences,
		"test_results": []dto.TestResult{{Name: srcName, Status: "success"}},
		"categories":   computeCategories(differences),
		"source":       source,
	}
	if len(req.Models) > 0 {
		responseData["source_data"] = data
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"data":    responseData,
	})
}

func newExternalHTTPClient(timeoutSec int) *http.Client {
	if timeoutSec <= 0 {
		timeoutSec = defaultTimeoutSeconds
	}
	dialer := &net.Dialer{Timeout: 10 * time.Second}
	transport := &http.Transport{
		MaxIdleConns:          100,
		IdleConnTimeout:       90 * time.Second,
		TLSHandshakeTimeout:   10 * time.Second,
		ExpectContinueTimeout: 1 * time.Second,
		ResponseHeaderTimeout: time.Duration(timeoutSec) * time.Second,
	}
	transport.DialContext = func(ctx context.Context, network, addr string) (net.Conn, error) {
		if conn, err := dialer.DialContext(ctx, "tcp4", addr); err == nil {
			return conn, nil
		}
		return dialer.DialContext(ctx, network, addr)
	}
	return &http.Client{Transport: transport, Timeout: time.Duration(timeoutSec+5) * time.Second}
}

type modelsDevTier struct {
	Input      float64 `json:"input"`
	Output     float64 `json:"output"`
	CacheRead  float64 `json:"cache_read"`
	CacheWrite float64 `json:"cache_write"`
	Tier       struct {
		Type string `json:"type"`
		Size int    `json:"size"`
	} `json:"tier"`
}

type modelsDevCost struct {
	Input      float64         `json:"input"`
	Output     float64         `json:"output"`
	CacheRead  float64         `json:"cache_read"`
	CacheWrite float64         `json:"cache_write"`
	Tiers      []modelsDevTier `json:"tiers"`
}

// fetchModelsDev fetches models.dev pricing and converts it into upstreamResult.Data ratio maps.
// models.dev /api.json shape: "<provider>": { "models": { "<model>": { "cost": { input, output, cache_read } } } } }
func fetchModelsDev(ctx context.Context, client *http.Client) (map[string]any, error) {
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodGet, modelsDevURL, nil)
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Accept", "application/json")

	resp, err := client.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("models.dev 閺夆晜鏌ㄥú?%s", resp.Status)
	}

	limited := io.LimitReader(resp.Body, maxExternalBytes)
	var providers map[string]struct {
		Models map[string]struct {
			Cost *modelsDevCost `json:"cost"`
		} `json:"models"`
	}
	if err := json.NewDecoder(limited).Decode(&providers); err != nil {
		return nil, fmt.Errorf("parse models.dev data failed: %w", err)
	}

	modelRatio := make(map[string]any)
	completion := make(map[string]any)
	cache := make(map[string]any)
	tiered := make(map[string]any)

	for _, p := range providers {
		for name, m := range p.Models {
			if m.Cost == nil {
				continue
			}
			applyExternalPricing(name, m.Cost.Input, m.Cost.Output, m.Cost.CacheRead,
				modelRatio, completion, cache)
			if cfg := buildModelsDevTieredPricing(m.Cost.Input, m.Cost.Output, m.Cost.CacheRead, m.Cost.CacheWrite, m.Cost.Tiers); cfg != nil {
				tiered[name] = cfg
			}
		}
	}

	return assembleSourceData(modelRatio, completion, cache, nil, tiered), nil
}

func fetchOpenRouter(ctx context.Context, client *http.Client) (map[string]any, error) {
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodGet, openRouterURL, nil)
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Accept", "application/json")

	resp, err := client.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("OpenRouter 閺夆晜鏌ㄥú?%s", resp.Status)
	}

	limited := io.LimitReader(resp.Body, maxExternalBytes)
	var body struct {
		Data []struct {
			ID      string `json:"id"`
			Pricing struct {
				Prompt         string `json:"prompt"`
				Completion     string `json:"completion"`
				InputCacheRead string `json:"input_cache_read"`
			} `json:"pricing"`
		} `json:"data"`
	}
	if err := json.NewDecoder(limited).Decode(&body); err != nil {
		return nil, fmt.Errorf("parse OpenRouter data failed: %w", err)
	}

	modelRatio := make(map[string]any)
	completion := make(map[string]any)
	cache := make(map[string]any)

	for _, m := range body.Data {
		name := m.ID
		if idx := strings.LastIndex(name, "/"); idx >= 0 {
			name = name[idx+1:]
		}
		inputPer1M := parseFloatSafe(m.Pricing.Prompt) * 1e6
		outputPer1M := parseFloatSafe(m.Pricing.Completion) * 1e6
		cacheReadPer1M := parseFloatSafe(m.Pricing.InputCacheRead) * 1e6
		applyExternalPricing(name, inputPer1M, outputPer1M, cacheReadPer1M,
			modelRatio, completion, cache)
	}

	return assembleSourceData(modelRatio, completion, cache, nil, nil), nil
}

func applyExternalPricing(name string, inputPer1M, outputPer1M, cacheReadPer1M float64,
	modelRatio, completion, cache map[string]any) {
	if name == "" {
		return
	}
	if _, exists := modelRatio[name]; exists {
		return
	}
	if inputPer1M <= 0 {
		return
	}
	modelRatio[name] = inputPer1M / 2.0
	if outputPer1M > 0 {
		completion[name] = outputPer1M / inputPer1M
	}
	if cacheReadPer1M > 0 {
		cache[name] = cacheReadPer1M / inputPer1M
	}
}

func fetchTieredSources(ctx context.Context, client *http.Client) (map[string]any, error) {
	modelsDevData, modelsDevErr := fetchModelsDev(ctx, client)
	liteLLMData, liteLLMErr := fetchLiteLLM(ctx, client)
	if modelsDevErr != nil && liteLLMErr != nil {
		return nil, fmt.Errorf("models.dev: %v; LiteLLM: %v", modelsDevErr, liteLLMErr)
	}
	if modelsDevErr != nil {
		return liteLLMData, nil
	}
	if liteLLMErr != nil {
		return modelsDevData, nil
	}
	return mergeExternalSourceData(modelsDevData, liteLLMData), nil
}

func mergeExternalSourceData(primary, fallback map[string]any) map[string]any {
	out := make(map[string]any)
	for _, ratioType := range ratioTypes {
		merged := make(map[string]any)
		if sub := mapFromConfigValue(primary[ratioType]); sub != nil {
			for k, v := range sub {
				merged[k] = v
			}
		}
		if sub := mapFromConfigValue(fallback[ratioType]); sub != nil {
			for k, v := range sub {
				if _, exists := merged[k]; !exists {
					merged[k] = v
				}
			}
		}
		if len(merged) > 0 {
			out[ratioType] = merged
		}
	}
	return out
}

func buildModelsDevTieredPricing(baseInput, baseOutput, baseCacheRead, baseCacheWrite float64, sourceTiers []modelsDevTier) *ratio_setting.TieredPricing {
	if len(sourceTiers) == 0 || (baseInput <= 0 && baseOutput <= 0) {
		return nil
	}
	tiers := make([]modelsDevTier, 0, len(sourceTiers))
	for _, tier := range sourceTiers {
		if tier.Tier.Size <= 0 {
			continue
		}
		if tier.Tier.Type != "" && tier.Tier.Type != "context" {
			continue
		}
		tiers = append(tiers, tier)
	}
	if len(tiers) == 0 {
		return nil
	}
	sort.Slice(tiers, func(i, j int) bool {
		return tiers[i].Tier.Size < tiers[j].Tier.Size
	})
	out := make([]ratio_setting.PriceTier, 0, len(tiers)+1)
	out = append(out, ratio_setting.PriceTier{MinTokens: 0, MaxTokens: tokensToK(tiers[0].Tier.Size), InputPrice: baseInput, OutputPrice: baseOutput, CacheHitPrice: baseCacheRead, CacheStorePrice: baseCacheWrite})
	for i, tier := range tiers {
		maxTokens := -1
		if i+1 < len(tiers) {
			maxTokens = tokensToK(tiers[i+1].Tier.Size)
		}
		out = append(out, ratio_setting.PriceTier{MinTokens: tokensToK(tier.Tier.Size), MaxTokens: maxTokens, InputPrice: priceOrFallback(tier.Input, baseInput), OutputPrice: priceOrFallback(tier.Output, baseOutput), CacheHitPrice: priceOrFallback(tier.CacheRead, baseCacheRead), CacheStorePrice: priceOrFallback(tier.CacheWrite, baseCacheWrite)})
	}
	return &ratio_setting.TieredPricing{Enabled: true, Tiers: out}
}

var liteLLMAboveCostPattern = regexp.MustCompile(`^(input_cost_per_token|output_cost_per_token|cache_read_input_token_cost|cache_creation_input_token_cost)_above_([0-9]+)k_tokens$`)

type liteLLMThresholdCost struct {
	Input       float64
	Output      float64
	CacheRead   float64
	CacheCreate float64
}

func fetchLiteLLM(ctx context.Context, client *http.Client) (map[string]any, error) {
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodGet, liteLLMURL, nil)
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Accept", "application/json")
	resp, err := client.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("LiteLLM returned %s", resp.Status)
	}
	limited := io.LimitReader(resp.Body, maxExternalBytes)
	var catalog map[string]map[string]any
	if err := json.NewDecoder(limited).Decode(&catalog); err != nil {
		return nil, fmt.Errorf("parse LiteLLM data failed: %w", err)
	}
	modelRatio := make(map[string]any)
	completion := make(map[string]any)
	cache := make(map[string]any)
	tiered := make(map[string]any)
	for sourceName, raw := range catalog {
		if sourceName == "sample_spec" || raw == nil {
			continue
		}
		baseInput := floatField(raw, "input_cost_per_token") * 1e6
		baseOutput := floatField(raw, "output_cost_per_token") * 1e6
		baseCacheRead := firstFloatField(raw, "cache_read_input_token_cost", "input_cost_per_token_cache_read") * 1e6
		baseCacheCreate := firstFloatField(raw, "cache_creation_input_token_cost", "input_cost_per_token_cache_creation") * 1e6
		for _, name := range localModelAliases(sourceName) {
			applyExternalPricing(name, baseInput, baseOutput, baseCacheRead, modelRatio, completion, cache)
		}
		thresholds := map[int]*liteLLMThresholdCost{}
		for key, value := range raw {
			matches := liteLLMAboveCostPattern.FindStringSubmatch(key)
			if len(matches) != 3 {
				continue
			}
			thresholdK, _ := strconv.Atoi(matches[2])
			if thresholdK <= 0 {
				continue
			}
			cost := thresholds[thresholdK]
			if cost == nil {
				cost = &liteLLMThresholdCost{}
				thresholds[thresholdK] = cost
			}
			price := numericValue(value) * 1e6
			switch matches[1] {
			case "input_cost_per_token":
				cost.Input = price
			case "output_cost_per_token":
				cost.Output = price
			case "cache_read_input_token_cost":
				cost.CacheRead = price
			case "cache_creation_input_token_cost":
				cost.CacheCreate = price
			}
		}
		if len(thresholds) == 0 || (baseInput <= 0 && baseOutput <= 0) {
			continue
		}
		cfg := buildLiteLLMTieredPricing(baseInput, baseOutput, baseCacheRead, baseCacheCreate, thresholds)
		if cfg == nil {
			continue
		}
		for _, name := range localModelAliases(sourceName) {
			if _, exists := tiered[name]; !exists {
				tiered[name] = cfg
			}
		}
	}
	return assembleSourceData(modelRatio, completion, cache, nil, tiered), nil
}

func buildLiteLLMTieredPricing(baseInput, baseOutput, baseCacheRead, baseCacheCreate float64, thresholds map[int]*liteLLMThresholdCost) *ratio_setting.TieredPricing {
	keys := make([]int, 0, len(thresholds))
	for thresholdK := range thresholds {
		keys = append(keys, thresholdK)
	}
	sort.Ints(keys)
	if len(keys) == 0 {
		return nil
	}
	out := make([]ratio_setting.PriceTier, 0, len(keys)+1)
	out = append(out, ratio_setting.PriceTier{MinTokens: 0, MaxTokens: keys[0], InputPrice: baseInput, OutputPrice: baseOutput, CacheHitPrice: baseCacheRead, CacheStorePrice: baseCacheCreate})
	for i, thresholdK := range keys {
		cost := thresholds[thresholdK]
		maxTokens := -1
		if i+1 < len(keys) {
			maxTokens = keys[i+1]
		}
		out = append(out, ratio_setting.PriceTier{MinTokens: thresholdK, MaxTokens: maxTokens, InputPrice: priceOrFallback(cost.Input, baseInput), OutputPrice: priceOrFallback(cost.Output, baseOutput), CacheHitPrice: priceOrFallback(cost.CacheRead, baseCacheRead), CacheStorePrice: priceOrFallback(cost.CacheCreate, baseCacheCreate)})
	}
	return &ratio_setting.TieredPricing{Enabled: true, Tiers: out}
}

func localModelAliases(sourceName string) []string {
	sourceName = strings.TrimSpace(sourceName)
	if sourceName == "" {
		return nil
	}
	if idx := strings.LastIndex(sourceName, "/"); idx >= 0 && idx+1 < len(sourceName) {
		last := sourceName[idx+1:]
		if last != sourceName {
			return []string{last, sourceName}
		}
	}
	return []string{sourceName}
}

func tokensToK(tokens int) int {
	if tokens <= 0 {
		return 0
	}
	return (tokens + 999) / 1000
}

func priceOrFallback(price, fallback float64) float64 {
	if price > 0 {
		return price
	}
	return fallback
}

func floatField(raw map[string]any, key string) float64 {
	return numericValue(raw[key])
}

func firstFloatField(raw map[string]any, keys ...string) float64 {
	for _, key := range keys {
		if value := numericValue(raw[key]); value > 0 {
			return value
		}
	}
	return 0
}

func numericValue(value any) float64 {
	switch v := value.(type) {
	case float64:
		return v
	case float32:
		return float64(v)
	case int:
		return float64(v)
	case int64:
		return float64(v)
	case json.Number:
		f, _ := v.Float64()
		return f
	case string:
		f, _ := strconv.ParseFloat(strings.TrimSpace(v), 64)
		return f
	default:
		return 0
	}
}

func assembleSourceData(modelRatio, completion, cache, modelPrice, tieredPricing map[string]any) map[string]any {
	data := make(map[string]any)
	if len(modelRatio) > 0 {
		data["model_ratio"] = modelRatio
	}
	if len(completion) > 0 {
		data["completion_ratio"] = completion
	}
	if len(cache) > 0 {
		data["cache_ratio"] = cache
	}
	if len(modelPrice) > 0 {
		data["model_price"] = modelPrice
	}
	if len(tieredPricing) > 0 {
		data["tiered_pricing"] = tieredPricing
	}
	return data
}

func parseFloatSafe(s string) float64 {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0
	}
	f, err := strconv.ParseFloat(s, 64)
	if err != nil {
		return 0
	}
	return f
}

func buildModelFilter(req *dto.UpstreamRequest) func(string) bool {
	exact := make(map[string]struct{})
	var wildcards []string

	if req.OnlyExisting {
		for k := range ratio_setting.GetModelRatioCopy() {
			exact[k] = struct{}{}
		}
		for k := range ratio_setting.GetTieredPricingCopy() {
			exact[k] = struct{}{}
		}
	}
	for _, m := range req.Models {
		m = strings.TrimSpace(m)
		if m == "" {
			continue
		}
		if strings.Contains(m, "*") {
			wildcards = append(wildcards, m)
		} else {
			exact[m] = struct{}{}
		}
	}

	if len(exact) == 0 && len(wildcards) == 0 {
		return func(string) bool { return true }
	}
	return func(name string) bool {
		if _, ok := exact[name]; ok {
			return true
		}
		for _, w := range wildcards {
			if ratio_setting.MatchModelPattern(w, name) {
				return true
			}
		}
		return false
	}
}

func buildExcludeFilter(req *dto.UpstreamRequest) func(string) bool {
	exact := make(map[string]struct{})
	var wildcards []string
	for _, m := range req.ExcludeModels {
		m = strings.TrimSpace(m)
		if m == "" {
			continue
		}
		if strings.Contains(m, "*") {
			wildcards = append(wildcards, m)
		} else {
			exact[m] = struct{}{}
		}
	}
	if len(exact) == 0 && len(wildcards) == 0 {
		return func(string) bool { return false }
	}
	return func(name string) bool {
		if _, ok := exact[name]; ok {
			return true
		}
		for _, w := range wildcards {
			if ratio_setting.MatchModelPattern(w, name) {
				return true
			}
		}
		return false
	}
}

// filterSourceData filters all ratio maps in source data by include/exclude predicates.
func filterSourceData(data map[string]any, include func(string) bool, exclude func(string) bool) {
	for _, rt := range ratioTypes {
		sub, ok := data[rt].(map[string]any)
		if !ok {
			continue
		}
		for name := range sub {
			if !include(name) || exclude(name) {
				delete(sub, name)
			}
		}
		if len(sub) == 0 {
			delete(data, rt)
		}
	}
}

func classifyBillingMode(model string) string {
	if ratio_setting.IsTieredPricingEnabled(model) {
		return categoryTiered
	}
	if isImageModel(model) {
		return categoryImage
	}
	if _, ok := ratio_setting.GetModelPrice(model, false); ok {
		return categoryOnce
	}
	return categoryText
}

func isImageModel(model string) bool {
	if _, ok := ratio_setting.GetImageRatio(model); ok {
		return true
	}
	if _, ok := ratio_setting.GetImageCompletionRatio(model); ok {
		return true
	}
	lower := strings.ToLower(model)
	for _, kw := range imageModelNameKeywords {
		if strings.Contains(lower, kw) {
			return true
		}
	}
	return false
}

func computeCategories(differences map[string]map[string]dto.DifferenceItem) map[string]string {
	cats := make(map[string]string, len(differences))
	for model, ratioMap := range differences {
		if _, ok := ratioMap["tiered_pricing"]; ok {
			cats[model] = categoryTiered
			continue
		}
		cats[model] = classifyBillingMode(model)
	}
	return cats
}
