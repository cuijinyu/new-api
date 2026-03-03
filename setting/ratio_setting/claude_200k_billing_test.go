package ratio_setting

import (
	"math"
	"testing"
)

// 模拟“promptTokens 不含缓存”的 ratio 计费分支计算逻辑
//（例如 Claude 原生计费链路中的总输入组装方式）
// 用于集成验证 Claude 200K 倍率对最终 quota 的影响
//
// 计费公式:
//   正常: quota = (promptQuota + completionQuota) * modelRatio * groupRatio
//   Claude >200K: quota = promptQuota * modelRatio * groupRatio * inputMult
//                       + completionQuota * modelRatio * groupRatio * outputMult
//
// 其中:
//   promptQuota = baseTokens + cacheTokens*cacheRatio + cacheCreationTokens*cacheCreationRatio
//   completionQuota = completionTokens * completionRatio

const (
	testQuotaPerUnit = 500 * 1000.0 // 与 common.QuotaPerUnit 一致
)

type billingTestCase struct {
	name                  string
	modelName             string
	promptTokens          int     // 实际输入 tokens（不含缓存）
	cacheTokens           int     // 缓存读取 tokens (cache_read_input_tokens)
	cacheCreationTokens   int     // 缓存创建 tokens (cache_creation_input_tokens)
	completionTokens      int     // 输出 tokens
	modelRatio            float64 // 模型倍率
	completionRatio       float64 // 输出倍率
	cacheRatio            float64 // 缓存命中倍率
	cacheCreationRatio    float64 // 缓存创建倍率
	groupRatio            float64 // 分组倍率

	// 期望值
	expectHigherRate bool    // 是否预期触发 >200K 倍率
	expectedQuota    float64 // 期望的 quota（允许浮点误差）
}

// simulateBilling 模拟 ratio 计费分支（promptTokens 不含缓存）
// totalInput = promptTokens + cacheTokens + cacheCreationTokens
func simulateBilling(tc billingTestCase) (quota float64, inputMult float64, outputMult float64) {
	// 计算 promptQuota（模拟 Anthropic 频道，promptTokens 不含缓存）
	baseTokens := float64(tc.promptTokens)
	cachedTokensWithRatio := float64(tc.cacheTokens) * tc.cacheRatio
	cachedCreationTokensWithRatio := float64(tc.cacheCreationTokens) * tc.cacheCreationRatio
	promptQuota := baseTokens + cachedTokensWithRatio + cachedCreationTokensWithRatio

	// 计算 completionQuota
	completionQuota := float64(tc.completionTokens) * tc.completionRatio

	// 计算 ratio
	ratio := tc.modelRatio * tc.groupRatio

	// Claude 200K 倍率：totalInput = promptTokens + cacheTokens + cacheCreationTokens
	totalInputTokens := tc.promptTokens + tc.cacheTokens + tc.cacheCreationTokens
	inputMult, outputMult = GetClaude200KMultipliers(tc.modelName, totalInputTokens)

	if inputMult != 1.0 || outputMult != 1.0 {
		// 分别对输入和输出应用不同倍率
		quota = promptQuota*ratio*inputMult + completionQuota*ratio*outputMult
	} else {
		// 正常计费
		quota = (promptQuota + completionQuota) * ratio
	}

	return quota, inputMult, outputMult
}

// TestClaudeCompatible200KThresholdNoDoubleCountCache 验证 compatible 链路阈值判断口径：
// compatible_handler 中 promptTokens 已包含 cache_read / cache_creation，不能再次叠加。
func TestClaudeCompatible200KThresholdNoDoubleCountCache(t *testing.T) {
	modelName := "claude-sonnet-4-20250514"

	// 在 compatible 链路中，promptTokens 已是“总输入”。
	// 这个用例设计为：
	// - 正确口径（只看 promptTokens）=> 190K，不触发 >200K
	// - 错误口径（再加 cache/cachedCreation）=> 300K，错误触发 >200K
	promptTokens := 190000
	cacheTokens := 90000
	cacheCreationTokens := 20000
	completionTokens := 1000
	modelRatio := 1.5
	completionRatio := 5.0
	cacheRatio := 0.1
	cacheCreationRatio := 1.25
	groupRatio := 1.0

	correctInputMult, correctOutputMult := GetClaude200KMultipliers(modelName, promptTokens)
	if correctInputMult != 1.0 || correctOutputMult != 1.0 {
		t.Fatalf("correct threshold should not trigger >200K, got input=%f output=%f", correctInputMult, correctOutputMult)
	}

	legacyTotal := promptTokens + cacheTokens + cacheCreationTokens
	legacyInputMult, legacyOutputMult := GetClaude200KMultipliers(modelName, legacyTotal)
	if legacyInputMult == 1.0 && legacyOutputMult == 1.0 {
		t.Fatalf("legacy threshold should (incorrectly) trigger >200K in this case")
	}

	// 计算同一 usage 下两种阈值口径的 quota，确保错误口径会显著高估
	baseTokens := float64(promptTokens - cacheTokens - cacheCreationTokens)
	promptQuota := baseTokens +
		float64(cacheTokens)*cacheRatio +
		float64(cacheCreationTokens)*cacheCreationRatio
	completionQuota := float64(completionTokens) * completionRatio
	ratio := modelRatio * groupRatio

	correctQuota := (promptQuota + completionQuota) * ratio
	legacyQuota := promptQuota*ratio*legacyInputMult + completionQuota*ratio*legacyOutputMult

	if legacyQuota <= correctQuota {
		t.Fatalf("legacy quota should be greater due to incorrect >200K trigger, got legacy=%f correct=%f", legacyQuota, correctQuota)
	}
}

