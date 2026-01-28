package kling

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"math"
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
	Prompt               string `json:"prompt,omitempty"`              // 文本提示词，可选，不超过2500字符
	ImageUrl             string `json:"image_url"`                     // 参考图像，必须
	VideoUrl             string `json:"video_url"`                     // 参考视频，必须
	KeepOriginalSound    string `json:"keep_original_sound,omitempty"` // 是否保留视频原声，可选，默认yes，枚举值：yes/no
	CharacterOrientation string `json:"character_orientation"`         // 人物朝向，必须，枚举值：image/video
	Mode                 string `json:"mode"`                          // 生成模式，必须，枚举值：std/pro
	CallbackUrl          string `json:"callback_url,omitempty"`        // 回调地址，可选
	ExternalTaskId       string `json:"external_task_id,omitempty"`    // 自定义任务ID，可选
}

// identifyFaceRequestPayload 人脸识别 API 专用请求结构 (对口型前置步骤)
type identifyFaceRequestPayload struct {
	VideoId  string `json:"video_id,omitempty"`  // 可灵AI生成的视频的ID，与video_url二选一
	VideoUrl string `json:"video_url,omitempty"` // 视频的获取URL，与video_id二选一
}

// faceChooseItem 对口型人脸选择项
type faceChooseItem struct {
	FaceId              string  `json:"face_id"`                         // 人脸ID，由人脸识别接口返回
	AudioId             string  `json:"audio_id,omitempty"`              // 试听接口生成的音频的ID，与sound_file二选一
	SoundFile           string  `json:"sound_file,omitempty"`            // 音频文件（Base64编码或URL），与audio_id二选一
	SoundStartTime      int64   `json:"sound_start_time"`                // 音频裁剪起点时间，单位ms
	SoundEndTime        int64   `json:"sound_end_time"`                  // 音频裁剪终点时间，单位ms
	SoundInsertTime     int64   `json:"sound_insert_time"`               // 裁剪后音频插入时间，单位ms
	SoundVolume         float64 `json:"sound_volume,omitempty"`          // 音频音量大小，取值范围[0, 2]，默认1
	OriginalAudioVolume float64 `json:"original_audio_volume,omitempty"` // 原始视频音量大小，取值范围[0, 2]，默认1
}

// advancedLipSyncRequestPayload 对口型创建任务 API 专用请求结构
type advancedLipSyncRequestPayload struct {
	SessionId      string           `json:"session_id"`                 // 会话ID，由人脸识别接口生成
	FaceChoose     []faceChooseItem `json:"face_choose"`                // 指定人脸对口型，暂时仅支持单人
	ExternalTaskId string           `json:"external_task_id,omitempty"` // 自定义任务ID，可选
	CallbackUrl    string           `json:"callback_url,omitempty"`     // 回调地址，可选
}

// videoExtendRequestPayload 视频延长 API 专用请求结构
type videoExtendRequestPayload struct {
	VideoId        string  `json:"video_id"`                  // 视频ID，必须
	Prompt         string  `json:"prompt,omitempty"`          // 正向文本提示词，不超过2500字符
	NegativePrompt string  `json:"negative_prompt,omitempty"` // 负向文本提示词，不超过2500字符
	CfgScale       float64 `json:"cfg_scale,omitempty"`       // 提示词参考强度，取值范围[0,1]，默认0.5
	CallbackUrl    string  `json:"callback_url,omitempty"`    // 回调地址，可选
}

// ============================
// 语音合成 (TTS) 请求/响应结构体
// ============================

// ttsRequestPayload 语音合成 API 请求结构
// 官方文档: https://app.klingai.com/cn/dev/document-api/apiReference/model/TTS
// 接口地址: POST /v1/audio/tts
type ttsRequestPayload struct {
	Text          string  `json:"text"`                     // 待合成的文本内容，必须，最大长度1000字符
	VoiceId       string  `json:"voice_id"`                 // 音色ID，必须
	VoiceLanguage string  `json:"voice_language,omitempty"` // 音色语种，枚举值：zh, en，默认zh
	VoiceSpeed    float64 `json:"voice_speed,omitempty"`    // 语速，可选，取值范围[0.8, 2.0]，默认1.0
	CallbackUrl   string  `json:"callback_url,omitempty"`   // 回调地址，可选
}

// ttsResponsePayload 语音合成 API 响应结构（同步返回音频结果）
type ttsResponsePayload struct {
	Code      int    `json:"code"`
	Message   string `json:"message"`
	RequestId string `json:"request_id"`
	Data      struct {
		TaskId        string `json:"task_id"`         // 任务ID
		TaskStatus    string `json:"task_status"`     // 任务状态：succeed
		TaskStatusMsg string `json:"task_status_msg"` // 任务状态信息
		TaskResult    struct {
			Audios []struct {
				Id       string `json:"id"`       // 生成音频的ID
				Url      string `json:"url"`      // 生成音频的URL
				Duration string `json:"duration"` // 音频时长（秒）
			} `json:"audios"`
		} `json:"task_result"`
		CreatedAt int64 `json:"created_at"` // 任务创建时间
		UpdatedAt int64 `json:"updated_at"` // 任务更新时间
	} `json:"data"`
}

// ============================
// 多模态视频编辑 (Multi-Elements) 请求/响应结构体
// ============================

// multiElementsInitRequestPayload 初始化待编辑视频 API 请求结构
type multiElementsInitRequestPayload struct {
	VideoId  string `json:"video_id,omitempty"`  // 视频ID，从历史作品中选择，与video_url二选一
	VideoUrl string `json:"video_url,omitempty"` // 获取视频的URL，与video_id二选一
}

// multiElementsInitResponsePayload 初始化待编辑视频 API 响应结构
type multiElementsInitResponsePayload struct {
	Code      int    `json:"code"`
	Message   string `json:"message"`
	RequestId string `json:"request_id"`
	Data      struct {
		Status           int     `json:"status"`            // 拒识码，非0为识别失败
		SessionId        string  `json:"session_id"`        // 会话ID，有效期24小时
		Fps              float64 `json:"fps"`               // 解析后视频的帧数
		OriginalDuration float64 `json:"original_duration"` // 解析后视频的时长（毫秒）
		Width            int     `json:"width"`             // 解析后视频的宽
		Height           int     `json:"height"`            // 解析后视频的高
		TotalFrame       int     `json:"total_frame"`       // 解析后视频的总帧数
		NormalizedVideo  string  `json:"normalized_video"`  // 初始化后的视频URL
	} `json:"data"`
}

