package common

import (
	"context"
	"strings"
	"time"

	"github.com/go-redis/redis/v8"
)

type redisMetricsHookKeyType struct{}

var redisMetricsStartKey = redisMetricsHookKeyType{}

// RedisMetricsEmitter is set by the middleware package to avoid import cycles.
var RedisMetricsEmitter func(command string, latencyMs float64, hasError bool)

type redisMetricsHook struct{}

func NewRedisMetricsHook() redis.Hook {
	return &redisMetricsHook{}
}

func (h *redisMetricsHook) BeforeProcess(ctx context.Context, cmd redis.Cmder) (context.Context, error) {
	return context.WithValue(ctx, redisMetricsStartKey, time.Now()), nil
}

func (h *redisMetricsHook) AfterProcess(ctx context.Context, cmd redis.Cmder) error {
	if RedisMetricsEmitter == nil {
		return nil
	}
	start, ok := ctx.Value(redisMetricsStartKey).(time.Time)
	if !ok {
		return nil
	}
	latencyMs := float64(time.Since(start).Microseconds()) / 1000.0
	hasError := cmd.Err() != nil && cmd.Err() != redis.Nil
	command := strings.ToUpper(cmd.Name())
	RedisMetricsEmitter(command, latencyMs, hasError)
	return nil
}

func (h *redisMetricsHook) BeforeProcessPipeline(ctx context.Context, cmds []redis.Cmder) (context.Context, error) {
	return context.WithValue(ctx, redisMetricsStartKey, time.Now()), nil
}

func (h *redisMetricsHook) AfterProcessPipeline(ctx context.Context, cmds []redis.Cmder) error {
	if RedisMetricsEmitter == nil {
		return nil
	}
	start, ok := ctx.Value(redisMetricsStartKey).(time.Time)
	if !ok {
		return nil
	}
	latencyMs := float64(time.Since(start).Microseconds()) / 1000.0
	var hasError bool
	for _, cmd := range cmds {
		if cmd.Err() != nil && cmd.Err() != redis.Nil {
			hasError = true
			break
		}
	}
	RedisMetricsEmitter("PIPELINE", latencyMs, hasError)
	return nil
}
