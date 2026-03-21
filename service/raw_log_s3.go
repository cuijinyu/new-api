package service

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"path"
	"strings"
	"sync"
	"sync/atomic"
	"time"
	"unicode/utf8"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/logger"
	relaycommon "github.com/QuantumNous/new-api/relay/common"

	"github.com/aws/aws-sdk-go-v2/aws"
	v4 "github.com/aws/aws-sdk-go-v2/aws/signer/v4"
	"github.com/gin-gonic/gin"
)

var sensitiveHeaders = []string{
	"authorization", "api-key", "x-api-key", "proxy-authorization",
}

type rawLogUploader struct {
	enabled         bool
	bucket          string
	prefix          string
	region          string
	endpoint        string
	maxBytes        int
	retries         int
	batchSize       int
	batchBytes      int
	flushSec        int
	enqueueTimeout  time.Duration

	credentials aws.Credentials
	signer      *v4.Signer
	httpClient  *http.Client
	queue       chan []byte
	stopCh      chan struct{}
	wg          sync.WaitGroup

	dropCount  atomic.Int64
	totalCount atomic.Int64
}

type rawLogPayload struct {
	RequestID      string      `json:"request_id"`
	CreatedAt      string      `json:"created_at"`
	Method         string      `json:"method"`
	Path           string      `json:"path"`
	URL            string      `json:"url"`
	RelayMode      string      `json:"relay_mode,omitempty"`
	Model          string      `json:"model,omitempty"`
	ChannelID      int         `json:"channel_id,omitempty"`
	ChannelName    string      `json:"channel_name,omitempty"`
	ChannelType    int         `json:"channel_type,omitempty"`
	UserID         int         `json:"user_id,omitempty"`
	RequestHeaders http.Header `json:"request_headers,omitempty"`
	RequestBody    string      `json:"request_body,omitempty"`
	StatusCode     int         `json:"status_code"`
	ResponseBody   string      `json:"response_body,omitempty"`
	ResponseError  string      `json:"response_error,omitempty"`
}

var (
	rawLogOnce sync.Once
	rawLogInst *rawLogUploader

	errorLogOnce sync.Once
	errorLogInst *rawLogUploader
)

func getRawLogUploader() *rawLogUploader {
	rawLogOnce.Do(func() {
		rawLogInst = initRawLogUploader()
	})
	return rawLogInst
}

func getErrorLogUploader() *rawLogUploader {
	errorLogOnce.Do(func() {
		errorLogInst = initErrorLogUploader()
	})
	return errorLogInst
}

type rawLogS3Config struct {
	bucket       string
	region       string
	endpoint     string
	accessKey    string
	secretKey    string
	sessionToken string
}

func loadRawLogS3Config() (rawLogS3Config, bool) {
	if !common.GetEnvOrDefaultBool("RAW_LOG_S3_ENABLED", false) {
		return rawLogS3Config{}, false
	}
	cfg := rawLogS3Config{
		bucket:       common.GetEnvOrDefaultString("RAW_LOG_S3_BUCKET", ""),
		region:       common.GetEnvOrDefaultString("RAW_LOG_S3_REGION", ""),
		endpoint:     common.GetEnvOrDefaultString("RAW_LOG_S3_ENDPOINT", ""),
		accessKey:    common.GetEnvOrDefaultString("RAW_LOG_S3_ACCESS_KEY_ID", ""),
		secretKey:    common.GetEnvOrDefaultString("RAW_LOG_S3_SECRET_ACCESS_KEY", ""),
		sessionToken: common.GetEnvOrDefaultString("RAW_LOG_S3_SESSION_TOKEN", ""),
	}
	if cfg.bucket == "" || cfg.region == "" || cfg.accessKey == "" || cfg.secretKey == "" {
		return rawLogS3Config{}, false
	}
	return cfg, true
}

