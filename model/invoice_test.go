package model

import (
	"encoding/json"
	"math"
	"testing"

	"github.com/QuantumNous/new-api/common"
)

func TestInvoiceJSONRoundTrip(t *testing.T) {
	original := Invoice{
		Id:             1,
		InvoiceNo:      "INV-202602-0001",
		UserId:         100,
		Username:       "testuser",
		StartTimestamp: 1740000000,
		EndTimestamp:   1742678400,
		TotalQuota:     500000,
		TotalAmount:    1.0,
		Currency:       "USD",
		Items:          `[{"model_name":"gpt-4o"}]`,
		Note:           "测试账单",
		CreatedAt:      1742700000,
		CreatedBy:      1,
	}

	data, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("Failed to marshal Invoice: %v", err)
	}

	var decoded Invoice
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Failed to unmarshal Invoice: %v", err)
	}

	if decoded.InvoiceNo != original.InvoiceNo {
		t.Errorf("InvoiceNo = %s, want %s", decoded.InvoiceNo, original.InvoiceNo)
	}
	if decoded.UserId != original.UserId {
		t.Errorf("UserId = %d, want %d", decoded.UserId, original.UserId)
	}
	if decoded.Username != original.Username {
		t.Errorf("Username = %s, want %s", decoded.Username, original.Username)
	}
	if decoded.StartTimestamp != original.StartTimestamp {
		t.Errorf("StartTimestamp = %d, want %d", decoded.StartTimestamp, original.StartTimestamp)
	}
	if decoded.EndTimestamp != original.EndTimestamp {
		t.Errorf("EndTimestamp = %d, want %d", decoded.EndTimestamp, original.EndTimestamp)
	}
	if decoded.TotalQuota != original.TotalQuota {
		t.Errorf("TotalQuota = %d, want %d", decoded.TotalQuota, original.TotalQuota)
	}
	if decoded.TotalAmount != original.TotalAmount {
		t.Errorf("TotalAmount = %f, want %f", decoded.TotalAmount, original.TotalAmount)
	}
	if decoded.Currency != original.Currency {
		t.Errorf("Currency = %s, want %s", decoded.Currency, original.Currency)
	}
	if decoded.Note != original.Note {
		t.Errorf("Note = %s, want %s", decoded.Note, original.Note)
	}
	if decoded.CreatedBy != original.CreatedBy {
		t.Errorf("CreatedBy = %d, want %d", decoded.CreatedBy, original.CreatedBy)
	}
}

func TestInvoiceJSONFieldNames(t *testing.T) {
	invoice := Invoice{
		InvoiceNo:      "INV-202602-0001",
		StartTimestamp: 1740000000,
		EndTimestamp:   1742678400,
		TotalQuota:     100000,
		TotalAmount:    0.2,
		CreatedAt:      1742700000,
		CreatedBy:      1,
	}

	data, err := json.Marshal(invoice)
	if err != nil {
		t.Fatalf("Failed to marshal: %v", err)
	}

	var parsed map[string]interface{}
	if err := json.Unmarshal(data, &parsed); err != nil {
		t.Fatalf("Failed to unmarshal to map: %v", err)
	}

	expectedFields := []string{
		"id", "invoice_no", "user_id", "username",
		"start_timestamp", "end_timestamp",
		"total_quota", "total_amount", "currency",
		"items", "note", "created_at", "created_by",
	}
	for _, field := range expectedFields {
		if _, ok := parsed[field]; !ok {
			t.Errorf("JSON field %q missing from output", field)
		}
	}
}

func TestInvoiceItemJSONRoundTrip(t *testing.T) {
	original := InvoiceItem{
		ModelName:        "gpt-4o",
		RequestCount:     150,
		PromptTokens:     50000,
		CompletionTokens: 20000,
		Quota:            250000,
		Amount:           0.5,
	}

	data, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("Failed to marshal InvoiceItem: %v", err)
	}

	var decoded InvoiceItem
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Failed to unmarshal InvoiceItem: %v", err)
	}

	if decoded.ModelName != original.ModelName {
		t.Errorf("ModelName = %s, want %s", decoded.ModelName, original.ModelName)
	}
	if decoded.RequestCount != original.RequestCount {
		t.Errorf("RequestCount = %d, want %d", decoded.RequestCount, original.RequestCount)
	}
	if decoded.PromptTokens != original.PromptTokens {
		t.Errorf("PromptTokens = %d, want %d", decoded.PromptTokens, original.PromptTokens)
	}
	if decoded.CompletionTokens != original.CompletionTokens {
		t.Errorf("CompletionTokens = %d, want %d", decoded.CompletionTokens, original.CompletionTokens)
	}
	if decoded.Quota != original.Quota {
		t.Errorf("Quota = %d, want %d", decoded.Quota, original.Quota)
	}
	if decoded.Amount != original.Amount {
		t.Errorf("Amount = %f, want %f", decoded.Amount, original.Amount)
	}
}

