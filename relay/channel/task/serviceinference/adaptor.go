package serviceinference

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"strconv"
	"strings"

	"github.com/QuantumNous/new-api/constant"
	"github.com/QuantumNous/new-api/dto"
	"github.com/QuantumNous/new-api/model"
	"github.com/QuantumNous/new-api/relay/channel"
	relaycommon "github.com/QuantumNous/new-api/relay/common"
	"github.com/QuantumNous/new-api/service"

	"github.com/gin-gonic/gin"
	"github.com/pkg/errors"
)

type mediaURL struct {
	URL string `json:"url"`
}

type contentItem struct {
	Type     string    `json:"type"`
	Text     string    `json:"text,omitempty"`
	ImageURL *mediaURL `json:"image_url,omitempty"`
	VideoURL *mediaURL `json:"video_url,omitempty"`
	AudioURL *mediaURL `json:"audio_url,omitempty"`
	Role     string    `json:"role,omitempty"`
}

type requestPayload struct {
	Model         string        `json:"model"`
	Content       []contentItem `json:"content,omitempty"`
	Duration      *int          `json:"duration,omitempty"`
	Resolution    string        `json:"resolution,omitempty"`
	Ratio         string        `json:"ratio,omitempty"`
	GenerateAudio *bool         `json:"generate_audio,omitempty"`
	Watermark     *bool         `json:"watermark,omitempty"`
}

type taskResponse struct {
	Task serviceInferenceTask `json:"task"`
}

type serviceInferenceTask struct {
	ID              string          `json:"id"`
	Status          string          `json:"status"`
	Model           string          `json:"model"`
	DurationSeconds float64         `json:"duration_seconds"`
	Outputs         []string        `json:"outputs"`
	Error           json.RawMessage `json:"error"`
	CreatedAt       string          `json:"created_at"`
	CompletedAt     string          `json:"completed_at"`
	Usage           struct {
		CompletionTokens int `json:"completion_tokens"`
		TotalTokens      int `json:"total_tokens"`
	} `json:"usage"`
}

type TaskAdaptor struct {
	ChannelType int
	apiKey      string
	baseURL     string
}

const localBillingKey = "_newapi_service_inference_billing"

type billingMetadata struct {
	Model                      string  `json:"model"`
	Resolution                 string  `json:"resolution"`
	HasReference               bool    `json:"has_reference"`
	PriceTier                  string  `json:"price_tier"`
	SelectedPriceUSDPerMillion float64 `json:"selected_price_usd_per_million"`
	BasePriceUSDPerMillion     float64 `json:"base_price_usd_per_million"`
	EstimatedTokens            int     `json:"estimated_tokens,omitempty"`
}

func (a *TaskAdaptor) Init(info *relaycommon.RelayInfo) {
	a.ChannelType = info.ChannelType
	a.baseURL = strings.TrimRight(info.ChannelBaseUrl, "/")
	a.apiKey = info.ApiKey
}

func (a *TaskAdaptor) GetPriceScale(c *gin.Context, info *relaycommon.RelayInfo) (float32, error) {
	req, err := taskSubmitReqFromContext(c)
	if err != nil {
		return 0, err
	}
	meta, err := buildBillingMetadata(&req, info)
	if err != nil {
		return 0, err
	}
	meta.EstimatedTokens = estimateTokens(&req, meta.Resolution)
	return float32(float64(meta.EstimatedTokens) / 1_000_000 * meta.priceRatio()), nil
}

func (a *TaskAdaptor) GetUnitPriceScale(c *gin.Context, info *relaycommon.RelayInfo) (float32, error) {
	req, err := taskSubmitReqFromContext(c)
	if err != nil {
		return float32(1.0 / 1_000_000), nil
	}
	meta, err := buildBillingMetadata(&req, info)
	if err != nil {
		return float32(1.0 / 1_000_000), nil
	}
	return float32(meta.priceRatio() / 1_000_000), nil
}

func (a *TaskAdaptor) ValidateRequestAndSetAction(c *gin.Context, info *relaycommon.RelayInfo) (taskErr *dto.TaskError) {
	return relaycommon.ValidateBasicTaskRequest(c, info, constant.TaskActionGenerate)
}

func (a *TaskAdaptor) BuildRequestURL(info *relaycommon.RelayInfo) (string, error) {
	return fmt.Sprintf("%s/v1/video/generate", a.baseURL), nil
}

func (a *TaskAdaptor) BuildRequestHeader(c *gin.Context, req *http.Request, info *relaycommon.RelayInfo) error {
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Authorization", "Bearer "+a.apiKey)
	return nil
}

