package controller

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/constant"
	"github.com/QuantumNous/new-api/dto"
	"github.com/QuantumNous/new-api/middleware"
	"github.com/QuantumNous/new-api/model"
	"github.com/QuantumNous/new-api/relay"
	relaycommon "github.com/QuantumNous/new-api/relay/common"
	"github.com/QuantumNous/new-api/relay/helper"
	"github.com/QuantumNous/new-api/setting/ratio_setting"
	"github.com/QuantumNous/new-api/types"

	"github.com/gin-gonic/gin"
	"github.com/shopspring/decimal"
)

type DiagnosticTestRequest struct {
	ChannelIDs []int              `json:"channel_ids" binding:"required,min=1"`
	Model      string             `json:"model" binding:"required"`
	TestType   string             `json:"test_type" binding:"required"`
	Options    DiagnosticOptions  `json:"options"`
}

type DiagnosticOptions struct {
	EnableCache       bool   `json:"enable_cache"`
	CacheTTL          string `json:"cache_ttl"`
	EnableThinking    bool   `json:"enable_thinking"`
	ThinkingType      string `json:"thinking_type"`
	ThinkingBudget    int    `json:"thinking_budget"`
	ThinkingEffort    string `json:"thinking_effort"`
	TargetInputTokens int    `json:"target_input_tokens"`
	MaxTokens         uint   `json:"max_tokens"`
	EndpointType      string `json:"endpoint_type"`
	Stream            bool   `json:"stream"`
}

type DiagnosticUsage struct {
	PromptTokens           int `json:"prompt_tokens"`
	CompletionTokens       int `json:"completion_tokens"`
	CachedTokens           int `json:"cached_tokens"`
	CacheCreationTokens    int `json:"cache_creation_tokens"`
	CacheCreation5mTokens  int `json:"cache_creation_5m_tokens"`
	CacheCreation1hTokens  int `json:"cache_creation_1h_tokens"`
	ReasoningTokens        int `json:"reasoning_tokens"`
}

type DiagnosticPricing struct {
	InputPricePerMTok        float64 `json:"input_price_per_mtok"`
	OutputPricePerMTok       float64 `json:"output_price_per_mtok"`
	CacheHitPricePerMTok     float64 `json:"cache_hit_price_per_mtok"`
	CacheStore5mPricePerMTok float64 `json:"cache_store_5m_price_per_mtok"`
	CacheStore1hPricePerMTok float64 `json:"cache_store_1h_price_per_mtok"`
	TotalCostUSD             float64 `json:"total_cost_usd"`
	TierUsed                 string  `json:"tier_used"`
	UseTieredPricing         bool    `json:"use_tiered_pricing"`
}

type DiagnosticCheck struct {
	Name   string `json:"name"`
	Passed bool   `json:"passed"`
	Detail string `json:"detail"`
}

type DiagnosticChannelResult struct {
	ChannelID   int                `json:"channel_id"`
	ChannelName string             `json:"channel_name"`
	Status      string             `json:"status"`
	Error       string             `json:"error,omitempty"`
	DurationMs  int64              `json:"duration_ms"`
	Usage       *DiagnosticUsage   `json:"usage,omitempty"`
	Pricing     *DiagnosticPricing `json:"pricing,omitempty"`
	Checks      []DiagnosticCheck  `json:"checks"`
}

type DiagnosticTestResponse struct {
	TestType string                    `json:"test_type"`
	Model    string                    `json:"model"`
	Results  []DiagnosticChannelResult `json:"results"`
}

type diagnosticResult struct {
	usage    *dto.Usage
	priceData types.PriceData
	err      error
	duration int64
}

