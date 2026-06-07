package service

import (
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