func (a *TaskAdaptor) BuildRequestBody(c *gin.Context, info *relaycommon.RelayInfo) (io.Reader, error) {
	v, exists := c.Get("task_request")
	if !exists {
		return nil, fmt.Errorf("request not found in context")
	}
	req := v.(relaycommon.TaskSubmitReq)

	body, err := convertToRequestPayload(&req, info)
	if err != nil {
		return nil, errors.Wrap(err, "convert request payload failed")
	}
	data, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}
	return bytes.NewReader(data), nil
}

func (a *TaskAdaptor) DoRequest(c *gin.Context, info *relaycommon.RelayInfo, requestBody io.Reader) (*http.Response, error) {
	return channel.DoTaskApiRequest(a, c, info, requestBody)
}

func (a *TaskAdaptor) DoResponse(c *gin.Context, resp *http.Response, info *relaycommon.RelayInfo) (taskID string, taskData []byte, taskErr *dto.TaskError) {
	responseBody, err := io.ReadAll(resp.Body)
	if err != nil {
		taskErr = service.TaskErrorWrapper(err, "read_response_body_failed", http.StatusInternalServerError)
		return
	}
	_ = resp.Body.Close()

	var taskResp taskResponse
	if err := json.Unmarshal(responseBody, &taskResp); err != nil {
		taskErr = service.TaskErrorWrapper(errors.Wrapf(err, "body: %s", responseBody), "unmarshal_response_body_failed", http.StatusInternalServerError)
		return
	}
	if taskResp.Task.ID == "" {
		taskErr = service.TaskErrorWrapper(fmt.Errorf("task_id is empty"), "invalid_response", http.StatusInternalServerError)
		return
	}

	taskData = responseBody
	if req, err := taskSubmitReqFromContext(c); err == nil {
		if meta, err := buildBillingMetadata(&req, info); err == nil {
			meta.EstimatedTokens = estimateTokens(&req, meta.Resolution)
			if data, err := withLocalBillingMetadata(responseBody, meta); err == nil {
				taskData = data
			}
		}
	}

	c.JSON(http.StatusOK, gin.H{
		"task_id": taskResp.Task.ID,
		"status":  taskResp.Task.Status,
	})
	return taskResp.Task.ID, taskData, nil
}

func (a *TaskAdaptor) FetchTask(baseUrl, key string, body map[string]any) (*http.Response, error) {
	taskID, ok := body["task_id"].(string)
	if !ok || taskID == "" {
		return nil, fmt.Errorf("invalid task_id")
	}

	uri := fmt.Sprintf("%s/v1/video/tasks/%s", strings.TrimRight(baseUrl, "/"), taskID)
	req, err := http.NewRequest(http.MethodGet, uri, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+key)
	return service.GetHttpClient().Do(req)
}

func (a *TaskAdaptor) GetModelList() []string {
	return ModelList
}

func (a *TaskAdaptor) GetChannelName() string {
	return ChannelName
}

func (a *TaskAdaptor) ParseTaskResult(respBody []byte) (*relaycommon.TaskInfo, error) {
	var taskResp taskResponse
	if err := json.Unmarshal(respBody, &taskResp); err != nil {
		return nil, errors.Wrap(err, "unmarshal task result failed")
	}

	resTask := taskResp.Task
	taskResult := relaycommon.TaskInfo{
		Code:             0,
		TaskID:           resTask.ID,
		CompletionTokens: resTask.Usage.CompletionTokens,
		TotalTokens:      resTask.Usage.TotalTokens,
		Duration:         resTask.DurationSeconds,
	}

	switch resTask.Status {
	case "pending", "queued", "submitted":
		taskResult.Status = model.TaskStatusQueued
		taskResult.Progress = "20%"
	case "processing", "running", "in_progress":
		taskResult.Status = model.TaskStatusInProgress
		taskResult.Progress = "50%"
	case "completed", "succeeded", "success":
		taskResult.Status = model.TaskStatusSuccess
		taskResult.Progress = "100%"
		if len(resTask.Outputs) > 0 {
			taskResult.Url = resTask.Outputs[0]
		}
	case "failed", "failure", "cancelled", "canceled":
		taskResult.Status = model.TaskStatusFailure
		taskResult.Progress = "100%"
		taskResult.Reason = parseTaskError(resTask.Error)
		if taskResult.Reason == "" {
			taskResult.Reason = "task failed"
		}
	default:
		if reason := parseTaskError(resTask.Error); reason != "" {
			taskResult.Status = model.TaskStatusFailure
			taskResult.Progress = "100%"
			taskResult.Reason = reason
			break
		}
		taskResult.Status = model.TaskStatusInProgress
		taskResult.Progress = "30%"
		taskResult.Reason = fmt.Sprintf("unknown status: %s", resTask.Status)
	}

	return &taskResult, nil
}

