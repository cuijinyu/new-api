package service

import (
	"bytes"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/pkg/cachex"
	"github.com/QuantumNous/new-api/setting/operation_setting"
	"github.com/gin-gonic/gin"
	"github.com/samber/hot"
)

func init() {
	gin.SetMode(gin.TestMode)
}

// resetPoisonCache replaces the global poison cache with a fresh in-memory instance for test isolation.
func resetPoisonCache() {
	channelAffinityPoisonCache = cachex.NewHybridCache[string](cachex.HybridCacheConfig[string]{
		Namespace:    cachex.Namespace(channelAffinityPoisonCacheNamespace),
		RedisEnabled: func() bool { return false },
		RedisCodec:   cachex.StringCodec{},
		Memory: func() *hot.HotCache[string, string] {
			return hot.NewHotCache[string, string](hot.LRU, 1000).
				WithTTL(1 * time.Hour).
				WithJanitor().
				Build()
		},
	})
}

// resetAffinityCache replaces the global affinity cache with a fresh in-memory instance for test isolation.
func resetAffinityCache() {
	channelAffinityCache = cachex.NewHybridCache[int](cachex.HybridCacheConfig[int]{
		Namespace:    cachex.Namespace(channelAffinityCacheNamespace),
		RedisEnabled: func() bool { return false },
		RedisCodec:   cachex.IntCodec{},
		Memory: func() *hot.HotCache[string, int] {
			return hot.NewHotCache[string, int](hot.LRU, 1000).
				WithTTL(1 * time.Hour).
				WithJanitor().
				Build()
		},
	})
}

func newTestContext(body string) (*gin.Context, *httptest.ResponseRecorder) {
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodPost, "/v1/messages", bytes.NewBufferString(body))
	c.Request.Header.Set("Content-Type", "application/json")
	return c, w
}

func setAffinityMeta(c *gin.Context, meta channelAffinityMeta) {
	setChannelAffinityContext(c, meta)
}

// --- Tests for InvalidateChannelAffinityOnFailure ---

func TestInvalidateChannelAffinityOnFailure_ClearsCache(t *testing.T) {
	resetAffinityCache()
	cache := getChannelAffinityCache()

	cacheKeySuffix := "claude cli trace:default:user123"
	cacheKeyFull := channelAffinityCacheNamespace + ":" + cacheKeySuffix
	_ = cache.SetWithTTL(cacheKeySuffix, 54, 1*time.Hour)

	// Verify it's in cache
	val, found, err := cache.Get(cacheKeySuffix)
	if err != nil || !found || val != 54 {
		t.Fatalf("expected cache hit with value 54, got found=%v val=%d err=%v", found, val, err)
	}

	c, _ := newTestContext(`{}`)
	setAffinityMeta(c, channelAffinityMeta{
		CacheKey:   cacheKeyFull,
		TTLSeconds: 3600,
		RuleName:   "claude cli trace",
	})

	InvalidateChannelAffinityOnFailure(c)

	// Verify it's gone
	_, found, _ = cache.Get(cacheKeySuffix)
	if found {
		t.Error("expected cache entry to be deleted after invalidation")
	}
}

func TestInvalidateChannelAffinityOnFailure_NilContext(t *testing.T) {
	// Should not panic
	InvalidateChannelAffinityOnFailure(nil)
}

func TestInvalidateChannelAffinityOnFailure_NoAffinityContext(t *testing.T) {
	resetAffinityCache()
	c, _ := newTestContext(`{}`)
	// No affinity meta set — should be a no-op
	InvalidateChannelAffinityOnFailure(c)
}

// --- Tests for RecordChannelAffinityPoison + GetChannelAffinityPoisonRewrite ---

func TestPoisonCache_RecordAndRetrieve(t *testing.T) {
	resetPoisonCache()

	body := `{"metadata":{"user_id":"abc123"},"model":"claude-3-sonnet"}`
	c, _ := newTestContext(body)
	// Pre-read body into context cache
	_, _ = common.GetRequestBody(c)

	setAffinityMeta(c, channelAffinityMeta{
		CacheKey:      channelAffinityCacheNamespace + ":claude cli trace:default:abc123",
		TTLSeconds:    3600,
		RuleName:      "claude cli trace",
		KeySourceType: "gjson",
		KeySourcePath: "metadata.user_id",
		UsingGroup:    "default",
	})

	RecordChannelAffinityPoison(c, 54)

	gjsonPath, suffix, found := GetChannelAffinityPoisonRewrite(c, 54)
	if !found {
		t.Fatal("expected poison cache hit")
	}
	if gjsonPath != "metadata.user_id" {
		t.Errorf("expected gjsonPath=metadata.user_id, got %s", gjsonPath)
	}
	if len(suffix) == 0 || suffix[:3] != "::r" {
		t.Errorf("expected suffix starting with ::r, got %s", suffix)
	}
}

