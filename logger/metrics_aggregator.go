package logger

import (
	"math"
	"strings"
	"sync"
	"time"
)

// quotaPerUnitUSD mirrors common.QuotaPerUnit (500_000 quota = $1 USD).
// Duplicated here to avoid importing common and creating a circular dependency.
const quotaPerUnitUSD = 500_000.0

// metricValue tracks aggregated statistics for a single metric within a dimension bucket.
type metricValue struct {
	Sum   float64
	Count int64
	Min   float64
	Max   float64
}

func newMetricValue(v float64) metricValue {
	return metricValue{Sum: v, Count: 1, Min: v, Max: v}
}

func (m *metricValue) add(v float64) {
	m.Sum += v
	m.Count++
	if v < m.Min {
		m.Min = v
	}
	if v > m.Max {
		m.Max = v
	}
}

// dimBucket holds all metric values for one unique dimension combination.
type dimBucket struct {
	dims    map[string]string
	metrics map[string]*metricValue
}

// metricSetAggregator aggregates metrics for one metric set (e.g. Request, Upstream, Billing).
type metricSetAggregator struct {
	mu         sync.Mutex
	buckets    map[string]*dimBucket // key = sorted dim values
	dimKeys    [][]string
	metricDefs []MetricDef
}

func newMetricSetAggregator(dimKeys [][]string, metricDefs []MetricDef) *metricSetAggregator {
	return &metricSetAggregator{
		buckets:    make(map[string]*dimBucket),
		dimKeys:    dimKeys,
		metricDefs: metricDefs,
	}
}

func dimKeyString(dims map[string]string) string {
	if len(dims) == 0 {
		return "_global_"
	}
	var b strings.Builder
	first := true
	for k, v := range dims {
		if !first {
			b.WriteByte('|')
		}
		b.WriteString(k)
		b.WriteByte('=')
		b.WriteString(v)
		first = false
	}
	return b.String()
}

func (a *metricSetAggregator) record(dims map[string]string, metrics map[string]float64) {
	key := dimKeyString(dims)
	a.mu.Lock()
	bucket, ok := a.buckets[key]
	if !ok {
		bucket = &dimBucket{
			dims:    dims,
			metrics: make(map[string]*metricValue),
		}
		a.buckets[key] = bucket
	}
	for name, val := range metrics {
		if mv, exists := bucket.metrics[name]; exists {
			mv.add(val)
		} else {
			v := newMetricValue(val)
			bucket.metrics[name] = &v
		}
	}
	a.mu.Unlock()
}

// flush drains all buckets and emits EMF logs. Returns the number of EMF lines emitted.
func (a *metricSetAggregator) flush() int {
	a.mu.Lock()
	old := a.buckets
	a.buckets = make(map[string]*dimBucket, len(old))
	a.mu.Unlock()

	count := 0
	for _, bucket := range old {
		emf := NewEMF()
		if emf == nil {
			return count
		}
		emf.AddMetricSet(a.dimKeys, a.metricDefs)
		for k, v := range bucket.dims {
			emf.Dim(k, v)
		}
		for _, def := range a.metricDefs {
			mv, ok := bucket.metrics[def.Name]
			if !ok {
				emf.Metric(def.Name, 0)
				continue
			}
			if def.Unit == UnitMilliseconds || def.Unit == UnitSeconds || def.Unit == UnitMegabytes {
				// For latency/gauge metrics, emit as a CloudWatch Metric Datum array [min, max, values...]
				// to preserve statistical distribution info.
				// EMF supports "Values" + "Counts" format for richer statistics.
				emf.Metric(def.Name, buildStatisticSet(mv))
			} else {
				// For counters, emit the sum directly.
				emf.Metric(def.Name, mv.Sum)
			}
		}
		emf.Prop("_agg_samples", totalSamples(bucket.metrics))
		emf.Emit()
		count++
	}
	return count
}

func totalSamples(metrics map[string]*metricValue) int64 {
	var maxCount int64
	for _, mv := range metrics {
		if mv.Count > maxCount {
			maxCount = mv.Count
		}
	}
	return maxCount
}

