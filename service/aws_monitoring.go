package service

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/xml"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/logger"
	"github.com/QuantumNous/new-api/model"

	"github.com/aws/aws-sdk-go-v2/aws"
	v4 "github.com/aws/aws-sdk-go-v2/aws/signer/v4"
)

const (
	defaultMonitoringHours = 24
	defaultChannelLimit    = 120
	maxChannelLimit        = 500
)

type AWSMonitoringRequest struct {
	Hours        int
	Period       int
	ChannelLimit int
}

type AWSMonitoringPoint struct {
	Time                int64   `json:"time"`
	Requests            float64 `json:"requests"`
	Errors              float64 `json:"errors"`
	Tokens              float64 `json:"tokens"`
	CachedTokens        float64 `json:"cached_tokens"`
	CacheCreationTokens float64 `json:"cache_creation_tokens"`
	ReasoningTokens     float64 `json:"reasoning_tokens"`
	ProviderTokens      float64 `json:"provider_tokens"`
	RPM                 float64 `json:"rpm"`
	TPM                 float64 `json:"tpm"`
	ProviderTPM         float64 `json:"provider_tpm"`
	SuccessRate         float64 `json:"success_rate"`
	LatencyMs           float64 `json:"latency_ms"`
	LatencyP99Ms        float64 `json:"latency_p99_ms"`
	UpstreamLatencyMs   float64 `json:"upstream_latency_ms"`
	UpstreamP99Ms       float64 `json:"upstream_p99_ms"`
	TTFTMs              float64 `json:"ttft_ms"`
	TTFTP99Ms           float64 `json:"ttft_p99_ms"`
}

type AWSMonitoringSummary struct {
	Requests            float64 `json:"requests"`
	Errors              float64 `json:"errors"`
	Tokens              float64 `json:"tokens"`
	CachedTokens        float64 `json:"cached_tokens"`
	CacheCreationTokens float64 `json:"cache_creation_tokens"`
	ReasoningTokens     float64 `json:"reasoning_tokens"`
	ProviderTokens      float64 `json:"provider_tokens"`
	SuccessRate         float64 `json:"success_rate"`
	AverageRPM          float64 `json:"avg_rpm"`
	PeakRPM             float64 `json:"peak_rpm"`
	AverageTPM          float64 `json:"avg_tpm"`
	PeakTPM             float64 `json:"peak_tpm"`
	AverageProviderTPM  float64 `json:"avg_provider_tpm"`
	PeakProviderTPM     float64 `json:"peak_provider_tpm"`
	AverageLatencyMs    float64 `json:"avg_latency_ms"`
	LatencyP99Ms        float64 `json:"latency_p99_ms"`
	AverageTTFTMs       float64 `json:"avg_ttft_ms"`
	TTFTP99Ms           float64 `json:"ttft_p99_ms"`
	UpstreamLatencyMs   float64 `json:"upstream_latency_ms"`
	UpstreamP99Ms       float64 `json:"upstream_p99_ms"`
}

type AWSMonitoringChannel struct {
	ID                  int                         `json:"id"`
	Name                string                      `json:"name"`
	Type                int                         `json:"type"`
	Status              int                         `json:"status"`
	StatusText          string                      `json:"status_text"`
	MonitorKey          string                      `json:"monitor_key"`
	Requests            float64                     `json:"requests"`
	Errors              float64                     `json:"errors"`
	Tokens              float64                     `json:"tokens"`
	CachedTokens        float64                     `json:"cached_tokens"`
	CacheCreationTokens float64                     `json:"cache_creation_tokens"`
	ReasoningTokens     float64                     `json:"reasoning_tokens"`
	ProviderTokens      float64                     `json:"provider_tokens"`
	SuccessRate         float64                     `json:"success_rate"`
	AverageLatencyMs    float64                     `json:"avg_latency_ms"`
	LatencyP99Ms        float64                     `json:"latency_p99_ms"`
	AverageTTFTMs       float64                     `json:"avg_ttft_ms"`
	TTFTP99Ms           float64                     `json:"ttft_p99_ms"`
	UpstreamLatencyMs   float64                     `json:"upstream_latency_ms"`
	UpstreamP99Ms       float64                     `json:"upstream_p99_ms"`
	UpstreamErrors      float64                     `json:"upstream_errors"`
	Timeouts            float64                     `json:"timeouts"`
	Fallbacks           float64                     `json:"fallbacks"`
	LastTestTime        int64                       `json:"last_test_time"`
	ResponseTime        int                         `json:"response_time"`
	Series              []AWSMonitoringChannelPoint `json:"series"`
}

type AWSMonitoringChannelPoint struct {
	Time                int64   `json:"time"`
	Requests            float64 `json:"requests"`
	Errors              float64 `json:"errors"`
	Tokens              float64 `json:"tokens"`
	CachedTokens        float64 `json:"cached_tokens"`
	CacheCreationTokens float64 `json:"cache_creation_tokens"`
	ReasoningTokens     float64 `json:"reasoning_tokens"`
	ProviderTokens      float64 `json:"provider_tokens"`
	RPM                 float64 `json:"rpm"`
	TPM                 float64 `json:"tpm"`
	ProviderTPM         float64 `json:"provider_tpm"`
	SuccessRate         float64 `json:"success_rate"`
	AverageLatencyMs    float64 `json:"avg_latency_ms"`
	LatencyP99Ms        float64 `json:"latency_p99_ms"`
	AverageTTFTMs       float64 `json:"avg_ttft_ms"`
	TTFTP99Ms           float64 `json:"ttft_p99_ms"`
	UpstreamLatencyMs   float64 `json:"upstream_latency_ms"`
	UpstreamP99Ms       float64 `json:"upstream_p99_ms"`
	UpstreamErrors      float64 `json:"upstream_errors"`
	Timeouts            float64 `json:"timeouts"`
	Fallbacks           float64 `json:"fallbacks"`
}