func TestPoisonCache_DifferentChannelNotPoisoned(t *testing.T) {
	resetPoisonCache()

	body := `{"metadata":{"user_id":"abc123"}}`
	c, _ := newTestContext(body)
	_, _ = common.GetRequestBody(c)

	setAffinityMeta(c, channelAffinityMeta{
		CacheKey:      channelAffinityCacheNamespace + ":claude cli trace:default:abc123",
		TTLSeconds:    3600,
		RuleName:      "claude cli trace",
		KeySourceType: "gjson",
		KeySourcePath: "metadata.user_id",
		UsingGroup:    "default",
	})

	RecordChannelAffinityPoison(c, 54)

	// Channel 65 should NOT be poisoned
	_, _, found := GetChannelAffinityPoisonRewrite(c, 65)
	if found {
		t.Error("expected no poison for channel 65")
	}
}

func TestPoisonCache_NonGjsonKeySourceIgnored(t *testing.T) {
	resetPoisonCache()

	c, _ := newTestContext(`{}`)
	setAffinityMeta(c, channelAffinityMeta{
		CacheKey:      channelAffinityCacheNamespace + ":test:default:42",
		TTLSeconds:    3600,
		RuleName:      "test",
		KeySourceType: "context_int",
		KeySourceKey:  "id",
	})

	// Record should still work (it extracts value from context)
	c.Set("id", 42)
	RecordChannelAffinityPoison(c, 54)

	// But rewrite should NOT be found because key source is not gjson
	_, _, found := GetChannelAffinityPoisonRewrite(c, 54)
	if found {
		t.Error("expected no poison rewrite for non-gjson key source")
	}
}

func TestPoisonCache_NilContext(t *testing.T) {
	RecordChannelAffinityPoison(nil, 54)
	_, _, found := GetChannelAffinityPoisonRewrite(nil, 54)
	if found {
		t.Error("expected no result for nil context")
	}
}

func TestPoisonCache_ZeroChannelID(t *testing.T) {
	c, _ := newTestContext(`{}`)
	RecordChannelAffinityPoison(c, 0)
	_, _, found := GetChannelAffinityPoisonRewrite(c, 0)
	if found {
		t.Error("expected no result for zero channel ID")
	}
}

// --- Tests for ApplyChannelAffinityPoisonRewrite ---

func TestApplyPoisonRewrite_InjectsAppendOperation(t *testing.T) {
	resetPoisonCache()

	body := `{"metadata":{"user_id":"abc123"}}`
	c, _ := newTestContext(body)
	_, _ = common.GetRequestBody(c)

	setAffinityMeta(c, channelAffinityMeta{
		CacheKey:      channelAffinityCacheNamespace + ":claude cli trace:default:abc123",
		TTLSeconds:    3600,
		RuleName:      "claude cli trace",
		KeySourceType: "gjson",
		KeySourcePath: "metadata.user_id",
		UsingGroup:    "default",
	})

	RecordChannelAffinityPoison(c, 54)

	paramOverride := map[string]interface{}{
		"operations": []interface{}{
			map[string]interface{}{
				"mode":  "pass_headers",
				"value": []interface{}{"User-Agent"},
			},
		},
	}

	result, applied := ApplyChannelAffinityPoisonRewrite(c, 54, paramOverride)
	if !applied {
		t.Fatal("expected rewrite to be applied")
	}

	ops, ok := result["operations"].([]interface{})
	if !ok {
		t.Fatal("expected operations to be []interface{}")
	}
	if len(ops) != 2 {
		t.Fatalf("expected 2 operations, got %d", len(ops))
	}

	appendOp, ok := ops[1].(map[string]interface{})
	if !ok {
		t.Fatal("expected second operation to be map")
	}
	if appendOp["path"] != "metadata.user_id" {
		t.Errorf("expected path=metadata.user_id, got %v", appendOp["path"])
	}
	if appendOp["mode"] != "append" {
		t.Errorf("expected mode=append, got %v", appendOp["mode"])
	}
	suffix, ok := appendOp["value"].(string)
	if !ok || len(suffix) < 3 || suffix[:3] != "::r" {
		t.Errorf("expected value starting with ::r, got %v", appendOp["value"])
	}
}

