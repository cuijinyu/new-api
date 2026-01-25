package kling

import (
	"math"
	"net/http/httptest"
	"strconv"
	"testing"

	"github.com/QuantumNous/new-api/constant"
	relaycommon "github.com/QuantumNous/new-api/relay/common"
	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
)

func TestKlingAdaptor_GetPriceScale(t *testing.T) {
	adaptor := &TaskAdaptor{}
	gin.SetMode(gin.TestMode)

	tests := []struct {
		name     string
		action   string
		mode     string
		model    string
		metadata map[string]interface{}
		want     float32
	}{
		{
			name:   "Legacy Text2Video Std 5s",
			action: constant.TaskActionGenerate,
			mode:   "std",
			model:  "kling-v1",
			want:   5.0, // 5s * 1.0
		},
		{
			name:   "Legacy V2.6 Pro 5s",
			action: constant.TaskActionGenerate,
			mode:   "pro",
			model:  "kling-v2-6",
			want:   5.0, // 5s * 1.0 (v2-6 proScale is 1.0 for legacy)
		},
		{
			name:   "Legacy V1 Pro 5s",
			action: constant.TaskActionGenerate,
			mode:   "pro",
			model:  "kling-v1",
			want:   17.5, // 5s * 3.5
		},
		{
			name:   "Motion Control Image Std Max",
			action: constant.TaskActionMotionControl,
			mode:   "std",
			model:  "kling-v2-6",
			metadata: map[string]interface{}{
				"character_orientation": "image",
			},
			want: 10.0, // 10s * 1.0
		},
		{
			name:   "Motion Control Video Pro Max",
			action: constant.TaskActionMotionControl,
			mode:   "pro",
			model:  "kling-v2-6",
			metadata: map[string]interface{}{
				"character_orientation": "video",
			},
			want: 48.0, // 30s * 1.6 (motionControl proScale is 1.6)
		},
		{
			name:   "kling-video-o1 Std 5s (No Video Input)",
			action: constant.TaskActionOmniVideo,
			mode:   "std",
			model:  "kling-video-o1",
			want:   5.0, // 5s * 1.0
		},
		{
			name:   "kling-video-o1 Pro 5s (No Video Input)",
			action: constant.TaskActionOmniVideo,
			mode:   "pro",
			model:  "kling-video-o1",
			want:   float32(5.0 * (0.112 / 0.084)), // 5s * 1.3333333
		},
		{
			name:   "kling-video-o1 Std 5s (With Video Input)",
			action: constant.TaskActionOmniVideo,
			mode:   "std",
			model:  "kling-video-o1",
			metadata: map[string]interface{}{
				"video_list": []interface{}{
					map[string]interface{}{"video_url": "test.mp4"},
				},
			},
			want: float32(5.0 * (0.126 / 0.084)), // 5s * 1.5
		},
		{
			name:   "kling-v2-master (Master mode)",
			action: constant.TaskActionGenerate,
			mode:   "master",
			model:  "kling-v2-master",
			want:   5.0, // 5s * 1.0
		},
		{
			name:   "kling-v2-5-turbo Pro 10s",
			action: constant.TaskActionGenerate,
			mode:   "pro",
			model:  "kling-v2-5-turbo",
			metadata: map[string]interface{}{
				"duration": "10",
			},
			want: float32(10.0 * (0.07 / 0.042)), // 10s * 1.666666
		},
		{
			name:   "kling-v2-master with Std mode (Auto compatibility)",
			action: constant.TaskActionGenerate,
			mode:   "std",
			model:  "kling-v2-master",
			want:   5.0, // Should use master scale (1.0) * duration (5)
		},
		{
			name:   "kling-v2-master with empty mode (Auto compatibility)",
			action: constant.TaskActionGenerate,
			mode:   "",
			model:  "kling-v2-master",
			want:   5.0,
		},
		{
			name:   "MultiImage2Video Std 10s",
			action: constant.TaskActionMultiImage2Video,
			mode:   "std",
			model:  "kling-v1-6",
			metadata: map[string]interface{}{
				"prompt":   "test multi image",
				"duration": "10",
				"image_list": []interface{}{
					map[string]interface{}{"image": "url1"},
					map[string]interface{}{"image": "url2"},
				},
			},
			// 多图生视频与普通视频价格相同: 10s × 1.0 = 10
			// 官方价格: V1.6 Std 10s = 4元，与普通视频一致
			want: 10.0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c, _ := gin.CreateTestContext(httptest.NewRecorder())
			modelName := tt.model
			req := relaycommon.TaskSubmitReq{
				Model:    modelName,
				Mode:     tt.mode,
				Metadata: tt.metadata,
			}
			if tt.metadata != nil {
				if prompt, ok := tt.metadata["prompt"].(string); ok {
					req.Prompt = prompt
				}
				if duration, ok := tt.metadata["duration"].(string); ok {
					if d, err := strconv.Atoi(duration); err == nil {
						req.Duration = d
					}
				}
			}
			c.Set("task_request", req)
			c.Set("action", tt.action)

			info := &relaycommon.RelayInfo{
				TaskRelayInfo: &relaycommon.TaskRelayInfo{
					Action: tt.action,
				},
			}

			got, err := adaptor.GetPriceScale(c, info)
			assert.NoError(t, err)
			assert.Equal(t, tt.want, got)
		})
	}
}

func TestKlingAdaptor_GetUnitPriceScale(t *testing.T) {
	adaptor := &TaskAdaptor{}
	gin.SetMode(gin.TestMode)

	tests := []struct {
		name     string
		mode     string
		action   string
		model    string
		metadata map[string]interface{}
		want     float32
	}{
		{
			name:   "Std Mode Motion",
			mode:   "std",
			action: constant.TaskActionMotionControl,
			model:  "kling-v2-6",
			want:   1.0,
		},
		{
			name:   "Pro Mode Motion",
			mode:   "pro",
			action: constant.TaskActionMotionControl,
			model:  "kling-v2-6",
			want:   1.6,
		},
		{
			name:   "Pro Mode Legacy V1",
			mode:   "pro",
			action: constant.TaskActionGenerate,
			model:  "kling-v1",
			want:   3.5,
		},
		{
			name:   "kling-v2-6 with Sound On",
			mode:   "std",
			action: constant.TaskActionGenerate,
			model:  "kling-v2-6",
			metadata: map[string]interface{}{
				"sound": "on",
			},
			want: 2.0, // 1.0 * 2.0
		},
		{
			name:   "kling-v2-6 with Sound On and Voice Control",
			mode:   "std",
			action: constant.TaskActionGenerate,
			model:  "kling-v2-6",
			metadata: map[string]interface{}{
				"sound":      "on",
				"prompt":     "hello <<<voice_1>>>",
				"voice_list": []interface{}{map[string]interface{}{"voice_id": "v1"}},
			},
			want: 2.4, // 1.0 * 2.0 * 1.2
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c, _ := gin.CreateTestContext(httptest.NewRecorder())
			req := relaycommon.TaskSubmitReq{
				Model:    tt.model,
				Mode:     tt.mode,
				Metadata: tt.metadata,
			}
			if tt.metadata != nil && tt.metadata["prompt"] != nil {
				req.Prompt = tt.metadata["prompt"].(string)
			}
			c.Set("task_request", req)
			c.Set("action", tt.action)

			info := &relaycommon.RelayInfo{
				TaskRelayInfo: &relaycommon.TaskRelayInfo{
					Action: tt.action,
				},
			}

			got, err := adaptor.GetUnitPriceScale(c, info)
			assert.NoError(t, err)
			assert.Equal(t, tt.want, got)
		})
	}
}

