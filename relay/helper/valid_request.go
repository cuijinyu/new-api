package helper

import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"strings"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/dto"
	"github.com/QuantumNous/new-api/logger"
	relayconstant "github.com/QuantumNous/new-api/relay/constant"
	"github.com/QuantumNous/new-api/types"

	"github.com/gin-gonic/gin"
)

func GetAndValidateRequest(c *gin.Context, format types.RelayFormat) (request dto.Request, err error) {
	relayMode := relayconstant.Path2RelayMode(c.Request.URL.Path)

	switch format {
	case types.RelayFormatOpenAI:
		request, err = GetAndValidateTextRequest(c, relayMode)
	case types.RelayFormatGemini:
		if strings.Contains(c.Request.URL.Path, ":embedContent") {
			request, err = GetAndValidateGeminiEmbeddingRequest(c)
		} else if strings.Contains(c.Request.URL.Path, ":batchEmbedContents") {
			request, err = GetAndValidateGeminiBatchEmbeddingRequest(c)
		} else {
			request, err = GetAndValidateGeminiRequest(c)
		}
	case types.RelayFormatClaude:
		request, err = GetAndValidateClaudeRequest(c)
	case types.RelayFormatOpenAIResponses:
		request, err = GetAndValidateResponsesRequest(c)

	case types.RelayFormatOpenAIImage:
		request, err = GetAndValidOpenAIImageRequest(c, relayMode)
	case types.RelayFormatEmbedding:
		request, err = GetAndValidateEmbeddingRequest(c, relayMode)
	case types.RelayFormatRerank:
		request, err = GetAndValidateRerankRequest(c)
	case types.RelayFormatOpenAIAudio:
		request, err = GetAndValidAudioRequest(c, relayMode)
	case types.RelayFormatOpenAIRealtime:
		request = &dto.BaseRequest{}
	default:
		return nil, fmt.Errorf("unsupported relay format: %s", format)
	}
	return request, err
}

func GetAndValidAudioRequest(c *gin.Context, relayMode int) (*dto.AudioRequest, error) {
	audioRequest := &dto.AudioRequest{}
	err := common.UnmarshalBodyReusable(c, audioRequest)
	if err != nil {
		return nil, err
	}
	switch relayMode {
	case relayconstant.RelayModeAudioSpeech:
		if audioRequest.Model == "" {
			return nil, errors.New("model is required")
		}
	default:
		if audioRequest.Model == "" {
			return nil, errors.New("model is required")
		}
		if audioRequest.ResponseFormat == "" {
			audioRequest.ResponseFormat = "json"
		}
	}
	return audioRequest, nil
}

func GetAndValidateRerankRequest(c *gin.Context) (*dto.RerankRequest, error) {
	var rerankRequest *dto.RerankRequest
	err := common.UnmarshalBodyReusable(c, &rerankRequest)
	if err != nil {
		logger.LogError(c, fmt.Sprintf("getAndValidateTextRequest failed: %s", err.Error()))
		return nil, types.NewError(err, types.ErrorCodeInvalidRequest, types.ErrOptionWithSkipRetry())
	}

	if rerankRequest.Query == "" {
		return nil, types.NewError(fmt.Errorf("query is empty"), types.ErrorCodeInvalidRequest, types.ErrOptionWithSkipRetry())
	}
	if len(rerankRequest.Documents) == 0 {
		return nil, types.NewError(fmt.Errorf("documents is empty"), types.ErrorCodeInvalidRequest, types.ErrOptionWithSkipRetry())
	}
	return rerankRequest, nil
}

func GetAndValidateEmbeddingRequest(c *gin.Context, relayMode int) (*dto.EmbeddingRequest, error) {
	var embeddingRequest *dto.EmbeddingRequest
	err := common.UnmarshalBodyReusable(c, &embeddingRequest)
	if err != nil {
		logger.LogError(c, fmt.Sprintf("getAndValidateTextRequest failed: %s", err.Error()))
		return nil, types.NewError(err, types.ErrorCodeInvalidRequest, types.ErrOptionWithSkipRetry())
	}

	if embeddingRequest.Input == nil {
		return nil, fmt.Errorf("input is empty")
	}
	if relayMode == relayconstant.RelayModeModerations && embeddingRequest.Model == "" {
		embeddingRequest.Model = "omni-moderation-latest"
	}
	if relayMode == relayconstant.RelayModeEmbeddings && embeddingRequest.Model == "" {
		embeddingRequest.Model = c.Param("model")
	}
	return embeddingRequest, nil
}