// multiElementsPointItem 点选坐标项
type multiElementsPointItem struct {
	X float64 `json:"x"` // 取值范围[0,1]
	Y float64 `json:"y"` // 取值范围[0,1]
}

// multiElementsAddSelectionRequestPayload 增加视频选区 API 请求结构
type multiElementsAddSelectionRequestPayload struct {
	SessionId  string                   `json:"session_id"`  // 会话ID，必须
	FrameIndex int                      `json:"frame_index"` // 帧号，必须
	Points     []multiElementsPointItem `json:"points"`      // 点选坐标，必须
}

// multiElementsDeleteSelectionRequestPayload 删减视频选区 API 请求结构
type multiElementsDeleteSelectionRequestPayload struct {
	SessionId  string                   `json:"session_id"`  // 会话ID，必须
	FrameIndex int                      `json:"frame_index"` // 帧号，必须
	Points     []multiElementsPointItem `json:"points"`      // 点选坐标，必须
}

// multiElementsClearSelectionRequestPayload 清除视频选区 API 请求结构
type multiElementsClearSelectionRequestPayload struct {
	SessionId string `json:"session_id"` // 会话ID，必须
}

// multiElementsPreviewRequestPayload 预览已选区视频 API 请求结构
type multiElementsPreviewRequestPayload struct {
	SessionId string `json:"session_id"` // 会话ID，必须
}

// RleMaskItem RLE蒙版项
type RleMaskItem struct {
	Size   []int  `json:"size"`   // [宽, 高]
	Counts string `json:"counts"` // RLE编码字符串
}

// PngMaskItem PNG蒙版项
type PngMaskItem struct {
	Size   []int  `json:"size"`   // [宽, 高]
	Base64 string `json:"base64"` // Base64编码的PNG图片
}

// RleMaskListItem RLE蒙版列表项
type RleMaskListItem struct {
	ObjectId int          `json:"object_id"` // 对象ID
	RleMask  *RleMaskItem `json:"rle_mask"`  // RLE蒙版
	PngMask  *PngMaskItem `json:"png_mask"`  // PNG蒙版
}

// multiElementsSelectionResponsePayload 选区操作（增加/删减/清除）响应结构
type multiElementsSelectionResponsePayload struct {
	Code      int    `json:"code"`
	Message   string `json:"message"`
	RequestId string `json:"request_id"`
	Data      struct {
		Status    int    `json:"status"`     // 拒识码，非0为识别失败
		SessionId string `json:"session_id"` // 会话ID
		Res       *struct {
			FrameIndex  int               `json:"frame_index"`   // 帧号
			RleMaskList []RleMaskListItem `json:"rle_mask_list"` // RLE蒙版列表
		} `json:"res,omitempty"` // 图像分割返回结果
	} `json:"data"`
}

// multiElementsPreviewResponsePayload 预览已选区视频响应结构
type multiElementsPreviewResponsePayload struct {
	Code      int    `json:"code"`
	Message   string `json:"message"`
	RequestId string `json:"request_id"`
	Data      struct {
		Status    int    `json:"status"`     // 拒识码，非0为识别失败
		SessionId string `json:"session_id"` // 会话ID
		Res       *struct {
			Video          string `json:"video"`           // 含mask的视频URL
			VideoCover     string `json:"video_cover"`     // 含mask的视频封面URL
			TrackingOutput string `json:"tracking_output"` // 图像分割结果中，每一帧mask结果
		} `json:"res,omitempty"`
	} `json:"data"`
}

// multiElementsCreateRequestPayload 创建多模态视频编辑任务请求结构
type multiElementsCreateRequestPayload struct {
	ModelName      string           `json:"model_name,omitempty"`       // 模型名称，枚举值：kling-v1-6
	SessionId      string           `json:"session_id"`                 // 会话ID，必须
	EditMode       string           `json:"edit_mode"`                  // 操作类型，必须：addition/swap/removal
	ImageList      []MultiImageItem `json:"image_list,omitempty"`       // 裁剪后的参考图像，增加/替换元素时必填
	Prompt         string           `json:"prompt"`                     // 正向文本提示词，必须，不超过2500字符
	NegativePrompt string           `json:"negative_prompt,omitempty"`  // 负向文本提示词，不超过2500字符
	Mode           string           `json:"mode,omitempty"`             // 生成模式，枚举值：std/pro
	Duration       string           `json:"duration,omitempty"`         // 生成视频时长，枚举值：5/10
	CallbackUrl    string           `json:"callback_url,omitempty"`     // 回调地址，可选
	ExternalTaskId string           `json:"external_task_id,omitempty"` // 自定义任务ID，可选
}

// multiElementsCreateResponsePayload 创建多模态视频编辑任务响应结构
type multiElementsCreateResponsePayload struct {
	Code      int    `json:"code"`
	Message   string `json:"message"`
	RequestId string `json:"request_id"`
	Data      struct {
		TaskId     string `json:"task_id"`     // 任务ID
		TaskStatus string `json:"task_status"` // 任务状态
		SessionId  string `json:"session_id"`  // 会话ID
		CreatedAt  int64  `json:"created_at"`  // 任务创建时间
		UpdatedAt  int64  `json:"updated_at"`  // 任务更新时间
	} `json:"data"`
}

// multiElementsQueryResponsePayload 查询多模态视频编辑任务响应结构
type multiElementsQueryResponsePayload struct {
	Code      int    `json:"code"`
	Message   string `json:"message"`
	RequestId string `json:"request_id"`
	Data      struct {
		TaskId        string `json:"task_id"`         // 任务ID
		TaskStatus    string `json:"task_status"`     // 任务状态
		TaskStatusMsg string `json:"task_status_msg"` // 任务状态信息
		TaskInfo      struct {
			ExternalTaskId string `json:"external_task_id"` // 客户自定义任务ID
		} `json:"task_info"`
		TaskResult struct {
			Videos []struct {
				Id        string `json:"id"`         // 生成的视频ID
				SessionId string `json:"session_id"` // 会话ID
				Url       string `json:"url"`        // 生成视频的URL
				Duration  string `json:"duration"`   // 视频总时长
			} `json:"videos"`
		} `json:"task_result"`
		CreatedAt int64 `json:"created_at"` // 任务创建时间
		UpdatedAt int64 `json:"updated_at"` // 任务更新时间
	} `json:"data"`
}

