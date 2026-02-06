package ratio_setting

import (
	"math"
	"testing"
)

// 模拟 compatible_handler.go 中 ratio 计费分支的计算逻辑
// 用于集成验证 Claude 200K 倍率对最终 quota 的影响
//
// 计费公式:
//   正常: quota = (promptQuota + completionQuota) * modelRatio * groupRatio
//   Claude >200K: quota = promptQuota * modelRatio * groupRatio * inputMult
//                       + completionQuota * modelRatio * groupRatio * outputMult
//
// 其中:
//   promptQuota = promptTokens（减去缓存后的实际输入 tokens + 缓存 tokens * cacheRatio）
//   completionQuota = completionTokens * completionRatio

const (
	testQuotaPerUnit = 500 * 1000.0 // 与 common.QuotaPerUnit 一致
)

type billingTestCase struct {
	name             string
	modelName        string
	promptTokens     int     // 实际输入 tokens（不含缓存）
	cacheTokens      int     // 缓存 tokens
	completionTokens int     // 输出 tokens
	modelRatio       float64 // 模型倍率
	completionRatio  float64 // 输出倍率
	cacheRatio       float64 // 缓存命中倍率
	groupRatio       float64 // 分组倍率

	// 期望值
	expectHigherRate bool    // 是否预期触发 >200K 倍率
	expectedQuota    float64 // 期望的 quota（允许浮点误差）
}

