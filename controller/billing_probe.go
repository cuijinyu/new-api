package controller

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/model"
	"github.com/gin-gonic/gin"
	"github.com/shopspring/decimal"
)

const billingProbeDefaultPrompt = "Please reply with one short sentence for a billing validation probe."

type BillingProbeRequest struct {
	TokenID        int      `json:"token_id"`
	APIKey         string   `json:"api_key"`
	ChannelID      int      `json:"channel_id"`
	BaseURL        string   `json:"base_url"`
	Models         []string `json:"models"`
	Cases          []string `json:"cases"`
	Prompt         string   `json:"prompt"`
	MaxTokens      int      `json:"max_tokens"`
	TimeoutSeconds int      `json:"timeout_seconds"`
	LogWaitSeconds int      `json:"log_wait_seconds"`
}

type BillingProbeResponse struct {
	BaseURL string               `json:"base_url"`
	Results []BillingProbeResult `json:"results"`
}

type BillingProbeResult struct {
	Name             string                   `json:"name"`
	Model            string                   `json:"model"`
	Case             string                   `json:"case"`
	HTTPStatus       int                      `json:"http_status"`
	RequestID        string                   `json:"request_id,omitempty"`
	HasImage         bool                     `json:"has_image"`
	LogID            int                      `json:"log_id,omitempty"`
	ChannelID        int                      `json:"channel_id,omitempty"`
	Quota            int                      `json:"quota,omitempty"`
	ExpectedQuota    int                      `json:"expected_quota,omitempty"`
	Delta            int                      `json:"delta,omitempty"`
	PromptTokens     int                      `json:"prompt_tokens,omitempty"`
	CompletionTokens int                      `json:"completion_tokens,omitempty"`
	ImageTokens      int                      `json:"image_tokens,omitempty"`
	TokenSource      string                   `json:"token_source,omitempty"`
	IsStream         bool                     `json:"is_stream"`
	Billing          *GeminiBillingDebitCheck `json:"billing,omitempty"`
	Status           string                   `json:"status"`
	Message          string                   `json:"message,omitempty"`
	Other            map[string]any           `json:"other,omitempty"`
}

func BillingProbeRun(c *gin.Context) {
	var req BillingProbeRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "参数错误: "+err.Error())
		return
	}

	apiKey, tokenID, err := resolveBillingProbeKey(req)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	if tokenID == 0 {
		common.ApiErrorMsg(c, "端到端扣费校验必须选择系统内 token")
		return
	}

	models := normalizeBillingProbeModels(req.Models)
	cases := normalizeBillingProbeCases(req.Cases)
	if len(models) == 0 || len(cases) == 0 {
		common.ApiErrorMsg(c, "至少需要一个模型和一个校验场景")
		return
	}
	if len(models)*len(cases) > 24 {
		common.ApiErrorMsg(c, "单次最多运行 24 个计费校验 probe")
		return
	}

	baseURL := strings.TrimRight(req.BaseURL, "/")
	if baseURL == "" {
		baseURL = inferLocalRelayBaseURL(c)
	}
	prompt := strings.TrimSpace(req.Prompt)
	if prompt == "" {
		prompt = billingProbeDefaultPrompt
	}
	maxTokens := req.MaxTokens
	if maxTokens <= 0 {
		maxTokens = 32
	}
	timeout := time.Duration(req.TimeoutSeconds) * time.Second
	if timeout <= 0 {
		timeout = 5 * time.Minute
	}
	logWait := time.Duration(req.LogWaitSeconds) * time.Second
	if logWait <= 0 {
		logWait = 20 * time.Second
	}

	client := &http.Client{Timeout: timeout}
	results := make([]BillingProbeResult, 0, len(models)*len(cases))
	for _, modelName := range models {
		for _, testCase := range cases {
			results = append(results, runBillingProbeCase(client, baseURL, apiKey, tokenID, req.ChannelID, modelName, testCase, prompt, maxTokens, logWait))
		}
	}

	common.ApiSuccess(c, BillingProbeResponse{
		BaseURL: baseURL,
		Results: results,
	})
}

