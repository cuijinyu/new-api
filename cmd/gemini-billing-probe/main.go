package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/glebarez/sqlite"
	"github.com/shopspring/decimal"
	"gorm.io/driver/mysql"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

const (
	requestIDHeader = "X-Oneapi-Request-Id"
	logTypeConsume  = 2
	quotaPerUnit    = 500000
)

const latestImageModels = "gemini-2.5-flash-image,gemini-2.5-flash-image-preview,gemini-3.1-flash-image,gemini-3.1-flash-image-preview,gemini-3-pro-image,gemini-3-pro-image-preview,nano-banana,nano-banana-pro"

var tinyPNGBase64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="

type config struct {
	BaseURL      string
	APIKey       string
	SQLDSN       string
	DBType       string
	Models       []string
	Cases        []string
	Prompt       string
	Timeout      time.Duration
	LogWait      time.Duration
	JSONOutput   bool
	AllowFailure bool
}

type consumeLog struct {
	ID               int
	CreatedAt        int64
	ModelName        string
	Quota            int
	PromptTokens     int
	CompletionTokens int
	IsStream         bool
	ChannelID        int `gorm:"column:channel_id"`
	RequestID        string
	Other            string
}

type checkResult struct {
	Name             string                 `json:"name"`
	Model            string                 `json:"model"`
	Case             string                 `json:"case"`
	HTTPStatus       int                    `json:"http_status"`
	RequestID        string                 `json:"request_id,omitempty"`
	HasImage         bool                   `json:"has_image"`
	LogID            int                    `json:"log_id,omitempty"`
	ChannelID        int                    `json:"channel_id,omitempty"`
	Quota            int                    `json:"quota,omitempty"`
	ExpectedQuota    *int                   `json:"expected_quota,omitempty"`
	Delta            *int                   `json:"delta,omitempty"`
	PromptTokens     int                    `json:"prompt_tokens,omitempty"`
	CompletionTokens int                    `json:"completion_tokens,omitempty"`
	ImageTokens      int                    `json:"image_tokens,omitempty"`
	TokenSource      string                 `json:"token_source,omitempty"`
	Status           string                 `json:"status"`
	Message          string                 `json:"message,omitempty"`
	Other            map[string]interface{} `json:"other,omitempty"`
}

func main() {
	cfg := parseFlags()
	if err := run(cfg); err != nil {
		fmt.Fprintf(os.Stderr, "gemini-billing-probe failed: %v\n", err)
		os.Exit(1)
	}
}

func parseFlags() config {
	var modelList, caseList string
	cfg := config{}
	flag.StringVar(&cfg.BaseURL, "base-url", envOr("NEW_API_BASE_URL", "http://localhost:3000"), "new-api base URL")
	flag.StringVar(&cfg.APIKey, "api-key", envOr("NEW_API_API_KEY", envOr("EZMODEL_API_KEY", "")), "API key used to call new-api")
	flag.StringVar(&cfg.SQLDSN, "sql-dsn", envOr("LOG_SQL_DSN", envOr("SQL_DSN", "")), "database DSN used to read consume logs")
	flag.StringVar(&cfg.DBType, "db-type", envOr("DB_TYPE", "auto"), "database type: auto, mysql, postgres, sqlite")
	flag.StringVar(&modelList, "models", envOr("GEMINI_BILLING_MODELS", "gemini-2.5-flash-image"), "comma-separated models, or 'latest-image'")
	flag.StringVar(&caseList, "cases", envOr("GEMINI_BILLING_CASES", "native"), "comma-separated cases: native,native-stream,native-edit,openai-image")
	flag.StringVar(&cfg.Prompt, "prompt", "Generate one simple original image of a small ceramic teapot on a white table, studio lighting.", "prompt used for image generation")
	timeoutSeconds := flag.Int("timeout", 300, "HTTP timeout in seconds")
	logWaitSeconds := flag.Int("log-wait", 15, "seconds to wait for consume log")
	flag.BoolVar(&cfg.JSONOutput, "json", false, "print JSON result")
	flag.BoolVar(&cfg.AllowFailure, "allow-failure", false, "exit 0 even if a probe fails")
	flag.Parse()

	cfg.Timeout = time.Duration(*timeoutSeconds) * time.Second
	cfg.LogWait = time.Duration(*logWaitSeconds) * time.Second
	if strings.EqualFold(strings.TrimSpace(modelList), "latest-image") {
		modelList = latestImageModels
	}
	cfg.Models = splitCSV(modelList)
	cfg.Cases = splitCSV(caseList)
	return cfg
}

