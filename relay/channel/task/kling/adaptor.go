package kling

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/model"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/pkg/errors"

	"github.com/QuantumNous/new-api/constant"
	"github.com/QuantumNous/new-api/dto"
	"github.com/QuantumNous/new-api/relay/channel"
	relaycommon "github.com/QuantumNous/new-api/relay/common"
	"github.com/QuantumNous/new-api/service"
)

// ============================
// Request / Response structures
// ============================

type TrajectoryPoint struct {
	X int `json:"x"`
	Y int `json:"y"`
}

type DynamicMask struct {
	Mask         string            `json:"mask,omitempty"`
	Trajectories []TrajectoryPoint `json:"trajectories,omitempty"`
}

type CameraConfig struct {
	Horizontal float64 `json:"horizontal,omitempty"`
	Vertical   float64 `json:"vertical,omitempty"`
	Pan        float64 `json:"pan,omitempty"`
	Tilt       float64 `json:"tilt,omitempty"`
	Roll       float64 `json:"roll,omitempty"`
	Zoom       float64 `json:"zoom,omitempty"`
}

type CameraControl struct {
	Type   string        `json:"type,omitempty"`
	Config *CameraConfig `json:"config,omitempty"`
}

type VoiceItem struct {
	VoiceId string `json:"voice_id"`
}

type OmniImageItem struct {
	ImageUrl string `json:"image_url"`
	Type     string `json:"type,omitempty"` // first_frame, end_frame
}

type OmniVideoItem struct {
	VideoUrl          string `json:"video_url"`
	ReferType         string `json:"refer_type"`          // feature, base
	KeepOriginalSound string `json:"keep_original_sound"` // yes, no
}

type OmniElementItem struct {
	ElementId int64 `json:"element_id"`
}

type MultiImageItem struct {
	Image string `json:"image"`
}

// multiImageRequestPayload 多图参考生视频 API 专用请求结构
type multiImageRequestPayload struct {
	ModelName      string           `json:"model_name,omitempty"`
	ImageList      []MultiImageItem `json:"image_list"`
	Prompt         string           `json:"prompt"`
	NegativePrompt string           `json:"negative_prompt,omitempty"`
	Mode           string           `json:"mode,omitempty"`
	Duration       string           `json:"duration,omitempty"`
	AspectRatio    string           `json:"aspect_ratio,omitempty"`
	CallbackUrl    string           `json:"callback_url,omitempty"`
	ExternalTaskId string           `json:"external_task_id,omitempty"`
}

// motionControlRequestPayload Motion Control API 专用请求结构
type motionControlRequestPayload struct {
	Prompt               string `json:"prompt,omitempty"`                 // 文本提示词，可选，不超过2500字符
	ImageUrl             string `json:"image_url"`                        // 参考图像，必须
	VideoUrl             string `json:"video_url"`                        // 参考视频，必须
	KeepOriginalSound    string `json:"keep_original_sound,omitempty"`    // 是否保留视频原声，可选，默认yes，枚举值：yes/no
	CharacterOrientation string `json:"character_orientation"`            // 人物朝向，必须，枚举值：image/video
	Mode                 string `json:"mode"`                             // 生成模式，必须，枚举值：std/pro
	CallbackUrl          string `json:"callback_url,omitempty"`           // 回调地址，可选
	ExternalTaskId       string `json:"external_task_id,omitempty"`       // 自定义任务ID，可选
}

type requestPayload struct {
	// --- 公共字段 ---
	ModelName      string `json:"model_name,omitempty"`
	Model          string `json:"model,omitempty"` // 兼容性字段
	Prompt         string `json:"prompt,omitempty"`
	Mode           string `json:"mode,omitempty"` // std, pro
	Duration       string `json:"duration,omitempty"`
	AspectRatio    string `json:"aspect_ratio,omitempty"`
	CallbackUrl    string `json:"callback_url,omitempty"`
	ExternalTaskId string `json:"external_task_id,omitempty"`

	// --- List 2 (V1/V2) 专用字段 ---
	NegativePrompt string         `json:"negative_prompt,omitempty"`
	Image          string         `json:"image,omitempty"`      // 旧版首帧
	ImageTail      string         `json:"image_tail,omitempty"` // 旧版尾帧
	CfgScale       float64        `json:"cfg_scale,omitempty"`
	Sound          string         `json:"sound,omitempty"`
	CameraControl  *CameraControl `json:"camera_control,omitempty"`
	StaticMask     string         `json:"static_mask,omitempty"`
	DynamicMasks   []DynamicMask  `json:"dynamic_masks,omitempty"`
	VoiceList      []VoiceItem    `json:"voice_list,omitempty"`

	// --- List 1 (Omni) 新增字段 ---
	ImageList   []OmniImageItem   `json:"image_list,omitempty"`
	VideoList   []OmniVideoItem   `json:"video_list,omitempty"`
	ElementList []OmniElementItem `json:"element_list,omitempty"`
}