func TestKlingAdaptor_ParseTaskResult(t *testing.T) {
	adaptor := &TaskAdaptor{}
	
	respBody := `{
		"code": 0,
		"data": {
			"task_id": "test_task_123",
			"task_status": "succeed",
			"task_result": {
				"videos": [
					{
						"url": "https://example.com/video.mp4",
						"duration": "12.5"
					}
				]
			}
		}
	}`

	taskInfo, err := adaptor.ParseTaskResult([]byte(respBody))
	assert.NoError(t, err)
	assert.Equal(t, "test_task_123", taskInfo.TaskID)
	assert.Equal(t, 12.5, taskInfo.Duration)
}

func TestKling_CalculateOmniVideoDuration(t *testing.T) {
	tests := []struct {
		name    string
		req     *requestPayload
		want    int
		wantErr bool
	}{
		{
			name: "Text2Video 5s",
			req: &requestPayload{
				Duration: "5",
			},
			want: 5,
		},
		{
			name: "Text2Video 10s",
			req: &requestPayload{
				Duration: "10",
			},
			want: 10,
		},
		{
			name: "Text2Video Invalid",
			req: &requestPayload{
				Duration: "3",
			},
			wantErr: true,
		},
		{
			name: "Image2Video 5s",
			req: &requestPayload{
				ImageList: []OmniImageItem{{ImageUrl: "img"}},
				Duration:  "5",
			},
			want: 5,
		},
		{
			name: "Image2Video (First Frame) 3s",
			req: &requestPayload{
				ImageList: []OmniImageItem{{ImageUrl: "img", Type: "first_frame"}},
				Duration:  "3",
			},
			want: 3,
		},
		{
			name: "Image2Video (First Frame) 10s",
			req: &requestPayload{
				ImageList: []OmniImageItem{{ImageUrl: "img", Type: "first_frame"}},
				Duration:  "10",
			},
			want: 10,
		},
		{
			name: "Video Feature 3s",
			req: &requestPayload{
				VideoList: []OmniVideoItem{{VideoUrl: "vid", ReferType: "feature"}},
				Duration:  "3",
			},
			want: 3,
		},
		{
			name: "Video Base (Unsupported)",
			req: &requestPayload{
				VideoList: []OmniVideoItem{{VideoUrl: "vid", ReferType: "base"}},
				Duration:  "5",
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := calculateOmniVideoDuration(tt.req)
			if tt.wantErr {
				assert.Error(t, err)
			} else {
				assert.NoError(t, err)
				assert.Equal(t, tt.want, got)
			}
		})
	}
}

func TestKling_ConvertToRequestPayload(t *testing.T) {
	adaptor := &TaskAdaptor{}
	
	submitReq := &relaycommon.TaskSubmitReq{
		Prompt: "test prompt",
		Model:  "kling-v2-6",
		Mode:   "pro",
		Metadata: map[string]interface{}{
			"duration": "10",
			"sound":    "on",
			"voice_list": []interface{}{
				map[string]interface{}{"voice_id": "v1"},
			},
		},
	}

	payload, err := adaptor.convertToRequestPayload(submitReq)
	assert.NoError(t, err)
	assert.Equal(t, "test prompt", payload.Prompt)
	assert.Equal(t, "pro", payload.Mode)
	assert.Equal(t, "10", payload.Duration)
	assert.Equal(t, "on", payload.Sound)
	assert.Len(t, payload.VoiceList, 1)
	assert.Equal(t, "v1", payload.VoiceList[0].VoiceId)

	// Test case: kling-v2-master with std mode
	submitReq2 := &relaycommon.TaskSubmitReq{
		Model: "kling-v2-master",
		Mode:  "std",
	}
	payload2, err := adaptor.convertToRequestPayload(submitReq2)
	assert.NoError(t, err)
	assert.Equal(t, "", payload2.Mode) // Should be empty for non-std models

	// Test case: kling-v2-master with empty mode
	submitReq3 := &relaycommon.TaskSubmitReq{
		Model: "kling-v2-master",
		Mode:  "",
	}
	payload3, err := adaptor.convertToRequestPayload(submitReq3)
	assert.NoError(t, err)
	assert.Equal(t, "", payload3.Mode)

	// Test case: kling-v2-6 with std mode
	submitReq4 := &relaycommon.TaskSubmitReq{
		Model: "kling-v2-6",
		Mode:  "std",
	}
	payload4, err := adaptor.convertToRequestPayload(submitReq4)
	assert.NoError(t, err)
	assert.Equal(t, "std", payload4.Mode)
}

// ============================================================================
// 可灵计费策略验证测试
// 验证各功能的计费是否与官方价格一致
// ============================================================================