type AWSMonitoringOverview struct {
	Namespace    string                 `json:"namespace"`
	Region       string                 `json:"region"`
	StartTime    int64                  `json:"start_time"`
	EndTime      int64                  `json:"end_time"`
	Period       int                    `json:"period"`
	Hours        int                    `json:"hours"`
	ChannelLimit int                    `json:"channel_limit"`
	Summary      AWSMonitoringSummary   `json:"summary"`
	Series       []AWSMonitoringPoint   `json:"series"`
	Channels     []AWSMonitoringChannel `json:"channels"`
}

type cwSeries struct {
	Values map[int64]float64
	Sum    float64
	Avg    float64
	Peak   float64
}

type cwQuery struct {
	ID         string
	Expression string
	Label      string
	Namespace  string
	MetricName string
	Stat       string
	Period     int
	DimName    string
	DimValue   string
	ReturnData bool
}

type cwGetMetricDataResponse struct {
	XMLName xml.Name `xml:"GetMetricDataResponse"`
	Result  struct {
		NextToken         string `xml:"NextToken"`
		MetricDataResults struct {
			Members []struct {
				ID         string `xml:"Id"`
				Label      string `xml:"Label"`
				Timestamps struct {
					Members []string `xml:"member"`
				} `xml:"Timestamps"`
				Values struct {
					Members []float64 `xml:"member"`
				} `xml:"Values"`
			} `xml:"member"`
		} `xml:"MetricDataResults"`
	} `xml:"GetMetricDataResult"`
}

func GetAWSMonitoringOverview(ctx context.Context, req AWSMonitoringRequest) (*AWSMonitoringOverview, error) {
	req = normalizeMonitoringRequest(req)
	end := time.Now().UTC()
	start := end.Add(-time.Duration(req.Hours) * time.Hour)
	namespace := logger.MetricsNamespace()
	region := logger.ResolveCloudWatchRegion()

	cfg, err := logger.LoadAWSConfigForCloudWatch(ctx)
	if err != nil {
		return nil, err
	}
	if region == "" {
		region = cfg.Region
	}
	if strings.TrimSpace(region) == "" {
		return nil, fmt.Errorf("cloudwatch monitoring: set CLOUDWATCH_LOG_REGION, RAW_LOG_S3_REGION, or AWS_REGION")
	}

	channels, err := model.GetAllChannels(0, req.ChannelLimit, false, false)
	if err != nil {
		return nil, err
	}

	buckets := buildTimeBuckets(start, end, req.Period)
	site, err := fetchSiteMetrics(ctx, cfg, namespace, start, end, req.Period)
	if err != nil {
		return nil, err
	}
	channelMetrics, err := fetchChannelMetrics(ctx, cfg, namespace, start, end, req.Period, channels)
	if err != nil {
		return nil, err
	}

	channelRows := buildMonitoringChannels(channels, channelMetrics, buckets, req.Period)
	channelSite := aggregateChannelMetrics(channelMetrics, req.Period)
	site = mergeSiteMetricFallback(site, channelSite)
	series := buildMonitoringSeries(buckets, site, req.Period)
	summary := buildMonitoringSummary(series)
	if summary.Requests == 0 {
		summary = buildMonitoringSummaryFromChannels(channelRows, req.Hours)
	}

	return &AWSMonitoringOverview{
		Namespace:    namespace,
		Region:       region,
		StartTime:    start.Unix(),
		EndTime:      end.Unix(),
		Period:       req.Period,
		Hours:        req.Hours,
		ChannelLimit: req.ChannelLimit,
		Summary:      summary,
		Series:       series,
		Channels:     channelRows,
	}, nil
}

func normalizeMonitoringRequest(req AWSMonitoringRequest) AWSMonitoringRequest {
	if req.Hours <= 0 {
		req.Hours = defaultMonitoringHours
	}
	if req.Hours > 168 {
		req.Hours = 168
	}
	if req.Period <= 0 {
		switch {
		case req.Hours <= 3:
			req.Period = 60
		case req.Hours <= 24:
			req.Period = 300
		default:
			req.Period = 3600
		}
	}
	if req.Period < 60 {
		req.Period = 60
	}
	if req.ChannelLimit <= 0 {
		req.ChannelLimit = defaultChannelLimit
	}
	if req.ChannelLimit > maxChannelLimit {
		req.ChannelLimit = maxChannelLimit
	}
	return req
}

func buildTimeBuckets(start, end time.Time, period int) []int64 {
	startUnix := start.Unix()
	period64 := int64(period)
	aligned := startUnix - (startUnix % period64)
	var buckets []int64
	for ts := aligned; ts <= end.Unix(); ts += period64 {
		buckets = append(buckets, ts)
	}
	return buckets
}