func BillingProbeGetChannels(c *gin.Context) {
	DiagnosticGetChannels(c)
}

func BillingProbeGetTokens(c *gin.Context) {
	type tokenInfo struct {
		ID             int    `json:"id"`
		Name           string `json:"name"`
		UserID         int    `json:"user_id"`
		Username       string `json:"username"`
		Status         int    `json:"status"`
		RemainQuota    int    `json:"remain_quota"`
		UsedQuota      int    `json:"used_quota"`
		UnlimitedQuota bool   `json:"unlimited_quota"`
	}

	var tokens []tokenInfo
	err := model.DB.Table("tokens").
		Select("tokens.id, tokens.name, tokens.user_id, users.username, tokens.status, tokens.remain_quota, tokens.used_quota, tokens.unlimited_quota").
		Joins("left join users on users.id = tokens.user_id").
		Where("tokens.deleted_at IS NULL AND tokens.status = ?", 1).
		Order("tokens.id desc").
		Limit(500).
		Scan(&tokens).Error
	if err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, tokens)
}

func resolveBillingProbeKey(req BillingProbeRequest) (string, int, error) {
	key := strings.TrimSpace(req.APIKey)
	var token *model.Token
	var err error

	if req.TokenID > 0 {
		token, err = model.GetTokenById(req.TokenID)
		if err != nil {
			return "", 0, fmt.Errorf("测试 token 不存在: %w", err)
		}
		key = token.Key
	} else if key != "" {
		token, _ = model.GetTokenByKey(strings.TrimPrefix(key, "sk-"), false)
	} else {
		return "", 0, errors.New("请选择测试 token，或提供 api_key")
	}

	if req.ChannelID > 0 {
		if token == nil {
			return "", 0, errors.New("指定 channel_id 时必须选择系统内 token，不能只传 api_key")
		}
		if !model.IsAdmin(token.UserId) {
			return "", 0, errors.New("指定 channel_id 需要使用 admin/root 用户的 token")
		}
		key = strings.TrimPrefix(key, "sk-") + "-" + strconv.Itoa(req.ChannelID)
	}

	if !strings.HasPrefix(key, "sk-") {
		key = "sk-" + key
	}
	if token != nil {
		return key, token.Id, nil
	}
	return key, 0, nil
}

func normalizeBillingProbeModels(models []string) []string {
	if len(models) == 0 {
		return []string{"gpt-4o-mini"}
	}
	out := make([]string, 0, len(models))
	for _, item := range models {
		for _, modelName := range strings.Split(item, ",") {
			modelName = strings.TrimSpace(modelName)
			if modelName == "" {
				continue
			}
			if strings.EqualFold(modelName, "latest-image") {
				out = append(out, geminiBillingLatestImageModels...)
				continue
			}
			out = append(out, modelName)
		}
	}
	return dedupeStrings(out)
}

func normalizeBillingProbeCases(cases []string) []string {
	if len(cases) == 0 {
		return []string{"openai_chat"}
	}
	valid := map[string]bool{
		"openai_chat":        true,
		"openai_chat_stream": true,
		"openai_responses":   true,
		"openai_image":       true,
		"gemini_native":      true,
		"gemini_stream":      true,
		"gemini_edit":        true,
	}
	out := make([]string, 0, len(cases))
	for _, item := range cases {
		for _, testCase := range strings.Split(item, ",") {
			testCase = strings.TrimSpace(testCase)
			if valid[testCase] {
				out = append(out, testCase)
			}
		}
	}
	return dedupeStrings(out)
}

