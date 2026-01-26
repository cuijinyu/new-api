package router

import (
	"github.com/QuantumNous/new-api/controller"
	"github.com/QuantumNous/new-api/middleware"

	"github.com/gin-gonic/gin"
)

func SetVideoRouter(router *gin.Engine) {
	videoV1Router := router.Group("/v1")
	videoV1Router.Use(middleware.TokenAuth(), middleware.Distribute())
	{
		videoV1Router.GET("/videos/:task_id/content", controller.VideoProxy)
		videoV1Router.POST("/video/generations", controller.RelayTask)
		videoV1Router.GET("/video/generations/:task_id", controller.RelayTask)
	}
	// openai compatible API video routes
	// docs: https://platform.openai.com/docs/api-reference/videos/create
	{
		videoV1Router.POST("/videos", controller.RelayTask)
		videoV1Router.GET("/videos/:task_id", controller.RelayTask)
	}

	klingV1Router := router.Group("/kling/v1")
	klingV1Router.Use(middleware.KlingRequestConvert(), middleware.TokenAuth(), middleware.Distribute())
	{
		klingV1Router.POST("/videos/text2video", controller.RelayTask)
		klingV1Router.POST("/videos/image2video", controller.RelayTask)
		klingV1Router.POST("/videos/omni-video", controller.RelayTask)
		klingV1Router.POST("/videos/motion-control", controller.RelayTask)
		klingV1Router.POST("/videos/multi-image2video", controller.RelayTask)
		klingV1Router.GET("/videos/text2video/:task_id", controller.RelayTask)
		klingV1Router.GET("/videos/image2video/:task_id", controller.RelayTask)
		klingV1Router.GET("/videos/omni-video/:task_id", controller.RelayTask)
		klingV1Router.GET("/videos/motion-control/:task_id", controller.RelayTask)
		klingV1Router.GET("/videos/multi-image2video/:task_id", controller.RelayTask)
		// 对口型 (Lip-Sync) 端点
		klingV1Router.POST("/videos/identify-face", controller.RelayTask)
		klingV1Router.POST("/videos/advanced-lip-sync", controller.RelayTask)
		klingV1Router.GET("/videos/advanced-lip-sync/:task_id", controller.RelayTask)
		// 视频延长 (Video Extend) 端点
		klingV1Router.POST("/videos/video-extend", controller.RelayTask)
		klingV1Router.GET("/videos/video-extend/:task_id", controller.RelayTask)
		// 语音合成 (TTS) 端点
		klingV1Router.POST("/tts", controller.RelayTask)
		// 多模态视频编辑 (Multi-Elements) 端点
		klingV1Router.POST("/videos/multi-elements/init-selection", controller.RelayTask)    // 初始化待编辑视频
		klingV1Router.POST("/videos/multi-elements/add-selection", controller.RelayTask)     // 增加视频选区
		klingV1Router.POST("/videos/multi-elements/delete-selection", controller.RelayTask)  // 删减视频选区
		klingV1Router.POST("/videos/multi-elements/clear-selection", controller.RelayTask)   // 清除视频选区
		klingV1Router.POST("/videos/multi-elements/preview-selection", controller.RelayTask) // 预览已选区视频
		klingV1Router.POST("/videos/multi-elements", controller.RelayTask)                   // 创建多模态视频编辑任务
		klingV1Router.POST("/videos/multi-elements/", controller.RelayTask)                  // 创建多模态视频编辑任务（带斜杠）
		klingV1Router.GET("/videos/multi-elements/:task_id", controller.RelayTask)           // 查询多模态视频编辑任务
	}

	// Jimeng official API routes - direct mapping to official API format
	jimengOfficialGroup := router.Group("jimeng")
	jimengOfficialGroup.Use(middleware.JimengRequestConvert(), middleware.TokenAuth(), middleware.Distribute())
	{
		// Maps to: /?Action=CVSync2AsyncSubmitTask&Version=2022-08-31 and /?Action=CVSync2AsyncGetResult&Version=2022-08-31
		jimengOfficialGroup.POST("/", controller.RelayTask)
	}
}
