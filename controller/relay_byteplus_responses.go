package controller

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/constant"
	"github.com/QuantumNous/new-api/dto"
	"github.com/QuantumNous/new-api/logger"
	"github.com/QuantumNous/new-api/model"
	relaycommon "github.com/QuantumNous/new-api/relay/common"
	relayconstant "github.com/QuantumNous/new-api/relay/constant"
	"github.com/QuantumNous/new-api/service"
	"github.com/QuantumNous/new-api/setting/ratio_setting"
	"github.com/QuantumNous/new-api/types"

	"github.com/gin-gonic/gin"
)

// RelayBytePlusResponses 处理 BytePlus Responses API
// POST /api/v3/responses
func RelayBytePlusResponses(c *gin.Context) {
	requestId := c.GetString(common.RequestIdKey)

	// 解析请求
	var request dto.BytePlusResponsesRequest
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

	// 获取渠道信息
	channel, err := getChannelForBytePlusResponses(c, request.Model)
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
	info := buildBytePlusResponsesRelayInfo(c, channel, request.Model, relayconstant.RelayModeBytePlusResponses)
	info.IsStream = request.Stream

	// 转发请求到上游
	resp, usage, apiErr := forwardBytePlusResponsesRequest(c, info, &request)
	if apiErr != nil {
		logger.LogError(c, fmt.Sprintf("BytePlus responses error: %s", apiErr.Error()))
		c.JSON(apiErr.StatusCode, gin.H{
			"error": apiErr.ToOpenAIError(),
		})
		return
	}
	defer resp.Body.Close()

	// 处理流式响应
	if request.Stream {
		handleBytePlusResponsesStream(c, resp, info, usage)
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

	// 检查响应状态
	if resp.StatusCode != http.StatusOK {
		c.Data(resp.StatusCode, resp.Header.Get("Content-Type"), body)
		return
	}

	// 解析响应以获取 usage
	var response dto.BytePlusResponsesResponse
	if err := json.Unmarshal(body, &response); err == nil && response.Usage != nil {
		// 记录消费
		postBytePlusResponsesConsume(c, info, response.Usage)
	}

	// 返回响应
	c.Data(resp.StatusCode, resp.Header.Get("Content-Type"), body)
}

// getChannelForBytePlusResponses 获取用于 BytePlus Responses 的渠道
func getChannelForBytePlusResponses(c *gin.Context, modelName string) (*model.Channel, error) {
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

// buildBytePlusResponsesRelayInfo 构建 BytePlus Responses 的 relay info
func buildBytePlusResponsesRelayInfo(c *gin.Context, channel *model.Channel, modelName string, relayMode int) *relaycommon.RelayInfo {
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

// forwardBytePlusResponsesRequest 转发 BytePlus Responses 请求到上游
func forwardBytePlusResponsesRequest(c *gin.Context, info *relaycommon.RelayInfo, request *dto.BytePlusResponsesRequest) (*http.Response, *dto.BytePlusResponsesUsage, *types.NewAPIError) {
	// 应用模型映射
	if info.ChannelMeta.IsModelMapped {
		request.Model = info.ChannelMeta.UpstreamModelName
	}

	// 序列化请求体
	jsonData, err := json.Marshal(request)
	if err != nil {
		return nil, nil, types.NewErrorWithStatusCode(
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
	fullURL := fmt.Sprintf("%s/api/v3/responses", baseURL)

	// 创建请求
	req, err := http.NewRequest(http.MethodPost, fullURL, bytes.NewReader(jsonData))
	if err != nil {
		return nil, nil, types.NewErrorWithStatusCode(
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
		return nil, nil, types.NewErrorWithStatusCode(
			fmt.Errorf("failed to send request: %w", err),
			types.ErrorCodeDoRequestFailed,
			http.StatusBadGateway,
		)
	}

	return resp, nil, nil
}

// handleBytePlusResponsesStream 处理流式响应
func handleBytePlusResponsesStream(c *gin.Context, resp *http.Response, info *relaycommon.RelayInfo, initialUsage *dto.BytePlusResponsesUsage) {
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("Connection", "keep-alive")
	c.Header("Transfer-Encoding", "chunked")

	var finalUsage *dto.BytePlusResponsesUsage

	c.Stream(func(w io.Writer) bool {
		buf := make([]byte, 4096)
		n, err := resp.Body.Read(buf)
		if n > 0 {
			data := buf[:n]
			w.Write(data)

			// 尝试解析流式响应以获取 usage
			lines := strings.Split(string(data), "\n")
			for _, line := range lines {
				if strings.HasPrefix(line, "data: ") {
					jsonStr := strings.TrimPrefix(line, "data: ")
					if jsonStr == "[DONE]" {
						continue
					}
					var streamResp dto.BytePlusResponsesStreamResponse
					if err := json.Unmarshal([]byte(jsonStr), &streamResp); err == nil {
						if streamResp.Response != nil && streamResp.Response.Usage != nil {
							finalUsage = streamResp.Response.Usage
						}
					}
				}
			}
		}
		return err == nil
	})

	// 记录消费
	if finalUsage != nil {
		postBytePlusResponsesConsume(c, info, finalUsage)
	}
}

// postBytePlusResponsesConsume 记录 BytePlus Responses 消费
func postBytePlusResponsesConsume(c *gin.Context, info *relaycommon.RelayInfo, byteplusUsage *dto.BytePlusResponsesUsage) {
	if byteplusUsage == nil {
		return
	}

	// 转换为标准 Usage
	usage := byteplusUsage.ToUsage()
	if usage == nil {
		return
	}

	// 获取分段计费配置
	tieredConfig, hasTiered := ratio_setting.GetTieredPricing(info.OriginModelName)
	
	// 计算配额
	var quota int
	var otherInfo = make(map[string]interface{})
	
	if hasTiered && tieredConfig != nil && tieredConfig.Enabled {
		// 使用分段计费
		inputTokensK := usage.PromptTokens / 1000
		tier, foundTier := ratio_setting.GetPriceTierForTokens(info.OriginModelName, inputTokensK)
		
		if foundTier && tier != nil {
			// 计算缓存 tokens
			cachedTokens := usage.PromptTokensDetails.CachedTokens
			nonCachedInputTokens := usage.PromptTokens - cachedTokens
			
			// 计算费用
			inputCost := float64(nonCachedInputTokens) * tier.InputPrice / 1000000.0
			outputCost := float64(usage.CompletionTokens) * tier.OutputPrice / 1000000.0
			cacheCost := float64(cachedTokens) * tier.CacheHitPrice / 1000000.0
			
			totalCostUSD := inputCost + outputCost + cacheCost
			
			// 转换为配额 (1 USD = 500000 quota)
			quota = int(totalCostUSD * common.QuotaPerUnit)
			
			// 记录分段计费信息
			otherInfo["tiered_pricing"] = true
			otherInfo["tiered_tier_range"] = fmt.Sprintf("%d-%d", tier.MinTokens, tier.MaxTokens)
			otherInfo["tiered_input_price"] = tier.InputPrice
			otherInfo["tiered_output_price"] = tier.OutputPrice
			otherInfo["tiered_cache_hit_price"] = tier.CacheHitPrice
			otherInfo["cache_tokens"] = cachedTokens
		}
	}
	
	if quota == 0 {
		// 使用标准计费 - 使用模型倍率和分组倍率计算
		modelRatio, _, _ := ratio_setting.GetModelRatio(info.OriginModelName)
		groupRatio := ratio_setting.GetGroupRatio(info.UsingGroup)
		completionRatio := ratio_setting.GetCompletionRatio(info.OriginModelName)
		
		promptTokensFloat := float64(usage.PromptTokens)
		completionTokensFloat := float64(usage.CompletionTokens)
		
		quota = int((promptTokensFloat + completionTokensFloat*completionRatio) * modelRatio * groupRatio)
	}
	
	// 记录其他信息
	otherInfo["request_path"] = "/api/v3/responses"
	otherInfo["cache_tokens"] = usage.PromptTokensDetails.CachedTokens
	
	// 记录消费日志
	logger.LogInfo(c, fmt.Sprintf("BytePlus Responses consume: prompt_tokens=%d, completion_tokens=%d, cached_tokens=%d, quota=%d",
		usage.PromptTokens, usage.CompletionTokens, usage.PromptTokensDetails.CachedTokens, quota))
	
	// 扣除配额
	if quota > 0 {
		userId := info.UserId
		channelId := info.ChannelMeta.ChannelId
		modelName := info.OriginModelName
		
		err := service.PostConsumeQuota(info, quota, 0, true)
		if err != nil {
			logger.LogError(c, fmt.Sprintf("Failed to consume token quota: %v", err))
		}
		
		// 记录日志
		logContent := fmt.Sprintf("模型: %s, 输入: %d, 输出: %d, 缓存: %d",
			modelName, usage.PromptTokens, usage.CompletionTokens, usage.PromptTokensDetails.CachedTokens)
		model.RecordConsumeLog(c, userId, model.RecordConsumeLogParams{
			ChannelId:        channelId,
			PromptTokens:     usage.PromptTokens,
			CompletionTokens: usage.CompletionTokens,
			ModelName:        modelName,
			TokenName:        info.TokenKey,
			Quota:            quota,
			Content:          logContent,
			TokenId:          info.TokenId,
			UseTimeSeconds:   0,
			IsStream:         info.IsStream,
			Group:            info.UsingGroup,
			Other:            otherInfo,
		})
	}
}
