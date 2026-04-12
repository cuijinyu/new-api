package middleware

import (
	"fmt"
	"sync/atomic"
	"time"

	"github.com/QuantumNous/new-api/logger"

	"github.com/gin-gonic/gin"
)

func MetricsMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		if !logger.MetricsEnabled() {
			c.Next()
			return
		}

		start := time.Now()
		c.Next()
		latencyMs := time.Since(start).Milliseconds()

		channelId := c.GetInt("channel_id")
		channel := fmt.Sprintf("ch%d", channelId)
		model := c.GetString("original_model")
		statusCode := c.Writer.Status()

		inputTokens := c.GetInt("metric_input_tokens")
		outputTokens := c.GetInt("metric_output_tokens")
		cachedTokens := c.GetInt("metric_cached_tokens")
		cacheCreationTokens := c.GetInt("metric_cache_creation_tokens")
		cacheCreation5mTokens := c.GetInt("metric_cache_creation_5m_tokens")
		cacheCreation1hTokens := c.GetInt("metric_cache_creation_1h_tokens")
		reasoningTokens := c.GetInt("metric_reasoning_tokens")
		isStream, _ := c.Get("metric_is_stream")
		isStreamBool, _ := isStream.(bool)

		outputTPS := -1.0
		if tps, exists := c.Get("metric_output_tps"); exists {
			if v, ok := tps.(float64); ok {
				outputTPS = v
			}
		}

		var ttftMs int64
		if v, exists := c.Get("metric_ttft_ms"); exists {
			if ms, ok := v.(int64); ok {
				ttftMs = ms
			}
		}

		var errCount int
		if statusCode >= 400 {
			errCount = 1
		}

		logger.RecordRequest(channel, model, isStreamBool, latencyMs, errCount, inputTokens, outputTokens, cachedTokens, cacheCreationTokens, cacheCreation5mTokens, cacheCreation1hTokens, reasoningTokens, outputTPS, ttftMs)

		if finishReason, exists := c.Get("metric_finish_reason"); exists {
			if reason, ok := finishReason.(string); ok && reason != "" {
				logger.RecordFinishReason(model, reason)
			}
		}
	}
}

// EmitDBMetrics reports database query metrics via the aggregator.
func EmitDBMetrics(operation string, latencyMs float64, isSlow bool) {
	var slowCount int
	if isSlow {
		slowCount = 1
	}
	logger.RecordDB(operation, latencyMs, slowCount)
}

// EmitRedisMetrics reports Redis operation metrics via the aggregator.
func EmitRedisMetrics(command string, latencyMs float64, hasError bool) {
	var errCount int
	if hasError {
		errCount = 1
	}
	logger.RecordRedis(command, latencyMs, errCount)
}

// GetActiveConnections exposes the atomic counter for the runtime collector.
func GetActiveConnections() int64 {
	return atomic.LoadInt64(&globalStats.activeConnections)
}