// =====================================================================
// Claude 原生端点 (PostClaudeConsumeQuota) 计费模拟
// =====================================================================

// claudeNativeBillingTestCase 模拟 PostClaudeConsumeQuota 的全部参数
type claudeNativeBillingTestCase struct {
	name                    string
	modelName               string
	promptTokens            int     // input_tokens（不含 cache_read / cache_creation）
	cacheTokens             int     // cache_read_input_tokens
	cacheCreationTokens     int     // cache_creation_input_tokens（总量）
	cacheCreationTokens5m   int     // 5 分钟缓存创建 tokens
	cacheCreationTokens1h   int     // 1 小时缓存创建 tokens
	completionTokens        int     // output_tokens
	modelRatio              float64
	completionRatio         float64
	cacheRatio              float64 // 缓存读取倍率
	cacheCreationRatio      float64 // 缓存创建倍率（默认）
	cacheCreationRatio5m    float64 // 5m 缓存创建倍率
	cacheCreationRatio1h    float64 // 1h 缓存创建倍率
	groupRatio              float64

	// 期望值
	expectHigherRate bool
	expectedQuota    float64
}

// simulateClaudeNativeBilling 模拟 service/quota.go PostClaudeConsumeQuota 的计费逻辑
func simulateClaudeNativeBilling(tc claudeNativeBillingTestCase) (quota float64, inputMult float64, outputMult float64) {
	// totalInput = promptTokens + cacheTokens + cacheCreationTokens
	totalInputForClaude := tc.promptTokens + tc.cacheTokens + tc.cacheCreationTokens
	inputMult, outputMult = GetClaude200KMultipliers(tc.modelName, totalInputForClaude)

	promptQuota := float64(tc.promptTokens)
	promptQuota += float64(tc.cacheTokens) * tc.cacheRatio
	promptQuota += float64(tc.cacheCreationTokens5m) * tc.cacheCreationRatio5m
	promptQuota += float64(tc.cacheCreationTokens1h) * tc.cacheCreationRatio1h
	remaining := tc.cacheCreationTokens - tc.cacheCreationTokens5m - tc.cacheCreationTokens1h
	if remaining > 0 {
		promptQuota += float64(remaining) * tc.cacheCreationRatio
	}
	completionQuota := float64(tc.completionTokens) * tc.completionRatio

	if inputMult != 1.0 || outputMult != 1.0 {
		quota = promptQuota*tc.modelRatio*tc.groupRatio*inputMult +
			completionQuota*tc.modelRatio*tc.groupRatio*outputMult
	} else {
		quota = (promptQuota + completionQuota) * tc.groupRatio * tc.modelRatio
	}

	return quota, inputMult, outputMult
}