func fetchSiteMetrics(ctx context.Context, cfg aws.Config, namespace string, start, end time.Time, period int) (map[string]cwSeries, error) {
	queries := []cwQuery{
		expressionQuery("site_req", searchSumExpression(namespace, "RequestCount", "Sum", period), "Requests"),
		expressionQuery("site_err", searchSumExpression(namespace, "ErrorCount", "Sum", period), "Errors"),
		expressionQuery("site_in", searchSumExpression(namespace, "InputTokens", "Sum", period), "InputTokens"),
		expressionQuery("site_out", searchSumExpression(namespace, "OutputTokens", "Sum", period), "OutputTokens"),
		expressionQuery("site_cached", searchSumExpression(namespace, "CachedTokens", "Sum", period), "CachedTokens"),
		expressionQuery("site_cache_create", searchSumExpression(namespace, "CacheCreationTokens", "Sum", period), "CacheCreationTokens"),
		expressionQuery("site_reasoning", searchSumExpression(namespace, "ReasoningTokens", "Sum", period), "ReasoningTokens"),
		expressionQuery("site_lat", searchAvgExpression(namespace, "RequestLatencyMs", "Average", period), "Latency"),
		expressionQuery("site_lat_p99", searchAvgExpression(namespace, "RequestLatencyMs", "p99", period), "LatencyP99"),
		expressionQuery("site_lat_max", searchAvgExpression(namespace, "RequestLatencyMs", "Maximum", period), "LatencyMax"),
		expressionQuery("site_ttft", searchAvgExpression(namespace, "TTFTMs", "Average", period), "TTFT"),
		expressionQuery("site_ttft_p99", searchAvgExpression(namespace, "TTFTMs", "p99", period), "TTFTP99"),
		expressionQuery("site_ttft_max", searchAvgExpression(namespace, "TTFTMs", "Maximum", period), "TTFTMax"),
		expressionQuery("site_uplat", searchAvgExpression(namespace, "UpstreamLatencyMs", "Average", period), "UpstreamLatency"),
		expressionQuery("site_uplat_p99", searchAvgExpression(namespace, "UpstreamLatencyMs", "p99", period), "UpstreamLatencyP99"),
		expressionQuery("site_uplat_max", searchAvgExpression(namespace, "UpstreamLatencyMs", "Maximum", period), "UpstreamLatencyMax"),
	}
	results, err := getMetricData(ctx, cfg, start, end, queries)
	if err != nil {
		return nil, err
	}
	return results, nil
}

func fetchChannelMetrics(ctx context.Context, cfg aws.Config, namespace string, start, end time.Time, period int, channels []*model.Channel) (map[int]map[string]cwSeries, error) {
	results := make(map[int]map[string]cwSeries)
	const metricsPerChannel = 19
	chunkSize := 500 / metricsPerChannel
	if chunkSize < 1 {
		chunkSize = 1
	}
	for i := 0; i < len(channels); i += chunkSize {
		endIdx := i + chunkSize
		if endIdx > len(channels) {
			endIdx = len(channels)
		}
		queryChannels := channels[i:endIdx]
		queries := make([]cwQuery, 0, len(queryChannels)*metricsPerChannel)
		idMap := make(map[string]struct {
			channelID int
			metric    string
		})
		for idx, ch := range queryChannels {
			prefix := fmt.Sprintf("c%d_%d", i, idx)
			channelKey := channelMetricKey(ch.Id)
			add := func(suffix, metricName, stat string) {
				id := prefix + "_" + suffix
				queries = append(queries, metricQuery(id, namespace, metricName, stat, period, "Channel", channelKey))
				idMap[id] = struct {
					channelID int
					metric    string
				}{channelID: ch.Id, metric: suffix}
			}
			add("req", "RequestCount", "Sum")
			add("err", "ErrorCount", "Sum")
			add("in", "InputTokens", "Sum")
			add("out", "OutputTokens", "Sum")
			add("cached", "CachedTokens", "Sum")
			add("cache_create", "CacheCreationTokens", "Sum")
			add("reasoning", "ReasoningTokens", "Sum")
			add("lat", "RequestLatencyMs", "Average")
			add("lat_p99", "RequestLatencyMs", "p99")
			add("lat_max", "RequestLatencyMs", "Maximum")
			add("ttft", "TTFTMs", "Average")
			add("ttft_p99", "TTFTMs", "p99")
			add("ttft_max", "TTFTMs", "Maximum")
			add("uplat", "UpstreamLatencyMs", "Average")
			add("uplat_p99", "UpstreamLatencyMs", "p99")
			add("uplat_max", "UpstreamLatencyMs", "Maximum")
			add("uperr", "UpstreamErrorCount", "Sum")
			add("timeout", "UpstreamTimeoutCount", "Sum")
			add("fallback", "ChannelFallbackCount", "Sum")
		}
		batchResults, err := getMetricData(ctx, cfg, start, end, queries)
		if err != nil {
			return nil, err
		}
		for id, series := range batchResults {
			meta, ok := idMap[id]
			if !ok {
				continue
			}
			if _, exists := results[meta.channelID]; !exists {
				results[meta.channelID] = make(map[string]cwSeries)
			}
			results[meta.channelID][meta.metric] = series
		}
	}
	return results, nil
}

func getMetricData(ctx context.Context, cfg aws.Config, start, end time.Time, queries []cwQuery) (map[string]cwSeries, error) {
	seriesByID := make(map[string]cwSeries, len(queries))
	if len(queries) == 0 {
		return seriesByID, nil
	}
	nextToken := ""
	for {
		out, err := callCloudWatchGetMetricData(ctx, cfg, start, end, queries, nextToken)
		if err != nil {
			return nil, err
		}
		for _, result := range out.Result.MetricDataResults.Members {
			id := result.ID
			current := seriesByID[id]
			if current.Values == nil {
				current.Values = make(map[int64]float64)
			}
			for i, tsRaw := range result.Timestamps.Members {
				if i >= len(result.Values.Members) {
					continue
				}
				ts, err := time.Parse(time.RFC3339, tsRaw)
				if err != nil {
					continue
				}
				current.Values[ts.Unix()] += result.Values.Members[i]
			}
			seriesByID[id] = current
		}
		if out.Result.NextToken == "" {
			break
		}
		nextToken = out.Result.NextToken
	}
	for id, series := range seriesByID {
		series = finalizeSeries(series)
		seriesByID[id] = series
	}
	return seriesByID, nil
}

