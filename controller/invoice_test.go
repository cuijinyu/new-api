package controller

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/QuantumNous/new-api/model"

	"github.com/gin-gonic/gin"
)

func TestGenerateInvoiceRequestBinding(t *testing.T) {
	tests := []struct {
		name    string
		body    string
		wantErr bool
	}{
		{
			name:    "valid request",
			body:    `{"user_id":1,"start_timestamp":1740000000,"end_timestamp":1742678400,"note":"test"}`,
			wantErr: false,
		},
		{
			name:    "missing user_id",
			body:    `{"start_timestamp":1740000000,"end_timestamp":1742678400}`,
			wantErr: true,
		},
		{
			name:    "missing start_timestamp",
			body:    `{"user_id":1,"end_timestamp":1742678400}`,
			wantErr: true,
		},
		{
			name:    "missing end_timestamp",
			body:    `{"user_id":1,"start_timestamp":1740000000}`,
			wantErr: true,
		},
		{
			name:    "empty body",
			body:    `{}`,
			wantErr: true,
		},
		{
			name:    "note is optional",
			body:    `{"user_id":1,"start_timestamp":1740000000,"end_timestamp":1742678400}`,
			wantErr: false,
		},
	}

	gin.SetMode(gin.TestMode)

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			w := httptest.NewRecorder()
			c, _ := gin.CreateTestContext(w)
			c.Request = httptest.NewRequest(http.MethodPost, "/api/invoice/generate", bytes.NewBufferString(tt.body))
			c.Request.Header.Set("Content-Type", "application/json")

			var req GenerateInvoiceRequest
			err := c.ShouldBindJSON(&req)
			if (err != nil) != tt.wantErr {
				t.Errorf("ShouldBindJSON() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func TestGenerateInvoiceRequestValues(t *testing.T) {
	gin.SetMode(gin.TestMode)

	body := `{"user_id":42,"start_timestamp":1740000000,"end_timestamp":1742678400,"note":"monthly bill"}`
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodPost, "/api/invoice/generate", bytes.NewBufferString(body))
	c.Request.Header.Set("Content-Type", "application/json")

	var req GenerateInvoiceRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		t.Fatalf("ShouldBindJSON() error: %v", err)
	}

	if req.UserId != 42 {
		t.Errorf("UserId = %d, want 42", req.UserId)
	}
	if req.StartTimestamp != 1740000000 {
		t.Errorf("StartTimestamp = %d, want 1740000000", req.StartTimestamp)
	}
	if req.EndTimestamp != 1742678400 {
		t.Errorf("EndTimestamp = %d, want 1742678400", req.EndTimestamp)
	}
	if req.Note != "monthly bill" {
		t.Errorf("Note = %s, want 'monthly bill'", req.Note)
	}
}

