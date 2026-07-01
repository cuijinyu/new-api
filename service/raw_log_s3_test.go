package service

import (
	"encoding/json"
	"io"
	"strings"
	"testing"
)

func TestRawLogCaptureKeepsTailAndUsageMetadata(t *testing.T) {
	largeImage := strings.Repeat("A", 4096)
	body := `{"candidates":[{"content":{"parts":[{"inlineData":{"mimeType":"image/png","data":"` +
		largeImage +
		`"}}]}}],"usageMetadata":{"promptTokenCount":17,"candidatesTokenCount":1120,"totalTokenCount":1137,"candidatesTokensDetails":[{"modality":"IMAGE","tokenCount":1120}]}}`

	var captured capturedBody
	rc := newCaptureReadCloser(io.NopCloser(strings.NewReader(body)), 128, 512, func(result capturedBody, err error) {
		if err != nil {
			t.Fatalf("close callback received error: %v", err)
		}
		captured = result
	})

	readBack, err := io.ReadAll(rc)
	if err != nil {
		t.Fatalf("read capture body: %v", err)
	}
	if string(readBack) != body {
		t.Fatalf("capture reader changed response body")
	}
	if err := rc.Close(); err != nil {
		t.Fatalf("close capture body: %v", err)
	}

	if !captured.Truncated {
		t.Fatalf("captured body was not marked truncated")
	}
	if captured.Bytes != int64(len(body)) {
		t.Fatalf("captured bytes = %d, want %d", captured.Bytes, len(body))
	}
	if len(captured.Head) != 128 {
		t.Fatalf("head length = %d, want 128", len(captured.Head))
	}
	if strings.Contains(string(captured.Head), "usageMetadata") {
		t.Fatalf("test setup invalid: usageMetadata unexpectedly present in head")
	}
	if !strings.Contains(string(captured.Tail), "usageMetadata") {
		t.Fatalf("usageMetadata missing from captured tail")
	}

	var payload rawLogPayload
	applyCapturedResponseToPayload(&payload, captured)
	if !payload.ResponseBodyTruncated {
		t.Fatalf("payload response_body_truncated = false, want true")
	}
	if payload.ResponseBodyBytes != int64(len(body)) {
		t.Fatalf("payload response_body_bytes = %d, want %d", payload.ResponseBodyBytes, len(body))
	}
	if payload.ResponseBodyTail == "" {
		t.Fatalf("payload response_body_tail is empty")
	}
	if payload.ResponseUsageMetadata == "" {
		t.Fatalf("payload response_usage_metadata is empty")
	}

	var usage struct {
		PromptTokenCount     int `json:"promptTokenCount"`
		CandidatesTokenCount int `json:"candidatesTokenCount"`
		TotalTokenCount      int `json:"totalTokenCount"`
	}
	if err := json.Unmarshal([]byte(payload.ResponseUsageMetadata), &usage); err != nil {
		t.Fatalf("unmarshal usage metadata: %v; payload=%s", err, payload.ResponseUsageMetadata)
	}
	if usage.PromptTokenCount != 17 || usage.CandidatesTokenCount != 1120 || usage.TotalTokenCount != 1137 {
		t.Fatalf("unexpected usage metadata: %+v", usage)
	}
}

func TestRawLogCaptureSmallBodyDoesNotEmitTail(t *testing.T) {
	body := `{"usageMetadata":{"promptTokenCount":1,"totalTokenCount":2}}`

	var captured capturedBody
	rc := newCaptureReadCloser(io.NopCloser(strings.NewReader(body)), 1024, 128, func(result capturedBody, err error) {
		if err != nil {
			t.Fatalf("close callback received error: %v", err)
		}
		captured = result
	})
	if _, err := io.ReadAll(rc); err != nil {
		t.Fatalf("read capture body: %v", err)
	}
	if err := rc.Close(); err != nil {
		t.Fatalf("close capture body: %v", err)
	}

	var payload rawLogPayload
	applyCapturedResponseToPayload(&payload, captured)
	if payload.ResponseBodyTruncated {
		t.Fatalf("payload response_body_truncated = true, want false")
	}
	if payload.ResponseBodyTail != "" {
		t.Fatalf("payload response_body_tail = %q, want empty", payload.ResponseBodyTail)
	}
	if payload.ResponseUsageMetadata == "" {
		t.Fatalf("payload response_usage_metadata is empty")
	}
}
