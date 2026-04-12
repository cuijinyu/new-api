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
	relaycommon "github.com/QuantumNous/new-api/relay/common"

	"github.com/aws/aws-sdk-go-v2/aws"
	v4 "github.com/aws/aws-sdk-go-v2/aws/signer/v4"
)

// BillingRetryPayload contains the minimal information needed to retry a failed
// PostConsumeQuota call. Written to S3 as NDJSON so it survives DB outages.
type BillingRetryPayload struct {
	RequestID  string `json:"request_id"`
	CreatedAt  int64  `json:"created_at"`
	UserID     int    `json:"user_id"`
	TokenID    int    `json:"token_id"`
	TokenKey   string `json:"token_key"`
	ChannelID  int    `json:"channel_id"`
	QuotaDelta int    `json:"quota_delta"`
	Playground bool   `json:"playground,omitempty"`
	Reason     string `json:"reason"`
	Error      string `json:"error"`
	RetryCount int    `json:"retry_count,omitempty"`
}

type billingRetryUploader struct {
	enabled        bool
	bucket         string
	prefix         string
	region         string
	endpoint       string
	retries        int
	credentials    aws.Credentials
	signer         *v4.Signer
	httpClient     *http.Client
	queue          chan []byte
	stopCh         chan struct{}
	wg             sync.WaitGroup
	dropCount      atomic.Int64
	totalCount     atomic.Int64
	uploadFailures atomic.Int64
}

var (
	billingRetryOnce sync.Once
	billingRetryInst *billingRetryUploader
)

func getBillingRetryUploader() *billingRetryUploader {
	billingRetryOnce.Do(func() {
		billingRetryInst = initBillingRetryUploader()
	})
	return billingRetryInst
}

func initBillingRetryUploader() *billingRetryUploader {
	if !common.GetEnvOrDefaultBool("RAW_LOG_S3_ENABLED", false) {
		return &billingRetryUploader{enabled: false}
	}
	if !common.GetEnvOrDefaultBool("BILLING_RETRY_S3_ENABLED", true) {
		return &billingRetryUploader{enabled: false}
	}

	bucket := common.GetEnvOrDefaultString("RAW_LOG_S3_BUCKET", "")
	region := common.GetEnvOrDefaultString("RAW_LOG_S3_REGION", "")
	accessKey := common.GetEnvOrDefaultString("RAW_LOG_S3_ACCESS_KEY_ID", "")
	secretKey := common.GetEnvOrDefaultString("RAW_LOG_S3_SECRET_ACCESS_KEY", "")
	sessionToken := common.GetEnvOrDefaultString("RAW_LOG_S3_SESSION_TOKEN", "")
	endpoint := common.GetEnvOrDefaultString("RAW_LOG_S3_ENDPOINT", "")
	if bucket == "" || region == "" || accessKey == "" || secretKey == "" {
		return &billingRetryUploader{enabled: false}
	}

	prefix := common.GetEnvOrDefaultString("BILLING_RETRY_S3_PREFIX", "billing-retries")
	retries := common.GetEnvOrDefault("BILLING_RETRY_S3_RETRIES", 3)
	if retries < 0 {
		retries = 0
	}
	queueSize := common.GetEnvOrDefault("BILLING_RETRY_S3_QUEUE_SIZE", 1000)

	u := &billingRetryUploader{
		enabled:     true,
		bucket:      bucket,
		prefix:      prefix,
		region:      region,
		endpoint:    endpoint,
		retries:     retries,
		credentials: aws.Credentials{AccessKeyID: accessKey, SecretAccessKey: secretKey, SessionToken: sessionToken},
		signer:      v4.NewSigner(),
		httpClient:  GetHttpClient(),
		queue:       make(chan []byte, queueSize),
		stopCh:      make(chan struct{}),
	}

	u.wg.Add(1)
	go u.worker()

	common.SysLog(fmt.Sprintf("billing retry s3 uploader enabled, region=%s, bucket=%s, prefix=%s, queue=%d",
		region, bucket, prefix, queueSize))
	return u
}

