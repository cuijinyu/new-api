package ratio_setting

import (
	"encoding/json"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/QuantumNous/new-api/common"

	"github.com/tidwall/gjson"
)

// 条件计费（结构化条件乘数）
//
// 在现有「固定档位价格表」结构之外，以最小侵入方式补充两类计费能力：
//  1. 时段计费（time）：按时区 + 小时区间 和/或 星期集合命中。
//  2. 按请求头/请求体条件计费（header/param）：如 Claude `anthropic-beta: fast-mode`、
//     OpenAI/Anthropic `service_tier=fast/priority`。
//
// 命中后将 multiplier 乘到最终计费上（分段 / ModelPrice / ModelRatio 三条路径统一生效）。
// 命中的规则标识、实际乘数、被引用字段的实际取值会一并写入结算日志 `other`，
// 以便对账侧直接读快照、无需在 Athena 侧重建求值环境。

// 条件类型
const (
	ConditionTypeHeader = "header" // 按请求头匹配
	ConditionTypeParam  = "param"  // 按请求体 JSON 路径匹配
	ConditionTypeTime   = "time"   // 按时段（时区 + 小时区间 / 星期）匹配
)

// 匹配方式（header / param 用）
const (
	ConditionMatchContains = "contains" // 子串包含
	ConditionMatchEquals   = "equals"   // 完全相等
	ConditionMatchPrefix   = "prefix"   // 前缀
	ConditionMatchExists   = "exists"   // 字段存在（非空）
)

// 命中策略
const (
	ConditionStrategyFirstMatch  = "first-match"  // 第一条命中即生效（默认）
	ConditionStrategyMultiplyAll = "multiply-all" // 所有命中规则的乘数连乘
)

// ConditionRule 单条条件规则
type ConditionRule struct {
	// Name 规则标识，写入快照便于对账与排查（如 "fast-mode" / "night-discount"）。
	Name string `json:"name,omitempty"`
	// Type 条件类型：header / param / time
	Type string `json:"type"`

	// --- header / param 通用 ---
	// Key：header 名（如 "anthropic-beta"）或请求体 JSON 路径（如 "service_tier"）。
	Key string `json:"key,omitempty"`
	// Match：contains / equals / prefix / exists
	Match string `json:"match,omitempty"`
	// Value：期望值（match=exists 时忽略）。
	Value string `json:"value,omitempty"`

	// --- time 专用 ---
	// Timezone：IANA 时区（如 "Asia/Shanghai"），为空按 UTC。
	Timezone string `json:"timezone,omitempty"`
	// StartHour / EndHour：小时区间 [StartHour, EndHour)，0-24。
	// 两者相等（如同为 0）表示不限制小时。EndHour <= StartHour 表示跨夜（如 22-8）。
	StartHour int `json:"start_hour,omitempty"`
	EndHour   int `json:"end_hour,omitempty"`
	// Weekdays：星期集合，0=周日 .. 6=周六。为空表示不限制星期。
	Weekdays []int `json:"weekdays,omitempty"`

	// Multiplier：命中后乘到价格上的乘数。
	Multiplier float64 `json:"multiplier"`
}

// ConditionalPricing 模型级条件规则配置（一组有序规则）
type ConditionalPricing struct {
	Enabled  bool            `json:"enabled"`
	Strategy string          `json:"strategy,omitempty"` // first-match（默认）/ multiply-all
	Rules    []ConditionRule `json:"rules"`
}

var (
	conditionalPricingMap      map[string]*ConditionalPricing = nil
	conditionalPricingMapMutex                                = sync.RWMutex{}
)

// defaultConditionalPricing 内置默认条件规则。
// 默认留空（不破坏任何现有计费行为）；示例配置见 README / 技能文档。
var defaultConditionalPricing = map[string]*ConditionalPricing{}

// InitConditionalPricingSettings 用内置默认初始化条件计费 map。
func InitConditionalPricingSettings() {
	conditionalPricingMapMutex.Lock()
	defer conditionalPricingMapMutex.Unlock()
	if conditionalPricingMap == nil {
		conditionalPricingMap = make(map[string]*ConditionalPricing)
	}
	for k, v := range defaultConditionalPricing {
		if _, exists := conditionalPricingMap[k]; !exists {
			rulesCopy := make([]ConditionRule, len(v.Rules))
			copy(rulesCopy, v.Rules)
			conditionalPricingMap[k] = &ConditionalPricing{Enabled: v.Enabled, Strategy: v.Strategy, Rules: rulesCopy}
		}
	}
}