func callCloudWatchGetMetricData(ctx context.Context, cfg aws.Config, start, end time.Time, queries []cwQuery, nextToken string) (*cwGetMetricDataResponse, error) {
	values := url.Values{}
	values.Set("Action", "GetMetricData")
	values.Set("Version", "2010-08-01")
	values.Set("StartTime", start.Format(time.RFC3339))
	values.Set("EndTime", end.Format(time.RFC3339))
	values.Set("ScanBy", "TimestampAscending")
	if nextToken != "" {
		values.Set("NextToken", nextToken)
	}
	for i, query := range queries {
		prefix := fmt.Sprintf("MetricDataQueries.member.%d.", i+1)
		values.Set(prefix+"Id", query.ID)
		values.Set(prefix+"ReturnData", strconv.FormatBool(query.ReturnData))
		if query.Label != "" {
			values.Set(prefix+"Label", query.Label)
		}
		if query.Expression != "" {
			values.Set(prefix+"Expression", query.Expression)
			continue
		}
		values.Set(prefix+"MetricStat.Metric.Namespace", query.Namespace)
		values.Set(prefix+"MetricStat.Metric.MetricName", query.MetricName)
		values.Set(prefix+"MetricStat.Metric.Dimensions.member.1.Name", query.DimName)
		values.Set(prefix+"MetricStat.Metric.Dimensions.member.1.Value", query.DimValue)
		values.Set(prefix+"MetricStat.Period", strconv.Itoa(query.Period))
		values.Set(prefix+"MetricStat.Stat", query.Stat)
	}

	body := values.Encode()
	endpoint := fmt.Sprintf("https://monitoring.%s.amazonaws.com/", cfg.Region)
	httpClient := cfg.HTTPClient
	if httpClient == nil {
		httpClient = http.DefaultClient
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, strings.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded; charset=utf-8")

	hashBytes := sha256.Sum256([]byte(body))
	payloadHash := hex.EncodeToString(hashBytes[:])
	req.Header.Set("X-Amz-Content-Sha256", payloadHash)
	creds, err := cfg.Credentials.Retrieve(ctx)
	if err != nil {
		return nil, fmt.Errorf("cloudwatch monitoring: retrieve aws credentials: %w", err)
	}
	if err = v4.NewSigner().SignHTTP(ctx, creds, req, payloadHash, "monitoring", cfg.Region, time.Now()); err != nil {
		return nil, fmt.Errorf("cloudwatch monitoring: sign request: %w", err)
	}
	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("cloudwatch monitoring: request failed: %w", err)
	}
	defer CloseResponseBodyGracefully(resp)
	respBody, err := io.ReadAll(io.LimitReader(resp.Body, 4*1024*1024))
	if err != nil {
		return nil, err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("cloudwatch monitoring: status=%d body=%s", resp.StatusCode, string(respBody))
	}
	var parsed cwGetMetricDataResponse
	if err := xml.Unmarshal(respBody, &parsed); err != nil {
		return nil, fmt.Errorf("cloudwatch monitoring: parse response: %w", err)
	}
	return &parsed, nil
}

func finalizeSeries(series cwSeries) cwSeries {
	var count float64
	for _, v := range series.Values {
		if math.IsNaN(v) || math.IsInf(v, 0) {
			continue
		}
		series.Sum += v
		if v > series.Peak {
			series.Peak = v
		}
		if v != 0 {
			series.Avg += v
			count++
		}
	}
	if count > 0 {
		series.Avg = series.Avg / count
	}
	return series
}

