package middleware

import (
	"encoding/json"
	"testing"
)

func TestMapArkStatus(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"SUCCESS", "succeeded"},
		{"succeeded", "succeeded"},
		{"SUCCEEDED", "succeeded"},
		{"FAILURE", "failed"},
		{"failed", "failed"},
		{"QUEUED", "queued"},
		{"SUBMITTED", "queued"},
		{"NOT_START", "queued"},
		{"PENDING", "queued"},
		{"pending", "queued"}, // lowercase upstream status
		{"CREATED", "queued"},
		{"IN_PROGRESS", "processing"},
		{"PROCESSING", "processing"},
		{"RUNNING", "processing"},
		{"UNKNOWN", "processing"},
		{"", "processing"},
		{"something_new", "something_new"}, // unknown -> lowercased passthrough
	}
	for _, c := range cases {
		got := mapArkStatus(c.in)
		if got != c.want {
			t.Errorf("mapArkStatus(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestIsSuccessFailureStatus(t *testing.T) {
	successCases := []string{"SUCCESS", "succeeded", "SUCCEEDED"}
	for _, s := range successCases {
		if !isSuccessStatus(s) {
			t.Errorf("isSuccessStatus(%q) = false, want true", s)
		}
	}
	if isSuccessStatus("FAILURE") {
		t.Error("isSuccessStatus(FAILURE) = true, want false")
	}

	failureCases := []string{"FAILURE", "failed", "FAILED"}
	for _, s := range failureCases {
		if !isFailureStatus(s) {
			t.Errorf("isFailureStatus(%q) = false, want true", s)
		}
	}
	if isFailureStatus("SUCCESS") {
		t.Error("isFailureStatus(SUCCESS) = true, want false")
	}
}

// decodeJSON unmarshals a JSON byte slice into a generic map for order-independent
// comparison (encoding/json sorts map keys, but comparing as maps is clearest).
func decodeJSON(t *testing.T, b []byte) map[string]interface{} {
	t.Helper()
	var m map[string]interface{}
	if err := json.Unmarshal(b, &m); err != nil {
		t.Fatalf("failed to decode JSON %q: %v", string(b), err)
	}
	return m
}

func TestRewriteArkSubmitResponse(t *testing.T) {
	t.Run("basic pending submit", func(t *testing.T) {
		in := []byte(`{"task_id":"mvt-abc","status":"pending"}`)
		out := rewriteArkSubmitResponse(in)
		m := decodeJSON(t, out)
		if m["id"] != "mvt-abc" {
			t.Errorf("id = %v, want mvt-abc", m["id"])
		}
		if m["status"] != "queued" {
			t.Errorf("status = %v, want queued", m["status"])
		}
	})

	t.Run("includes model when present", func(t *testing.T) {
		in := []byte(`{"task_id":"mvt-1","status":"queued","model":"dreamina-seedance-2-0-fast-260128"}`)
		out := rewriteArkSubmitResponse(in)
		m := decodeJSON(t, out)
		if m["model"] != "dreamina-seedance-2-0-fast-260128" {
			t.Errorf("model = %v, want dreamina seedance fast", m["model"])
		}
	})

	t.Run("missing task_id returns nil", func(t *testing.T) {
		in := []byte(`{"status":"ok"}`)
		if rewriteArkSubmitResponse(in) != nil {
			t.Error("expected nil when task_id absent")
		}
	})

	t.Run("invalid json returns nil", func(t *testing.T) {
		in := []byte(`{not json`)
		if rewriteArkSubmitResponse(in) != nil {
			t.Error("expected nil for invalid json")
		}
	})
}

func TestRewriteArkQueryResponse(t *testing.T) {
	t.Run("success surfaces video_url from fail_reason", func(t *testing.T) {
		in := []byte(`{
			"code":"success",
			"data":{
				"task_id":"mvt-1",
				"status":"SUCCESS",
				"fail_reason":"https://cdn.example.com/v.mp4",
				"data":{"task":{"model":"dreamina-seedance-2-0-fast-260128","usage":{"total_tokens":87300,"completion_tokens":87300}}}
			}
		}`)
		out := rewriteArkQueryResponse(in)
		m := decodeJSON(t, out)
		if m["id"] != "mvt-1" {
			t.Errorf("id = %v, want mvt-1", m["id"])
		}
		if m["status"] != "succeeded" {
			t.Errorf("status = %v, want succeeded", m["status"])
		}
		content, ok := m["content"].(map[string]interface{})
		if !ok {
			t.Fatalf("content not a map: %T", m["content"])
		}
		if content["video_url"] != "https://cdn.example.com/v.mp4" {
			t.Errorf("content.video_url = %v", content["video_url"])
		}
		if m["error"] != nil {
			t.Errorf("error should be absent on success, got %v", m["error"])
		}
		if m["model"] != "dreamina-seedance-2-0-fast-260128" {
			t.Errorf("model = %v", m["model"])
		}
		usage, ok := m["usage"].(map[string]interface{})
		if !ok {
			t.Fatalf("usage not a map: %T", m["usage"])
		}
		if usage["total_tokens"] != float64(87300) {
			t.Errorf("usage.total_tokens = %v, want 87300", usage["total_tokens"])
		}
	})

	t.Run("failure surfaces error.message and no video_url", func(t *testing.T) {
		in := []byte(`{
			"code":"success",
			"data":{"task_id":"mvt-2","status":"FAILURE","fail_reason":"upstream timeout"}
		}`)
		out := rewriteArkQueryResponse(in)
		m := decodeJSON(t, out)
		if m["status"] != "failed" {
			t.Errorf("status = %v, want failed", m["status"])
		}
		errObj, ok := m["error"].(map[string]interface{})
		if !ok {
			t.Fatalf("error not a map: %T", m["error"])
		}
		if errObj["message"] != "upstream timeout" {
			t.Errorf("error.message = %v", errObj["message"])
		}
		if m["content"] != nil {
			t.Errorf("content should be absent on failure, got %v", m["content"])
		}
	})

	t.Run("in-progress has no content and no error", func(t *testing.T) {
		in := []byte(`{"code":"success","data":{"task_id":"mvt-3","status":"IN_PROGRESS"}}`)
		out := rewriteArkQueryResponse(in)
		m := decodeJSON(t, out)
		if m["status"] != "processing" {
			t.Errorf("status = %v, want processing", m["status"])
		}
		if m["content"] != nil {
			t.Errorf("content should be absent while processing, got %v", m["content"])
		}
		if m["error"] != nil {
			t.Errorf("error should be absent while processing, got %v", m["error"])
		}
	})

	t.Run("invalid json returns nil", func(t *testing.T) {
		if rewriteArkQueryResponse([]byte(`{broken`)) != nil {
			t.Error("expected nil for invalid json")
		}
	})

	t.Run("missing data returns nil", func(t *testing.T) {
		if rewriteArkQueryResponse([]byte(`{"code":"success"}`)) != nil {
			t.Error("expected nil when data absent")
		}
	})
}

func TestRewriteArkResponseDispatch(t *testing.T) {
	t.Run("empty body returns nil", func(t *testing.T) {
		if rewriteArkResponse(nil, "POST") != nil {
			t.Error("expected nil for empty body")
		}
	})
	t.Run("POST dispatches to submit", func(t *testing.T) {
		out := rewriteArkResponse([]byte(`{"task_id":"mvt-x","status":"queued"}`), "POST")
		m := decodeJSON(t, out)
		if m["id"] != "mvt-x" {
			t.Errorf("id = %v, want mvt-x", m["id"])
		}
	})
	t.Run("GET dispatches to query", func(t *testing.T) {
		out := rewriteArkResponse([]byte(`{"code":"success","data":{"task_id":"mvt-y","status":"SUCCESS"}}`), "GET")
		m := decodeJSON(t, out)
		if m["id"] != "mvt-y" {
			t.Errorf("id = %v, want mvt-y", m["id"])
		}
		if m["status"] != "succeeded" {
			t.Errorf("status = %v, want succeeded", m["status"])
		}
	})
}

func TestExtractArkModelAndUsage(t *testing.T) {
	t.Run("service-inference nested task shape", func(t *testing.T) {
		in := []byte(`{"task":{"model":"dreamina-seedance-2-0-fast-260128","usage":{"total_tokens":100,"completion_tokens":100}},"_newapi_service_inference_billing":{"estimated_tokens":48000}}`)
		out := map[string]interface{}{}
		extractArkModelAndUsage(in, out)
		if out["model"] != "dreamina-seedance-2-0-fast-260128" {
			t.Errorf("model = %v", out["model"])
		}
		usage, ok := out["usage"].(map[string]interface{})
		if !ok {
			t.Fatalf("usage not a map: %T", out["usage"])
		}
		if usage["total_tokens"] != float64(100) {
			t.Errorf("total_tokens = %v, want 100", usage["total_tokens"])
		}
	})

	t.Run("falls back to top-level usage", func(t *testing.T) {
		in := []byte(`{"usage":{"total_tokens":5}}`)
		out := map[string]interface{}{}
		extractArkModelAndUsage(in, out)
		usage, ok := out["usage"].(map[string]interface{})
		if !ok {
			t.Fatalf("usage not a map: %T", out["usage"])
		}
		if usage["total_tokens"] != float64(5) {
			t.Errorf("total_tokens = %v, want 5", usage["total_tokens"])
		}
	})

	t.Run("does not overwrite an existing model", func(t *testing.T) {
		in := []byte(`{"task":{"model":"should-not-win"}}`)
		out := map[string]interface{}{"model": "already-set"}
		extractArkModelAndUsage(in, out)
		if out["model"] != "already-set" {
			t.Errorf("model = %v, want already-set", out["model"])
		}
	})

	t.Run("empty payload is a no-op", func(t *testing.T) {
		in := []byte(`{}`)
		out := map[string]interface{}{}
		extractArkModelAndUsage(in, out)
		if len(out) != 0 {
			t.Errorf("expected empty out, got %v", out)
		}
	})

	t.Run("invalid json is a no-op", func(t *testing.T) {
		in := []byte(`{not json`)
		out := map[string]interface{}{}
		extractArkModelAndUsage(in, out)
		if len(out) != 0 {
			t.Errorf("expected empty out on invalid json, got %v", out)
		}
	})
}
