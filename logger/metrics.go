package logger

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"
)

var (
	metricsEnabled   bool
	metricsNamespace string
	metricsInitOnce  sync.Once
)

func InitMetrics() {
	metricsInitOnce.Do(func() {
		metricsEnabled = strings.EqualFold(os.Getenv("CLOUDWATCH_METRICS_ENABLED"), "true")
		metricsNamespace = os.Getenv("CLOUDWATCH_METRICS_NAMESPACE")
		if metricsNamespace == "" {
			metricsNamespace = "EZModel/API"
		}
		if metricsEnabled && cloudWatchSink == nil {
			fmt.Fprintln(os.Stderr, "CLOUDWATCH_METRICS_ENABLED=true but CloudWatch Logs sink is not initialized; metrics will be dropped")
			metricsEnabled = false
		}
	})
}

func MetricsEnabled() bool {
	return metricsEnabled
}

type MetricUnit string

const (
	UnitCount        MetricUnit = "Count"
	UnitMilliseconds MetricUnit = "Milliseconds"
	UnitSeconds      MetricUnit = "Seconds"
	UnitBytes        MetricUnit = "Bytes"
	UnitMegabytes    MetricUnit = "Megabytes"
	UnitPercent      MetricUnit = "Percent"
	UnitNone         MetricUnit = "None"
)

type MetricDef struct {
	Name string     `json:"Name"`
	Unit MetricUnit `json:"Unit"`
}

type cwMetricDirective struct {
	Namespace  string     `json:"Namespace"`
	Dimensions [][]string `json:"Dimensions"`
	Metrics    []MetricDef `json:"Metrics"`
}

type EMFBuilder struct {
	directives []cwMetricDirective
	fields     map[string]interface{}
}

func NewEMF() *EMFBuilder {
	if !metricsEnabled {
		return nil
	}
	return &EMFBuilder{
		fields: make(map[string]interface{}),
	}
}

func (b *EMFBuilder) AddMetricSet(dimensions [][]string, metrics []MetricDef) *EMFBuilder {
	if b == nil {
		return nil
	}
	b.directives = append(b.directives, cwMetricDirective{
		Namespace:  metricsNamespace,
		Dimensions: dimensions,
		Metrics:    metrics,
	})
	return b
}

func (b *EMFBuilder) Dim(key, value string) *EMFBuilder {
	if b == nil {
		return nil
	}
	if value == "" {
		value = "unknown"
	}
	b.fields[key] = value
	return b
}

func (b *EMFBuilder) Metric(key string, value interface{}) *EMFBuilder {
	if b == nil {
		return nil
	}
	b.fields[key] = value
	return b
}

func (b *EMFBuilder) Prop(key string, value interface{}) *EMFBuilder {
	if b == nil {
		return nil
	}
	b.fields[key] = value
	return b
}

func (b *EMFBuilder) Emit() {
	if b == nil || len(b.directives) == 0 {
		return
	}
	b.fields["_aws"] = map[string]interface{}{
		"Timestamp":         time.Now().UnixMilli(),
		"CloudWatchMetrics": b.directives,
	}
	data, err := json.Marshal(b.fields)
	if err != nil {
		fmt.Fprintf(os.Stderr, "EMF marshal error: %v\n", err)
		return
	}
	data = append(data, '\n')
	if cloudWatchSink != nil {
		cloudWatchSink.Write(data)
	}
}

// EmitPipelineMetrics reports log pipeline health metrics.
// Placed in logger package to avoid circular imports (service -> middleware).
func EmitPipelineMetrics(pipeline string, queueDepth int, uploadFailures int64, drops int64) {
	if !metricsEnabled {
		return
	}
	emf := NewEMF()
	if emf == nil {
		return
	}
	emf.AddMetricSet(PipelineDims, PipelineMetrics).
		Dim("Pipeline", pipeline).
		Metric("LogQueueDepth", queueDepth).
		Metric("LogUploadFailureCount", uploadFailures).
		Metric("LogDropCount", drops).
		Emit()

	pipelineGlobalMu.Lock()
	pipelineGlobalQueueDepth += queueDepth
	pipelineGlobalUploadFail += uploadFailures
	pipelineGlobalDrops += drops
	pipelineGlobalMu.Unlock()
}

// FlushPipelineGlobalMetrics emits dimensionless pipeline totals for alarms.
func FlushPipelineGlobalMetrics() {
	if !metricsEnabled {
		return
	}
	pipelineGlobalMu.Lock()
	qd := pipelineGlobalQueueDepth
	uf := pipelineGlobalUploadFail
	dr := pipelineGlobalDrops
	pipelineGlobalQueueDepth = 0
	pipelineGlobalUploadFail = 0
	pipelineGlobalDrops = 0
	pipelineGlobalMu.Unlock()

	emf := NewEMF()
	if emf == nil {
		return
	}
	globalPipelineDefs := []MetricDef{
		{Name: "TotalLogQueueDepth", Unit: UnitCount},
		{Name: "TotalLogUploadFailureCount", Unit: UnitCount},
		{Name: "TotalLogDropCount", Unit: UnitCount},
	}
	emf.AddMetricSet([][]string{{}}, globalPipelineDefs).
		Metric("TotalLogQueueDepth", qd).
		Metric("TotalLogUploadFailureCount", uf).
		Metric("TotalLogDropCount", dr).
		Emit()
}