func aggregateChannelMetrics(metrics map[int]map[string]cwSeries, period int) map[string]cwSeries {
	site := map[string]cwSeries{
		"site_req":       {},
		"site_err":       {},
		"site_in":        {},
		"site_out":       {},
		"site_lat":       {},
		"site_ttft":      {},
		"site_uplat":     {},
		"site_lat_p99":   {},
		"site_lat_max":   {},
		"site_ttft_p99":  {},
		"site_ttft_max":  {},
		"site_uplat_p99": {},
		"site_uplat_max": {},
	}
	latencyWeightByBucket := make(map[int64]float64)
	latencyCountByBucket := make(map[int64]float64)
	ttftWeightByBucket := make(map[int64]float64)
	ttftCountByBucket := make(map[int64]float64)
	upstreamLatencyWeightByBucket := make(map[int64]float64)
	upstreamLatencyCountByBucket := make(map[int64]float64)
	for _, channelMetrics := range metrics {
		reqSeries := channelMetrics["req"]
		addMetricSeries(site, "site_req", channelMetrics["req"], period)
		addMetricSeries(site, "site_err", channelMetrics["err"], period)
		addMetricSeries(site, "site_in", channelMetrics["in"], period)
		addMetricSeries(site, "site_out", channelMetrics["out"], period)
		addMetricSeries(site, "site_cached", channelMetrics["cached"], period)
		addMetricSeries(site, "site_cache_create", channelMetrics["cache_create"], period)
		addMetricSeries(site, "site_reasoning", channelMetrics["reasoning"], period)
		for rawTS, latency := range channelMetrics["lat"].Values {
			if latency <= 0 || math.IsNaN(latency) || math.IsInf(latency, 0) {
				continue
			}
			ts := alignMetricTimestamp(rawTS, period)
			weight := reqSeries.Values[rawTS]
			if weight <= 0 {
				weight = 1
			}
			addWeightedMetricValue(site, "site_lat", ts, latency, weight)
			latencyWeightByBucket[ts] += latency * weight
			latencyCountByBucket[ts] += weight
		}
		for rawTS, latency := range channelMetrics["uplat"].Values {
			if latency <= 0 || math.IsNaN(latency) || math.IsInf(latency, 0) {
				continue
			}
			ts := alignMetricTimestamp(rawTS, period)
			weight := reqSeries.Values[rawTS]
			if weight <= 0 {
				weight = 1
			}
			addWeightedMetricValue(site, "site_uplat", ts, latency, weight)
			upstreamLatencyWeightByBucket[ts] += latency * weight
			upstreamLatencyCountByBucket[ts] += weight
		}
		for rawTS, ttft := range channelMetrics["ttft"].Values {
			if ttft <= 0 || math.IsNaN(ttft) || math.IsInf(ttft, 0) {
				continue
			}
			ts := alignMetricTimestamp(rawTS, period)
			weight := reqSeries.Values[rawTS]
			if weight <= 0 {
				weight = 1
			}
			addWeightedMetricValue(site, "site_ttft", ts, ttft, weight)
			ttftWeightByBucket[ts] += ttft * weight
			ttftCountByBucket[ts] += weight
		}
		addMaxMetricSeries(site, "site_lat_p99", channelMetrics["lat_p99"], period)
		addMaxMetricSeries(site, "site_lat_max", channelMetrics["lat_max"], period)
		addMaxMetricSeries(site, "site_ttft_p99", channelMetrics["ttft_p99"], period)
		addMaxMetricSeries(site, "site_ttft_max", channelMetrics["ttft_max"], period)
		addMaxMetricSeries(site, "site_uplat_p99", channelMetrics["uplat_p99"], period)
		addMaxMetricSeries(site, "site_uplat_max", channelMetrics["uplat_max"], period)
	}
	if latSeries := site["site_lat"]; latSeries.Values != nil {
		for ts, weightedLatency := range latencyWeightByBucket {
			if latencyCountByBucket[ts] > 0 {
				latSeries.Values[ts] = weightedLatency / latencyCountByBucket[ts]
			}
		}
		site["site_lat"] = latSeries
	}
	if latencySeries := site["site_uplat"]; latencySeries.Values != nil {
		for ts, weightedLatency := range upstreamLatencyWeightByBucket {
			if upstreamLatencyCountByBucket[ts] > 0 {
				latencySeries.Values[ts] = weightedLatency / upstreamLatencyCountByBucket[ts]
			}
		}
		site["site_uplat"] = latencySeries
	}
	if ttftSeries := site["site_ttft"]; ttftSeries.Values != nil {
		for ts, weightedTTFT := range ttftWeightByBucket {
			if ttftCountByBucket[ts] > 0 {
				ttftSeries.Values[ts] = weightedTTFT / ttftCountByBucket[ts]
			}
		}
		site["site_ttft"] = ttftSeries
	}
	for id, series := range site {
		site[id] = finalizeSeries(series)
	}
	return site
}

func addMetricSeries(target map[string]cwSeries, id string, source cwSeries, period int) {
	for rawTS, value := range source.Values {
		if value == 0 || math.IsNaN(value) || math.IsInf(value, 0) {
			continue
		}
		addMetricValue(target, id, alignMetricTimestamp(rawTS, period), value)
	}
}

func addMaxMetricSeries(target map[string]cwSeries, id string, source cwSeries, period int) {
	for rawTS, value := range source.Values {
		if value == 0 || math.IsNaN(value) || math.IsInf(value, 0) {
			continue
		}
		addMaxMetricValue(target, id, alignMetricTimestamp(rawTS, period), value)
	}
}

func addMetricValue(target map[string]cwSeries, id string, ts int64, value float64) {
	series := target[id]
	if series.Values == nil {
		series.Values = make(map[int64]float64)
	}
	series.Values[ts] += value
	target[id] = series
}

func addMaxMetricValue(target map[string]cwSeries, id string, ts int64, value float64) {
	series := target[id]
	if series.Values == nil {
		series.Values = make(map[int64]float64)
	}
	if value > series.Values[ts] {
		series.Values[ts] = value
	}
	target[id] = series
}

func addWeightedMetricValue(target map[string]cwSeries, id string, ts int64, value, weight float64) {
	series := target[id]
	if series.Values == nil {
		series.Values = make(map[int64]float64)
	}
	series.Values[ts] += value * weight
	target[id] = series
}

func alignMetricTimestamp(ts int64, period int) int64 {
	if period <= 0 {
		return ts
	}
	period64 := int64(period)
	return ts - (ts % period64)
}

func mergeSiteMetricFallback(primary, fallback map[string]cwSeries) map[string]cwSeries {
	if primary == nil {
		return fallback
	}
	for id, fallbackSeries := range fallback {
		primarySeries := primary[id]
		if primarySeries.Sum == 0 && fallbackSeries.Sum > 0 {
			primary[id] = fallbackSeries
		}
	}
	return primary
}

func expressionQuery(id, expression, label string) cwQuery {
	return cwQuery{
		ID:         id,
		Expression: expression,
		Label:      label,
		ReturnData: true,
	}
}

func metricQuery(id, namespace, metricName, stat string, period int, dimensionName, dimensionValue string) cwQuery {
	return cwQuery{
		ID:         id,
		Namespace:  namespace,
		MetricName: metricName,
		Stat:       stat,
		Period:     period,
		DimName:    dimensionName,
		DimValue:   dimensionValue,
		ReturnData: true,
	}
}

func searchSumExpression(namespace, metricName, stat string, period int) string {
	return fmt.Sprintf("SUM(SEARCH('{%s,Channel} MetricName=\"%s\"', '%s', %d))", namespace, metricName, stat, period)
}

func searchAvgExpression(namespace, metricName, stat string, period int) string {
	return fmt.Sprintf("AVG(SEARCH('{%s,Channel} MetricName=\"%s\"', '%s', %d))", namespace, metricName, stat, period)
}