func TestClaude200KBillingIntegration(t *testing.T) {
	tests := []billingTestCase{
		// ========== Claude Opus 4.6 (modelRatio=2.5, completionRatio=5) ==========
		// $5/MTok input, $25/MTok output
		{
			name:               "Claude Opus 4.6 - 100K tokens, normal rate",
			modelName:          "claude-opus-4-6-20260120",
			promptTokens:       100000,
			completionTokens:   1000,
			modelRatio:         2.5,
			completionRatio:    5.0,
			cacheRatio:         0.1,
			cacheCreationRatio: 1.25,
			groupRatio:         1.0,
			expectHigherRate:   false,
			// quota = (100000 + 1000*5) * 2.5 = 105000 * 2.5 = 262500
			expectedQuota: 262500,
		},
		{
			name:               "Claude Opus 4.6 - exactly 200K tokens, normal rate (boundary)",
			modelName:          "claude-opus-4-6-20260120",
			promptTokens:       200000,
			completionTokens:   1000,
			modelRatio:         2.5,
			completionRatio:    5.0,
			cacheRatio:         0.1,
			cacheCreationRatio: 1.25,
			groupRatio:         1.0,
			expectHigherRate:   false,
			// quota = (200000 + 1000*5) * 2.5 = 205000 * 2.5 = 512500
			expectedQuota: 512500,
		},
		{
			name:               "Claude Opus 4.6 - 200001 tokens, higher rate (just over)",
			modelName:          "claude-opus-4-6-20260120",
			promptTokens:       200001,
			completionTokens:   1000,
			modelRatio:         2.5,
			completionRatio:    5.0,
			cacheRatio:         0.1,
			cacheCreationRatio: 1.25,
			groupRatio:         1.0,
			expectHigherRate:   true,
			// quota = 200001 * 2.5 * 2.0 + 1000 * 5 * 2.5 * 1.5
			//       = 1000005 + 18750 = 1018755
			expectedQuota: 1018755,
		},
		{
			name:               "Claude Opus 4.6 - 300K tokens, higher rate",
			modelName:          "claude-opus-4-6-20260120",
			promptTokens:       300000,
			completionTokens:   2000,
			modelRatio:         2.5,
			completionRatio:    5.0,
			cacheRatio:         0.1,
			cacheCreationRatio: 1.25,
			groupRatio:         1.0,
			expectHigherRate:   true,
			// quota = 300000 * 2.5 * 2.0 + 2000 * 5 * 2.5 * 1.5
			//       = 1500000 + 37500 = 1537500
			expectedQuota: 1537500,
		},

		// ========== 缓存读取场景 ==========
		{
			name:               "Claude - 150K prompt + 60K cache_read = 210K total, triggers higher rate",
			modelName:          "claude-opus-4-5-20251101",
			promptTokens:       150000,
			cacheTokens:        60000,
			completionTokens:   500,
			modelRatio:         2.5,
			completionRatio:    5.0,
			cacheRatio:         0.1,
			cacheCreationRatio: 1.25,
			groupRatio:         1.0,
			expectHigherRate:   true,
			// promptQuota = 150000 + 60000*0.1 = 156000
			// completionQuota = 500 * 5 = 2500
			// quota = 156000 * 2.5 * 2.0 + 2500 * 2.5 * 1.5
			//       = 780000 + 9375 = 789375
			expectedQuota: 789375,
		},
		{
			name:               "Claude - 100K prompt + 90K cache_read = 190K total, normal rate",
			modelName:          "claude-sonnet-4-20250514",
			promptTokens:       100000,
			cacheTokens:        90000,
			completionTokens:   500,
			modelRatio:         1.5,
			completionRatio:    5.0,
			cacheRatio:         0.1,
			cacheCreationRatio: 1.25,
			groupRatio:         1.0,
			expectHigherRate:   false,
			// promptQuota = 100000 + 90000*0.1 = 109000
			// completionQuota = 500 * 5 = 2500
			// quota = (109000 + 2500) * 1.5 = 167250
			expectedQuota: 167250,
		},

		// ========== 缓存创建参与 200K 阈值判断 ==========
		{
			name:                "Claude - 26 prompt + 284516 cache_creation = 284542 total, triggers higher rate",
			modelName:           "claude-sonnet-4-20250514",
			promptTokens:        26,
			cacheCreationTokens: 284516,
			completionTokens:    54,
			modelRatio:          1.5,
			completionRatio:     5.0,
			cacheRatio:          0.1,
			cacheCreationRatio:  1.25,
			groupRatio:          1.0,
			expectHigherRate:    true,
			// promptQuota = 26 + 284516*1.25 = 26 + 355645 = 355671
			// completionQuota = 54 * 5 = 270
			// quota = 355671 * 1.5 * 2.0 + 270 * 1.5 * 1.5
			//       = 1067013 + 607.5 = 1067620.5
			expectedQuota: 1067620.5,
		},
		{
			name:                "Claude - 100K prompt + 101K cache_creation = 201K total, triggers higher rate",
			modelName:           "claude-opus-4-6-20260120",
			promptTokens:        100000,
			cacheCreationTokens: 101000,
			completionTokens:    1000,
			modelRatio:          2.5,
			completionRatio:     5.0,
			cacheRatio:          0.1,
			cacheCreationRatio:  1.25,
			groupRatio:          1.0,
			expectHigherRate:    true,
			// promptQuota = 100000 + 101000*1.25 = 100000 + 126250 = 226250
			// completionQuota = 1000 * 5 = 5000
			// quota = 226250 * 2.5 * 2.0 + 5000 * 2.5 * 1.5
			//       = 1131250 + 18750 = 1150000
			expectedQuota: 1150000,
		},
		{
			name:                "Claude - 100K prompt + 99K cache_creation = 199K total, normal rate",
			modelName:           "claude-opus-4-6-20260120",
			promptTokens:        100000,
			cacheCreationTokens: 99000,
			completionTokens:    1000,
			modelRatio:          2.5,
			completionRatio:     5.0,
			cacheRatio:          0.1,
			cacheCreationRatio:  1.25,
			groupRatio:          1.0,
			expectHigherRate:    false,
			// promptQuota = 100000 + 99000*1.25 = 100000 + 123750 = 223750
			// completionQuota = 1000 * 5 = 5000
			// quota = (223750 + 5000) * 2.5 = 228750 * 2.5 = 571875
			expectedQuota: 571875,
		},
		{
			name:                "Claude - prompt + cache_read + cache_creation all contribute to 200K threshold",
			modelName:           "claude-sonnet-4-20250514",
			promptTokens:        50000,
			cacheTokens:         80000,
			cacheCreationTokens: 80000,
			completionTokens:    500,
			modelRatio:          1.5,
			completionRatio:     5.0,
			cacheRatio:          0.1,
			cacheCreationRatio:  1.25,
			groupRatio:          1.0,
			expectHigherRate:    true, // 50K + 80K + 80K = 210K > 200K
			// promptQuota = 50000 + 80000*0.1 + 80000*1.25 = 50000 + 8000 + 100000 = 158000
			// completionQuota = 500 * 5 = 2500
			// quota = 158000 * 1.5 * 2.0 + 2500 * 1.5 * 1.5
			//       = 474000 + 5625 = 479625
			expectedQuota: 479625,
		},

		// ========== 分组倍率场景 ==========
		{
			name:               "Claude >200K with groupRatio 1.5",
			modelName:          "claude-opus-4-6-20260120",
			promptTokens:       250000,
			completionTokens:   1000,
			modelRatio:         2.5,
			completionRatio:    5.0,
			cacheRatio:         0.1,
			cacheCreationRatio: 1.25,
			groupRatio:         1.5,
			expectHigherRate:   true,
			// ratio = 2.5 * 1.5 = 3.75
			// quota = 250000 * 3.75 * 2.0 + 1000 * 5 * 3.75 * 1.5
			//       = 1875000 + 28125 = 1903125
			expectedQuota: 1903125,
		},

		// ========== 非 Claude 模型 - 超过 200K 也不触发 ==========
		{
			name:               "GPT-4 - 300K tokens, no multiplier",
			modelName:          "gpt-4",
			promptTokens:       300000,
			completionTokens:   1000,
			modelRatio:         15.0,
			completionRatio:    2.0,
			cacheRatio:         0.0,
			cacheCreationRatio: 0.0,
			groupRatio:         1.0,
			expectHigherRate:   false,
			// quota = (300000 + 1000*2) * 15 = 302000 * 15 = 4530000
			expectedQuota: 4530000,
		},

		// ========== Claude Sonnet 模型 ==========
		{
			name:               "Claude Sonnet 4.5 - 250K tokens, higher rate",
			modelName:          "claude-sonnet-4-5-20250929",
			promptTokens:       250000,
			completionTokens:   2000,
			modelRatio:         1.5,
			completionRatio:    5.0,
			cacheRatio:         0.1,
			cacheCreationRatio: 1.25,
			groupRatio:         1.0,
			expectHigherRate:   true,
			// quota = 250000 * 1.5 * 2.0 + 2000 * 5 * 1.5 * 1.5
			//       = 750000 + 22500 = 772500
			expectedQuota: 772500,
		},

		// ========== 极端情况 ==========
		{
			name:               "Claude - 0 prompt, 0 completion, 0 cache",
			modelName:          "claude-opus-4-6-20260120",
			promptTokens:       0,
			completionTokens:   0,
			modelRatio:         2.5,
			completionRatio:    5.0,
			cacheRatio:         0.1,
			cacheCreationRatio: 1.25,
			groupRatio:         1.0,
			expectHigherRate:   false,
			expectedQuota:      0,
		},
		{
			name:               "Claude - only cache_read tokens, 0+201K cache = 201K total",
			modelName:          "claude-opus-4-6-20260120",
			promptTokens:       0,
			cacheTokens:        201000,
			completionTokens:   100,
			modelRatio:         2.5,
			completionRatio:    5.0,
			cacheRatio:         0.1,
			cacheCreationRatio: 1.25,
			groupRatio:         1.0,
			expectHigherRate:   true,
			// promptQuota = 0 + 201000*0.1 = 20100
			// completionQuota = 100 * 5 = 500
			// quota = 20100 * 2.5 * 2.0 + 500 * 2.5 * 1.5
			//       = 100500 + 1875 = 102375
			expectedQuota: 102375,
		},
		{
			name:                "Claude - only cache_creation tokens, 0+210K creation = 210K total",
			modelName:           "claude-opus-4-6-20260120",
			promptTokens:        0,
			cacheCreationTokens: 210000,
			completionTokens:    100,
			modelRatio:          2.5,
			completionRatio:     5.0,
			cacheRatio:          0.1,
			cacheCreationRatio:  1.25,
			groupRatio:          1.0,
			expectHigherRate:    true,
			// promptQuota = 0 + 210000*1.25 = 262500
			// completionQuota = 100 * 5 = 500
			// quota = 262500 * 2.5 * 2.0 + 500 * 2.5 * 1.5
			//       = 1312500 + 1875 = 1314375
			expectedQuota: 1314375,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			quota, inputMult, outputMult := simulateBilling(tt)

			// 验证是否触发 >200K 倍率
			isHigherRate := (inputMult != 1.0 || outputMult != 1.0)
			if isHigherRate != tt.expectHigherRate {
				t.Errorf("higher rate triggered = %v, want %v (inputMult=%f, outputMult=%f)",
					isHigherRate, tt.expectHigherRate, inputMult, outputMult)
			}

			// 验证 quota 计算结果（允许浮点精度误差 0.01）
			if math.Abs(quota-tt.expectedQuota) > 0.01 {
				t.Errorf("quota = %f, want %f (diff=%f)",
					quota, tt.expectedQuota, quota-tt.expectedQuota)
			}

			// 验证 >200K 时的 quota 确实大于正常 quota
			if tt.expectHigherRate && tt.promptTokens > 0 {
				normalQuota := simulateNormalBilling(tt)
				if quota <= normalQuota {
					t.Errorf("Claude >200K quota (%f) should be greater than normal quota (%f)",
						quota, normalQuota)
				}
				// 验证输入部分确实是 2 倍
				ratio := tt.modelRatio * tt.groupRatio
				promptQuota := float64(tt.promptTokens) + float64(tt.cacheTokens)*tt.cacheRatio
				inputNormal := promptQuota * ratio
				inputHigher := promptQuota * ratio * inputMult
				if math.Abs(inputHigher/inputNormal-2.0) > 0.001 {
					t.Errorf("input multiplier ratio = %f, want 2.0", inputHigher/inputNormal)
				}
			}
		})
	}
}