// TestKlingPricing_OrdinaryVideo 普通视频生成计费测试
// 验证 text2video / image2video 的 Std/Pro 模式计费
func TestKlingPricing_OrdinaryVideo(t *testing.T) {
	adaptor := &TaskAdaptor{}
	gin.SetMode(gin.TestMode)

	// 官方价格（每秒）:
	// kling-v1: std=0.028, pro=0.098 → pro/std=3.5
	// kling-v1-5/v1-6/v2-1: std=0.056, pro=0.098 → pro/std=1.75
	// kling-v2-5-turbo: std=0.042, pro=0.07 → pro/std=1.667
	// kling-v2-6: std=0.07, pro=0.07 → pro/std=1.0
	// kling-video-o1: std=0.084, pro=0.112 → pro/std=1.333

	tests := []struct {
		name          string
		model         string
		mode          string
		duration      int
		expectedScale float64 // 预期的 PriceScale
		description   string
	}{
		// kling-v1 测试
		{
			name:          "V1 Std 5s",
			model:         "kling-v1",
			mode:          "std",
			duration:      5,
			expectedScale: 5.0 * 1.0,
			description:   "V1 Std: 5s × 1.0 = 5.0",
		},
		{
			name:          "V1 Pro 5s",
			model:         "kling-v1",
			mode:          "pro",
			duration:      5,
			expectedScale: 5.0 * (0.098 / 0.028), // 5 × 3.5 = 17.5
			description:   "V1 Pro: 5s × 3.5 = 17.5",
		},
		// kling-v1-6 测试
		{
			name:          "V1.6 Std 5s",
			model:         "kling-v1-6",
			mode:          "std",
			duration:      5,
			expectedScale: 5.0 * 1.0,
			description:   "V1.6 Std: 5s × 1.0 = 5.0",
		},
		{
			name:          "V1.6 Pro 10s",
			model:         "kling-v1-6",
			mode:          "pro",
			duration:      10,
			expectedScale: 10.0 * (0.098 / 0.056), // 10 × 1.75 = 17.5
			description:   "V1.6 Pro: 10s × 1.75 = 17.5",
		},
		// kling-v2-6 测试 (Pro 和 Std 价格相同)
		{
			name:          "V2.6 Std 5s",
			model:         "kling-v2-6",
			mode:          "std",
			duration:      5,
			expectedScale: 5.0 * 1.0,
			description:   "V2.6 Std: 5s × 1.0 = 5.0",
		},
		{
			name:          "V2.6 Pro 5s",
			model:         "kling-v2-6",
			mode:          "pro",
			duration:      5,
			expectedScale: 5.0 * (0.07 / 0.07), // 5 × 1.0 = 5.0
			description:   "V2.6 Pro: 5s × 1.0 = 5.0 (Pro和Std价格相同)",
		},
		// kling-v2-5-turbo 测试
		{
			name:          "V2.5-turbo Pro 10s",
			model:         "kling-v2-5-turbo",
			mode:          "pro",
			duration:      10,
			expectedScale: 10.0 * (0.07 / 0.042), // 10 × 1.667 = 16.67
			description:   "V2.5-turbo Pro: 10s × 1.667 = 16.67",
		},
		// kling-video-o1 测试
		{
			name:          "O1 Std 5s",
			model:         "kling-video-o1",
			mode:          "std",
			duration:      5,
			expectedScale: 5.0 * 1.0,
			description:   "O1 Std: 5s × 1.0 = 5.0",
		},
		{
			name:          "O1 Pro 5s",
			model:         "kling-video-o1",
			mode:          "pro",
			duration:      5,
			expectedScale: 5.0 * (0.112 / 0.084), // 5 × 1.333 = 6.67
			description:   "O1 Pro: 5s × 1.333 = 6.67",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c, _ := gin.CreateTestContext(httptest.NewRecorder())
			req := relaycommon.TaskSubmitReq{
				Model:    tt.model,
				Mode:     tt.mode,
				Duration: tt.duration,
			}
			c.Set("task_request", req)
			c.Set("action", constant.TaskActionGenerate)

			info := &relaycommon.RelayInfo{
				TaskRelayInfo: &relaycommon.TaskRelayInfo{
					Action: constant.TaskActionGenerate,
				},
			}

			got, err := adaptor.GetPriceScale(c, info)
			assert.NoError(t, err, tt.description)
			assert.InDelta(t, tt.expectedScale, float64(got), 0.01, tt.description)
		})
	}
}

// TestKlingPricing_MultiImage2Video 多图参考生视频计费测试
// 官方价格: V1.6 std 5s=2元, 10s=4元; pro 5s=3.5元, 10s=7元
func TestKlingPricing_MultiImage2Video(t *testing.T) {
	adaptor := &TaskAdaptor{}
	gin.SetMode(gin.TestMode)

	// 多图生视频与普通 V1.6 视频价格相同
	// 官方价格: Std 5s=2元, 10s=4元; Pro 5s=3.5元, 10s=7元
	// ModelPrice = 0.056 (内部计价单位)
	// 内部计价 = 官方价格 × 0.14
	const priceRatio = 0.14

	tests := []struct {
		name          string
		mode          string
		duration      string
		expectedScale float64
		officialPrice float64 // 官方价格（元）
		description   string
	}{
		{
			name:          "Std 5s",
			mode:          "std",
			duration:      "5",
			expectedScale: 5.0,                  // duration × modeScale(1.0)
			officialPrice: 2.0 * priceRatio,    // 2元 × 0.14 = 0.28
			description:   "多图生视频 Std 5s = 2元",
		},
		{
			name:          "Std 10s",
			mode:          "std",
			duration:      "10",
			expectedScale: 10.0,                 // duration × modeScale(1.0)
			officialPrice: 4.0 * priceRatio,    // 4元 × 0.14 = 0.56
			description:   "多图生视频 Std 10s = 4元",
		},
		{
			name:          "Pro 5s",
			mode:          "pro",
			duration:      "5",
			expectedScale: 5.0 * 1.75,           // duration × proScale(1.75)
			officialPrice: 3.5 * priceRatio,    // 3.5元 × 0.14 = 0.49
			description:   "多图生视频 Pro 5s = 3.5元",
		},
		{
			name:          "Pro 10s",
			mode:          "pro",
			duration:      "10",
			expectedScale: 10.0 * 1.75,          // duration × proScale(1.75)
			officialPrice: 7.0 * priceRatio,    // 7元 × 0.14 = 0.98
			description:   "多图生视频 Pro 10s = 7元",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c, _ := gin.CreateTestContext(httptest.NewRecorder())
			req := relaycommon.TaskSubmitReq{
				Model:  "kling-v1-6",
				Mode:   tt.mode,
				Prompt: "test multi image video prompt", // 必填字段
				Metadata: map[string]interface{}{
					"duration": tt.duration,
					"image_list": []interface{}{
						map[string]interface{}{"image": "https://example.com/img1.jpg"},
						map[string]interface{}{"image": "https://example.com/img2.jpg"},
					},
				},
			}
			c.Set("task_request", req)
			c.Set("action", constant.TaskActionMultiImage2Video)

			info := &relaycommon.RelayInfo{
				TaskRelayInfo: &relaycommon.TaskRelayInfo{
					Action: constant.TaskActionMultiImage2Video,
				},
			}

			got, err := adaptor.GetPriceScale(c, info)
			assert.NoError(t, err, tt.description)

			// 验证 PriceScale
			assert.InDelta(t, tt.expectedScale, float64(got), 0.01, tt.description)

			// 验证最终价格 = ModelPrice(0.056) × PriceScale
			calculatedPrice := 0.056 * float64(got)
			assert.InDelta(t, tt.officialPrice, calculatedPrice, 0.01,
				"价格验证失败: %s, 计算价格=%.2f, 官方价格=%.2f",
				tt.description, calculatedPrice, tt.officialPrice)
		})
	}
}

