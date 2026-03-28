package logger

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs/types"
)

const (
	cwMaxEventsPerBatch = 500
	cwMaxBatchBytes     = 900_000
	cwMaxMessageLen     = 256 * 1024
	cwChunkChanCap      = 16384
)

var ansiRegexp = regexp.MustCompile("\x1b\\[[0-9;]*m")

type cwSink struct {
	client *cloudwatchlogs.Client
	group  string
	stream string

	stripANSI bool

	chunkCh chan []byte
	stopCh  chan struct{}
	wg      sync.WaitGroup

	mu            sync.Mutex
	sequenceToken *string
}

var cloudWatchSink *cwSink

// resolveCloudWatchRegion 与 S3 原始日志同区（如新加坡 ap-southeast-1）：优先专用变量，其次 RAW_LOG_S3_REGION，再 AWS_REGION。
func resolveCloudWatchRegion() string {
	for _, key := range []string{"CLOUDWATCH_LOG_REGION", "RAW_LOG_S3_REGION", "AWS_REGION"} {
		if r := strings.TrimSpace(os.Getenv(key)); r != "" {
			return r
		}
	}
	return ""
}

func loadAWSConfigForCloudWatch(ctx context.Context) (aws.Config, error) {
	opts := []func(*config.LoadOptions) error{}
	if r := resolveCloudWatchRegion(); r != "" {
		opts = append(opts, config.WithRegion(r))
	}

	if strings.TrimSpace(os.Getenv("AWS_ACCESS_KEY_ID")) != "" {
		cfg, err := config.LoadDefaultConfig(ctx, opts...)
		if err != nil {
			return aws.Config{}, fmt.Errorf("cloudwatch logs: load aws config: %w", err)
		}
		return cfg, nil
	}
	rawAK := strings.TrimSpace(os.Getenv("RAW_LOG_S3_ACCESS_KEY_ID"))
	rawSK := strings.TrimSpace(os.Getenv("RAW_LOG_S3_SECRET_ACCESS_KEY"))
	if rawAK != "" && rawSK != "" {
		region := resolveCloudWatchRegion()
		if region == "" {
			return aws.Config{}, fmt.Errorf("cloudwatch logs: set CLOUDWATCH_LOG_REGION, RAW_LOG_S3_REGION, or AWS_REGION when using RAW_LOG_S3_* credentials")
		}
		token := os.Getenv("RAW_LOG_S3_SESSION_TOKEN")
		cfg, err := config.LoadDefaultConfig(ctx,
			config.WithRegion(region),
			config.WithCredentialsProvider(credentials.NewStaticCredentialsProvider(rawAK, rawSK, token)),
		)
		if err != nil {
			return aws.Config{}, fmt.Errorf("cloudwatch logs: load aws config: %w", err)
		}
		return cfg, nil
	}
	cfg, err := config.LoadDefaultConfig(ctx, opts...)
	if err != nil {
		return aws.Config{}, fmt.Errorf("cloudwatch logs: load aws config: %w", err)
	}
	return cfg, nil
}

