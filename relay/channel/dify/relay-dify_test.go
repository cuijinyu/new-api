package dify

import (
	"testing"

	"github.com/QuantumNous/new-api/dto"
)

func TestRequestOpenAI2DifyRemoteImage(t *testing.T) {
	req := dto.GeneralOpenAIRequest{
		User: "test-user",
		Messages: []dto.Message{
			{
				Role: "user",
				Content: []any{
					dto.MediaContent{
						Type: dto.ContentTypeImageURL,
						ImageUrl: &dto.MessageImageUrl{
							Url:      "https://example.com/image.png",
							MimeType: "image/png",
						},
					},
				},
			},
		},
	}

	difyReq := requestOpenAI2Dify(nil, nil, req)
	if difyReq == nil {
		t.Fatal("expected Dify request")
	}
	if len(difyReq.Files) != 1 {
		t.Fatalf("expected one file, got %d", len(difyReq.Files))
	}

	file := difyReq.Files[0]
	if file.TransferMode != "remote_url" {
		t.Fatalf("expected remote_url transfer mode, got %q", file.TransferMode)
	}
	if file.URL != "https://example.com/image.png" {
		t.Fatalf("expected remote image URL, got %q", file.URL)
	}
	if file.Type != "image/png" {
		t.Fatalf("expected image/png type, got %q", file.Type)
	}
}
