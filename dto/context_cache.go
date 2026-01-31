package dto

// BytePlus/Volcengine Context Cache API DTOs
// Reference: https://docs.byteplus.com/en/docs/ModelArk/1346559

// ContextCacheCreateRequest 创建上下文缓存请求
type ContextCacheCreateRequest struct {
	Model              string                      `json:"model"`                         // 推理接入点 ID (endpoint ID)
	Messages           []Message                   `json:"messages"`                      // 初始消息列表
	Mode               string                      `json:"mode,omitempty"`                // 缓存类型: "session" 或 "common_prefix"
	TTL                int                         `json:"ttl,omitempty"`                 // 过期时间（秒），范围 [3600, 604800]
	TruncationStrategy *ContextTruncationStrategy  `json:"truncation_strategy,omitempty"` // 截断策略
}

// ContextTruncationStrategy 上下文截断策略
type ContextTruncationStrategy struct {
	Type          string `json:"type,omitempty"`           // 截断策略类型: "rolling_tokens"
	RollingTokens bool   `json:"rolling_tokens,omitempty"` // 是否自动裁剪历史上下文
}

// ContextCacheCreateResponse 创建上下文缓存响应
type ContextCacheCreateResponse struct {
	ID                 string                     `json:"id"`                            // 缓存 ID (ctx-xxx)
	Model              string                     `json:"model"`                         // 推理接入点 ID
	TTL                int                        `json:"ttl"`                           // 过期时间（秒）
	Mode               string                     `json:"mode,omitempty"`                // 缓存类型
	TruncationStrategy *ContextTruncationStrategy `json:"truncation_strategy,omitempty"` // 截断策略
	Usage              *ContextCacheUsage         `json:"usage,omitempty"`               // Token 使用情况
}

// ContextCacheUsage 上下文缓存 token 使用情况
type ContextCacheUsage struct {
	PromptTokens        int                   `json:"prompt_tokens"`
	CompletionTokens    int                   `json:"completion_tokens"`
	TotalTokens         int                   `json:"total_tokens"`
	PromptTokensDetails *PromptTokensDetails  `json:"prompt_tokens_details,omitempty"`
}

// PromptTokensDetails prompt tokens 详情
type PromptTokensDetails struct {
	CachedTokens int `json:"cached_tokens"`
}

// ContextCacheChatRequest 使用上下文缓存的对话请求
type ContextCacheChatRequest struct {
	Model         string    `json:"model"`                    // 推理接入点 ID
	ContextID     string    `json:"context_id"`               // 上下文缓存 ID
	Messages      []Message `json:"messages"`                 // 消息列表（仅需传入最新消息）
	Stream        bool      `json:"stream,omitempty"`         // 是否流式响应
	StreamOptions any       `json:"stream_options,omitempty"` // 流式响应选项
	MaxTokens     int       `json:"max_tokens,omitempty"`     // 最大生成 token 数
	Temperature   float64   `json:"temperature,omitempty"`    // 采样温度
	TopP          float64   `json:"top_p,omitempty"`          // 核采样概率
	Stop          any       `json:"stop,omitempty"`           // 停止词
}

// ContextCacheChatResponse 使用上下文缓存的对话响应
type ContextCacheChatResponse struct {
	ID      string                     `json:"id"`
	Object  string                     `json:"object"`
	Created int64                      `json:"created"`
	Model   string                     `json:"model"`
	Choices []ContextCacheChatChoice   `json:"choices"`
	Usage   *ContextCacheUsage         `json:"usage,omitempty"`
}

// ContextCacheChatChoice 对话选项
type ContextCacheChatChoice struct {
	Index        int      `json:"index"`
	Message      *Message `json:"message,omitempty"`
	Delta        *Message `json:"delta,omitempty"` // 流式响应时使用
	FinishReason string   `json:"finish_reason,omitempty"`
}

// GetModel 获取模型名称
func (r *ContextCacheCreateRequest) GetModel() string {
	return r.Model
}

// SetModel 设置模型名称
func (r *ContextCacheCreateRequest) SetModel(model string) {
	r.Model = model
}

// GetModel 获取模型名称
func (r *ContextCacheChatRequest) GetModel() string {
	return r.Model
}

// SetModel 设置模型名称
func (r *ContextCacheChatRequest) SetModel(model string) {
	r.Model = model
}

// IsStream 是否流式请求
func (r *ContextCacheChatRequest) IsStream() bool {
	return r.Stream
}
