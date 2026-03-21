package service

import (
	"bytes"
	"compress/gzip"
	"encoding/json"
	"fmt"
	"net/http"
	"path"
	"sync"
	"sync/atomic"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/logger"

	"github.com/aws/aws-sdk-go-v2/aws"
	v4 "github.com/aws/aws-sdk-go-v2/aws/signer/v4"
	"github.com/gin-gonic/gin"
)

type UsageLogPayload struct {
	RequestID        string                 `json:"request_id,omitempty"`
	CreatedAt        int64                  `json:"created_at"`
	UserID           int                    `json:"user_id"`
	Username         string                 `json:"username"`
	ChannelID        int                    `json:"channel_id"`
	ModelName        string                 `json:"model_name"`
	TokenName        string                 `json:"token_name"`
	TokenID          int                    `json:"token_id"`
	Group            string                 `json:"group,omitempty"`
	PromptTokens     int                    `json:"prompt_tokens"`
	CompletionTokens int                    `json:"completion_tokens"`
	Quota            int                    `json:"quota"`
	Content          string                 `json:"content,omitempty"`
	UseTimeSeconds   int                    `json:"use_time_seconds"`
	IsStream         bool                   `json:"is_stream"`
	Ip               string                 `json:"ip,omitempty"`
	Other            map[string]interface{} `json:"other,omitempty"`
}

type usageLogUploader struct {
	enabled        bool
	bucket         string
	prefix         string
	region         string
	endpoint       string
	retries        int
	batchSize      int
	batchBytes     int
	flushSec       int
	enqueueTimeout time.Duration

	credentials aws.Credentials
	signer      *v4.Signer
	httpClient  *http.Client
	queue       chan []byte
	stopCh      chan struct{}
	wg          sync.WaitGroup

	dropCount  atomic.Int64
	totalCount atomic.Int64
}

var (
	usageLogOnce sync.Once
	usageLogInst *usageLogUploader
)

func getUsageLogUploader() *usageLogUploader {
	usageLogOnce.Do(func() {
		usageLogInst = initUsageLogUploader()
	})
	return usageLogInst
}

func initUsageLogUploader() *usageLogUploader {
	if !common.GetEnvOrDefaultBool("RAW_LOG_S3_ENABLED", false) {
		return &usageLogUploader{enabled: false}
	}
	if !common.GetEnvOrDefaultBool("USAGE_LOG_S3_ENABLED", true) {
		return &usageLogUploader{enabled: false}
	}

	bucket := common.GetEnvOrDefaultString("RAW_LOG_S3_BUCKET", "")
	region := common.GetEnvOrDefaultString("RAW_LOG_S3_REGION", "")
	prefix := common.GetEnvOrDefaultString("USAGE_LOG_S3_PREFIX", "llm-usage-logs")
	accessKey := common.GetEnvOrDefaultString("RAW_LOG_S3_ACCESS_KEY_ID", "")
	secretKey := common.GetEnvOrDefaultString("RAW_LOG_S3_SECRET_ACCESS_KEY", "")
	sessionToken := common.GetEnvOrDefaultString("RAW_LOG_S3_SESSION_TOKEN", "")
	endpoint := common.GetEnvOrDefaultString("RAW_LOG_S3_ENDPOINT", "")
	if bucket == "" || region == "" || accessKey == "" || secretKey == "" {
		return &usageLogUploader{enabled: false}
	}

	retries := common.GetEnvOrDefault("USAGE_LOG_S3_RETRIES", 2)
	if retries < 0 {
		retries = 0
	}
	batchSize := common.GetEnvOrDefault("USAGE_LOG_S3_BATCH_SIZE", 500)
	if batchSize < 1 {
		batchSize = 1
	}
	batchBytes := common.GetEnvOrDefault("USAGE_LOG_S3_BATCH_BYTES", 2*1024*1024)
	if batchBytes < 1 {
		batchBytes = 2 * 1024 * 1024
	}
	flushSec := common.GetEnvOrDefault("USAGE_LOG_S3_FLUSH_INTERVAL", 15)
	if flushSec < 1 {
		flushSec = 1
	}
	enqueueTimeoutSec := common.GetEnvOrDefault("USAGE_LOG_S3_ENQUEUE_TIMEOUT", 5)
	if enqueueTimeoutSec < 0 {
		enqueueTimeoutSec = 0
	}
	queueSize := common.GetEnvOrDefault("USAGE_LOG_S3_QUEUE_SIZE", 50000)

	u := &usageLogUploader{
		enabled:        true,
		bucket:         bucket,
		prefix:         prefix,
		region:         region,
		endpoint:       endpoint,
		retries:        retries,
		batchSize:      batchSize,
		batchBytes:     batchBytes,
		flushSec:       flushSec,
		enqueueTimeout: time.Duration(enqueueTimeoutSec) * time.Second,
		credentials:    aws.Credentials{AccessKeyID: accessKey, SecretAccessKey: secretKey, SessionToken: sessionToken},
		signer:         v4.NewSigner(),
		httpClient:     GetHttpClient(),
		queue:          make(chan []byte, queueSize),
		stopCh:         make(chan struct{}),
	}

	workerNum := common.GetEnvOrDefault("USAGE_LOG_S3_WORKERS", 2)
	if workerNum < 1 {
		workerNum = 1
	}
	for i := 0; i < workerNum; i++ {
		u.wg.Add(1)
		go u.batchWorker()
	}
	go u.reportDropStats()

	common.SysLog(fmt.Sprintf("usage log s3 uploader enabled, region=%s, bucket=%s, prefix=%s, batch=%d, flush=%ds, workers=%d, queue=%d",
		region, bucket, prefix, batchSize, flushSec, workerNum, queueSize))
	return u
}