func GetAndValidateResponsesRequest(c *gin.Context) (*dto.OpenAIResponsesRequest, error) {
	request := &dto.OpenAIResponsesRequest{}
	err := common.UnmarshalBodyReusable(c, request)
	if err != nil {
		return nil, err
	}
	if request.Model == "" {
		return nil, errors.New("model is required")
	}
	if request.Input == nil {
		return nil, errors.New("input is required")
	}
	return request, nil
}

func ConvertChatCompletionsToResponsesRequest(request *dto.GeneralOpenAIRequest) (*dto.OpenAIResponsesRequest, error) {
	if request == nil {
		return nil, errors.New("request is nil")
	}

	input, instructions, err := convertChatMessagesToResponsesInput(request.Messages)
	if err != nil {
		return nil, err
	}

	responsesRequest := &dto.OpenAIResponsesRequest{
		Model:                request.Model,
		Input:                input,
		MaxOutputTokens:      request.MaxCompletionTokens,
		Stream:               request.Stream,
		Store:                request.Store,
		PromptCacheRetention: request.PromptCacheRetention,
		User:                 request.User,
		Metadata:             request.Metadata,
	}
	if responsesRequest.MaxOutputTokens == 0 {
		responsesRequest.MaxOutputTokens = request.MaxTokens
	}
	if instructions != nil {
		responsesRequest.Instructions = instructions
	}
	if request.ReasoningEffort != "" {
		responsesRequest.Reasoning = &dto.Reasoning{Effort: request.ReasoningEffort}
	}
	if request.Temperature != nil {
		responsesRequest.Temperature = *request.Temperature
	}
	if request.TopP != 0 {
		responsesRequest.TopP = request.TopP
	}
	if request.PromptCacheKey != "" {
		responsesRequest.PromptCacheKey, _ = json.Marshal(request.PromptCacheKey)
	}
	if request.ParallelTooCalls != nil {
		responsesRequest.ParallelToolCalls, _ = json.Marshal(*request.ParallelTooCalls)
	}
	if len(request.Tools) > 0 {
		responsesRequest.Tools, err = json.Marshal(request.Tools)
		if err != nil {
			return nil, fmt.Errorf("marshal tools failed: %w", err)
		}
	}
	if request.ToolChoice != nil {
		responsesRequest.ToolChoice, err = json.Marshal(request.ToolChoice)
		if err != nil {
			return nil, fmt.Errorf("marshal tool_choice failed: %w", err)
		}
	}
	if request.ResponseFormat != nil {
		responsesRequest.Text, err = json.Marshal(map[string]any{
			"format": request.ResponseFormat,
		})
		if err != nil {
			return nil, fmt.Errorf("marshal text format failed: %w", err)
		}
	}
	if len(request.Verbosity) > 0 {
		var text map[string]any
		if len(responsesRequest.Text) > 0 {
			_ = json.Unmarshal(responsesRequest.Text, &text)
		}
		if text == nil {
			text = make(map[string]any)
		}
		var verbosity any
		if err := json.Unmarshal(request.Verbosity, &verbosity); err == nil {
			text["verbosity"] = verbosity
			responsesRequest.Text, _ = json.Marshal(text)
		}
	}

	return responsesRequest, nil
}

func convertChatMessagesToResponsesInput(messages []dto.Message) (json.RawMessage, json.RawMessage, error) {
	input := make([]map[string]any, 0, len(messages))
	instructions := make([]string, 0)

	for _, message := range messages {
		role := strings.TrimSpace(message.Role)
		if role == "" {
			role = "user"
		}

		content, err := convertChatContentToResponsesContent(message.Content)
		if err != nil {
			return nil, nil, err
		}

		if role == "system" || role == "developer" {
			if text, ok := content.(string); ok && text != "" {
				instructions = append(instructions, text)
			}
			continue
		}

		item := map[string]any{
			"role":    role,
			"content": content,
		}
		if message.Name != nil {
			item["name"] = *message.Name
		}
		if message.ToolCallId != "" {
			item["tool_call_id"] = message.ToolCallId
		}
		if len(message.ToolCalls) > 0 {
			var toolCalls any
			if err := json.Unmarshal(message.ToolCalls, &toolCalls); err == nil {
				item["tool_calls"] = toolCalls
			}
		}
		input = append(input, item)
	}

	inputRaw, err := json.Marshal(input)
	if err != nil {
		return nil, nil, fmt.Errorf("marshal responses input failed: %w", err)
	}
	var instructionsRaw json.RawMessage
	if len(instructions) > 0 {
		instructionsRaw, err = json.Marshal(strings.Join(instructions, "\n"))
		if err != nil {
			return nil, nil, fmt.Errorf("marshal responses instructions failed: %w", err)
		}
	}
	return inputRaw, instructionsRaw, nil
}