// simulateNormalBilling 计算不带 Claude 200K 倍率的正常 quota
func simulateNormalBilling(tc billingTestCase) float64 {
	baseTokens := float64(tc.promptTokens)
	cachedTokensWithRatio := float64(tc.cacheTokens) * tc.cacheRatio
	cachedCreationTokensWithRatio := float64(tc.cacheCreationTokens) * tc.cacheCreationRatio
	promptQuota := baseTokens + cachedTokensWithRatio + cachedCreationTokensWithRatio
	completionQuota := float64(tc.completionTokens) * tc.completionRatio
	ratio := tc.modelRatio * tc.groupRatio
	return (promptQuota + completionQuota) * ratio
}

// TestClaude200KPriceVerification 验证倍率是否正确对应官方价格
// Claude Opus 4.6:
//   ≤ 200K: Input $5/MTok, Output $25/MTok
//   > 200K: Input $10/MTok, Output $37.50/MTok
func TestClaude200KPriceVerification(t *testing.T) {
	// modelRatio 2.5 对应 $5/MTok（因为 ratio 1.0 = $2/MTok）
	modelRatio := 2.5
	completionRatio := 5.0 // $25/$5 = 5

	// 1M input tokens 的价格计算
	inputTokens := 1000000

	// ≤ 200K 时: inputCost = 1M * 2.5 = 2,500,000 (ratio units)
	// 换算成 USD: 2,500,000 / 500,000 = $5.00 ✓
	normalInputCost := float64(inputTokens) * modelRatio
	normalInputUSD := normalInputCost / testQuotaPerUnit
	if math.Abs(normalInputUSD-5.0) > 0.001 {
		t.Errorf("Normal input price per 1M tokens = $%f, want $5.00", normalInputUSD)
	}

	// > 200K 时: inputCost = 1M * 2.5 * 2.0 = 5,000,000 (ratio units)
	// 换算成 USD: 5,000,000 / 500,000 = $10.00 ✓
	higherInputCost := float64(inputTokens) * modelRatio * Claude200KInputMultiplier
	higherInputUSD := higherInputCost / testQuotaPerUnit
	if math.Abs(higherInputUSD-10.0) > 0.001 {
		t.Errorf("Higher input price per 1M tokens = $%f, want $10.00", higherInputUSD)
	}

	// ≤ 200K 时: outputCost = 1M * 5.0 * 2.5 = 12,500,000 (ratio units)
	// 换算成 USD: 12,500,000 / 500,000 = $25.00 ✓
	normalOutputCost := float64(inputTokens) * completionRatio * modelRatio
	normalOutputUSD := normalOutputCost / testQuotaPerUnit
	if math.Abs(normalOutputUSD-25.0) > 0.001 {
		t.Errorf("Normal output price per 1M tokens = $%f, want $25.00", normalOutputUSD)
	}

	// > 200K 时: outputCost = 1M * 5.0 * 2.5 * 1.5 = 18,750,000 (ratio units)
	// 换算成 USD: 18,750,000 / 500,000 = $37.50 ✓
	higherOutputCost := float64(inputTokens) * completionRatio * modelRatio * Claude200KOutputMultiplier
	higherOutputUSD := higherOutputCost / testQuotaPerUnit
	if math.Abs(higherOutputUSD-37.50) > 0.001 {
		t.Errorf("Higher output price per 1M tokens = $%f, want $37.50", higherOutputUSD)
	}

	t.Logf("Price verification passed:")
	t.Logf("  ≤200K: Input $%.2f/MTok, Output $%.2f/MTok", normalInputUSD, normalOutputUSD)
	t.Logf("  >200K: Input $%.2f/MTok, Output $%.2f/MTok", higherInputUSD, higherOutputUSD)
}

