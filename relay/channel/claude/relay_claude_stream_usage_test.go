package claude

import (
	"strings"
	"testing"

	"github.com/QuantumNous/new-api/dto"
	relaycommon "github.com/QuantumNous/new-api/relay/common"
	"github.com/QuantumNous/new-api/types"

	"github.com/gin-gonic/gin"
)

func TestHandleStreamFinalResponsePreservesMessageStartCacheUsage(t *testing.T) {
	gin.SetMode(gin.TestMode)
	c, _ := gin.CreateTestContext(nil)

	claudeInfo := &ClaudeResponseInfo{
		Model:        "claude-opus-4-7",
		ResponseText: strings.Builder{},
		Usage:        &dto.Usage{},
	}

	start := &dto.ClaudeResponse{
		Type: "message_start",
		Message: &dto.ClaudeMediaMessage{
			Model: "claude-opus-4-7",
			Usage: &dto.ClaudeUsage{
				InputTokens:              1,
				CacheCreationInputTokens: 632741,
				CacheReadInputTokens:     43059,
				OutputTokens:             1,
				CacheCreation: &dto.ClaudeCacheCreationUsage{
					Ephemeral5mInputTokens: 632741,
				},
			},
		},
	}

	FormatClaudeResponseInfo(RequestModeMessage, start, nil, claudeInfo)
	if claudeInfo.Done {
		t.Fatalf("message_start should not mark the stream as done")
	}

	HandleStreamFinalResponse(c, &relaycommon.RelayInfo{
		ChannelMeta: &relaycommon.ChannelMeta{
			UpstreamModelName: "claude-opus-4-7",
		},
		RelayFormat: types.RelayFormatClaude,
	}, claudeInfo, RequestModeMessage)

	if got := claudeInfo.Usage.PromptTokensDetails.CachedCreationTokens; got != 632741 {
		t.Fatalf("cached creation tokens = %d, want 632741", got)
	}
	if got := claudeInfo.Usage.ClaudeCacheCreation5mTokens; got != 632741 {
		t.Fatalf("5m cache creation tokens = %d, want 632741", got)
	}
	if got := claudeInfo.Usage.PromptTokensDetails.CachedTokens; got != 43059 {
		t.Fatalf("cache read tokens = %d, want 43059", got)
	}
	if got := claudeInfo.Usage.PromptTokens; got != 1 {
		t.Fatalf("prompt tokens = %d, want 1", got)
	}
	if got := claudeInfo.Usage.CompletionTokens; got != 1 {
		t.Fatalf("completion tokens = %d, want 1", got)
	}
	if got := claudeInfo.Usage.TotalTokens; got != 2 {
		t.Fatalf("total tokens = %d, want 2", got)
	}
}