// simulateBilling 模拟 compatible_handler.go 中 ratio 计费分支的计算
func simulateBilling(tc billingTestCase) (quota float64, inputMult float64, outputMult float64) {
	// 计算 promptQuota（模拟 Anthropic 频道，promptTokens 不含缓存）
	baseTokens := float64(tc.promptTokens)
	cachedTokensWithRatio := float64(tc.cacheTokens) * tc.cacheRatio
	promptQuota := baseTokens + cachedTokensWithRatio

	// 计算 completionQuota
	completionQuota := float64(tc.completionTokens) * tc.completionRatio

	// 计算 ratio
	ratio := tc.modelRatio * tc.groupRatio

	// Claude 200K 倍率
	totalInputTokens := tc.promptTokens + tc.cacheTokens
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

func TestClaude200KBillingIntegration(t *testing.T) {
	tests := []billingTestCase{
		// ========== Claude Opus 4.6 (modelRatio=2.5, completionRatio=5) ==========
		// $5/MTok input, $25/MTok output
		{
			name:             "Claude Opus 4.6 - 100K tokens, normal rate",
			modelName:        "claude-opus-4-6-20260120",
			promptTokens:     100000,
			cacheTokens:      0,
			completionTokens: 1000,
			modelRatio:       2.5,
			completionRatio:  5.0,
			cacheRatio:       0.1,
			groupRatio:       1.0,
			expectHigherRate: false,
			// quota = (100000 + 1000*5) * 2.5 = 105000 * 2.5 = 262500
			expectedQuota: 262500,
		},
		{
			name:             "Claude Opus 4.6 - exactly 200K tokens, normal rate (boundary)",
			modelName:        "claude-opus-4-6-20260120",
			promptTokens:     200000,
			cacheTokens:      0,
			completionTokens: 1000,
			modelRatio:       2.5,
			completionRatio:  5.0,
			cacheRatio:       0.1,
			groupRatio:       1.0,
			expectHigherRate: false,
			// quota = (200000 + 1000*5) * 2.5 = 205000 * 2.5 = 512500
			expectedQuota: 512500,
		},
		{
			name:             "Claude Opus 4.6 - 200001 tokens, higher rate (just over)",
			modelName:        "claude-opus-4-6-20260120",
			promptTokens:     200001,
			cacheTokens:      0,
			completionTokens: 1000,
			modelRatio:       2.5,
			completionRatio:  5.0,
			cacheRatio:       0.1,
			groupRatio:       1.0,
			expectHigherRate: true,
			// quota = 200001 * 2.5 * 2.0 + 1000 * 5 * 2.5 * 1.5
			//       = 1000005 + 18750 = 1018755
			expectedQuota: 1018755,
		},
		{
			name:             "Claude Opus 4.6 - 300K tokens, higher rate",
			modelName:        "claude-opus-4-6-20260120",
			promptTokens:     300000,
			cacheTokens:      0,
			completionTokens: 2000,
			modelRatio:       2.5,
			completionRatio:  5.0,
			cacheRatio:       0.1,
			groupRatio:       1.0,
			expectHigherRate: true,
			// quota = 300000 * 2.5 * 2.0 + 2000 * 5 * 2.5 * 1.5
			//       = 1500000 + 37500 = 1537500
			expectedQuota: 1537500,
		},

		// ========== 缓存场景 ==========
		{
			name:             "Claude - 150K prompt + 60K cache = 210K total, triggers higher rate",
			modelName:        "claude-opus-4-5-20251101",
			promptTokens:     150000,
			cacheTokens:      60000,
			completionTokens: 500,
			modelRatio:       2.5,
			completionRatio:  5.0,
			cacheRatio:       0.1,
			groupRatio:       1.0,
			expectHigherRate: true,
			// promptQuota = 150000 + 60000*0.1 = 156000
			// completionQuota = 500 * 5 = 2500
			// quota = 156000 * 2.5 * 2.0 + 2500 * 2.5 * 1.5
			//       = 780000 + 9375 = 789375
			expectedQuota: 789375,
		},
		{
			name:             "Claude - 100K prompt + 90K cache = 190K total, normal rate",
			modelName:        "claude-sonnet-4-20250514",
			promptTokens:     100000,
			cacheTokens:      90000,
			completionTokens: 500,
			modelRatio:       1.5,
			completionRatio:  5.0,
			cacheRatio:       0.1,
			groupRatio:       1.0,
			expectHigherRate: false,
			// promptQuota = 100000 + 90000*0.1 = 109000
			// completionQuota = 500 * 5 = 2500
			// quota = (109000 + 2500) * 1.5 = 167250
			expectedQuota: 167250,
		},

		// ========== 分组倍率场景 ==========
		{
			name:             "Claude >200K with groupRatio 1.5",
			modelName:        "claude-opus-4-6-20260120",
			promptTokens:     250000,
			cacheTokens:      0,
			completionTokens: 1000,
			modelRatio:       2.5,
			completionRatio:  5.0,
			cacheRatio:       0.1,
			groupRatio:       1.5,
			expectHigherRate: true,
			// ratio = 2.5 * 1.5 = 3.75
			// quota = 250000 * 3.75 * 2.0 + 1000 * 5 * 3.75 * 1.5
			//       = 1875000 + 28125 = 1903125
			expectedQuota: 1903125,
		},

		// ========== 非 Claude 模型 - 超过 200K 也不触发 ==========
		{
			name:             "GPT-4 - 300K tokens, no multiplier",
			modelName:        "gpt-4",
			promptTokens:     300000,
			cacheTokens:      0,
			completionTokens: 1000,
			modelRatio:       15.0,
			completionRatio:  2.0,
			cacheRatio:       0.0,
			groupRatio:       1.0,
			expectHigherRate: false,
			// quota = (300000 + 1000*2) * 15 = 302000 * 15 = 4530000
			expectedQuota: 4530000,
		},

		// ========== Claude Sonnet 模型 ==========
		{
			name:             "Claude Sonnet 4.5 - 250K tokens, higher rate",
			modelName:        "claude-sonnet-4-5-20250929",
			promptTokens:     250000,
			cacheTokens:      0,
			completionTokens: 2000,
			modelRatio:       1.5,
			completionRatio:  5.0,
			cacheRatio:       0.1,
			groupRatio:       1.0,
			expectHigherRate: true,
			// quota = 250000 * 1.5 * 2.0 + 2000 * 5 * 1.5 * 1.5
			//       = 750000 + 22500 = 772500
			expectedQuota: 772500,
		},

		// ========== 极端情况 ==========
		{
			name:             "Claude - 0 prompt, 0 completion, 0 cache",
			modelName:        "claude-opus-4-6-20260120",
			promptTokens:     0,
			cacheTokens:      0,
			completionTokens: 0,
			modelRatio:       2.5,
			completionRatio:  5.0,
			cacheRatio:       0.1,
			groupRatio:       1.0,
			expectHigherRate: false,
			expectedQuota:    0,
		},
		{
			name:             "Claude - only cache tokens, 0+201K cache = 201K total",
			modelName:        "claude-opus-4-6-20260120",
			promptTokens:     0,
			cacheTokens:      201000,
			completionTokens: 100,
			modelRatio:       2.5,
			completionRatio:  5.0,
			cacheRatio:       0.1,
			groupRatio:       1.0,
			expectHigherRate: true,
			// promptQuota = 0 + 201000*0.1 = 20100
			// completionQuota = 100 * 5 = 500
			// quota = 20100 * 2.5 * 2.0 + 500 * 2.5 * 1.5
			//       = 100500 + 1875 = 102375
			expectedQuota: 102375,
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
	promptQuota := baseTokens + cachedTokensWithRatio
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
		modelName:        model,
		promptTokens:     200000,
		completionTokens: 1000,
		modelRatio:       2.5,
		completionRatio:  5.0,
		cacheRatio:       0.1,
		groupRatio:       1.0,
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
