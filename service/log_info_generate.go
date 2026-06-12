package service

import (
	"encoding/json"
	"strconv"
	"strings"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/constant"
	"github.com/QuantumNous/new-api/dto"
	relaycommon "github.com/QuantumNous/new-api/relay/common"
	"github.com/QuantumNous/new-api/types"

	"github.com/gin-gonic/gin"
)

func appendRequestPath(ctx *gin.Context, relayInfo *relaycommon.RelayInfo, other map[string]interface{}) {
	if other == nil {
		return
	}
	if ctx != nil && ctx.Request != nil && ctx.Request.URL != nil {
		if path := ctx.Request.URL.Path; path != "" {
			other["request_path"] = path
			return
		}
	}
	if relayInfo != nil && relayInfo.RequestURLPath != "" {
		path := relayInfo.RequestURLPath
		if idx := strings.Index(path, "?"); idx != -1 {
			path = path[:idx]
		}
		other["request_path"] = path
	}
}

func GenerateTextOtherInfo(ctx *gin.Context, relayInfo *relaycommon.RelayInfo, modelRatio, groupRatio, completionRatio float64,
	cacheTokens int, cacheRatio float64, modelPrice float64, userGroupRatio float64) map[string]interface{} {
	other := make(map[string]interface{})
	other["model_ratio"] = modelRatio
	other["group_ratio"] = groupRatio
	other["completion_ratio"] = completionRatio
	other["cache_tokens"] = cacheTokens
	other["cache_ratio"] = cacheRatio
	other["model_price"] = modelPrice
	other["user_group_ratio"] = userGroupRatio
	other["frt"] = float64(relayInfo.FirstResponseTime.UnixMilli() - relayInfo.StartTime.UnixMilli())
	if relayInfo.ReasoningEffort != "" {
		other["reasoning_effort"] = relayInfo.ReasoningEffort
	}
	if relayInfo.IsModelMapped {
		other["is_model_mapped"] = true
		other["upstream_model_name"] = relayInfo.UpstreamModelName
	}
	if len(relayInfo.ParamOverrideAudit) > 0 {
		other["param_override_audit"] = relayInfo.ParamOverrideAudit
	}

	isSystemPromptOverwritten := common.GetContextKeyBool(ctx, constant.ContextKeySystemPromptOverride)
	if isSystemPromptOverwritten {
		other["is_system_prompt_overwritten"] = true
	}

	adminInfo := make(map[string]interface{})
	adminInfo["use_channel"] = ctx.GetStringSlice("use_channel")
	isMultiKey := common.GetContextKeyBool(ctx, constant.ContextKeyChannelIsMultiKey)
	if isMultiKey {
		adminInfo["is_multi_key"] = true
		adminInfo["multi_key_index"] = common.GetContextKeyInt(ctx, constant.ContextKeyChannelMultiKeyIndex)
	}

	isLocalCountTokens := common.GetContextKeyBool(ctx, constant.ContextKeyLocalCountTokens)
	if isLocalCountTokens {
		adminInfo["local_count_tokens"] = isLocalCountTokens
	}

	other["admin_info"] = adminInfo
	appendRequestPath(ctx, relayInfo, other)
	return other
}

func GenerateWssOtherInfo(ctx *gin.Context, relayInfo *relaycommon.RelayInfo, usage *dto.RealtimeUsage, modelRatio, groupRatio, completionRatio, audioRatio, audioCompletionRatio, modelPrice, userGroupRatio float64) map[string]interface{} {
	info := GenerateTextOtherInfo(ctx, relayInfo, modelRatio, groupRatio, completionRatio, 0, 0.0, modelPrice, userGroupRatio)
	info["ws"] = true
	info["audio_input"] = usage.InputTokenDetails.AudioTokens
	info["audio_output"] = usage.OutputTokenDetails.AudioTokens
	info["text_input"] = usage.InputTokenDetails.TextTokens
	info["text_output"] = usage.OutputTokenDetails.TextTokens
	info["audio_ratio"] = audioRatio
	info["audio_completion_ratio"] = audioCompletionRatio
	return info
}

