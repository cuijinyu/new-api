package service

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/logger"
	"github.com/QuantumNous/new-api/model"

	"github.com/aws/aws-sdk-go-v2/aws"
	v4 "github.com/aws/aws-sdk-go-v2/aws/signer/v4"
)

const (
	billingRetryLockPrefix    = "billing_retry_lock:"
	billingRetryLockTTL       = 10 * time.Minute
	billingRetryMaxRetries    = 3
)

type billingRetryWorker struct {
	enabled     bool
	bucket      string
	prefix      string
	region      string
	endpoint    string
	credentials aws.Credentials
	signer      *v4.Signer
	httpClient  *http.Client
	interval    time.Duration
	stopCh      chan struct{}
	wg          sync.WaitGroup
}

var (
	retryWorkerOnce sync.Once
	retryWorkerInst *billingRetryWorker
)

func getBillingRetryWorker() *billingRetryWorker {
	retryWorkerOnce.Do(func() {
		retryWorkerInst = initBillingRetryWorker()
	})
	return retryWorkerInst
}

func initBillingRetryWorker() *billingRetryWorker {
	u := getBillingRetryUploader()
	if !u.enabled {
		return &billingRetryWorker{enabled: false}
	}

	intervalSec := common.GetEnvOrDefault("BILLING_RETRY_INTERVAL", 60)
	if intervalSec < 10 {
		intervalSec = 10
	}

	return &billingRetryWorker{
		enabled:     true,
		bucket:      u.bucket,
		prefix:      u.prefix,
		region:      u.region,
		endpoint:    u.endpoint,
		credentials: u.credentials,
		signer:      v4.NewSigner(),
		httpClient:  GetHttpClient(),
		interval:    time.Duration(intervalSec) * time.Second,
		stopCh:      make(chan struct{}),
	}
}

// StartBillingRetryWorker launches the background goroutine that periodically
// scans S3 for pending billing retry records and processes them.
func StartBillingRetryWorker() {
	w := getBillingRetryWorker()
	if !w.enabled {
		return
	}
	w.wg.Add(1)
	go w.run()
	common.SysLog(fmt.Sprintf("billing retry worker started, interval=%s", w.interval))
}

// StopBillingRetryWorker signals the worker to stop and waits for it to finish.
func StopBillingRetryWorker() {
	w := getBillingRetryWorker()
	if !w.enabled {
		return
	}
	close(w.stopCh)
	w.wg.Wait()
}

func (w *billingRetryWorker) run() {
	defer w.wg.Done()

	// Initial delay to let the system stabilize after startup
	select {
	case <-time.After(30 * time.Second):
	case <-w.stopCh:
		return
	}

	ticker := time.NewTicker(w.interval)
	defer ticker.Stop()

	for {
		w.processOnce()
		select {
		case <-ticker.C:
		case <-w.stopCh:
			return
		}
	}
}