func DiagnosticTest(c *gin.Context) {
	var req DiagnosticTestRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "参数错误: "+err.Error())
		return
	}

	if len(req.ChannelIDs) > 10 {
		common.ApiErrorMsg(c, "最多同时测试 10 个渠道")
		return
	}

	validTestTypes := map[string]bool{
		"standard": true, "cache": true, "long_context": true,
		"thinking": true, "pricing_verify": true,
	}
	if !validTestTypes[req.TestType] {
		common.ApiErrorMsg(c, "无效的测试类型: "+req.TestType)
		return
	}

	channels := make([]*model.Channel, 0, len(req.ChannelIDs))
	for _, id := range req.ChannelIDs {
		ch, err := model.GetChannelById(id, true)
		if err != nil {
			common.ApiErrorMsg(c, fmt.Sprintf("渠道 %d 不存在", id))
			return
		}
		channels = append(channels, ch)
	}

	var wg sync.WaitGroup
	results := make([]DiagnosticChannelResult, len(channels))

	for i, ch := range channels {
		wg.Add(1)
		go func(idx int, channel *model.Channel) {
			defer wg.Done()
			results[idx] = runDiagnosticTest(channel, req.Model, req.TestType, req.Options)
		}(i, ch)
	}

	wg.Wait()

	common.ApiSuccess(c, DiagnosticTestResponse{
		TestType: req.TestType,
		Model:    req.Model,
		Results:  results,
	})
}

func runDiagnosticTest(channel *model.Channel, modelName string, testType string, opts DiagnosticOptions) DiagnosticChannelResult {
	result := DiagnosticChannelResult{
		ChannelID:   channel.Id,
		ChannelName: channel.Name,
		Checks:      make([]DiagnosticCheck, 0),
	}

	switch testType {
	case "standard":
		runStandardTest(channel, modelName, opts, &result)
	case "cache":
		runCacheTest(channel, modelName, opts, &result)
	case "thinking":
		runThinkingTest(channel, modelName, opts, &result)
	case "long_context":
		runLongContextTest(channel, modelName, opts, &result)
	case "pricing_verify":
		runPricingVerifyTest(channel, modelName, opts, &result)
	}

	return result
}

func runStandardTest(channel *model.Channel, modelName string, opts DiagnosticOptions, result *DiagnosticChannelResult) {
	cleanOpts := opts
	cleanOpts.EnableCache = false

	dr := executeDiagnosticRequest(channel, modelName, cleanOpts)
	if dr.err != nil {
		result.Status = "error"
		result.Error = dr.err.Error()
		result.DurationMs = dr.duration
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name: "API 连通性", Passed: false, Detail: dr.err.Error(),
		})
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name: "空提示词检测", Passed: true,
			Detail: "请求失败，无法检测（非异常）",
		})
		return
	}

	result.Status = "success"
	result.DurationMs = dr.duration
	result.Usage = convertUsage(dr.usage)
	result.Pricing = computePricing(dr.usage, dr.priceData, modelName)
	result.Checks = append(result.Checks, DiagnosticCheck{
		Name: "API 连通性", Passed: true,
		Detail: fmt.Sprintf("响应正常, 耗时 %dms", dr.duration),
	})

	if dr.usage.PromptTokens > 0 {
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name: "Usage 返回", Passed: true,
			Detail: fmt.Sprintf("prompt=%d, completion=%d", dr.usage.PromptTokens, dr.usage.CompletionTokens),
		})
	}

	cachedTokens := dr.usage.PromptTokensDetails.CachedTokens
	cacheCreation := dr.usage.PromptTokensDetails.CachedCreationTokens
	if cachedTokens > 0 {
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name:   "空提示词检测",
			Passed: false,
			Detail: fmt.Sprintf("未发送缓存指令但出现 cached_tokens=%d，渠道注入了带缓存的系统提示词（疑似逆向）", cachedTokens),
		})
	} else if cacheCreation > 0 {
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name:   "空提示词检测",
			Passed: false,
			Detail: fmt.Sprintf("未发送缓存指令但出现 cache_creation=%d，渠道注入了缓存写入（疑似逆向）", cacheCreation),
		})
	} else {
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name:   "空提示词检测",
			Passed: true,
			Detail: "未检测到意外的缓存 token，渠道行为正常",
		})
	}
}