func runBillingProbeCase(client *http.Client, baseURL, apiKey string, tokenID int, requestedChannelID int, modelName, testCase, prompt string, maxTokens int, logWait time.Duration) BillingProbeResult {
	result := BillingProbeResult{
		Name:   modelName + "/" + testCase,
		Model:  modelName,
		Case:   testCase,
		Status: "fail",
	}

	beforeBalance, err := readGeminiBillingBalanceSnapshot(tokenID, requestedChannelID)
	if err != nil {
		result.Message = "read balance before request failed: " + err.Error()
		return result
	}

	startedAt := common.GetTimestamp()
	body, requestID, statusCode, err := callBillingProbe(client, baseURL, apiKey, modelName, testCase, prompt, maxTokens)
	result.HTTPStatus = statusCode
	result.RequestID = requestID
	if err != nil {
		result.Message = err.Error()
		return result
	}
	result.HasImage = geminiBillingResponseHasImage(body, testCase)
	if statusCode < 200 || statusCode >= 300 {
		result.Message = truncateString(body, 500)
		return result
	}
	if requestID == "" {
		result.Message = "响应缺少 X-Oneapi-Request-Id，无法定位 consume log"
		return result
	}

	logRow, err := waitGeminiBillingConsumeLog(requestID, tokenID, modelName, startedAt, logWait)
	if err != nil {
		result.Message = err.Error()
		return result
	}

	other, err := parseGeminiBillingOther(logRow.Other)
	if err != nil {
		result.Message = "usage log other 不是合法 JSON: " + err.Error()
		return result
	}

	expectedQuota, err := calculateBillingProbeExpectedQuota(*logRow, other)
	if err != nil {
		result.Message = "无法复算 quota: " + err.Error()
		return result
	}

	result.LogID = logRow.ID
	result.ChannelID = logRow.ChannelID
	result.Quota = logRow.Quota
	result.ExpectedQuota = expectedQuota
	result.Delta = logRow.Quota - expectedQuota
	result.PromptTokens = logRow.PromptTokens
	result.CompletionTokens = logRow.CompletionTokens
	result.ImageTokens = geminiBillingIntField(other, "output_image_tokens", "image_completion_tokens")
	result.TokenSource = geminiBillingStringField(other, "gemini_image_output_token_source")
	result.IsStream = logRow.IsStream
	result.Other = other
	result.Billing = waitGeminiBillingDebitCheck(beforeBalance, logRow.ChannelID, expectedQuota, logWait)

	if result.Delta != 0 {
		result.Message = fmt.Sprintf("consume log quota 不一致: actual=%d expected=%d delta=%d", result.Quota, result.ExpectedQuota, result.Delta)
		return result
	}
	if result.Billing == nil || !result.Billing.Settled {
		result.Message = "actual debit does not match expected quota"
		if result.Billing != nil && len(result.Billing.Mismatches) > 0 {
			result.Message += ": " + strings.Join(result.Billing.Mismatches, ", ")
		}
		return result
	}

	result.Status = "pass"
	result.Message = "generation, consume log and actual debit are consistent"
	return result
}