func (w *billingRetryWorker) processOnce() {
	if !common.TryRunOnce("billing_retry_scan", w.interval-time.Second) {
		return
	}

	prefix := w.prefix + "/pending/"
	keys, err := w.s3List(prefix, 100)
	if err != nil {
		common.SysError(fmt.Sprintf("billing retry worker: list error: %s", err.Error()))
		return
	}
	if len(keys) == 0 {
		return
	}

	common.SysLog(fmt.Sprintf("billing retry worker: found %d pending records", len(keys)))

	succeeded := 0
	failed := 0
	skipped := 0
	for _, key := range keys {
		lockKey := billingRetryLockPrefix + key
		if !common.TryRunOnce(lockKey, billingRetryLockTTL) {
			skipped++
			continue
		}

		payload, err := w.s3Get(key)
		if err != nil {
			common.SysError(fmt.Sprintf("billing retry worker: get %s error: %s", key, err.Error()))
			_ = common.RedisDel("once:" + lockKey)
			failed++
			continue
		}

		if err := w.retryBilling(payload); err != nil {
			payload.RetryCount++
			common.SysError(fmt.Sprintf("billing retry worker: retry failed (attempt %d/%d) for user=%d quota=%d: %s",
				payload.RetryCount, billingRetryMaxRetries, payload.UserID, payload.QuotaDelta, err.Error()))
			if payload.RetryCount >= billingRetryMaxRetries {
				common.SysError(fmt.Sprintf("billing retry worker: max retries exceeded, discarding: request=%s user=%d delta=%d",
					payload.RequestID, payload.UserID, payload.QuotaDelta))
				_ = w.s3Delete(key)
			} else {
				w.rewritePending(key, payload)
			}
			_ = common.RedisDel("once:" + lockKey)
			failed++
			continue
		}

		if err := w.s3Delete(key); err != nil {
			common.SysError(fmt.Sprintf("billing retry worker: delete %s error: %s (lock held, will not re-process)", key, err.Error()))
		}
		succeeded++
	}

	if succeeded > 0 || failed > 0 || skipped > 0 {
		common.SysLog(fmt.Sprintf("billing retry worker: processed %d succeeded, %d failed, %d skipped(locked)", succeeded, failed, skipped))
	}
	if logger.MetricsEnabled() {
		logger.RecordBillingRetry(succeeded, failed)
		dropped, uploadFailed := SwapBillingRetryUploaderStats()
		if dropped > 0 || uploadFailed > 0 {
			logger.RecordBillingRetryUploader(dropped, uploadFailed)
		}
	}
}

func (w *billingRetryWorker) retryBilling(p *BillingRetryPayload) error {
	if p.QuotaDelta > 0 {
		if err := model.DecreaseUserQuota(p.UserID, p.QuotaDelta); err != nil {
			return fmt.Errorf("decrease user quota: %w", err)
		}
		if !p.Playground {
			if err := model.DecreaseTokenQuota(p.TokenID, p.TokenKey, p.QuotaDelta); err != nil {
				common.SysError(fmt.Sprintf("billing retry: user quota decreased but token quota failed (will not retry to avoid double-charge): user=%d token=%d delta=%d err=%s",
					p.UserID, p.TokenID, p.QuotaDelta, err.Error()))
			}
		}
	} else if p.QuotaDelta < 0 {
		if err := model.IncreaseUserQuota(p.UserID, -p.QuotaDelta, false); err != nil {
			return fmt.Errorf("increase user quota: %w", err)
		}
		if !p.Playground {
			if err := model.IncreaseTokenQuota(p.TokenID, p.TokenKey, -p.QuotaDelta); err != nil {
				common.SysError(fmt.Sprintf("billing retry: user quota increased but token quota failed (will not retry to avoid double-refund): user=%d token=%d delta=%d err=%s",
					p.UserID, p.TokenID, -p.QuotaDelta, err.Error()))
			}
		}
	}

	common.SysLog(fmt.Sprintf("billing retry succeeded: request=%s user=%d token=%d delta=%d reason=%s",
		p.RequestID, p.UserID, p.TokenID, p.QuotaDelta, p.Reason))
	return nil
}

// rewritePending overwrites the pending S3 object with the updated payload
// (e.g. incremented RetryCount) so the next scan picks up the new state.
func (w *billingRetryWorker) rewritePending(key string, p *BillingRetryPayload) {
	data, err := json.Marshal(p)
	if err != nil {
		common.SysError(fmt.Sprintf("billing retry worker: marshal for rewrite failed: %s", err.Error()))
		return
	}
	buf, err := gzipBytes(data)
	if err != nil {
		common.SysError(fmt.Sprintf("billing retry worker: gzip for rewrite failed: %s", err.Error()))
		return
	}
	if err := s3Upload(w.httpClient, w.signer, w.credentials, w.endpoint, w.bucket, w.region, key, buf); err != nil {
		common.SysError(fmt.Sprintf("billing retry worker: rewrite pending %s failed: %s", key, err.Error()))
	}
}

// --- S3 helper operations (list, get, delete) using raw HTTP + SigV4 ---

