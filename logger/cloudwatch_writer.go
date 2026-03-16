package logger

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"
)

const (
	defaultCloudWatchBatchSize     = 32
	defaultCloudWatchFlushInterval = time.Second
)

type cloudWatchWriter struct {
	logGroupName string
	logStream    string
	region       string

	queue         chan string
	flushInterval time.Duration
	batchSize     int
}

func newCloudWatchWriterFromEnv() (*cloudWatchWriter, error) {
	logGroup := strings.TrimSpace(os.Getenv("AWS_LOG_GROUP_NAME"))
	logStream := strings.TrimSpace(os.Getenv("AWS_LOG_STREAM_NAME"))
	if logGroup == "" || logStream == "" {
		return nil, nil
	}
	region := strings.TrimSpace(os.Getenv("AWS_REGION"))
	if region == "" {
		return nil, fmt.Errorf("AWS_REGION is required when AWS_LOG_GROUP_NAME and AWS_LOG_STREAM_NAME are set")
	}
	if _, err := exec.LookPath("aws"); err != nil {
		return nil, fmt.Errorf("aws cli is not found in PATH")
	}

	writer := &cloudWatchWriter{
		logGroupName:  logGroup,
		logStream:     logStream,
		region:        region,
		queue:         make(chan string, 2048),
		flushInterval: defaultCloudWatchFlushInterval,
		batchSize:     defaultCloudWatchBatchSize,
	}

	// ignore "already exists" errors to make startup idempotent
	_ = writer.runAWSCommand("logs", "create-log-group", "--log-group-name", writer.logGroupName)
	_ = writer.runAWSCommand("logs", "create-log-stream", "--log-group-name", writer.logGroupName, "--log-stream-name", writer.logStream)

	go writer.flushLoop()
	return writer, nil
}

func (w *cloudWatchWriter) Write(p []byte) (n int, err error) {
	msg := strings.TrimRight(string(p), "\n")
	if msg == "" {
		return len(p), nil
	}
	select {
	case w.queue <- msg:
	default:
	}
	return len(p), nil
}

func (w *cloudWatchWriter) flushLoop() {
	ticker := time.NewTicker(w.flushInterval)
	defer ticker.Stop()

	batch := make([]string, 0, w.batchSize)
	for {
		select {
		case msg := <-w.queue:
			batch = append(batch, msg)
			if len(batch) >= w.batchSize {
				w.sendBatch(batch)
				batch = batch[:0]
			}
		case <-ticker.C:
			if len(batch) > 0 {
				w.sendBatch(batch)
				batch = batch[:0]
			}
		}
	}
}

func (w *cloudWatchWriter) sendBatch(messages []string) {
	type inputLogEvent struct {
		Timestamp int64  `json:"timestamp"`
		Message   string `json:"message"`
	}
	events := make([]inputLogEvent, 0, len(messages))
	nowMs := time.Now().UnixMilli()
	for i, msg := range messages {
		events = append(events, inputLogEvent{Timestamp: nowMs + int64(i), Message: msg})
	}
	payload, _ := json.Marshal(events)

	err := w.runAWSCommand(
		"logs", "put-log-events",
		"--log-group-name", w.logGroupName,
		"--log-stream-name", w.logStream,
		"--log-events", string(payload),
	)
	if err != nil {
		fmt.Fprintf(os.Stderr, "[WARN] %v | SYSTEM | failed to push logs to cloudwatch: %v\n", time.Now().Format("2006/01/02 - 15:04:05"), err)
	}
}

func (w *cloudWatchWriter) runAWSCommand(args ...string) error {
	cmd := exec.Command("aws", args...)
	cmd.Env = append(os.Environ(), "AWS_REGION="+w.region)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		msg := strings.TrimSpace(stderr.String())
		if msg == "" {
			return err
		}
		return fmt.Errorf("%w: %s", err, msg)
	}
	return nil
}
