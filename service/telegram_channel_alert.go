package service

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/common"
)

// SendChannelProbeTelegramAlert sends a Telegram message for channel probe(test) alerts.
//
// Env:
// - TG_BOT_TOKEN: Telegram bot token
// - TG_CHAT_ID: Telegram chat id (group/channel ids can start with -100)
//
// Return:
// - true when sent successfully
// - false when env not configured or send failed
func SendChannelProbeTelegramAlert(kind string, title string, content string) bool {
	botToken := strings.TrimSpace(os.Getenv("TG_BOT_TOKEN"))
	chatID := strings.TrimSpace(os.Getenv("TG_CHAT_ID"))
	if botToken == "" || chatID == "" {
		return false
	}

	kind = strings.TrimSpace(kind)
	if kind == "" {
		kind = "alert"
	}
	if len(kind) > 20 {
		kind = kind[:20]
	}

	// Telegram text-only message; convert common HTML breaks.
	text := fmt.Sprintf("[%s] %s\n%s", kind, title, strings.ReplaceAll(content, "<br/>", "\n"))
	text = strings.ReplaceAll(text, "<br>", "\n")
	text = strings.ReplaceAll(text, "\r", "")

	// Telegram hard limit is ~4096 chars for text messages.
	if len(text) > 4096 {
		text = text[:4096]
	}

	url := fmt.Sprintf("https://api.telegram.org/bot%s/sendMessage", botToken)
	payload := map[string]any{
		"chat_id":                  chatID,
		"text":                      text,
		"disable_web_page_preview": true,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		common.SysError("telegram channel alert marshal failed: " + err.Error())
		return false
	}

	client := GetHttpClient()
	httpClient := client
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 10 * time.Second}
	} else if httpClient.Timeout == 0 {
		httpClient = &http.Client{Timeout: 10 * time.Second}
	}

	resp, err := httpClient.Post(url, "application/json", bytes.NewBuffer(body))
	if err != nil {
		common.SysError("telegram channel alert post failed: " + err.Error())
		return false
	}
	defer resp.Body.Close()

	var tgResp struct {
		Ok          bool   `json:"ok"`
		Description string `json:"description"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&tgResp); err != nil {
		// If decoding fails, fall back to http status.
		return resp.StatusCode >= 200 && resp.StatusCode < 300
	}
	if !tgResp.Ok {
		common.SysError("telegram channel alert not ok: " + tgResp.Description)
		return false
	}
	return true
}

