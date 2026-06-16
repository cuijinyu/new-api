package service

import (
	"context"
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/logger"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs"
	logtypes "github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs/types"
)

const (
	defaultLogQueryHours = 1
	defaultLogQueryLimit = 100
	maxLogQueryHours     = 168
	maxLogQueryLimit     = 500
	defaultLogQuery      = "fields @timestamp, @logStream, @message | sort @timestamp desc | limit 100"
)

type AWSLogQueryRequest struct {
	Hours int
	Limit int
	Query string
}

type AWSLogQueryResult struct {
	LogGroup string           `json:"log_group"`
	Region   string           `json:"region"`
	Start    int64            `json:"start_time"`
	End      int64            `json:"end_time"`
	QueryID  string           `json:"query_id"`
	Query    string           `json:"query"`
	Status   string           `json:"status"`
	Fields   []string         `json:"fields"`
	Rows     []AWSLogQueryRow `json:"rows"`
	Stats    AWSLogQueryStats `json:"stats"`
	Partial  bool             `json:"partial"`
}

type AWSLogQueryRow map[string]string

type AWSLogQueryStats struct {
	RecordsMatched float64 `json:"records_matched"`
	RecordsScanned float64 `json:"records_scanned"`
	BytesScanned   float64 `json:"bytes_scanned"`
}

func ParseAWSLogQueryRequest(hours, limit, query string) AWSLogQueryRequest {
	req := AWSLogQueryRequest{
		Hours: parseIntOrDefault(hours, defaultLogQueryHours),
		Limit: parseIntOrDefault(limit, defaultLogQueryLimit),
		Query: strings.TrimSpace(query),
	}
	if req.Query == "" {
		req.Query = defaultLogQuery
	}
	if req.Hours <= 0 {
		req.Hours = defaultLogQueryHours
	}
	if req.Hours > maxLogQueryHours {
		req.Hours = maxLogQueryHours
	}
	if req.Limit <= 0 {
		req.Limit = defaultLogQueryLimit
	}
	if req.Limit > maxLogQueryLimit {
		req.Limit = maxLogQueryLimit
	}
	return req
}

func GetAWSLogQuery(ctx context.Context, req AWSLogQueryRequest) (*AWSLogQueryResult, error) {
	req = normalizeAWSLogQueryRequest(req)
	logGroup := strings.TrimSpace(os.Getenv("CLOUDWATCH_LOG_GROUP"))
	if logGroup == "" {
		return nil, fmt.Errorf("cloudwatch logs: set CLOUDWATCH_LOG_GROUP")
	}

	cfg, err := logger.LoadAWSConfigForCloudWatch(ctx)
	if err != nil {
		return nil, err
	}
	region := logger.ResolveCloudWatchRegion()
	if region == "" {
		region = cfg.Region
	}
	if strings.TrimSpace(region) == "" {
		return nil, fmt.Errorf("cloudwatch logs: set CLOUDWATCH_LOG_REGION, RAW_LOG_S3_REGION, or AWS_REGION")
	}

	end := time.Now().UTC()
	start := end.Add(-time.Duration(req.Hours) * time.Hour)
	client := cloudwatchlogs.NewFromConfig(cfg)
	query := ensureLogQueryLimit(req.Query, req.Limit)
	startOut, err := client.StartQuery(ctx, &cloudwatchlogs.StartQueryInput{
		LogGroupName: aws.String(logGroup),
		StartTime:    aws.Int64(start.Unix()),
		EndTime:      aws.Int64(end.Unix()),
		QueryString:  aws.String(query),
		Limit:        aws.Int32(int32(req.Limit)),
	})
	if err != nil {
		return nil, fmt.Errorf("cloudwatch logs: start query: %w", err)
	}
	if startOut.QueryId == nil || *startOut.QueryId == "" {
		return nil, fmt.Errorf("cloudwatch logs: empty query id")
	}

	out, partial, err := waitForLogQuery(ctx, client, *startOut.QueryId)
	if err != nil {
		return nil, err
	}

	fields, rows := flattenLogQueryRows(out.Results)
	return &AWSLogQueryResult{
		LogGroup: logGroup,
		Region:   region,
		Start:    start.Unix(),
		End:      end.Unix(),
		QueryID:  *startOut.QueryId,
		Query:    query,
		Status:   string(out.Status),
		Fields:   fields,
		Rows:     rows,
		Stats:    logQueryStats(out.Statistics),
		Partial:  partial,
	}, nil
}