// ============================
// 数字人 (Avatar) 请求/响应结构体
// ============================

// avatarImage2VideoRequestPayload 数字人图生视频 API 请求结构
// 官方文档: https://app.klingai.com/cn/dev/document-api/apiReference/model/avatar
// 接口地址: POST /v1/videos/avatar/image2video
type avatarImage2VideoRequestPayload struct {
	Image          string `json:"image"`                      // 数字人参考图，必须，支持Base64编码或图片URL
	AudioId        string `json:"audio_id,omitempty"`         // 试听接口生成的音频ID，与sound_file二选一
	SoundFile      string `json:"sound_file,omitempty"`       // 音频文件（Base64编码或URL），与audio_id二选一
	Prompt         string `json:"prompt,omitempty"`           // 正向文本提示词，可定义数字人动作、情绪及运镜等，不超过2500字符
	Mode           string `json:"mode,omitempty"`             // 生成视频的模式，枚举值：std（标准模式）, pro（专家模式），默认std
	CallbackUrl    string `json:"callback_url,omitempty"`     // 回调通知地址，可选
	ExternalTaskId string `json:"external_task_id,omitempty"` // 自定义任务ID，可选
}

// avatarImage2VideoResponsePayload 数字人图生视频 API 响应结构
type avatarImage2VideoResponsePayload struct {
	Code      int    `json:"code"`       // 错误码
	Message   string `json:"message"`    // 错误信息
	RequestId string `json:"request_id"` // 请求ID
	Data      struct {
		TaskId     string `json:"task_id"`     // 任务ID
		TaskInfo   struct {
			ExternalTaskId string `json:"external_task_id"` // 客户自定义任务ID
		} `json:"task_info"`
		TaskStatus string `json:"task_status"` // 任务状态：submitted, processing, succeed, failed
		CreatedAt  int64  `json:"created_at"`  // 任务创建时间，Unix时间戳ms
		UpdatedAt  int64  `json:"updated_at"`  // 任务更新时间，Unix时间戳ms
	} `json:"data"`
}