// TestClaude200KBoundaryPrecision 精确测试 200K 边界
func TestClaude200KBoundaryPrecision(t *testing.T) {
	model := "claude-opus-4-6-20260120"

	// 刚好 200K - 不触发
	inputMult, outputMult := GetClaude200KMultipliers(model, 200000)
	if inputMult != 1.0 || outputMult != 1.0 {
		t.Errorf("At exactly 200K: inputMult=%f, outputMult=%f, both should be 1.0", inputMult, outputMult)
	}

	// 200001 - 触发
	inputMult, outputMult = GetClaude200KMultipliers(model, 200001)
	if inputMult != 2.0 || outputMult != 1.5 {
		t.Errorf("At 200001: inputMult=%f (want 2.0), outputMult=%f (want 1.5)", inputMult, outputMult)
	}

	// 验证 quota 差异：200000 vs 200001 应该有明显跳变
	tc200K := billingTestCase{
		modelName:          model,
		promptTokens:       200000,
		completionTokens:   1000,
		modelRatio:         2.5,
		completionRatio:    5.0,
		cacheRatio:         0.1,
		cacheCreationRatio: 1.25,
		groupRatio:         1.0,
	}
	tc200K1 := tc200K
	tc200K1.promptTokens = 200001

	quota200K, _, _ := simulateBilling(tc200K)
	quota200K1, _, _ := simulateBilling(tc200K1)

	// 200001 tokens 应该比 200000 tokens 贵接近 2 倍（输入部分）
	t.Logf("Quota at 200K: %f", quota200K)
	t.Logf("Quota at 200K+1: %f", quota200K1)
	t.Logf("Ratio: %f", quota200K1/quota200K)

	if quota200K1 <= quota200K {
		t.Errorf("quota at 200001 (%f) should be > quota at 200000 (%f)", quota200K1, quota200K)
	}

	// 跳变比例应接近 2x（因为输入部分占大多数）
	jumpRatio := quota200K1 / quota200K
	if jumpRatio < 1.5 {
		t.Errorf("Jump ratio at boundary = %f, expected > 1.5 (input doubles)", jumpRatio)
	}
}