type responsePayload struct {
	Code      int    `json:"code"`
	Message   string `json:"message"`
	TaskId    string `json:"task_id"`
	RequestId string `json:"request_id"`
	Data      struct {
		TaskId        string `json:"task_id"`
		TaskStatus    string `json:"task_status"`
		TaskStatusMsg string `json:"task_status_msg"`
		TaskResult    struct {
			Videos []struct {
				Id       string `json:"id"`
				Url      string `json:"url"`
				Duration string `json:"duration"`
			} `json:"videos"`
		} `json:"task_result"`
		CreatedAt int64 `json:"created_at"`
		UpdatedAt int64 `json:"updated_at"`
	} `json:"data"`
}

// ============================
// Adaptor implementation
// ============================

type TaskAdaptor struct {
	ChannelType int
	apiKey      string
	baseURL     string
}

func (a *TaskAdaptor) Init(info *relaycommon.RelayInfo) {
	a.ChannelType = info.ChannelType
	a.baseURL = info.ChannelBaseUrl
	a.apiKey = info.ApiKey

	// apiKey format: "access_key|secret_key"
}

// withVideoInputScaleMap 带视频输入的价格倍率（可叠加在 Std 或 Pro 上）
var withVideoInputScaleMap = map[string]float64{
	"kling-video-o1": 0.126 / 0.084, // 1.5 - 相对于无视频输入的倍率
}

// proScaleMap Pro 模式相对于 Std 模式的价格倍率
var proScaleMap = map[string]float64{
	"kling-video-o1":   0.112 / 0.084, // 1.333 - Pro/Std 倍率
	"kling-v2-6":       0.07 / 0.07,           // 普通任务 Pro 和 Std 价格相同
	"kling-v2-5-turbo": 0.07 / 0.042,  // 1.667
	"kling-v2-1":       0.098 / 0.056, // 1.75
	"kling-v1-6":       0.098 / 0.056, // 1.75
	"kling-v1-5":       0.098 / 0.056, // 1.75
	"kling-v1":         0.098 / 0.028, // 3.5
}

// masterScaleMap Master 模式相对于 Std 模式的价格倍率
var masterScaleMap = map[string]float64{
	"kling-v2-1-master": 1.0, // 1.0 - Master 模型没有 Std，以 Master 为基准
	"kling-v2-master":   1.0, // 1.0 - Master 模型没有 Std，以 Master 为基准
}

// stdSupportedModels 支持 Std 模式的模型列表
var stdSupportedModels = map[string]bool{
	"kling-video-o1":   true,
	"kling-v2-6":       true,
	"kling-v2-5-turbo": true,
	"kling-v2-1":       true,
	"kling-v1-6":       true,
	"kling-v1-5":       true,
	"kling-v1":         true,
}

var soundScaleMap = map[string]float64{
	"kling-v2-6": 2.0 / 1.0,
}

var voiceControlScaleMap = map[string]float64{
	"kling-v2-6": 1.2 / 1.0,
}

func isUseVoiceControl(req *requestPayload) bool {
	if len(req.VoiceList) == 0 {
		return false
	}

	// 检查 prompt 中是否包含完整的音色标记，如 <<<voice_1>>> 或 <<<voice_2>>>
	// 一次视频生成任务至多引用2个音色
	for i := 1; i <= len(req.VoiceList); i++ {
		voiceTag := fmt.Sprintf("<<<voice_%d>>>", i)
		if strings.Contains(req.Prompt, voiceTag) {
			return true
		}
	}
	return false
}