func runCacheTest(channel *model.Channel, modelName string, opts DiagnosticOptions, result *DiagnosticChannelResult) {
	opts.EnableCache = true
	if opts.CacheTTL == "" {
		opts.CacheTTL = "5m"
	}

	// First request: create cache
	dr1 := executeDiagnosticRequest(channel, modelName, opts)
	if dr1.err != nil {
		result.Status = "error"
		result.Error = "首次请求失败: " + dr1.err.Error()
		result.DurationMs = dr1.duration
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name: "缓存创建", Passed: false, Detail: dr1.err.Error(),
		})
		return
	}

	cacheCreated := dr1.usage.PromptTokensDetails.CachedCreationTokens > 0
	result.Checks = append(result.Checks, DiagnosticCheck{
		Name: "缓存创建", Passed: cacheCreated,
		Detail: fmt.Sprintf("cache_creation_tokens=%d", dr1.usage.PromptTokensDetails.CachedCreationTokens),
	})

	if opts.CacheTTL == "5m" && dr1.usage.ClaudeCacheCreation5mTokens > 0 {
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name: "5m 缓存 TTL", Passed: true,
			Detail: fmt.Sprintf("5m_tokens=%d", dr1.usage.ClaudeCacheCreation5mTokens),
		})
	} else if opts.CacheTTL == "1h" && dr1.usage.ClaudeCacheCreation1hTokens > 0 {
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name: "1h 缓存 TTL", Passed: true,
			Detail: fmt.Sprintf("1h_tokens=%d", dr1.usage.ClaudeCacheCreation1hTokens),
		})
	}

	ttlMismatch := false
	if opts.CacheTTL == "5m" && dr1.usage.ClaudeCacheCreation1hTokens > 0 && dr1.usage.ClaudeCacheCreation5mTokens == 0 {
		ttlMismatch = true
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name: "缓存 TTL 一致性", Passed: false,
			Detail: "请求 5m 缓存但返回 1h tokens，渠道可能自动升级 TTL",
		})
	}

	// Second request: verify cache hit
	time.Sleep(500 * time.Millisecond)
	dr2 := executeDiagnosticRequest(channel, modelName, opts)
	if dr2.err != nil {
		result.Status = "error"
		result.Error = "第二次请求失败: " + dr2.err.Error()
		result.DurationMs = dr1.duration + dr2.duration
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name: "缓存命中", Passed: false, Detail: dr2.err.Error(),
		})
		return
	}

	r2Cached := dr2.usage.PromptTokensDetails.CachedTokens
	r2Creation := dr2.usage.PromptTokensDetails.CachedCreationTokens
	r1Creation := dr1.usage.PromptTokensDetails.CachedCreationTokens

	cacheHit := r2Cached > 0
	result.Checks = append(result.Checks, DiagnosticCheck{
		Name: "缓存命中", Passed: cacheHit,
		Detail: fmt.Sprintf("第二次请求 cached_tokens=%d（第一次 cache_creation=%d）", r2Cached, r1Creation),
	})

	if cacheHit && r1Creation > 0 {
		hitRatio := float64(r2Cached) / float64(r1Creation) * 100
		fullHit := r2Cached >= r1Creation
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name:   "缓存命中完整性",
			Passed: fullHit,
			Detail: fmt.Sprintf("命中率 %.1f%%: cached=%d vs created=%d", hitRatio, r2Cached, r1Creation),
		})
	}

	if r2Creation > 0 {
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name:   "二次缓存写入检测",
			Passed: false,
			Detail: fmt.Sprintf("第二次请求仍产生 cache_creation=%d，缓存未正确复用", r2Creation),
		})
	} else if cacheHit {
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name:   "二次缓存写入检测",
			Passed: true,
			Detail: "第二次请求无新缓存写入，缓存正确复用",
		})
	}

	if !ttlMismatch {
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name: "缓存 TTL 一致性", Passed: true,
			Detail: fmt.Sprintf("TTL=%s 行为正常", opts.CacheTTL),
		})
	}

	result.Status = "success"
	result.DurationMs = dr1.duration + dr2.duration
	result.Usage = convertUsage(dr2.usage)
	result.Usage.CacheCreationTokens = r1Creation
	result.Usage.CacheCreation5mTokens = dr1.usage.ClaudeCacheCreation5mTokens
	result.Usage.CacheCreation1hTokens = dr1.usage.ClaudeCacheCreation1hTokens
	result.Pricing = computePricing(dr1.usage, dr1.priceData, modelName)
}

