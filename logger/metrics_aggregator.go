package logger

import (
	"math"
	"strings"
	"sync"
	"time"
)

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
	aggRequest  *metricSetAggregator
	aggUpstream *metricSetAggregator
	aggBilling  *metricSetAggregator
	aggDB       *metricSetAggregator
	aggRedis    *metricSetAggregator

	aggStopCh chan struct{}
	aggWg     sync.WaitGroup
	aggOnce   sync.Once
)

func initAggregators() {
	aggRequest = newMetricSetAggregator(RequestDims, RequestMetrics)
	aggUpstream = newMetricSetAggregator(UpstreamDims, UpstreamMetrics)
	aggBilling = newMetricSetAggregator(BillingDims, BillingMetrics)
	aggDB = newMetricSetAggregator(DBDims, DBMetrics)
	aggRedis = newMetricSetAggregator(RedisDims, RedisMetrics)
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
	if aggRequest != nil {
		aggRequest.flush()
	}
	if aggUpstream != nil {
		aggUpstream.flush()
	}
	if aggBilling != nil {
		aggBilling.flush()
	}
	if aggDB != nil {
		aggDB.flush()
	}
	if aggRedis != nil {
		aggRedis.flush()
	}
}

// --- Public recording functions (called from hot paths) ---

// RecordRequest records API request metrics into the aggregator.
func RecordRequest(channel, model string, latencyMs int64, errCount, inputTokens, outputTokens int) {
	if aggRequest == nil {
		return
	}
	dims := map[string]string{"Channel": normDim(channel), "Model": normDim(model)}
	aggRequest.record(dims, map[string]float64{
		"RequestCount":    1,
		"RequestLatencyMs": float64(latencyMs),
		"ErrorCount":      float64(errCount),
		"InputTokens":     float64(inputTokens),
		"OutputTokens":    float64(outputTokens),
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
func RecordBilling(channel string, quotaConsumed int, failCount int) {
	if aggBilling == nil {
		return
	}
	dims := map[string]string{"Channel": normDim(channel)}
	aggBilling.record(dims, map[string]float64{
		"QuotaConsumed":      float64(quotaConsumed),
		"BillingFailureCount": float64(failCount),
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

func normDim(v string) string {
	if v == "" {
		return "unknown"
	}
	return v
}