// InitCloudWatch 从环境变量初始化 CloudWatch Logs（与 Gin / logger 共用输出链）。
// CLOUDWATCH_LOG_ENABLED=true 时启用；需 logs:PutLogEvents、CreateLogStream 等权限。
// 凭证：优先标准链（如 AWS_ACCESS_KEY_ID / 实例角色）；若未设置 AWS_ACCESS_KEY_ID 且已配置
// RAW_LOG_S3_ACCESS_KEY_ID / RAW_LOG_S3_SECRET_ACCESS_KEY，则与 S3 原始日志共用同一套 Key。
// 区域：CLOUDWATCH_LOG_REGION → RAW_LOG_S3_REGION（与 S3 同区，如新加坡 ap-southeast-1）→ AWS_REGION。
func InitCloudWatch() error {
	if os.Getenv("CLOUDWATCH_LOG_ENABLED") != "true" {
		return nil
	}
	group := os.Getenv("CLOUDWATCH_LOG_GROUP")
	if group == "" {
		return fmt.Errorf("CLOUDWATCH_LOG_ENABLED is true but CLOUDWATCH_LOG_GROUP is empty")
	}
	stream := os.Getenv("CLOUDWATCH_LOG_STREAM")
	if stream == "" {
		host, _ := os.Hostname()
		if host == "" {
			host = "unknown"
		}
		stream = fmt.Sprintf("%s-%d", host, os.Getpid())
	}
	stripANSI := os.Getenv("CLOUDWATCH_STRIP_ANSI") != "false"

	ctx := context.Background()
	cfg, err := loadAWSConfigForCloudWatch(ctx)
	if err != nil {
		return err
	}
	client := cloudwatchlogs.NewFromConfig(cfg)

	if os.Getenv("CLOUDWATCH_CREATE_LOG_GROUP") == "true" {
		_, err = client.CreateLogGroup(ctx, &cloudwatchlogs.CreateLogGroupInput{
			LogGroupName: aws.String(group),
		})
		if err != nil && !isAlreadyExists(err) {
			return fmt.Errorf("cloudwatch logs: create log group: %w", err)
		}
	}

	_, err = client.CreateLogStream(ctx, &cloudwatchlogs.CreateLogStreamInput{
		LogGroupName:  aws.String(group),
		LogStreamName: aws.String(stream),
	})
	if err != nil && !isAlreadyExists(err) {
		return fmt.Errorf("cloudwatch logs: create log stream: %w", err)
	}

	token, err := fetchUploadSequenceToken(ctx, client, group, stream)
	if err != nil {
		return err
	}

	sink := &cwSink{
		client:        client,
		group:         group,
		stream:        stream,
		stripANSI:     stripANSI,
		chunkCh:       make(chan []byte, cwChunkChanCap),
		stopCh:        make(chan struct{}),
		sequenceToken: token,
	}
	sink.wg.Add(1)
	go sink.run()
	cloudWatchSink = sink
	return nil
}

func fetchUploadSequenceToken(ctx context.Context, client *cloudwatchlogs.Client, group, stream string) (*string, error) {
	out, err := client.DescribeLogStreams(ctx, &cloudwatchlogs.DescribeLogStreamsInput{
		LogGroupName:        aws.String(group),
		LogStreamNamePrefix: aws.String(stream),
		Limit:               aws.Int32(50),
	})
	if err != nil {
		return nil, fmt.Errorf("cloudwatch logs: describe log streams: %w", err)
	}
	for _, ls := range out.LogStreams {
		if ls.LogStreamName != nil && *ls.LogStreamName == stream {
			return ls.UploadSequenceToken, nil
		}
	}
	return nil, nil
}

func isAlreadyExists(err error) bool {
	var re *types.ResourceAlreadyExistsException
	return errors.As(err, &re)
}

func (s *cwSink) Write(p []byte) (int, error) {
	if len(p) == 0 {
		return 0, nil
	}
	buf := make([]byte, len(p))
	copy(buf, p)
	select {
	case s.chunkCh <- buf:
	default:
		// channel 满时丢弃，避免阻塞 HTTP 请求 goroutine
	}
	return len(p), nil
}

func (s *cwSink) run() {
	defer s.wg.Done()
	var lineBuf bytes.Buffer
	var batch []types.InputLogEvent
	var batchBytes int
	lastTs := int64(0)

	flush := func() {
		if len(batch) == 0 {
			return
		}
		toSend := make([]types.InputLogEvent, len(batch))
		copy(toSend, batch)
		s.putBatch(toSend)
		batch = batch[:0]
		batchBytes = 0
	}

	flushMs := 200
	if v := os.Getenv("CLOUDWATCH_FLUSH_MS"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 50 {
			flushMs = n
		}
	}
	ticker := time.NewTicker(time.Duration(flushMs) * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case <-s.stopCh:
			for {
				select {
				case chunk := <-s.chunkCh:
					lineBuf.Write(chunk)
					s.drainLines(&lineBuf, &batch, &batchBytes, &lastTs, flush)
				default:
					goto stopped
				}
			}
		stopped:
			s.flushTailLine(&lineBuf, &batch, &batchBytes, &lastTs)
			flush()
			return
		case chunk := <-s.chunkCh:
			lineBuf.Write(chunk)
			s.drainLines(&lineBuf, &batch, &batchBytes, &lastTs, flush)
			if len(batch) >= cwMaxEventsPerBatch || batchBytes >= cwMaxBatchBytes {
				flush()
			}
		case <-ticker.C:
			flush()
		}
	}
}