func convertChatContentToResponsesContent(content any) (any, error) {
	switch value := content.(type) {
	case string:
		return value, nil
	case []any:
		parts := make([]map[string]any, 0, len(value))
		for _, part := range value {
			partMap, ok := part.(map[string]any)
			if !ok {
				parts = append(parts, map[string]any{
					"type": "input_text",
					"text": fmt.Sprintf("%v", part),
				})
				continue
			}
			parts = append(parts, convertChatContentPartToResponsesPart(partMap))
		}
		return parts, nil
	default:
		return value, nil
	}
}

func convertChatContentPartToResponsesPart(part map[string]any) map[string]any {
	partType := common.Interface2String(part["type"])
	switch partType {
	case dto.ContentTypeText:
		return map[string]any{
			"type": "input_text",
			"text": common.Interface2String(part["text"]),
		}
	case dto.ContentTypeImageURL:
		image := map[string]any{
			"type": "input_image",
		}
		switch imageURL := part["image_url"].(type) {
		case string:
			image["image_url"] = imageURL
		case map[string]any:
			if url := common.Interface2String(imageURL["url"]); url != "" {
				image["image_url"] = url
			}
			if detail := common.Interface2String(imageURL["detail"]); detail != "" {
				image["detail"] = detail
			}
		default:
			image["image_url"] = imageURL
		}
		return image
	case dto.ContentTypeFile:
		file := map[string]any{
			"type": "input_file",
		}
		if fileMap, ok := part["file"].(map[string]any); ok {
			for _, key := range []string{"file_id", "file_data", "filename"} {
				if value, exists := fileMap[key]; exists {
					file[key] = value
				}
			}
		}
		return file
	default:
		return part
	}
}

func GetAndValidOpenAIImageRequest(c *gin.Context, relayMode int) (*dto.ImageRequest, error) {
	imageRequest := &dto.ImageRequest{}

	switch relayMode {
	case relayconstant.RelayModeImagesEdits:
		if strings.Contains(c.Request.Header.Get("Content-Type"), "multipart/form-data") {
			_, err := c.MultipartForm()
			if err != nil {
				return nil, fmt.Errorf("failed to parse image edit form request: %w", err)
			}
			formData := c.Request.PostForm
			imageRequest.Prompt = formData.Get("prompt")
			imageRequest.Model = formData.Get("model")
			imageRequest.N = uint(common.String2Int(formData.Get("n")))
			imageRequest.Quality = formData.Get("quality")
			imageRequest.Size = formData.Get("size")
			imageRequest.ResponseFormat = formData.Get("response_format")
			if imageValue := formData.Get("image"); imageValue != "" {
				imageRequest.Image, _ = json.Marshal(imageValue)
			}

			if imageRequest.Model == "gpt-image-1" {
				if imageRequest.Quality == "" {
					imageRequest.Quality = "standard"
				}
			}
			if imageRequest.N == 0 {
				imageRequest.N = 1
			}

			hasWatermark := formData.Has("watermark")
			if hasWatermark {
				watermark := formData.Get("watermark") == "true"
				imageRequest.Watermark = &watermark
			}
			break
		}
		fallthrough
	default:
		err := common.UnmarshalBodyReusable(c, imageRequest)
		if err != nil {
			return nil, err
		}

		if imageRequest.Model == "" {
			//imageRequest.Model = "dall-e-3"
			return nil, errors.New("model is required")
		}

		if strings.Contains(imageRequest.Size, "×") {
			return nil, errors.New("size an unexpected error occurred in the parameter, please use 'x' instead of the multiplication sign '×'")
		}

		// Not "256x256", "512x512", or "1024x1024"
		if imageRequest.Model == "dall-e-2" || imageRequest.Model == "dall-e" {
			if imageRequest.Size != "" && imageRequest.Size != "256x256" && imageRequest.Size != "512x512" && imageRequest.Size != "1024x1024" {
				return nil, errors.New("size must be one of 256x256, 512x512, or 1024x1024 for dall-e-2 or dall-e")
			}
			if imageRequest.Size == "" {
				imageRequest.Size = "1024x1024"
			}
		} else if imageRequest.Model == "dall-e-3" {
			if imageRequest.Size != "" && imageRequest.Size != "1024x1024" && imageRequest.Size != "1024x1792" && imageRequest.Size != "1792x1024" {
				return nil, errors.New("size must be one of 1024x1024, 1024x1792 or 1792x1024 for dall-e-3")
			}
			if imageRequest.Quality == "" {
				imageRequest.Quality = "standard"
			}
			if imageRequest.Size == "" {
				imageRequest.Size = "1024x1024"
			}
		} else if imageRequest.Model == "gpt-image-1" {
			if imageRequest.Quality == "" {
				imageRequest.Quality = "auto"
			}
		}

		//if imageRequest.Prompt == "" {
		//	return nil, errors.New("prompt is required")
		//}

		if imageRequest.N == 0 {
			imageRequest.N = 1
		}
	}

	return imageRequest, nil
}