func TestApplyPoisonRewrite_NilParamOverride(t *testing.T) {
	resetPoisonCache()

	body := `{"metadata":{"user_id":"abc123"}}`
	c, _ := newTestContext(body)
	_, _ = common.GetRequestBody(c)

	setAffinityMeta(c, channelAffinityMeta{
		CacheKey:      channelAffinityCacheNamespace + ":claude cli trace:default:abc123",
		TTLSeconds:    3600,
		RuleName:      "claude cli trace",
		KeySourceType: "gjson",
		KeySourcePath: "metadata.user_id",
		UsingGroup:    "default",
	})

	RecordChannelAffinityPoison(c, 54)

	result, applied := ApplyChannelAffinityPoisonRewrite(c, 54, nil)
	if !applied {
		t.Fatal("expected rewrite to be applied even with nil paramOverride")
	}

	ops, ok := result["operations"].([]interface{})
	if !ok || len(ops) != 1 {
		t.Fatalf("expected 1 operation, got %v", result["operations"])
	}
}

func TestApplyPoisonRewrite_NoPoisonNoChange(t *testing.T) {
	resetPoisonCache()

	c, _ := newTestContext(`{"metadata":{"user_id":"clean_user"}}`)
	_, _ = common.GetRequestBody(c)

	setAffinityMeta(c, channelAffinityMeta{
		CacheKey:      channelAffinityCacheNamespace + ":claude cli trace:default:clean_user",
		TTLSeconds:    3600,
		RuleName:      "claude cli trace",
		KeySourceType: "gjson",
		KeySourcePath: "metadata.user_id",
		UsingGroup:    "default",
	})

	original := map[string]interface{}{"foo": "bar"}
	result, applied := ApplyChannelAffinityPoisonRewrite(c, 54, original)
	if applied {
		t.Error("expected no rewrite for non-poisoned request")
	}
	if result["foo"] != "bar" {
		t.Error("expected original paramOverride to be returned unchanged")
	}
}

// --- Tests for buildPoisonCacheKey ---

func TestBuildPoisonCacheKey(t *testing.T) {
	key := buildPoisonCacheKey(54, "abc123")
	if key != "54:abc123" {
		t.Errorf("expected 54:abc123, got %s", key)
	}
}

// --- Integration: full flow test ---

func TestFullFlow_AffinityFailure_InvalidateAndPoison(t *testing.T) {
	resetAffinityCache()
	resetPoisonCache()

	affinityCache := getChannelAffinityCache()
	cacheKeySuffix := "claude cli trace:default:user_xyz"
	_ = affinityCache.SetWithTTL(cacheKeySuffix, 54, 1*time.Hour)

	body := `{"metadata":{"user_id":"user_xyz"},"model":"claude-3-sonnet"}`
	c, _ := newTestContext(body)
	_, _ = common.GetRequestBody(c)

	cacheKeyFull := channelAffinityCacheNamespace + ":" + cacheKeySuffix
	setAffinityMeta(c, channelAffinityMeta{
		CacheKey:      cacheKeyFull,
		TTLSeconds:    3600,
		RuleName:      "claude cli trace",
		KeySourceType: "gjson",
		KeySourcePath: "metadata.user_id",
		UsingGroup:    "default",
	})

	// Simulate: affinity selected ch54, request returned 429
	// Step 1: Invalidate affinity cache
	InvalidateChannelAffinityOnFailure(c)
	_, found, _ := affinityCache.Get(cacheKeySuffix)
	if found {
		t.Error("affinity cache should be cleared after invalidation")
	}

	// Step 2: Record poison
	RecordChannelAffinityPoison(c, 54)

	// Step 3: Next request arrives, gets routed to ch54 again (random)
	// SetupContextForSelectedChannel would call ApplyChannelAffinityPoisonRewrite
	paramOverride := map[string]interface{}{}
	result, applied := ApplyChannelAffinityPoisonRewrite(c, 54, paramOverride)
	if !applied {
		t.Fatal("expected poison rewrite to be applied")
	}

	ops := result["operations"].([]interface{})
	appendOp := ops[0].(map[string]interface{})
	if appendOp["path"] != "metadata.user_id" {
		t.Errorf("wrong path: %v", appendOp["path"])
	}
	if appendOp["mode"] != "append" {
		t.Errorf("wrong mode: %v", appendOp["mode"])
	}

	// Step 4: Same request to ch65 should NOT be rewritten
	_, applied2 := ApplyChannelAffinityPoisonRewrite(c, 65, paramOverride)
	if applied2 {
		t.Error("ch65 should not be poisoned")
	}
}