// worker writes each retry record individually to S3 (one object per record)
// so the retry processor can handle them independently.
func (u *billingRetryUploader) worker() {
	defer u.wg.Done()
	for {
		select {
		case data, ok := <-u.queue:
			if !ok {
				return
			}
			u.uploadOne(data)
		case <-u.stopCh:
			for {
				select {
				case data := <-u.queue:
					u.uploadOne(data)
				default:
					return
				}
			}
		}
	}
}

func (u *billingRetryUploader) uploadOne(data []byte) {
	var buf bytes.Buffer
	gw, err := gzip.NewWriterLevel(&buf, gzip.BestSpeed)
	if err != nil {
		common.SysError(fmt.Sprintf("billing retry gzip error: %s", err.Error()))
		return
	}
	_, _ = gw.Write(data)
	if err = gw.Close(); err != nil {
		common.SysError(fmt.Sprintf("billing retry gzip close error: %s", err.Error()))
		return
	}

	now := time.Now()
	keyPrefix := path.Join(u.prefix, "pending", now.Format("2006/01/02/15"))
	objectKey := path.Join(keyPrefix, fmt.Sprintf("%d.json.gz", now.UnixNano()))

	var lastErr error
	for attempt := 0; attempt <= u.retries; attempt++ {
		if attempt > 0 {
			time.Sleep(time.Duration(attempt) * time.Second)
		}
		lastErr = s3Upload(u.httpClient, u.signer, u.credentials, u.endpoint, u.bucket, u.region, objectKey, buf.Bytes())
		if lastErr == nil {
			return
		}
	}
	u.uploadFailures.Add(1)
	common.SysError(fmt.Sprintf("billing retry upload failed after %d attempts: %s (key=%s)", u.retries+1, lastErr.Error(), objectKey))
}

func (u *billingRetryUploader) enqueue(data []byte) {
	u.totalCount.Add(1)
	select {
	case u.queue <- data:
	default:
		u.dropCount.Add(1)
		common.SysError("billing retry queue full, dropping record")
	}
}

func (u *billingRetryUploader) Shutdown() {
	if !u.enabled {
		return
	}
	close(u.stopCh)
	u.wg.Wait()
}

// EnqueueBillingRetry persists a failed PostConsumeQuota call to S3 for later retry.
// requestID should be passed from the gin context (common.RequestIdKey).
func EnqueueBillingRetry(relayInfo *relaycommon.RelayInfo, quotaDelta int, requestID string, reason string, retryErr error) {
	u := getBillingRetryUploader()
	if !u.enabled {
		return
	}

	payload := BillingRetryPayload{
		RequestID:  requestID,
		CreatedAt:  time.Now().Unix(),
		UserID:     relayInfo.UserId,
		TokenID:    relayInfo.TokenId,
		TokenKey:   relayInfo.TokenKey,
		ChannelID:  relayInfo.ChannelId,
		QuotaDelta: quotaDelta,
		Playground: relayInfo.IsPlayground,
		Reason:     reason,
		Error:      retryErr.Error(),
	}

	data, err := json.Marshal(payload)
	if err != nil {
		common.SysError(fmt.Sprintf("billing retry marshal error: %s", err.Error()))
		return
	}
	u.enqueue(data)
}

// BillingRetryS3Enabled returns true if the billing retry S3 uploader is active.
func BillingRetryS3Enabled() bool {
	return getBillingRetryUploader().enabled
}

// SwapBillingRetryUploaderStats atomically reads and resets the drop/upload-failure
// counters, returning the values accumulated since the last call.
func SwapBillingRetryUploaderStats() (dropped, uploadFailed int64) {
	u := getBillingRetryUploader()
	if !u.enabled {
		return 0, 0
	}
	return u.dropCount.Swap(0), u.uploadFailures.Swap(0)
}

// ShutdownBillingRetryUploader drains the queue and waits for the worker to finish.
func ShutdownBillingRetryUploader() {
	getBillingRetryUploader().Shutdown()
}