func run(cfg config) error {
	if cfg.APIKey == "" {
		return errors.New("--api-key or NEW_API_API_KEY is required")
	}
	if cfg.SQLDSN == "" {
		return errors.New("--sql-dsn, LOG_SQL_DSN, or SQL_DSN is required")
	}
	if len(cfg.Models) == 0 || len(cfg.Cases) == 0 {
		return errors.New("at least one model and one case are required")
	}

	db, err := openDB(cfg.DBType, cfg.SQLDSN)
	if err != nil {
		return err
	}

	client := &http.Client{Timeout: cfg.Timeout}
	var results []checkResult
	for _, model := range cfg.Models {
		for _, probeCase := range cfg.Cases {
			result := runOne(cfg, client, db, model, probeCase)
			results = append(results, result)
			if !cfg.JSONOutput {
				printResult(result)
			}
		}
	}

	if cfg.JSONOutput {
		out, _ := json.MarshalIndent(results, "", "  ")
		fmt.Println(string(out))
	}
	if !cfg.AllowFailure {
		for _, result := range results {
			if result.Status != "pass" {
				return fmt.Errorf("%s/%s failed: %s", result.Model, result.Case, result.Message)
			}
		}
	}
	return nil
}

func runOne(cfg config, client *http.Client, db *gorm.DB, modelName, probeCase string) checkResult {
	name := modelName + "/" + probeCase
	result := checkResult{Name: name, Model: modelName, Case: probeCase, Status: "fail"}

	respBody, requestID, statusCode, err := callProbe(client, cfg, modelName, probeCase)
	result.HTTPStatus = statusCode
	result.RequestID = requestID
	if err != nil {
		result.Message = err.Error()
		return result
	}
	result.HasImage = responseHasImage(respBody, probeCase)
	if statusCode < 200 || statusCode >= 300 {
		result.Message = truncate(respBody, 500)
		return result
	}
	if requestID == "" {
		result.Message = "response missing X-Oneapi-Request-Id"
		return result
	}

	logRow, err := waitConsumeLog(db, requestID, cfg.LogWait)
	if err != nil {
		result.Message = err.Error()
		return result
	}
	result.LogID = logRow.ID
	result.ChannelID = logRow.ChannelID
	result.Quota = logRow.Quota
	result.PromptTokens = logRow.PromptTokens
	result.CompletionTokens = logRow.CompletionTokens

	other, err := parseOther(logRow.Other)
	if err != nil {
		result.Message = "invalid log other JSON: " + err.Error()
		return result
	}
	result.Other = other
	result.ImageTokens = intField(other, "output_image_tokens", "image_completion_tokens")
	result.TokenSource = stringField(other, "gemini_image_output_token_source")

	expected, err := calculateExpectedQuota(*logRow, other)
	if err != nil {
		result.Message = "cannot calculate expected quota: " + err.Error()
		return result
	}
	expectedInt := expected
	delta := logRow.Quota - expected
	result.ExpectedQuota = &expectedInt
	result.Delta = &delta

	if delta != 0 {
		result.Message = fmt.Sprintf("quota mismatch: actual=%d expected=%d delta=%d", logRow.Quota, expected, delta)
		return result
	}
	if strings.Contains(probeCase, "image") || strings.Contains(probeCase, "native") {
		if !result.HasImage && result.ImageTokens > 0 {
			result.Status = "warn"
			result.Message = "log has image tokens but response does not contain inline image"
			return result
		}
		if result.HasImage && result.ImageTokens == 0 {
			result.Message = "response contains image but log has no output image tokens"
			return result
		}
	}

	result.Status = "pass"
	result.Message = "quota matches consume log"
	return result
}

