package controller

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/model"
	"github.com/gin-gonic/gin"
	"github.com/shopspring/decimal"
)

const (
	geminiBillingRequestIDHeader = "X-Oneapi-Request-Id"
	geminiBillingLogTypeConsume  = 2
	geminiBillingDefaultPrompt   = "Generate one simple original image of a small ceramic teapot on a white table, studio lighting."
)

var geminiBillingLatestImageModels = []string{
	"gemini-2.5-flash-image",
	"gemini-2.5-flash-image-preview",
	"gemini-3.1-flash-image",
	"gemini-3.1-flash-image-preview",
	"gemini-3-pro-image",
	"gemini-3-pro-image-preview",
	"nano-banana",
	"nano-banana-pro",
}

type GeminiBillingProbeRequest struct {
	TokenID        int      `json:"token_id"`
	APIKey         string   `json:"api_key"`
	ChannelID      int      `json:"channel_id"`
	BaseURL        string   `json:"base_url"`
	Models         []string `json:"models"`
	Cases          []string `json:"cases"`
	Prompt         string   `json:"prompt"`
	TimeoutSeconds int      `json:"timeout_seconds"`
	LogWaitSeconds int      `json:"log_wait_seconds"`
}

type GeminiBillingProbeResponse struct {
	BaseURL string                     `json:"base_url"`
	Results []GeminiBillingProbeResult `json:"results"`
}

type GeminiBillingProbeResult struct {
	Name             string         `json:"name"`
	Model            string         `json:"model"`
	Case             string         `json:"case"`
	HTTPStatus       int            `json:"http_status"`
	RequestID        string         `json:"request_id,omitempty"`
	HasImage         bool           `json:"has_image"`
	LogID            int            `json:"log_id,omitempty"`
	ChannelID        int            `json:"channel_id,omitempty"`
	Quota            int            `json:"quota,omitempty"`
	ExpectedQuota    int            `json:"expected_quota,omitempty"`
	Delta            int            `json:"delta,omitempty"`
	PromptTokens     int            `json:"prompt_tokens,omitempty"`
	CompletionTokens int            `json:"completion_tokens,omitempty"`
	ImageTokens      int            `json:"image_tokens,omitempty"`
	TokenSource      string         `json:"token_source,omitempty"`
	IsStream         bool           `json:"is_stream"`
	Status           string         `json:"status"`
	Message          string         `json:"message,omitempty"`
	Other            map[string]any `json:"other,omitempty"`
}

type geminiBillingLog struct {
	ID               int
	ModelName        string
	Quota            int
	PromptTokens     int
	CompletionTokens int
	IsStream         bool
	ChannelID        int `gorm:"column:channel_id"`
	RequestID        string
	Other            string
}

// DiagnosticGeminiBillingProbe runs real Gemini image requests through the local relay
// and verifies the resulting consume log quota. The route is admin-only.
func DiagnosticGeminiBillingProbe(c *gin.Context) {
	var req GeminiBillingProbeRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "参数错误: "+err.Error())
		return
	}

	apiKey, tokenID, err := resolveGeminiBillingProbeKey(req)
	if err != nil {
		common.ApiError(c, err)
		return
	}

	models := normalizeGeminiBillingModels(req.Models)
	cases := normalizeGeminiBillingCases(req.Cases)
	if len(models) == 0 || len(cases) == 0 {
		common.ApiErrorMsg(c, "至少需要一个模型和一个测试模式")
		return
	}
	if len(models)*len(cases) > 24 {
		common.ApiErrorMsg(c, "单次最多运行 24 个 Gemini 计费探针")
		return
	}

	baseURL := strings.TrimRight(req.BaseURL, "/")
	if baseURL == "" {
		baseURL = inferLocalRelayBaseURL(c)
	}
	prompt := strings.TrimSpace(req.Prompt)
	if prompt == "" {
		prompt = geminiBillingDefaultPrompt
	}
	timeout := time.Duration(req.TimeoutSeconds) * time.Second
	if timeout <= 0 {
		timeout = 5 * time.Minute
	}
	logWait := time.Duration(req.LogWaitSeconds) * time.Second
	if logWait <= 0 {
		logWait = 15 * time.Second
	}

	client := &http.Client{Timeout: timeout}
	results := make([]GeminiBillingProbeResult, 0, len(models)*len(cases))
	for _, modelName := range models {
		for _, testCase := range cases {
			results = append(results, runGeminiBillingProbeCase(client, baseURL, apiKey, tokenID, modelName, testCase, prompt, logWait))
		}
	}

	common.ApiSuccess(c, GeminiBillingProbeResponse{
		BaseURL: baseURL,
		Results: results,
	})
}