func convertToRequestPayload(req *relaycommon.TaskSubmitReq, info *relaycommon.RelayInfo) (*requestPayload, error) {
	r := requestPayload{}
	if req.Metadata != nil {
		metadata := cloneMetadataWithoutModel(req.Metadata)
		metadataBytes, err := json.Marshal(metadata)
		if err != nil {
			return nil, fmt.Errorf("marshal metadata failed: %w", err)
		}
		if err := json.Unmarshal(metadataBytes, &r); err != nil {
			return nil, fmt.Errorf("unmarshal metadata failed: %w", err)
		}
		r.Content = filterTextContent(r.Content)
	}

	r.Model = upstreamModelName(req, info)

	if req.HasImage() {
		for _, imgURL := range req.Images {
			if strings.TrimSpace(imgURL) == "" {
				continue
			}
			r.Content = append(r.Content, contentItem{
				Type:     "image_url",
				ImageURL: &mediaURL{URL: imgURL},
				Role:     "reference_image",
			})
		}
	}

	if strings.TrimSpace(req.Prompt) != "" {
		r.Content = append(r.Content, contentItem{
			Type: "text",
			Text: req.Prompt,
		})
	}

	if req.Duration > 0 {
		r.Duration = intPtr(req.Duration)
	}
	if req.Seconds != "" {
		if seconds, err := strconv.Atoi(req.Seconds); err == nil && seconds > 0 {
			r.Duration = intPtr(seconds)
		}
	}
	if r.Resolution == "" && req.Size != "" {
		r.Resolution = req.Size
	}

	return &r, nil
}

func taskSubmitReqFromContext(c *gin.Context) (relaycommon.TaskSubmitReq, error) {
	v, exists := c.Get("task_request")
	if !exists {
		return relaycommon.TaskSubmitReq{}, fmt.Errorf("request not found in context")
	}
	req, ok := v.(relaycommon.TaskSubmitReq)
	if !ok {
		return relaycommon.TaskSubmitReq{}, fmt.Errorf("invalid task request type")
	}
	return req, nil
}

func buildBillingMetadata(req *relaycommon.TaskSubmitReq, info *relaycommon.RelayInfo) (billingMetadata, error) {
	if meta, ok := billingMetadataFromMap(req.Metadata); ok {
		return meta, nil
	}

	payload, err := convertToRequestPayload(req, info)
	if err != nil {
		return billingMetadata{}, err
	}
	modelName := upstreamModelName(req, info)
	if modelName == "" {
		modelName = req.Model
	}
	resolution := normalizeResolution(payload.Resolution)
	hasReference := hasReferenceContent(payload.Content)
	selectedPrice, ok := priceUSDPerMillion(modelName, resolution, hasReference)
	if !ok {
		return billingMetadata{}, fmt.Errorf("service-inference price not configured: model=%s resolution=%s has_reference=%t", modelName, resolution, hasReference)
	}
	basePrice := basePriceUSDPerMillion(modelName)
	return billingMetadata{
		Model:                      modelName,
		Resolution:                 resolution,
		HasReference:               hasReference,
		PriceTier:                  priceTier(resolution, hasReference),
		SelectedPriceUSDPerMillion: selectedPrice,
		BasePriceUSDPerMillion:     basePrice,
	}, nil
}

func (m billingMetadata) priceRatio() float64 {
	if m.BasePriceUSDPerMillion <= 0 {
		return 1
	}
	return m.SelectedPriceUSDPerMillion / m.BasePriceUSDPerMillion
}

func billingMetadataFromMap(m map[string]interface{}) (billingMetadata, bool) {
	if m == nil {
		return billingMetadata{}, false
	}
	raw, ok := m[localBillingKey]
	if !ok {
		return billingMetadata{}, false
	}
	data, err := json.Marshal(raw)
	if err != nil {
		return billingMetadata{}, false
	}
	var meta billingMetadata
	if err := json.Unmarshal(data, &meta); err != nil {
		return billingMetadata{}, false
	}
	if meta.Resolution == "" || meta.SelectedPriceUSDPerMillion <= 0 || meta.BasePriceUSDPerMillion <= 0 {
		return billingMetadata{}, false
	}
	return meta, true
}

