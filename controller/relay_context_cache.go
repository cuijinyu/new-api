package controller

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/constant"
	"github.com/QuantumNous/new-api/dto"
	"github.com/QuantumNous/new-api/logger"
	"github.com/QuantumNous/new-api/model"
	relaycommon "github.com/QuantumNous/new-api/relay/common"
	relayconstant "github.com/QuantumNous/new-api/relay/constant"
	"github.com/QuantumNous/new-api/service"
	"github.com/QuantumNous/new-api/types"

	"github.com/gin-gonic/gin"
)

// RelayContextCacheCreate 创建上下文缓存
// POST /api/v3/context/create
func RelayContextCacheCreate(c *gin.Context) {
	requestId := c.GetString(common.RequestIdKey)

	// 解析请求
	var request dto.ContextCacheCreateRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": types.NewOpenAIError(
				errors.New(common.MessageWithRequestId("Invalid request body: "+err.Error(), requestId)),
				types.ErrorCodeBadRequestBody,
				http.StatusBadRequest,
			).ToOpenAIError(),
		})
		return
	}

	// 验证必要参数
	if request.Model == "" {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": types.NewOpenAIError(
				errors.New(common.MessageWithRequestId("model is required", requestId)),
				types.ErrorCodeBadRequestBody,
				http.StatusBadRequest,
			).ToOpenAIError(),
		})
		return
	}

	if len(request.Messages) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": types.NewOpenAIError(
				errors.New(common.MessageWithRequestId("messages is required", requestId)),
				types.ErrorCodeBadRequestBody,
				http.StatusBadRequest,
			).ToOpenAIError(),
		})
		return
	}

	// 设置默认值
	if request.Mode == "" {
		request.Mode = "session"
	}
	if request.TTL == 0 {
		request.TTL = 86400 // 默认 24 小时
	}

	// 获取渠道信息
	channel, err := getChannelForContextCache(c, request.Model)
	if err != nil {
		logger.LogError(c, fmt.Sprintf("Failed to get channel for model %s: %v", request.Model, err))
		c.JSON(http.StatusBadRequest, gin.H{
			"error": types.NewOpenAIError(
				errors.New(common.MessageWithRequestId(err.Error(), requestId)),
				types.ErrorCodeGetChannelFailed,
				http.StatusBadRequest,
			).ToOpenAIError(),
		})
		return
	}
	logger.LogInfo(c, fmt.Sprintf("Got channel %d (%s) for model %s", channel.Id, channel.Name, request.Model))

	// 构建 relay info
	info := buildContextCacheRelayInfo(c, channel, request.Model, relayconstant.RelayModeContextCacheCreate)
	
	// 转发请求到上游
	resp, apiErr := forwardContextCacheRequest(c, info, &request, "/api/v3/context/create")
	if apiErr != nil {
		logger.LogError(c, fmt.Sprintf("context cache create error: %s", apiErr.Error()))
		c.JSON(apiErr.StatusCode, gin.H{
			"error": apiErr.ToOpenAIError(),
		})
		return
	}
	defer resp.Body.Close()

	// 读取响应
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": types.NewOpenAIError(
				errors.New(common.MessageWithRequestId("Failed to read response: "+err.Error(), requestId)),
				types.ErrorCodeReadResponseBodyFailed,
				http.StatusInternalServerError,
			).ToOpenAIError(),
		})
		return
	}

	// 检查响应状态
	if resp.StatusCode != http.StatusOK {
		c.Data(resp.StatusCode, resp.Header.Get("Content-Type"), body)
		return
	}

	// 解析并返回响应
	var response dto.ContextCacheCreateResponse
	if err := json.Unmarshal(body, &response); err != nil {
		// 如果解析失败，直接返回原始响应
		c.Data(resp.StatusCode, resp.Header.Get("Content-Type"), body)
		return
	}

	c.JSON(http.StatusOK, response)
}

// RelayContextCacheChat 使用上下文缓存进行对话
// POST /api/v3/context/chat/completions
func RelayContextCacheChat(c *gin.Context) {
	requestId := c.GetString(common.RequestIdKey)

	// 解析请求
	var request dto.ContextCacheChatRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": types.NewOpenAIError(
				errors.New(common.MessageWithRequestId("Invalid request body: "+err.Error(), requestId)),
				types.ErrorCodeBadRequestBody,
				http.StatusBadRequest,
			).ToOpenAIError(),
		})
		return
	}

	// 验证必要参数
	if request.Model == "" {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": types.NewOpenAIError(
				errors.New(common.MessageWithRequestId("model is required", requestId)),
				types.ErrorCodeBadRequestBody,
				http.StatusBadRequest,
			).ToOpenAIError(),
		})
		return
	}

	if request.ContextID == "" {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": types.NewOpenAIError(
				errors.New(common.MessageWithRequestId("context_id is required", requestId)),
				types.ErrorCodeBadRequestBody,
				http.StatusBadRequest,
			).ToOpenAIError(),
		})
		return
	}

	// 获取渠道信息
	channel, err := getChannelForContextCache(c, request.Model)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": types.NewOpenAIError(
				errors.New(common.MessageWithRequestId(err.Error(), requestId)),
				types.ErrorCodeGetChannelFailed,
				http.StatusBadRequest,
			).ToOpenAIError(),
		})
		return
	}

	// 构建 relay info
	info := buildContextCacheRelayInfo(c, channel, request.Model, relayconstant.RelayModeContextCacheChat)
	info.IsStream = request.IsStream()

	// 转发请求到上游
	resp, apiErr := forwardContextCacheRequest(c, info, &request, "/api/v3/context/chat/completions")
	if apiErr != nil {
		logger.LogError(c, fmt.Sprintf("context cache chat error: %s", apiErr.Error()))
		c.JSON(apiErr.StatusCode, gin.H{
			"error": apiErr.ToOpenAIError(),
		})
		return
	}
	defer resp.Body.Close()

	// 处理流式响应
	if request.IsStream() {
		handleContextCacheStreamResponse(c, resp)
		return
	}

	// 读取非流式响应
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": types.NewOpenAIError(
				errors.New(common.MessageWithRequestId("Failed to read response: "+err.Error(), requestId)),
				types.ErrorCodeReadResponseBodyFailed,
				http.StatusInternalServerError,
			).ToOpenAIError(),
		})
		return
	}

	// 返回响应
	c.Data(resp.StatusCode, resp.Header.Get("Content-Type"), body)
}