func callBillingProbe(client *http.Client, baseURL, apiKey, modelName, testCase, prompt string, maxTokens int) (body string, requestID string, statusCode int, err error) {
	var endpoint string
	var payload []byte
	escapedModel := url.PathEscape(modelName)

	switch testCase {
	case "openai_chat":
		endpoint = baseURL + "/v1/chat/completions"
		payload, _ = json.Marshal(map[string]any{
			"model":      modelName,
			"messages":   []map[string]string{{"role": "user", "content": prompt}},
			"max_tokens": maxTokens,
			"stream":     false,
		})
	case "openai_chat_stream":
		endpoint = baseURL + "/v1/chat/completions"
		payload, _ = json.Marshal(map[string]any{
			"model":      modelName,
			"messages":   []map[string]string{{"role": "user", "content": prompt}},
			"max_tokens": maxTokens,
			"stream":     true,
		})
	case "openai_responses":
		endpoint = baseURL + "/v1/responses"
		payload, _ = json.Marshal(map[string]any{
			"model":             modelName,
			"input":             prompt,
			"max_output_tokens": maxTokens,
		})
	case "openai_image":
		endpoint = baseURL + "/v1/images/generations"
		payload, _ = json.Marshal(map[string]any{
			"model":           modelName,
			"prompt":          prompt,
			"n":               1,
			"response_format": "b64_json",
		})
	case "gemini_native":
		endpoint = fmt.Sprintf("%s/v1beta/models/%s:generateContent", baseURL, escapedModel)
		payload, _ = json.Marshal(geminiBillingNativePayload(prompt, false))
	case "gemini_stream":
		endpoint = fmt.Sprintf("%s/v1beta/models/%s:streamGenerateContent?alt=sse", baseURL, escapedModel)
		payload, _ = json.Marshal(geminiBillingNativePayload(prompt, false))
	case "gemini_edit":
		endpoint = fmt.Sprintf("%s/v1beta/models/%s:generateContent", baseURL, escapedModel)
		payload, _ = json.Marshal(geminiBillingNativePayload(prompt+" Use the provided input image only as a color reference.", true))
	default:
		return "", "", 0, fmt.Errorf("未知校验场景: %s", testCase)
	}

	req, err := http.NewRequest(http.MethodPost, endpoint, bytes.NewReader(payload))
	if err != nil {
		return "", "", 0, err
	}
	req.Header.Set("Authorization", "Bearer "+apiKey)
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return "", "", 0, err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", resp.Header.Get(geminiBillingRequestIDHeader), resp.StatusCode, err
	}
	return string(raw), resp.Header.Get(geminiBillingRequestIDHeader), resp.StatusCode, nil
}

