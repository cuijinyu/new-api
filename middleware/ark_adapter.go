package middleware

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"

	"github.com/QuantumNous/new-api/common"
	relayconstant "github.com/QuantumNous/new-api/relay/constant"

	"github.com/gin-gonic/gin"
)

// ArkRequestConvert exposes a BytePlus / Volcengine Ark-style entry for video
// (Seedance) tasks. Clients send requests in the Ark native shape:
//
//	POST /ark/api/v3/contents/generations/tasks        {model, content[], ...}
//	GET  /ark/api/v3/contents/generations/tasks/{id}
//
// The upstream link itself is unchanged (it still goes through whatever video
// channel — e.g. Service Inference — the token resolves to). This converter only
// reshapes the request into the unified /v1/video/generations flow, then rewrites
// the response body back to the Ark shape ({id,...} on submit; {id,model,status,
// content,usage} on query) so existing BytePlus SDK clients integrate unchanged.
func ArkRequestConvert() gin.HandlerFunc {
	return func(c *gin.Context) {
		path := c.Request.URL.Path
		isSubmit := c.Request.Method == http.MethodPost && strings.HasSuffix(path, "/contents/generations/tasks")
		isQuery := c.Request.Method == http.MethodGet && strings.Contains(path, "/contents/generations/tasks/")

		if isSubmit {
			if err := convertArkSubmitRequest(c); err != nil {
				abortWithOpenAiMessage(c, http.StatusBadRequest, "Invalid Ark request body: "+err.Error())
				return
			}
		} else if isQuery {
			convertArkQueryRequest(c)
		}

		// Buffer the response so we can reshape it to the Ark format on the way out.
		bw := &arkBodyWriter{ResponseWriter: c.Writer, body: &bytes.Buffer{}}
		c.Writer = bw

		c.Next()

		status := bw.ResponseWriter.Status()
		var emitted []byte
		if status >= 200 && status < 300 {
			emitted = rewriteArkResponse(bw.body.Bytes(), c.Request.Method)
		}
		if len(emitted) == 0 {
			emitted = bw.body.Bytes()
		}
		// Rewriting the body changes its length; reset header fields and let the
		// underlying writer flush status + headers on the next Write.
		bw.ResponseWriter.Header().Set("Content-Type", "application/json")
		bw.ResponseWriter.Header().Set("Content-Length", strconv.Itoa(len(emitted)))
		_, _ = bw.ResponseWriter.Write(emitted)
	}
}

// arkBodyWriter buffers everything written to the response body without forwarding,
// so the wrapping middleware can transform the bytes before they reach the wire.
// Status codes and headers are still routed through the embedded gin.ResponseWriter.
type arkBodyWriter struct {
	gin.ResponseWriter
	body *bytes.Buffer
}

func (w *arkBodyWriter) Write(b []byte) (int, error) {
	return w.body.Write(b)
}

func (w *arkBodyWriter) WriteString(s string) (int, error) {
	return w.body.WriteString(s)
}

// convertArkSubmitRequest parses an Ark submit body ({model, content[], duration, ...})
// and rewrites it into the unified TaskSubmitReq shape consumed by /v1/video/generations.
func convertArkSubmitRequest(c *gin.Context) error {
	var arkReq map[string]interface{}
	if err := common.UnmarshalBodyReusable(c, &arkReq); err != nil {
		return err
	}

	unified := map[string]interface{}{}
	meta := map[string]interface{}{}
	unified["metadata"] = meta

	if m, ok := arkReq["model"].(string); ok && m != "" {
		unified["model"] = m
	}

	// Ark content[] → prompt + images + non-text passthrough (video/audio refs).
	if contents, ok := arkReq["content"].([]interface{}); ok {
		var texts []string
		var images []string
		var passthrough []map[string]interface{}
		for _, raw := range contents {
			item, ok := raw.(map[string]interface{})
			if !ok {
				continue
			}
			switch item["type"] {
			case "text":
				if t, ok := item["text"].(string); ok && strings.TrimSpace(t) != "" {
					texts = append(texts, t)
				}
			case "image_url":
				// images go via the top-level `images` field (handled below) so the
				// downstream adaptor can attach the reference_image role uniformly.
				if iu, ok := item["image_url"].(map[string]interface{}); ok {
					if u, ok := iu["url"].(string); ok && u != "" {
						images = append(images, u)
					}
				}
			case "video_url", "audio_url":
				// Preserve these as upstream content items with their original role.
				passthrough = append(passthrough, item)
			}
		}
		if len(texts) > 0 {
			unified["prompt"] = strings.Join(texts, "\n")
		}
		if len(images) > 0 {
			unified["images"] = images
		}
		if len(passthrough) > 0 {
			meta["content"] = passthrough
		}
	}

	// Top-level Ark / Seedance parameters are forwarded via metadata so the
	// service-inference adaptor picks them up (resolution, ratio, duration, ...).
	for _, k := range []string{"resolution", "ratio", "duration", "seconds", "size", "generate_audio", "watermark"} {
		if v, ok := arkReq[k]; ok {
			meta[k] = v
		}
	}

	data, err := json.Marshal(unified)
	if err != nil {
		return err
	}
	c.Request.Body = io.NopCloser(bytes.NewBuffer(data))
	c.Set(common.KeyRequestBody, data)
	c.Request.URL.Path = "/v1/video/generations"
	return nil
}