func (s *cwSink) flushTailLine(lineBuf *bytes.Buffer, batch *[]types.InputLogEvent, batchBytes *int, lastTs *int64) {
	if lineBuf.Len() == 0 {
		return
	}
	line := lineBuf.String()
	lineBuf.Reset()
	if line == "" {
		return
	}
	if s.stripANSI {
		line = ansiRegexp.ReplaceAllString(line, "")
	}
	if len(line) > cwMaxMessageLen {
		line = line[:cwMaxMessageLen]
	}
	ts := time.Now().UnixMilli()
	if ts <= *lastTs {
		ts = *lastTs + 1
	}
	*lastTs = ts
	*batch = append(*batch, types.InputLogEvent{
		Message:   aws.String(line),
		Timestamp: aws.Int64(ts),
	})
	*batchBytes += len(line) + 16
}

func (s *cwSink) drainLines(lineBuf *bytes.Buffer, batch *[]types.InputLogEvent, batchBytes *int, lastTs *int64, flush func()) {
	for {
		data := lineBuf.Bytes()
		idx := bytes.IndexByte(data, '\n')
		if idx < 0 {
			break
		}
		line := string(data[:idx])
		lineBuf.Next(idx + 1)
		if line == "" {
			continue
		}
		if s.stripANSI {
			line = ansiRegexp.ReplaceAllString(line, "")
		}
		if len(line) > cwMaxMessageLen {
			line = line[:cwMaxMessageLen]
		}
		ts := time.Now().UnixMilli()
		if ts <= *lastTs {
			ts = *lastTs + 1
		}
		*lastTs = ts
		*batch = append(*batch, types.InputLogEvent{
			Message:   aws.String(line),
			Timestamp: aws.Int64(ts),
		})
		*batchBytes += len(line) + 16
	}
}

func (s *cwSink) putBatch(events []types.InputLogEvent) {
	if len(events) == 0 {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 25*time.Second)
	defer cancel()

	const maxAttempts = 5
	for attempt := 0; attempt < maxAttempts; attempt++ {
		s.mu.Lock()
		token := s.sequenceToken
		s.mu.Unlock()

		out, err := s.client.PutLogEvents(ctx, &cloudwatchlogs.PutLogEventsInput{
			LogGroupName:  aws.String(s.group),
			LogStreamName: aws.String(s.stream),
			LogEvents:     events,
			SequenceToken: token,
		})
		if err == nil {
			if out.NextSequenceToken != nil {
				s.mu.Lock()
				s.sequenceToken = out.NextSequenceToken
				s.mu.Unlock()
			}
			return
		}

		var seq *types.InvalidSequenceTokenException
		if errors.As(err, &seq) {
			if seq.ExpectedSequenceToken != nil {
				s.mu.Lock()
				s.sequenceToken = seq.ExpectedSequenceToken
				s.mu.Unlock()
			}
			time.Sleep(time.Duration(attempt+1) * 100 * time.Millisecond)
			continue
		}

		fmt.Fprintf(os.Stderr, "cloudwatch PutLogEvents failed: %v\n", err)
		return
	}
	fmt.Fprintf(os.Stderr, "cloudwatch PutLogEvents failed after %d attempts (sequence token), dropping %d events\n", maxAttempts, len(events))
}

var cloudWatchShutdownOnce sync.Once

// ShutdownCloudWatch 刷新并停止后台 goroutine（进程退出前应调用）。
func ShutdownCloudWatch() {
	cloudWatchShutdownOnce.Do(func() {
		if cloudWatchSink == nil {
			return
		}
		close(cloudWatchSink.stopCh)
		cloudWatchSink.wg.Wait()
		cloudWatchSink = nil
	})
}
