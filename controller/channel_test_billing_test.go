package controller

import (
	"net/http/httptest"
	"testing"

	"github.com/QuantumNous/new-api/constant"
	"github.com/QuantumNous/new-api/dto"
	"github.com/QuantumNous/new-api/types"

	"github.com/gin-gonic/gin"
)

func TestChannelTestTokenOtherIncludesImageOutput(t *testing.T) {
	gin.SetMode(gin.TestMode)
	c, _ := gin.CreateTestContext(httptest.NewRecorder())
	c.Set("gemini_image_output_count", 1)

	usage := &dto.Usage{
		PromptTokens:     2,
		CompletionTokens: 1409,
		TotalTokens:      1411,
	}
	usage.CompletionTokenDetails.ImageTokens = 1409

	breakdown := buildChannelTestTokenBreakdown(c, usage, types.PriceData{
		ImageRatio:           1,
		ImageCompletionRatio: 120,
		ModelRatio:           1,
		CompletionRatio:      6,
		GroupRatioInfo:       types.GroupRatioInfo{GroupRatio: 1},
		CacheRatio:           1,
		CacheCreationRatio:   1,
	})
	other := map[string]interface{}{}
	appendChannelTestTokenOther(other, breakdown)

	if got := other["output_image_tokens"]; got != 1409 {
		t.Fatalf("output_image_tokens = %v, want 1409", got)
	}
	if got := other["image_completion_ratio"]; got != float64(120) {
		t.Fatalf("image_completion_ratio = %v, want 120", got)
	}
	if got := other["gemini_image_output_count"]; got != 1 {
		t.Fatalf("gemini_image_output_count = %v, want 1", got)
	}
	if _, ok := other["output_non_image_tokens"]; ok {
		t.Fatalf("output_non_image_tokens should be omitted for image-only output: %v", other["output_non_image_tokens"])
	}
}

func TestChannelTestGeminiImageEndpointPathUsesModel(t *testing.T) {
	path, ok := channelTestEndpointPath(string(constant.EndpointTypeGemini), "gemini-3-pro-image-preview")
	if !ok {
		t.Fatal("expected gemini endpoint path")
	}
	if path != "/v1beta/models/gemini-3-pro-image-preview:generateContent" {
		t.Fatalf("path = %q", path)
	}
}

func TestBuildTestRequestUsesImagePromptForGeminiImageModels(t *testing.T) {
	req := buildTestRequest("gemini-3-pro-image-preview", "", false)
	generalReq, ok := req.(*dto.GeneralOpenAIRequest)
	if !ok {
		t.Fatalf("request type = %T, want *dto.GeneralOpenAIRequest", req)
	}
	if len(generalReq.Messages) != 1 {
		t.Fatalf("messages len = %d, want 1", len(generalReq.Messages))
	}
	content, ok := generalReq.Messages[0].Content.(string)
	if !ok {
		t.Fatalf("message content type = %T, want string", generalReq.Messages[0].Content)
	}
	if content == "hi" {
		t.Fatal("gemini image test prompt should request image output")
	}
}