func callProbe(client *http.Client, cfg config, modelName, probeCase string) (body, requestID string, statusCode int, err error) {
	var endpoint string
	var payload []byte

	switch probeCase {
	case "native":
		endpoint = fmt.Sprintf("%s/v1beta/models/%s:generateContent", trimSlash(cfg.BaseURL), url.PathEscape(modelName))
		payload, _ = json.Marshal(nativePayload(cfg.Prompt, false))
	case "native-stream":
		endpoint = fmt.Sprintf("%s/v1beta/models/%s:streamGenerateContent?alt=sse", trimSlash(cfg.BaseURL), url.PathEscape(modelName))
		payload, _ = json.Marshal(nativePayload(cfg.Prompt, false))
	case "native-edit":
		endpoint = fmt.Sprintf("%s/v1beta/models/%s:generateContent", trimSlash(cfg.BaseURL), url.PathEscape(modelName))
		payload, _ = json.Marshal(nativePayload(cfg.Prompt+" Use the provided tiny input image only as a color reference.", true))
	case "openai-image":
		endpoint = trimSlash(cfg.BaseURL) + "/v1/images/generations"
		payload, _ = json.Marshal(map[string]interface{}{
			"model":           modelName,
			"prompt":          cfg.Prompt,
			"n":               1,
			"response_format": "b64_json",
		})
	default:
		return "", "", 0, fmt.Errorf("unknown case %q", probeCase)
	}

	req, err := http.NewRequest(http.MethodPost, endpoint, bytes.NewReader(payload))
	if err != nil {
		return "", "", 0, err
	}
	req.Header.Set("Authorization", "Bearer "+cfg.APIKey)
	req.Header.Set("Content-Type", "application/json")
	resp, err := client.Do(req)
	if err != nil {
		return "", "", 0, err
	}
	defer resp.Body.Close()
	raw, readErr := io.ReadAll(resp.Body)
	if readErr != nil {
		return "", resp.Header.Get(requestIDHeader), resp.StatusCode, readErr
	}
	return string(raw), resp.Header.Get(requestIDHeader), resp.StatusCode, nil
}

func nativePayload(prompt string, withImage bool) map[string]interface{} {
	parts := []map[string]interface{}{{"text": prompt}}
	if withImage {
		parts = append(parts, map[string]interface{}{
			"inlineData": map[string]interface{}{
				"mimeType": "image/png",
				"data":     tinyPNGBase64,
			},
		})
	}
	return map[string]interface{}{
		"contents": []map[string]interface{}{
			{"parts": parts},
		},
		"generationConfig": map[string]interface{}{
			"responseModalities": []string{"TEXT", "IMAGE"},
			"imageConfig": map[string]interface{}{
				"aspectRatio": "1:1",
				"imageSize":   "1K",
			},
		},
	}
}

func responseHasImage(body, probeCase string) bool {
	if probeCase == "native-stream" {
		return strings.Contains(body, `"inlineData"`) || strings.Contains(body, `"inline_data"`)
	}
	var parsed interface{}
	if json.Unmarshal([]byte(body), &parsed) != nil {
		return false
	}
	return containsImage(parsed)
}

func containsImage(v interface{}) bool {
	switch typed := v.(type) {
	case map[string]interface{}:
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
			if containsImage(child) {
				return true
			}
		}
	case []interface{}:
		for _, child := range typed {
			if containsImage(child) {
				return true
			}
		}
	}
	return false
}

func waitConsumeLog(db *gorm.DB, requestID string, wait time.Duration) (*consumeLog, error) {
	deadline := time.Now().Add(wait)
	var lastErr error
	for {
		var logRow consumeLog
		err := db.Table("logs").
			Where("request_id = ? AND type = ?", requestID, logTypeConsume).
			Order("id DESC").
			First(&logRow).Error
		if err == nil {
			return &logRow, nil
		}
		lastErr = err
		if time.Now().After(deadline) {
			return nil, fmt.Errorf("consume log not found for request_id=%s: %w", requestID, lastErr)
		}
		time.Sleep(500 * time.Millisecond)
	}
}

func parseOther(raw string) (map[string]interface{}, error) {
	if strings.TrimSpace(raw) == "" {
		return map[string]interface{}{}, nil
	}
	var other map[string]interface{}
	err := json.Unmarshal([]byte(raw), &other)
	return other, err
}