var (
	pipelineGlobalQueueDepth int
	pipelineGlobalUploadFail int64
	pipelineGlobalDrops      int64
	pipelineGlobalMu         sync.Mutex
)

// Pre-defined metric sets to avoid repeated allocation.

var (
	RequestMetrics = []MetricDef{
		{Name: "RequestCount", Unit: UnitCount},
		{Name: "RequestLatencyMs", Unit: UnitMilliseconds},
		{Name: "ErrorCount", Unit: UnitCount},
		{Name: "InputTokens", Unit: UnitCount},
		{Name: "OutputTokens", Unit: UnitCount},
		{Name: "CachedTokens", Unit: UnitCount},
		{Name: "CacheHitCount", Unit: UnitCount},
		{Name: "CacheCreationTokens", Unit: UnitCount},
		{Name: "CacheCreationCount", Unit: UnitCount},
		{Name: "CacheCreation5mTokens", Unit: UnitCount},
		{Name: "CacheCreation1hTokens", Unit: UnitCount},
		{Name: "ReasoningTokens", Unit: UnitCount},
		{Name: "OutputTokensPerSec", Unit: UnitNone},
		{Name: "TTFTMs", Unit: UnitMilliseconds},
	}
	RequestDims = [][]string{{"Channel"}, {"Model"}, {"IsStream"}}

	UpstreamMetrics = []MetricDef{
		{Name: "UpstreamLatencyMs", Unit: UnitMilliseconds},
		{Name: "UpstreamErrorCount", Unit: UnitCount},
		{Name: "UpstreamTimeoutCount", Unit: UnitCount},
		{Name: "ChannelFallbackCount", Unit: UnitCount},
	}
	UpstreamDims = [][]string{{"Channel"}}

	UpstreamStatusMetrics = []MetricDef{
		{Name: "UpstreamStatusCount", Unit: UnitCount},
	}
	UpstreamStatusDims = [][]string{{"Channel", "StatusGroup"}}

	BillingMetrics = []MetricDef{
		{Name: "CostUSD", Unit: UnitNone},
		{Name: "BillingFailureCount", Unit: UnitCount},
		{Name: "QuotaDeltaAbs", Unit: UnitNone},
		{Name: "QuotaOverchargeCount", Unit: UnitCount},
		{Name: "QuotaUnderchargeCount", Unit: UnitCount},
	}
	BillingDims = [][]string{{"Channel"}}

	PipelineMetrics = []MetricDef{
		{Name: "LogQueueDepth", Unit: UnitCount},
		{Name: "LogUploadFailureCount", Unit: UnitCount},
		{Name: "LogDropCount", Unit: UnitCount},
	}
	PipelineDims = [][]string{{"Pipeline"}}

	RuntimeMetrics = []MetricDef{
		{Name: "ActiveConnections", Unit: UnitCount},
		{Name: "GoroutineCount", Unit: UnitCount},
		{Name: "HeapAllocMB", Unit: UnitMegabytes},
		{Name: "GCPauseMs", Unit: UnitMilliseconds},
	}
	RuntimeDims = [][]string{{}}

	DBMetrics = []MetricDef{
		{Name: "DBQueryLatencyMs", Unit: UnitMilliseconds},
		{Name: "DBSlowQueryCount", Unit: UnitCount},
	}
	DBDims = [][]string{{"Operation"}}

	RedisMetrics = []MetricDef{
		{Name: "RedisLatencyMs", Unit: UnitMilliseconds},
		{Name: "RedisErrorCount", Unit: UnitCount},
	}
	RedisDims = [][]string{{"Command"}}

	StreamFinishMetrics = []MetricDef{
		{Name: "StreamFinishCount", Unit: UnitCount},
		{Name: "StreamTimeoutCount", Unit: UnitCount},
		{Name: "StreamClientDisconnectCount", Unit: UnitCount},
		{Name: "StreamDurationMs", Unit: UnitMilliseconds},
	}
	StreamFinishDims = [][]string{{"Channel"}, {"Reason"}}

	StreamInterruptBillingMetrics = []MetricDef{
		{Name: "StreamInterruptCount", Unit: UnitCount},
		{Name: "StreamInterruptPartialTokens", Unit: UnitCount},
	}
	StreamInterruptBillingDims = [][]string{{"Channel"}, {"Reason"}}

	RateLimitMetrics = []MetricDef{
		{Name: "RateLimitRejectCount", Unit: UnitCount},
	}
	RateLimitDims = [][]string{{"LimitType"}}

	ChannelHealthMetrics = []MetricDef{
		{Name: "ChannelHealthEventCount", Unit: UnitCount},
	}
	ChannelHealthDims = [][]string{{"Channel", "Event"}}

	RetryMetrics = []MetricDef{
		{Name: "RetryAttempts", Unit: UnitCount},
		{Name: "RetryExhaustedCount", Unit: UnitCount},
	}
	RetryDims = [][]string{{"Model", "Result"}}

	QuotaRejectMetrics = []MetricDef{
		{Name: "QuotaRejectCount", Unit: UnitCount},
	}
	QuotaRejectDims = [][]string{{}}

	AffinityMetrics = []MetricDef{
		{Name: "AffinityHitCount", Unit: UnitCount},
		{Name: "AffinityMissCount", Unit: UnitCount},
	}
	AffinityDims = [][]string{{"Model"}}

	FinishReasonMetrics = []MetricDef{
		{Name: "FinishReasonCount", Unit: UnitCount},
	}
	FinishReasonDims = [][]string{{"Model", "FinishReason"}}
)