// convertArkQueryRequest rewrites an Ark GET poll into the unified fetch-by-id flow.
func convertArkQueryRequest(c *gin.Context) {
	taskID := c.Param("task_id")
	if taskID == "" {
		// Fallback: derive from the trailing path segment.
		idx := strings.LastIndex(c.Request.URL.Path, "/")
		if idx >= 0 && idx < len(c.Request.URL.Path)-1 {
			taskID = c.Request.URL.Path[idx+1:]
		}
	}
	if taskID != "" {
		c.Set("task_id", taskID)
		c.Set("relay_mode", relayconstant.RelayModeVideoFetchByID)
		c.Request.URL.Path = "/v1/video/generations/" + taskID
	}
}

// rewriteArkResponse reshapes the buffered response body to the Ark native format.
// Returns nil when the body is not recognized (caller then passes the original through).
func rewriteArkResponse(body []byte, method string) []byte {
	if len(body) == 0 {
		return nil
	}
	if method == http.MethodPost {
		return rewriteArkSubmitResponse(body)
	}
	return rewriteArkQueryResponse(body)
}

func rewriteArkSubmitResponse(body []byte) []byte {
	var m map[string]json.RawMessage
	if err := json.Unmarshal(body, &m); err != nil {
		return nil
	}
	rawID, ok := m["task_id"]
	if !ok {
		return nil // not a submit response we know how to translate
	}
	out := map[string]interface{}{}
	var id string
	if json.Unmarshal(rawID, &id) == nil {
		out["id"] = id
	}
	if raw, ok := m["status"]; ok {
		var s string
		if json.Unmarshal(raw, &s) == nil {
			out["status"] = mapArkStatus(s)
		}
	}
	if raw, ok := m["model"]; ok {
		var s string
		if json.Unmarshal(raw, &s) == nil && s != "" {
			out["model"] = s
		}
	}
	decoded, err := json.Marshal(out)
	if err != nil {
		return nil
	}
	return decoded
}

func rewriteArkQueryResponse(body []byte) []byte {
	var wrapper struct {
		Code string                 `json:"code"`
		Data map[string]interface{} `json:"data"`
	}
	if err := json.Unmarshal(body, &wrapper); err != nil || wrapper.Data == nil {
		return nil
	}

	out := map[string]interface{}{}
	if id, ok := wrapper.Data["task_id"].(string); ok {
		out["id"] = id
	}
	statusRaw, _ := wrapper.Data["status"].(string)
	out["status"] = mapArkStatus(statusRaw)

	// On success the final video URL is carried by fail_reason (see RefreshVideoTaskForFetch).
	if fr, ok := wrapper.Data["fail_reason"].(string); ok && fr != "" && isSuccessStatus(statusRaw) {
		out["content"] = map[string]interface{}{"video_url": fr}
	}
	// Reason on failure for client visibility.
	if fr, ok := wrapper.Data["fail_reason"].(string); ok && fr != "" && isFailureStatus(statusRaw) {
		out["error"] = map[string]interface{}{"message": fr}
	}

	// Model + usage are nested inside the stored raw upstream payload (task.Data).
	if raw, ok := wrapper.Data["data"]; ok {
		if dataBytes, err := json.Marshal(raw); err == nil {
			extractArkModelAndUsage(dataBytes, out)
		}
	}

	if st, ok := wrapper.Data["submit_time"]; ok {
		out["created_at"] = st
	}
	if ft, ok := wrapper.Data["finish_time"]; ok {
		out["updated_at"] = ft
	}

	decoded, err := json.Marshal(out)
	if err != nil {
		return nil
	}
	return decoded
}

// extractArkModelAndUsage pulls model/usage out of the stored upstream payload.
// Service-Inference shape: {"task":{"model":..,"usage":{..}}, "_newapi_...":{..}}
func extractArkModelAndUsage(dataBytes []byte, out map[string]interface{}) {
	var data map[string]interface{}
	if err := json.Unmarshal(dataBytes, &data); err != nil {
		return
	}
	if task, ok := data["task"].(map[string]interface{}); ok {
		if m, ok := task["model"].(string); ok && m != "" {
			if _, exists := out["model"]; !exists {
				out["model"] = m
			}
		}
		if u, ok := task["usage"].(map[string]interface{}); ok {
			out["usage"] = u
		}
	}
	if _, exists := out["usage"]; !exists {
		if u, ok := data["usage"].(map[string]interface{}); ok {
			out["usage"] = u
		}
	}
}

func mapArkStatus(s string) string {
	switch strings.ToUpper(strings.TrimSpace(s)) {
	case "SUCCESS", "SUCCEEDED":
		return "succeeded"
	case "FAILURE", "FAILED":
		return "failed"
	case "QUEUED", "SUBMITTED", "NOT_START", "PENDING", "CREATED":
		return "queued"
	case "IN_PROGRESS", "PROCESSING", "RUNNING":
		return "processing"
	case "UNKNOWN", "":
		return "processing"
	default:
		return strings.ToLower(s)
	}
}

func isSuccessStatus(s string) bool {
	switch strings.ToUpper(strings.TrimSpace(s)) {
	case "SUCCESS", "SUCCEEDED":
		return true
	}
	return false
}

func isFailureStatus(s string) bool {
	switch strings.ToUpper(strings.TrimSpace(s)) {
	case "FAILURE", "FAILED":
		return true
	}
	return false
}