func initRawLogUploader() *rawLogUploader {
	cfg, ok := loadRawLogS3Config()
	if !ok {
		common.SysError("raw log s3 enabled but config missing, disable uploader")
		return &rawLogUploader{enabled: false}
	}
	prefix := common.GetEnvOrDefaultString("RAW_LOG_S3_PREFIX", "llm-raw-logs")
	maxBytes := common.GetEnvOrDefault("RAW_LOG_S3_MAX_BYTES", 1024*1024)
	if maxBytes <= 0 {
		maxBytes = 1024 * 1024
	}
	retries := common.GetEnvOrDefault("RAW_LOG_S3_RETRIES", 2)
	if retries < 0 {
		retries = 0
	}
	batchSize := common.GetEnvOrDefault("RAW_LOG_S3_BATCH_SIZE", 10000)
	if batchSize < 1 {
		batchSize = 1
	}
	batchBytes := common.GetEnvOrDefault("RAW_LOG_S3_BATCH_BYTES", 200*1024*1024)
	if batchBytes < 1 {
		batchBytes = 200 * 1024 * 1024
	}
	flushSec := common.GetEnvOrDefault("RAW_LOG_S3_FLUSH_INTERVAL", 120)
	if flushSec < 1 {
		flushSec = 1
	}
	enqueueTimeoutSec := common.GetEnvOrDefault("RAW_LOG_S3_ENQUEUE_TIMEOUT", 5)
	if enqueueTimeoutSec < 0 {
		enqueueTimeoutSec = 0
	}

	u := &rawLogUploader{
		enabled:        true,
		bucket:         cfg.bucket,
		prefix:         prefix,
		region:         cfg.region,
		endpoint:       cfg.endpoint,
		maxBytes:       maxBytes,
		retries:        retries,
		batchSize:      batchSize,
		batchBytes:     batchBytes,
		flushSec:       flushSec,
		enqueueTimeout: time.Duration(enqueueTimeoutSec) * time.Second,
		credentials:    aws.Credentials{AccessKeyID: cfg.accessKey, SecretAccessKey: cfg.secretKey, SessionToken: cfg.sessionToken},
		signer:         v4.NewSigner(),
		httpClient:     GetHttpClient(),
		queue:          make(chan []byte, common.GetEnvOrDefault("RAW_LOG_S3_QUEUE_SIZE", 50000)),
		stopCh:         make(chan struct{}),
	}
	workerNum := common.GetEnvOrDefault("RAW_LOG_S3_WORKERS", 4)
	if workerNum < 1 {
		workerNum = 1
	}
	for i := 0; i < workerNum; i++ {
		u.wg.Add(1)
		go u.batchWorker()
	}
	go u.reportDropStats()
	common.SysLog(fmt.Sprintf("raw log s3 uploader enabled, region=%s, bucket=%s, batch=%d, flush=%ds, workers=%d, queue=%d, enqueue_timeout=%ds, gzip=on",
		cfg.region, cfg.bucket, batchSize, flushSec, workerNum, cap(u.queue), enqueueTimeoutSec))
	return u
}