func buildMonitoringSeries(buckets []int64, site map[string]cwSeries, period int) []AWSMonitoringPoint {
	buckets = mergeMetricBuckets(buckets, site)
	points := make([]AWSMonitoringPoint, 0, len(buckets))
	minutes := float64(period) / 60.0
	for _, ts := range buckets {
		requests := valueAt(site, "site_req", ts)
		errors := valueAt(site, "site_err", ts)
		tokens := valueAt(site, "site_in", ts) + valueAt(site, "site_out", ts)
		cachedTokens := valueAt(site, "site_cached", ts)
		cacheCreationTokens := valueAt(site, "site_cache_create", ts)
		reasoningTokens := valueAt(site, "site_reasoning", ts)
		providerTokens := tokens + cachedTokens + cacheCreationTokens + reasoningTokens
		latencyP99 := firstNonZero(valueAt(site, "site_lat_p99", ts), valueAt(site, "site_lat_max", ts))
		ttftP99 := firstNonZero(valueAt(site, "site_ttft_p99", ts), valueAt(site, "site_ttft_max", ts))
		upstreamP99 := firstNonZero(valueAt(site, "site_uplat_p99", ts), valueAt(site, "site_uplat_max", ts))
		point := AWSMonitoringPoint{
			Time:                ts,
			Requests:            roundMetric(requests),
			Errors:              roundMetric(errors),
			Tokens:              roundMetric(tokens),
			CachedTokens:        roundMetric(cachedTokens),
			CacheCreationTokens: roundMetric(cacheCreationTokens),
			ReasoningTokens:     roundMetric(reasoningTokens),
			ProviderTokens:      roundMetric(providerTokens),
			RPM:                 roundMetric(requests / minutes),
			TPM:                 roundMetric(tokens / minutes),
			ProviderTPM:         roundMetric(providerTokens / minutes),
			SuccessRate:         successRate(requests, errors),
			LatencyMs:           roundMetric(valueAt(site, "site_lat", ts)),
			LatencyP99Ms:        roundMetric(latencyP99),
			UpstreamLatencyMs:   roundMetric(valueAt(site, "site_uplat", ts)),
			UpstreamP99Ms:       roundMetric(upstreamP99),
			TTFTMs:              roundMetric(valueAt(site, "site_ttft", ts)),
			TTFTP99Ms:           roundMetric(ttftP99),
		}
		points = append(points, point)
	}
	return points
}

func mergeMetricBuckets(buckets []int64, site map[string]cwSeries) []int64 {
	seen := make(map[int64]bool, len(buckets))
	for _, ts := range buckets {
		seen[ts] = true
	}
	for _, series := range site {
		for ts := range series.Values {
			seen[ts] = true
		}
	}
	merged := make([]int64, 0, len(seen))
	for ts := range seen {
		merged = append(merged, ts)
	}
	sort.Slice(merged, func(i, j int) bool {
		return merged[i] < merged[j]
	})
	return merged
}

func buildMonitoringSummary(series []AWSMonitoringPoint) AWSMonitoringSummary {
	var summary AWSMonitoringSummary
	var latencySum float64
	var latencyCount float64
	var ttftSum float64
	var ttftCount float64
	var upstreamLatencySum float64
	var upstreamLatencyCount float64
	var rpmSum float64
	var tpmSum float64
	var providerTpmSum float64
	for _, point := range series {
		summary.Requests += point.Requests
		summary.Errors += point.Errors
		summary.Tokens += point.Tokens
		summary.CachedTokens += point.CachedTokens
		summary.CacheCreationTokens += point.CacheCreationTokens
		summary.ReasoningTokens += point.ReasoningTokens
		summary.ProviderTokens += point.ProviderTokens
		rpmSum += point.RPM
		tpmSum += point.TPM
		providerTpmSum += point.ProviderTPM
		if point.RPM > summary.PeakRPM {
			summary.PeakRPM = point.RPM
		}
		if point.TPM > summary.PeakTPM {
			summary.PeakTPM = point.TPM
		}
		if point.ProviderTPM > summary.PeakProviderTPM {
			summary.PeakProviderTPM = point.ProviderTPM
		}
		if point.LatencyMs > 0 {
			latencySum += point.LatencyMs
			latencyCount++
		}
		if point.LatencyP99Ms > summary.LatencyP99Ms {
			summary.LatencyP99Ms = point.LatencyP99Ms
		}
		if point.TTFTMs > 0 {
			ttftSum += point.TTFTMs
			ttftCount++
		}
		if point.TTFTP99Ms > summary.TTFTP99Ms {
			summary.TTFTP99Ms = point.TTFTP99Ms
		}
		if point.UpstreamLatencyMs > 0 {
			upstreamLatencySum += point.UpstreamLatencyMs
			upstreamLatencyCount++
		}
		if point.UpstreamP99Ms > summary.UpstreamP99Ms {
			summary.UpstreamP99Ms = point.UpstreamP99Ms
		}
	}
	if len(series) > 0 {
		summary.AverageRPM = roundMetric(rpmSum / float64(len(series)))
		summary.AverageTPM = roundMetric(tpmSum / float64(len(series)))
		summary.AverageProviderTPM = roundMetric(providerTpmSum / float64(len(series)))
	}
	if latencyCount > 0 {
		summary.AverageLatencyMs = roundMetric(latencySum / latencyCount)
	}
	if ttftCount > 0 {
		summary.AverageTTFTMs = roundMetric(ttftSum / ttftCount)
	}
	if upstreamLatencyCount > 0 {
		summary.UpstreamLatencyMs = roundMetric(upstreamLatencySum / upstreamLatencyCount)
	}
	summary.Requests = roundMetric(summary.Requests)
	summary.Errors = roundMetric(summary.Errors)
	summary.Tokens = roundMetric(summary.Tokens)
	summary.CachedTokens = roundMetric(summary.CachedTokens)
	summary.CacheCreationTokens = roundMetric(summary.CacheCreationTokens)
	summary.ReasoningTokens = roundMetric(summary.ReasoningTokens)
	summary.ProviderTokens = roundMetric(summary.ProviderTokens)
	summary.SuccessRate = successRate(summary.Requests, summary.Errors)
	return summary
}