func runThinkingTest(channel *model.Channel, modelName string, opts DiagnosticOptions, result *DiagnosticChannelResult) {
	opts.EnableThinking = true
	if opts.ThinkingType == "" {
		opts.ThinkingType = "enabled"
	}
	if opts.ThinkingBudget == 0 {
		opts.ThinkingBudget = 10000
	}
	if opts.MaxTokens == 0 {
		opts.MaxTokens = 16000
	}

	dr := executeDiagnosticRequest(channel, modelName, opts)
	if dr.err != nil {
		result.Status = "error"
		result.Error = dr.err.Error()
		result.DurationMs = dr.duration
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name: "Thinking 模式", Passed: false, Detail: dr.err.Error(),
		})
		return
	}

	result.Status = "success"
	result.DurationMs = dr.duration
	result.Usage = convertUsage(dr.usage)
	result.Pricing = computePricing(dr.usage, dr.priceData, modelName)

	hasReasoning := dr.usage.CompletionTokenDetails.ReasoningTokens > 0
	result.Checks = append(result.Checks, DiagnosticCheck{
		Name: "API 连通性", Passed: true,
		Detail: fmt.Sprintf("响应正常, 耗时 %dms", dr.duration),
	})
	result.Checks = append(result.Checks, DiagnosticCheck{
		Name: "Thinking 返回", Passed: hasReasoning,
		Detail: fmt.Sprintf("reasoning_tokens=%d, type=%s", dr.usage.CompletionTokenDetails.ReasoningTokens, opts.ThinkingType),
	})
}

func runLongContextTest(channel *model.Channel, modelName string, opts DiagnosticOptions, result *DiagnosticChannelResult) {
	if opts.TargetInputTokens == 0 {
		opts.TargetInputTokens = 210000
	}

	dr := executeDiagnosticRequest(channel, modelName, opts)
	if dr.err != nil {
		result.Status = "error"
		result.Error = dr.err.Error()
		result.DurationMs = dr.duration
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name: "长上下文请求", Passed: false, Detail: dr.err.Error(),
		})
		return
	}

	result.Status = "success"
	result.DurationMs = dr.duration
	result.Usage = convertUsage(dr.usage)
	result.Pricing = computePricing(dr.usage, dr.priceData, modelName)

	result.Checks = append(result.Checks, DiagnosticCheck{
		Name: "长上下文请求", Passed: true,
		Detail: fmt.Sprintf("prompt_tokens=%d, 目标=%d", dr.usage.PromptTokens, opts.TargetInputTokens),
	})

	if result.Pricing != nil && result.Pricing.UseTieredPricing {
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name: "分段计费", Passed: true,
			Detail: fmt.Sprintf("使用价格区间: %s", result.Pricing.TierUsed),
		})
	}
}

func runPricingVerifyTest(channel *model.Channel, modelName string, opts DiagnosticOptions, result *DiagnosticChannelResult) {
	runStandardTest(channel, modelName, opts, result)
	if result.Status == "error" {
		return
	}

	if result.Pricing != nil && result.Pricing.UseTieredPricing {
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name: "分段计费启用", Passed: true,
			Detail: fmt.Sprintf("区间: %s, 输入价: $%.2f/MTok, 输出价: $%.2f/MTok",
				result.Pricing.TierUsed, result.Pricing.InputPricePerMTok, result.Pricing.OutputPricePerMTok),
		})
	} else if result.Pricing != nil {
		result.Checks = append(result.Checks, DiagnosticCheck{
			Name: "分段计费启用", Passed: false,
			Detail: "该模型未配置分段计费，使用默认倍率计费",
		})
	}
}