// TestKlingPricing_VideoExtend 视频延长计费测试
// 官方价格: V1 std=1元, pro=3.5元; V1.5/V1.6 std=2元, pro=3.5元
func TestKlingPricing_VideoExtend(t *testing.T) {
	adaptor := &TaskAdaptor{}
	gin.SetMode(gin.TestMode)

	// 视频延长按次计费，不按时长
	// 需要特殊配置使最终价格正确

	tests := []struct {
		name          string
		model         string
		mode          string
		expectedScale float64
		description   string
	}{
		{
			name:          "V1 Std",
			model:         "kling-v1",
			mode:          "std",
			expectedScale: 1.0, // V1 std 基准倍率
			description:   "V1 视频延长 Std = 1元/次",
		},
		{
			name:          "V1 Pro",
			model:         "kling-v1",
			mode:          "pro",
			expectedScale: 1.0 * 3.5, // V1 pro/std = 3.5
			description:   "V1 视频延长 Pro = 3.5元/次",
		},
		{
			name:          "V1.5 Std",
			model:         "kling-v1-5",
			mode:          "std",
			expectedScale: 2.0, // V1.5 std = 2元
			description:   "V1.5 视频延长 Std = 2元/次",
		},
		{
			name:          "V1.5 Pro",
			model:         "kling-v1-5",
			mode:          "pro",
			expectedScale: 2.0 * 1.75, // V1.5 pro/std = 1.75
			description:   "V1.5 视频延长 Pro = 3.5元/次",
		},
		{
			name:          "V1.6 Std",
			model:         "kling-v1-6",
			mode:          "std",
			expectedScale: 2.0, // V1.6 std = 2元
			description:   "V1.6 视频延长 Std = 2元/次",
		},
		{
			name:          "V1.6 Pro",
			model:         "kling-v1-6",
			mode:          "pro",
			expectedScale: 2.0 * 1.75, // V1.6 pro/std = 1.75
			description:   "V1.6 视频延长 Pro = 3.5元/次",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c, _ := gin.CreateTestContext(httptest.NewRecorder())
			req := relaycommon.TaskSubmitReq{
				Model: tt.model,
				Mode:  tt.mode,
				Metadata: map[string]interface{}{
					"video_id": "test_video_id",
				},
			}
			c.Set("task_request", req)
			c.Set("action", constant.TaskActionVideoExtend)

			info := &relaycommon.RelayInfo{
				TaskRelayInfo: &relaycommon.TaskRelayInfo{
					Action: constant.TaskActionVideoExtend,
				},
			}

			got, err := adaptor.GetPriceScale(c, info)
			assert.NoError(t, err, tt.description)
			assert.InDelta(t, tt.expectedScale, float64(got), 0.01, tt.description)
		})
	}
}

// TestKlingPricing_AdvancedLipSync 对口型计费测试
// 官方价格: 每5秒0.5元，不足5秒按5秒计算
func TestKlingPricing_AdvancedLipSync(t *testing.T) {
	adaptor := &TaskAdaptor{}
	gin.SetMode(gin.TestMode)

	tests := []struct {
		name           string
		audioDurationMs int64  // 音频时长（毫秒）
		expectedScale  float64
		expectedPrice  float64 // 预期价格（元）
		description    string
	}{
		{
			name:            "3秒音频",
			audioDurationMs: 3000,
			expectedScale:   0.5, // 不足5秒按5秒计，1单位 × 0.5
			expectedPrice:   0.5,
			description:     "3秒音频 → 1单位 × 0.5元 = 0.5元",
		},
		{
			name:            "5秒音频",
			audioDurationMs: 5000,
			expectedScale:   0.5, // 1单位 × 0.5
			expectedPrice:   0.5,
			description:     "5秒音频 → 1单位 × 0.5元 = 0.5元",
		},
		{
			name:            "7秒音频",
			audioDurationMs: 7000,
			expectedScale:   1.0, // 向上取整到2单位 × 0.5
			expectedPrice:   1.0,
			description:     "7秒音频 → 2单位 × 0.5元 = 1.0元",
		},
		{
			name:            "10秒音频",
			audioDurationMs: 10000,
			expectedScale:   1.0, // 2单位 × 0.5
			expectedPrice:   1.0,
			description:     "10秒音频 → 2单位 × 0.5元 = 1.0元",
		},
		{
			name:            "12秒音频",
			audioDurationMs: 12000,
			expectedScale:   1.5, // 向上取整到3单位 × 0.5
			expectedPrice:   1.5,
			description:     "12秒音频 → 3单位 × 0.5元 = 1.5元",
		},
		{
			name:            "25秒音频",
			audioDurationMs: 25000,
			expectedScale:   2.5, // 5单位 × 0.5
			expectedPrice:   2.5,
			description:     "25秒音频 → 5单位 × 0.5元 = 2.5元",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c, _ := gin.CreateTestContext(httptest.NewRecorder())
			req := relaycommon.TaskSubmitReq{
				Model: "kling-v1-6",
				Metadata: map[string]interface{}{
					"session_id": "test_session_id", // 必填字段
					"face_choose": []interface{}{
						map[string]interface{}{
							"face_id":           "face_1",
							"audio_id":          "audio_1",
							"sound_start_time":  int64(0),
							"sound_end_time":    tt.audioDurationMs,
							"sound_insert_time": int64(0),
						},
					},
				},
			}
			c.Set("task_request", req)
			c.Set("action", constant.TaskActionAdvancedLipSync)

			info := &relaycommon.RelayInfo{
				TaskRelayInfo: &relaycommon.TaskRelayInfo{
					Action: constant.TaskActionAdvancedLipSync,
				},
			}

			got, err := adaptor.GetPriceScale(c, info)
			assert.NoError(t, err, tt.description)
			assert.InDelta(t, tt.expectedScale, float64(got), 0.01, tt.description)
		})
	}
}

