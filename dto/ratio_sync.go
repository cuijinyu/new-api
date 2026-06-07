package dto

type UpstreamDTO struct {
	ID       int    `json:"id,omitempty"`
	Name     string `json:"name" binding:"required"`
	BaseURL  string `json:"base_url" binding:"required"`
	Endpoint string `json:"endpoint"`
}

type UpstreamRequest struct {
	ChannelIDs []int64       `json:"channel_ids"`
	Upstreams  []UpstreamDTO `json:"upstreams"`
	Timeout    int           `json:"timeout"`

	// Source 选择价格来源：
	//   ""/"channel" -> 现有逻辑（其他 new-api 渠道，保持向后兼容）
	//   "models.dev" -> 从 models.dev 全量价目表同步
	//   "openrouter" -> 从 OpenRouter 全量价目表同步
	Source string `json:"source"`

	// Models 可选过滤列表，支持精确名与通配（如 "gpt-4*"）。
	// 仅对外部源（models.dev/openrouter）生效；为空表示返回全量。
	Models []string `json:"models"`

	// OnlyExisting 为 true 时，仅同步本站已配置（model_ratio）的模型。
	// 与 Models 取并集；仅对外部源生效。
	OnlyExisting bool `json:"only_existing"`

	// ExcludeModels 排除名单，支持精确名与通配。命中的模型不会出现在预览中。
	ExcludeModels []string `json:"exclude_models"`
}

// TestResult 上游测试连通性结果
type TestResult struct {
	Name   string `json:"name"`
	Status string `json:"status"`
	Error  string `json:"error,omitempty"`
}

// DifferenceItem 差异项
// Current 为本地值，可能为 nil
// Upstreams 为各渠道的上游值，具体数值 / "same" / nil

type DifferenceItem struct {
	Current    interface{}            `json:"current"`
	Upstreams  map[string]interface{} `json:"upstreams"`
	Confidence map[string]bool        `json:"confidence"`
}

type SyncableChannel struct {
	ID      int    `json:"id"`
	Name    string `json:"name"`
	BaseURL string `json:"base_url"`
	Status  int    `json:"status"`
}