func executeDiagnosticRequest(channel *model.Channel, modelName string, opts DiagnosticOptions) diagnosticResult {
	tik := time.Now()

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	requestPath := "/v1/chat/completions"
	endpointType := opts.EndpointType

	if endpointType != "" {
		if endpointInfo, ok := common.GetDefaultEndpointInfo(constant.EndpointType(endpointType)); ok {
			requestPath = endpointInfo.Path
		}
	}

	c.Request = &http.Request{
		Method: "POST",
		URL:    &url.URL{Path: requestPath},
		Body:   nil,
		Header: make(http.Header),
	}

	cache, err := model.GetUserCache(1)
	if err != nil {
		return diagnosticResult{err: err, duration: time.Since(tik).Milliseconds()}
	}
	cache.WriteContext(c)

	c.Request.Header.Set("Content-Type", "application/json")
	c.Set("channel", channel.Type)
	c.Set("base_url", channel.GetBaseURL())
	group, _ := model.GetUserGroup(1, false)
	c.Set("group", group)

	newAPIError := middleware.SetupContextForSelectedChannel(c, channel, modelName)
	if newAPIError != nil {
		return diagnosticResult{err: newAPIError, duration: time.Since(tik).Milliseconds()}
	}

	var relayFormat types.RelayFormat
	if endpointType != "" {
		switch constant.EndpointType(endpointType) {
		case constant.EndpointTypeAnthropic:
			relayFormat = types.RelayFormatClaude
		case constant.EndpointTypeGemini:
			relayFormat = types.RelayFormatGemini
		default:
			relayFormat = types.RelayFormatOpenAI
		}
	} else {
		relayFormat = types.RelayFormatOpenAI
	}

	request := buildDiagnosticRequest(modelName, opts)

	info, err := relaycommon.GenRelayInfo(c, relayFormat, request, nil)
	if err != nil {
		return diagnosticResult{err: err, duration: time.Since(tik).Milliseconds()}
	}

	info.InitChannelMeta(c)

	err = helper.ModelMappedHelper(c, info, request)
	if err != nil {
		return diagnosticResult{err: err, duration: time.Since(tik).Milliseconds()}
	}

	upstreamModel := info.UpstreamModelName
	request.SetModelName(upstreamModel)

	apiType, _ := common.ChannelType2APIType(channel.Type)
	adaptor := relay.GetAdaptor(apiType)
	if adaptor == nil {
		return diagnosticResult{err: fmt.Errorf("invalid api type: %d", apiType), duration: time.Since(tik).Milliseconds()}
	}

	priceData, err := helper.ModelPriceHelper(c, info, 0, request.GetTokenCountMeta())
	if err != nil {
		return diagnosticResult{err: err, duration: time.Since(tik).Milliseconds()}
	}

	adaptor.Init(info)

	var convertedRequest any
	switch info.RelayMode {
	default:
		if generalReq, ok := request.(*dto.GeneralOpenAIRequest); ok {
			convertedRequest, err = adaptor.ConvertOpenAIRequest(c, info, generalReq)
		} else {
			err = fmt.Errorf("invalid request type")
		}
	}

	if err != nil {
		return diagnosticResult{err: err, duration: time.Since(tik).Milliseconds()}
	}

	jsonData, err := json.Marshal(convertedRequest)
	if err != nil {
		return diagnosticResult{err: err, duration: time.Since(tik).Milliseconds()}
	}

	requestBody := bytes.NewBuffer(jsonData)
	c.Request.Body = io.NopCloser(requestBody)
	resp, err := adaptor.DoRequest(c, info, requestBody)
	if err != nil {
		return diagnosticResult{err: err, duration: time.Since(tik).Milliseconds()}
	}

	var httpResp *http.Response
	if resp != nil {
		httpResp = resp.(*http.Response)
		if httpResp.StatusCode != http.StatusOK {
			bodyBytes, _ := io.ReadAll(httpResp.Body)
			return diagnosticResult{
				err:      fmt.Errorf("上游返回 HTTP %d: %s", httpResp.StatusCode, truncateString(string(bodyBytes), 500)),
				duration: time.Since(tik).Milliseconds(),
			}
		}
	}

	usageA, respErr := adaptor.DoResponse(c, httpResp, info)
	if respErr != nil {
		return diagnosticResult{err: respErr, duration: time.Since(tik).Milliseconds()}
	}
	if usageA == nil {
		return diagnosticResult{err: fmt.Errorf("usage is nil"), duration: time.Since(tik).Milliseconds()}
	}

	usage := usageA.(*dto.Usage)
	duration := time.Since(tik).Milliseconds()

	return diagnosticResult{
		usage:     usage,
		priceData: priceData,
		err:       nil,
		duration:  duration,
	}
}