// buildStatisticSet returns a CloudWatch EMF statistic set for richer aggregation.
// Format: {"Min": x, "Max": x, "Sum": x, "Count": n}
func buildStatisticSet(mv *metricValue) map[string]interface{} {
	return map[string]interface{}{
		"Min":   roundTo(mv.Min, 3),
		"Max":   roundTo(mv.Max, 3),
		"Sum":   roundTo(mv.Sum, 3),
		"Count": mv.Count,
	}
}

func roundTo(v float64, decimals int) float64 {
	pow := math.Pow(10, float64(decimals))
	return math.Round(v*pow) / pow
}

// --- Global aggregator registry ---

var (
	aggRequest             *metricSetAggregator
	aggUpstream            *metricSetAggregator
	aggUpstreamStatus      *metricSetAggregator
	aggBilling             *metricSetAggregator
	aggDB                  *metricSetAggregator
	aggRedis               *metricSetAggregator
	aggStreamFinish        *metricSetAggregator
	aggStreamInterruptBill *metricSetAggregator
	aggRateLimit           *metricSetAggregator
	aggChannelHealth       *metricSetAggregator
	aggRetry               *metricSetAggregator
	aggQuotaReject         *metricSetAggregator
	aggAffinity            *metricSetAggregator
	aggFinishReason        *metricSetAggregator

	aggStopCh chan struct{}
	aggWg     sync.WaitGroup
	aggOnce   sync.Once
)

func initAggregators() {
	aggRequest = newMetricSetAggregator(RequestDims, RequestMetrics)
	aggUpstream = newMetricSetAggregator(UpstreamDims, UpstreamMetrics)
	aggUpstreamStatus = newMetricSetAggregator(UpstreamStatusDims, UpstreamStatusMetrics)
	aggBilling = newMetricSetAggregator(BillingDims, BillingMetrics)
	aggDB = newMetricSetAggregator(DBDims, DBMetrics)
	aggRedis = newMetricSetAggregator(RedisDims, RedisMetrics)
	aggStreamFinish = newMetricSetAggregator(StreamFinishDims, StreamFinishMetrics)
	aggStreamInterruptBill = newMetricSetAggregator(StreamInterruptBillingDims, StreamInterruptBillingMetrics)
	aggRateLimit = newMetricSetAggregator(RateLimitDims, RateLimitMetrics)
	aggChannelHealth = newMetricSetAggregator(ChannelHealthDims, ChannelHealthMetrics)
	aggRetry = newMetricSetAggregator(RetryDims, RetryMetrics)
	aggQuotaReject = newMetricSetAggregator(QuotaRejectDims, QuotaRejectMetrics)
	aggAffinity = newMetricSetAggregator(AffinityDims, AffinityMetrics)
	aggFinishReason = newMetricSetAggregator(FinishReasonDims, FinishReasonMetrics)
}

// StartAggregator starts the background flush loop. Call after InitMetrics.
func StartAggregator() {
	if !metricsEnabled {
		return
	}
	aggOnce.Do(func() {
		initAggregators()
		aggStopCh = make(chan struct{})
		aggWg.Add(1)
		go runAggregatorLoop()
	})
}

// StopAggregator flushes remaining data and stops the background loop.
func StopAggregator() {
	if aggStopCh == nil {
		return
	}
	select {
	case <-aggStopCh:
	default:
		close(aggStopCh)
	}
	aggWg.Wait()
}

func runAggregatorLoop() {
	defer aggWg.Done()
	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			flushAll()
		case <-aggStopCh:
			flushAll()
			return
		}
	}
}

func flushAll() {
	for _, agg := range []*metricSetAggregator{
		aggRequest, aggUpstream, aggUpstreamStatus, aggBilling,
		aggDB, aggRedis, aggStreamFinish, aggStreamInterruptBill,
		aggRateLimit, aggChannelHealth, aggRetry, aggQuotaReject,
		aggAffinity, aggFinishReason,
	} {
		if agg != nil {
			agg.flush()
		}
	}
}

// --- Public recording functions (called from hot paths) ---