func GenerateAudioOtherInfo(ctx *gin.Context, relayInfo *relaycommon.RelayInfo, usage *dto.Usage, modelRatio, groupRatio, completionRatio, audioRatio, audioCompletionRatio, modelPrice, userGroupRatio float64) map[string]interface{} {
	info := GenerateTextOtherInfo(ctx, relayInfo, modelRatio, groupRatio, completionRatio, 0, 0.0, modelPrice, userGroupRatio)
	info["audio"] = true
	info["audio_input"] = usage.PromptTokensDetails.AudioTokens
	info["audio_output"] = usage.CompletionTokenDetails.AudioTokens
	info["text_input"] = usage.PromptTokensDetails.TextTokens
	info["text_output"] = usage.CompletionTokenDetails.TextTokens
	info["audio_ratio"] = audioRatio
	info["audio_completion_ratio"] = audioCompletionRatio
	return info
}

func GenerateClaudeOtherInfo(ctx *gin.Context, relayInfo *relaycommon.RelayInfo, modelRatio, groupRatio, completionRatio float64,
	cacheTokens int, cacheRatio float64,
	cacheCreationTokens int, cacheCreationRatio float64,
	cacheCreationTokens5m int, cacheCreationRatio5m float64,
	cacheCreationTokens1h int, cacheCreationRatio1h float64,
	modelPrice float64, userGroupRatio float64) map[string]interface{} {
	info := GenerateTextOtherInfo(ctx, relayInfo, modelRatio, groupRatio, completionRatio, cacheTokens, cacheRatio, modelPrice, userGroupRatio)
	info["claude"] = true
	info["cache_creation_tokens"] = cacheCreationTokens
	info["cache_creation_ratio"] = cacheCreationRatio
	if cacheCreationTokens5m != 0 {
		info["cache_creation_tokens_5m"] = cacheCreationTokens5m
		info["cache_creation_ratio_5m"] = cacheCreationRatio5m
	}
	if cacheCreationTokens1h != 0 {
		info["cache_creation_tokens_1h"] = cacheCreationTokens1h
		info["cache_creation_ratio_1h"] = cacheCreationRatio1h
	}
	return info
}

// AppendConditionalPricingOther 把条件计费命中的快照写入结算日志 other。
// 仅在命中（Matched 且乘数 != 1.0）时写入，老日志无该字段时对账按 1.0 处理，向后兼容。
// 快照字段与现有 tiered_* 并列，对账侧只需读 billing_cond_multiplier 即可复算。
func AppendConditionalPricingOther(other map[string]interface{}, priceData *types.PriceData) {
	if other == nil || priceData == nil {
		return
	}
	cp := priceData.ConditionalPricing
	if cp == nil || !cp.Matched {
		return
	}
	if cp.Multiplier <= 0 || cp.Multiplier == 1.0 {
		return
	}
	other["billing_cond_multiplier"] = cp.Multiplier
	if len(cp.MatchedRules) > 0 {
		other["billing_cond_matched"] = strings.Join(cp.MatchedRules, ",")
	}
	if len(cp.FieldValues) > 0 {
		other["billing_cond_fields"] = cp.FieldValues
	}
}