func TestInvoiceGetItems(t *testing.T) {
	tests := []struct {
		name    string
		items   string
		wantLen int
		wantErr bool
	}{
		{
			name:    "valid single item",
			items:   `[{"model_name":"gpt-4o","request_count":10,"prompt_tokens":1000,"completion_tokens":500,"quota":50000,"amount":0.1}]`,
			wantLen: 1,
			wantErr: false,
		},
		{
			name:    "valid multiple items",
			items:   `[{"model_name":"gpt-4o","quota":50000},{"model_name":"claude-3","quota":30000}]`,
			wantLen: 2,
			wantErr: false,
		},
		{
			name:    "empty string",
			items:   "",
			wantLen: 0,
			wantErr: false,
		},
		{
			name:    "null string",
			items:   "null",
			wantLen: 0,
			wantErr: false,
		},
		{
			name:    "empty array",
			items:   "[]",
			wantLen: 0,
			wantErr: false,
		},
		{
			name:    "invalid json",
			items:   "not-valid-json",
			wantLen: 0,
			wantErr: true,
		},
		{
			name:    "invalid json object instead of array",
			items:   `{"model_name":"gpt-4o"}`,
			wantLen: 0,
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			invoice := &Invoice{Items: tt.items}
			items, err := invoice.GetItems()
			if (err != nil) != tt.wantErr {
				t.Errorf("GetItems() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if len(items) != tt.wantLen {
				t.Errorf("GetItems() returned %d items, want %d", len(items), tt.wantLen)
			}
		})
	}
}

func TestInvoiceGetItemsDataIntegrity(t *testing.T) {
	itemsJSON := `[{"model_name":"gpt-4o","request_count":100,"prompt_tokens":50000,"completion_tokens":20000,"quota":250000,"amount":0.5}]`
	invoice := &Invoice{Items: itemsJSON}

	items, err := invoice.GetItems()
	if err != nil {
		t.Fatalf("GetItems() error: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("GetItems() returned %d items, want 1", len(items))
	}

	item := items[0]
	if item.ModelName != "gpt-4o" {
		t.Errorf("ModelName = %s, want gpt-4o", item.ModelName)
	}
	if item.RequestCount != 100 {
		t.Errorf("RequestCount = %d, want 100", item.RequestCount)
	}
	if item.PromptTokens != 50000 {
		t.Errorf("PromptTokens = %d, want 50000", item.PromptTokens)
	}
	if item.CompletionTokens != 20000 {
		t.Errorf("CompletionTokens = %d, want 20000", item.CompletionTokens)
	}
	if item.Quota != 250000 {
		t.Errorf("Quota = %d, want 250000", item.Quota)
	}
	if item.Amount != 0.5 {
		t.Errorf("Amount = %f, want 0.5", item.Amount)
	}
}

func TestInvoiceItemAmountCalculation(t *testing.T) {
	tests := []struct {
		name       string
		quota      int
		wantAmount float64
	}{
		{"zero quota", 0, 0.0},
		{"500000 quota = 1 USD", 500000, 1.0},
		{"250000 quota = 0.5 USD", 250000, 0.5},
		{"1000000 quota = 2 USD", 1000000, 2.0},
		{"1 quota", 1, 1.0 / 500000.0},
		{"small quota 100", 100, 100.0 / 500000.0},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			amount := float64(tt.quota) / common.QuotaPerUnit
			if math.Abs(amount-tt.wantAmount) > 1e-10 {
				t.Errorf("quota %d -> amount = %f, want %f", tt.quota, amount, tt.wantAmount)
			}
		})
	}
}

func TestInvoiceItemAmountFieldMatchesQuota(t *testing.T) {
	quotas := []int{0, 1, 100, 250000, 500000, 1000000, 5000000}

	for _, quota := range quotas {
		expectedAmount := float64(quota) / common.QuotaPerUnit
		item := InvoiceItem{
			ModelName: "test-model",
			Quota:     quota,
			Amount:    expectedAmount,
		}

		data, err := json.Marshal(item)
		if err != nil {
			t.Fatalf("Failed to marshal for quota %d: %v", quota, err)
		}

		var decoded InvoiceItem
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Failed to unmarshal for quota %d: %v", quota, err)
		}

		if math.Abs(decoded.Amount-expectedAmount) > 1e-10 {
			t.Errorf("quota %d: decoded Amount = %f, want %f", quota, decoded.Amount, expectedAmount)
		}
	}
}