// RecordRequest records API request metrics into the aggregator.
func RecordRequest(channel, model string, isStream bool, latencyMs int64, errCount, inputTokens, outputTokens, cachedTokens, cacheCreationTokens, cacheCreation5mTokens, cacheCreation1hTokens, reasoningTokens int, outputTokensPerSec float64, ttftMs int64) {
	if aggRequest == nil {
		return
	}
	var cacheHitCount float64
	if cachedTokens > 0 {
		cacheHitCount = 1
	}
	var cacheCreationCount float64
	if cacheCreationTokens > 0 {
		cacheCreationCount = 1
	}
	streamDim := "false"
	if isStream {
		streamDim = "true"
	}
	// Negative outputTokensPerSec means not applicable; skip it.
	tps := outputTokensPerSec
	if tps < 0 {
		tps = 0
	}
	// ttftMs <= 0 means not applicable (non-stream or not recorded).
	ttft := float64(ttftMs)
	if ttft <= 0 {
		ttft = 0
	}
	dims := map[string]string{"Channel": normDim(channel), "Model": normDim(model), "IsStream": streamDim}
	aggRequest.record(dims, map[string]float64{
		"RequestCount":          1,
		"RequestLatencyMs":      float64(latencyMs),
		"ErrorCount":            float64(errCount),
		"InputTokens":           float64(inputTokens),
		"OutputTokens":          float64(outputTokens),
		"CachedTokens":          float64(cachedTokens),
		"CacheHitCount":         cacheHitCount,
		"CacheCreationTokens":   float64(cacheCreationTokens),
		"CacheCreationCount":    cacheCreationCount,
		"CacheCreation5mTokens": float64(cacheCreation5mTokens),
		"CacheCreation1hTokens": float64(cacheCreation1hTokens),
		"ReasoningTokens":       float64(reasoningTokens),
		"OutputTokensPerSec":    tps,
		"TTFTMs":                ttft,
	})
}

// RecordUpstream records upstream channel health metrics.
func RecordUpstream(channel string, latencyMs int64, errCount, timeoutCount int) {
	if aggUpstream == nil {
		return
	}
	dims := map[string]string{"Channel": normDim(channel)}
	aggUpstream.record(dims, map[string]float64{
		"UpstreamLatencyMs":    float64(latencyMs),
		"UpstreamErrorCount":   float64(errCount),
		"UpstreamTimeoutCount": float64(timeoutCount),
		"ChannelFallbackCount": 0,
	})
}

// RecordChannelFallback records a channel fallback/retry event.
func RecordChannelFallback(channel string) {
	if aggUpstream == nil {
		return
	}
	dims := map[string]string{"Channel": normDim(channel)}
	aggUpstream.record(dims, map[string]float64{
		"UpstreamLatencyMs":    0,
		"UpstreamErrorCount":   0,
		"UpstreamTimeoutCount": 0,
		"ChannelFallbackCount": 1,
	})
}

// RecordBilling records billing/quota consumption metrics.
// quotaConsumed is in internal quota units; it is converted to USD for the metric.
// quotaDelta is the difference between actual and pre-consumed quota (positive = underestimate).
func RecordBilling(channel string, quotaConsumed int, failCount int, quotaDelta int) {
	if aggBilling == nil {
		return
	}
	var overcharge, undercharge float64
	if quotaDelta > 0 {
		undercharge = 1
	} else if quotaDelta < 0 {
		overcharge = 1
	}
	absD := float64(quotaDelta)
	if absD < 0 {
		absD = -absD
	}
	dims := map[string]string{"Channel": normDim(channel)}
	aggBilling.record(dims, map[string]float64{
		"CostUSD":                float64(quotaConsumed) / quotaPerUnitUSD,
		"BillingFailureCount":    float64(failCount),
		"QuotaDeltaAbs":          absD / quotaPerUnitUSD,
		"QuotaOverchargeCount":   overcharge,
		"QuotaUnderchargeCount":  undercharge,
	})
}

// RecordDB records database query metrics.
func RecordDB(operation string, latencyMs float64, slowCount int) {
	if aggDB == nil {
		return
	}
	dims := map[string]string{"Operation": operation}
	aggDB.record(dims, map[string]float64{
		"DBQueryLatencyMs": latencyMs,
		"DBSlowQueryCount": float64(slowCount),
	})
}

// RecordRedis records Redis operation metrics.
func RecordRedis(command string, latencyMs float64, errCount int) {
	if aggRedis == nil {
		return
	}
	dims := map[string]string{"Command": command}
	aggRedis.record(dims, map[string]float64{
		"RedisLatencyMs": latencyMs,
		"RedisErrorCount": float64(errCount),
	})
}

