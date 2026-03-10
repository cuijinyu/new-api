package service

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"path"
	"sync"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/logger"
	relaycommon "github.com/QuantumNous/new-api/relay/common"

	"github.com/aws/aws-sdk-go-v2/aws"
	v4 "github.com/aws/aws-sdk-go-v2/aws/signer/v4"
	"github.com/gin-gonic/gin"
)

type rawLogUploader struct {
	enabled     bool
	bucket      string
	prefix      string
	region      string
	credentials aws.Credentials
	signer      *v4.Signer
	httpClient  *http.Client
	queue       chan rawLogRecord
}

type rawLogRecord struct {
	Key  string
	Body []byte
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
)

func getRawLogUploader() *rawLogUploader {
	rawLogOnce.Do(func() {
		rawLogInst = initRawLogUploader()
	})
	return rawLogInst
}

func initRawLogUploader() *rawLogUploader {
	if !common.GetEnvOrDefaultBool("RAW_LOG_S3_ENABLED", false) {
		return &rawLogUploader{enabled: false}
	}
	bucket := common.GetEnvOrDefaultString("RAW_LOG_S3_BUCKET", "")
	region := common.GetEnvOrDefaultString("RAW_LOG_S3_REGION", "")
	prefix := common.GetEnvOrDefaultString("RAW_LOG_S3_PREFIX", "llm-raw-logs")
	accessKey := common.GetEnvOrDefaultString("RAW_LOG_S3_ACCESS_KEY_ID", "")
	secretKey := common.GetEnvOrDefaultString("RAW_LOG_S3_SECRET_ACCESS_KEY", "")
	sessionToken := common.GetEnvOrDefaultString("RAW_LOG_S3_SESSION_TOKEN", "")
	if bucket == "" || region == "" || accessKey == "" || secretKey == "" {
		common.SysError("raw log s3 enabled but config missing, disable uploader")
		return &rawLogUploader{enabled: false}
	}
	u := &rawLogUploader{
		enabled:     true,
		bucket:      bucket,
		prefix:      prefix,
		region:      region,
		credentials: aws.Credentials{AccessKeyID: accessKey, SecretAccessKey: secretKey, SessionToken: sessionToken},
		signer:      v4.NewSigner(),
		httpClient:  GetHttpClient(),
		queue:       make(chan rawLogRecord, common.GetEnvOrDefault("RAW_LOG_S3_QUEUE_SIZE", 1000)),
	}
	workerNum := common.GetEnvOrDefault("RAW_LOG_S3_WORKERS", 2)
	if workerNum < 1 {
		workerNum = 1
	}
	for i := 0; i < workerNum; i++ {
		go u.worker()
	}
	common.SysLog(fmt.Sprintf("raw log s3 uploader enabled, region=%s, bucket=%s", region, bucket))
	return u
}

func (u *rawLogUploader) worker() {
	for item := range u.queue {
		if err := u.upload(item); err != nil {
			common.SysError("failed to upload raw log to s3: " + err.Error())
		}
	}
}

func (u *rawLogUploader) upload(item rawLogRecord) error {
	url := fmt.Sprintf("https://%s.s3.%s.amazonaws.com/%s", u.bucket, u.region, item.Key)
	req, err := http.NewRequest(http.MethodPut, url, bytes.NewReader(item.Body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	hashBytes := sha256.Sum256(item.Body)
	payloadHash := hex.EncodeToString(hashBytes[:])
	if err = u.signer.SignHTTP(context.Background(), u.credentials, req, payloadHash, "s3", u.region, time.Now()); err != nil {
		return err
	}
	resp, err := u.httpClient.Do(req)
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

func AttachRawLogCapture(c *gin.Context, info *relaycommon.RelayInfo, req *http.Request, resp *http.Response) {
	u := getRawLogUploader()
	if !u.enabled || req == nil || resp == nil || resp.Body == nil {
		return
	}
	reqBody := readRequestBody(req)
	payload := rawLogPayload{
		RequestID:      c.GetString(common.RequestIdKey),
		CreatedAt:      time.Now().Format(time.RFC3339Nano),
		Method:         req.Method,
		Path:           c.Request.URL.Path,
		URL:            req.URL.String(),
		StatusCode:     resp.StatusCode,
		RequestHeaders: req.Header.Clone(),
		RequestBody:    truncateRawLog(string(reqBody)),
		ChannelID:      c.GetInt("channel_id"),
		ChannelName:    c.GetString("channel_name"),
		ChannelType:    c.GetInt("channel_type"),
		UserID:         c.GetInt("id"),
	}
	if info != nil {
		payload.Model = info.OriginModelName
		payload.RelayMode = fmt.Sprintf("%d", info.RelayMode)
	}
	keyPrefix := time.Now().Format("2006/01/02")
	if u.prefix != "" {
		keyPrefix = path.Join(u.prefix, keyPrefix)
	}
	objectKey := path.Join(keyPrefix, fmt.Sprintf("%s-%d.json", payload.RequestID, time.Now().UnixNano()))

	resp.Body = newCaptureReadCloser(resp.Body, common.GetEnvOrDefault("RAW_LOG_S3_MAX_BYTES", 1024*1024), func(captured []byte, closeErr error) {
		payload.ResponseBody = truncateRawLog(string(captured))
		if closeErr != nil {
			payload.ResponseError = closeErr.Error()
		}
		data, err := json.Marshal(payload)
		if err != nil {
			logger.LogError(c, "failed to marshal raw log payload: "+err.Error())
			return
		}
		rec := rawLogRecord{Key: objectKey, Body: data}
		select {
		case u.queue <- rec:
		default:
			logger.LogWarn(c, "raw log s3 queue full, drop current raw log")
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

func truncateRawLog(v string) string {
	maxLen := common.GetEnvOrDefault("RAW_LOG_S3_MAX_BYTES", 1024*1024)
	if maxLen <= 0 {
		return ""
	}
	if len(v) <= maxLen {
		return v
	}
	return v[:maxLen]
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
