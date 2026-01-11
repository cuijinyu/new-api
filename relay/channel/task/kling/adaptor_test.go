package kling

import (
	"net/http/httptest"
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