func calculateExpectedQuota(logRow consumeLog, other map[string]interface{}) (int, error) {
	if boolField(other, "tiered_pricing") {
		return 0, errors.New("tiered_pricing logs are not supported by this probe")
	}
	if boolField(other, "image_generation_call") || boolField(other, "web_search") || boolField(other, "file_search") {
		return 0, errors.New("tool-call fixed price logs are not supported by this probe")
	}

	modelRatio, ok := requiredFloat(other, "model_ratio")
	if !ok {
		return 0, errors.New("other.model_ratio is missing")
	}
	groupRatio := floatFieldDefault(other, "group_ratio", 1)
	completionRatio := floatFieldDefault(other, "completion_ratio", 1)
	cacheRatio := floatFieldDefault(other, "cache_ratio", 1)
	cacheCreationRatio := floatFieldDefault(other, "cache_creation_ratio", 1)
	imageRatio := floatFieldDefault(other, "image_ratio", 1)
	imageCompletionRatio := floatFieldDefault(other, "image_completion_ratio", 1)
	condMultiplier := floatFieldDefault(other, "billing_cond_multiplier", 1)

	promptTokens := decimal.NewFromInt(int64(logRow.PromptTokens))
	cacheTokens := decimal.NewFromInt(int64(intField(other, "cache_tokens")))
	cacheCreationTokens := decimal.NewFromInt(int64(intField(other, "cache_creation_tokens")))
	imageInputTokens := decimal.NewFromInt(int64(intField(other, "input_image_tokens", "image_output")))

	baseTokens := promptTokens.Sub(cacheTokens).Sub(cacheCreationTokens).Sub(imageInputTokens)
	if baseTokens.IsNegative() {
		baseTokens = decimal.Zero
	}

	promptQuota := baseTokens.
		Add(cacheTokens.Mul(decimal.NewFromFloat(cacheRatio))).
		Add(cacheCreationTokens.Mul(decimal.NewFromFloat(cacheCreationRatio))).
		Add(imageInputTokens.Mul(decimal.NewFromFloat(imageRatio)))

	completionTokens := decimal.NewFromInt(int64(logRow.CompletionTokens))
	imageOutputTokens := decimal.NewFromInt(int64(intField(other, "output_image_tokens", "image_completion_tokens")))
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

func openDB(dbType, dsn string) (*gorm.DB, error) {
	kind := strings.ToLower(strings.TrimSpace(dbType))
	if kind == "" || kind == "auto" {
		kind = inferDBType(dsn)
	}
	switch kind {
	case "postgres", "postgresql":
		return gorm.Open(postgres.New(postgres.Config{DSN: dsn, PreferSimpleProtocol: true}), &gorm.Config{})
	case "sqlite", "sqlite3":
		if dsn == "local" {
			dsn = "one-api.db"
		}
		return gorm.Open(sqlite.Open(dsn), &gorm.Config{})
	case "mysql":
		if !strings.Contains(dsn, "parseTime") {
			if strings.Contains(dsn, "?") {
				dsn += "&parseTime=true"
			} else {
				dsn += "?parseTime=true"
			}
		}
		return gorm.Open(mysql.Open(dsn), &gorm.Config{})
	default:
		return nil, fmt.Errorf("unsupported db type %q", dbType)
	}
}

func inferDBType(dsn string) string {
	lower := strings.ToLower(strings.TrimSpace(dsn))
	if strings.HasPrefix(lower, "postgres://") || strings.HasPrefix(lower, "postgresql://") {
		return "postgres"
	}
	if lower == "local" || strings.HasSuffix(lower, ".db") || strings.HasPrefix(lower, "file:") {
		return "sqlite"
	}
	return "mysql"
}

func printResult(result checkResult) {
	prefix := "[FAIL]"
	if result.Status == "pass" {
		prefix = "[PASS]"
	} else if result.Status == "warn" {
		prefix = "[WARN]"
	}
	expected := "-"
	delta := "-"
	if result.ExpectedQuota != nil {
		expected = fmt.Sprintf("%d", *result.ExpectedQuota)
	}
	if result.Delta != nil {
		delta = fmt.Sprintf("%+d", *result.Delta)
	}
	fmt.Printf("%s %-44s http=%d log=%d quota=%d expected=%s delta=%s image=%v image_tokens=%d source=%s\n",
		prefix, result.Name, result.HTTPStatus, result.LogID, result.Quota, expected, delta, result.HasImage, result.ImageTokens, result.TokenSource)
	if result.Message != "" {
		fmt.Printf("      %s\n", result.Message)
	}
}

func envOr(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}

func splitCSV(value string) []string {
	parts := strings.Split(value, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		if trimmed := strings.TrimSpace(part); trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return out
}

func trimSlash(value string) string {
	return strings.TrimRight(value, "/")
}

func truncate(value string, max int) string {
	if len(value) <= max {
		return value
	}
	return value[:max]
}

func intField(other map[string]interface{}, keys ...string) int {
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

func boolField(other map[string]interface{}, key string) bool {
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

func stringField(other map[string]interface{}, key string) string {
	if value, ok := other[key].(string); ok {
		return value
	}
	return ""
}

func requiredFloat(other map[string]interface{}, key string) (float64, bool) {
	value, ok := other[key]
	if !ok {
		return 0, false
	}
	return toFloat(value), true
}

func floatFieldDefault(other map[string]interface{}, key string, fallback float64) float64 {
	if value, ok := other[key]; ok {
		return toFloat(value)
	}
	return fallback
}

func toFloat(value interface{}) float64 {
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

func decodeTinyPNG() []byte {
	data, _ := base64.StdEncoding.DecodeString(tinyPNGBase64)
	return data
}
