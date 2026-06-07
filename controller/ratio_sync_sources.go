package controller

// 价格源同步扩展：在不改动现有 FetchUpstreamRatios（其他 new-api 渠道）行为的前提下，
// 新增 models.dev / OpenRouter 两个外部价格源，并提供分段/图片/按次计费护栏。
//
// 核心约定（与计划一致）：
//   - 换算：model_ratio = input_usd_per_1M / 2（$2/1M => ratio 1.0）；
//           completion_ratio = output_usd / input_usd；cache_ratio = cache_read_usd / input_usd。
//   - 取价与落库严格两步：本文件只负责“获取->返回 diff 预览”，绝不写库。
//   - 计费模式分流：每个模型按 分段(tiered)/图片(image)/按次(once)/纯文本(text) 归类，
//     前端据此分桶展示；分段/图片/按次默认不勾选，避免扁平价覆盖运行时的分段/图片/按次计费。

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/dto"
	"github.com/QuantumNous/new-api/logger"
	"github.com/QuantumNous/new-api/setting/ratio_setting"

	"github.com/gin-gonic/gin"
)

const (
	sourceChannel    = ""
	sourceModelsDev  = "models.dev"
	sourceOpenRouter = "openrouter"

	modelsDevURL  = "https://models.dev/api.json"
	openRouterURL = "https://openrouter.ai/api/v1/models"

	maxExternalBytes = 64 << 20 // 64MB，models.dev/OpenRouter 全量价目表

	// 计费模式分桶标识，前端据此决定默认勾选/置灰与提示文案
	categoryText   = "text"   // 纯文本 ratio，可直接预览/应用
	categoryTiered = "tiered" // 分段计费，需复核
	categoryImage  = "image"  // 图片专用计费，需复核
	categoryOnce   = "once"   // 按次计费，需复核
)

// imageModelNameKeywords 用于在外部源里识别“图像生成/图片”类模型名。
// 这些模型在本站走图片专用计费（size/quality/N 或 image token 倍率），
// 外部源的扁平 token 价无法表达，必须排除自动写入。
var imageModelNameKeywords = []string{
	"dall-e", "dalle", "gpt-image", "stable-diffusion", "sdxl", "flux",
	"midjourney", "imagen", "ideogram", "recraft", "playground-v",
	"kolors", "seedream", "seededit", "hunyuan-image", "nano-banana",
	"qwen-image", "wan2", "wan-",
}

// normalizeSource 将前端传入的源名标准化为内部常量。
func normalizeSource(s string) string {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "", "channel", "channels", "newapi":
		return sourceChannel
	case "models.dev", "modelsdev", "models_dev", "models-dev":
		return sourceModelsDev
	case "openrouter", "open_router", "open-router":
		return sourceOpenRouter
	default:
		return strings.ToLower(strings.TrimSpace(s))
	}
}

// handleExternalSource 处理 models.dev / OpenRouter 外部源的获取与预览（不写库）。
func handleExternalSource(c *gin.Context, req *dto.UpstreamRequest, source string) {
	client := newExternalHTTPClient(req.Timeout)
	ctx, cancel := context.WithTimeout(c.Request.Context(), time.Duration(req.Timeout)*time.Second)
	defer cancel()

	var (
		data    map[string]any
		err     error
		srcName string
	)
	switch source {
	case sourceModelsDev:
		srcName = "models.dev"
		data, err = fetchModelsDev(ctx, client)
	case sourceOpenRouter:
		srcName = "OpenRouter"
		data, err = fetchOpenRouter(ctx, client)
	default:
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "未知价格源"})
		return
	}

	if err != nil {
		logger.LogWarn(c.Request.Context(), "fetch external price source failed ("+srcName+"): "+err.Error())
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": fmt.Sprintf("获取 %s 价目表失败：%s", srcName, err.Error()),
			"data": gin.H{
				"test_results": []dto.TestResult{{Name: srcName, Status: "error", Error: err.Error()}},
			},
		})
		return
	}

	include := buildModelFilter(req)
	exclude := buildExcludeFilter(req)
	filterSourceData(data, include, exclude)

	localData := ratio_setting.GetExposedData()
	successfulChannels := []struct {
		name string
		data map[string]any
	}{{name: srcName, data: data}}

	differences := buildDifferences(localData, successfulChannels)

	responseData := gin.H{
		"differences":  differences,
		"test_results": []dto.TestResult{{Name: srcName, Status: "success"}},
		"categories":   computeCategories(differences),
		"source":       source,
	}
	if len(req.Models) > 0 {
		responseData["source_data"] = data
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"data":    responseData,
	})
}

