package middleware

import (
	"bytes"
	"encoding/json"
	"io"
	"strings"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/constant"

	"github.com/gin-gonic/gin"
)

func KlingRequestConvert() func(c *gin.Context) {
	return func(c *gin.Context) {
		var originalReq map[string]interface{}
		if err := common.UnmarshalBodyReusable(c, &originalReq); err != nil {
			c.Next()
			return
		}

	// 判断任务类型（在重写路径之前检测原始路径）
	originalPath := c.Request.URL.Path
	isOmniVideo := strings.Contains(originalPath, "omni-video")
	isMotionControl := strings.Contains(originalPath, "motion-control")
	isMultiImage := strings.Contains(originalPath, "multi-image2video")
	isIdentifyFace := strings.Contains(originalPath, "identify-face")
	isAdvancedLipSync := strings.Contains(originalPath, "advanced-lip-sync")
	isVideoExtend := strings.Contains(originalPath, "video-extend")
	isTTS := strings.Contains(originalPath, "/audio/tts")

	// 多模态视频编辑端点识别
	isMultiElementsInit := strings.Contains(originalPath, "multi-elements/init-selection")
	isMultiElementsAddSelection := strings.Contains(originalPath, "multi-elements/add-selection")
	isMultiElementsDeleteSelection := strings.Contains(originalPath, "multi-elements/delete-selection")
	isMultiElementsClearSelection := strings.Contains(originalPath, "multi-elements/clear-selection")
	isMultiElementsPreview := strings.Contains(originalPath, "multi-elements/preview-selection")
	// 创建任务端点：POST /v1/videos/multi-elements/ (注意末尾有/)
	isMultiElementsCreate := strings.HasSuffix(originalPath, "multi-elements") || strings.HasSuffix(originalPath, "multi-elements/")

		// Support both model_name and model fields
		model, _ := originalReq["model_name"].(string)
		if model == "" {
			model, _ = originalReq["model"].(string)
		}

		// 对于不需要 model 的辅助接口，设置默认模型名称以便渠道路由
		// 这些接口本身不使用 model 参数，但 new-api 需要 model 来选择渠道
		if model == "" {
			if isTTS {
				model = "kling-tts" // TTS 专用模型，用于独立计费
			} else if isMultiElementsInit || isMultiElementsAddSelection || isMultiElementsDeleteSelection ||
				isMultiElementsClearSelection || isMultiElementsPreview ||
				isIdentifyFace || isAdvancedLipSync || isVideoExtend {
				model = "kling-v1-6" // 默认模型，用于渠道路由
			}
		}

		prompt, _ := originalReq["prompt"].(string)

		unifiedReq := map[string]interface{}{
			"model":    model,
			"prompt":   prompt,
			"metadata": originalReq,
		}

		jsonData, err := json.Marshal(unifiedReq)
		if err != nil {
			c.Next()
			return
		}

		// Rewrite request body and path
		c.Request.Body = io.NopCloser(bytes.NewBuffer(jsonData))
		c.Request.URL.Path = "/v1/video/generations"

		// 设置任务类型
		if isIdentifyFace {
			c.Set("action", constant.TaskActionIdentifyFace)
		} else if isAdvancedLipSync {
			c.Set("action", constant.TaskActionAdvancedLipSync)
		} else if isVideoExtend {
			c.Set("action", constant.TaskActionVideoExtend)
		} else if isTTS {
			c.Set("action", constant.TaskActionTTS)
		} else if isMultiElementsInit {
			c.Set("action", constant.TaskActionMultiElementsInit)
		} else if isMultiElementsAddSelection {
			c.Set("action", constant.TaskActionMultiElementsAddSelection)
		} else if isMultiElementsDeleteSelection {
			c.Set("action", constant.TaskActionMultiElementsDeleteSelection)
		} else if isMultiElementsClearSelection {
			c.Set("action", constant.TaskActionMultiElementsClearSelection)
		} else if isMultiElementsPreview {
			c.Set("action", constant.TaskActionMultiElementsPreview)
		} else if isMultiElementsCreate {
			c.Set("action", constant.TaskActionMultiElementsCreate)
		} else if isOmniVideo {
			c.Set("action", constant.TaskActionOmniVideo)
		} else if isMotionControl {
			c.Set("action", constant.TaskActionMotionControl)
		} else if isMultiImage {
			c.Set("action", constant.TaskActionMultiImage2Video)
		} else if image, ok := originalReq["image"]; !ok || image == "" {
			c.Set("action", constant.TaskActionTextGenerate)
		}

		// We have to reset the request body for the next handlers
		c.Set(common.KeyRequestBody, jsonData)
		c.Next()
	}
}
