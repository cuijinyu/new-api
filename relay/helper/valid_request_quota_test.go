package helper

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	relayconstant "github.com/QuantumNous/new-api/relay/constant"

	"github.com/gin-gonic/gin"
)

func TestGetAndValidOpenAIImageRequestRejectsLargeN(t *testing.T) {
	gin.SetMode(gin.TestMode)
	body := []byte(`{"model":"dall-e-3","prompt":"quota overflow validation","n":101,"size":"1024x1024"}`)
	req := httptest.NewRequest(http.MethodPost, "/v1/images/generations", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = req

	_, err := GetAndValidOpenAIImageRequest(c, relayconstant.RelayModeImagesGenerations)
	if err == nil {
		t.Fatal("expected n above maxImageN to be rejected")
	}
	if !strings.Contains(err.Error(), "n must be between 1 and 100") {
		t.Fatalf("unexpected error: %v", err)
	}
}
