package openai

import (
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/dto"
	relaycommon "github.com/QuantumNous/new-api/relay/common"
	"github.com/QuantumNous/new-api/relay/helper"
	"github.com/QuantumNous/new-api/service"
	"github.com/QuantumNous/new-api/types"

	"github.com/gin-gonic/gin"
	"github.com/tidwall/gjson"
	"github.com/tidwall/sjson"
)

// maxImageN caps the actual image count we are willing to bill, guarding
// against absurd upstream values. Upstream defines dto.MaxImageN; this fork
// does not have that constant, so we use a sane local ceiling.
const maxImageN = 100

// setOpenAIImageCount records the actual completed image count into
// PriceData.OtherRatios["n"]. ImageHelper reads this back after DoResponse to
// rescale ModelPrice, so billing reflects what was actually delivered rather
// than only what was requested.
func setOpenAIImageCount(info *relaycommon.RelayInfo, count int64) {
	if info == nil || !info.PriceData.UsePrice || count <= 0 || count > maxImageN {
		return
	}
	if info.PriceData.OtherRatios == nil {
		info.PriceData.OtherRatios = make(map[string]float64)
	}
	info.PriceData.OtherRatios["n"] = float64(count)
}

// normalizeImageUsage maps the input_tokens/output_tokens fields that some
// image providers (gpt-image-1) return onto the prompt_tokens/completion_tokens
// fields the billing layer expects. This fork has no shared
// normalizeOpenAIUsage helper, so this mirrors the inline logic in
// OpenaiHandlerWithUsage.
func normalizeImageUsage(usage *dto.Usage) {
	if usage == nil {
		return
	}
	if usage.InputTokens > 0 {
		usage.PromptTokens += usage.InputTokens
	}
	if usage.OutputTokens > 0 {
		usage.CompletionTokens += usage.OutputTokens
	}
	if usage.InputTokensDetails != nil {
		usage.PromptTokensDetails.ImageTokens += usage.InputTokensDetails.ImageTokens
		usage.PromptTokensDetails.TextTokens += usage.InputTokensDetails.TextTokens
	}
}

// OpenaiImageHandler handles non-streaming OpenAI image responses
// (generations/edits), returning the parsed usage for billing. Compared to
// the generic OpenaiHandlerWithUsage it additionally:
//   - rejects upstream error bodies (200 with an error payload) before billing,
//   - records the actual delivered image count for billing.
func OpenaiImageHandler(c *gin.Context, info *relaycommon.RelayInfo, resp *http.Response) (*dto.Usage, *types.NewAPIError) {
	defer service.CloseResponseBodyGracefully(resp)

	responseBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, types.NewOpenAIError(err, types.ErrorCodeReadResponseBodyFailed, http.StatusInternalServerError)
	}

	var usageResp dto.SimpleResponse
	if err := common.Unmarshal(responseBody, &usageResp); err != nil {
		return nil, types.NewOpenAIError(err, types.ErrorCodeBadResponseBody, http.StatusInternalServerError)
	}
	if oaiError := usageResp.GetOpenAIError(); oaiError != nil && oaiError.Type != "" {
		return nil, types.WithOpenAIError(*oaiError, resp.StatusCode)
	}

	// Bill by the actual number of images returned, not just the requested n.
	setOpenAIImageCount(info, gjson.GetBytes(responseBody, "data.#").Int())

	// Write the original response body to the client unchanged.
	service.IOCopyBytesGracefully(c, resp, responseBody)

	normalizeImageUsage(&usageResp.Usage)
	applyUsagePostProcessing(info, &usageResp.Usage, responseBody)
	return &usageResp.Usage, nil
}

// OpenaiImageStreamHandler handles image responses when info.IsStream is true.
// It supports two upstream shapes:
//   - true SSE ("text/event-stream"): forwarded chunk by chunk via the shared
//     StreamScannerHandler, with a disconnect-aware billing guard.
//   - a buffered JSON body: converted to SSE with gjson/sjson to avoid copying
//     multi-MB Base64 blobs through Go structs.
func OpenaiImageStreamHandler(c *gin.Context, info *relaycommon.RelayInfo, resp *http.Response) (*dto.Usage, *types.NewAPIError) {
	if resp.StatusCode != http.StatusOK {
		return OpenaiImageHandler(c, info, resp)
	}
	contentType := resp.Header.Get("Content-Type")
	if !strings.Contains(contentType, "text/event-stream") {
		return openaiImageJSONAsStreamHandler(c, info, resp)
	}

	// Reuse the shared streaming engine (helper.StreamScannerHandler) so the
	// image streaming path gets the same ping keepalive, streaming-timeout
	// enforcement, and client-disconnect detection as the text paths.
	usage := &dto.Usage{}
	var completedImages int64

	helper.StreamScannerHandler(c, resp, info, func(data string) bool {
		// Stop promptly if the client has gone away; the scanner also watches
		// the request context, but this avoids one extra write to a dead socket.
		if c.Request.Context().Err() != nil {
			return false
		}
		raw := common.StringToByteSlice(data)

		var chunk struct {
			Type  string    `json:"type"`
			Usage dto.Usage `json:"usage"`
		}
		if err := common.Unmarshal(raw, &chunk); err == nil {
			normalizeImageUsage(&chunk.Usage)
			if service.ValidUsage(&chunk.Usage) {
				usage = &chunk.Usage
			}
			if chunk.Type == "image_generation.completed" || chunk.Type == "image_edit.completed" {
				completedImages++
			}
		}
		writeOpenaiImageStreamChunk(c, raw)
		return true
	})

	// Re-emit the terminal [DONE] only when the client is still connected.
	// StreamScannerHandler consumes the upstream [DONE] without forwarding it.
	if c.Request.Context().Err() == nil {
		helper.Done(c)
	}

	applyUsagePostProcessing(info, usage, nil)

	// Disconnect-aware billing guard. Upstream already generated (and was
	// charged for) all requested images, so a client abort after the first
	// completed event must not lower the charge. We only trust the
	// completed-event counter when the stream ended cleanly; on abort we keep
	// the requested n — unless completed events already exceed it, in which
	// case the higher actual count wins regardless.
	clientGone := c.Request.Context().Err() != nil
	requestedN := 1.0
	if info.PriceData.OtherRatios != nil {
		if n, ok := info.PriceData.OtherRatios["n"]; ok && n > 0 {
			requestedN = n
		}
	}
	if !clientGone || float64(completedImages) > requestedN {
		setOpenAIImageCount(info, completedImages)
	}
	return usage, nil
}