func initErrorLogUploader() *rawLogUploader {
	cfg, ok := loadRawLogS3Config()
	if !ok {
		return &rawLogUploader{enabled: false}
	}
	if !common.GetEnvOrDefaultBool("ERROR_LOG_S3_ENABLED", true) {
		return &rawLogUploader{enabled: false}
	}
	prefix := common.GetEnvOrDefaultString("ERROR_LOG_S3_PREFIX", "llm-error-logs")
	maxBytes := common.GetEnvOrDefault("RAW_LOG_S3_MAX_BYTES", 1024*1024)
	if maxBytes <= 0 {
		maxBytes = 1024 * 1024
	}
	retries := common.GetEnvOrDefault("ERROR_LOG_S3_RETRIES", 2)
	if retries < 0 {
		retries = 0
	}
	batchSize := common.GetEnvOrDefault("ERROR_LOG_S3_BATCH_SIZE", 5000)
	if batchSize < 1 {
		batchSize = 1
	}
	batchBytes := common.GetEnvOrDefault("ERROR_LOG_S3_BATCH_BYTES", 100*1024*1024)
	if batchBytes < 1 {
		batchBytes = 100 * 1024 * 1024
	}
	flushSec := common.GetEnvOrDefault("ERROR_LOG_S3_FLUSH_INTERVAL", 120)
	if flushSec < 1 {
		flushSec = 1
	}
	enqueueTimeoutSec := common.GetEnvOrDefault("ERROR_LOG_S3_ENQUEUE_TIMEOUT", 5)
	if enqueueTimeoutSec < 0 {
		enqueueTimeoutSec = 0
	}
	queueSize := common.GetEnvOrDefault("ERROR_LOG_S3_QUEUE_SIZE", 20000)

	u := &rawLogUploader{
		enabled:        true,
		bucket:         cfg.bucket,
		prefix:         prefix,
		region:         cfg.region,
		endpoint:       cfg.endpoint,
		maxBytes:       maxBytes,
		retries:        retries,
		batchSize:      batchSize,
		batchBytes:     batchBytes,
		flushSec:       flushSec,
		enqueueTimeout: time.Duration(enqueueTimeoutSec) * time.Second,
		credentials:    aws.Credentials{AccessKeyID: cfg.accessKey, SecretAccessKey: cfg.secretKey, SessionToken: cfg.sessionToken},
		signer:         v4.NewSigner(),
		httpClient:     GetHttpClient(),
		queue:          make(chan []byte, queueSize),
		stopCh:         make(chan struct{}),
	}
	workerNum := common.GetEnvOrDefault("ERROR_LOG_S3_WORKERS", 2)
	if workerNum < 1 {
		workerNum = 1
	}
	for i := 0; i < workerNum; i++ {
		u.wg.Add(1)
		go u.batchWorker()
	}
	go u.reportDropStats()
	common.SysLog(fmt.Sprintf("error log s3 uploader enabled, region=%s, bucket=%s, prefix=%s, batch=%d, flush=%ds, workers=%d, queue=%d",
		cfg.region, cfg.bucket, prefix, batchSize, flushSec, workerNum, queueSize))
	return u
}

