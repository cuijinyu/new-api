package controller

import (
	"testing"

	"github.com/QuantumNous/new-api/constant"
	relaycommon "github.com/QuantumNous/new-api/relay/common"
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