// RecordStreamFinish records how a streaming request ended.
// reason should be one of: "completed", "timeout", "client_disconnect".
func RecordStreamFinish(channel, reason string, durationMs int64) {
	if aggStreamFinish == nil {
		return
	}
	var timeoutCount, disconnectCount float64
	switch reason {
	case "timeout":
		timeoutCount = 1
	case "client_disconnect":
		disconnectCount = 1
	}
	dims := map[string]string{"Channel": normDim(channel), "Reason": normDim(reason)}
	aggStreamFinish.record(dims, map[string]float64{
		"StreamFinishCount":           1,
		"StreamTimeoutCount":          timeoutCount,
		"StreamClientDisconnectCount": disconnectCount,
		"StreamDurationMs":            float64(durationMs),
	})
}

// RecordStreamInterruptBilling records a billing event where streaming was interrupted
// (timeout or client disconnect), meaning the billed tokens may be less than what
// the upstream provider actually consumed.
func RecordStreamInterruptBilling(channel, reason string, partialCompletionTokens int) {
	if aggStreamInterruptBill == nil {
		return
	}
	dims := map[string]string{"Channel": normDim(channel), "Reason": normDim(reason)}
	aggStreamInterruptBill.record(dims, map[string]float64{
		"StreamInterruptCount":         1,
		"StreamInterruptPartialTokens": float64(partialCompletionTokens),
	})
}

// RecordUpstreamStatus records upstream HTTP status code distribution.
// statusGroup should be one of: "2xx", "4xx_429", "4xx_other", "5xx", "timeout", "conn_error".
func RecordUpstreamStatus(channel, statusGroup string) {
	if aggUpstreamStatus == nil {
		return
	}
	dims := map[string]string{"Channel": normDim(channel), "StatusGroup": normDim(statusGroup)}
	aggUpstreamStatus.record(dims, map[string]float64{
		"UpstreamStatusCount": 1,
	})
}

// RecordRateLimitReject records a rate-limit rejection event.
// limitType should be one of: "global_api", "global_web", "model_total", "model_success".
func RecordRateLimitReject(limitType string) {
	if aggRateLimit == nil {
		return
	}
	dims := map[string]string{"LimitType": normDim(limitType)}
	aggRateLimit.record(dims, map[string]float64{
		"RateLimitRejectCount": 1,
	})
}

// RecordChannelHealthEvent records a channel auto-disable or re-enable event.
func RecordChannelHealthEvent(channel, event string) {
	if aggChannelHealth == nil {
		return
	}
	dims := map[string]string{"Channel": normDim(channel), "Event": normDim(event)}
	aggChannelHealth.record(dims, map[string]float64{
		"ChannelHealthEventCount": 1,
	})
}

// RecordRetryResult records the outcome of a request retry loop.
func RecordRetryResult(model string, attempts int, success bool) {
	if aggRetry == nil {
		return
	}
	result := "success"
	var exhaustedCount float64
	if !success {
		result = "exhausted"
		exhaustedCount = 1
	}
	dims := map[string]string{"Model": normDim(model), "Result": result}
	aggRetry.record(dims, map[string]float64{
		"RetryAttempts":       float64(attempts),
		"RetryExhaustedCount": exhaustedCount,
	})
}

// RecordQuotaReject records a request rejection due to insufficient user quota.
func RecordQuotaReject() {
	if aggQuotaReject == nil {
		return
	}
	aggQuotaReject.record(map[string]string{}, map[string]float64{
		"QuotaRejectCount": 1,
	})
}

// RecordAffinityResult records whether channel affinity cache was hit or missed.
func RecordAffinityResult(model string, hit bool) {
	if aggAffinity == nil {
		return
	}
	var hitCount, missCount float64
	if hit {
		hitCount = 1
	} else {
		missCount = 1
	}
	dims := map[string]string{"Model": normDim(model)}
	aggAffinity.record(dims, map[string]float64{
		"AffinityHitCount":  hitCount,
		"AffinityMissCount": missCount,
	})
}

// RecordFinishReason records the model-level finish_reason for a completed request.
func RecordFinishReason(model, reason string) {
	if aggFinishReason == nil {
		return
	}
	dims := map[string]string{"Model": normDim(model), "FinishReason": normDim(reason)}
	aggFinishReason.record(dims, map[string]float64{
		"FinishReasonCount": 1,
	})
}

func normDim(v string) string {
	if v == "" {
		return "unknown"
	}
	return v
}