func resolveGeminiBillingProbeKey(req GeminiBillingProbeRequest) (string, int, error) {
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

func normalizeGeminiBillingModels(models []string) []string {
	if len(models) == 0 {
		return []string{"gemini-2.5-flash-image"}
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

func normalizeGeminiBillingCases(cases []string) []string {
	if len(cases) == 0 {
		return []string{"native"}
	}
	valid := map[string]bool{
		"native":        true,
		"native_stream": true,
		"native_edit":   true,
		"openai_image":  true,
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

func runGeminiBillingProbeCase(client *http.Client, baseURL, apiKey string, tokenID int, modelName, testCase, prompt string, logWait time.Duration) GeminiBillingProbeResult {
	result := GeminiBillingProbeResult{
		Name:   modelName + "/" + testCase,
		Model:  modelName,
		Case:   testCase,
		Status: "fail",
	}

	startedAt := common.GetTimestamp()
	body, requestID, statusCode, err := callGeminiBillingProbe(client, baseURL, apiKey, modelName, testCase, prompt)
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

	expectedQuota, err := calculateGeminiBillingExpectedQuota(*logRow, other)
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

	if result.Delta != 0 {
		result.Message = fmt.Sprintf("quota 不一致: actual=%d expected=%d delta=%d", result.Quota, result.ExpectedQuota, result.Delta)
		return result
	}
	if result.HasImage && result.ImageTokens == 0 {
		result.Message = "响应包含图片，但 consume log 没有 output_image_tokens"
		return result
	}
	if !result.HasImage && result.ImageTokens > 0 {
		result.Status = "warn"
		result.Message = "consume log 有图片 token，但响应里没有检测到图片"
		return result
	}

	result.Status = "pass"
	result.Message = "quota 与 consume log 复算一致"
	return result
}

func callGeminiBillingProbe(client *http.Client, baseURL, apiKey, modelName, testCase, prompt string) (body string, requestID string, statusCode int, err error) {
	var endpoint string
	var payload []byte
	escapedModel := url.PathEscape(modelName)

	switch testCase {
	case "native":
		endpoint = fmt.Sprintf("%s/v1beta/models/%s:generateContent", baseURL, escapedModel)
		payload, _ = json.Marshal(geminiBillingNativePayload(prompt, false))
	case "native_stream":
		endpoint = fmt.Sprintf("%s/v1beta/models/%s:streamGenerateContent?alt=sse", baseURL, escapedModel)
		payload, _ = json.Marshal(geminiBillingNativePayload(prompt, false))
	case "native_edit":
		endpoint = fmt.Sprintf("%s/v1beta/models/%s:generateContent", baseURL, escapedModel)
		payload, _ = json.Marshal(geminiBillingNativePayload(prompt+" Use the provided tiny input image only as a color reference.", true))
	case "openai_image":
		endpoint = baseURL + "/v1/images/generations"
		payload, _ = json.Marshal(map[string]any{
			"model":           modelName,
			"prompt":          prompt,
			"n":               1,
			"response_format": "b64_json",
		})
	default:
		return "", "", 0, fmt.Errorf("未知测试模式: %s", testCase)
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

func geminiBillingNativePayload(prompt string, withImage bool) map[string]any {
	parts := []map[string]any{{"text": prompt}}
	if withImage {
		parts = append(parts, map[string]any{
			"inlineData": map[string]any{
				"mimeType": "image/png",
				"data":     "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
			},
		})
	}
	return map[string]any{
		"contents": []map[string]any{
			{"parts": parts},
		},
		"generationConfig": map[string]any{
			"responseModalities": []string{"TEXT", "IMAGE"},
			"imageConfig": map[string]any{
				"aspectRatio": "1:1",
				"imageSize":   "1K",
			},
		},
	}
}

func waitGeminiBillingConsumeLog(requestID string, tokenID int, modelName string, startedAt int64, wait time.Duration) (*geminiBillingLog, error) {
	deadline := time.Now().Add(wait)
	var lastErr error
	for {
		var logRow geminiBillingLog
		tx := model.LOG_DB.Table("logs").Where("type = ?", geminiBillingLogTypeConsume)
		if requestID != "" {
			tx = tx.Where("request_id = ?", requestID)
		} else {
			tx = tx.Where("1 = 0")
		}
		err := tx.Order("id DESC").First(&logRow).Error
		if err != nil && tokenID > 0 {
			fallbackTx := model.LOG_DB.Table("logs").
				Where("type = ? AND token_id = ? AND model_name = ? AND created_at >= ?", geminiBillingLogTypeConsume, tokenID, modelName, startedAt-1)
			err = fallbackTx.Order("id DESC").First(&logRow).Error
		}
		if err == nil {
			return &logRow, nil
		}
		lastErr = err
		if time.Now().After(deadline) {
			return nil, fmt.Errorf("找不到 request_id=%s token_id=%d model=%s 的 consume log: %w", requestID, tokenID, modelName, lastErr)
		}
		time.Sleep(500 * time.Millisecond)
	}
}

func parseGeminiBillingOther(raw string) (map[string]any, error) {
	if strings.TrimSpace(raw) == "" {
		return map[string]any{}, nil
	}
	var other map[string]any
	err := json.Unmarshal([]byte(raw), &other)
	return other, err
}

func calculateGeminiBillingExpectedQuota(logRow geminiBillingLog, other map[string]any) (int, error) {
	if geminiBillingBoolField(other, "tiered_pricing") {
		return 0, errors.New("暂不支持 tiered_pricing 日志复算")
	}
	if geminiBillingBoolField(other, "image_generation_call") || geminiBillingBoolField(other, "web_search") || geminiBillingBoolField(other, "file_search") {
		return 0, errors.New("暂不支持额外工具/固定调用费日志复算")
	}

	modelRatio, ok := geminiBillingRequiredFloat(other, "model_ratio")
	if !ok {
		return 0, errors.New("other.model_ratio 缺失")
	}
	groupRatio := geminiBillingFloatFieldDefault(other, "group_ratio", 1)
	completionRatio := geminiBillingFloatFieldDefault(other, "completion_ratio", 1)
	cacheRatio := geminiBillingFloatFieldDefault(other, "cache_ratio", 1)
	cacheCreationRatio := geminiBillingFloatFieldDefault(other, "cache_creation_ratio", 1)
	imageRatio := geminiBillingFloatFieldDefault(other, "image_ratio", 1)
	imageCompletionRatio := geminiBillingFloatFieldDefault(other, "image_completion_ratio", 1)
	condMultiplier := geminiBillingFloatFieldDefault(other, "billing_cond_multiplier", 1)

	promptTokens := decimal.NewFromInt(int64(logRow.PromptTokens))
	cacheTokens := decimal.NewFromInt(int64(geminiBillingIntField(other, "cache_tokens")))
	cacheCreationTokens := decimal.NewFromInt(int64(geminiBillingIntField(other, "cache_creation_tokens")))
	imageInputTokens := decimal.NewFromInt(int64(geminiBillingIntField(other, "input_image_tokens", "image_output")))

	baseTokens := promptTokens.Sub(cacheTokens).Sub(cacheCreationTokens).Sub(imageInputTokens)
	if baseTokens.IsNegative() {
		baseTokens = decimal.Zero
	}

	promptQuota := baseTokens.
		Add(cacheTokens.Mul(decimal.NewFromFloat(cacheRatio))).
		Add(cacheCreationTokens.Mul(decimal.NewFromFloat(cacheCreationRatio))).
		Add(imageInputTokens.Mul(decimal.NewFromFloat(imageRatio)))

	completionTokens := decimal.NewFromInt(int64(logRow.CompletionTokens))
	imageOutputTokens := decimal.NewFromInt(int64(geminiBillingIntField(other, "output_image_tokens", "image_completion_tokens")))
	textCompletionTokens := completionTokens.Sub(imageOutputTokens)
	if textCompletionTokens.IsNegative() {
		textCompletionTokens = decimal.Zero
	}

	completionQuota := textCompletionTokens.Mul(decimal.NewFromFloat(completionRatio)).
		Add(imageOutputTokens.Mul(decimal.NewFromFloat(imageCompletionRatio)))

	quota := promptQuota.Add(completionQuota).
		Mul(decimal.NewFromFloat(modelRatio)).
		Mul(decimal.NewFromFloat(groupRatio)).
		Mul(decimal.NewFromFloat(condMultiplier))

	ratio := decimal.NewFromFloat(modelRatio).Mul(decimal.NewFromFloat(groupRatio))
	if !ratio.IsZero() && quota.LessThanOrEqual(decimal.Zero) && logRow.PromptTokens+logRow.CompletionTokens > 0 {
		quota = decimal.NewFromInt(1)
	}

	return int(quota.Round(0).IntPart()), nil
}

func geminiBillingResponseHasImage(body string, testCase string) bool {
	if testCase == "native_stream" {
		return strings.Contains(body, `"inlineData"`) || strings.Contains(body, `"inline_data"`)
	}
	var parsed any
	if json.Unmarshal([]byte(body), &parsed) != nil {
		return false
	}
	return geminiBillingContainsImage(parsed)
}

func geminiBillingContainsImage(value any) bool {
	switch typed := value.(type) {
	case map[string]any:
		if _, ok := typed["inlineData"]; ok {
			return true
		}
		if _, ok := typed["inline_data"]; ok {
			return true
		}
		if data, ok := typed["b64_json"].(string); ok && data != "" {
			return true
		}
		if data, ok := typed["url"].(string); ok && data != "" {
			return true
		}
		for _, child := range typed {
			if geminiBillingContainsImage(child) {
				return true
			}
		}
	case []any:
		for _, child := range typed {
			if geminiBillingContainsImage(child) {
				return true
			}
		}
	}
	return false
}

func inferLocalRelayBaseURL(c *gin.Context) string {
	port := os.Getenv("PORT")
	if port == "" {
		port = "3000"
	}
	return "http://127.0.0.1:" + port
}

func dedupeStrings(items []string) []string {
	seen := make(map[string]bool)
	out := make([]string, 0, len(items))
	for _, item := range items {
		if item == "" || seen[item] {
			continue
		}
		seen[item] = true
		out = append(out, item)
	}
	return out
}

func geminiBillingIntField(other map[string]any, keys ...string) int {
	for _, key := range keys {
		if value, ok := other[key]; ok {
			switch typed := value.(type) {
			case float64:
				return int(typed)
			case int:
				return typed
			case int64:
				return int(typed)
			case json.Number:
				i, _ := typed.Int64()
				return int(i)
			}
		}
	}
	return 0
}

func geminiBillingBoolField(other map[string]any, key string) bool {
	value, ok := other[key]
	if !ok {
		return false
	}
	switch typed := value.(type) {
	case bool:
		return typed
	case string:
		return strings.EqualFold(typed, "true")
	default:
		return false
	}
}

func geminiBillingStringField(other map[string]any, key string) string {
	if value, ok := other[key].(string); ok {
		return value
	}
	return ""
}

func geminiBillingRequiredFloat(other map[string]any, key string) (float64, bool) {
	value, ok := other[key]
	if !ok {
		return 0, false
	}
	return geminiBillingToFloat(value), true
}

func geminiBillingFloatFieldDefault(other map[string]any, key string, fallback float64) float64 {
	if value, ok := other[key]; ok {
		return geminiBillingToFloat(value)
	}
	return fallback
}

func geminiBillingToFloat(value any) float64 {
	switch typed := value.(type) {
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
		d, err := decimal.NewFromString(typed)
		if err == nil {
			return d.InexactFloat64()
		}
	}
	return 0
}
