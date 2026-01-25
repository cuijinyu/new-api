package kling

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/QuantumNous/new-api/constant"
	relaycommon "github.com/QuantumNous/new-api/relay/common"
	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// ============================================================================
// 可灵扣费端到端测试 - 基于官方价格表和 demoscripts 真实场景
//
// 官方价格表（2026年1月）:
// ============================================================================
//
// Video-O1 模型（按秒计费）:
//   - Std 无参考视频: 0.6元/秒
//   - Std 有参考视频: 0.9元/秒
//   - Pro 无参考视频: 0.8元/秒
//   - Pro 有参考视频: 1.2元/秒
//
// V1 模型:
//   - Std 5s=1元, 10s=2元 → 每秒0.2元
//   - Pro 5s=3.5元, 10s=7元 → 每秒0.7元
//
// V1.5 模型:
//   - Std 5s=2元, 10s=4元 → 每秒0.4元
//   - Pro 5s=3.5元, 10s=7元 → 每秒0.7元
//
// V1.6 模型:
//   - Std 5s=2元, 10s=4元 → 每秒0.4元
//   - Pro 5s=3.5元, 10s=7元 → 每秒0.7元
//
// V1.6 多图参考生视频:
//   - Std 5s=2元, 10s=4元 → 每秒0.4元
//   - Pro 5s=3.5元, 10s=7元 → 每秒0.7元
//
// V2.0 大师版: 5s=10元, 10s=20元 → 每秒2元
//
// V2.1 模型:
//   - Std 5s=2元, 10s=4元 → 每秒0.4元
//   - Pro 5s=3.5元, 10s=7元 → 每秒0.7元
//
// V2.1 大师版: 5s=10元, 10s=20元 → 每秒2元
//
// V2.5 turbo:
//   - Std 5s=1.5元, 10s=3元 → 每秒0.3元
//   - Pro 5s=2.5元, 10s=5元 → 每秒0.5元
//
// V2.6 模型:
//   - Pro 无声: 5s=2.5元, 10s=5元 → 每秒0.5元
//   - Pro 有声: 5s=5元, 10s=10元 → 每秒1元
//   - Pro 有声+音色: 5s=6元, 10s=12元 → 每秒1.2元
//
// V2.6 动作控制:
//   - Std: 0.5元/秒
//   - Pro: 0.8元/秒
//
// 多模态视频编辑 (V1.6):
//   - Std 5s=3元, 10s=6元 → 每秒0.6元
//   - Pro 5s=5元, 10s=10元 → 每秒1元
//
// 视频延长（按次计费）:
//   - V1 Std: 1元/次, Pro: 3.5元/次
//   - V1.5 Std: 2元/次, Pro: 3.5元/次
//   - V1.6 Std: 2元/次, Pro: 3.5元/次
//
// 对口型: 每5秒0.5元，不足5秒按5秒计算
//
// ============================================================================

// OfficialPricePerSecond 官方每秒价格（元/秒）
var OfficialPricePerSecond = map[string]map[string]float64{
	// Video-O1 无视频输入
	"kling-video-o1": {
		"std":           0.6,
		"pro":           0.8,
		"std_with_video": 0.9,
		"pro_with_video": 1.2,
	},
	// V1 模型
	"kling-v1": {
		"std": 0.2, // 5s=1元
		"pro": 0.7, // 5s=3.5元
	},
	// V1.5 模型
	"kling-v1-5": {
		"std": 0.4, // 5s=2元
		"pro": 0.7, // 5s=3.5元
	},
	// V1.6 模型
	"kling-v1-6": {
		"std": 0.4, // 5s=2元
		"pro": 0.7, // 5s=3.5元
	},
	// V2.1 模型
	"kling-v2-1": {
		"std": 0.4, // 5s=2元
		"pro": 0.7, // 5s=3.5元
	},
	// V2.5 turbo
	"kling-v2-5-turbo": {
		"std": 0.3, // 5s=1.5元
		"pro": 0.5, // 5s=2.5元
	},
	// V2.6 模型 (Pro only, 无声)
	"kling-v2-6": {
		"std":                    0.5,  // 等同 pro 无声
		"pro":                    0.5,  // 无声: 5s=2.5元
		"pro_with_sound":         1.0,  // 有声: 5s=5元
		"pro_with_voice_control": 1.2,  // 有声+音色: 5s=6元
	},
	// V2.0 大师版
	"kling-v2-master": {
		"master": 2.0, // 5s=10元
	},
	// V2.1 大师版
	"kling-v2-1-master": {
		"master": 2.0, // 5s=10元
	},
}

// OfficialMotionControlPrice V2.6 动作控制价格（元/秒）
var OfficialMotionControlPrice = map[string]float64{
	"std": 0.5,
	"pro": 0.8,
}

// OfficialMultiElementsPrice 多模态视频编辑价格（元/秒）
var OfficialMultiElementsPrice = map[string]float64{
	"std": 0.6, // 5s=3元
	"pro": 1.0, // 5s=5元
}

// OfficialVideoExtendPrice 视频延长价格（元/次）
var OfficialVideoExtendPrice = map[string]map[string]float64{
	"kling-v1": {
		"std": 1.0,
		"pro": 3.5,
	},
	"kling-v1-5": {
		"std": 2.0,
		"pro": 3.5,
	},
	"kling-v1-6": {
		"std": 2.0,
		"pro": 3.5,
	},
}

// OfficialLipSyncPrice 对口型价格（元/5秒）
const OfficialLipSyncPricePerUnit = 0.5 // 每5秒0.5元