type s3ListResult struct {
	XMLName  xml.Name   `xml:"ListBucketResult"`
	Contents []s3Object `xml:"Contents"`
}

type s3Object struct {
	Key string `xml:"Key"`
}

func (w *billingRetryWorker) s3BaseURL() string {
	if w.endpoint != "" {
		return fmt.Sprintf("%s/%s", strings.TrimRight(w.endpoint, "/"), w.bucket)
	}
	return fmt.Sprintf("https://%s.s3.%s.amazonaws.com", w.bucket, w.region)
}

func (w *billingRetryWorker) s3List(prefix string, maxKeys int) ([]string, error) {
	url := fmt.Sprintf("%s?list-type=2&prefix=%s&max-keys=%d", w.s3BaseURL(), prefix, maxKeys)
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}

	emptyHash := sha256.Sum256(nil)
	payloadHash := hex.EncodeToString(emptyHash[:])
	req.Header.Set("X-Amz-Content-Sha256", payloadHash)
	if err = w.signer.SignHTTP(context.Background(), w.credentials, req, payloadHash, "s3", w.region, time.Now()); err != nil {
		return nil, err
	}

	resp, err := w.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer CloseResponseBodyGracefully(resp)

	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1024*1024))
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("s3 list failed, status=%d, body=%s", resp.StatusCode, string(body))
	}

	var result s3ListResult
	if err := xml.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("s3 list xml parse: %w", err)
	}

	keys := make([]string, 0, len(result.Contents))
	for _, obj := range result.Contents {
		keys = append(keys, obj.Key)
	}
	return keys, nil
}

func (w *billingRetryWorker) s3Get(key string) (*BillingRetryPayload, error) {
	url := fmt.Sprintf("%s/%s", w.s3BaseURL(), key)
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}

	emptyHash := sha256.Sum256(nil)
	payloadHash := hex.EncodeToString(emptyHash[:])
	req.Header.Set("X-Amz-Content-Sha256", payloadHash)
	if err = w.signer.SignHTTP(context.Background(), w.credentials, req, payloadHash, "s3", w.region, time.Now()); err != nil {
		return nil, err
	}

	resp, err := w.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer CloseResponseBodyGracefully(resp)

	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return nil, fmt.Errorf("s3 get failed, status=%d, body=%s", resp.StatusCode, string(b))
	}

	raw, err := io.ReadAll(io.LimitReader(resp.Body, 1024*1024))
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}

	data := raw
	if strings.HasSuffix(key, ".gz") {
		if gr, gzErr := gzip.NewReader(bytes.NewReader(raw)); gzErr == nil {
			if decompressed, readErr := io.ReadAll(gr); readErr == nil {
				data = decompressed
			}
			gr.Close()
		}
	}

	var payload BillingRetryPayload
	if err := json.Unmarshal(data, &payload); err != nil {
		return nil, fmt.Errorf("json unmarshal: %w", err)
	}
	return &payload, nil
}

func (w *billingRetryWorker) s3Delete(key string) error {
	url := fmt.Sprintf("%s/%s", w.s3BaseURL(), key)
	req, err := http.NewRequest(http.MethodDelete, url, nil)
	if err != nil {
		return err
	}

	emptyHash := sha256.Sum256(nil)
	payloadHash := hex.EncodeToString(emptyHash[:])
	req.Header.Set("X-Amz-Content-Sha256", payloadHash)
	if err = w.signer.SignHTTP(context.Background(), w.credentials, req, payloadHash, "s3", w.region, time.Now()); err != nil {
		return err
	}

	resp, err := w.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer CloseResponseBodyGracefully(resp)

	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return fmt.Errorf("s3 delete failed, status=%d, body=%s", resp.StatusCode, string(b))
	}
	return nil
}

func gzipBytes(data []byte) ([]byte, error) {
	var buf bytes.Buffer
	gw, err := gzip.NewWriterLevel(&buf, gzip.BestSpeed)
	if err != nil {
		return nil, err
	}
	if _, err := gw.Write(data); err != nil {
		return nil, err
	}
	if err := gw.Close(); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}