// validateIntegerDuration 验证 duration 是否为纯整数格式，并返回解析后的值
// 这个函数确保 duration 字符串格式正确（无小数点、无其他字符）
func validateIntegerDuration(duration string) (int, error) {
	var durationVal int
	if _, err := fmt.Sscanf(duration, "%d", &durationVal); err != nil {
		return 0, fmt.Errorf("invalid duration format: %s", duration)
	}
	// 验证解析后的值转回字符串是否与原始值一致，确保是纯整数
	checkDuration := fmt.Sprintf("%d", durationVal)
	if duration != checkDuration {
		return 0, fmt.Errorf("duration must be an integer, got: %s", duration)
	}
	return durationVal, nil
}

// calculateModeScale 计算模式倍率（std/pro/master）
func calculateModeScale(mode, model string) (float64, error) {
	switch mode {
	case "std", "":
		// Std 模式，基准倍率 1.0
		if _, ok := stdSupportedModels[model]; !ok {
			// 如果该模型不在 Std 支持列表中，检查是否在 Master 支持列表中
			if scale, ok := masterScaleMap[model]; ok {
				return scale, nil
			}
			return 1.0, fmt.Errorf("model %s does not support std mode", model)
		}
		return 1.0, nil
	case "pro":
		if scale, ok := proScaleMap[model]; ok {
			return scale, nil
		}
		return 1.0, fmt.Errorf("unsupported model for pro mode: %s", model)
	case "master":
		if scale, ok := masterScaleMap[model]; ok {
			return scale, nil
		}
		return 1.0, fmt.Errorf("unsupported model for master mode: %s", model)
	default:
		return 1.0, fmt.Errorf("unsupported mode: %s", mode)
	}
}

// calculateAdvanceScale 计算高级参数倍率（视频输入、音频、音色控制）
func calculateAdvanceScale(action string, req *requestPayload) float64 {
	scale := 1.0

	// 1. 视频输入倍率
	hasVideoInput := action == constant.TaskActionOmniVideo && len(req.VideoList) > 0
	if hasVideoInput {
		if videoScale, ok := withVideoInputScaleMap[req.Model]; ok {
			scale *= videoScale
		}
	}

	// 2. 音频倍率
	if req.Sound == "on" {
		if soundScale, ok := soundScaleMap[req.Model]; ok {
			scale *= soundScale

			// 3. 音色控制倍率（只在开启音频时生效）
			if isUseVoiceControl(req) {
				if voiceControlScale, ok := voiceControlScaleMap[req.Model]; ok {
					scale *= voiceControlScale
				}
			}
		}
	}

	return scale
}

// calculateOmniVideoDuration 计算 omni-video 端点的 duration
// 规则：
// 1. 文生、图生（不含首尾帧）：可选 5s/10s
// 2. 有视频输入且使用视频编辑功能（类型=base）：不可指定时长，跟视频对齐
// 3. 其他情况（不传视频+传图片+主体，或传视频+类型=feature）：可选 3-10s
func calculateOmniVideoDuration(req *requestPayload) (int, error) {
	hasVideo := len(req.VideoList) > 0
	hasImage := len(req.ImageList) > 0
	isVideoBase := false

	// 检查是否使用视频编辑功能（refer_type=base）
	for _, video := range req.VideoList {
		if video.ReferType == "base" {
			isVideoBase = true
			break
		}
	}

	// 规则 2: 有视频输入且使用视频编辑功能（类型=base）
	if hasVideo && isVideoBase {
		return 0, fmt.Errorf("video editing mode (refer_type=base) is not supported")
	}

	// 规则 1: 文生视频（无图片、无视频输入）
	if !hasVideo && !hasImage {
		if req.Duration != "5" && req.Duration != "10" {
			return 0, fmt.Errorf("text2video only supports duration 5 or 10, got: %s", req.Duration)
		}
		durationVal, err := validateIntegerDuration(req.Duration)
		if err != nil {
			return 0, err
		}
		return durationVal, nil
	}

	// 规则 1: 图生视频（有图片但无视频）
	if hasImage && !hasVideo {
		// 检查是否是首尾帧模式
		hasFirstOrEndFrame := false
		for _, img := range req.ImageList {
			if img.Type == "first_frame" || img.Type == "end_frame" {
				hasFirstOrEndFrame = true
				break
			}
		}

		if hasFirstOrEndFrame {
			// 规则 3: 首尾帧模式：可选 3-10s
			durationVal, err := validateIntegerDuration(req.Duration)
			if err != nil {
				return 0, err
			}
			if durationVal < 3 || durationVal > 10 {
				return 0, fmt.Errorf("first/end frame mode supports duration 3-10, got: %d", durationVal)
			}
			return durationVal, nil
		} else {
			// 规则 1: 普通图生视频：仅支持 5 和 10s
			if req.Duration != "5" && req.Duration != "10" {
				return 0, fmt.Errorf("image2video only supports duration 5 or 10, got: %s", req.Duration)
			}
			durationVal, err := validateIntegerDuration(req.Duration)
			if err != nil {
				return 0, err
			}
			return durationVal, nil
		}
	}

	// 规则 3: 其他情况（传视频+类型=feature，或混合输入）：可选 3-10s
	durationVal, err := validateIntegerDuration(req.Duration)
	if err != nil {
		return 0, err
	}
	if durationVal < 3 || durationVal > 10 {
		return 0, fmt.Errorf("duration must be between 3-10, got: %d", durationVal)
	}
	return durationVal, nil
}