// =====================================================================
// Claude 原生端点 (PostClaudeConsumeQuota) 计费测试
// =====================================================================

func TestClaudeNative200KBilling(t *testing.T) {
	tests := []claudeNativeBillingTestCase{
		// ========== 基本场景：无缓存，不触发 200K ==========
		{
			name:               "Native - 100K prompt, no cache, normal rate",
			modelName:          "claude-sonnet-4-20250514",
			promptTokens:       100000,
			completionTokens:   1000,
			modelRatio:         1.5,
			completionRatio:    5.0,
			cacheRatio:         0.1,
			cacheCreationRatio: 1.25,
			groupRatio:         1.0,
			expectHigherRate:   false,
			// promptQuota = 100000
			// completionQuota = 1000 * 5 = 5000
			// quota = (100000 + 5000) * 1.0 * 1.5 = 157500
			expectedQuota: 157500,
		},

		// ========== 真实场景复现：26 prompt + 284516 cache_creation ==========
		{
			name:                "Native - real scenario: 26 prompt + 284516 cache_creation + 54 output",
			modelName:           "claude-sonnet-4-20250514",
			promptTokens:        26,
			cacheCreationTokens: 284516,
			completionTokens:    54,
			modelRatio:          1.5,
			completionRatio:     5.0,
			cacheRatio:          0.1,
			cacheCreationRatio:  1.25,
			groupRatio:          1.0,
			expectHigherRate:    true, // 26 + 284516 = 284542 > 200K
			// promptQuota = 26 + 284516*1.25 = 26 + 355645 = 355671
			// completionQuota = 54 * 5 = 270
			// quota = 355671 * 1.5 * 2.0 + 270 * 1.5 * 1.5
			//       = 1067013 + 607.5 = 1067620.5
			expectedQuota: 1067620.5,
		},

		// ========== 真实场景复现：缓存命中 ==========
		{
			name:               "Native - real scenario: 26 prompt + 284516 cache_read + 55 output",
			modelName:          "claude-sonnet-4-20250514",
			promptTokens:       26,
			cacheTokens:        284516,
			completionTokens:   55,
			modelRatio:         1.5,
			completionRatio:    5.0,
			cacheRatio:         0.1,
			cacheCreationRatio: 1.25,
			groupRatio:         1.0,
			expectHigherRate:   true, // 26 + 284516 = 284542 > 200K
			// promptQuota = 26 + 284516*0.1 = 26 + 28451.6 = 28477.6
			// completionQuota = 55 * 5 = 275
			// quota = 28477.6 * 1.5 * 2.0 + 275 * 1.5 * 1.5
			//       = 85432.8 + 618.75 = 86051.55
			expectedQuota: 86051.55,
		},

		// ========== 5m/1h 分级缓存创建 + 200K 加价 ==========
		{
			name:                  "Native - 5m/1h split cache creation, triggers 200K",
			modelName:             "claude-opus-4-6-20260120",
			promptTokens:          10000,
			cacheCreationTokens:   200000,
			cacheCreationTokens5m: 120000,
			cacheCreationTokens1h: 50000,
			completionTokens:      500,
			modelRatio:            2.5,
			completionRatio:       5.0,
			cacheRatio:            0.1,
			cacheCreationRatio:    1.25,
			cacheCreationRatio5m:  1.25,
			cacheCreationRatio1h:  2.0, // 1h = 5m * 1.6 ≈ 2.0
			groupRatio:            1.0,
			expectHigherRate:      true, // 10000 + 200000 = 210000 > 200K
			// promptQuota = 10000 + 120000*1.25 + 50000*2.0 + (200000-120000-50000)*1.25
			//             = 10000 + 150000 + 100000 + 37500 = 297500
			// completionQuota = 500 * 5 = 2500
			// quota = 297500 * 2.5 * 2.0 + 2500 * 2.5 * 1.5
			//       = 1487500 + 9375 = 1496875
			expectedQuota: 1496875,
		},

		// ========== 5m/1h 分级缓存创建，不触发 200K ==========
		{
			name:                  "Native - 5m/1h split cache creation, under 200K",
			modelName:             "claude-sonnet-4-20250514",
			promptTokens:          10000,
			cacheCreationTokens:   100000,
			cacheCreationTokens5m: 60000,
			cacheCreationTokens1h: 30000,
			completionTokens:      500,
			modelRatio:            1.5,
			completionRatio:       5.0,
			cacheRatio:            0.1,
			cacheCreationRatio:    1.25,
			cacheCreationRatio5m:  1.25,
			cacheCreationRatio1h:  2.0,
			groupRatio:            1.0,
			expectHigherRate:      false, // 10000 + 100000 = 110000 < 200K
			// promptQuota = 10000 + 60000*1.25 + 30000*2.0 + (100000-60000-30000)*1.25
			//             = 10000 + 75000 + 60000 + 12500 = 157500
			// completionQuota = 500 * 5 = 2500
			// quota = (157500 + 2500) * 1.0 * 1.5 = 240000
			expectedQuota: 240000,
		},

		// ========== prompt + cache_read + cache_creation 三者共同超过 200K ==========
		{
			name:                "Native - all three token types contribute to >200K",
			modelName:           "claude-opus-4-5-20251101",
			promptTokens:        50000,
			cacheTokens:         80000,
			cacheCreationTokens: 80000,
			completionTokens:    1000,
			modelRatio:          2.5,
			completionRatio:     5.0,
			cacheRatio:          0.1,
			cacheCreationRatio:  1.25,
			groupRatio:          1.0,
			expectHigherRate:    true, // 50K + 80K + 80K = 210K > 200K
			// promptQuota = 50000 + 80000*0.1 + 80000*1.25 = 50000 + 8000 + 100000 = 158000
			// completionQuota = 1000 * 5 = 5000
			// quota = 158000 * 2.5 * 2.0 + 5000 * 2.5 * 1.5
			//       = 790000 + 18750 = 808750
			expectedQuota: 808750,
		},

		// ========== 边界：刚好 200K 不触发 ==========
		{
			name:                "Native - exactly 200K with cache_creation, normal rate",
			modelName:           "claude-sonnet-4-20250514",
			promptTokens:        100000,
			cacheCreationTokens: 100000,
			completionTokens:    500,
			modelRatio:          1.5,
			completionRatio:     5.0,
			cacheRatio:          0.1,
			cacheCreationRatio:  1.25,
			groupRatio:          1.0,
			expectHigherRate:    false, // 100K + 100K = 200K，不触发
			// promptQuota = 100000 + 100000*1.25 = 225000
			// completionQuota = 500 * 5 = 2500
			// quota = (225000 + 2500) * 1.0 * 1.5 = 341250
			expectedQuota: 341250,
		},

		// ========== 边界：200001 触发 ==========
		{
			name:                "Native - 200001 with cache_creation, triggers higher rate",
			modelName:           "claude-sonnet-4-20250514",
			promptTokens:        100000,
			cacheCreationTokens: 100001,
			completionTokens:    500,
			modelRatio:          1.5,
			completionRatio:     5.0,
			cacheRatio:          0.1,
			cacheCreationRatio:  1.25,
			groupRatio:          1.0,
			expectHigherRate:    true, // 100K + 100001 = 200001 > 200K
			// promptQuota = 100000 + 100001*1.25 = 100000 + 125001.25 = 225001.25
			// completionQuota = 500 * 5 = 2500
			// quota = 225001.25 * 1.5 * 2.0 + 2500 * 1.5 * 1.5
			//       = 675003.75 + 5625 = 680628.75
			expectedQuota: 680628.75,
		},

		// ========== 非 Claude 模型不触发 ==========
		{
			name:                "Native - GPT-4 with cache_creation >200K, no multiplier",
			modelName:           "gpt-4",
			promptTokens:        100000,
			cacheCreationTokens: 150000,
			completionTokens:    1000,
			modelRatio:          15.0,
			completionRatio:     2.0,
			cacheRatio:          0.0,
			cacheCreationRatio:  1.0,
			groupRatio:          1.0,
			expectHigherRate:    false,
			// promptQuota = 100000 + 150000*1.0 = 250000
			// completionQuota = 1000 * 2 = 2000
			// quota = (250000 + 2000) * 1.0 * 15 = 3780000
			expectedQuota: 3780000,
		},

		// ========== 分组倍率 + 200K ==========
		{
			name:                "Native - cache_creation >200K with groupRatio 1.5",
			modelName:           "claude-opus-4-6-20260120",
			promptTokens:        30,
			cacheCreationTokens: 250000,
			completionTokens:    100,
			modelRatio:          2.5,
			completionRatio:     5.0,
			cacheRatio:          0.1,
			cacheCreationRatio:  1.25,
			groupRatio:          1.5,
			expectHigherRate:    true, // 30 + 250000 = 250030 > 200K
			// promptQuota = 30 + 250000*1.25 = 30 + 312500 = 312530
			// completionQuota = 100 * 5 = 500
			// ratio = 2.5 * 1.5 = 3.75
			// quota = 312530 * 3.75 * 2.0 + 500 * 3.75 * 1.5
			//       = 2343975 + 2812.5 = 2346787.5
			expectedQuota: 2346787.5,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			quota, inputMult, outputMult := simulateClaudeNativeBilling(tt)

			// 验证是否触发 >200K 倍率
			isHigherRate := (inputMult != 1.0 || outputMult != 1.0)
			if isHigherRate != tt.expectHigherRate {
				totalInput := tt.promptTokens + tt.cacheTokens + tt.cacheCreationTokens
				t.Errorf("higher rate triggered = %v, want %v (totalInput=%d, inputMult=%f, outputMult=%f)",
					isHigherRate, tt.expectHigherRate, totalInput, inputMult, outputMult)
			}

			// 验证 quota 计算结果（允许浮点精度误差 0.01）
			if math.Abs(quota-tt.expectedQuota) > 0.01 {
				t.Errorf("quota = %f, want %f (diff=%f)",
					quota, tt.expectedQuota, quota-tt.expectedQuota)
			}

			// 验证 >200K 时的倍率值
			if tt.expectHigherRate {
				if inputMult != Claude200KInputMultiplier {
					t.Errorf("inputMult = %f, want %f", inputMult, Claude200KInputMultiplier)
				}
				if outputMult != Claude200KOutputMultiplier {
					t.Errorf("outputMult = %f, want %f", outputMult, Claude200KOutputMultiplier)
				}
			}
		})
	}
}

