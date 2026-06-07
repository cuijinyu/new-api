package ratio_setting

import (
	"net/http"
	"testing"
	"time"
)

func setupConditionalPricing(t *testing.T, jsonStr string) {
	t.Helper()
	if err := UpdateConditionalPricingByJSONString(jsonStr); err != nil {
		t.Fatalf("UpdateConditionalPricingByJSONString failed: %v", err)
	}
}

func TestConditionalHeaderFastMode(t *testing.T) {
	setupConditionalPricing(t, `{
		"claude-sonnet-4-6": {
			"enabled": true,
			"strategy": "first-match",
			"rules": [
				{"name": "fast-mode", "type": "header", "key": "anthropic-beta", "match": "contains", "value": "fast-mode", "multiplier": 6}
			]
		}
	}`)

	h := http.Header{}
	h.Set("anthropic-beta", "output-128k-2025-02-19,fast-mode")
	res := EvaluateConditionalMultiplier("claude-sonnet-4-6", RequestConditionContext{Headers: h, Now: time.Now()})
	if !res.Matched || res.Multiplier != 6 {
		t.Fatalf("expected matched multiplier 6, got matched=%v mult=%v", res.Matched, res.Multiplier)
	}
	if res.FieldValues["header:anthropic-beta"] != "output-128k-2025-02-19,fast-mode" {
		t.Fatalf("unexpected field snapshot: %#v", res.FieldValues)
	}

	// 未命中：无该 header
	res2 := EvaluateConditionalMultiplier("claude-sonnet-4-6", RequestConditionContext{Headers: http.Header{}, Now: time.Now()})
	if res2.Matched || res2.Multiplier != 1.0 {
		t.Fatalf("expected no match multiplier 1.0, got matched=%v mult=%v", res2.Matched, res2.Multiplier)
	}
}

func TestConditionalParamServiceTier(t *testing.T) {
	setupConditionalPricing(t, `{
		"gpt-5.5": {
			"enabled": true,
			"rules": [
				{"name": "priority-tier", "type": "param", "key": "service_tier", "match": "equals", "value": "priority", "multiplier": 2}
			]
		}
	}`)

	body := []byte(`{"model":"gpt-5.5","service_tier":"priority","messages":[]}`)
	res := EvaluateConditionalMultiplier("gpt-5.5", RequestConditionContext{Body: body, Now: time.Now()})
	if !res.Matched || res.Multiplier != 2 {
		t.Fatalf("expected matched multiplier 2, got matched=%v mult=%v", res.Matched, res.Multiplier)
	}
	if res.FieldValues["param:service_tier"] != "priority" {
		t.Fatalf("unexpected field snapshot: %#v", res.FieldValues)
	}

	// service_tier=fast 不应命中 priority 规则
	body2 := []byte(`{"service_tier":"fast"}`)
	res2 := EvaluateConditionalMultiplier("gpt-5.5", RequestConditionContext{Body: body2, Now: time.Now()})
	if res2.Matched || res2.Multiplier != 1.0 {
		t.Fatalf("expected no match, got matched=%v mult=%v", res2.Matched, res2.Multiplier)
	}
}

func TestConditionalTimeNightDiscount(t *testing.T) {
	setupConditionalPricing(t, `{
		"my-model": {
			"enabled": true,
			"rules": [
				{"name": "night-discount", "type": "time", "timezone": "Asia/Shanghai", "start_hour": 0, "end_hour": 8, "multiplier": 0.5}
			]
		}
	}`)

	loc, _ := time.LoadLocation("Asia/Shanghai")
	// 03:00 命中
	night := time.Date(2026, 1, 1, 3, 0, 0, 0, loc)
	res := EvaluateConditionalMultiplier("my-model", RequestConditionContext{Now: night})
	if !res.Matched || res.Multiplier != 0.5 {
		t.Fatalf("night: expected matched 0.5, got matched=%v mult=%v", res.Matched, res.Multiplier)
	}

	// 12:00 不命中
	day := time.Date(2026, 1, 1, 12, 0, 0, 0, loc)
	res2 := EvaluateConditionalMultiplier("my-model", RequestConditionContext{Now: day})
	if res2.Matched || res2.Multiplier != 1.0 {
		t.Fatalf("day: expected no match 1.0, got matched=%v mult=%v", res2.Matched, res2.Multiplier)
	}
}

