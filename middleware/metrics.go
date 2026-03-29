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

		var errCount int
		if statusCode >= 400 {
			errCount = 1
		}

		logger.RecordRequest(channel, model, latencyMs, errCount, inputTokens, outputTokens)
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