func TestFullFlow_NonRetryableError_NoInvalidation(t *testing.T) {
	resetAffinityCache()

	affinityCache := getChannelAffinityCache()
	cacheKeySuffix := "claude cli trace:default:user_400"
	_ = affinityCache.SetWithTTL(cacheKeySuffix, 54, 1*time.Hour)

	c, _ := newTestContext(`{}`)
	// No affinity meta set (simulates non-affinity request)

	// Calling invalidate without affinity context should be a no-op
	InvalidateChannelAffinityOnFailure(c)

	val, found, _ := affinityCache.Get(cacheKeySuffix)
	if !found || val != 54 {
		t.Error("affinity cache should NOT be cleared for non-affinity requests")
	}
}

// --- Test extractAffinityValueFromContext ---

func TestExtractAffinityValueFromContext_Gjson(t *testing.T) {
	body := `{"metadata":{"user_id":"test_user"}}`
	c, _ := newTestContext(body)
	// Must read body into context first
	_, _ = io.ReadAll(c.Request.Body)
	c.Request.Body = io.NopCloser(bytes.NewBufferString(body))
	c.Set(common.KeyRequestBody, []byte(body))

	meta := channelAffinityMeta{
		KeySourceType: "gjson",
		KeySourcePath: "metadata.user_id",
	}
	val := extractAffinityValueFromContext(c, meta)
	if val != "test_user" {
		t.Errorf("expected test_user, got %s", val)
	}
}

func TestExtractAffinityValueFromContext_ContextInt(t *testing.T) {
	c, _ := newTestContext(`{}`)
	c.Set("id", 42)

	meta := channelAffinityMeta{
		KeySourceType: "context_int",
		KeySourceKey:  "id",
	}
	val := extractAffinityValueFromContext(c, meta)
	if val != "42" {
		t.Errorf("expected 42, got %s", val)
	}
}

func TestExtractAffinityValueFromContext_ContextString(t *testing.T) {
	c, _ := newTestContext(`{}`)
	c.Set("token", "my-token")

	meta := channelAffinityMeta{
		KeySourceType: "context_string",
		KeySourceKey:  "token",
	}
	val := extractAffinityValueFromContext(c, meta)
	if val != "my-token" {
		t.Errorf("expected my-token, got %s", val)
	}
}

func TestExtractAffinityValueFromContext_EmptyType(t *testing.T) {
	c, _ := newTestContext(`{}`)
	meta := channelAffinityMeta{KeySourceType: ""}
	val := extractAffinityValueFromContext(c, meta)
	if val != "" {
		t.Errorf("expected empty, got %s", val)
	}
}

// --- Test codex prompt_cache_key scenario ---

func TestPoisonCache_CodexPromptCacheKey(t *testing.T) {
	resetPoisonCache()

	body := `{"prompt_cache_key":"session-abc-123","model":"gpt-4o"}`
	c, _ := newTestContext(body)
	_, _ = common.GetRequestBody(c)

	setAffinityMeta(c, channelAffinityMeta{
		CacheKey:      channelAffinityCacheNamespace + ":codex cli trace:default:session-abc-123",
		TTLSeconds:    3600,
		RuleName:      "codex cli trace",
		KeySourceType: "gjson",
		KeySourcePath: "prompt_cache_key",
		UsingGroup:    "default",
	})

	RecordChannelAffinityPoison(c, 58)

	gjsonPath, suffix, found := GetChannelAffinityPoisonRewrite(c, 58)
	if !found {
		t.Fatal("expected poison hit for codex prompt_cache_key")
	}
	if gjsonPath != "prompt_cache_key" {
		t.Errorf("expected path=prompt_cache_key, got %s", gjsonPath)
	}
	if len(suffix) < 3 {
		t.Errorf("suffix too short: %s", suffix)
	}
}