func normalizeAWSLogQueryRequest(req AWSLogQueryRequest) AWSLogQueryRequest {
	if req.Hours <= 0 {
		req.Hours = defaultLogQueryHours
	}
	if req.Hours > maxLogQueryHours {
		req.Hours = maxLogQueryHours
	}
	if req.Limit <= 0 {
		req.Limit = defaultLogQueryLimit
	}
	if req.Limit > maxLogQueryLimit {
		req.Limit = maxLogQueryLimit
	}
	req.Query = strings.TrimSpace(req.Query)
	if req.Query == "" {
		req.Query = defaultLogQuery
	}
	return req
}

func ensureLogQueryLimit(query string, limit int) string {
	lines := strings.Split(query, "|")
	for _, line := range lines {
		if strings.HasPrefix(strings.TrimSpace(strings.ToLower(line)), "limit ") {
			return query
		}
	}
	return fmt.Sprintf("%s | limit %d", query, limit)
}

func waitForLogQuery(ctx context.Context, client *cloudwatchlogs.Client, queryID string) (*cloudwatchlogs.GetQueryResultsOutput, bool, error) {
	ticker := time.NewTicker(600 * time.Millisecond)
	defer ticker.Stop()
	deadline := time.NewTimer(18 * time.Second)
	defer deadline.Stop()

	var latest *cloudwatchlogs.GetQueryResultsOutput
	for {
		out, err := client.GetQueryResults(ctx, &cloudwatchlogs.GetQueryResultsInput{
			QueryId: aws.String(queryID),
		})
		if err != nil {
			return nil, false, fmt.Errorf("cloudwatch logs: get query results: %w", err)
		}
		latest = out
		switch out.Status {
		case logtypes.QueryStatusComplete:
			return out, false, nil
		case logtypes.QueryStatusFailed, logtypes.QueryStatusCancelled, logtypes.QueryStatusTimeout:
			return out, true, nil
		}

		select {
		case <-ctx.Done():
			if latest != nil {
				return latest, true, nil
			}
			return nil, false, ctx.Err()
		case <-deadline.C:
			return latest, true, nil
		case <-ticker.C:
		}
	}
}

func flattenLogQueryRows(results [][]logtypes.ResultField) ([]string, []AWSLogQueryRow) {
	fieldSet := make(map[string]bool)
	rows := make([]AWSLogQueryRow, 0, len(results))
	for _, result := range results {
		row := make(AWSLogQueryRow)
		for _, field := range result {
			if field.Field == nil {
				continue
			}
			name := *field.Field
			value := ""
			if field.Value != nil {
				value = *field.Value
			}
			fieldSet[name] = true
			row[name] = value
		}
		rows = append(rows, row)
	}
	fields := make([]string, 0, len(fieldSet))
	for field := range fieldSet {
		fields = append(fields, field)
	}
	sort.Slice(fields, func(i, j int) bool {
		return logFieldWeight(fields[i]) < logFieldWeight(fields[j])
	})
	return fields, rows
}

func logFieldWeight(field string) string {
	switch field {
	case "@timestamp":
		return "00"
	case "@logStream":
		return "01"
	case "@message":
		return "02"
	case "@ptr":
		return "99"
	default:
		return "50" + field
	}
}

func logQueryStats(stats *logtypes.QueryStatistics) AWSLogQueryStats {
	if stats == nil {
		return AWSLogQueryStats{}
	}
	return AWSLogQueryStats{
		RecordsMatched: stats.RecordsMatched,
		RecordsScanned: stats.RecordsScanned,
		BytesScanned:   stats.BytesScanned,
	}
}

func parseIntOrDefault(raw string, fallback int) int {
	value, err := strconv.Atoi(strings.TrimSpace(raw))
	if err != nil {
		return fallback
	}
	return value
}