func buildMonitoringSummaryFromChannels(channels []AWSMonitoringChannel, hours int) AWSMonitoringSummary {
	var summary AWSMonitoringSummary
	var latencyWeightedSum float64
	var latencyWeight float64
	var ttftWeightedSum float64
	var ttftWeight float64
	var upstreamLatencyWeightedSum float64
	var upstreamLatencyWeight float64
	for _, channel := range channels {
		summary.Requests += channel.Requests
		summary.Errors += channel.Errors
		summary.Tokens += channel.Tokens
		summary.CachedTokens += channel.CachedTokens
		summary.CacheCreationTokens += channel.CacheCreationTokens
		summary.ReasoningTokens += channel.ReasoningTokens
		summary.ProviderTokens += channel.ProviderTokens
		if channel.AverageLatencyMs > 0 {
			weight := channel.Requests
			if weight <= 0 {
				weight = 1
			}
			latencyWeightedSum += channel.AverageLatencyMs * weight
			latencyWeight += weight
		}
		if channel.LatencyP99Ms > summary.LatencyP99Ms {
			summary.LatencyP99Ms = channel.LatencyP99Ms
		}
		if channel.AverageTTFTMs > 0 {
			weight := channel.Requests
			if weight <= 0 {
				weight = 1
			}
			ttftWeightedSum += channel.AverageTTFTMs * weight
			ttftWeight += weight
		}
		if channel.TTFTP99Ms > summary.TTFTP99Ms {
			summary.TTFTP99Ms = channel.TTFTP99Ms
		}
		if channel.UpstreamLatencyMs > 0 {
			weight := channel.Requests
			if weight <= 0 {
				weight = 1
			}
			upstreamLatencyWeightedSum += channel.UpstreamLatencyMs * weight
			upstreamLatencyWeight += weight
		}
		if channel.UpstreamP99Ms > summary.UpstreamP99Ms {
			summary.UpstreamP99Ms = channel.UpstreamP99Ms
		}
	}
	if hours > 0 {
		minutes := float64(hours * 60)
		summary.AverageRPM = roundMetric(summary.Requests / minutes)
		summary.AverageTPM = roundMetric(summary.Tokens / minutes)
		summary.AverageProviderTPM = roundMetric(summary.ProviderTokens / minutes)
	}
	if latencyWeight > 0 {
		summary.AverageLatencyMs = roundMetric(latencyWeightedSum / latencyWeight)
	}
	if ttftWeight > 0 {
		summary.AverageTTFTMs = roundMetric(ttftWeightedSum / ttftWeight)
	}
	if upstreamLatencyWeight > 0 {
		summary.UpstreamLatencyMs = roundMetric(upstreamLatencyWeightedSum / upstreamLatencyWeight)
	}
	summary.Requests = roundMetric(summary.Requests)
	summary.Errors = roundMetric(summary.Errors)
	summary.Tokens = roundMetric(summary.Tokens)
	summary.CachedTokens = roundMetric(summary.CachedTokens)
	summary.CacheCreationTokens = roundMetric(summary.CacheCreationTokens)
	summary.ReasoningTokens = roundMetric(summary.ReasoningTokens)
	summary.ProviderTokens = roundMetric(summary.ProviderTokens)
	summary.SuccessRate = successRate(summary.Requests, summary.Errors)
	return summary
}

func buildMonitoringChannels(channels []*model.Channel, metrics map[int]map[string]cwSeries, buckets []int64, period int) []AWSMonitoringChannel {
	rows := make([]AWSMonitoringChannel, 0, len(channels))
	for _, ch := range channels {
		rowMetrics := metrics[ch.Id]
		requests := seriesSum(rowMetrics, "req")
		errors := seriesSum(rowMetrics, "err")
		input := seriesSum(rowMetrics, "in")
		output := seriesSum(rowMetrics, "out")
		cached := seriesSum(rowMetrics, "cached")
		cacheCreate := seriesSum(rowMetrics, "cache_create")
		reasoning := seriesSum(rowMetrics, "reasoning")
		tokens := input + output
		providerTokens := tokens + cached + cacheCreate + reasoning
		row := AWSMonitoringChannel{
			ID:                  ch.Id,
			Name:                ch.Name,
			Type:                ch.Type,
			Status:              ch.Status,
			StatusText:          channelStatusText(ch.Status),
			MonitorKey:          channelMetricKey(ch.Id),
			Requests:            roundMetric(requests),
			Errors:              roundMetric(errors),
			Tokens:              roundMetric(tokens),
			CachedTokens:        roundMetric(cached),
			CacheCreationTokens: roundMetric(cacheCreate),
			ReasoningTokens:     roundMetric(reasoning),
			ProviderTokens:      roundMetric(providerTokens),
			SuccessRate:         successRate(requests, errors),
			AverageLatencyMs:    roundMetric(seriesAvg(rowMetrics, "lat")),
			LatencyP99Ms:        roundMetric(firstNonZero(seriesPeak(rowMetrics, "lat_p99"), seriesPeak(rowMetrics, "lat_max"))),
			AverageTTFTMs:       roundMetric(seriesAvg(rowMetrics, "ttft")),
			TTFTP99Ms:           roundMetric(firstNonZero(seriesPeak(rowMetrics, "ttft_p99"), seriesPeak(rowMetrics, "ttft_max"))),
			UpstreamLatencyMs:   roundMetric(seriesAvg(rowMetrics, "uplat")),
			UpstreamP99Ms:       roundMetric(firstNonZero(seriesPeak(rowMetrics, "uplat_p99"), seriesPeak(rowMetrics, "uplat_max"))),
			UpstreamErrors:      roundMetric(seriesSum(rowMetrics, "uperr")),
			Timeouts:            roundMetric(seriesSum(rowMetrics, "timeout")),
			Fallbacks:           roundMetric(seriesSum(rowMetrics, "fallback")),
			LastTestTime:        ch.TestTime,
			ResponseTime:        ch.ResponseTime,
			Series:              buildMonitoringChannelSeries(rowMetrics, buckets, period),
		}
		rows = append(rows, row)
	}
	sort.SliceStable(rows, func(i, j int) bool {
		if rows[i].Requests == rows[j].Requests {
			return rows[i].ID < rows[j].ID
		}
		return rows[i].Requests > rows[j].Requests
	})
	return rows
}