func calculateBillingProbeExpectedQuota(logRow geminiBillingLog, other map[string]any) (int, error) {
	groupRatio := geminiBillingFloatFieldDefault(other, "group_ratio", 1)
	condMultiplier := geminiBillingFloatFieldDefault(other, "billing_cond_multiplier", 1)
	modelPrice := geminiBillingFloatFieldDefault(other, "model_price", 0)
	modelRatio := geminiBillingFloatFieldDefault(other, "model_ratio", 0)

	if modelPrice > 0 && modelRatio == 0 {
		quota := decimal.NewFromFloat(modelPrice).
			Mul(decimal.NewFromFloat(common.QuotaPerUnit)).
			Mul(decimal.NewFromFloat(groupRatio)).
			Mul(decimal.NewFromFloat(condMultiplier))
		return int(quota.Round(0).IntPart()), nil
	}

	if geminiBillingBoolField(other, "tiered_pricing") {
		return calculateBillingProbeTieredQuota(logRow, other, groupRatio, condMultiplier), nil
	}

	if modelRatio == 0 {
		return 0, errors.New("other.model_ratio 缺失或为 0，且不是按价模型")
	}

	completionRatio := geminiBillingFloatFieldDefault(other, "completion_ratio", 1)
	cacheRatio := geminiBillingFloatFieldDefault(other, "cache_ratio", 1)
	cacheCreationRatio := geminiBillingFloatFieldDefault(other, "cache_creation_ratio", 1)
	imageRatio := geminiBillingFloatFieldDefault(other, "image_ratio", 1)
	imageCompletionRatio := geminiBillingFloatFieldDefault(other, "image_completion_ratio", 1)

	promptTokens := decimal.NewFromInt(int64(logRow.PromptTokens))
	cacheTokens := decimal.NewFromInt(int64(geminiBillingIntField(other, "cache_tokens")))
	cacheCreationTokens := decimal.NewFromInt(int64(geminiBillingIntField(other, "cache_creation_tokens")))
	imageInputTokens := decimal.NewFromInt(int64(geminiBillingIntField(other, "input_image_tokens", "image_output")))
	audioInputTokens := decimal.NewFromInt(int64(geminiBillingIntField(other, "input_audio_tokens", "audio_input_token_count")))

	baseTokens := promptTokens.Sub(cacheTokens).Sub(cacheCreationTokens).Sub(imageInputTokens).Sub(audioInputTokens)
	if baseTokens.IsNegative() {
		baseTokens = decimal.Zero
	}

	promptQuota := baseTokens.
		Add(cacheTokens.Mul(decimal.NewFromFloat(cacheRatio))).
		Add(cacheCreationTokens.Mul(decimal.NewFromFloat(cacheCreationRatio))).
		Add(imageInputTokens.Mul(decimal.NewFromFloat(imageRatio)))

	if audioPrice := geminiBillingFloatFieldDefault(other, "audio_input_price", 0); audioPrice > 0 {
		audioQuota := decimal.NewFromFloat(audioPrice).
			Div(decimal.NewFromInt(1000000)).
			Mul(audioInputTokens).
			Mul(decimal.NewFromFloat(common.QuotaPerUnit)).
			Mul(decimal.NewFromFloat(groupRatio))
		promptQuota = promptQuota.Add(audioQuota.Div(decimal.NewFromFloat(modelRatio)).Div(decimal.NewFromFloat(groupRatio)))
	}

	completionTokens := decimal.NewFromInt(int64(logRow.CompletionTokens))
	imageOutputTokens := decimal.NewFromInt(int64(geminiBillingIntField(other, "output_image_tokens", "image_completion_tokens")))
	textCompletionTokens := completionTokens.Sub(imageOutputTokens)
	if textCompletionTokens.IsNegative() {
		textCompletionTokens = decimal.Zero
	}

	completionQuota := textCompletionTokens.Mul(decimal.NewFromFloat(completionRatio)).
		Add(imageOutputTokens.Mul(decimal.NewFromFloat(imageCompletionRatio)))

	claudeInputMult := geminiBillingFloatFieldDefault(other, "claude_200k_input_multiplier", 1)
	claudeOutputMult := geminiBillingFloatFieldDefault(other, "claude_200k_output_multiplier", 1)
	if claudeInputMult != 1 {
		promptQuota = promptQuota.Mul(decimal.NewFromFloat(claudeInputMult))
	}
	if claudeOutputMult != 1 {
		completionQuota = completionQuota.Mul(decimal.NewFromFloat(claudeOutputMult))
	}

	quota := promptQuota.Add(completionQuota).
		Mul(decimal.NewFromFloat(modelRatio)).
		Mul(decimal.NewFromFloat(groupRatio)).
		Mul(decimal.NewFromFloat(condMultiplier))

	quota = quota.Add(billingProbeToolQuota(other, groupRatio))

	ratio := decimal.NewFromFloat(modelRatio).Mul(decimal.NewFromFloat(groupRatio))
	if !ratio.IsZero() && quota.LessThanOrEqual(decimal.Zero) && logRow.PromptTokens+logRow.CompletionTokens > 0 {
		quota = decimal.NewFromInt(1)
	}

	return int(quota.Round(0).IntPart()), nil
}