// calculateLegacyVideoDuration 计算传统端点（text2video/image2video）的 duration
// 规则：仅支持 5s 和 10s
func calculateLegacyVideoDuration(req *requestPayload) (int, error) {
	if req.Duration == "" {
		return 5, nil
	}

	if req.Duration != "5" && req.Duration != "10" {
		return 0, fmt.Errorf("legacy endpoint only supports duration 5 or 10, got: %s", req.Duration)
	}

	durationVal, err := validateIntegerDuration(req.Duration)
	if err != nil {
		return 0, err
	}
	return durationVal, nil
}

// motionControlProScale Motion Control Pro 模式相对于 Std 模式的价格倍率
var motionControlProScale = 1.5 // Pro 模式价格是 Std 的 1.5 倍

// calculateUnitPriceScale 计算单价系数（Mode、声音、视频输入等系数的乘积）
func (a *TaskAdaptor) calculateUnitPriceScale(action string, req *relaycommon.TaskSubmitReq) (float64, error) {
	mode := defaultString(req.Mode, "std")

	// 1. 计算模式倍率 (std/pro/master)
	var modeScale float64 = 1.0
	var err error

	if action == constant.TaskActionMotionControl {
		// 动作控制专用倍率：Std = 1.0, Pro = 0.8/0.5 = 1.6
		if mode == "pro" {
			modeScale = 1.6
		} else {
			modeScale = 1.0
		}
	} else {
		// 普通任务沿用原有的模型倍率表
		modeScale, err = calculateModeScale(mode, req.Model)
		if err != nil {
			return 1.0, err
		}
	}

	// 2. 计算高级参数倍率 (音频、音色控制、视频输入等)
	klingReq, _ := a.convertToRequestPayload(req)
	advanceScale := calculateAdvanceScale(action, klingReq)

	return modeScale * advanceScale, nil
}

// GetUnitPriceScale 获取单位价格倍率（用于异步核销）
func (a *TaskAdaptor) GetUnitPriceScale(c *gin.Context, info *relaycommon.RelayInfo) (float32, error) {
	v, exists := c.Get("task_request")
	if !exists {
		return 1.0, fmt.Errorf("request not found in context")
	}
	req := v.(relaycommon.TaskSubmitReq)

	action := info.Action
	if ctxAction := c.GetString("action"); ctxAction != "" {
		action = ctxAction
	}

	scale, err := a.calculateUnitPriceScale(action, &req)
	if err != nil {
		return 1.0, err
	}
	return float32(scale), nil
}