// GetConditionalPricingMap 返回条件计费 map（只读引用）。
func GetConditionalPricingMap() map[string]*ConditionalPricing {
	conditionalPricingMapMutex.RLock()
	defer conditionalPricingMapMutex.RUnlock()
	return conditionalPricingMap
}

// GetConditionalPricingCopy 返回条件计费 map 的深拷贝。
func GetConditionalPricingCopy() map[string]*ConditionalPricing {
	conditionalPricingMapMutex.RLock()
	defer conditionalPricingMapMutex.RUnlock()
	copyMap := make(map[string]*ConditionalPricing, len(conditionalPricingMap))
	for k, v := range conditionalPricingMap {
		if v == nil {
			copyMap[k] = nil
			continue
		}
		rulesCopy := make([]ConditionRule, len(v.Rules))
		copy(rulesCopy, v.Rules)
		copyMap[k] = &ConditionalPricing{Enabled: v.Enabled, Strategy: v.Strategy, Rules: rulesCopy}
	}
	return copyMap
}

// ConditionalPricing2JSONString 序列化条件计费 map 为 JSON 字符串。
func ConditionalPricing2JSONString() string {
	conditionalPricingMapMutex.RLock()
	defer conditionalPricingMapMutex.RUnlock()
	jsonBytes, err := json.Marshal(conditionalPricingMap)
	if err != nil {
		common.SysLog("error marshalling conditional pricing: " + err.Error())
		return "{}"
	}
	return string(jsonBytes)
}

// UpdateConditionalPricingByJSONString 从 JSON 字符串更新条件计费 map。
func UpdateConditionalPricingByJSONString(jsonStr string) error {
	conditionalPricingMapMutex.Lock()
	defer conditionalPricingMapMutex.Unlock()

	newMap := make(map[string]*ConditionalPricing)
	if err := json.Unmarshal([]byte(jsonStr), &newMap); err != nil {
		return err
	}
	conditionalPricingMap = newMap
	InvalidateExposedDataCache()
	return nil
}

// GetConditionalPricing 返回模型的条件计费配置，支持通配匹配（同 tiered_pricing 规则）。
func GetConditionalPricing(modelName string) (*ConditionalPricing, bool) {
	conditionalPricingMapMutex.RLock()
	defer conditionalPricingMapMutex.RUnlock()

	if cfg, ok := conditionalPricingMap[modelName]; ok && cfg != nil {
		return cfg, true
	}
	for pattern, cfg := range conditionalPricingMap {
		if cfg == nil || !cfg.Enabled {
			continue
		}
		if matchWildcard(pattern, modelName) {
			return cfg, true
		}
	}
	return nil, false
}

// RequestConditionContext 求值所需的请求上下文（与 gin 解耦，便于复用与单测）。
type RequestConditionContext struct {
	Headers http.Header // 请求头（可为 nil）
	Body    []byte      // 已缓存的请求体（可为 nil；param 条件依赖它）
	Now     time.Time   // 计费发生时刻（用于 time 条件）
}

// ConditionMatchResult 条件求值结果（含对账快照所需信息）。
type ConditionMatchResult struct {
	Matched      bool              // 是否有规则命中
	Multiplier   float64           // 最终乘数（未命中为 1.0）
	MatchedRules []string          // 命中规则标识（按命中顺序）
	FieldValues  map[string]string // 被引用字段的实际取值快照（header/param）
}

// EvaluateConditionalMultiplier 对给定模型与请求上下文求条件乘数。
// 未命中或未配置时返回 {Multiplier: 1.0}。
func EvaluateConditionalMultiplier(modelName string, rc RequestConditionContext) ConditionMatchResult {
	result := ConditionMatchResult{Multiplier: 1.0}

	cfg, ok := GetConditionalPricing(modelName)
	if !ok || cfg == nil || !cfg.Enabled || len(cfg.Rules) == 0 {
		return result
	}

	strategy := cfg.Strategy
	if strategy == "" {
		strategy = ConditionStrategyFirstMatch
	}

	for i := range cfg.Rules {
		rule := &cfg.Rules[i]
		matched, fieldKey, fieldVal := evalRule(rule, rc)
		if !matched {
			continue
		}
		// 记录命中信息
		ruleName := rule.Name
		if ruleName == "" {
			ruleName = ruleIdentity(rule)
		}
		result.Matched = true
		result.MatchedRules = append(result.MatchedRules, ruleName)
		if fieldKey != "" {
			if result.FieldValues == nil {
				result.FieldValues = make(map[string]string)
			}
			result.FieldValues[fieldKey] = fieldVal
		}

		mult := rule.Multiplier
		if mult <= 0 {
			// 乘数非法（<=0）视为 1.0，避免误清零计费
			mult = 1.0
		}

		if strategy == ConditionStrategyMultiplyAll {
			result.Multiplier *= mult
		} else {
			// first-match：第一条命中即生效
			result.Multiplier = mult
			break
		}
	}

	return result
}

