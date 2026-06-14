package serviceinference

import (
	"encoding/json"
	"math"
	"net/http/httptest"
	"testing"

	relaycommon "github.com/QuantumNous/new-api/relay/common"

	"github.com/gin-gonic/gin"
)

func TestConvertToRequestPayloadUsesMappedModelAndMetadata(t *testing.T) {
	generateAudio := true
	watermark := false
	req := &relaycommon.TaskSubmitReq{
		Model:   "doubao-seedance-2-0-260128",
		Prompt:  "make a calm product video",
		Images:  []string{"asset://asset-123"},
		Seconds: "6",
		Size:    "720p",
		Metadata: map[string]interface{}{
			"model":          "should-not-pass",
			"resolution":     "480p",
			"ratio":          "16:9",
			"generate_audio": generateAudio,
			"watermark":      watermark,
			"content": []interface{}{
				map[string]interface{}{
					"type": "text",
					"text": "metadata prompt should be replaced",
				},
				map[string]interface{}{
					"type": "audio_url",
					"audio_url": map[string]interface{}{
						"url": "https://example.com/ref.mp3",
					},
					"role": "reference_audio",
				},
			},
		},
	}
	info := &relaycommon.RelayInfo{
		ChannelMeta: &relaycommon.ChannelMeta{
			UpstreamModelName: "dreamina-seedance-2-0-260128",
		},
	}

	payload, err := convertToRequestPayload(req, info)
	if err != nil {
		t.Fatalf("convertToRequestPayload returned error: %v", err)
	}
	if payload.Model != "dreamina-seedance-2-0-260128" {
		t.Fatalf("model = %q, want mapped upstream model", payload.Model)
	}
	if payload.Duration == nil || *payload.Duration != 6 {
		t.Fatalf("duration = %v, want 6", payload.Duration)
	}
	if payload.Resolution != "480p" {
		t.Fatalf("resolution = %q, want metadata value", payload.Resolution)
	}
	if payload.Ratio != "16:9" {
		t.Fatalf("ratio = %q, want 16:9", payload.Ratio)
	}
	if payload.GenerateAudio == nil || *payload.GenerateAudio != true {
		t.Fatalf("generate_audio = %v, want true", payload.GenerateAudio)
	}
	if payload.Watermark == nil || *payload.Watermark != false {
		t.Fatalf("watermark = %v, want false", payload.Watermark)
	}

	var hasAudio, hasImage, hasPrompt, hasMetadataText bool
	for _, item := range payload.Content {
		if item.Type == "audio_url" && item.AudioURL != nil && item.AudioURL.URL == "https://example.com/ref.mp3" {
			hasAudio = true
		}
		if item.Type == "image_url" && item.ImageURL != nil && item.ImageURL.URL == "asset://asset-123" {
			hasImage = true
		}
		if item.Type == "text" && item.Text == "make a calm product video" {
			hasPrompt = true
		}
		if item.Type == "text" && item.Text == "metadata prompt should be replaced" {
			hasMetadataText = true
		}
	}
	if !hasAudio || !hasImage || !hasPrompt {
		b, _ := json.Marshal(payload.Content)
		t.Fatalf("content missing expected items: %s", b)
	}
	if hasMetadataText {
		t.Fatalf("metadata text content was not replaced")
	}
}

func TestParseTaskResultCompleted(t *testing.T) {
	adaptor := &TaskAdaptor{}
	result, err := adaptor.ParseTaskResult([]byte(`{
		"task": {
			"id": "mvt-1",
			"status": "completed",
			"duration_seconds": 4,
			"outputs": ["https://example.com/video.mp4"],
			"usage": {
				"completion_tokens": 40594,
				"total_tokens": 40594
			}
		}
	}`))
	if err != nil {
		t.Fatalf("ParseTaskResult returned error: %v", err)
	}
	if result.Status != "SUCCESS" {
		t.Fatalf("status = %q, want SUCCESS", result.Status)
	}
	if result.Url != "https://example.com/video.mp4" {
		t.Fatalf("url = %q, want output url", result.Url)
	}
	if result.TotalTokens != 40594 || result.CompletionTokens != 40594 {
		t.Fatalf("tokens = completion:%d total:%d, want 40594", result.CompletionTokens, result.TotalTokens)
	}
	if result.Duration != 4 {
		t.Fatalf("duration = %v, want 4", result.Duration)
	}
}