// GetPriceScale 获取总价格倍率（用于预扣费阶段：预估时长 * 单价系数）
func (a *TaskAdaptor) GetPriceScale(c *gin.Context, info *relaycommon.RelayInfo) (float32, error) {
	v, exists := c.Get("task_request")
	if !exists {
		return 1.0, fmt.Errorf("request not found in context")
	}
	req := v.(relaycommon.TaskSubmitReq)

	action := info.Action
	if ctxAction := c.GetString("action"); ctxAction != "" {
		action = ctxAction
	}

	// 1. 获取单价系数
	unitScale, err := a.calculateUnitPriceScale(action, &req)
	if err != nil {
		return 1.0, err
	}

	// 2. 计算预估时长
	klingReq, _ := a.convertToRequestPayload(&req)
	var duration float64 = 1.0

	if action == constant.TaskActionMotionControl {
		// Motion Control 预扣最大时长：image 10s, video 30s
		duration = 10.0
		if req.Metadata != nil {
			orientation, _ := req.Metadata["character_orientation"].(string)
			if orientation == "video" {
				duration = 30.0
			}
		}
	} else if action == constant.TaskActionMultiImage2Video {
		multiImageReq, _ := a.convertToMultiImagePayload(&req)
		// 多图生视频仅支持 5s 和 10s
		if multiImageReq.Duration != "5" && multiImageReq.Duration != "10" {
			duration = 5.0 // 默认 5s
		} else {
			durationInt, _ := validateIntegerDuration(multiImageReq.Duration)
			duration = float64(durationInt)
		}
	} else {
		var durationInt int
		if action == constant.TaskActionOmniVideo {
			durationInt, err = calculateOmniVideoDuration(klingReq)
		} else {
			durationInt, err = calculateLegacyVideoDuration(klingReq)
		}
		if err != nil {
			return 1.0, err
		}
		duration = float64(durationInt)
	}

	return float32(duration * unitScale), nil
}

// ... 保持其他代码不变 ...


// ValidateRequestAndSetAction parses body, validates fields and sets default action.
func (a *TaskAdaptor) ValidateRequestAndSetAction(c *gin.Context, info *relaycommon.RelayInfo) (taskErr *dto.TaskError) {
	// Use the standard validation method for TaskSubmitReq
	return relaycommon.ValidateBasicTaskRequest(c, info, constant.TaskActionGenerate)
}

// BuildRequestURL constructs the upstream URL.
func (a *TaskAdaptor) BuildRequestURL(info *relaycommon.RelayInfo) (string, error) {
	var path string
	switch info.Action {
	case constant.TaskActionOmniVideo:
		path = "/v1/videos/omni-video"
	case constant.TaskActionMotionControl:
		path = "/v1/videos/motion-control"
	case constant.TaskActionMultiImage2Video:
		path = "/v1/videos/multi-image2video"
	case constant.TaskActionGenerate:
		path = "/v1/videos/image2video"
	default:
		path = "/v1/videos/text2video"
	}

	if isNewAPIRelay(info.ApiKey) {
		return fmt.Sprintf("%s/kling%s", a.baseURL, path), nil
	}

	return fmt.Sprintf("%s%s", a.baseURL, path), nil
}