// TestKlingPricing_MultiElements 多模态视频编辑计费测试
// 官方价格: std 5s=3元, 10s=6元; pro 5s=5元, 10s=10元
func TestKlingPricing_MultiElements(t *testing.T) {
	adaptor := &TaskAdaptor{}
	gin.SetMode(gin.TestMode)

	// 多模态编辑 Std 每秒 = 0.6元
	// Pro/Std 倍率 = 5/3 ≈ 1.667

	tests := []struct {
		name          string
		mode          string
		duration      string
		expectedScale float64
		description   string
	}{
		{
			name:          "Std 5s",
			mode:          "std",
			duration:      "5",
			expectedScale: 5.0 * 1.0, // 5s × 1.0
			description:   "多模态编辑 Std 5s",
		},
		{
			name:          "Std 10s",
			mode:          "std",
			duration:      "10",
			expectedScale: 10.0 * 1.0, // 10s × 1.0
			description:   "多模态编辑 Std 10s",
		},
		{
			name:          "Pro 5s",
			mode:          "pro",
			duration:      "5",
			expectedScale: 5.0 * (5.0 / 3.0), // 5s × 1.667 ≈ 8.33
			description:   "多模态编辑 Pro 5s",
		},
		{
			name:          "Pro 10s",
			mode:          "pro",
			duration:      "10",
			expectedScale: 10.0 * (5.0 / 3.0), // 10s × 1.667 ≈ 16.67
			description:   "多模态编辑 Pro 10s",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c, _ := gin.CreateTestContext(httptest.NewRecorder())
			req := relaycommon.TaskSubmitReq{
				Model:  "kling-v1-6",
				Mode:   tt.mode,
				Prompt: "test multi elements prompt", // 必填字段
				Metadata: map[string]interface{}{
					"session_id": "test_session",
					"duration":   tt.duration,
					"edit_mode":  "removal", // 必填字段，removal 模式不需要 image_list
				},
			}
			c.Set("task_request", req)
			c.Set("action", constant.TaskActionMultiElementsCreate)

			info := &relaycommon.RelayInfo{
				TaskRelayInfo: &relaycommon.TaskRelayInfo{
					Action: constant.TaskActionMultiElementsCreate,
				},
			}

			got, err := adaptor.GetPriceScale(c, info)
			assert.NoError(t, err, tt.description)
			assert.InDelta(t, tt.expectedScale, float64(got), 0.01, tt.description)
		})
	}
}

// TestKlingPricing_MotionControl 动作控制计费测试
func TestKlingPricing_MotionControl(t *testing.T) {
	adaptor := &TaskAdaptor{}
	gin.SetMode(gin.TestMode)

	// 动作控制 Pro/Std 倍率 = 1.6
	// 预扣时长: image=10s, video=30s

	tests := []struct {
		name          string
		mode          string
		orientation   string
		expectedScale float64
		description   string
	}{
		{
			name:          "Image Std",
			mode:          "std",
			orientation:   "image",
			expectedScale: 10.0 * 1.0, // 10s × 1.0
			description:   "动作控制 Image Std 预扣10s",
		},
		{
			name:          "Image Pro",
			mode:          "pro",
			orientation:   "image",
			expectedScale: 10.0 * 1.6, // 10s × 1.6 = 16
			description:   "动作控制 Image Pro 预扣10s × 1.6",
		},
		{
			name:          "Video Std",
			mode:          "std",
			orientation:   "video",
			expectedScale: 30.0 * 1.0, // 30s × 1.0
			description:   "动作控制 Video Std 预扣30s",
		},
		{
			name:          "Video Pro",
			mode:          "pro",
			orientation:   "video",
			expectedScale: 30.0 * 1.6, // 30s × 1.6 = 48
			description:   "动作控制 Video Pro 预扣30s × 1.6",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c, _ := gin.CreateTestContext(httptest.NewRecorder())
			req := relaycommon.TaskSubmitReq{
				Model: "kling-v2-6",
				Mode:  tt.mode,
				Metadata: map[string]interface{}{
					"character_orientation": tt.orientation,
				},
			}
			c.Set("task_request", req)
			c.Set("action", constant.TaskActionMotionControl)

			info := &relaycommon.RelayInfo{
				TaskRelayInfo: &relaycommon.TaskRelayInfo{
					Action: constant.TaskActionMotionControl,
				},
			}

			got, err := adaptor.GetPriceScale(c, info)
			assert.NoError(t, err, tt.description)
			assert.InDelta(t, tt.expectedScale, float64(got), 0.01, tt.description)
		})
	}
}

// TestKlingPricing_FreeActions 免费操作测试
// 验证辅助操作不扣费
func TestKlingPricing_FreeActions(t *testing.T) {
	adaptor := &TaskAdaptor{}
	gin.SetMode(gin.TestMode)

	freeActions := []struct {
		name   string
		action string
	}{
		{"多模态编辑-初始化", constant.TaskActionMultiElementsInit},
		{"多模态编辑-增加选区", constant.TaskActionMultiElementsAddSelection},
		{"多模态编辑-删减选区", constant.TaskActionMultiElementsDeleteSelection},
		{"多模态编辑-清除选区", constant.TaskActionMultiElementsClearSelection},
		{"多模态编辑-预览", constant.TaskActionMultiElementsPreview},
		// 注意：人脸识别不再免费，已移至收费测试
	}

	for _, tt := range freeActions {
		t.Run(tt.name, func(t *testing.T) {
			c, _ := gin.CreateTestContext(httptest.NewRecorder())
			req := relaycommon.TaskSubmitReq{
				Model: "kling-v1-6",
			}
			c.Set("task_request", req)
			c.Set("action", tt.action)

			info := &relaycommon.RelayInfo{
				TaskRelayInfo: &relaycommon.TaskRelayInfo{
					Action: tt.action,
				},
			}

			got, err := adaptor.GetPriceScale(c, info)
			assert.NoError(t, err)
			assert.Equal(t, float32(0), got, "免费操作 %s 应返回0", tt.name)
		})
	}
}