// getChannelForContextCache 获取用于上下文缓存的渠道
func getChannelForContextCache(c *gin.Context, modelName string) (*model.Channel, error) {
	// 从上下文获取已分配的渠道
	channelId := common.GetContextKeyInt(c, constant.ContextKeyChannelId)
	if channelId > 0 {
		channel, err := model.GetChannelById(channelId, true)
		if err == nil && channel != nil {
			return channel, nil
		}
	}

	// 尝试通过模型名称获取渠道
	group := common.GetContextKeyString(c, constant.ContextKeyUsingGroup)
	if group == "" {
		group = "default"
	}

	channel, err := model.GetChannel(group, modelName, 0)
	if err != nil || channel == nil {
		return nil, fmt.Errorf("no available channel for model: %s", modelName)
	}

	return channel, nil
}

// buildContextCacheRelayInfo 构建上下文缓存的 relay info
func buildContextCacheRelayInfo(c *gin.Context, channel *model.Channel, modelName string, relayMode int) *relaycommon.RelayInfo {
	info := &relaycommon.RelayInfo{
		RelayMode:       relayMode,
		OriginModelName: modelName,
		TokenId:         common.GetContextKeyInt(c, constant.ContextKeyTokenId),
		TokenKey:        common.GetContextKeyString(c, constant.ContextKeyTokenKey),
		UserId:          common.GetContextKeyInt(c, constant.ContextKeyUserId),
		UsingGroup:      common.GetContextKeyString(c, constant.ContextKeyUsingGroup),
	}

	// 初始化 ChannelMeta
	upstreamModelName := modelName
	if channel.ModelMapping != nil && *channel.ModelMapping != "" {
		// 解析 ModelMapping JSON
		var modelMappingMap map[string]string
		if err := json.Unmarshal([]byte(*channel.ModelMapping), &modelMappingMap); err == nil {
			if mappedModel, ok := modelMappingMap[modelName]; ok {
				upstreamModelName = mappedModel
			}
		}
	}

	info.ChannelMeta = &relaycommon.ChannelMeta{
		ChannelType:       channel.Type,
		ChannelId:         channel.Id,
		ChannelBaseUrl:    channel.GetBaseURL(),
		ApiKey:            channel.Key,
		UpstreamModelName: upstreamModelName,
		IsModelMapped:     upstreamModelName != modelName,
	}

	return info
}

// forwardContextCacheRequest 转发上下文缓存请求到上游
func forwardContextCacheRequest(c *gin.Context, info *relaycommon.RelayInfo, request any, path string) (*http.Response, *types.NewAPIError) {
	// 应用模型映射
	if info.ChannelMeta.IsModelMapped {
		switch req := request.(type) {
		case *dto.ContextCacheCreateRequest:
			logger.LogInfo(c, fmt.Sprintf("Applying model mapping: %s -> %s", req.Model, info.ChannelMeta.UpstreamModelName))
			req.Model = info.ChannelMeta.UpstreamModelName
		case *dto.ContextCacheChatRequest:
			logger.LogInfo(c, fmt.Sprintf("Applying model mapping: %s -> %s", req.Model, info.ChannelMeta.UpstreamModelName))
			req.Model = info.ChannelMeta.UpstreamModelName
		}
	}
	
	// 序列化请求体
	jsonData, err := json.Marshal(request)
	if err != nil {
		return nil, types.NewErrorWithStatusCode(
			fmt.Errorf("failed to marshal request: %w", err),
			types.ErrorCodeBadRequestBody,
			http.StatusBadRequest,
		)
	}

	// 构建上游 URL
	baseURL := info.ChannelMeta.ChannelBaseUrl
	if baseURL == "" {
		baseURL = "https://ark.ap-southeast.bytepluses.com"
	}
	fullURL := baseURL + path

	// 创建请求
	req, err := http.NewRequest(http.MethodPost, fullURL, bytes.NewReader(jsonData))
	if err != nil {
		return nil, types.NewErrorWithStatusCode(
			fmt.Errorf("failed to create request: %w", err),
			types.ErrorCodeDoRequestFailed,
			http.StatusInternalServerError,
		)
	}

	// 设置请求头
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+info.ChannelMeta.ApiKey)
	req.Header.Set("Accept", "*/*")

	// 发送请求
	client := service.GetHttpClient()
	resp, err := client.Do(req)
	if err != nil {
		return nil, types.NewErrorWithStatusCode(
			fmt.Errorf("failed to send request: %w", err),
			types.ErrorCodeDoRequestFailed,
			http.StatusBadGateway,
		)
	}

	return resp, nil
}

// handleContextCacheStreamResponse 处理流式响应
func handleContextCacheStreamResponse(c *gin.Context, resp *http.Response) {
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("Connection", "keep-alive")
	c.Header("Transfer-Encoding", "chunked")

	c.Stream(func(w io.Writer) bool {
		buf := make([]byte, 4096)
		n, err := resp.Body.Read(buf)
		if n > 0 {
			w.Write(buf[:n])
		}
		return err == nil
	})
}