// BuildRequestHeader sets required headers.
func (a *TaskAdaptor) BuildRequestHeader(c *gin.Context, req *http.Request, info *relaycommon.RelayInfo) error {
	token, err := a.createJWTToken()
	if err != nil {
		return fmt.Errorf("failed to create JWT token: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("User-Agent", "kling-sdk/1.0")
	return nil
}

// BuildRequestBody converts request into Kling specific format.
func (a *TaskAdaptor) BuildRequestBody(c *gin.Context, info *relaycommon.RelayInfo) (io.Reader, error) {
	v, exists := c.Get("task_request")
	if !exists {
		return nil, fmt.Errorf("request not found in context")
	}
	req := v.(relaycommon.TaskSubmitReq)

	currentAction := c.GetString("action")

	// Motion Control 使用专用的请求结构
	if currentAction == constant.TaskActionMotionControl {
		body, err := a.convertToMotionControlPayload(&req)
		if err != nil {
			return nil, err
		}
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		return bytes.NewReader(data), nil
	}

	// 多图参考生视频使用专用的请求结构
	if currentAction == constant.TaskActionMultiImage2Video {
		body, err := a.convertToMultiImagePayload(&req)
		if err != nil {
			return nil, err
		}
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		return bytes.NewReader(data), nil
	}

	body, err := a.convertToRequestPayload(&req)
	if err != nil {
		return nil, err
	}

	// 只有在非 Omni 端点时，才判断是否为文生视频
	if currentAction != constant.TaskActionOmniVideo {
		// 兼容旧版和新版字段，判断是否为文生视频
		// 只有在没有任何输入（图片、视频）时才是纯文生视频
		hasAnyInput := body.Image != "" || body.ImageTail != ""
		if !hasAnyInput {
			c.Set("action", constant.TaskActionTextGenerate)
		}
	}

	data, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}
	return bytes.NewReader(data), nil
}

// DoRequest delegates to common helper.
func (a *TaskAdaptor) DoRequest(c *gin.Context, info *relaycommon.RelayInfo, requestBody io.Reader) (*http.Response, error) {
	if action := c.GetString("action"); action != "" {
		info.Action = action
	}
	return channel.DoTaskApiRequest(a, c, info, requestBody)
}

// DoResponse handles upstream response, returns taskID etc.
func (a *TaskAdaptor) DoResponse(c *gin.Context, resp *http.Response, info *relaycommon.RelayInfo) (taskID string, taskData []byte, taskErr *dto.TaskError) {
	responseBody, err := io.ReadAll(resp.Body)
	if err != nil {
		taskErr = service.TaskErrorWrapper(err, "read_response_body_failed", http.StatusInternalServerError)
		return
	}

	var kResp responsePayload
	err = json.Unmarshal(responseBody, &kResp)
	if err != nil {
		taskErr = service.TaskErrorWrapper(err, "unmarshal_response_failed", http.StatusInternalServerError)
		return
	}
	if kResp.Code != 0 {
		taskErr = service.TaskErrorWrapperLocal(errors.New(kResp.Message), "task_failed", http.StatusBadRequest)
		return
	}
	ov := dto.NewOpenAIVideo()
	ov.ID = kResp.Data.TaskId
	ov.TaskID = kResp.Data.TaskId
	ov.CreatedAt = time.Now().Unix()
	ov.Model = info.OriginModelName
	c.JSON(http.StatusOK, ov)
	return kResp.Data.TaskId, responseBody, nil
}

// FetchTask fetch task status
func (a *TaskAdaptor) FetchTask(baseUrl, key string, body map[string]any) (*http.Response, error) {
	taskID, ok := body["task_id"].(string)
	if !ok {
		return nil, fmt.Errorf("invalid task_id")
	}
	action, ok := body["action"].(string)
	if !ok {
		return nil, fmt.Errorf("invalid action")
	}

	var path string
	switch action {
	case constant.TaskActionOmniVideo:
		path = "/v1/videos/omni-video"
	case constant.TaskActionMotionControl:
		path = "/v1/videos/motion-control"
	case constant.TaskActionMultiImage2Video:
		path = "/v1/videos/multi-image2video"
	case constant.TaskActionGenerate:
		path = "/v1/videos/image2video"
	default:
		path = "/v1/videos/text2video"
	}

	url := fmt.Sprintf("%s%s/%s", baseUrl, path, taskID)
	if isNewAPIRelay(key) {
		url = fmt.Sprintf("%s/kling%s/%s", baseUrl, path, taskID)
	}

	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}

	token, err := a.createJWTTokenWithKey(key)
	if err != nil {
		token = key
	}

	req.Header.Set("Accept", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("User-Agent", "kling-sdk/1.0")

	return service.GetHttpClient().Do(req)
}

func (a *TaskAdaptor) GetModelList() []string {
	return []string{
		"kling-video-o1",
		"kling-v2-6",
		"kling-v2-5-turbo",
		"kling-v2-1",
		"kling-v1-6",
		"kling-v1-5",
		"kling-v1",
		"kling-v2-1-master",
		"kling-v2-master",
	}
}

func (a *TaskAdaptor) GetChannelName() string {
	return "kling"
}

// ============================
// helpers
// ============================

func (a *TaskAdaptor) convertToRequestPayload(req *relaycommon.TaskSubmitReq) (*requestPayload, error) {
	mode := req.Mode
	if mode == "" || mode == "std" {
		// 如果是默认的 std 模式，但模型本身不支持 std，则置为空（json omitempty 会忽略此字段）
		if _, ok := stdSupportedModels[req.Model]; !ok {
			mode = ""
		}
	}

	r := requestPayload{
		Prompt:         req.Prompt,
		Image:          req.Image,
		Mode:           mode,
		Duration:       fmt.Sprintf("%d", defaultInt(req.Duration, 5)),
		AspectRatio:    a.getAspectRatio(req.Size),
		ModelName:      req.Model,
		Model:          req.Model, // Keep consistent with model_name, double writing improves compatibility
		CfgScale:       0.5,
		StaticMask:     "",
		DynamicMasks:   []DynamicMask{},
		CameraControl:  nil,
		CallbackUrl:    "",
		ExternalTaskId: "",
		Sound:          "off",
	}
	if r.ModelName == "" {
		r.ModelName = "kling-v1"
	}
	metadata := req.Metadata
	medaBytes, err := json.Marshal(metadata)
	if err != nil {
		return nil, errors.Wrap(err, "metadata marshal metadata failed")
	}
	err = json.Unmarshal(medaBytes, &r)
	if err != nil {
		return nil, errors.Wrap(err, "unmarshal metadata failed")
	}
	return &r, nil
}

// convertToMultiImagePayload 转换为多图参考生视频 API 专用请求格式
func (a *TaskAdaptor) convertToMultiImagePayload(req *relaycommon.TaskSubmitReq) (*multiImageRequestPayload, error) {
	r := multiImageRequestPayload{
		Prompt:      req.Prompt,
		Mode:        defaultString(req.Mode, "std"),
		Duration:    fmt.Sprintf("%d", defaultInt(req.Duration, 5)),
		AspectRatio: a.getAspectRatio(req.Size),
		ModelName:   req.Model,
	}

	if r.ModelName == "" {
		r.ModelName = "kling-v1-6"
	}

	// 从 metadata 中解析所有字段
	if req.Metadata != nil {
		metaBytes, err := json.Marshal(req.Metadata)
		if err != nil {
			return nil, errors.Wrap(err, "marshal metadata failed")
		}
		err = json.Unmarshal(metaBytes, &r)
		if err != nil {
			return nil, errors.Wrap(err, "unmarshal metadata failed")
		}
	}

	// 验证必填字段
	if len(r.ImageList) == 0 {
		return nil, fmt.Errorf("image_list is required for multi-image2video")
	}
	if len(r.ImageList) > 4 {
		return nil, fmt.Errorf("image_list supports up to 4 images, got: %d", len(r.ImageList))
	}
	if r.Prompt == "" {
		return nil, fmt.Errorf("prompt is required for multi-image2video")
	}

	return &r, nil
}

// convertToMotionControlPayload 转换为 Motion Control API 专用请求格式
func (a *TaskAdaptor) convertToMotionControlPayload(req *relaycommon.TaskSubmitReq) (*motionControlRequestPayload, error) {
	r := motionControlRequestPayload{
		Prompt:            req.Prompt,
		Mode:              defaultString(req.Mode, "std"),
		KeepOriginalSound: "yes", // 默认保留原声
	}

	// 从 metadata 中解析所有字段
	if req.Metadata != nil {
		metaBytes, err := json.Marshal(req.Metadata)
		if err != nil {
			return nil, errors.Wrap(err, "marshal metadata failed")
		}
		err = json.Unmarshal(metaBytes, &r)
		if err != nil {
			return nil, errors.Wrap(err, "unmarshal metadata failed")
		}
	}

	// 验证必填字段
	if r.ImageUrl == "" {
		return nil, fmt.Errorf("image_url is required for motion-control")
	}
	if r.VideoUrl == "" {
		return nil, fmt.Errorf("video_url is required for motion-control")
	}
	if r.CharacterOrientation == "" {
		return nil, fmt.Errorf("character_orientation is required for motion-control, must be 'image' or 'video'")
	}
	if r.CharacterOrientation != "image" && r.CharacterOrientation != "video" {
		return nil, fmt.Errorf("character_orientation must be 'image' or 'video', got: %s", r.CharacterOrientation)
	}
	if r.Mode != "std" && r.Mode != "pro" {
		return nil, fmt.Errorf("mode must be 'std' or 'pro', got: %s", r.Mode)
	}

	return &r, nil
}

func (a *TaskAdaptor) getAspectRatio(size string) string {
	switch size {
	case "1024x1024", "512x512":
		return "1:1"
	case "1280x720", "1920x1080":
		return "16:9"
	case "720x1280", "1080x1920":
		return "9:16"
	default:
		return "1:1"
	}
}

func defaultString(s, def string) string {
	if strings.TrimSpace(s) == "" {
		return def
	}
	return s
}

func defaultInt(v int, def int) int {
	if v == 0 {
		return def
	}
	return v
}

// ============================
// JWT helpers
// ============================

func (a *TaskAdaptor) createJWTToken() (string, error) {
	return a.createJWTTokenWithKey(a.apiKey)
}

func (a *TaskAdaptor) createJWTTokenWithKey(apiKey string) (string, error) {
	if isNewAPIRelay(apiKey) {
		return apiKey, nil // new api relay
	}
	keyParts := strings.Split(apiKey, "|")
	if len(keyParts) != 2 {
		return "", errors.New("invalid api_key, required format is accessKey|secretKey")
	}
	accessKey := strings.TrimSpace(keyParts[0])
	if len(keyParts) == 1 {
		return accessKey, nil
	}
	secretKey := strings.TrimSpace(keyParts[1])
	now := time.Now().Unix()
	claims := jwt.MapClaims{
		"iss": accessKey,
		"exp": now + 1800, // 30 minutes
		"nbf": now - 5,
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	token.Header["typ"] = "JWT"
	return token.SignedString([]byte(secretKey))
}

func (a *TaskAdaptor) ParseTaskResult(respBody []byte) (*relaycommon.TaskInfo, error) {
	taskInfo := &relaycommon.TaskInfo{}
	resPayload := responsePayload{}
	err := json.Unmarshal(respBody, &resPayload)
	if err != nil {
		return nil, errors.Wrap(err, "failed to unmarshal response body")
	}
	taskInfo.Code = resPayload.Code
	taskInfo.TaskID = resPayload.Data.TaskId
	taskInfo.Reason = resPayload.Message
	//任务状态，枚举值：submitted（已提交）、processing（处理中）、succeed（成功）、failed（失败）
	status := resPayload.Data.TaskStatus
	switch status {
	case "submitted":
		taskInfo.Status = model.TaskStatusSubmitted
	case "processing":
		taskInfo.Status = model.TaskStatusInProgress
	case "succeed":
		taskInfo.Status = model.TaskStatusSuccess
	case "failed":
		taskInfo.Status = model.TaskStatusFailure
	default:
		return nil, fmt.Errorf("unknown task status: %s", status)
	}
	if status == "succeed" && len(resPayload.Data.TaskResult.Videos) > 0 {
		video := resPayload.Data.TaskResult.Videos[0]
		taskInfo.Url = video.Url
		// 将视频实际时长解析并存入明确的 Duration 字段（用于异步核销）
		if video.Duration != "" {
			var duration float64
			if _, err := fmt.Sscanf(video.Duration, "%f", &duration); err == nil {
				taskInfo.Duration = duration
			}
		}
	}
	return taskInfo, nil
}

func isNewAPIRelay(apiKey string) bool {
	return strings.HasPrefix(apiKey, "sk-")
}

func (a *TaskAdaptor) ConvertToOpenAIVideo(originTask *model.Task) ([]byte, error) {
	var klingResp responsePayload
	if err := json.Unmarshal(originTask.Data, &klingResp); err != nil {
		return nil, errors.Wrap(err, "unmarshal kling task data failed")
	}

	openAIVideo := dto.NewOpenAIVideo()
	openAIVideo.ID = originTask.TaskID
	openAIVideo.Status = originTask.Status.ToVideoStatus()
	openAIVideo.SetProgressStr(originTask.Progress)
	openAIVideo.CreatedAt = klingResp.Data.CreatedAt
	openAIVideo.CompletedAt = klingResp.Data.UpdatedAt

	if len(klingResp.Data.TaskResult.Videos) > 0 {
		video := klingResp.Data.TaskResult.Videos[0]
		if video.Url != "" {
			openAIVideo.SetMetadata("url", video.Url)
		}
		if video.Duration != "" {
			openAIVideo.Seconds = video.Duration
		}
	}

	if klingResp.Code != 0 && klingResp.Message != "" {
		openAIVideo.Error = &dto.OpenAIVideoError{
			Message: klingResp.Message,
			Code:    fmt.Sprintf("%d", klingResp.Code),
		}
	}
	jsonData, _ := common.Marshal(openAIVideo)
	return jsonData, nil
}
