package controller

import (
	"testing"

	"github.com/QuantumNous/new-api/constant"
	relaycommon "github.com/QuantumNous/new-api/relay/common"
	"github.com/QuantumNous/new-api/setting/ratio_setting"
)

func TestResolveVideoActualUsageServiceInferenceUsesTotalTokens(t *testing.T) {
	got, source := resolveVideoActualUsage(constant.ChannelTypeServiceInferenceVideo, &relaycommon.TaskInfo{
		Duration:    4,
		TotalTokens: 40594,
	}, nil)
	if got != 40594 {
		t.Fatalf("usage = %v, want total tokens", got)
	}
	if source != "upstream_total_tokens" {
		t.Fatalf("source = %q, want upstream_total_tokens", source)
	}
}

func TestResolveVideoActualUsageServiceInferenceFallsBackToEstimatedTokens(t *testing.T) {
	taskData := []byte(`{"_newapi_service_inference_billing":{"estimated_tokens":48000}}`)
	got, source := resolveVideoActualUsage(constant.ChannelTypeServiceInferenceVideo, &relaycommon.TaskInfo{
		Duration: 4,
	}, taskData)
	if got != 48000 {
		t.Fatalf("usage = %v, want estimated tokens", got)
	}
	if source != "estimated_tokens" {
		t.Fatalf("source = %q, want estimated_tokens", source)
	}
}

func TestResolveVideoActualUsageServiceInferenceDoesNotUseDurationAsTokens(t *testing.T) {
	got, source := resolveVideoActualUsage(constant.ChannelTypeServiceInferenceVideo, &relaycommon.TaskInfo{
		Duration: 4,
	}, nil)
	if got != 0 {
		t.Fatalf("usage = %v, want 0 when token data is missing", got)
	}
	if source != "missing_service_inference_total_tokens" {
		t.Fatalf("source = %q, want missing_service_inference_total_tokens", source)
	}
}

func TestResolveVideoActualUsageOtherVideoUsesDuration(t *testing.T) {
	got, source := resolveVideoActualUsage(constant.ChannelTypeDoubaoVideo, &relaycommon.TaskInfo{
		Duration:    4,
		TotalTokens: 40594,
	}, nil)
	if got != 4 {
		t.Fatalf("usage = %v, want duration", got)
	}
	if source != "duration_seconds" {
		t.Fatalf("source = %q, want duration_seconds", source)
	}
}

func TestResolveVideoModelPriceOrRatioFallsBackToDefaultModelPrice(t *testing.T) {
	originalModelPrice := ratio_setting.ModelPrice2JSONString()
	t.Cleanup(func() {
		if err := ratio_setting.UpdateModelPriceByJSONString(originalModelPrice); err != nil {
			t.Fatalf("restore model price: %v", err)
		}
	})
	if err := ratio_setting.UpdateModelPriceByJSONString(`{}`); err != nil {
		t.Fatalf("clear model price: %v", err)
	}

	value, isPrice, found, source := resolveVideoModelPriceOrRatio("dreamina-seedance-2-0-fast-260128")
	if !found {
		t.Fatal("found = false, want default model price fallback")
	}
	if !isPrice {
		t.Fatal("isPrice = false, want price mode")
	}
	if value != 5.6 {
		t.Fatalf("value = %v, want 5.6", value)
	}
	if source != "default_model_price" {
		t.Fatalf("source = %q, want default_model_price", source)
	}
}