// TestKlingPricing_AdvancedFeatures 高级功能附加倍率测试
// 验证音频、音色控制、视频输入等附加倍率
func TestKlingPricing_AdvancedFeatures(t *testing.T) {
	adaptor := &TaskAdaptor{}
	gin.SetMode(gin.TestMode)

	tests := []struct {
		name          string
		model         string
		mode          string
		action        string
		metadata      map[string]interface{}
		prompt        string
		expectedScale float64
		description   string
	}{
		{
			name:   "V2.6 开启音频",
			model:  "kling-v2-6",
			mode:   "std",
			action: constant.TaskActionGenerate,
			metadata: map[string]interface{}{
				"sound": "on",
			},
			expectedScale: 5.0 * 1.0 * 2.0, // 5s × modeScale(1.0) × soundScale(2.0)
			description:   "V2.6 Std + 音频: 5s × 2.0 = 10",
		},
		{
			name:   "V2.6 开启音频+音色控制",
			model:  "kling-v2-6",
			mode:   "std",
			action: constant.TaskActionGenerate,
			metadata: map[string]interface{}{
				"sound":      "on",
				"voice_list": []interface{}{map[string]interface{}{"voice_id": "v1"}},
			},
			prompt:        "hello <<<voice_1>>>",
			expectedScale: 5.0 * 1.0 * 2.0 * 1.2, // 5s × 1.0 × 2.0 × 1.2 = 12
			description:   "V2.6 Std + 音频 + 音色: 5s × 2.0 × 1.2 = 12",
		},
		{
			name:   "O1 带视频输入 Std",
			model:  "kling-video-o1",
			mode:   "std",
			action: constant.TaskActionOmniVideo,
			metadata: map[string]interface{}{
				"video_list": []interface{}{
					map[string]interface{}{"video_url": "test.mp4"},
				},
			},
			expectedScale: 5.0 * 1.0 * (0.126 / 0.084), // 5s × 1.0 × 1.5 = 7.5
			description:   "O1 Std + 视频输入: 5s × 1.5 = 7.5",
		},
		{
			name:   "O1 带视频输入 Pro",
			model:  "kling-video-o1",
			mode:   "pro",
			action: constant.TaskActionOmniVideo,
			metadata: map[string]interface{}{
				"video_list": []interface{}{
					map[string]interface{}{"video_url": "test.mp4"},
				},
			},
			expectedScale: 5.0 * (0.112 / 0.084) * (0.126 / 0.084), // 5s × 1.333 × 1.5 = 10
			description:   "O1 Pro + 视频输入: 5s × 1.333 × 1.5 = 10",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c, _ := gin.CreateTestContext(httptest.NewRecorder())
			req := relaycommon.TaskSubmitReq{
				Model:    tt.model,
				Mode:     tt.mode,
				Prompt:   tt.prompt,
				Metadata: tt.metadata,
			}
			c.Set("task_request", req)
			c.Set("action", tt.action)

			info := &relaycommon.RelayInfo{
				TaskRelayInfo: &relaycommon.TaskRelayInfo{
					Action: tt.action,
				},
			}

			got, err := adaptor.GetPriceScale(c, info)
			assert.NoError(t, err, tt.description)
			assert.InDelta(t, tt.expectedScale, float64(got), 0.01, tt.description)
		})
	}
}

