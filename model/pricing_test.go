package model

import (
	"encoding/json"
	"sort"
	"testing"

	"github.com/QuantumNous/new-api/constant"
)

func TestPricingCreatedTimeJSONSerialization(t *testing.T) {
	pricing := Pricing{
		ModelName:   "gpt-4o",
		QuotaType:   1,
		ModelPrice:  0.005,
		CreatedTime: 1708300000,
		EnableGroup: []string{"default"},
		SupportedEndpointTypes: []constant.EndpointType{
			constant.EndpointType("chat"),
		},
	}

	data, err := json.Marshal(pricing)
	if err != nil {
		t.Fatalf("Failed to marshal Pricing: %v", err)
	}

	var parsed map[string]interface{}
	if err := json.Unmarshal(data, &parsed); err != nil {
		t.Fatalf("Failed to unmarshal JSON: %v", err)
	}

	ct, ok := parsed["created_time"]
	if !ok {
		t.Fatal("created_time field missing from JSON output")
	}
	if ct.(float64) != 1708300000 {
		t.Errorf("created_time = %v, want 1708300000", ct)
	}
}

func TestPricingCreatedTimeZeroValue(t *testing.T) {
	pricing := Pricing{
		ModelName: "test-model",
	}

	data, err := json.Marshal(pricing)
	if err != nil {
		t.Fatalf("Failed to marshal Pricing: %v", err)
	}

	var parsed map[string]interface{}
	if err := json.Unmarshal(data, &parsed); err != nil {
		t.Fatalf("Failed to unmarshal JSON: %v", err)
	}

	ct, ok := parsed["created_time"]
	if !ok {
		t.Fatal("created_time field missing from JSON output when zero")
	}
	if ct.(float64) != 0 {
		t.Errorf("created_time = %v, want 0", ct)
	}
}

func TestPricingSortByCreatedTimeDescending(t *testing.T) {
	pricings := []Pricing{
		{ModelName: "old-model", CreatedTime: 1700000000},
		{ModelName: "newest-model", CreatedTime: 1710000000},
		{ModelName: "middle-model", CreatedTime: 1705000000},
		{ModelName: "no-time-model", CreatedTime: 0},
	}

	sort.Slice(pricings, func(i, j int) bool {
		return pricings[i].CreatedTime > pricings[j].CreatedTime
	})

	expected := []string{"newest-model", "middle-model", "old-model", "no-time-model"}
	for i, p := range pricings {
		if p.ModelName != expected[i] {
			t.Errorf("Position %d: got %s, want %s", i, p.ModelName, expected[i])
		}
	}
}

func TestPricingSortStabilityWithSameCreatedTime(t *testing.T) {
	pricings := []Pricing{
		{ModelName: "model-a", CreatedTime: 1700000000},
		{ModelName: "model-b", CreatedTime: 1700000000},
		{ModelName: "model-c", CreatedTime: 1710000000},
	}

	sort.SliceStable(pricings, func(i, j int) bool {
		return pricings[i].CreatedTime > pricings[j].CreatedTime
	})

	if pricings[0].ModelName != "model-c" {
		t.Errorf("Position 0: got %s, want model-c", pricings[0].ModelName)
	}
	if pricings[1].ModelName != "model-a" {
		t.Errorf("Position 1: got %s, want model-a (stable sort preserves order)", pricings[1].ModelName)
	}
	if pricings[2].ModelName != "model-b" {
		t.Errorf("Position 2: got %s, want model-b (stable sort preserves order)", pricings[2].ModelName)
	}
}

func TestGetModelSupportEndpointTypesEmpty(t *testing.T) {
	result := GetModelSupportEndpointTypes("")
	if len(result) != 0 {
		t.Errorf("Expected empty slice for empty model, got %v", result)
	}
}

func TestGetModelSupportEndpointTypesUnknownModel(t *testing.T) {
	result := GetModelSupportEndpointTypes("nonexistent-model-xyz")
	if len(result) != 0 {
		t.Errorf("Expected empty slice for unknown model, got %v", result)
	}
}

func TestPricingJSONRoundTrip(t *testing.T) {
	original := Pricing{
		ModelName:   "claude-3.5-sonnet",
		Description: "Test model",
		Tags:        "chat,reasoning",
		VendorID:    1,
		QuotaType:   1,
		ModelPrice:  0.003,
		CreatedTime: 1708300000,
		EnableGroup: []string{"default", "vip"},
		SupportedEndpointTypes: []constant.EndpointType{
			constant.EndpointType("chat"),
			constant.EndpointType("completions"),
		},
	}

	data, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("Failed to marshal: %v", err)
	}

	var decoded Pricing
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Failed to unmarshal: %v", err)
	}

	if decoded.CreatedTime != original.CreatedTime {
		t.Errorf("CreatedTime mismatch: got %d, want %d", decoded.CreatedTime, original.CreatedTime)
	}
	if decoded.ModelName != original.ModelName {
		t.Errorf("ModelName mismatch: got %s, want %s", decoded.ModelName, original.ModelName)
	}
	if decoded.QuotaType != original.QuotaType {
		t.Errorf("QuotaType mismatch: got %d, want %d", decoded.QuotaType, original.QuotaType)
	}
}
