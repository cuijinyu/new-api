package dto

type ChannelSettings struct {
	ForceFormat            bool   `json:"force_format,omitempty"`
	ThinkingToContent      bool   `json:"thinking_to_content,omitempty"`
	Proxy                  string `json:"proxy"`
	PassThroughBodyEnabled bool   `json:"pass_through_body_enabled,omitempty"`
	SystemPrompt           string `json:"system_prompt,omitempty"`
	SystemPromptOverride   bool   `json:"system_prompt_override,omitempty"`
}

type VertexKeyType string

const (
	VertexKeyTypeJSON   VertexKeyType = "json"
	VertexKeyTypeAPIKey VertexKeyType = "api_key"
)

type AwsKeyType string

const (
	AwsKeyTypeAKSK   AwsKeyType = "ak_sk" // 默认
	AwsKeyTypeApiKey AwsKeyType = "api_key"
)

type ChannelOtherSettings struct {
	AzureResponsesVersion  string        `json:"azure_responses_version,omitempty"`
	VertexKeyType          VertexKeyType `json:"vertex_key_type,omitempty"` // "json" or "api_key"
	OpenRouterEnterprise   *bool         `json:"openrouter_enterprise,omitempty"`
	AllowServiceTier       bool          `json:"allow_service_tier,omitempty"`        // 是否允许 service_tier 透传（默认过滤以避免额外计费）
	DisableStore           bool          `json:"disable_store,omitempty"`             // 是否禁用 store 透传（默认允许透传，禁用后可能导致 Codex 无法使用）
	AllowSafetyIdentifier  bool          `json:"allow_safety_identifier,omitempty"`   // 是否允许 safety_identifier 透传（默认过滤以保护用户隐私）
	AllowContextManagement bool          `json:"allow_context_management,omitempty"`  // 是否允许 context_management 透传（仅 Claude，默认过滤以避免上游不兼容）
	AllowCacheControlScope bool          `json:"allow_cache_control_scope,omitempty"` // 是否允许 cache_control.scope 透传（仅 Claude，默认过滤以兼容 Bedrock 等非 Anthropic 上游）
	AwsKeyType             AwsKeyType    `json:"aws_key_type,omitempty"`
}

func (s *ChannelOtherSettings) IsOpenRouterEnterprise() bool {
	if s == nil || s.OpenRouterEnterprise == nil {
		return false
	}
	return *s.OpenRouterEnterprise
}