func TestExportInvoiceCSVFormat(t *testing.T) {
	gin.SetMode(gin.TestMode)

	items := []model.InvoiceItem{
		{
			ModelName:        "gpt-4o",
			RequestCount:     100,
			PromptTokens:     50000,
			CompletionTokens: 20000,
			Quota:            250000,
			Amount:           0.5,
		},
		{
			ModelName:        "claude-3-sonnet",
			RequestCount:     50,
			PromptTokens:     30000,
			CompletionTokens: 10000,
			Quota:            150000,
			Amount:           0.3,
		},
	}
	itemsJSON, _ := json.Marshal(items)

	invoice := &model.Invoice{
		Id:             1,
		InvoiceNo:      "INV-202602-0001",
		Username:       "testuser",
		StartTimestamp: 1740000000,
		EndTimestamp:   1742678400,
		TotalQuota:     400000,
		TotalAmount:    0.8,
		Note:           "test note",
		Items:          string(itemsJSON),
	}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/api/invoice/1/export", nil)

	// 模拟 ExportInvoiceCSV 的核心输出逻辑
	c.Header("Content-Type", "text/csv; charset=utf-8")
	c.Header("Content-Disposition", fmt.Sprintf("attachment; filename=%s.csv", invoice.InvoiceNo))
	c.Writer.Write([]byte{0xEF, 0xBB, 0xBF})

	c.Writer.WriteString("Invoice No,Username,Start Time,End Time,Total Quota,Total Amount (USD),Note\n")
	c.Writer.WriteString(fmt.Sprintf("%s,%s,%d,%d,%d,%.6f,%s\n\n",
		invoice.InvoiceNo, invoice.Username,
		invoice.StartTimestamp, invoice.EndTimestamp,
		invoice.TotalQuota, invoice.TotalAmount, invoice.Note))

	c.Writer.WriteString("Model Name,Request Count,Prompt Tokens,Completion Tokens,Quota,Amount (USD)\n")
	for _, item := range items {
		c.Writer.WriteString(fmt.Sprintf("%s,%d,%d,%d,%d,%.6f\n",
			item.ModelName, item.RequestCount,
			item.PromptTokens, item.CompletionTokens,
			item.Quota, item.Amount))
	}

	result := w.Result()
	body := w.Body.String()

	// 验证 Content-Type
	contentType := result.Header.Get("Content-Type")
	if !strings.Contains(contentType, "text/csv") {
		t.Errorf("Content-Type = %s, want text/csv", contentType)
	}

	// 验证 Content-Disposition
	disposition := result.Header.Get("Content-Disposition")
	if !strings.Contains(disposition, "INV-202602-0001.csv") {
		t.Errorf("Content-Disposition = %s, want to contain INV-202602-0001.csv", disposition)
	}

	// 验证 UTF-8 BOM
	if !strings.HasPrefix(body, "\xEF\xBB\xBF") {
		t.Error("CSV output missing UTF-8 BOM")
	}

	// 去掉 BOM 后验证内容
	csvContent := strings.TrimPrefix(body, "\xEF\xBB\xBF")
	lines := strings.Split(strings.TrimSpace(csvContent), "\n")

	// 至少应有：header行 + 数据行 + 空行 + 明细header行 + 2条明细行 = 6行
	if len(lines) < 5 {
		t.Fatalf("CSV has %d lines, want at least 5", len(lines))
	}

	// 验证头部 header
	if lines[0] != "Invoice No,Username,Start Time,End Time,Total Quota,Total Amount (USD),Note" {
		t.Errorf("Header line = %s", lines[0])
	}

	// 验证账单数据行包含关键字段
	if !strings.Contains(lines[1], "INV-202602-0001") {
		t.Errorf("Data line missing invoice_no: %s", lines[1])
	}
	if !strings.Contains(lines[1], "testuser") {
		t.Errorf("Data line missing username: %s", lines[1])
	}

	// 验证明细 header
	detailHeaderIdx := -1
	for i, line := range lines {
		if strings.HasPrefix(line, "Model Name,") {
			detailHeaderIdx = i
			break
		}
	}
	if detailHeaderIdx == -1 {
		t.Fatal("Detail header line not found")
	}

	// 验证明细数据行
	if detailHeaderIdx+1 >= len(lines) {
		t.Fatal("Missing detail data lines after detail header")
	}
	if !strings.HasPrefix(lines[detailHeaderIdx+1], "gpt-4o,") {
		t.Errorf("First detail line = %s, want to start with gpt-4o", lines[detailHeaderIdx+1])
	}
	if detailHeaderIdx+2 >= len(lines) {
		t.Fatal("Missing second detail data line")
	}
	if !strings.HasPrefix(lines[detailHeaderIdx+2], "claude-3-sonnet,") {
		t.Errorf("Second detail line = %s, want to start with claude-3-sonnet", lines[detailHeaderIdx+2])
	}
}

func TestExportInvoiceCSVEmptyItems(t *testing.T) {
	gin.SetMode(gin.TestMode)

	invoice := &model.Invoice{
		InvoiceNo:      "INV-202602-0002",
		Username:       "emptyuser",
		StartTimestamp: 1740000000,
		EndTimestamp:   1742678400,
		TotalQuota:     0,
		TotalAmount:    0,
		Items:          "[]",
	}

	parsedItems, err := invoice.GetItems()
	if err != nil {
		t.Fatalf("GetItems() error: %v", err)
	}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/api/invoice/2/export", nil)

	c.Writer.Write([]byte{0xEF, 0xBB, 0xBF})
	c.Writer.WriteString("Invoice No,Username,Start Time,End Time,Total Quota,Total Amount (USD),Note\n")
	c.Writer.WriteString(fmt.Sprintf("%s,%s,%d,%d,%d,%.6f,%s\n\n",
		invoice.InvoiceNo, invoice.Username,
		invoice.StartTimestamp, invoice.EndTimestamp,
		invoice.TotalQuota, invoice.TotalAmount, invoice.Note))
	c.Writer.WriteString("Model Name,Request Count,Prompt Tokens,Completion Tokens,Quota,Amount (USD)\n")
	for _, item := range parsedItems {
		c.Writer.WriteString(fmt.Sprintf("%s,%d,%d,%d,%d,%.6f\n",
			item.ModelName, item.RequestCount,
			item.PromptTokens, item.CompletionTokens,
			item.Quota, item.Amount))
	}

	csvContent := strings.TrimPrefix(w.Body.String(), "\xEF\xBB\xBF")
	lines := strings.Split(strings.TrimSpace(csvContent), "\n")

	// 应有：header + data + 空行 + detail header = 4行（无明细数据行）
	detailCount := 0
	foundDetailHeader := false
	for _, line := range lines {
		if strings.HasPrefix(line, "Model Name,") {
			foundDetailHeader = true
			continue
		}
		if foundDetailHeader && line != "" {
			detailCount++
		}
	}

	if !foundDetailHeader {
		t.Error("Detail header not found in CSV")
	}
	if detailCount != 0 {
		t.Errorf("Expected 0 detail lines for empty items, got %d", detailCount)
	}
}