// TestClaudeNative200KTotalInputCalculation 专门验证 totalInput 的计算方式
// 确保 promptTokens + cacheTokens + cacheCreationTokens 都参与阈值判断
func TestClaudeNative200KTotalInputCalculation(t *testing.T) {
	model := "claude-sonnet-4-20250514"

	tests := []struct {
		name                string
		prompt              int
		cacheRead           int
		cacheCreation       int
		expectedTotal       int
		expectHigherRate    bool
	}{
		{"only prompt 200K", 200000, 0, 0, 200000, false},
		{"only prompt 200001", 200001, 0, 0, 200001, true},
		{"only cache_read 200K", 0, 200000, 0, 200000, false},
		{"only cache_read 200001", 0, 200001, 0, 200001, true},
		{"only cache_creation 200K", 0, 0, 200000, 200000, false},
		{"only cache_creation 200001", 0, 0, 200001, 200001, true},
		{"mixed exactly 200K", 100000, 50000, 50000, 200000, false},
		{"mixed 200001", 100000, 50000, 50001, 200001, true},
		{"real scenario: tiny prompt + large creation", 26, 0, 284516, 284542, true},
		{"real scenario: tiny prompt + large read", 26, 284516, 0, 284542, true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			total := tt.prompt + tt.cacheRead + tt.cacheCreation
			if total != tt.expectedTotal {
				t.Errorf("total = %d, want %d", total, tt.expectedTotal)
			}

			inputMult, outputMult := GetClaude200KMultipliers(model, total)
			isHigherRate := (inputMult != 1.0 || outputMult != 1.0)
			if isHigherRate != tt.expectHigherRate {
				t.Errorf("higher rate = %v, want %v (total=%d)", isHigherRate, tt.expectHigherRate, total)
			}
		})
	}
}