// TestKlingPricing_OfficialPriceVerification 官方价格完整验证
// 综合测试：验证配置正确的 ModelPrice 后，计算结果与官方价格一致
func TestKlingPricing_OfficialPriceVerification(t *testing.T) {
	// 这个测试验证：当 ModelPrice 配置正确时，最终价格与官方一致
	
	type priceCase struct {
		name          string
		action        string
		model         string
		mode          string
		duration      int
		metadata      map[string]interface{}
		prompt        string  // 提示词（某些接口必填）
		modelPrice    float64 // 配置的 ModelPrice
		officialPrice float64 // 官方价格
	}

	// 系统使用内部计价单位: ModelPrice = 官方价格 × 0.14
	// 验证: 计算价格 = ModelPrice × PriceScale, 还原官方价格 = 计算价格 / 0.14
	const priceRatio = 0.14 // 内部计价单位与官方价格的比例

	cases := []priceCase{
		// ========== 普通视频 V1 ==========
		// 官方价格: Std 5s=1元, 10s=2元; Pro 5s=3.5元, 10s=7元
		{"普通视频 V1 Std 5s", constant.TaskActionGenerate, "kling-v1", "std", 5, nil, "", 0.028, 1.0 * priceRatio},
		{"普通视频 V1 Std 10s", constant.TaskActionGenerate, "kling-v1", "std", 10, nil, "", 0.028, 2.0 * priceRatio},
		{"普通视频 V1 Pro 5s", constant.TaskActionGenerate, "kling-v1", "pro", 5, nil, "", 0.028, 3.5 * priceRatio},
		{"普通视频 V1 Pro 10s", constant.TaskActionGenerate, "kling-v1", "pro", 10, nil, "", 0.028, 7.0 * priceRatio},

		// ========== 普通视频 V1.6 ==========
		// 官方价格: Std 5s=2元, 10s=4元; Pro 5s=3.5元, 10s=7元
		{"普通视频 V1.6 Std 5s", constant.TaskActionGenerate, "kling-v1-6", "std", 5, nil, "", 0.056, 2.0 * priceRatio},
		{"普通视频 V1.6 Std 10s", constant.TaskActionGenerate, "kling-v1-6", "std", 10, nil, "", 0.056, 4.0 * priceRatio},
		{"普通视频 V1.6 Pro 5s", constant.TaskActionGenerate, "kling-v1-6", "pro", 5, nil, "", 0.056, 3.5 * priceRatio},
		{"普通视频 V1.6 Pro 10s", constant.TaskActionGenerate, "kling-v1-6", "pro", 10, nil, "", 0.056, 7.0 * priceRatio},

		// ========== 普通视频 V2.5-turbo ==========
		// 官方价格: Std 5s=1.5元, 10s=3元; Pro 5s=2.5元, 10s=5元
		{"普通视频 V2.5-turbo Std 5s", constant.TaskActionGenerate, "kling-v2-5-turbo", "std", 5, nil, "", 0.042, 1.5 * priceRatio},
		{"普通视频 V2.5-turbo Pro 5s", constant.TaskActionGenerate, "kling-v2-5-turbo", "pro", 5, nil, "", 0.042, 2.5 * priceRatio},

		// ========== 普通视频 V2.6 ==========
		// 官方价格: Pro 5s 无声=2.5元, 有声=5元, 有声+音色=6元
		{"普通视频 V2.6 Pro 5s 无声", constant.TaskActionGenerate, "kling-v2-6", "pro", 5, nil, "", 0.07, 2.5 * priceRatio},
		{"普通视频 V2.6 Pro 5s 有声", constant.TaskActionGenerate, "kling-v2-6", "pro", 5,
			map[string]interface{}{"sound": "on"}, "", 0.07, 5.0 * priceRatio},
		{"普通视频 V2.6 Pro 5s 有声+音色", constant.TaskActionGenerate, "kling-v2-6", "pro", 5,
			map[string]interface{}{"sound": "on", "voice_list": []interface{}{map[string]interface{}{"voice_id": "v1"}}},
			"hello <<<voice_1>>>", 0.07, 6.0 * priceRatio},

		// ========== Video-O1 模型 ==========
		// 官方价格: Std 无视频 每秒0.6元, 有视频 每秒0.9元; Pro 无视频 每秒0.8元, 有视频 每秒1.2元
		{"Video-O1 Std 5s 无视频", constant.TaskActionOmniVideo, "kling-video-o1", "std", 5, nil, "", 0.084, 3.0 * priceRatio},
		{"Video-O1 Std 5s 有视频", constant.TaskActionOmniVideo, "kling-video-o1", "std", 5,
			map[string]interface{}{"video_list": []interface{}{map[string]interface{}{"video_url": "test.mp4"}}},
			"", 0.084, 4.5 * priceRatio},
		{"Video-O1 Pro 5s 无视频", constant.TaskActionOmniVideo, "kling-video-o1", "pro", 5, nil, "", 0.084, 4.0 * priceRatio},
		{"Video-O1 Pro 5s 有视频", constant.TaskActionOmniVideo, "kling-video-o1", "pro", 5,
			map[string]interface{}{"video_list": []interface{}{map[string]interface{}{"video_url": "test.mp4"}}},
			"", 0.084, 6.0 * priceRatio},

		// ========== Master 模型 ==========
		// 官方价格: 5s=10元, 10s=20元
		{"Master V2.0 5s", constant.TaskActionGenerate, "kling-v2-master", "master", 5, nil, "", 0.28, 10.0 * priceRatio},
		{"Master V2.0 10s", constant.TaskActionGenerate, "kling-v2-master", "master", 10, nil, "", 0.28, 20.0 * priceRatio},
		{"Master V2.1 5s", constant.TaskActionGenerate, "kling-v2-1-master", "master", 5, nil, "", 0.28, 10.0 * priceRatio},

		// ========== 多图参考生视频 V1.6 ==========
		// 官方价格: Std 5s=2元, 10s=4元; Pro 5s=3.5元, 10s=7元 (与普通V1.6相同)
		{"多图生视频 V1.6 Std 5s", constant.TaskActionMultiImage2Video, "kling-v1-6", "std", 5,
			map[string]interface{}{"duration": "5", "image_list": []interface{}{map[string]interface{}{"image": "https://example.com/img.jpg"}}},
			"test multi image prompt", 0.056, 2.0 * priceRatio},
		{"多图生视频 V1.6 Std 10s", constant.TaskActionMultiImage2Video, "kling-v1-6", "std", 10,
			map[string]interface{}{"duration": "10", "image_list": []interface{}{map[string]interface{}{"image": "https://example.com/img.jpg"}}},
			"test multi image prompt", 0.056, 4.0 * priceRatio},
		{"多图生视频 V1.6 Pro 5s", constant.TaskActionMultiImage2Video, "kling-v1-6", "pro", 5,
			map[string]interface{}{"duration": "5", "image_list": []interface{}{map[string]interface{}{"image": "https://example.com/img.jpg"}}},
			"test multi image prompt", 0.056, 3.5 * priceRatio},
		{"多图生视频 V1.6 Pro 10s", constant.TaskActionMultiImage2Video, "kling-v1-6", "pro", 10,
			map[string]interface{}{"duration": "10", "image_list": []interface{}{map[string]interface{}{"image": "https://example.com/img.jpg"}}},
			"test multi image prompt", 0.056, 7.0 * priceRatio},

		// ========== 多模态视频编辑 ==========
		// 官方价格: Std 5s=3元, 10s=6元; Pro 5s=5元, 10s=10元
		// 多模态编辑使用独立的计价，ModelPrice=0.056 (V1.6基准)，需要额外倍率
		// Std 每秒 0.6元 = 0.056 × scale → scale = 0.6/0.056/0.14 ≈ 76.53 (不合理)
		// 实际应该用专用 ModelPrice 或直接返回价格
		// 当前实现: PriceScale = duration × modeScale, 需要 ModelPrice = 0.6×0.14 = 0.084
		{"多模态编辑 Std 5s", constant.TaskActionMultiElementsCreate, "kling-v1-6", "std", 5,
			map[string]interface{}{"session_id": "test_session", "duration": "5", "edit_mode": "removal"},
			"test multi elements prompt", 0.084, 3.0 * priceRatio},
		{"多模态编辑 Std 10s", constant.TaskActionMultiElementsCreate, "kling-v1-6", "std", 10,
			map[string]interface{}{"session_id": "test_session", "duration": "10", "edit_mode": "removal"},
			"test multi elements prompt", 0.084, 6.0 * priceRatio},
		{"多模态编辑 Pro 5s", constant.TaskActionMultiElementsCreate, "kling-v1-6", "pro", 5,
			map[string]interface{}{"session_id": "test_session", "duration": "5", "edit_mode": "removal"},
			"test multi elements prompt", 0.084, 5.0 * priceRatio},
		{"多模态编辑 Pro 10s", constant.TaskActionMultiElementsCreate, "kling-v1-6", "pro", 10,
			map[string]interface{}{"session_id": "test_session", "duration": "10", "edit_mode": "removal"},
			"test multi elements prompt", 0.084, 10.0 * priceRatio},

		// ========== V2.6 动作控制 ==========
		// 官方价格: Std 每秒0.5元, Pro 每秒0.8元
		// ModelPrice = 0.07 (V2.6), 需要验证动作控制的倍率
		{"动作控制 Std 10s", constant.TaskActionMotionControl, "kling-v2-6", "std", 0,
			map[string]interface{}{"character_orientation": "image"},
			"", 0.07, 5.0 * priceRatio}, // 10s × 0.5元/s = 5元
		{"动作控制 Pro 10s", constant.TaskActionMotionControl, "kling-v2-6", "pro", 0,
			map[string]interface{}{"character_orientation": "image"},
			"", 0.07, 8.0 * priceRatio}, // 10s × 0.8元/s = 8元

		// ========== 视频延长 ==========
		// 官方价格: V1 std=1元, pro=3.5元; V1.5/V1.6 std=2元, pro=3.5元
		// 视频延长按次计费，PriceScale 直接返回倍率
		{"视频延长 V1 Std", constant.TaskActionVideoExtend, "kling-v1", "std", 0,
			map[string]interface{}{"video_id": "test_video"},
			"", 0.14, 1.0 * priceRatio}, // ModelPrice=0.14 使 1×scale=官方价格×0.14
		{"视频延长 V1 Pro", constant.TaskActionVideoExtend, "kling-v1", "pro", 0,
			map[string]interface{}{"video_id": "test_video"},
			"", 0.14, 3.5 * priceRatio},
		{"视频延长 V1.6 Std", constant.TaskActionVideoExtend, "kling-v1-6", "std", 0,
			map[string]interface{}{"video_id": "test_video"},
			"", 0.14, 2.0 * priceRatio},
		{"视频延长 V1.6 Pro", constant.TaskActionVideoExtend, "kling-v1-6", "pro", 0,
			map[string]interface{}{"video_id": "test_video"},
			"", 0.14, 3.5 * priceRatio},

		// ========== 对口型 ==========
		// 官方价格: 每5秒0.5元，不足5秒按5秒计算
		// PriceScale 直接返回价格倍率 (units × 0.5)
		{"对口型 5秒音频", constant.TaskActionAdvancedLipSync, "kling-v1-6", "", 0,
			map[string]interface{}{
				"session_id": "test_session",
				"face_choose": []interface{}{
					map[string]interface{}{
						"face_id": "face_1", "audio_id": "audio_1",
						"sound_start_time": int64(0), "sound_end_time": int64(5000), "sound_insert_time": int64(0),
					},
				},
			},
			"", 0.14, 0.5 * priceRatio}, // 1单位 × 0.5元 = 0.5元
		{"对口型 10秒音频", constant.TaskActionAdvancedLipSync, "kling-v1-6", "", 0,
			map[string]interface{}{
				"session_id": "test_session",
				"face_choose": []interface{}{
					map[string]interface{}{
						"face_id": "face_1", "audio_id": "audio_1",
						"sound_start_time": int64(0), "sound_end_time": int64(10000), "sound_insert_time": int64(0),
					},
				},
			},
			"", 0.14, 1.0 * priceRatio}, // 2单位 × 0.5元 = 1.0元
		{"对口型 25秒音频", constant.TaskActionAdvancedLipSync, "kling-v1-6", "", 0,
			map[string]interface{}{
				"session_id": "test_session",
				"face_choose": []interface{}{
					map[string]interface{}{
						"face_id": "face_1", "audio_id": "audio_1",
						"sound_start_time": int64(0), "sound_end_time": int64(25000), "sound_insert_time": int64(0),
					},
				},
			},
			"", 0.14, 2.5 * priceRatio}, // 5单位 × 0.5元 = 2.5元

		// ========== 人脸识别 ==========
		// 官方价格: 每次0.05元
		// PriceScale = 0.05/0.14 ≈ 0.357, 计算价格 = 0.14 × 0.357 ≈ 0.05
		{"人脸识别", constant.TaskActionIdentifyFace, "kling-v1-6", "", 0,
			map[string]interface{}{"video_url": "https://example.com/video.mp4"},
			"", 0.14, 0.05}, // 0.05元/次 (直接验证最终价格)
	}

	adaptor := &TaskAdaptor{}
	gin.SetMode(gin.TestMode)

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			c, _ := gin.CreateTestContext(httptest.NewRecorder())
			req := relaycommon.TaskSubmitReq{
				Model:    tc.model,
				Mode:     tc.mode,
				Duration: tc.duration,
				Metadata: tc.metadata,
				Prompt:   tc.prompt,
			}
			c.Set("task_request", req)
			c.Set("action", tc.action)

			info := &relaycommon.RelayInfo{
				TaskRelayInfo: &relaycommon.TaskRelayInfo{
					Action: tc.action,
				},
			}

			priceScale, err := adaptor.GetPriceScale(c, info)
			assert.NoError(t, err)

			// 计算最终价格
			calculatedPrice := tc.modelPrice * float64(priceScale)
			
			// 验证与官方价格一致（允许0.01误差）
			assert.InDelta(t, tc.officialPrice, calculatedPrice, 0.01,
				"%s: 计算价格=%.2f, 官方价格=%.2f, PriceScale=%.2f",
				tc.name, calculatedPrice, tc.officialPrice, priceScale)
		})
	}
}