// newExternalHTTPClient 构造用于外部源拉取的 http client（IPv4 优先，带超时）。
func newExternalHTTPClient(timeoutSec int) *http.Client {
	if timeoutSec <= 0 {
		timeoutSec = defaultTimeoutSeconds
	}
	dialer := &net.Dialer{Timeout: 10 * time.Second}
	transport := &http.Transport{
		MaxIdleConns:          100,
		IdleConnTimeout:       90 * time.Second,
		TLSHandshakeTimeout:   10 * time.Second,
		ExpectContinueTimeout: 1 * time.Second,
		ResponseHeaderTimeout: time.Duration(timeoutSec) * time.Second,
	}
	transport.DialContext = func(ctx context.Context, network, addr string) (net.Conn, error) {
		if conn, err := dialer.DialContext(ctx, "tcp4", addr); err == nil {
			return conn, nil
		}
		return dialer.DialContext(ctx, network, addr)
	}
	return &http.Client{Transport: transport, Timeout: time.Duration(timeoutSec+5) * time.Second}
}

// fetchModelsDev 解析 models.dev 全量价目表 -> 与现有 upstreamResult.Data 同结构的 ratio map。
// models.dev /api.json 结构：{ "<provider>": { "models": { "<model>": { "cost": { input, output, cache_read } } } } }
// 其中 cost.* 单位为 USD / 1M tokens。
func fetchModelsDev(ctx context.Context, client *http.Client) (map[string]any, error) {
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodGet, modelsDevURL, nil)
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Accept", "application/json")

	resp, err := client.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("models.dev 返回 %s", resp.Status)
	}

	limited := io.LimitReader(resp.Body, maxExternalBytes)
	var providers map[string]struct {
		Models map[string]struct {
			Cost *struct {
				Input     float64 `json:"input"`
				Output    float64 `json:"output"`
				CacheRead float64 `json:"cache_read"`
			} `json:"cost"`
		} `json:"models"`
	}
	if err := json.NewDecoder(limited).Decode(&providers); err != nil {
		return nil, fmt.Errorf("解析 models.dev 数据失败：%w", err)
	}

	modelRatio := make(map[string]any)
	completion := make(map[string]any)
	cache := make(map[string]any)

	for _, p := range providers {
		for name, m := range p.Models {
			if m.Cost == nil {
				continue
			}
			applyExternalPricing(name, m.Cost.Input, m.Cost.Output, m.Cost.CacheRead,
				modelRatio, completion, cache)
		}
	}

	return assembleSourceData(modelRatio, completion, cache), nil
}

// fetchOpenRouter 解析 OpenRouter /api/v1/models -> 同结构 ratio map。
// pricing.* 单位为 USD / token（字符串），需 ×1e6 转成 USD / 1M tokens。
// model id 形如 "anthropic/claude-3.5-sonnet"，取最后一段作为本站模型名。
func fetchOpenRouter(ctx context.Context, client *http.Client) (map[string]any, error) {
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodGet, openRouterURL, nil)
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Accept", "application/json")

	resp, err := client.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("OpenRouter 返回 %s", resp.Status)
	}

	limited := io.LimitReader(resp.Body, maxExternalBytes)
	var body struct {
		Data []struct {
			ID      string `json:"id"`
			Pricing struct {
				Prompt         string `json:"prompt"`
				Completion     string `json:"completion"`
				InputCacheRead string `json:"input_cache_read"`
			} `json:"pricing"`
		} `json:"data"`
	}
	if err := json.NewDecoder(limited).Decode(&body); err != nil {
		return nil, fmt.Errorf("解析 OpenRouter 数据失败：%w", err)
	}

	modelRatio := make(map[string]any)
	completion := make(map[string]any)
	cache := make(map[string]any)

	for _, m := range body.Data {
		name := m.ID
		if idx := strings.LastIndex(name, "/"); idx >= 0 {
			name = name[idx+1:]
		}
		inputPer1M := parseFloatSafe(m.Pricing.Prompt) * 1e6
		outputPer1M := parseFloatSafe(m.Pricing.Completion) * 1e6
		cacheReadPer1M := parseFloatSafe(m.Pricing.InputCacheRead) * 1e6
		applyExternalPricing(name, inputPer1M, outputPer1M, cacheReadPer1M,
			modelRatio, completion, cache)
	}

	return assembleSourceData(modelRatio, completion, cache), nil
}