func AppendBillingContextOther(other map[string]interface{}, relayInfo *relaycommon.RelayInfo, usage *dto.Usage, actualQuota int) {
	if other == nil || relayInfo == nil {
		return
	}
	provider := billingSourceProvider(relayInfo)
	providerModelID := billingProviderModelID(relayInfo, other)
	scenario := billingScenario(other)
	billing := map[string]interface{}{
		"source_provider":         provider,
		"provider_model_id":       providerModelID,
		"canonical_model_id":      providerModelID,
		"local_model_name":        relayInfo.OriginModelName,
		"scenario":                scenario,
		"actual_quota":            actualQuota,
		"group_ratio":             other["group_ratio"],
		"cond_multiplier":         firstExisting(other, "billing_cond_multiplier", 1),
		"model_ratio":             other["model_ratio"],
		"completion_ratio":        other["completion_ratio"],
		"cache_ratio":             other["cache_ratio"],
		"cache_creation_ratio":    other["cache_creation_ratio"],
		"cache_creation_ratio_5m": other["cache_creation_ratio_5m"],
		"cache_creation_ratio_1h": other["cache_creation_ratio_1h"],
		"image_ratio":             other["image_ratio"],
		"image_completion_ratio":  other["image_completion_ratio"],
		"audio_ratio":             other["audio_ratio"],
		"audio_completion_ratio":  other["audio_completion_ratio"],
		"model_price":             other["model_price"],
	}
	if usage != nil {
		billing["input_total_tokens"] = firstPositiveInt(other, usage.PromptTokens, "input_total_tokens", "prompt_tokens")
		billing["output_total_tokens"] = firstPositiveInt(other, usage.CompletionTokens, "output_total_tokens", "completion_tokens")
		billing["input_text_tokens"] = firstPositiveInt(other, usage.PromptTokensDetails.TextTokens, "input_text_tokens", "text_input")
		billing["output_text_tokens"] = firstPositiveInt(other, usage.CompletionTokenDetails.TextTokens, "output_text_tokens", "text_output")
		billing["cache_read_tokens"] = firstPositiveInt(other, usage.PromptTokensDetails.CachedTokens, "cache_tokens")
		billing["cache_write_tokens"] = firstPositiveInt(other, usage.PromptTokensDetails.CachedCreationTokens, "cache_creation_tokens", "tiered_cache_creation_tokens_remaining")
		billing["cache_write_5m_tokens"] = firstPositiveInt(other, usage.ClaudeCacheCreation5mTokens, "cache_creation_tokens_5m", "tiered_cache_creation_tokens_5m")
		billing["cache_write_1h_tokens"] = firstPositiveInt(other, usage.ClaudeCacheCreation1hTokens, "cache_creation_tokens_1h", "tiered_cache_creation_tokens_1h")
		billing["input_image_tokens"] = firstPositiveInt(other, usage.PromptTokensDetails.ImageTokens, "input_image_tokens", "image_output")
		billing["output_image_tokens"] = firstPositiveInt(other, usage.CompletionTokenDetails.ImageTokens, "output_image_tokens", "image_completion_tokens")
		billing["input_audio_tokens"] = firstPositiveInt(other, usage.PromptTokensDetails.AudioTokens, "input_audio_tokens", "audio_input_token_count", "audio_input")
		billing["output_audio_tokens"] = firstPositiveInt(other, usage.CompletionTokenDetails.AudioTokens, "output_audio_tokens", "audio_output")
		billing["output_reasoning_tokens"] = usage.CompletionTokenDetails.ReasoningTokens
		if usage.ToolUsePromptTokens > 0 {
			billing["input_tool_use_tokens"] = usage.ToolUsePromptTokens
		}
		if cost, ok := billingUsageCost(usage); ok {
			billing["provider_usage_cost"] = cost
			if provider == "openrouter" {
				other["openrouter_cost"] = cost
			}
		}
	}
	if webSearchCalls := intFromOther(other, "web_search_call_count"); webSearchCalls > 0 {
		billing["web_search_call_count"] = webSearchCalls
		billing["web_search_price"] = other["web_search_price"]
	}
	if fileSearchCalls := intFromOther(other, "file_search_call_count"); fileSearchCalls > 0 {
		billing["file_search_call_count"] = fileSearchCalls
		billing["file_search_price"] = other["file_search_price"]
	}
	if imageCount := intFromOther(other, "gemini_image_output_count"); imageCount > 0 {
		billing["image_output_count"] = imageCount
		billing["image_output_tokens_per_image"] = other["gemini_image_output_tokens_per_image"]
		billing["image_output_token_source"] = other["gemini_image_output_token_source"]
	}
	copyBillingFields(other, billing,
		"claude",
		"claude_200k",
		"claude_200k_input_multiplier",
		"claude_200k_output_multiplier",
		"claude_200k_total_input_tokens",
		"tiered_pricing",
		"tiered_input_price",
		"tiered_output_price",
		"tiered_cache_hit_price",
		"tiered_cache_store_price",
		"tiered_cache_store_price_5m",
		"tiered_cache_store_price_1h",
		"tiered_cache_creation_tokens_5m",
		"tiered_cache_creation_tokens_1h",
		"tiered_cache_creation_tokens_remaining",
		"tiered_prompt_tokens_include_cache",
		"tiered_tier_range",
		"audio_input_price",
		"image_generation_call",
		"image_generation_call_price",
	)
	if provider == "openrouter" && providerModelID != "" {
		other["openrouter_model_id"] = providerModelID
	}
	other["billing"] = billing
}