func withLocalBillingMetadata(body []byte, meta billingMetadata) ([]byte, error) {
	var m map[string]interface{}
	if err := json.Unmarshal(body, &m); err != nil {
		return nil, err
	}
	m[localBillingKey] = meta
	return json.Marshal(m)
}

func normalizeResolution(resolution string) string {
	resolution = strings.ToLower(strings.TrimSpace(resolution))
	switch {
	case strings.Contains(resolution, "1080"):
		return "1080p"
	case strings.Contains(resolution, "720"):
		return "720p"
	case strings.Contains(resolution, "480"):
		return "480p"
	default:
		return "720p"
	}
}

func hasReferenceContent(content []contentItem) bool {
	for _, item := range content {
		if item.Type == "text" {
			continue
		}
		if isAssetReference(item.ImageURL) || isAssetReference(item.AudioURL) || isAssetReference(item.VideoURL) {
			return true
		}
	}
	return false
}

func isAssetReference(ref *mediaURL) bool {
	if ref == nil {
		return false
	}
	return strings.HasPrefix(strings.ToLower(strings.TrimSpace(ref.URL)), "asset://")
}

func priceTier(resolution string, hasReference bool) string {
	ref := "no_ref"
	if hasReference {
		ref = "with_ref"
	}
	return resolution + "_" + ref
}

func basePriceUSDPerMillion(model string) float64 {
	if strings.Contains(model, "fast") {
		return 5.60
	}
	return 7.00
}

func priceUSDPerMillion(model string, resolution string, hasReference bool) (float64, bool) {
	fast := strings.Contains(model, "fast")
	switch resolution {
	case "480p", "720p":
		if fast {
			if hasReference {
				return 3.30, true
			}
			return 5.60, true
		}
		if hasReference {
			return 4.30, true
		}
		return 7.00, true
	case "1080p":
		if fast {
			return 0, false
		}
		if hasReference {
			return 4.70, true
		}
		return 7.70, true
	default:
		return 0, false
	}
}

func estimateTokens(req *relaycommon.TaskSubmitReq, resolution string) int {
	duration := requestDurationSeconds(req)
	tokensPerSecond := 12000.0
	if resolution == "1080p" {
		tokensPerSecond = 18000.0
	}
	return int(math.Ceil(duration * tokensPerSecond))
}

func requestDurationSeconds(req *relaycommon.TaskSubmitReq) float64 {
	if req == nil {
		return 4
	}
	if req.Duration > 0 {
		return float64(req.Duration)
	}
	if req.Seconds != "" {
		if seconds, err := strconv.Atoi(req.Seconds); err == nil && seconds > 0 {
			return float64(seconds)
		}
	}
	if req.Metadata != nil {
		if duration, ok := numericMetadata(req.Metadata["duration"]); ok && duration > 0 {
			return duration
		}
	}
	return 4
}

func numericMetadata(v interface{}) (float64, bool) {
	switch value := v.(type) {
	case json.Number:
		f, err := value.Float64()
		return f, err == nil
	case float64:
		return value, true
	case float32:
		return float64(value), true
	case int:
		return float64(value), true
	case int64:
		return float64(value), true
	case string:
		f, err := strconv.ParseFloat(value, 64)
		return f, err == nil
	default:
		return 0, false
	}
}

func upstreamModelName(req *relaycommon.TaskSubmitReq, info *relaycommon.RelayInfo) string {
	if info != nil && info.ChannelMeta != nil && info.UpstreamModelName != "" {
		return info.UpstreamModelName
	}
	return req.Model
}

func cloneMetadataWithoutModel(metadata map[string]interface{}) map[string]interface{} {
	clone := make(map[string]interface{}, len(metadata))
	for k, v := range metadata {
		if strings.EqualFold(k, "model") {
			continue
		}
		clone[k] = v
	}
	return clone
}

func filterTextContent(items []contentItem) []contentItem {
	if len(items) == 0 {
		return items
	}
	filtered := make([]contentItem, 0, len(items))
	for _, item := range items {
		if item.Type == "text" {
			continue
		}
		filtered = append(filtered, item)
	}
	return filtered
}

func parseTaskError(raw json.RawMessage) string {
	if len(raw) == 0 || string(raw) == "null" {
		return ""
	}
	var msg string
	if err := json.Unmarshal(raw, &msg); err == nil {
		return msg
	}
	var obj struct {
		Message string `json:"message"`
		Code    string `json:"code"`
	}
	if err := json.Unmarshal(raw, &obj); err == nil {
		if obj.Message != "" {
			return obj.Message
		}
		if obj.Code != "" {
			return obj.Code
		}
	}
	return string(raw)
}

func intPtr(v int) *int {
	return &v
}
