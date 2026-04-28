package service

import (
	"bytes"
	"compress/gzip"
	"encoding/json"
	"fmt"
	"net/http"
	"path"
	"time"

	"github.com/QuantumNous/new-api/common"

	"github.com/aws/aws-sdk-go-v2/aws"
	v4 "github.com/aws/aws-sdk-go-v2/aws/signer/v4"
)

type fingerprintS3Uploader struct {
	enabled     bool
	bucket      string
	prefix      string
	region      string
	endpoint    string
	retries     int
	credentials aws.Credentials
	signer      *v4.Signer
	httpClient  *http.Client
}

var fingerprintS3Inst *fingerprintS3Uploader

func getFingerprintS3Uploader() *fingerprintS3Uploader {
	if fingerprintS3Inst != nil {
		return fingerprintS3Inst
	}
	fingerprintS3Inst = initFingerprintS3Uploader()
	return fingerprintS3Inst
}

func initFingerprintS3Uploader() *fingerprintS3Uploader {
	cfg, ok := loadRawLogS3Config()
	if !ok {
		return &fingerprintS3Uploader{enabled: false}
	}
	prefix := common.GetEnvOrDefaultString("FINGERPRINT_S3_PREFIX", "fingerprint-reports")

	return &fingerprintS3Uploader{
		enabled:  true,
		bucket:   cfg.bucket,
		prefix:   prefix,
		region:   cfg.region,
		endpoint: cfg.endpoint,
		retries:  2,
		credentials: aws.Credentials{
			AccessKeyID:     cfg.accessKey,
			SecretAccessKey: cfg.secretKey,
			SessionToken:    cfg.sessionToken,
		},
		signer:     v4.NewSigner(),
		httpClient: GetHttpClient(),
	}
}

// UploadFingerprintReport uploads fingerprint results as gzipped NDJSON to S3.
// Each element in results is JSON-marshalled as one line.
func UploadFingerprintReport(results []any) {
	u := getFingerprintS3Uploader()
	if !u.enabled || len(results) == 0 {
		return
	}

	var buf bytes.Buffer
	gw, err := gzip.NewWriterLevel(&buf, gzip.BestSpeed)
	if err != nil {
		common.SysError(fmt.Sprintf("fingerprint s3: gzip writer error: %s", err.Error()))
		return
	}
	for i, r := range results {
		if i > 0 {
			_, _ = gw.Write([]byte("\n"))
		}
		data, err := json.Marshal(r)
		if err != nil {
			common.SysError(fmt.Sprintf("fingerprint s3: marshal error: %s", err.Error()))
			continue
		}
		_, _ = gw.Write(data)
	}
	if err = gw.Close(); err != nil {
		common.SysError(fmt.Sprintf("fingerprint s3: gzip close error: %s", err.Error()))
		return
	}

	now := time.Now()
	keyPrefix := now.Format("2006/01/02/15")
	if u.prefix != "" {
		keyPrefix = path.Join(u.prefix, keyPrefix)
	}
	objectKey := path.Join(keyPrefix, fmt.Sprintf("%d-%d.ndjson.gz", now.Unix(), len(results)))

	var lastErr error
	for attempt := 0; attempt <= u.retries; attempt++ {
		if attempt > 0 {
			time.Sleep(time.Duration(attempt) * 500 * time.Millisecond)
		}
		lastErr = s3Upload(u.httpClient, u.signer, u.credentials, u.endpoint, u.bucket, u.region, objectKey, buf.Bytes())
		if lastErr == nil {
			common.SysLog(fmt.Sprintf("fingerprint s3: uploaded %d results to s3://%s/%s", len(results), u.bucket, objectKey))
			return
		}
	}
	common.SysError(fmt.Sprintf("fingerprint s3: upload failed after %d retries: %s", u.retries+1, lastErr.Error()))
}
