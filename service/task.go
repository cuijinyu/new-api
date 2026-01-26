package service

import (
	"strings"

	"github.com/QuantumNous/new-api/constant"
)

func CoverTaskActionToModelName(platform constant.TaskPlatform, action string) string {
	return strings.ToLower(string(platform)) + "_" + strings.ToLower(action)
}

// GetBillingModelName 获取用于计费的模型名
// 某些特殊功能（如多模态编辑、视频延长、对口型）需要使用专用的 ModelPrice，
// 而不是使用原模型的 ModelPrice，因为它们的官方价格不同。
//
// 可灵特殊功能计费模型名：
//   - 多模态视频编辑: kling-multi-elements (官方价格: Std 0.6元/秒, Pro 1.0元/秒)
//   - 视频延长: kling-video-extend (官方价格: 按次计费)
//   - 对口型: kling-lip-sync (官方价格: 每5秒0.5元)
//   - 人脸识别: kling-identify-face (官方价格: 每次0.05元)
//   - 语音合成: kling-tts (官方价格: 每次0.05元)
func GetBillingModelName(platform constant.TaskPlatform, action string, originalModelName string) string {
	// 可灵平台特殊功能
	if platform == constant.TaskPlatformKling {
		switch action {
		case constant.TaskActionMultiElementsCreate:
			return "kling-multi-elements"
		case constant.TaskActionVideoExtend:
			return "kling-video-extend"
		case constant.TaskActionAdvancedLipSync:
			return "kling-lip-sync"
		case constant.TaskActionIdentifyFace:
			return "kling-identify-face"
		case constant.TaskActionTTS:
			return "kling-tts"
		}
	}

	// 其他情况使用原模型名
	return originalModelName
}