func copyBillingFields(other, billing map[string]interface{}, keys ...string) {
	if other == nil || billing == nil {
		return
	}
	for _, key := range keys {
		if value, ok := other[key]; ok {
			billing[key] = value
		}
	}
}

func billingSourceProvider(relayInfo *relaycommon.RelayInfo) string {
	if relayInfo == nil || relayInfo.ChannelMeta == nil {
		return "unknown"
	}
	switch relayInfo.ChannelType {
	case constant.ChannelTypeOpenRouter:
		return "openrouter"
	case constant.ChannelTypeOpenAI, constant.ChannelTypeOpenAIMax:
		return "openai"
	case constant.ChannelTypeAzure:
		return "azure"
	case constant.ChannelTypeAnthropic:
		return "anthropic"
	case constant.ChannelTypeGemini, constant.ChannelTypeVertexAi:
		return "google"
	default:
		return strings.ToLower(constant.GetChannelTypeName(relayInfo.ChannelType))
	}
}

func billingProviderModelID(relayInfo *relaycommon.RelayInfo, other map[string]interface{}) string {
	if relayInfo == nil {
		return ""
	}
	if relayInfo.UpstreamModelName != "" {
		return relayInfo.UpstreamModelName
	}
	if value, ok := other["upstream_model_name"].(string); ok {
		return value
	}
	return relayInfo.OriginModelName
}

func billingScenario(other map[string]interface{}) string {
	if boolFromOther(other, "image_generation_call") || intFromOther(other, "output_image_tokens") > 0 || intFromOther(other, "image_completion_tokens") > 0 {
		return "image_generation"
	}
	if intFromOther(other, "input_image_tokens") > 0 || intFromOther(other, "image_output") > 0 {
		return "vision_input"
	}
	if intFromOther(other, "input_audio_tokens") > 0 || intFromOther(other, "output_audio_tokens") > 0 || intFromOther(other, "audio_input_token_count") > 0 {
		return "audio"
	}
	if intFromOther(other, "web_search_call_count") > 0 || intFromOther(other, "file_search_call_count") > 0 {
		return "tool_call"
	}
	return "text_token"
}

func billingUsageCost(usage *dto.Usage) (float64, bool) {
	if usage == nil || usage.Cost == nil {
		return 0, false
	}
	switch typed := usage.Cost.(type) {
	case float64:
		return typed, true
	case float32:
		return float64(typed), true
	case int:
		return float64(typed), true
	case int64:
		return float64(typed), true
	case json.Number:
		cost, err := typed.Float64()
		return cost, err == nil
	case string:
		cost, err := strconv.ParseFloat(strings.TrimSpace(typed), 64)
		return cost, err == nil
	default:
		return 0, false
	}
}

func firstExisting(other map[string]interface{}, key string, fallback interface{}) interface{} {
	if value, ok := other[key]; ok {
		return value
	}
	return fallback
}

func firstPositiveInt(other map[string]interface{}, fallback int, keys ...string) int {
	for _, key := range keys {
		if value := intFromOther(other, key); value > 0 {
			return value
		}
	}
	return fallback
}

func intFromOther(other map[string]interface{}, key string) int {
	if other == nil {
		return 0
	}
	value, ok := other[key]
	if !ok {
		return 0
	}
	switch typed := value.(type) {
	case int:
		return typed
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	case float32:
		return int(typed)
	case json.Number:
		i, _ := typed.Int64()
		return int(i)
	}
	return 0
}

func boolFromOther(other map[string]interface{}, key string) bool {
	if other == nil {
		return false
	}
	value, ok := other[key]
	if !ok {
		return false
	}
	switch typed := value.(type) {
	case bool:
		return typed
	case string:
		return typed == "true" || typed == "1"
	case int:
		return typed != 0
	case float64:
		return typed != 0
	default:
		return false
	}
}

func GenerateMjOtherInfo(relayInfo *relaycommon.RelayInfo, priceData types.PerCallPriceData) map[string]interface{} {
	other := make(map[string]interface{})
	other["model_price"] = priceData.ModelPrice
	other["group_ratio"] = priceData.GroupRatioInfo.GroupRatio
	if priceData.GroupRatioInfo.HasSpecialRatio {
		other["user_group_ratio"] = priceData.GroupRatioInfo.GroupSpecialRatio
	}
	appendRequestPath(nil, relayInfo, other)
	return other
}