func (u *rawLogUploader) batchWorker() {
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
			common.SysError(fmt.Sprintf("failed to flush %d raw logs to s3: %s", len(batch), err.Error()))
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

func (u *rawLogUploader) flushBatch(batch [][]byte) error {
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

func (u *rawLogUploader) enqueue(c *gin.Context, data []byte) {
	u.totalCount.Add(1)

	// 先尝试非阻塞写入
	select {
	case u.queue <- data:
		return
	default:
	}

	// 队列满，带超时等待
	if u.enqueueTimeout <= 0 {
		u.dropCount.Add(1)
		logger.LogWarn(c, "raw log s3 queue full, drop current raw log")
		return
	}

	timer := time.NewTimer(u.enqueueTimeout)
	defer timer.Stop()
	select {
	case u.queue <- data:
	case <-timer.C:
		u.dropCount.Add(1)
		logger.LogWarn(c, fmt.Sprintf("raw log s3 queue full after %s timeout, drop current raw log", u.enqueueTimeout))
	}
}

func (u *rawLogUploader) reportDropStats() {
	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ticker.C:
			dropped := u.dropCount.Load()
			total := u.totalCount.Load()
			if dropped > 0 {
				common.SysError(fmt.Sprintf("raw log s3: dropped %d/%d logs (%.1f%%) in last period, queue_len=%d/%d",
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

func (u *rawLogUploader) Shutdown() {
	close(u.stopCh)
	u.wg.Wait()
}

func (u *rawLogUploader) uploadWithRetry(key string, body []byte) error {
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

func s3Upload(httpClient *http.Client, signer *v4.Signer, creds aws.Credentials, endpoint, bucket, region, key string, body []byte) error {
	var url string
	if endpoint != "" {
		url = fmt.Sprintf("%s/%s/%s", strings.TrimRight(endpoint, "/"), bucket, key)
	} else {
		url = fmt.Sprintf("https://%s.s3.%s.amazonaws.com/%s", bucket, region, key)
	}
	req, err := http.NewRequest(http.MethodPut, url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/x-ndjson")
	req.Header.Set("Content-Encoding", "gzip")
	hashBytes := sha256.Sum256(body)
	payloadHash := hex.EncodeToString(hashBytes[:])
	req.Header.Set("X-Amz-Content-Sha256", payloadHash)
	if err = signer.SignHTTP(context.Background(), creds, req, payloadHash, "s3", region, time.Now()); err != nil {
		return err
	}
	resp, err := httpClient.Do(req)
	if err != nil {
		return err
	}
	defer CloseResponseBodyGracefully(resp)
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return fmt.Errorf("s3 upload failed, status=%d, body=%s", resp.StatusCode, string(b))
	}
	return nil
}

func sanitizeHeaders(h http.Header) http.Header {
	cleaned := h.Clone()
	for _, key := range sensitiveHeaders {
		for k := range cleaned {
			if strings.EqualFold(k, key) {
				cleaned.Set(k, "***")
			}
		}
	}
	return cleaned
}

func AttachRawLogCapture(c *gin.Context, info *relaycommon.RelayInfo, req *http.Request, resp *http.Response) {
	u := getRawLogUploader()
	eu := getErrorLogUploader()
	if (!u.enabled && !eu.enabled) || req == nil || resp == nil || resp.Body == nil {
		return
	}
	maxBytes := u.maxBytes
	if !u.enabled && eu.enabled {
		maxBytes = eu.maxBytes
	}
	reqBody := readRequestBody(req)
	payload := rawLogPayload{
		RequestID:      c.GetString(common.RequestIdKey),
		CreatedAt:      time.Now().Format(time.RFC3339Nano),
		Method:         req.Method,
		Path:           c.Request.URL.Path,
		URL:            req.URL.String(),
		StatusCode:     resp.StatusCode,
		RequestHeaders: sanitizeHeaders(req.Header),
		RequestBody:    truncateUTF8(string(reqBody), maxBytes),
		ChannelID:      c.GetInt("channel_id"),
		ChannelName:    c.GetString("channel_name"),
		ChannelType:    c.GetInt("channel_type"),
		UserID:         c.GetInt("id"),
	}
	if info != nil {
		payload.Model = info.OriginModelName
		payload.RelayMode = fmt.Sprintf("%d", info.RelayMode)
	}

	isError := resp.StatusCode < 200 || resp.StatusCode >= 300

	resp.Body = newCaptureReadCloser(resp.Body, maxBytes, func(captured []byte, closeErr error) {
		payload.ResponseBody = truncateUTF8(string(captured), maxBytes)
		if closeErr != nil {
			payload.ResponseError = closeErr.Error()
		}
		data, err := json.Marshal(payload)
		if err != nil {
			logger.LogError(c, "failed to marshal raw log payload: "+err.Error())
			return
		}
		if u.enabled {
			u.enqueue(c, data)
		}
		if isError && eu.enabled {
			eu.enqueue(c, data)
		}
	})
}

func readRequestBody(req *http.Request) []byte {
	if req.GetBody == nil {
		return nil
	}
	body, err := req.GetBody()
	if err != nil {
		return nil
	}
	defer body.Close()
	data, err := io.ReadAll(body)
	if err != nil {
		return nil
	}
	return data
}

func truncateUTF8(v string, maxLen int) string {
	if maxLen <= 0 || len(v) == 0 {
		return ""
	}
	if len(v) <= maxLen {
		return v
	}
	truncated := v[:maxLen]
	for len(truncated) > 0 && !utf8.ValidString(truncated) {
		truncated = truncated[:len(truncated)-1]
	}
	return truncated
}

type captureReadCloser struct {
	src     io.ReadCloser
	buf     bytes.Buffer
	maxSize int
	onClose func([]byte, error)
}

func newCaptureReadCloser(src io.ReadCloser, maxSize int, onClose func([]byte, error)) io.ReadCloser {
	if maxSize <= 0 {
		maxSize = 1
	}
	return &captureReadCloser{src: src, maxSize: maxSize, onClose: onClose}
}

func (c *captureReadCloser) Read(p []byte) (int, error) {
	n, err := c.src.Read(p)
	if n > 0 && c.buf.Len() < c.maxSize {
		left := c.maxSize - c.buf.Len()
		if n < left {
			left = n
		}
		_, _ = c.buf.Write(p[:left])
	}
	return n, err
}

func (c *captureReadCloser) Close() error {
	err := c.src.Close()
	if c.onClose != nil {
		c.onClose(c.buf.Bytes(), err)
	}
	return err
}