func buildMonitoringChannelSeries(metrics map[string]cwSeries, buckets []int64, period int) []AWSMonitoringChannelPoint {
	if metrics == nil {
		return nil
	}
	buckets = mergeMetricBuckets(buckets, metrics)
	points := make([]AWSMonitoringChannelPoint, 0, len(buckets))
	minutes := float64(period) / 60.0
	for _, ts := range buckets {
		requests := valueAt(metrics, "req", ts)
		errors := valueAt(metrics, "err", ts)
		tokens := valueAt(metrics, "in", ts) + valueAt(metrics, "out", ts)
		cachedTokens := valueAt(metrics, "cached", ts)
		cacheCreationTokens := valueAt(metrics, "cache_create", ts)
		reasoningTokens := valueAt(metrics, "reasoning", ts)
		providerTokens := tokens + cachedTokens + cacheCreationTokens + reasoningTokens
		latencyP99 := firstNonZero(valueAt(metrics, "lat_p99", ts), valueAt(metrics, "lat_max", ts))
		ttftP99 := firstNonZero(valueAt(metrics, "ttft_p99", ts), valueAt(metrics, "ttft_max", ts))
		upstreamP99 := firstNonZero(valueAt(metrics, "uplat_p99", ts), valueAt(metrics, "uplat_max", ts))
		point := AWSMonitoringChannelPoint{
			Time:                ts,
			Requests:            roundMetric(requests),
			Errors:              roundMetric(errors),
			Tokens:              roundMetric(tokens),
			CachedTokens:        roundMetric(cachedTokens),
			CacheCreationTokens: roundMetric(cacheCreationTokens),
			ReasoningTokens:     roundMetric(reasoningTokens),
			ProviderTokens:      roundMetric(providerTokens),
			RPM:                 roundMetric(requests / minutes),
			TPM:                 roundMetric(tokens / minutes),
			ProviderTPM:         roundMetric(providerTokens / minutes),
			SuccessRate:         successRate(requests, errors),
			AverageLatencyMs:    roundMetric(valueAt(metrics, "lat", ts)),
			LatencyP99Ms:        roundMetric(latencyP99),
			AverageTTFTMs:       roundMetric(valueAt(metrics, "ttft", ts)),
			TTFTP99Ms:           roundMetric(ttftP99),
			UpstreamLatencyMs:   roundMetric(valueAt(metrics, "uplat", ts)),
			UpstreamP99Ms:       roundMetric(upstreamP99),
			UpstreamErrors:      roundMetric(valueAt(metrics, "uperr", ts)),
			Timeouts:            roundMetric(valueAt(metrics, "timeout", ts)),
			Fallbacks:           roundMetric(valueAt(metrics, "fallback", ts)),
		}
		points = append(points, point)
	}
	return points
}

func valueAt(series map[string]cwSeries, id string, ts int64) float64 {
	if series == nil {
		return 0
	}
	s, ok := series[id]
	if !ok || s.Values == nil {
		return 0
	}
	return s.Values[ts]
}

func seriesSum(metrics map[string]cwSeries, key string) float64 {
	if metrics == nil {
		return 0
	}
	return metrics[key].Sum
}

func seriesAvg(metrics map[string]cwSeries, key string) float64 {
	if metrics == nil {
		return 0
	}
	return metrics[key].Avg
}

func seriesPeak(metrics map[string]cwSeries, key string) float64 {
	if metrics == nil {
		return 0
	}
	return metrics[key].Peak
}

func firstNonZero(values ...float64) float64 {
	for _, value := range values {
		if value > 0 && !math.IsNaN(value) && !math.IsInf(value, 0) {
			return value
		}
	}
	return 0
}

func successRate(requests, errors float64) float64 {
	if requests <= 0 {
		return 0
	}
	rate := (requests - errors) / requests * 100
	if rate < 0 {
		rate = 0
	}
	return roundMetric(rate)
}

func roundMetric(v float64) float64 {
	if math.IsNaN(v) || math.IsInf(v, 0) {
		return 0
	}
	return math.Round(v*100) / 100
}

func channelMetricKey(channelID int) string {
	return "ch" + strconv.Itoa(channelID)
}

func channelStatusText(status int) string {
	switch status {
	case common.ChannelStatusEnabled:
		return "enabled"
	case common.ChannelStatusManuallyDisabled:
		return "manually_disabled"
	case common.ChannelStatusAutoDisabled:
		return "auto_disabled"
	default:
		return "unknown"
	}
}

func ParseAWSMonitoringRequest(hoursRaw, periodRaw, limitRaw string) AWSMonitoringRequest {
	parse := func(raw string) int {
		raw = strings.TrimSpace(raw)
		if raw == "" {
			return 0
		}
		v, _ := strconv.Atoi(raw)
		return v
	}
	return AWSMonitoringRequest{
		Hours:        parse(hoursRaw),
		Period:       parse(periodRaw),
		ChannelLimit: parse(limitRaw),
	}
}