// avatarImage2VideoQueryResponsePayload 数字人任务查询响应结构
type avatarImage2VideoQueryResponsePayload struct {
	Code      int    `json:"code"`       // 错误码
	Message   string `json:"message"`    // 错误信息
	RequestId string `json:"request_id"` // 请求ID
	Data      struct {
		TaskId        string `json:"task_id"`         // 任务ID
		TaskStatus    string `json:"task_status"`     // 任务状态：submitted, processing, succeed, failed
		TaskStatusMsg string `json:"task_status_msg"` // 任务状态信息，失败时展示失败原因
		TaskInfo      struct {
			ExternalTaskId string `json:"external_task_id"` // 客户自定义任务ID
		} `json:"task_info"`
		TaskResult struct {
			Videos []struct {
				Id       string `json:"id"`       // 生成的视频ID
				Url      string `json:"url"`      // 生成视频的URL
				Duration string `json:"duration"` // 视频总时长，单位s
			} `json:"videos"`
		} `json:"task_result"`
		CreatedAt int64 `json:"created_at"` // 任务创建时间，Unix时间戳ms
		UpdatedAt int64 `json:"updated_at"` // 任务更新时间，Unix时间戳ms
	} `json:"data"`
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

// identifyFaceResponsePayload 人脸识别响应结构体
type identifyFaceResponsePayload struct {
	Code      int    `json:"code"`
	Message   string `json:"message"`
	RequestId string `json:"request_id"`
	Data      struct {
		SessionId string `json:"session_id"` // 会话ID，有效期24小时
		FaceData  []struct {
			FaceId    string `json:"face_id"`    // 人脸ID
			FaceImage string `json:"face_image"` // 人脸示意图URL
			StartTime int64  `json:"start_time"` // 可对口型区间起点时间
			EndTime   int64  `json:"end_time"`   // 可对口型区间终点时间
		} `json:"face_data"`
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

// multiElementsProScale 多模态视频编辑 Pro 模式相对于 Std 模式的价格倍率
// 官方价格: std 5s=3元, 10s=6元; pro 5s=5元, 10s=10元
// Pro/Std 倍率 = 5/3 ≈ 1.667
var multiElementsProScale = 5.0 / 3.0

// multiImage2VideoProScale 多图参考生视频 Pro 模式相对于 Std 模式的价格倍率
// 官方价格: V1.6 std 5s=2元, 10s=4元; pro 5s=3.5元, 10s=7元
// Pro/Std 倍率 = 3.5/2 = 1.75
var multiImage2VideoProScale = 3.5 / 2.0

// multiImage2VideoStdScaleMap 多图参考生视频 Std 模式的基础倍率（相对于普通视频）
// 官方价格: V1.6 std 5s=2元, 10s=4元 → 每秒0.4元
// 普通视频 V1.6 std: 每秒约0.056元（5s=0.28元）
// 倍率 = 0.4 / 0.056 ≈ 7.14
var multiImage2VideoStdScaleMap = map[string]float64{
	"kling-v1-6": 2.0 / 0.28, // 约 7.14，使多图生视频 5s=2元（普通视频 5s=0.28元）
}

// videoExtendProScaleMap 视频延长 Pro 模式相对于 Std 模式的价格倍率
// 官方价格:
//   V1: std=1元, pro=3.5元 → pro/std = 3.5
//   V1.5: std=2元, pro=3.5元 → pro/std = 1.75
//   V1.6: std=2元, pro=3.5元 → pro/std = 1.75
var videoExtendProScaleMap = map[string]float64{
	"kling-v1":   3.5 / 1.0, // 3.5
	"kling-v1-5": 3.5 / 2.0, // 1.75
	"kling-v1-6": 3.5 / 2.0, // 1.75
}

// videoExtendStdScaleMap 视频延长 Std 模式的基础倍率（相对于 V1 std）
// V1 std=1元为基准, V1.5/V1.6 std=2元
var videoExtendStdScaleMap = map[string]float64{
	"kling-v1":   1.0,
	"kling-v1-5": 2.0,
	"kling-v1-6": 2.0,
}

// advancedLipSyncPricePerUnit 对口型计费：每5秒0.5元，不足5秒按5秒计算
// 计费单位为5秒，每单位0.5元
const advancedLipSyncPricePerUnit = 0.5 // 每5秒0.5元
const advancedLipSyncUnitSeconds = 5.0  // 计费单位：5秒

// identifyFacePricePerCall 人脸识别计费：每次0.05元
// 官方价格：每次从资源包总数里扣减0.05积分
const identifyFacePricePerCall = 0.05 // 每次0.05元

// ttsPricePerCall 语音合成计费：每次0.05元
// 官方价格：每次从资源包总数里扣减0.05积分
const ttsPricePerCall = 0.05 // 每次0.05元

// avatarStdPricePerCall 数字人 Std 模式计费：每次价格
// 官方价格：std 模式按次计费
const avatarStdPricePerCall = 1.0 // 每次1元（std模式），请根据官方价格调整

// avatarProPricePerCall 数字人 Pro 模式计费：每次价格
// 官方价格：pro 模式按次计费
const avatarProPricePerCall = 2.0 // 每次2元（pro模式），请根据官方价格调整

// priceRatioToOfficial 内部计价单位与官方价格的比例
// ModelPrice = 官方价格 × 0.14
const priceRatioToOfficial = 0.14

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
	} else if action == constant.TaskActionMultiElementsCreate {
		// 多模态视频编辑专用倍率：Std = 1.0, Pro = 5/3 ≈ 1.667
		// 官方价格: std 5s=3元, 10s=6元; pro 5s=5元, 10s=10元
		if mode == "pro" {
			modeScale = multiElementsProScale
		} else {
			modeScale = 1.0
		}
	} else if action == constant.TaskActionVideoExtend {
		// 视频延长计费：根据模型和模式计算
		// 官方价格: V1 std=1元, pro=3.5元; V1.5/V1.6 std=2元, pro=3.5元
		model := req.Model
		if model == "" {
			model = "kling-v1-6" // 默认模型
		}
		// 获取 std 基础倍率
		stdScale, ok := videoExtendStdScaleMap[model]
		if !ok {
			stdScale = 2.0 // 默认使用 V1.6 的价格
		}
		if mode == "pro" {
			// pro 模式：基础倍率 * pro/std 倍率
			proScale, ok := videoExtendProScaleMap[model]
			if !ok {
				proScale = 1.75 // 默认使用 V1.6 的倍率
			}
			modeScale = stdScale * proScale
		} else {
			modeScale = stdScale
		}
	} else if action == constant.TaskActionAdvancedLipSync {
		// 对口型计费：每5秒0.5元，不足5秒按5秒计算
		// 这里返回1.0，实际计费在 GetPriceScale 中按时长计算
		modeScale = 1.0
	} else if action == constant.TaskActionMultiImage2Video {
		// 多图参考生视频计费：与普通视频相同
		// 官方价格: V1.6 std 5s=2元, 10s=4元; pro 5s=3.5元, 10s=7元
		// 与普通 V1.6 视频价格完全一致，使用相同的计费逻辑
		model := req.Model
		if model == "" {
			model = "kling-v1-6" // 默认模型
		}
		modeScale, err = calculateModeScale(mode, model)
		if err != nil {
			return 1.0, err
		}
	} else if action == constant.TaskActionAvatarImage2Video {
		// 数字人图生视频按次计费，在 GetPriceScale 中单独处理
		// 这里返回 1.0，实际计费在 GetPriceScale 中按次计算
		modeScale = 1.0
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

	// 免费辅助操作不扣费，返回 0
	// 这些操作是多模态视频编辑的前置/辅助步骤
	freeActions := map[string]bool{
		constant.TaskActionMultiElementsInit:            true, // 初始化待编辑视频
		constant.TaskActionMultiElementsAddSelection:    true, // 增加视频选区
		constant.TaskActionMultiElementsDeleteSelection: true, // 删减视频选区
		constant.TaskActionMultiElementsClearSelection:  true, // 清除视频选区
		constant.TaskActionMultiElementsPreview:         true, // 预览已选区视频
		// 注意：人脸识别不再免费，按次收费 0.05 元
	}
	if freeActions[action] {
		return 0, nil
	}

	// 人脸识别按次计费：0.05 元/次
	// 官方价格：每次从资源包总数里扣减 0.05 积分
	if action == constant.TaskActionIdentifyFace {
		// 返回 0.05 / 0.14 ≈ 0.357，使 ModelPrice(0.14) × 0.357 ≈ 0.05
		return float32(identifyFacePricePerCall / priceRatioToOfficial), nil
	}

	// 语音合成按次计费：0.05 元/次
	// 官方价格：每次从资源包总数里扣减 0.05 积分
	if action == constant.TaskActionTTS {
		// 返回 0.05 / 0.14 ≈ 0.357，使 ModelPrice(0.14) × 0.357 ≈ 0.05
		return float32(ttsPricePerCall / priceRatioToOfficial), nil
	}

	// 数字人图生视频按次计费
	// 官方价格：std 模式和 pro 模式分别计费
	if action == constant.TaskActionAvatarImage2Video {
		mode := defaultString(req.Mode, "std")
		pricePerCall := avatarStdPricePerCall
		if mode == "pro" {
			pricePerCall = avatarProPricePerCall
		}
		return float32(pricePerCall / priceRatioToOfficial), nil
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
	} else if action == constant.TaskActionMultiElementsCreate {
		// 多模态视频编辑仅支持 5s 和 10s
		// 官方价格: std 5s=3元, 10s=6元; pro 5s=5元, 10s=10元
		multiElementsReq, _ := a.convertToMultiElementsCreatePayload(&req)
		if multiElementsReq.Duration != "5" && multiElementsReq.Duration != "10" {
			duration = 5.0 // 默认 5s
		} else {
			durationInt, _ := validateIntegerDuration(multiElementsReq.Duration)
			duration = float64(durationInt)
		}
	} else if action == constant.TaskActionVideoExtend {
		// 视频延长：每次延长 4~5s，按次计费
		// 官方价格: V1 std=1元, pro=3.5元; V1.5/V1.6 std=2元, pro=3.5元
		// duration 设为1，表示1次操作，unitScale 已包含模型和模式的价格
		duration = 1.0
	} else if action == constant.TaskActionAdvancedLipSync {
		// 对口型计费：每5秒0.5元，不足5秒按5秒计算
		// 预扣费时需要计算音频时长
		lipSyncReq, _ := a.convertToAdvancedLipSyncPayload(&req)
		if lipSyncReq != nil && len(lipSyncReq.FaceChoose) > 0 {
			// 计算总音频时长（毫秒）
			var totalDurationMs int64 = 0
			for _, face := range lipSyncReq.FaceChoose {
				audioDuration := face.SoundEndTime - face.SoundStartTime
				if audioDuration > 0 {
					totalDurationMs += audioDuration
				}
			}
			// 转换为秒，向上取整到5秒的倍数
			totalDurationSec := float64(totalDurationMs) / 1000.0
			if totalDurationSec < advancedLipSyncUnitSeconds {
				totalDurationSec = advancedLipSyncUnitSeconds // 最少5秒
			}
			// 计算计费单位数（每5秒一个单位）
			units := math.Ceil(totalDurationSec / advancedLipSyncUnitSeconds)
			// 每单位0.5元
			duration = units * advancedLipSyncPricePerUnit
		} else {
			// 默认预扣1个单位（5秒）
			duration = advancedLipSyncPricePerUnit
		}
		// 对口型的 unitScale 已设为1.0，这里 duration 直接是价格倍率
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
	// 检查是否是不需要 prompt 的接口
	currentAction := c.GetString("action")
	noPromptRequired := currentAction == constant.TaskActionMultiElementsInit || // 多模态视频编辑 - 初始化
		currentAction == constant.TaskActionMultiElementsAddSelection || // 多模态视频编辑 - 增加选区
		currentAction == constant.TaskActionMultiElementsDeleteSelection || // 多模态视频编辑 - 删减选区
		currentAction == constant.TaskActionMultiElementsClearSelection || // 多模态视频编辑 - 清除选区
		currentAction == constant.TaskActionMultiElementsPreview || // 多模态视频编辑 - 预览
		currentAction == constant.TaskActionIdentifyFace || // 人脸识别（对口型前置步骤）
		currentAction == constant.TaskActionAdvancedLipSync || // 对口型
		currentAction == constant.TaskActionVideoExtend || // 视频延长
		currentAction == constant.TaskActionTTS || // 语音合成（使用 text 而非 prompt）
		currentAction == constant.TaskActionAvatarImage2Video // 数字人图生视频（prompt 可选）

	// 使用带选项的验证方法
	return relaycommon.ValidateBasicTaskRequestWithOptions(c, info, constant.TaskActionGenerate, !noPromptRequired)
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
	case constant.TaskActionIdentifyFace:
		path = "/v1/videos/identify-face"
	case constant.TaskActionAdvancedLipSync:
		path = "/v1/videos/advanced-lip-sync"
	case constant.TaskActionVideoExtend:
		path = "/v1/videos/video-extend"
	case constant.TaskActionTTS:
		path = "/v1/audio/tts"
	// 数字人端点
	case constant.TaskActionAvatarImage2Video:
		path = "/v1/videos/avatar/image2video"
	// 多模态视频编辑端点
	case constant.TaskActionMultiElementsInit:
		path = "/v1/videos/multi-elements/init-selection"
	case constant.TaskActionMultiElementsAddSelection:
		path = "/v1/videos/multi-elements/add-selection"
	case constant.TaskActionMultiElementsDeleteSelection:
		path = "/v1/videos/multi-elements/delete-selection"
	case constant.TaskActionMultiElementsClearSelection:
		path = "/v1/videos/multi-elements/clear-selection"
	case constant.TaskActionMultiElementsPreview:
		path = "/v1/videos/multi-elements/preview-selection"
	case constant.TaskActionMultiElementsCreate:
		path = "/v1/videos/multi-elements"
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

	// 人脸识别（对口型前置步骤）使用专用的请求结构
	if currentAction == constant.TaskActionIdentifyFace {
		body, err := a.convertToIdentifyFacePayload(&req)
		if err != nil {
			return nil, err
		}
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		return bytes.NewReader(data), nil
	}

	// 对口型创建任务使用专用的请求结构
	if currentAction == constant.TaskActionAdvancedLipSync {
		body, err := a.convertToAdvancedLipSyncPayload(&req)
		if err != nil {
			return nil, err
		}
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		return bytes.NewReader(data), nil
	}

	// 视频延长使用专用的请求结构
	if currentAction == constant.TaskActionVideoExtend {
		body, err := a.convertToVideoExtendPayload(&req)
		if err != nil {
			return nil, err
		}
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		return bytes.NewReader(data), nil
	}

	// 语音合成使用专用的请求结构
	if currentAction == constant.TaskActionTTS {
		body, err := a.convertToTTSPayload(&req)
		if err != nil {
			return nil, err
		}
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		return bytes.NewReader(data), nil
	}

	// 数字人图生视频使用专用的请求结构
	if currentAction == constant.TaskActionAvatarImage2Video {
		body, err := a.convertToAvatarImage2VideoPayload(&req)
		if err != nil {
			return nil, err
		}
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		return bytes.NewReader(data), nil
	}

	// 多模态视频编辑 - 初始化待编辑视频
	if currentAction == constant.TaskActionMultiElementsInit {
		body, err := a.convertToMultiElementsInitPayload(&req)
		if err != nil {
			return nil, err
		}
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		return bytes.NewReader(data), nil
	}

	// 多模态视频编辑 - 增加视频选区
	if currentAction == constant.TaskActionMultiElementsAddSelection {
		body, err := a.convertToMultiElementsAddSelectionPayload(&req)
		if err != nil {
			return nil, err
		}
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		return bytes.NewReader(data), nil
	}

	// 多模态视频编辑 - 删减视频选区
	if currentAction == constant.TaskActionMultiElementsDeleteSelection {
		body, err := a.convertToMultiElementsDeleteSelectionPayload(&req)
		if err != nil {
			return nil, err
		}
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		return bytes.NewReader(data), nil
	}

	// 多模态视频编辑 - 清除视频选区
	if currentAction == constant.TaskActionMultiElementsClearSelection {
		body, err := a.convertToMultiElementsClearSelectionPayload(&req)
		if err != nil {
			return nil, err
		}
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		return bytes.NewReader(data), nil
	}

	// 多模态视频编辑 - 预览已选区视频
	if currentAction == constant.TaskActionMultiElementsPreview {
		body, err := a.convertToMultiElementsPreviewPayload(&req)
		if err != nil {
			return nil, err
		}
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		return bytes.NewReader(data), nil
	}

	// 多模态视频编辑 - 创建任务
	if currentAction == constant.TaskActionMultiElementsCreate {
		body, err := a.convertToMultiElementsCreatePayload(&req)
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

	currentAction := c.GetString("action")

	// 人脸识别端点返回的是人脸数据而非任务ID，直接透传响应
	if currentAction == constant.TaskActionIdentifyFace {
		var faceResp identifyFaceResponsePayload
		err = json.Unmarshal(responseBody, &faceResp)
		if err != nil {
			taskErr = service.TaskErrorWrapper(err, "unmarshal_response_failed", http.StatusInternalServerError)
			return
		}
		if faceResp.Code != 0 {
			taskErr = service.TaskErrorWrapperLocal(errors.New(faceResp.Message), "identify_face_failed", http.StatusBadRequest)
			return
		}
		// 直接返回原始响应给客户端
		c.Data(http.StatusOK, "application/json", responseBody)
		return "", responseBody, nil
	}

	// 语音合成是同步接口，直接返回音频结果，无需轮询
	if currentAction == constant.TaskActionTTS {
		var ttsResp ttsResponsePayload
		err = json.Unmarshal(responseBody, &ttsResp)
		if err != nil {
			taskErr = service.TaskErrorWrapper(err, "unmarshal_response_failed", http.StatusInternalServerError)
			return
		}
		if ttsResp.Code != 0 {
			taskErr = service.TaskErrorWrapperLocal(errors.New(ttsResp.Message), "tts_failed", http.StatusBadRequest)
			return
		}
		// 直接返回原始响应给客户端（同步接口，一次返回音频结果）
		c.Data(http.StatusOK, "application/json", responseBody)
		return "", responseBody, nil
	}

	// 多模态视频编辑 - 初始化待编辑视频（返回会话信息，非任务ID）
	if currentAction == constant.TaskActionMultiElementsInit {
		var initResp multiElementsInitResponsePayload
		err = json.Unmarshal(responseBody, &initResp)
		if err != nil {
			taskErr = service.TaskErrorWrapper(err, "unmarshal_response_failed", http.StatusInternalServerError)
			return
		}
		if initResp.Code != 0 {
			taskErr = service.TaskErrorWrapperLocal(errors.New(initResp.Message), "multi_elements_init_failed", http.StatusBadRequest)
			return
		}
		if initResp.Data.Status != 0 {
			taskErr = service.TaskErrorWrapperLocal(fmt.Errorf("init selection failed with status: %d", initResp.Data.Status), "multi_elements_init_rejected", http.StatusBadRequest)
			return
		}
		// 直接返回原始响应给客户端
		c.Data(http.StatusOK, "application/json", responseBody)
		return "", responseBody, nil
	}

	// 多模态视频编辑 - 增加/删减/清除视频选区（返回选区结果，非任务ID）
	if currentAction == constant.TaskActionMultiElementsAddSelection ||
		currentAction == constant.TaskActionMultiElementsDeleteSelection ||
		currentAction == constant.TaskActionMultiElementsClearSelection {
		var selectionResp multiElementsSelectionResponsePayload
		err = json.Unmarshal(responseBody, &selectionResp)
		if err != nil {
			taskErr = service.TaskErrorWrapper(err, "unmarshal_response_failed", http.StatusInternalServerError)
			return
		}
		if selectionResp.Code != 0 {
			taskErr = service.TaskErrorWrapperLocal(errors.New(selectionResp.Message), "multi_elements_selection_failed", http.StatusBadRequest)
			return
		}
		if selectionResp.Data.Status != 0 {
			taskErr = service.TaskErrorWrapperLocal(fmt.Errorf("selection operation failed with status: %d", selectionResp.Data.Status), "multi_elements_selection_rejected", http.StatusBadRequest)
			return
		}
		// 直接返回原始响应给客户端
		c.Data(http.StatusOK, "application/json", responseBody)
		return "", responseBody, nil
	}

	// 多模态视频编辑 - 预览已选区视频（返回预览结果，非任务ID）
	if currentAction == constant.TaskActionMultiElementsPreview {
		var previewResp multiElementsPreviewResponsePayload
		err = json.Unmarshal(responseBody, &previewResp)
		if err != nil {
			taskErr = service.TaskErrorWrapper(err, "unmarshal_response_failed", http.StatusInternalServerError)
			return
		}
		if previewResp.Code != 0 {
			taskErr = service.TaskErrorWrapperLocal(errors.New(previewResp.Message), "multi_elements_preview_failed", http.StatusBadRequest)
			return
		}
		if previewResp.Data.Status != 0 {
			taskErr = service.TaskErrorWrapperLocal(fmt.Errorf("preview operation failed with status: %d", previewResp.Data.Status), "multi_elements_preview_rejected", http.StatusBadRequest)
			return
		}
		// 直接返回原始响应给客户端
		c.Data(http.StatusOK, "application/json", responseBody)
		return "", responseBody, nil
	}

	// 多模态视频编辑 - 创建任务（返回任务ID）
	if currentAction == constant.TaskActionMultiElementsCreate {
		var createResp multiElementsCreateResponsePayload
		err = json.Unmarshal(responseBody, &createResp)
		if err != nil {
			taskErr = service.TaskErrorWrapper(err, "unmarshal_response_failed", http.StatusInternalServerError)
			return
		}
		if createResp.Code != 0 {
			taskErr = service.TaskErrorWrapperLocal(errors.New(createResp.Message), "multi_elements_create_failed", http.StatusBadRequest)
			return
		}
		ov := dto.NewOpenAIVideo()
		ov.ID = createResp.Data.TaskId
		ov.TaskID = createResp.Data.TaskId
		ov.CreatedAt = time.Now().Unix()
		ov.Model = info.OriginModelName
		c.JSON(http.StatusOK, ov)
		return createResp.Data.TaskId, responseBody, nil
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
	case constant.TaskActionAdvancedLipSync:
		path = "/v1/videos/advanced-lip-sync"
	case constant.TaskActionVideoExtend:
		path = "/v1/videos/video-extend"
	// 数字人任务查询
	case constant.TaskActionAvatarImage2Video:
		path = "/v1/videos/avatar/image2video"
	// 多模态视频编辑任务查询
	case constant.TaskActionMultiElementsCreate, constant.TaskActionMultiElementsQuery:
		path = "/v1/videos/multi-elements"
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
		// 视频生成模型
		"kling-video-o1",
		"kling-v2-6",
		"kling-v2-5-turbo",
		"kling-v2-1",
		"kling-v1-6",
		"kling-v1-5",
		"kling-v1",
		"kling-v2-1-master",
		"kling-v2-master",
		// 特殊功能模型（用于独立计费）
		"kling-tts",            // 语音合成
		"kling-lip-sync",       // 对口型
		"kling-identify-face",  // 人脸识别
		"kling-video-extend",   // 视频延长
		"kling-multi-elements", // 多模态视频编辑
		"kling-avatar",         // 数字人
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

// convertToIdentifyFacePayload 转换为人脸识别 API 专用请求格式
func (a *TaskAdaptor) convertToIdentifyFacePayload(req *relaycommon.TaskSubmitReq) (*identifyFaceRequestPayload, error) {
	r := identifyFaceRequestPayload{}

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

	// 验证：video_id 和 video_url 二选一，不能同时为空，也不能同时有值
	if r.VideoId == "" && r.VideoUrl == "" {
		return nil, fmt.Errorf("either video_id or video_url is required for identify-face")
	}
	if r.VideoId != "" && r.VideoUrl != "" {
		return nil, fmt.Errorf("video_id and video_url cannot be both provided for identify-face")
	}

	return &r, nil
}

// convertToAdvancedLipSyncPayload 转换为对口型创建任务 API 专用请求格式
func (a *TaskAdaptor) convertToAdvancedLipSyncPayload(req *relaycommon.TaskSubmitReq) (*advancedLipSyncRequestPayload, error) {
	r := advancedLipSyncRequestPayload{}

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
	if r.SessionId == "" {
		return nil, fmt.Errorf("session_id is required for advanced-lip-sync")
	}
	if len(r.FaceChoose) == 0 {
		return nil, fmt.Errorf("face_choose is required for advanced-lip-sync")
	}

	// 验证每个 face_choose 项
	for i, face := range r.FaceChoose {
		if face.FaceId == "" {
			return nil, fmt.Errorf("face_choose[%d].face_id is required", i)
		}
		// audio_id 和 sound_file 二选一
		if face.AudioId == "" && face.SoundFile == "" {
			return nil, fmt.Errorf("face_choose[%d]: either audio_id or sound_file is required", i)
		}
		if face.AudioId != "" && face.SoundFile != "" {
			return nil, fmt.Errorf("face_choose[%d]: audio_id and sound_file cannot be both provided", i)
		}
	}

	return &r, nil
}

// convertToVideoExtendPayload 转换为视频延长 API 专用请求格式
func (a *TaskAdaptor) convertToVideoExtendPayload(req *relaycommon.TaskSubmitReq) (*videoExtendRequestPayload, error) {
	r := videoExtendRequestPayload{
		Prompt:   req.Prompt,
		CfgScale: 0.5, // 默认值
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
	if r.VideoId == "" {
		return nil, fmt.Errorf("video_id is required for video-extend")
	}

	// 验证 cfg_scale 范围
	if r.CfgScale < 0 || r.CfgScale > 1 {
		return nil, fmt.Errorf("cfg_scale must be between 0 and 1, got: %f", r.CfgScale)
	}

	return &r, nil
}

// convertToTTSPayload 转换为语音合成 API 专用请求格式
func (a *TaskAdaptor) convertToTTSPayload(req *relaycommon.TaskSubmitReq) (*ttsRequestPayload, error) {
	r := ttsRequestPayload{
		VoiceLanguage: "zh",  // 默认中文
		VoiceSpeed:    1.0,   // 默认语速
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
	if r.Text == "" {
		return nil, fmt.Errorf("text is required for tts")
	}
	if len(r.Text) > 1000 {
		return nil, fmt.Errorf("text length exceeds maximum 1000 characters, got: %d", len(r.Text))
	}
	if r.VoiceId == "" {
		return nil, fmt.Errorf("voice_id is required for tts")
	}

	// 验证 voice_language 枚举值
	if r.VoiceLanguage != "" && r.VoiceLanguage != "zh" && r.VoiceLanguage != "en" {
		return nil, fmt.Errorf("voice_language must be 'zh' or 'en', got: %s", r.VoiceLanguage)
	}

	// 验证 voice_speed 范围 [0.8, 2.0]
	if r.VoiceSpeed != 0 && (r.VoiceSpeed < 0.8 || r.VoiceSpeed > 2.0) {
		return nil, fmt.Errorf("voice_speed must be between 0.8 and 2.0, got: %f", r.VoiceSpeed)
	}

	return &r, nil
}

// ============================
// 多模态视频编辑 (Multi-Elements) 请求转换函数
// ============================

// convertToMultiElementsInitPayload 转换为初始化待编辑视频 API 请求格式
func (a *TaskAdaptor) convertToMultiElementsInitPayload(req *relaycommon.TaskSubmitReq) (*multiElementsInitRequestPayload, error) {
	r := multiElementsInitRequestPayload{}

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

	// 验证：video_id 和 video_url 二选一，不能同时为空，也不能同时有值
	if r.VideoId == "" && r.VideoUrl == "" {
		return nil, fmt.Errorf("either video_id or video_url is required for multi-elements init")
	}
	if r.VideoId != "" && r.VideoUrl != "" {
		return nil, fmt.Errorf("video_id and video_url cannot be both provided for multi-elements init")
	}

	return &r, nil
}

// convertToMultiElementsAddSelectionPayload 转换为增加视频选区 API 请求格式
func (a *TaskAdaptor) convertToMultiElementsAddSelectionPayload(req *relaycommon.TaskSubmitReq) (*multiElementsAddSelectionRequestPayload, error) {
	r := multiElementsAddSelectionRequestPayload{}

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
	if r.SessionId == "" {
		return nil, fmt.Errorf("session_id is required for multi-elements add-selection")
	}
	if len(r.Points) == 0 {
		return nil, fmt.Errorf("points is required for multi-elements add-selection")
	}

	// 验证点坐标范围
	for i, point := range r.Points {
		if point.X < 0 || point.X > 1 || point.Y < 0 || point.Y > 1 {
			return nil, fmt.Errorf("points[%d]: x and y must be between 0 and 1", i)
		}
	}

	return &r, nil
}

// convertToMultiElementsDeleteSelectionPayload 转换为删减视频选区 API 请求格式
func (a *TaskAdaptor) convertToMultiElementsDeleteSelectionPayload(req *relaycommon.TaskSubmitReq) (*multiElementsDeleteSelectionRequestPayload, error) {
	r := multiElementsDeleteSelectionRequestPayload{}

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
	if r.SessionId == "" {
		return nil, fmt.Errorf("session_id is required for multi-elements delete-selection")
	}
	if len(r.Points) == 0 {
		return nil, fmt.Errorf("points is required for multi-elements delete-selection")
	}

	// 验证点坐标范围
	for i, point := range r.Points {
		if point.X < 0 || point.X > 1 || point.Y < 0 || point.Y > 1 {
			return nil, fmt.Errorf("points[%d]: x and y must be between 0 and 1", i)
		}
	}

	return &r, nil
}

// convertToMultiElementsClearSelectionPayload 转换为清除视频选区 API 请求格式
func (a *TaskAdaptor) convertToMultiElementsClearSelectionPayload(req *relaycommon.TaskSubmitReq) (*multiElementsClearSelectionRequestPayload, error) {
	r := multiElementsClearSelectionRequestPayload{}

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
	if r.SessionId == "" {
		return nil, fmt.Errorf("session_id is required for multi-elements clear-selection")
	}

	return &r, nil
}

// convertToMultiElementsPreviewPayload 转换为预览已选区视频 API 请求格式
func (a *TaskAdaptor) convertToMultiElementsPreviewPayload(req *relaycommon.TaskSubmitReq) (*multiElementsPreviewRequestPayload, error) {
	r := multiElementsPreviewRequestPayload{}

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
	if r.SessionId == "" {
		return nil, fmt.Errorf("session_id is required for multi-elements preview-selection")
	}

	return &r, nil
}

// convertToMultiElementsCreatePayload 转换为创建多模态视频编辑任务 API 请求格式
func (a *TaskAdaptor) convertToMultiElementsCreatePayload(req *relaycommon.TaskSubmitReq) (*multiElementsCreateRequestPayload, error) {
	r := multiElementsCreateRequestPayload{
		Prompt:    req.Prompt,
		ModelName: req.Model,
		Mode:      defaultString(req.Mode, "std"),
		Duration:  fmt.Sprintf("%d", defaultInt(req.Duration, 5)),
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
	if r.SessionId == "" {
		return nil, fmt.Errorf("session_id is required for multi-elements create")
	}
	if r.EditMode == "" {
		return nil, fmt.Errorf("edit_mode is required for multi-elements create")
	}
	if r.EditMode != "addition" && r.EditMode != "swap" && r.EditMode != "removal" {
		return nil, fmt.Errorf("edit_mode must be 'addition', 'swap' or 'removal', got: %s", r.EditMode)
	}
	if r.Prompt == "" {
		return nil, fmt.Errorf("prompt is required for multi-elements create")
	}

	// 根据 edit_mode 验证 image_list
	if r.EditMode == "addition" {
		if len(r.ImageList) == 0 {
			return nil, fmt.Errorf("image_list is required when edit_mode is 'addition'")
		}
		if len(r.ImageList) > 2 {
			return nil, fmt.Errorf("image_list supports up to 2 images for addition mode, got: %d", len(r.ImageList))
		}
	} else if r.EditMode == "swap" {
		if len(r.ImageList) != 1 {
			return nil, fmt.Errorf("image_list must contain exactly 1 image for swap mode, got: %d", len(r.ImageList))
		}
	}
	// removal 模式不需要 image_list

	// 验证 duration
	if r.Duration != "5" && r.Duration != "10" {
		return nil, fmt.Errorf("duration must be '5' or '10', got: %s", r.Duration)
	}

	// 验证 mode
	if r.Mode != "std" && r.Mode != "pro" {
		return nil, fmt.Errorf("mode must be 'std' or 'pro', got: %s", r.Mode)
	}

	return &r, nil
}

// convertToAvatarImage2VideoPayload 转换为数字人图生视频 API 请求格式
func (a *TaskAdaptor) convertToAvatarImage2VideoPayload(req *relaycommon.TaskSubmitReq) (*avatarImage2VideoRequestPayload, error) {
	r := avatarImage2VideoRequestPayload{
		Prompt: req.Prompt,
		Mode:   defaultString(req.Mode, "std"),
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
	if r.Image == "" {
		return nil, fmt.Errorf("image is required for avatar image2video")
	}

	// 验证 audio_id 和 sound_file 二选一
	if r.AudioId == "" && r.SoundFile == "" {
		return nil, fmt.Errorf("either audio_id or sound_file is required for avatar image2video")
	}
	if r.AudioId != "" && r.SoundFile != "" {
		return nil, fmt.Errorf("audio_id and sound_file cannot be both provided for avatar image2video")
	}

	// 验证 mode 枚举值
	if r.Mode != "" && r.Mode != "std" && r.Mode != "pro" {
		return nil, fmt.Errorf("mode must be 'std' or 'pro', got: %s", r.Mode)
	}

	// 验证 prompt 长度
	if len(r.Prompt) > 2500 {
		return nil, fmt.Errorf("prompt length exceeds maximum 2500 characters, got: %d", len(r.Prompt))
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