func calculateBillingProbeTieredQuota(logRow geminiBillingLog, other map[string]any, groupRatio float64, condMultiplier float64) int {
	promptTokens := geminiBillingIntField(other, "input_text_tokens")
	if promptTokens == 0 {
		promptTokens = logRow.PromptTokens
	}
	cacheTokens := geminiBillingIntField(other, "cache_tokens")
	cacheCreationTokens := geminiBillingIntField(other, "cache_creation_tokens")
	if geminiBillingBoolField(other, "tiered_prompt_tokens_include_cache") {
		promptTokens -= cacheTokens + cacheCreationTokens
	}
	promptTokens -= geminiBillingIntField(other, "input_image_tokens", "image_output")
	if promptTokens < 0 {
		promptTokens = 0
	}

	inputPrice := geminiBillingFloatFieldDefault(other, "tiered_input_price", 0)
	outputPrice := geminiBillingFloatFieldDefault(other, "tiered_output_price", 0)
	cacheHitPrice := geminiBillingFloatFieldDefault(other, "tiered_cache_hit_price", 0)
	cacheStorePrice := geminiBillingFloatFieldDefault(other, "tiered_cache_store_price", 0)
	cacheStore5mPrice := geminiBillingFloatFieldDefault(other, "tiered_cache_store_price_5m", cacheStorePrice)
	cacheStore1hPrice := geminiBillingFloatFieldDefault(other, "tiered_cache_store_price_1h", cacheStorePrice)
	cacheCreation5m := geminiBillingIntField(other, "tiered_cache_creation_tokens_5m", "cache_creation_tokens_5m")
	cacheCreation1h := geminiBillingIntField(other, "tiered_cache_creation_tokens_1h", "cache_creation_tokens_1h")
	cacheCreationRemaining := geminiBillingIntField(other, "tiered_cache_creation_tokens_remaining")
	if cacheCreationRemaining == 0 {
		cacheCreationRemaining = cacheCreationTokens - cacheCreation5m - cacheCreation1h
		if cacheCreationRemaining < 0 {
			cacheCreationRemaining = 0
		}
	}

	dMillion := decimal.NewFromInt(1000000)
	total := decimal.NewFromInt(int64(promptTokens)).Mul(decimal.NewFromFloat(inputPrice)).Div(dMillion).
		Add(decimal.NewFromInt(int64(logRow.CompletionTokens)).Mul(decimal.NewFromFloat(outputPrice)).Div(dMillion)).
		Add(decimal.NewFromInt(int64(cacheTokens)).Mul(decimal.NewFromFloat(cacheHitPrice)).Div(dMillion)).
		Add(decimal.NewFromInt(int64(cacheCreationRemaining)).Mul(decimal.NewFromFloat(cacheStorePrice)).Div(dMillion)).
		Add(decimal.NewFromInt(int64(cacheCreation5m)).Mul(decimal.NewFromFloat(cacheStore5mPrice)).Div(dMillion)).
		Add(decimal.NewFromInt(int64(cacheCreation1h)).Mul(decimal.NewFromFloat(cacheStore1hPrice)).Div(dMillion))

	quota := total.
		Mul(decimal.NewFromFloat(common.QuotaPerUnit)).
		Mul(decimal.NewFromFloat(groupRatio)).
		Mul(decimal.NewFromFloat(condMultiplier)).
		Add(billingProbeToolQuota(other, groupRatio))

	return int(quota.Round(0).IntPart())
}

func billingProbeToolQuota(other map[string]any, groupRatio float64) decimal.Decimal {
	total := decimal.Zero
	if geminiBillingBoolField(other, "web_search") {
		price := geminiBillingFloatFieldDefault(other, "web_search_price", 0)
		count := geminiBillingIntField(other, "web_search_call_count")
		total = total.Add(decimal.NewFromFloat(price).Mul(decimal.NewFromInt(int64(count))).Div(decimal.NewFromInt(1000)))
	}
	if geminiBillingBoolField(other, "file_search") {
		price := geminiBillingFloatFieldDefault(other, "file_search_price", 0)
		count := geminiBillingIntField(other, "file_search_call_count")
		total = total.Add(decimal.NewFromFloat(price).Mul(decimal.NewFromInt(int64(count))).Div(decimal.NewFromInt(1000)))
	}
	if geminiBillingBoolField(other, "image_generation_call") {
		total = total.Add(decimal.NewFromFloat(geminiBillingFloatFieldDefault(other, "image_generation_call_price", 0)))
	}
	return total.Mul(decimal.NewFromFloat(common.QuotaPerUnit)).Mul(decimal.NewFromFloat(groupRatio))
}