// --- Tests for ShouldRecordAffinityPoison ---

func TestShouldRecordAffinityPoison(t *testing.T) {
	tests := []struct {
		code   int
		expect bool
	}{
		{429, true},
		{401, true},
		{403, true},
		{400, false},
		{404, false},
		{500, false},
		{503, false},
		{200, false},
	}
	for _, tt := range tests {
		got := ShouldRecordAffinityPoison(tt.code)
		if got != tt.expect {
			t.Errorf("ShouldRecordAffinityPoison(%d) = %v, want %v", tt.code, got, tt.expect)
		}
	}
}

// --- Integration: 401/403 also trigger poison ---

func TestFullFlow_401_403_TriggerPoison(t *testing.T) {
	for _, statusCode := range []int{401, 403} {
		t.Run(http.StatusText(statusCode), func(t *testing.T) {
			resetAffinityCache()
			resetPoisonCache()

			affinityCache := getChannelAffinityCache()
			cacheKeySuffix := "claude cli trace:default:user_auth"
			_ = affinityCache.SetWithTTL(cacheKeySuffix, 54, 1*time.Hour)

			body := `{"metadata":{"user_id":"user_auth"},"model":"claude-3-sonnet"}`
			c, _ := newTestContext(body)
			_, _ = common.GetRequestBody(c)

			cacheKeyFull := channelAffinityCacheNamespace + ":" + cacheKeySuffix
			setAffinityMeta(c, channelAffinityMeta{
				CacheKey:      cacheKeyFull,
				TTLSeconds:    3600,
				RuleName:      "claude cli trace",
				KeySourceType: "gjson",
				KeySourcePath: "metadata.user_id",
				UsingGroup:    "default",
			})

			InvalidateChannelAffinityOnFailure(c)
			_, found, _ := affinityCache.Get(cacheKeySuffix)
			if found {
				t.Error("affinity cache should be cleared after invalidation")
			}

			if !ShouldRecordAffinityPoison(statusCode) {
				t.Fatalf("ShouldRecordAffinityPoison(%d) should return true", statusCode)
			}
			RecordChannelAffinityPoison(c, 54)

			_, _, poisonFound := GetChannelAffinityPoisonRewrite(c, 54)
			if !poisonFound {
				t.Errorf("expected poison cache hit for status %d", statusCode)
			}

			result, applied := ApplyChannelAffinityPoisonRewrite(c, 54, map[string]interface{}{})
			if !applied {
				t.Fatalf("expected poison rewrite to be applied for status %d", statusCode)
			}
			ops := result["operations"].([]interface{})
			appendOp := ops[0].(map[string]interface{})
			if appendOp["mode"] != "append" {
				t.Errorf("expected mode=append, got %v", appendOp["mode"])
			}
		})
	}
}

// --- Test that setting is respected ---

func TestPoisonCache_DefaultTTLFromSetting(t *testing.T) {
	resetPoisonCache()

	body := `{"metadata":{"user_id":"ttl_test"}}`
	c, _ := newTestContext(body)
	_, _ = common.GetRequestBody(c)

	// TTLSeconds = 0 should fall back to setting default
	setAffinityMeta(c, channelAffinityMeta{
		CacheKey:      channelAffinityCacheNamespace + ":test:default:ttl_test",
		TTLSeconds:    0,
		RuleName:      "test",
		KeySourceType: "gjson",
		KeySourcePath: "metadata.user_id",
		UsingGroup:    "default",
	})

	setting := operation_setting.GetChannelAffinitySetting()
	originalTTL := setting.DefaultTTLSeconds
	defer func() { setting.DefaultTTLSeconds = originalTTL }()

	// Even with TTL=0 in meta, it should use the global default
	RecordChannelAffinityPoison(c, 54)

	_, _, found := GetChannelAffinityPoisonRewrite(c, 54)
	if !found {
		t.Error("expected poison to be recorded even with TTL=0 in meta")
	}
}
