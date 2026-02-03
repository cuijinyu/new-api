package dto

import (
	"encoding/json"
)

// BytePlus/Volcengine Responses API DTOs
// Reference: https://docs.byteplus.com/en/docs/ModelArk/Create_model_request

// BytePlusResponsesRequest BytePlus Responses API 请求
type BytePlusResponsesRequest struct {
	Model              string          `json:"model"`                          // 推理接入点 ID (endpoint ID) 或 Model ID
	Input              json.RawMessage `json:"input,omitempty"`                // 输入内容
	Instructions       string          `json:"instructions,omitempty"`         // 系统指令
	MaxOutputTokens    int             `json:"max_output_tokens,omitempty"`    // 最大输出 token 数
	Temperature        float64         `json:"temperature,omitempty"`          // 采样温度
	TopP               float64         `json:"top_p,omitempty"`                // 核采样概率
	Stream             bool            `json:"stream,omitempty"`               // 是否流式响应
	PreviousResponseID string          `json:"previous_response_id,omitempty"` // 上一次响应的 ID（用于缓存）
	Caching            *ResponsesCaching `json:"caching,omitempty"`            // 缓存配置
	Thinking           *ResponsesThinking `json:"thinking,omitempty"`          // 思考模式配置
	Store              *bool           `json:"store,omitempty"`                // 是否存储响应
	Tools              json.RawMessage `json:"tools,omitempty"`                // 工具配置
	ToolChoice         json.RawMessage `json:"tool_choice,omitempty"`          // 工具选择
	Metadata           json.RawMessage `json:"metadata,omitempty"`             // 元数据
}

// ResponsesCaching 缓存配置
type ResponsesCaching struct {
	Type   string `json:"type,omitempty"`   // "enabled" 或 "disabled"
	Prefix *bool  `json:"prefix,omitempty"` // 是否启用前缀缓存
}

// ResponsesThinking 思考模式配置
type ResponsesThinking struct {
	Type string `json:"type,omitempty"` // "enabled" 或 "disabled"
}

// BytePlusResponsesResponse BytePlus Responses API 响应
type BytePlusResponsesResponse struct {
	ID                 string                    `json:"id"`
	Object             string                    `json:"object,omitempty"`
	CreatedAt          int64                     `json:"created_at,omitempty"`
	Model              string                    `json:"model,omitempty"`
	Output             []BytePlusResponsesOutput `json:"output,omitempty"`
	Usage              *BytePlusResponsesUsage   `json:"usage,omitempty"`
	Status             string                    `json:"status,omitempty"`
	Error              json.RawMessage           `json:"error,omitempty"`
	Caching            *ResponsesCachingResult   `json:"caching,omitempty"`
	Store              bool                      `json:"store,omitempty"`
	ExpireAt           int64                     `json:"expire_at,omitempty"`
}

// BytePlusResponsesOutput 输出内容
type BytePlusResponsesOutput struct {
	Type    string                       `json:"type,omitempty"`
	ID      string                       `json:"id,omitempty"`
	Status  string                       `json:"status,omitempty"`
	Role    string                       `json:"role,omitempty"`
	Content []BytePlusResponsesContent   `json:"content,omitempty"`
}

// BytePlusResponsesContent 内容项
type BytePlusResponsesContent struct {
	Type        string          `json:"type,omitempty"`
	Text        string          `json:"text,omitempty"`
	Annotations json.RawMessage `json:"annotations,omitempty"`
}

// BytePlusResponsesUsage token 使用情况
type BytePlusResponsesUsage struct {
	InputTokens        int                          `json:"input_tokens"`
	OutputTokens       int                          `json:"output_tokens"`
	TotalTokens        int                          `json:"total_tokens"`
	InputTokensDetails *BytePlusInputTokensDetails  `json:"input_tokens_details,omitempty"`
	OutputTokensDetails *BytePlusOutputTokensDetails `json:"output_tokens_details,omitempty"`
}

// BytePlusInputTokensDetails 输入 token 详情
type BytePlusInputTokensDetails struct {
	CachedTokens int `json:"cached_tokens"`
}

// BytePlusOutputTokensDetails 输出 token 详情
type BytePlusOutputTokensDetails struct {
	ReasoningTokens int `json:"reasoning_tokens"`
}

// ResponsesCachingResult 缓存结果
type ResponsesCachingResult struct {
	Type   string `json:"type,omitempty"`
	Prefix bool   `json:"prefix,omitempty"`
}

// GetModel 获取模型名称
func (r *BytePlusResponsesRequest) GetModel() string {
	return r.Model
}

// SetModel 设置模型名称
func (r *BytePlusResponsesRequest) SetModel(model string) {
	r.Model = model
}

// IsStream 是否流式请求
func (r *BytePlusResponsesRequest) IsStream() bool {
	return r.Stream
}

// ToUsage 转换为标准 Usage
func (u *BytePlusResponsesUsage) ToUsage() *Usage {
	if u == nil {
		return nil
	}
	usage := &Usage{
		PromptTokens:     u.InputTokens,
		CompletionTokens: u.OutputTokens,
		TotalTokens:      u.TotalTokens,
	}
	if u.InputTokensDetails != nil {
		usage.PromptTokensDetails.CachedTokens = u.InputTokensDetails.CachedTokens
	}
	return usage
}

// BytePlusResponsesStreamResponse 流式响应
type BytePlusResponsesStreamResponse struct {
	Type     string                     `json:"type"`
	Response *BytePlusResponsesResponse `json:"response,omitempty"`
	Delta    string                     `json:"delta,omitempty"`
	Item     *BytePlusResponsesOutput   `json:"item,omitempty"`
}