// ModelPriceMap 模型固定价格配置（内部计价单位，对应系统配置）
var ModelPriceMap = map[string]float64{
	"kling-video-o1":    0.084,
	"kling-v2-6":        0.07,
	"kling-v2-5-turbo":  0.042,
	"kling-v2-1":        0.056,
	"kling-v2-1-master": 0.28,
	"kling-v2-master":   0.28,
	"kling-v1-6":        0.056,
	"kling-v1-5":        0.056,
	"kling-v1":          0.028,
}

// SpecialModelPriceMap 特殊功能的 ModelPrice 配置
var SpecialModelPriceMap = map[string]float64{
	"multi_elements": 0.084, // 多模态编辑: 0.6元/秒 × 0.14 = 0.084
	"video_extend":   0.14,  // 视频延长: 使 PriceScale 直接等于官方价格
	"lip_sync":       0.14,  // 对口型: 使 PriceScale 直接等于官方价格
	"identify_face":  0.14,  // 人脸识别
}

const testPriceRatio = 0.14

// BillingResult 扣费计算结果
type BillingResult struct {
	PreDeductPriceScale float32
	PreDeductAmount     float64
	UnitPriceScale      float32
	ActualDuration      float64
	FinalPriceScale     float64
	FinalAmount         float64
	RefundAmount        float64
}

// E2EBillingTestCase 端到端扣费测试用例
type E2EBillingTestCase struct {
	Name                   string
	Description            string
	Action                 string
	Model                  string
	Mode                   string
	Duration               int
	Prompt                 string
	Metadata               map[string]interface{}
	MockTaskID             string
	MockVideoDuration      string
	ExpectedPreDeductScale float64
	ExpectedUnitScale      float64
	ExpectedOfficialPrice  float64
}

// runE2EBillingTestWithoutPriceCheck 执行端到端扣费测试（不验证官方价格）
func runE2EBillingTestWithoutPriceCheck(t *testing.T, tc E2EBillingTestCase) BillingResult {
	tc.ExpectedOfficialPrice = 0
	return runE2EBillingTest(t, tc)
}

// runE2EBillingTest 执行端到端扣费测试
func runE2EBillingTest(t *testing.T, tc E2EBillingTestCase) BillingResult {
	adaptor := &TaskAdaptor{}
	gin.SetMode(gin.TestMode)

	c, _ := gin.CreateTestContext(httptest.NewRecorder())
	req := relaycommon.TaskSubmitReq{
		Model:    tc.Model,
		Mode:     tc.Mode,
		Duration: tc.Duration,
		Prompt:   tc.Prompt,
		Metadata: tc.Metadata,
	}
	c.Set("task_request", req)
	c.Set("action", tc.Action)

	info := &relaycommon.RelayInfo{
		TaskRelayInfo: &relaycommon.TaskRelayInfo{
			Action: tc.Action,
		},
	}

	preDeductScale, err := adaptor.GetPriceScale(c, info)
	require.NoError(t, err, "GetPriceScale 不应返回错误")

	modelPrice := ModelPriceMap[tc.Model]
	preDeductAmount := modelPrice * float64(preDeductScale)

	unitScale, err := adaptor.GetUnitPriceScale(c, info)
	require.NoError(t, err, "GetUnitPriceScale 不应返回错误")

	var actualDuration float64
	if tc.MockVideoDuration != "" {
		fmt.Sscanf(tc.MockVideoDuration, "%f", &actualDuration)
	} else {
		actualDuration = float64(tc.Duration)
	}

	var finalPriceScale float64
	var finalAmount float64

	if tc.Action == constant.TaskActionAdvancedLipSync ||
		tc.Action == constant.TaskActionIdentifyFace {
		finalPriceScale = float64(preDeductScale)
		finalAmount = preDeductAmount
	} else {
		finalPriceScale = float64(unitScale) * actualDuration
		finalAmount = modelPrice * finalPriceScale
	}

	refundAmount := preDeductAmount - finalAmount
	if refundAmount < 0 {
		refundAmount = 0
	}

	result := BillingResult{
		PreDeductPriceScale: preDeductScale,
		PreDeductAmount:     preDeductAmount,
		UnitPriceScale:      unitScale,
		ActualDuration:      actualDuration,
		FinalPriceScale:     finalPriceScale,
		FinalAmount:         finalAmount,
		RefundAmount:        refundAmount,
	}

	if tc.ExpectedPreDeductScale > 0 {
		assert.InDelta(t, tc.ExpectedPreDeductScale, float64(preDeductScale), 0.01,
			"预扣倍率不匹配")
	}
	if tc.ExpectedUnitScale > 0 {
		assert.InDelta(t, tc.ExpectedUnitScale, float64(unitScale), 0.01,
			"单价倍率不匹配")
	}
	if tc.ExpectedOfficialPrice > 0 {
		calculatedOfficialPrice := finalAmount / testPriceRatio
		assert.InDelta(t, tc.ExpectedOfficialPrice, calculatedOfficialPrice, 0.1,
			"官方价格不匹配: 计算=%.2f, 期望=%.2f", calculatedOfficialPrice, tc.ExpectedOfficialPrice)
	}

	return result
}

// ============================================================================
// demoscripts/test_kling.py 场景测试
// ============================================================================