// applyExternalPricing 按换算约定把单模型价格写入三张 map（保留首个有效报价）。
func applyExternalPricing(name string, inputPer1M, outputPer1M, cacheReadPer1M float64,
	modelRatio, completion, cache map[string]any) {
	if name == "" {
		return
	}
	if _, exists := modelRatio[name]; exists {
		return // 多 provider 同名时保留首个
	}
	if inputPer1M <= 0 {
		return // 免费/缺失输入价无法表达为倍率，跳过
	}
	modelRatio[name] = inputPer1M / 2.0
	if outputPer1M > 0 {
		completion[name] = outputPer1M / inputPer1M
	}
	if cacheReadPer1M > 0 {
		cache[name] = cacheReadPer1M / inputPer1M
	}
}

func assembleSourceData(modelRatio, completion, cache map[string]any) map[string]any {
	data := make(map[string]any)
	if len(modelRatio) > 0 {
		data["model_ratio"] = modelRatio
	}
	if len(completion) > 0 {
		data["completion_ratio"] = completion
	}
	if len(cache) > 0 {
		data["cache_ratio"] = cache
	}
	return data
}

func parseFloatSafe(s string) float64 {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0
	}
	f, err := strconv.ParseFloat(s, 64)
	if err != nil {
		return 0
	}
	return f
}

// buildModelFilter 构造“是否纳入”谓词：OnlyExisting 与 Models 取并集；二者皆空 => 全量。
func buildModelFilter(req *dto.UpstreamRequest) func(string) bool {
	exact := make(map[string]struct{})
	var wildcards []string

	if req.OnlyExisting {
		for k := range ratio_setting.GetModelRatioCopy() {
			exact[k] = struct{}{}
		}
	}
	for _, m := range req.Models {
		m = strings.TrimSpace(m)
		if m == "" {
			continue
		}
		if strings.Contains(m, "*") {
			wildcards = append(wildcards, m)
		} else {
			exact[m] = struct{}{}
		}
	}

	if len(exact) == 0 && len(wildcards) == 0 {
		return func(string) bool { return true }
	}
	return func(name string) bool {
		if _, ok := exact[name]; ok {
			return true
		}
		for _, w := range wildcards {
			if ratio_setting.MatchModelPattern(w, name) {
				return true
			}
		}
		return false
	}
}

// buildExcludeFilter 构造排除谓词（命中则剔除，不出现在预览中）。
func buildExcludeFilter(req *dto.UpstreamRequest) func(string) bool {
	exact := make(map[string]struct{})
	var wildcards []string
	for _, m := range req.ExcludeModels {
		m = strings.TrimSpace(m)
		if m == "" {
			continue
		}
		if strings.Contains(m, "*") {
			wildcards = append(wildcards, m)
		} else {
			exact[m] = struct{}{}
		}
	}
	if len(exact) == 0 && len(wildcards) == 0 {
		return func(string) bool { return false }
	}
	return func(name string) bool {
		if _, ok := exact[name]; ok {
			return true
		}
		for _, w := range wildcards {
			if ratio_setting.MatchModelPattern(w, name) {
				return true
			}
		}
		return false
	}
}

// filterSourceData 原地过滤源数据的三张 ratio map。
func filterSourceData(data map[string]any, include func(string) bool, exclude func(string) bool) {
	for _, rt := range ratioTypes {
		sub, ok := data[rt].(map[string]any)
		if !ok {
			continue
		}
		for name := range sub {
			if !include(name) || exclude(name) {
				delete(sub, name)
			}
		}
		if len(sub) == 0 {
			delete(data, rt)
		}
	}
}

// classifyBillingMode 复用现有判定函数，按运行时优先级归类模型计费模式。
// 顺序与 relay/helper/price.go 的优先级一致：分段 > 图片 > 按次 > 扁平文本。
func classifyBillingMode(model string) string {
	if ratio_setting.IsTieredPricingEnabled(model) {
		return categoryTiered
	}
	if isImageModel(model) {
		return categoryImage
	}
	if _, ok := ratio_setting.GetModelPrice(model, false); ok {
		return categoryOnce
	}
	return categoryText
}

// isImageModel 判定是否为图片/图像生成模型：命中图片专用倍率或图像模型名特征。
func isImageModel(model string) bool {
	if _, ok := ratio_setting.GetImageRatio(model); ok {
		return true
	}
	if _, ok := ratio_setting.GetImageCompletionRatio(model); ok {
		return true
	}
	lower := strings.ToLower(model)
	for _, kw := range imageModelNameKeywords {
		if strings.Contains(lower, kw) {
			return true
		}
	}
	return false
}

// computeCategories 为预览中出现的每个模型计算计费模式分桶。
func computeCategories(differences map[string]map[string]dto.DifferenceItem) map[string]string {
	cats := make(map[string]string, len(differences))
	for model := range differences {
		cats[model] = classifyBillingMode(model)
	}
	return cats
}