// writeOpenaiImageStreamChunk rebuilds the SSE frame for an image stream chunk:
// it emits an "event:" line derived from the JSON "type" field (when present)
// followed by the verbatim "data:" payload, mirroring helper.ResponseChunkData.
func writeOpenaiImageStreamChunk(c *gin.Context, data []byte) {
	var payload struct {
		Type string `json:"type"`
	}
	_ = common.Unmarshal(data, &payload)
	if eventName := strings.TrimSpace(payload.Type); eventName != "" {
		helper.ResponseChunkData(c, dto.ResponsesStreamResponse{Type: eventName}, string(data))
		return
	}
	_ = helper.StringData(c, string(data))
}

// openaiImageJSONAsStreamHandler converts a buffered JSON image response into
// an SSE stream. It deliberately avoids unmarshalling data[] into Go structs:
// every b64_json value can be multi-MB, and marshalling/copying them per event
// dominates memory. Instead it uses gjson to count and slice, and sjson to
// assemble each SSE payload directly from byte slices of the original buffer.
func openaiImageJSONAsStreamHandler(c *gin.Context, info *relaycommon.RelayInfo, resp *http.Response) (*dto.Usage, *types.NewAPIError) {
	defer service.CloseResponseBodyGracefully(resp)

	responseBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, types.NewOpenAIError(err, types.ErrorCodeReadResponseBodyFailed, http.StatusInternalServerError)
	}

	// Only decode usage/error. Do not Unmarshal data[] into dto.ImageResponse —
	// b64_json values are large and would be copied into Go strings then
	// re-marshaled for each SSE event.
	var usageResp dto.SimpleResponse
	if err := common.Unmarshal(responseBody, &usageResp); err != nil {
		return nil, types.NewOpenAIError(err, types.ErrorCodeBadResponseBody, http.StatusInternalServerError)
	}
	if oaiError := usageResp.GetOpenAIError(); oaiError != nil && oaiError.Type != "" {
		return nil, types.WithOpenAIError(*oaiError, resp.StatusCode)
	}
	normalizeImageUsage(&usageResp.Usage)
	applyUsagePostProcessing(info, &usageResp.Usage, responseBody)

	imageCount := gjson.GetBytes(responseBody, "data.#").Int()
	setOpenAIImageCount(info, imageCount)

	helper.SetEventStreamHeaders(c)
	c.Status(http.StatusOK)

	created := gjson.GetBytes(responseBody, "created").Int()
	if created == 0 {
		created = time.Now().Unix()
	}
	if info != nil {
		info.SetFirstResponseTime()
	}

	validUsage := service.ValidUsage(&usageResp.Usage)
	var usageJSON []byte
	if validUsage {
		usageJSON, err = common.Marshal(usageResp.Usage)
		if err != nil {
			return nil, types.NewOpenAIError(err, types.ErrorCodeBadResponseBody, http.StatusInternalServerError)
		}
	}

	clientGone := false
	for i := int64(0); i < imageCount; i++ {
		if c.Request.Context().Err() != nil {
			clientGone = true
			break
		}
		dataPath := "data." + strconv.FormatInt(i, 10)
		payload := []byte(`{"type":"image_generation.completed"}`)
		payload, err = sjson.SetBytes(payload, "created_at", created)
		if err != nil {
			return nil, types.NewOpenAIError(err, types.ErrorCodeBadResponseBody, http.StatusInternalServerError)
		}
		if validUsage {
			payload, err = sjson.SetRawBytes(payload, "usage", usageJSON)
			if err != nil {
				return nil, types.NewOpenAIError(err, types.ErrorCodeBadResponseBody, http.StatusInternalServerError)
			}
		}
		// b64_json goes last: every sjson.Set* reallocates the whole payload,
		// so inserting the large blob after all small fields avoids re-copying
		// multi-MB buffers. We query each field directly against the full
		// responseBody via gjson.GetBytes so value.Index is guaranteed to be an
		// offset into responseBody, enabling a zero-copy slice of the base64.
		for _, field := range []string{"url", "revised_prompt", "b64_json"} {
			value := gjson.GetBytes(responseBody, dataPath+"."+field)
			if value.Type != gjson.String || value.Raw == `""` {
				continue
			}
			raw := []byte(value.Raw)
			if value.Index > 0 && value.Index+len(value.Raw) <= len(responseBody) {
				raw = responseBody[value.Index : value.Index+len(value.Raw)]
			}
			payload, err = sjson.SetRawBytes(payload, field, raw)
			if err != nil {
				return nil, types.NewOpenAIError(err, types.ErrorCodeBadResponseBody, http.StatusInternalServerError)
			}
		}
		helper.ResponseChunkData(c, dto.ResponsesStreamResponse{Type: "image_generation.completed"}, string(payload))
	}

	if !clientGone {
		helper.Done(c)
	}
	return &usageResp.Usage, nil
}