func TestE2E_TestKling_Text2Video_V26_Pro_5s(t *testing.T) {
	// test_kling.py: kling-v2-6 Pro 5s 文生视频
	// 官方价格: Pro 无声 5s = 2.5元

	tc := E2EBillingTestCase{
		Name:        "Text2Video_V26_Pro_5s",
		Description: "demoscripts/test_kling.py - V2.6 Pro 文生视频 5s 无声",
		Action:      constant.TaskActionGenerate,
		Model:       "kling-v2-6",
		Mode:        "pro",
		Duration:    5,
		Prompt:      "A cute cat running in the garden",

		MockVideoDuration: "5.0",

		ExpectedPreDeductScale: 5.0, // 5s × proScale(1.0)
		ExpectedUnitScale:      1.0,
		ExpectedOfficialPrice:  2.5, // 5s × 0.5元/秒
	}

	result := runE2EBillingTest(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: V2.6 Pro 无声 5s = 2.5元")
	t.Logf("ModelPrice: %.3f, PriceScale: %.2f", ModelPriceMap[tc.Model], result.PreDeductPriceScale)
	t.Logf("计算扣费: %.4f, 还原官方价格: %.2f 元", result.FinalAmount, result.FinalAmount/testPriceRatio)
}

func TestE2E_TestKling_MotionControl_V26_Std(t *testing.T) {
	// test_kling.py: Motion Control Std
	// 官方价格: Std 0.5元/秒，预估10s = 5元

	tc := E2EBillingTestCase{
		Name:        "MotionControl_V26_Std",
		Description: "demoscripts/test_kling.py - V2.6 Motion Control Std",
		Action:      constant.TaskActionMotionControl,
		Model:       "kling-v2-6",
		Mode:        "std",
		Prompt:      "The character follows the movement",
		Metadata: map[string]interface{}{
			"character_orientation": "image",
		},

		MockVideoDuration: "8.5",

		ExpectedPreDeductScale: 10.0, // 预扣最大 10s
		ExpectedUnitScale:      1.0,
		ExpectedOfficialPrice:  4.25, // 8.5s × 0.5元/秒
	}

	result := runE2EBillingTest(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: V2.6 动作控制 Std = 0.5元/秒")
	t.Logf("预扣 10s = %.2f 元, 实际 %.1fs = %.2f 元",
		10*OfficialMotionControlPrice["std"],
		result.ActualDuration,
		result.ActualDuration*OfficialMotionControlPrice["std"])
}

// ============================================================================
// demoscripts/test_kling_multi_elements.py 场景测试
// ============================================================================

func TestE2E_MultiElements_Addition_Std_5s(t *testing.T) {
	// 多模态编辑 Std 5s = 3元
	tc := E2EBillingTestCase{
		Name:        "MultiElements_Addition_Std_5s",
		Description: "demoscripts/test_kling_multi_elements.py - 增加元素 Std 5s",
		Action:      constant.TaskActionMultiElementsCreate,
		Model:       "kling-v1-6",
		Mode:        "std",
		Prompt:      "将猫咪融入画面右侧",
		Metadata: map[string]interface{}{
			"session_id": "mock_session",
			"edit_mode":  "addition",
			"duration":   "5",
			"image_list": []interface{}{
				map[string]interface{}{"image": "https://example.com/cat.jpg"},
			},
		},

		MockVideoDuration:      "5.0",
		ExpectedPreDeductScale: 5.0,
		ExpectedUnitScale:      1.0,
	}

	result := runE2EBillingTestWithoutPriceCheck(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: 多模态编辑 Std 5s = 3元 (0.6元/秒)")

	// 多模态编辑需要专用 ModelPrice
	correctModelPrice := SpecialModelPriceMap["multi_elements"]
	correctFinalAmount := correctModelPrice * float64(result.PreDeductPriceScale)
	correctOfficialPrice := correctFinalAmount / testPriceRatio

	t.Logf(">>> 需要配置 ModelPrice=%.3f <<<", correctModelPrice)
	t.Logf("正确扣费: %.4f, 还原官方价格: %.2f 元", correctFinalAmount, correctOfficialPrice)
	assert.InDelta(t, 3.0, correctOfficialPrice, 0.1, "多模态编辑 Std 5s 应为 3元")
}

func TestE2E_MultiElements_Pro_10s(t *testing.T) {
	// 多模态编辑 Pro 10s = 10元
	tc := E2EBillingTestCase{
		Name:   "MultiElements_Pro_10s",
		Action: constant.TaskActionMultiElementsCreate,
		Model:  "kling-v1-6",
		Mode:   "pro",
		Prompt: "删除人物",
		Metadata: map[string]interface{}{
			"session_id": "mock_session",
			"edit_mode":  "removal",
			"duration":   "10",
		},

		MockVideoDuration:      "10.0",
		ExpectedPreDeductScale: 10.0 * (5.0 / 3.0), // 16.67
		ExpectedUnitScale:      5.0 / 3.0,
	}

	result := runE2EBillingTestWithoutPriceCheck(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: 多模态编辑 Pro 10s = 10元 (1.0元/秒)")

	correctModelPrice := SpecialModelPriceMap["multi_elements"]
	correctFinalAmount := correctModelPrice * float64(result.PreDeductPriceScale)
	correctOfficialPrice := correctFinalAmount / testPriceRatio

	t.Logf(">>> 需要配置 ModelPrice=%.3f <<<", correctModelPrice)
	t.Logf("正确扣费: %.4f, 还原官方价格: %.2f 元", correctFinalAmount, correctOfficialPrice)
	assert.InDelta(t, 10.0, correctOfficialPrice, 0.1, "多模态编辑 Pro 10s 应为 10元")
}

// ============================================================================
// demoscripts/test_kling_lip_sync.py 场景测试
// ============================================================================

func TestE2E_LipSync_5s(t *testing.T) {
	// 对口型: 每5秒0.5元
	tc := E2EBillingTestCase{
		Name:   "LipSync_5s",
		Action: constant.TaskActionAdvancedLipSync,
		Model:  "kling-v1-6",
		Metadata: map[string]interface{}{
			"session_id": "mock_session",
			"face_choose": []interface{}{
				map[string]interface{}{
					"face_id":           "face_001",
					"audio_id":          "audio_001",
					"sound_start_time":  int64(0),
					"sound_end_time":    int64(5000),
					"sound_insert_time": int64(0),
				},
			},
		},

		ExpectedPreDeductScale: 0.5, // 1单位 × 0.5
	}

	result := runE2EBillingTestWithoutPriceCheck(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: 对口型 每5秒0.5元")
	t.Logf("5秒音频 = 1单位 × 0.5元 = 0.5元")

	correctModelPrice := SpecialModelPriceMap["lip_sync"]
	correctFinalAmount := correctModelPrice * float64(result.PreDeductPriceScale)
	correctOfficialPrice := correctFinalAmount / testPriceRatio

	t.Logf(">>> 需要配置 ModelPrice=%.3f <<<", correctModelPrice)
	t.Logf("正确扣费: %.4f, 还原官方价格: %.2f 元", correctFinalAmount, correctOfficialPrice)
	assert.InDelta(t, 0.5, correctOfficialPrice, 0.05, "对口型 5s 应为 0.5元")
}

func TestE2E_LipSync_12s(t *testing.T) {
	// 对口型: 12秒 → ceil(12/5)=3单位 × 0.5元 = 1.5元
	tc := E2EBillingTestCase{
		Name:   "LipSync_12s",
		Action: constant.TaskActionAdvancedLipSync,
		Model:  "kling-v1-6",
		Metadata: map[string]interface{}{
			"session_id": "mock_session",
			"face_choose": []interface{}{
				map[string]interface{}{
					"face_id":           "face_001",
					"audio_id":          "audio_001",
					"sound_start_time":  int64(0),
					"sound_end_time":    int64(12000),
					"sound_insert_time": int64(0),
				},
			},
		},

		ExpectedPreDeductScale: 1.5, // 3单位 × 0.5
	}

	result := runE2EBillingTestWithoutPriceCheck(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: 对口型 每5秒0.5元，不足5秒按5秒计算")
	t.Logf("12秒音频 → ceil(12/5)=3单位 × 0.5元 = 1.5元")

	correctModelPrice := SpecialModelPriceMap["lip_sync"]
	correctFinalAmount := correctModelPrice * float64(result.PreDeductPriceScale)
	correctOfficialPrice := correctFinalAmount / testPriceRatio

	t.Logf("正确扣费: %.4f, 还原官方价格: %.2f 元", correctFinalAmount, correctOfficialPrice)
	assert.InDelta(t, 1.5, correctOfficialPrice, 0.1, "对口型 12s 应为 1.5元")
}

// ============================================================================
// demoscripts/test_kling_video_extend.py 场景测试
// ============================================================================

func TestE2E_VideoExtend_V16_Std(t *testing.T) {
	// 视频延长 V1.6 Std = 2元/次
	tc := E2EBillingTestCase{
		Name:   "VideoExtend_V16_Std",
		Action: constant.TaskActionVideoExtend,
		Model:  "kling-v1-6",
		Mode:   "std",
		Metadata: map[string]interface{}{
			"video_id": "mock_video",
		},

		ExpectedPreDeductScale: 2.0, // V1.6 Std
		ExpectedUnitScale:      2.0,
	}

	result := runE2EBillingTestWithoutPriceCheck(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: 视频延长 V1.6 Std = 2元/次")

	correctModelPrice := SpecialModelPriceMap["video_extend"]
	correctFinalAmount := correctModelPrice * float64(result.PreDeductPriceScale)
	correctOfficialPrice := correctFinalAmount / testPriceRatio

	t.Logf(">>> 需要配置 ModelPrice=%.3f <<<", correctModelPrice)
	t.Logf("正确扣费: %.4f, 还原官方价格: %.2f 元", correctFinalAmount, correctOfficialPrice)
	assert.InDelta(t, 2.0, correctOfficialPrice, 0.1, "视频延长 V1.6 Std 应为 2元")
}

func TestE2E_VideoExtend_V1_Pro(t *testing.T) {
	// 视频延长 V1 Pro = 3.5元/次
	tc := E2EBillingTestCase{
		Name:   "VideoExtend_V1_Pro",
		Action: constant.TaskActionVideoExtend,
		Model:  "kling-v1",
		Mode:   "pro",
		Metadata: map[string]interface{}{
			"video_id": "mock_video",
		},

		ExpectedPreDeductScale: 3.5, // V1 Std(1.0) × Pro(3.5)
	}

	result := runE2EBillingTestWithoutPriceCheck(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: 视频延长 V1 Pro = 3.5元/次")

	correctModelPrice := SpecialModelPriceMap["video_extend"]
	correctFinalAmount := correctModelPrice * float64(result.PreDeductPriceScale)
	correctOfficialPrice := correctFinalAmount / testPriceRatio

	t.Logf("正确扣费: %.4f, 还原官方价格: %.2f 元", correctFinalAmount, correctOfficialPrice)
	assert.InDelta(t, 3.5, correctOfficialPrice, 0.1, "视频延长 V1 Pro 应为 3.5元")
}

// ============================================================================
// demoscripts/test_kling_multi_image.py 场景测试
// ============================================================================

func TestE2E_MultiImage2Video_V16_Std_5s(t *testing.T) {
	// 多图生视频 V1.6 Std 5s = 2元
	tc := E2EBillingTestCase{
		Name:     "MultiImage2Video_V16_Std_5s",
		Action:   constant.TaskActionMultiImage2Video,
		Model:    "kling-v1-6",
		Mode:     "std",
		Duration: 5,
		Prompt:   "Characters dancing together",
		Metadata: map[string]interface{}{
			"duration": "5",
			"image_list": []interface{}{
				map[string]interface{}{"image": "https://example.com/img1.jpg"},
				map[string]interface{}{"image": "https://example.com/img2.jpg"},
			},
		},

		MockVideoDuration:      "5.0",
		ExpectedPreDeductScale: 5.0,
		ExpectedUnitScale:      1.0,
		ExpectedOfficialPrice:  2.0, // 5s × 0.4元/秒
	}

	result := runE2EBillingTest(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: V1.6多图参考生视频 Std 5s = 2元 (0.4元/秒)")
	t.Logf("计算扣费: %.4f, 还原官方价格: %.2f 元", result.FinalAmount, result.FinalAmount/testPriceRatio)
}

func TestE2E_MultiImage2Video_V16_Pro_10s(t *testing.T) {
	// 多图生视频 V1.6 Pro 10s = 7元
	tc := E2EBillingTestCase{
		Name:     "MultiImage2Video_V16_Pro_10s",
		Action:   constant.TaskActionMultiImage2Video,
		Model:    "kling-v1-6",
		Mode:     "pro",
		Duration: 10,
		Prompt:   "test",
		Metadata: map[string]interface{}{
			"duration": "10",
			"image_list": []interface{}{
				map[string]interface{}{"image": "https://example.com/img.jpg"},
			},
		},

		MockVideoDuration:      "10.0",
		ExpectedPreDeductScale: 17.5, // 10s × proScale(1.75)
		ExpectedUnitScale:      1.75,
		ExpectedOfficialPrice:  7.0, // 10s × 0.7元/秒
	}

	result := runE2EBillingTest(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: V1.6多图参考生视频 Pro 10s = 7元 (0.7元/秒)")
	t.Logf("计算扣费: %.4f, 还原官方价格: %.2f 元", result.FinalAmount, result.FinalAmount/testPriceRatio)
}

// ============================================================================
// demoscripts/test_kling_image_tail.py 场景测试
// ============================================================================

func TestE2E_ImageTail_V26_Std_5s(t *testing.T) {
	// 首尾帧图生视频 V2.6 Std 5s = 2.5元 (无声)
	tc := E2EBillingTestCase{
		Name:     "ImageTail_V26_Std_5s",
		Action:   constant.TaskActionGenerate,
		Model:    "kling-v2-6",
		Mode:     "std",
		Duration: 5,
		Prompt:   "Characters dancing",
		Metadata: map[string]interface{}{
			"image":      "https://example.com/first.jpg",
			"image_tail": "https://example.com/last.jpg",
		},

		MockVideoDuration:      "5.0",
		ExpectedPreDeductScale: 5.0,
		ExpectedUnitScale:      1.0,
		ExpectedOfficialPrice:  2.5, // 5s × 0.5元/秒
	}

	result := runE2EBillingTest(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: V2.6 无声 5s = 2.5元 (0.5元/秒)")
	t.Logf("计算扣费: %.4f, 还原官方价格: %.2f 元", result.FinalAmount, result.FinalAmount/testPriceRatio)
}

// ============================================================================
// 高级功能测试: V2.6 音频和音色控制
// ============================================================================

func TestE2E_V26_Pro_WithSound_5s(t *testing.T) {
	// V2.6 Pro 有声 5s = 5元
	tc := E2EBillingTestCase{
		Name:     "V26_Pro_WithSound_5s",
		Action:   constant.TaskActionGenerate,
		Model:    "kling-v2-6",
		Mode:     "pro",
		Duration: 5,
		Prompt:   "A video with sound",
		Metadata: map[string]interface{}{
			"sound": "on",
		},

		MockVideoDuration:      "5.0",
		ExpectedPreDeductScale: 10.0, // 5s × soundScale(2.0)
		ExpectedUnitScale:      2.0,
		ExpectedOfficialPrice:  5.0, // 5s × 1.0元/秒
	}

	result := runE2EBillingTest(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: V2.6 Pro 有声 5s = 5元 (1.0元/秒)")
	t.Logf("计算扣费: %.4f, 还原官方价格: %.2f 元", result.FinalAmount, result.FinalAmount/testPriceRatio)
}

func TestE2E_V26_Pro_WithVoiceControl_5s(t *testing.T) {
	// V2.6 Pro 有声+音色 5s = 6元
	tc := E2EBillingTestCase{
		Name:     "V26_Pro_WithVoiceControl_5s",
		Action:   constant.TaskActionGenerate,
		Model:    "kling-v2-6",
		Mode:     "pro",
		Duration: 5,
		Prompt:   "Hello <<<voice_1>>> says",
		Metadata: map[string]interface{}{
			"sound": "on",
			"voice_list": []interface{}{
				map[string]interface{}{"voice_id": "v1"},
			},
		},

		MockVideoDuration:      "5.0",
		ExpectedPreDeductScale: 12.0, // 5s × soundScale(2.0) × voiceScale(1.2)
		ExpectedUnitScale:      2.4,
		ExpectedOfficialPrice:  6.0, // 5s × 1.2元/秒
	}

	result := runE2EBillingTest(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: V2.6 Pro 有声+音色 5s = 6元 (1.2元/秒)")
	t.Logf("计算扣费: %.4f, 还原官方价格: %.2f 元", result.FinalAmount, result.FinalAmount/testPriceRatio)
}

// ============================================================================
// Video-O1 模型测试
// ============================================================================

func TestE2E_VideoO1_Std_NoVideo_5s(t *testing.T) {
	// Video-O1 Std 无参考视频 5s = 3元 (0.6元/秒)
	tc := E2EBillingTestCase{
		Name:     "VideoO1_Std_NoVideo_5s",
		Action:   constant.TaskActionOmniVideo,
		Model:    "kling-video-o1",
		Mode:     "std",
		Duration: 5,
		Prompt:   "A beautiful scene",
		Metadata: map[string]interface{}{
			"duration": "5",
		},

		MockVideoDuration:      "5.0",
		ExpectedPreDeductScale: 5.0,
		ExpectedUnitScale:      1.0,
		ExpectedOfficialPrice:  3.0, // 5s × 0.6元/秒
	}

	result := runE2EBillingTest(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: Video-O1 Std 无参考视频 = 0.6元/秒")
	t.Logf("5s = 3元")
	t.Logf("计算扣费: %.4f, 还原官方价格: %.2f 元", result.FinalAmount, result.FinalAmount/testPriceRatio)
}

func TestE2E_VideoO1_Std_WithVideo_5s(t *testing.T) {
	// Video-O1 Std 有参考视频 5s = 4.5元 (0.9元/秒)
	tc := E2EBillingTestCase{
		Name:     "VideoO1_Std_WithVideo_5s",
		Action:   constant.TaskActionOmniVideo,
		Model:    "kling-video-o1",
		Mode:     "std",
		Duration: 5,
		Prompt:   "Enhance the video",
		Metadata: map[string]interface{}{
			"duration": "5",
			"video_list": []interface{}{
				map[string]interface{}{"video_url": "https://example.com/input.mp4"},
			},
		},

		MockVideoDuration:      "5.0",
		ExpectedPreDeductScale: 7.5, // 5s × videoInputScale(1.5)
		ExpectedUnitScale:      1.5,
		ExpectedOfficialPrice:  4.5, // 5s × 0.9元/秒
	}

	result := runE2EBillingTest(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: Video-O1 Std 有参考视频 = 0.9元/秒")
	t.Logf("5s = 4.5元")
	t.Logf("计算扣费: %.4f, 还原官方价格: %.2f 元", result.FinalAmount, result.FinalAmount/testPriceRatio)
}

func TestE2E_VideoO1_Pro_NoVideo_5s(t *testing.T) {
	// Video-O1 Pro 无参考视频 5s = 4元 (0.8元/秒)
	tc := E2EBillingTestCase{
		Name:     "VideoO1_Pro_NoVideo_5s",
		Action:   constant.TaskActionOmniVideo,
		Model:    "kling-video-o1",
		Mode:     "pro",
		Duration: 5,
		Prompt:   "High quality scene",
		Metadata: map[string]interface{}{
			"duration": "5",
		},

		MockVideoDuration:      "5.0",
		ExpectedPreDeductScale: 5.0 * (0.112 / 0.084), // ~6.67
		ExpectedUnitScale:      0.112 / 0.084,         // ~1.333
		ExpectedOfficialPrice:  4.0,                   // 5s × 0.8元/秒
	}

	result := runE2EBillingTest(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: Video-O1 Pro 无参考视频 = 0.8元/秒")
	t.Logf("5s = 4元")
	t.Logf("计算扣费: %.4f, 还原官方价格: %.2f 元", result.FinalAmount, result.FinalAmount/testPriceRatio)
}

func TestE2E_VideoO1_Pro_WithVideo_5s(t *testing.T) {
	// Video-O1 Pro 有参考视频 5s = 6元 (1.2元/秒)
	tc := E2EBillingTestCase{
		Name:     "VideoO1_Pro_WithVideo_5s",
		Action:   constant.TaskActionOmniVideo,
		Model:    "kling-video-o1",
		Mode:     "pro",
		Duration: 5,
		Prompt:   "Enhance with AI",
		Metadata: map[string]interface{}{
			"duration": "5",
			"video_list": []interface{}{
				map[string]interface{}{"video_url": "https://example.com/input.mp4"},
			},
		},

		MockVideoDuration:      "5.0",
		ExpectedPreDeductScale: 10.0, // 5s × proScale × videoScale
		ExpectedUnitScale:      2.0,
		ExpectedOfficialPrice:  6.0, // 5s × 1.2元/秒
	}

	result := runE2EBillingTest(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: Video-O1 Pro 有参考视频 = 1.2元/秒")
	t.Logf("5s = 6元")
	t.Logf("计算扣费: %.4f, 还原官方价格: %.2f 元", result.FinalAmount, result.FinalAmount/testPriceRatio)
}

// ============================================================================
// 其他模型测试
// ============================================================================

func TestE2E_V1_Std_5s(t *testing.T) {
	// V1 Std 5s = 1元
	tc := E2EBillingTestCase{
		Name:                   "V1_Std_5s",
		Action:                 constant.TaskActionGenerate,
		Model:                  "kling-v1",
		Mode:                   "std",
		Duration:               5,
		Prompt:                 "test",
		MockVideoDuration:      "5.0",
		ExpectedPreDeductScale: 5.0,
		ExpectedUnitScale:      1.0,
		ExpectedOfficialPrice:  1.0, // 5s × 0.2元/秒
	}

	result := runE2EBillingTest(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: V1 Std 5s = 1元")
	t.Logf("计算扣费: %.4f, 还原官方价格: %.2f 元", result.FinalAmount, result.FinalAmount/testPriceRatio)
}

func TestE2E_V1_Pro_5s(t *testing.T) {
	// V1 Pro 5s = 3.5元
	tc := E2EBillingTestCase{
		Name:                   "V1_Pro_5s",
		Action:                 constant.TaskActionGenerate,
		Model:                  "kling-v1",
		Mode:                   "pro",
		Duration:               5,
		Prompt:                 "test",
		MockVideoDuration:      "5.0",
		ExpectedPreDeductScale: 17.5, // 5s × proScale(3.5)
		ExpectedUnitScale:      3.5,
		ExpectedOfficialPrice:  3.5, // 5s × 0.7元/秒
	}

	result := runE2EBillingTest(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: V1 Pro 5s = 3.5元")
	t.Logf("计算扣费: %.4f, 还原官方价格: %.2f 元", result.FinalAmount, result.FinalAmount/testPriceRatio)
}

func TestE2E_V25Turbo_Std_5s(t *testing.T) {
	// V2.5 turbo Std 5s = 1.5元
	tc := E2EBillingTestCase{
		Name:                   "V25Turbo_Std_5s",
		Action:                 constant.TaskActionGenerate,
		Model:                  "kling-v2-5-turbo",
		Mode:                   "std",
		Duration:               5,
		Prompt:                 "test",
		MockVideoDuration:      "5.0",
		ExpectedPreDeductScale: 5.0,
		ExpectedUnitScale:      1.0,
		ExpectedOfficialPrice:  1.5, // 5s × 0.3元/秒
	}

	result := runE2EBillingTest(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: V2.5 turbo Std 5s = 1.5元")
	t.Logf("计算扣费: %.4f, 还原官方价格: %.2f 元", result.FinalAmount, result.FinalAmount/testPriceRatio)
}

func TestE2E_V25Turbo_Pro_5s(t *testing.T) {
	// V2.5 turbo Pro 5s = 2.5元
	tc := E2EBillingTestCase{
		Name:                   "V25Turbo_Pro_5s",
		Action:                 constant.TaskActionGenerate,
		Model:                  "kling-v2-5-turbo",
		Mode:                   "pro",
		Duration:               5,
		Prompt:                 "test",
		MockVideoDuration:      "5.0",
		ExpectedPreDeductScale: 5.0 * (0.07 / 0.042), // ~8.33
		ExpectedUnitScale:      0.07 / 0.042,         // ~1.667
		ExpectedOfficialPrice:  2.5,                  // 5s × 0.5元/秒
	}

	result := runE2EBillingTest(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: V2.5 turbo Pro 5s = 2.5元")
	t.Logf("计算扣费: %.4f, 还原官方价格: %.2f 元", result.FinalAmount, result.FinalAmount/testPriceRatio)
}

func TestE2E_V2Master_5s(t *testing.T) {
	// V2.0 大师版 5s = 10元
	tc := E2EBillingTestCase{
		Name:                   "V2Master_5s",
		Action:                 constant.TaskActionGenerate,
		Model:                  "kling-v2-master",
		Mode:                   "master",
		Duration:               5,
		Prompt:                 "test",
		MockVideoDuration:      "5.0",
		ExpectedPreDeductScale: 5.0,
		ExpectedUnitScale:      1.0,
		ExpectedOfficialPrice:  10.0, // 5s × 2.0元/秒
	}

	result := runE2EBillingTest(t, tc)

	t.Logf("=== %s ===", tc.Name)
	t.Logf("官方价格: V2.0 大师版 5s = 10元")
	t.Logf("计算扣费: %.4f, 还原官方价格: %.2f 元", result.FinalAmount, result.FinalAmount/testPriceRatio)
}

// ============================================================================
// 免费辅助操作测试
// ============================================================================

func TestE2E_FreeActions(t *testing.T) {
	adaptor := &TaskAdaptor{}
	gin.SetMode(gin.TestMode)

	freeActions := []struct {
		name   string
		action string
	}{
		{"多模态编辑-初始化", constant.TaskActionMultiElementsInit},
		{"多模态编辑-增加选区", constant.TaskActionMultiElementsAddSelection},
		{"多模态编辑-删减选区", constant.TaskActionMultiElementsDeleteSelection},
		{"多模态编辑-清除选区", constant.TaskActionMultiElementsClearSelection},
		{"多模态编辑-预览", constant.TaskActionMultiElementsPreview},
	}

	for _, tc := range freeActions {
		t.Run(tc.name, func(t *testing.T) {
			c, _ := gin.CreateTestContext(httptest.NewRecorder())
			req := relaycommon.TaskSubmitReq{Model: "kling-v1-6"}
			c.Set("task_request", req)
			c.Set("action", tc.action)

			info := &relaycommon.RelayInfo{
				TaskRelayInfo: &relaycommon.TaskRelayInfo{Action: tc.action},
			}

			priceScale, err := adaptor.GetPriceScale(c, info)
			assert.NoError(t, err)
			assert.Equal(t, float32(0), priceScale, "免费操作应返回 PriceScale=0")
			t.Logf("✓ %s: PriceScale=0 (免费)", tc.name)
		})
	}
}

// ============================================================================
// Mock HTTP Server 完整流程测试
// ============================================================================

func TestE2E_FullFlow_WithMockServer(t *testing.T) {
	mockServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		response := responsePayload{
			Code:    0,
			Message: "success",
			Data: struct {
				TaskId        string `json:"task_id"`
				TaskStatus    string `json:"task_status"`
				TaskStatusMsg string `json:"task_status_msg"`
				TaskResult    struct {
					Videos []struct {
						Id       string `json:"id"`
						Url      string `json:"url"`
						Duration string `json:"duration"`
					} `json:"videos"`
				} `json:"task_result"`
				CreatedAt int64 `json:"created_at"`
				UpdatedAt int64 `json:"updated_at"`
			}{
				TaskId:     "mock_task_001",
				TaskStatus: "succeed",
				TaskResult: struct {
					Videos []struct {
						Id       string `json:"id"`
						Url      string `json:"url"`
						Duration string `json:"duration"`
					} `json:"videos"`
				}{
					Videos: []struct {
						Id       string `json:"id"`
						Url      string `json:"url"`
						Duration string `json:"duration"`
					}{
						{Id: "v1", Url: "https://mock.kling.ai/video.mp4", Duration: "5.5"},
					},
				},
			},
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(response)
	}))
	defer mockServer.Close()

	adaptor := &TaskAdaptor{
		baseURL: mockServer.URL,
		apiKey:  "test_key|test_secret",
	}

	gin.SetMode(gin.TestMode)
	c, _ := gin.CreateTestContext(httptest.NewRecorder())

	req := relaycommon.TaskSubmitReq{
		Model:    "kling-v2-6",
		Mode:     "pro",
		Duration: 5,
		Prompt:   "A test video",
	}
	c.Set("task_request", req)
	c.Set("action", constant.TaskActionGenerate)

	info := &relaycommon.RelayInfo{
		TaskRelayInfo: &relaycommon.TaskRelayInfo{Action: constant.TaskActionGenerate},
	}

	// 1. 预扣费
	preDeductScale, _ := adaptor.GetPriceScale(c, info)
	modelPrice := ModelPriceMap["kling-v2-6"]
	preDeductAmount := modelPrice * float64(preDeductScale)

	t.Logf("=== 完整流程测试 ===")
	t.Logf("1. 预扣费: PriceScale=%.2f, 预扣金额=%.4f", preDeductScale, preDeductAmount)

	// 2. 构建请求
	requestBody, _ := adaptor.BuildRequestBody(c, info)
	bodyBytes, _ := io.ReadAll(requestBody)
	t.Logf("2. 请求体: %s", string(bodyBytes))

	// 3. 发送请求
	httpReq, _ := http.NewRequest("POST", mockServer.URL+"/v1/videos/text2video", bytes.NewReader(bodyBytes))
	httpReq.Header.Set("Content-Type", "application/json")
	resp, _ := http.DefaultClient.Do(httpReq)
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)
	t.Logf("3. Mock 响应: %s", string(respBody))

	// 4. 解析响应
	taskInfo, _ := adaptor.ParseTaskResult(respBody)
	t.Logf("4. 任务结果: TaskID=%s, Duration=%.1f", taskInfo.TaskID, taskInfo.Duration)

	// 5. 核销扣费
	unitScale, _ := adaptor.GetUnitPriceScale(c, info)
	finalPriceScale := float64(unitScale) * taskInfo.Duration
	finalAmount := modelPrice * finalPriceScale

	t.Logf("5. 核销扣费: UnitScale=%.2f × Duration=%.1f = FinalScale=%.2f",
		unitScale, taskInfo.Duration, finalPriceScale)
	t.Logf("   最终扣费: %.4f, 还原官方价格: %.2f 元", finalAmount, finalAmount/testPriceRatio)

	// 6. 验证
	assert.Equal(t, "mock_task_001", taskInfo.TaskID)
	assert.Equal(t, 5.5, taskInfo.Duration)
	assert.InDelta(t, 2.75, finalAmount/testPriceRatio, 0.1) // 5.5s × 0.5元/秒
}

// ============================================================================
// 扣费汇总报告
// ============================================================================

func TestE2E_BillingSummary(t *testing.T) {
	separator := "================================================================================"
	t.Log(separator)
	t.Log("可灵扣费测试汇总 - 官方价格验证")
	t.Log(separator)
	t.Log("")

	t.Log("【普通视频生成 - 使用对应模型的 ModelPrice】")
	t.Log("  V1 Std 5s=1元, Pro 5s=3.5元")
	t.Log("  V1.5/V1.6/V2.1 Std 5s=2元, Pro 5s=3.5元")
	t.Log("  V2.5 turbo Std 5s=1.5元, Pro 5s=2.5元")
	t.Log("  V2.6 Pro 无声=2.5元, 有声=5元, 有声+音色=6元")
	t.Log("  V2.0/V2.1 大师版 5s=10元")
	t.Log("  Video-O1 Std 无视频=3元, 有视频=4.5元; Pro 无视频=4元, 有视频=6元")
	t.Log("")

	t.Log("【特殊功能 - 需要专用 ModelPrice】")
	t.Log("  多模态编辑: ModelPrice=0.084 (Std 0.6元/秒, Pro 1.0元/秒)")
	t.Log("  视频延长: ModelPrice=0.14 (V1 Std=1元, V1.6 Std=2元, Pro=3.5元)")
	t.Log("  对口型: ModelPrice=0.14 (每5秒0.5元)")
	t.Log("  动作控制: ModelPrice=0.07 (Std 0.5元/秒, Pro 0.8元/秒)")
	t.Log("")

	t.Log("【免费辅助操作】")
	t.Log("  多模态编辑: 初始化、增加/删减/清除选区、预览")
	t.Log("")

	t.Log(separator)
}
