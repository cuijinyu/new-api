package constant

type TaskPlatform string

const (
	TaskPlatformSuno       TaskPlatform = "suno"
	TaskPlatformMidjourney TaskPlatform = "mj"
	TaskPlatformKling      TaskPlatform = "kling"
)

const (
	SunoActionMusic  = "MUSIC"
	SunoActionLyrics = "LYRICS"

	TaskActionGenerate          = "generate"
	TaskActionTextGenerate      = "textGenerate"
	TaskActionFirstTailGenerate = "firstTailGenerate"
	TaskActionReferenceGenerate = "referenceGenerate"
	TaskActionOmniVideo         = "omniVideo"
	TaskActionMotionControl     = "motionControl"
	TaskActionMultiImage2Video  = "multiImage2Video"
	TaskActionIdentifyFace      = "identifyFace"
	TaskActionAdvancedLipSync   = "advancedLipSync"
	TaskActionVideoExtend       = "videoExtend"
	TaskActionTTS               = "tts" // 语音合成 (Text-to-Speech)

	// 多模态视频编辑 (Multi-Elements) 相关 Action
	TaskActionMultiElementsInit           = "multiElementsInit"           // 初始化待编辑视频
	TaskActionMultiElementsAddSelection   = "multiElementsAddSelection"   // 增加视频选区
	TaskActionMultiElementsDeleteSelection = "multiElementsDeleteSelection" // 删减视频选区
	TaskActionMultiElementsClearSelection = "multiElementsClearSelection" // 清除视频选区
	TaskActionMultiElementsPreview        = "multiElementsPreview"        // 预览已选区视频
	TaskActionMultiElementsCreate         = "multiElementsCreate"         // 创建多模态视频编辑任务
	TaskActionMultiElementsQuery          = "multiElementsQuery"          // 查询多模态视频编辑任务
)

var SunoModel2Action = map[string]string{
	"suno_music":  SunoActionMusic,
	"suno_lyrics": SunoActionLyrics,
}