// TestKlingPricing_ProScaleMap 验证 Pro 模式倍率表
func TestKlingPricing_ProScaleMap(t *testing.T) {
	// 验证 proScaleMap 中的倍率是否正确
	expectedProScales := map[string]float64{
		"kling-video-o1":   0.112 / 0.084, // 1.333
		"kling-v2-6":       0.07 / 0.07,   // 1.0
		"kling-v2-5-turbo": 0.07 / 0.042,  // 1.667
		"kling-v2-1":       0.098 / 0.056, // 1.75
		"kling-v1-6":       0.098 / 0.056, // 1.75
		"kling-v1-5":       0.098 / 0.056, // 1.75
		"kling-v1":         0.098 / 0.028, // 3.5
	}

	for model, expectedScale := range expectedProScales {
		t.Run(model, func(t *testing.T) {
			actualScale, ok := proScaleMap[model]
			assert.True(t, ok, "模型 %s 应存在于 proScaleMap", model)
			assert.InDelta(t, expectedScale, actualScale, 0.001,
				"模型 %s 的 Pro 倍率不正确: 期望=%.3f, 实际=%.3f",
				model, expectedScale, actualScale)
		})
	}
}

// TestKlingPricing_LipSyncUnits 对口型计费单位计算测试
func TestKlingPricing_LipSyncUnits(t *testing.T) {
	// 验证对口型的计费单位计算逻辑
	// 每5秒一个单位，不足5秒按5秒计算
	
	testCases := []struct {
		durationSec   float64
		expectedUnits float64
	}{
		{1.0, 1.0},   // 1秒 → 1单位
		{4.9, 1.0},   // 4.9秒 → 1单位
		{5.0, 1.0},   // 5秒 → 1单位
		{5.1, 2.0},   // 5.1秒 → 2单位
		{10.0, 2.0},  // 10秒 → 2单位
		{10.1, 3.0},  // 10.1秒 → 3单位
		{25.0, 5.0},  // 25秒 → 5单位
		{60.0, 12.0}, // 60秒 → 12单位
	}

	for _, tc := range testCases {
		t.Run("", func(t *testing.T) {
			// 模拟计费逻辑
			totalDurationSec := tc.durationSec
			if totalDurationSec < advancedLipSyncUnitSeconds {
				totalDurationSec = advancedLipSyncUnitSeconds
			}
			units := math.Ceil(totalDurationSec / advancedLipSyncUnitSeconds)
			
			assert.Equal(t, tc.expectedUnits, units,
				"%.1f秒应计算为%.0f个单位", tc.durationSec, tc.expectedUnits)
		})
	}
}