func TestConditionalTimeCrossMidnight(t *testing.T) {
	setupConditionalPricing(t, `{
		"m": {"enabled": true, "rules": [
			{"name": "late", "type": "time", "timezone": "UTC", "start_hour": 22, "end_hour": 6, "multiplier": 1.2}
		]}
	}`)
	loc := time.UTC
	for _, h := range []int{22, 23, 0, 5} {
		ts := time.Date(2026, 1, 1, h, 30, 0, 0, loc)
		res := EvaluateConditionalMultiplier("m", RequestConditionContext{Now: ts})
		if !res.Matched {
			t.Fatalf("hour %d expected match", h)
		}
	}
	for _, h := range []int{6, 12, 21} {
		ts := time.Date(2026, 1, 1, h, 30, 0, 0, loc)
		res := EvaluateConditionalMultiplier("m", RequestConditionContext{Now: ts})
		if res.Matched {
			t.Fatalf("hour %d expected no match", h)
		}
	}
}

func TestConditionalStrategyFirstMatchVsMultiplyAll(t *testing.T) {
	// first-match：第一条命中即生效
	setupConditionalPricing(t, `{
		"m": {"enabled": true, "strategy": "first-match", "rules": [
			{"name": "r1", "type": "header", "key": "x-a", "match": "exists", "multiplier": 2},
			{"name": "r2", "type": "header", "key": "x-b", "match": "exists", "multiplier": 3}
		]}
	}`)
	h := http.Header{}
	h.Set("x-a", "1")
	h.Set("x-b", "1")
	res := EvaluateConditionalMultiplier("m", RequestConditionContext{Headers: h})
	if res.Multiplier != 2 {
		t.Fatalf("first-match expected 2, got %v", res.Multiplier)
	}

	// multiply-all：所有命中连乘
	setupConditionalPricing(t, `{
		"m": {"enabled": true, "strategy": "multiply-all", "rules": [
			{"name": "r1", "type": "header", "key": "x-a", "match": "exists", "multiplier": 2},
			{"name": "r2", "type": "header", "key": "x-b", "match": "exists", "multiplier": 3}
		]}
	}`)
	res2 := EvaluateConditionalMultiplier("m", RequestConditionContext{Headers: h})
	if res2.Multiplier != 6 {
		t.Fatalf("multiply-all expected 6, got %v", res2.Multiplier)
	}
}

func TestConditionalWildcardAndDisabled(t *testing.T) {
	setupConditionalPricing(t, `{
		"claude-*": {"enabled": true, "rules": [
			{"name": "fast", "type": "header", "key": "anthropic-beta", "match": "contains", "value": "fast-mode", "multiplier": 5}
		]},
		"off-model": {"enabled": false, "rules": [
			{"name": "x", "type": "header", "key": "h", "match": "exists", "multiplier": 9}
		]}
	}`)
	h := http.Header{}
	h.Set("anthropic-beta", "fast-mode")
	res := EvaluateConditionalMultiplier("claude-opus-4-6", RequestConditionContext{Headers: h})
	if !res.Matched || res.Multiplier != 5 {
		t.Fatalf("wildcard expected 5, got matched=%v mult=%v", res.Matched, res.Multiplier)
	}

	hh := http.Header{}
	hh.Set("h", "1")
	res2 := EvaluateConditionalMultiplier("off-model", RequestConditionContext{Headers: hh})
	if res2.Matched {
		t.Fatalf("disabled config should not match")
	}
}