func (u *usageLogUploader) batchWorker() {
	defer u.wg.Done()

	ticker := time.NewTicker(time.Duration(u.flushSec) * time.Second)
	defer ticker.Stop()

	batch := make([][]byte, 0, u.batchSize)
	batchLen := 0

	flush := func() {
		if len(batch) == 0 {
			return
		}
		if err := u.flushBatch(batch); err != nil {
			common.SysError(fmt.Sprintf("failed to flush %d usage logs to s3: %s", len(batch), err.Error()))
		}
		batch = make([][]byte, 0, u.batchSize)
		batchLen = 0
	}

	for {
		select {
		case line, ok := <-u.queue:
			if !ok {
				flush()
				return
			}
			batch = append(batch, line)
			batchLen += len(line)
			if len(batch) >= u.batchSize || batchLen >= u.batchBytes {
				flush()
			}
		case <-ticker.C:
			flush()
		case <-u.stopCh:
			for {
				select {
				case line := <-u.queue:
					batch = append(batch, line)
					batchLen += len(line)
					if len(batch) >= u.batchSize || batchLen >= u.batchBytes {
						flush()
					}
				default:
					flush()
					return
				}
			}
		}
	}
}

func (u *usageLogUploader) flushBatch(batch [][]byte) error {
	var buf bytes.Buffer
	gw, err := gzip.NewWriterLevel(&buf, gzip.BestSpeed)
	if err != nil {
		return fmt.Errorf("gzip writer: %w", err)
	}
	for i, line := range batch {
		if i > 0 {
			_, _ = gw.Write([]byte("\n"))
		}
		_, _ = gw.Write(line)
	}
	if err = gw.Close(); err != nil {
		return fmt.Errorf("gzip close: %w", err)
	}

	keyPrefix := time.Now().Format("2006/01/02/15")
	if u.prefix != "" {
		keyPrefix = path.Join(u.prefix, keyPrefix)
	}
	objectKey := path.Join(keyPrefix, fmt.Sprintf("%d-%d.ndjson.gz", time.Now().UnixNano(), len(batch)))

	return u.uploadWithRetry(objectKey, buf.Bytes())
}

func (u *usageLogUploader) uploadWithRetry(key string, body []byte) error {
	var lastErr error
	for attempt := 0; attempt <= u.retries; attempt++ {
		if attempt > 0 {
			time.Sleep(time.Duration(attempt) * 500 * time.Millisecond)
		}
		lastErr = s3Upload(u.httpClient, u.signer, u.credentials, u.endpoint, u.bucket, u.region, key, body)
		if lastErr == nil {
			return nil
		}
	}
	return lastErr
}

func (u *usageLogUploader) enqueue(c *gin.Context, data []byte) {
	u.totalCount.Add(1)

	select {
	case u.queue <- data:
		return
	default:
	}

	if u.enqueueTimeout <= 0 {
		u.dropCount.Add(1)
		logger.LogWarn(c, "usage log s3 queue full, drop current usage log")
		return
	}

	timer := time.NewTimer(u.enqueueTimeout)
	defer timer.Stop()
	select {
	case u.queue <- data:
	case <-timer.C:
		u.dropCount.Add(1)
		logger.LogWarn(c, fmt.Sprintf("usage log s3 queue full after %s timeout, drop current usage log", u.enqueueTimeout))
	}
}

func (u *usageLogUploader) reportDropStats() {
	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ticker.C:
			dropped := u.dropCount.Load()
			total := u.totalCount.Load()
			if dropped > 0 {
				common.SysError(fmt.Sprintf("usage log s3: dropped %d/%d logs (%.1f%%) in last period, queue_len=%d/%d",
					dropped, total, float64(dropped)/float64(max(total, 1))*100,
					len(u.queue), cap(u.queue)))
				u.dropCount.Store(0)
				u.totalCount.Store(0)
			}
		case <-u.stopCh:
			return
		}
	}
}

func (u *usageLogUploader) Shutdown() {
	if !u.enabled {
		return
	}
	close(u.stopCh)
	u.wg.Wait()
}

// EnqueueUsageLog serializes a usage log payload and enqueues it for async S3 upload.
func EnqueueUsageLog(c *gin.Context, payload UsageLogPayload) {
	u := getUsageLogUploader()
	if !u.enabled {
		return
	}
	data, err := json.Marshal(payload)
	if err != nil {
		logger.LogError(c, "failed to marshal usage log payload: "+err.Error())
		return
	}
	u.enqueue(c, data)
}

// UsageLogS3Enabled returns true if the usage log S3 uploader is active.
func UsageLogS3Enabled() bool {
	return getUsageLogUploader().enabled
}

// ShutdownUsageLogUploader drains the queue and waits for all workers to finish.
func ShutdownUsageLogUploader() {
	u := getUsageLogUploader()
	u.Shutdown()
}

// ShutdownRawLogUploader drains the raw log queue and waits for all workers to finish.
func ShutdownRawLogUploader() {
	u := getRawLogUploader()
	u.Shutdown()
}

// ShutdownErrorLogUploader drains the error log queue and waits for all workers to finish.
func ShutdownErrorLogUploader() {
	u := getErrorLogUploader()
	u.Shutdown()
}