func buildDiagnosticRequest(modelName string, opts DiagnosticOptions) dto.Request {
	maxTokens := opts.MaxTokens
	if maxTokens == 0 {
		maxTokens = 50
	}

	messages := []dto.Message{
		{Role: "user", Content: "Please respond with a short greeting."},
	}

	if opts.TargetInputTokens > 0 && opts.TargetInputTokens > 1000 {
		padding := strings.Repeat("The quick brown fox jumps over the lazy dog. ", opts.TargetInputTokens/10)
		messages = []dto.Message{
			{Role: "user", Content: padding + "\n\nPlease respond with a short greeting."},
		}
	}

	if opts.EnableCache && len(messages) > 0 {
		cacheControl := map[string]string{"type": "ephemeral"}
		if opts.CacheTTL == "1h" {
			cacheControl["ttl"] = "1h"
		}
		ccRaw, _ := json.Marshal(cacheControl)
		textContent := ""
		if s, ok := messages[0].Content.(string); ok {
			textContent = s
		}
		contentParts := []dto.MediaContent{
			{Type: "text", Text: textContent, CacheControl: ccRaw},
		}
		messages[0].Content = contentParts
	}

	req := &dto.GeneralOpenAIRequest{
		Model:     modelName,
		Stream:    opts.Stream,
		Messages:  messages,
		MaxTokens: maxTokens,
	}

	if opts.EnableThinking {
		thinking := map[string]any{"type": opts.ThinkingType}
		if opts.ThinkingType == "enabled" && opts.ThinkingBudget > 0 {
			thinking["budget_tokens"] = opts.ThinkingBudget
		}
		raw, _ := json.Marshal(thinking)
		req.THINKING = raw

		if opts.ThinkingType == "adaptive" && opts.ThinkingEffort != "" {
			// effort is set via output_config in the request
		}

		if maxTokens < uint(opts.ThinkingBudget)+1000 {
			req.MaxTokens = uint(opts.ThinkingBudget) + 1000
		}
	}

	return req
}

func convertUsage(usage *dto.Usage) *DiagnosticUsage {
	if usage == nil {
		return nil
	}
	return &DiagnosticUsage{
		PromptTokens:          usage.PromptTokens,
		CompletionTokens:      usage.CompletionTokens,
		CachedTokens:          usage.PromptTokensDetails.CachedTokens,
		CacheCreationTokens:   usage.PromptTokensDetails.CachedCreationTokens,
		CacheCreation5mTokens: usage.ClaudeCacheCreation5mTokens,
		CacheCreation1hTokens: usage.ClaudeCacheCreation1hTokens,
		ReasoningTokens:       usage.CompletionTokenDetails.ReasoningTokens,
	}
}