// evalRule 求值单条规则，返回 (是否命中, 被引用字段名, 实际取值)。
func evalRule(rule *ConditionRule, rc RequestConditionContext) (bool, string, string) {
	switch rule.Type {
	case ConditionTypeHeader:
		if rc.Headers == nil || rule.Key == "" {
			return false, "", ""
		}
		val := rc.Headers.Get(rule.Key)
		fieldKey := "header:" + rule.Key
		return matchString(val, rule.Match, rule.Value), fieldKey, val
	case ConditionTypeParam:
		if len(rc.Body) == 0 || rule.Key == "" {
			return false, "", ""
		}
		res := gjson.GetBytes(rc.Body, rule.Key)
		val := ""
		if res.Exists() {
			val = res.String()
		}
		fieldKey := "param:" + rule.Key
		// exists 语义对 param 用「路径存在」判断
		if rule.Match == ConditionMatchExists {
			return res.Exists(), fieldKey, val
		}
		if !res.Exists() {
			return false, fieldKey, val
		}
		return matchString(val, rule.Match, rule.Value), fieldKey, val
	case ConditionTypeTime:
		return matchTime(rule, rc.Now), "", ""
	default:
		return false, "", ""
	}
}

// matchString 按匹配方式比较实际值与期望值。
func matchString(actual, match, expected string) bool {
	switch match {
	case ConditionMatchExists:
		return actual != ""
	case ConditionMatchEquals:
		return actual == expected
	case ConditionMatchPrefix:
		return strings.HasPrefix(actual, expected)
	case ConditionMatchContains:
		fallthrough
	default:
		// 默认 contains
		if expected == "" {
			return false
		}
		return strings.Contains(actual, expected)
	}
}

// matchTime 判断时刻是否命中时段规则。
func matchTime(rule *ConditionRule, now time.Time) bool {
	if now.IsZero() {
		now = time.Now()
	}
	loc := time.UTC
	if rule.Timezone != "" {
		if l, err := time.LoadLocation(rule.Timezone); err == nil {
			loc = l
		}
	}
	t := now.In(loc)

	// 星期约束
	if len(rule.Weekdays) > 0 {
		wd := int(t.Weekday()) // 0=Sunday
		hit := false
		for _, w := range rule.Weekdays {
			if w == wd {
				hit = true
				break
			}
		}
		if !hit {
			return false
		}
	}

	// 小时约束：StartHour == EndHour 表示不限制小时
	if rule.StartHour != rule.EndHour {
		h := t.Hour()
		if rule.EndHour > rule.StartHour {
			// 普通区间 [Start, End)
			if !(h >= rule.StartHour && h < rule.EndHour) {
				return false
			}
		} else {
			// 跨夜区间，如 22-8：h >= Start || h < End
			if !(h >= rule.StartHour || h < rule.EndHour) {
				return false
			}
		}
	} else if len(rule.Weekdays) == 0 {
		// 既无小时约束也无星期约束的 time 规则视为无效，不命中
		return false
	}

	return true
}

// ruleIdentity 为未命名规则生成可读标识，写入快照。
func ruleIdentity(rule *ConditionRule) string {
	switch rule.Type {
	case ConditionTypeHeader:
		return "header:" + rule.Key
	case ConditionTypeParam:
		return "param:" + rule.Key
	case ConditionTypeTime:
		return "time"
	default:
		return rule.Type
	}
}

// IsConditionalPricingEnabled 模型是否启用了条件计费。
func IsConditionalPricingEnabled(modelName string) bool {
	cfg, ok := GetConditionalPricing(modelName)
	return ok && cfg != nil && cfg.Enabled
}