func TestParseTaskResultFailedWithObjectError(t *testing.T) {
	adaptor := &TaskAdaptor{}
	result, err := adaptor.ParseTaskResult([]byte(`{
		"task": {
			"id": "mvt-1",
			"status": "failed",
			"error": {"message": "quota exhausted", "code": "quota_exhausted"}
		}
	}`))
	if err != nil {
		t.Fatalf("ParseTaskResult returned error: %v", err)
	}
	if result.Status != "FAILURE" {
		t.Fatalf("status = %q, want FAILURE", result.Status)
	}
	if result.Reason != "quota exhausted" {
		t.Fatalf("reason = %q, want quota exhausted", result.Reason)
	}
}

func TestGetPriceScaleUsesTokenPriceTier(t *testing.T) {
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Set("task_request", relaycommon.TaskSubmitReq{
		Model:   "dreamina-seedance-2-0-fast-260128",
		Seconds: "4",
		Size:    "720p",
		Images:  []string{"asset://asset-123"},
	})

	got, err := (&TaskAdaptor{}).GetPriceScale(c, &relaycommon.RelayInfo{})
	if err != nil {
		t.Fatalf("GetPriceScale returned error: %v", err)
	}

	want := float32(48000.0 / 1_000_000 * (3.30 / 5.60))
	if math.Abs(float64(got-want)) > 0.000001 {
		t.Fatalf("price scale = %f, want %f", got, want)
	}
}

func TestGetPriceScaleTreatsDirectImageURLAsNoRefBilling(t *testing.T) {
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Set("task_request", relaycommon.TaskSubmitReq{
		Model:   "dreamina-seedance-2-0-fast-260128",
		Seconds: "4",
		Size:    "720p",
		Images:  []string{"https://example.com/ref.jpg"},
	})

	got, err := (&TaskAdaptor{}).GetPriceScale(c, &relaycommon.RelayInfo{})
	if err != nil {
		t.Fatalf("GetPriceScale returned error: %v", err)
	}

	want := float32(48000.0 / 1_000_000)
	if math.Abs(float64(got-want)) > 0.000001 {
		t.Fatalf("price scale = %f, want %f", got, want)
	}
}

func TestGetUnitPriceScaleUsesPersistedBillingMetadata(t *testing.T) {
	meta := billingMetadata{
		Model:                      "dreamina-seedance-2-0-260128",
		Resolution:                 "1080p",
		HasReference:               true,
		PriceTier:                  "1080p_with_ref",
		SelectedPriceUSDPerMillion: 4.70,
		BasePriceUSDPerMillion:     7.00,
	}
	body, err := withLocalBillingMetadata([]byte(`{"task":{"id":"mvt-1"}}`), meta)
	if err != nil {
		t.Fatalf("withLocalBillingMetadata returned error: %v", err)
	}
	var persisted map[string]interface{}
	if err := json.Unmarshal(body, &persisted); err != nil {
		t.Fatalf("unmarshal persisted metadata: %v", err)
	}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Set("task_request", relaycommon.TaskSubmitReq{
		Model:    "dreamina-seedance-2-0-260128",
		Metadata: persisted,
	})

	got, err := (&TaskAdaptor{}).GetUnitPriceScale(c, &relaycommon.RelayInfo{})
	if err != nil {
		t.Fatalf("GetUnitPriceScale returned error: %v", err)
	}

	want := float32((4.70 / 7.00) / 1_000_000)
	if math.Abs(float64(got-want)) > 0.000000001 {
		t.Fatalf("unit price scale = %.12f, want %.12f", got, want)
	}
}