func computePricing(usage *dto.Usage, priceData types.PriceData, modelName string) *DiagnosticPricing {
	if usage == nil {
		return nil
	}

	pricing := &DiagnosticPricing{}

	if priceData.UseTieredPricing && priceData.TieredPricingData != nil {
		tieredData := priceData.TieredPricingData

		totalInput := usage.PromptTokens
		inputTokensK := totalInput / 1000
		if priceTier, found := ratio_setting.GetPriceTierForTokens(modelName, inputTokensK); found {
			tieredData = &types.TieredPricingInfo{
				InputPrice:        priceTier.InputPrice,
				OutputPrice:       priceTier.OutputPrice,
				CacheHitPrice:     priceTier.CacheHitPrice,
				CacheStorePrice:   priceTier.CacheStorePrice,
				CacheStorePrice5m: priceTier.CacheStorePrice5m,
				CacheStorePrice1h: priceTier.CacheStorePrice1h,
				TierMinTokens:     priceTier.MinTokens,
				TierMaxTokens:     priceTier.MaxTokens,
			}
		}

		pricing.UseTieredPricing = true
		pricing.InputPricePerMTok = tieredData.InputPrice
		pricing.OutputPricePerMTok = tieredData.OutputPrice
		pricing.CacheHitPricePerMTok = tieredData.CacheHitPrice

		csp5m := tieredData.CacheStorePrice5m
		if csp5m <= 0 {
			csp5m = tieredData.CacheStorePrice
		}
		csp1h := tieredData.CacheStorePrice1h
		if csp1h <= 0 {
			csp1h = tieredData.CacheStorePrice
		}
		pricing.CacheStore5mPricePerMTok = csp5m
		pricing.CacheStore1hPricePerMTok = csp1h

		if tieredData.TierMaxTokens > 0 {
			pricing.TierUsed = fmt.Sprintf("%dK-%dK", tieredData.TierMinTokens, tieredData.TierMaxTokens)
		} else {
			pricing.TierUsed = fmt.Sprintf("%dK+", tieredData.TierMinTokens)
		}

		dMillion := decimal.NewFromInt(1000000)
		actualPrompt := usage.PromptTokens - usage.PromptTokensDetails.CachedTokens - usage.PromptTokensDetails.CachedCreationTokens
		if actualPrompt < 0 {
			actualPrompt = 0
		}

		inputCost := decimal.NewFromInt(int64(actualPrompt)).Mul(decimal.NewFromFloat(tieredData.InputPrice)).Div(dMillion)
		outputCost := decimal.NewFromInt(int64(usage.CompletionTokens)).Mul(decimal.NewFromFloat(tieredData.OutputPrice)).Div(dMillion)
		cacheCost := decimal.NewFromInt(int64(usage.PromptTokensDetails.CachedTokens)).Mul(decimal.NewFromFloat(tieredData.CacheHitPrice)).Div(dMillion)

		cc5m := usage.ClaudeCacheCreation5mTokens
		cc1h := usage.ClaudeCacheCreation1hTokens
		ccRemaining := usage.PromptTokensDetails.CachedCreationTokens - cc5m - cc1h
		if ccRemaining < 0 {
			ccRemaining = 0
		}

		cacheCreateCost := decimal.NewFromInt(int64(ccRemaining)).Mul(decimal.NewFromFloat(tieredData.CacheStorePrice)).Div(dMillion).
			Add(decimal.NewFromInt(int64(cc5m)).Mul(decimal.NewFromFloat(csp5m)).Div(dMillion)).
			Add(decimal.NewFromInt(int64(cc1h)).Mul(decimal.NewFromFloat(csp1h)).Div(dMillion))

		total := inputCost.Add(outputCost).Add(cacheCost).Add(cacheCreateCost)
		pricing.TotalCostUSD, _ = total.Float64()
	} else {
		pricing.UseTieredPricing = false
		pricing.TierUsed = "默认倍率"
	}

	return pricing
}

func truncateString(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "..."
}

// DiagnosticGetChannels returns all channels for the diagnostic tool
func DiagnosticGetChannels(c *gin.Context) {
	channels, err := model.GetAllChannels(0, 0, true, false)
	if err != nil {
		common.ApiError(c, err)
		return
	}

	type channelInfo struct {
		ID     int    `json:"id"`
		Name   string `json:"name"`
		Type   int    `json:"type"`
		Status int    `json:"status"`
		Models string `json:"models"`
	}

	list := make([]channelInfo, 0, len(channels))
	for _, ch := range channels {
		list = append(list, channelInfo{
			ID:     ch.Id,
			Name:   ch.Name,
			Type:   ch.Type,
			Status: ch.Status,
			Models: ch.Models,
		})
	}

	common.ApiSuccess(c, list)
}