func GetAndValidateClaudeRequest(c *gin.Context) (textRequest *dto.ClaudeRequest, err error) {
	textRequest = &dto.ClaudeRequest{}
	err = c.ShouldBindJSON(textRequest)
	if err != nil {
		return nil, err
	}
	if len(textRequest.Messages) == 0 {
		return nil, errors.New("field messages is required")
	}
	// Do not block empty content; only guard against missing `content` field (nil)
	// to avoid downstream conversion errors.
	for i := range textRequest.Messages {
		if textRequest.Messages[i].Content == nil {
			return nil, errors.New("field messages[i].content is required")
		}
	}
	if textRequest.Model == "" {
		return nil, errors.New("field model is required")
	}
	//if textRequest.Stream {
	//	relayInfo.IsStream = true
	//}

	return textRequest, nil
}

func GetAndValidateTextRequest(c *gin.Context, relayMode int) (*dto.GeneralOpenAIRequest, error) {
	textRequest := &dto.GeneralOpenAIRequest{}
	err := common.UnmarshalBodyReusable(c, textRequest)
	if err != nil {
		return nil, err
	}

	if relayMode == relayconstant.RelayModeModerations && textRequest.Model == "" {
		textRequest.Model = "text-moderation-latest"
	}
	if relayMode == relayconstant.RelayModeEmbeddings && textRequest.Model == "" {
		textRequest.Model = c.Param("model")
	}

	if textRequest.MaxTokens > math.MaxInt32/2 {
		return nil, errors.New("max_tokens is invalid")
	}
	if textRequest.Model == "" {
		return nil, errors.New("model is required")
	}
	if textRequest.WebSearchOptions != nil {
		if textRequest.WebSearchOptions.SearchContextSize != "" {
			validSizes := map[string]bool{
				"high":   true,
				"medium": true,
				"low":    true,
			}
			if !validSizes[textRequest.WebSearchOptions.SearchContextSize] {
				return nil, errors.New("invalid search_context_size, must be one of: high, medium, low")
			}
		} else {
			textRequest.WebSearchOptions.SearchContextSize = "medium"
		}
	}
	switch relayMode {
	case relayconstant.RelayModeCompletions:
		if textRequest.Prompt == "" {
			return nil, errors.New("field prompt is required")
		}
	case relayconstant.RelayModeChatCompletions:
		// For FIM (Fill-in-the-middle) requests with prefix/suffix, messages is optional
		// It will be filled by provider-specific adaptors if needed (e.g., SiliconFlow)。Or it is allowed by model vendor(s) (e.g., DeepSeek)
		if len(textRequest.Messages) == 0 && textRequest.Prefix == nil && textRequest.Suffix == nil {
			return nil, errors.New("field messages is required")
		}
	case relayconstant.RelayModeEmbeddings:
	case relayconstant.RelayModeModerations:
		if textRequest.Input == nil || textRequest.Input == "" {
			return nil, errors.New("field input is required")
		}
	case relayconstant.RelayModeEdits:
		if textRequest.Instruction == "" {
			return nil, errors.New("field instruction is required")
		}
	}
	return textRequest, nil
}

func GetAndValidateGeminiRequest(c *gin.Context) (*dto.GeminiChatRequest, error) {
	request := &dto.GeminiChatRequest{}
	err := common.UnmarshalBodyReusable(c, request)
	if err != nil {
		return nil, err
	}
	if len(request.Contents) == 0 && len(request.Requests) == 0 {
		return nil, errors.New("contents is required")
	}

	//if c.Query("alt") == "sse" {
	//	relayInfo.IsStream = true
	//}

	return request, nil
}

func GetAndValidateGeminiEmbeddingRequest(c *gin.Context) (*dto.GeminiEmbeddingRequest, error) {
	request := &dto.GeminiEmbeddingRequest{}
	err := common.UnmarshalBodyReusable(c, request)
	if err != nil {
		return nil, err
	}
	return request, nil
}

func GetAndValidateGeminiBatchEmbeddingRequest(c *gin.Context) (*dto.GeminiBatchEmbeddingRequest, error) {
	request := &dto.GeminiBatchEmbeddingRequest{}
	err := common.UnmarshalBodyReusable(c, request)
	if err != nil {
		return nil, err
	}
	return request, nil
}
