package controller

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/model"

	"github.com/gin-gonic/gin"
)

type GenerateInvoiceRequest struct {
	UserId         int    `json:"user_id" binding:"required"`
	StartTimestamp int64  `json:"start_timestamp" binding:"required"`
	EndTimestamp   int64  `json:"end_timestamp" binding:"required"`
	Note           string `json:"note"`
}

func GenerateInvoice(c *gin.Context) {
	var req GenerateInvoiceRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "参数错误: "+err.Error())
		return
	}

	if req.StartTimestamp >= req.EndTimestamp {
		common.ApiErrorMsg(c, "开始时间必须早于结束时间")
		return
	}

	user, err := model.GetUserById(req.UserId, false)
	if err != nil || user == nil {
		common.ApiErrorMsg(c, "用户不存在")
		return
	}

	items, totalQuota, err := model.GetInvoiceItemsFromLogs(req.UserId, req.StartTimestamp, req.EndTimestamp)
	if err != nil {
		common.ApiError(c, err)
		return
	}

	if len(items) == 0 {
		common.ApiErrorMsg(c, "该时间段内没有消费记录")
		return
	}

	itemsJSON, err := json.Marshal(items)
	if err != nil {
		common.ApiError(c, err)
		return
	}

	invoiceNo, err := model.GenerateInvoiceNo()
	if err != nil {
		common.ApiError(c, err)
		return
	}

	totalAmount := float64(totalQuota) / common.QuotaPerUnit

	invoice := &model.Invoice{
		InvoiceNo:      invoiceNo,
		UserId:         req.UserId,
		Username:       user.Username,
		StartTimestamp: req.StartTimestamp,
		EndTimestamp:   req.EndTimestamp,
		TotalQuota:     totalQuota,
		TotalAmount:    totalAmount,
		Currency:       "USD",
		Items:          string(itemsJSON),
		Note:           req.Note,
		CreatedAt:      common.GetTimestamp(),
		CreatedBy:      c.GetInt("id"),
	}

	if err := model.CreateInvoice(invoice); err != nil {
		common.ApiError(c, err)
		return
	}

	common.ApiSuccess(c, invoice)
}

func GetAllInvoices(c *gin.Context) {
	pageInfo := common.GetPageQuery(c)
	username := c.Query("username")
	startTimestamp, _ := strconv.ParseInt(c.Query("start_timestamp"), 10, 64)
	endTimestamp, _ := strconv.ParseInt(c.Query("end_timestamp"), 10, 64)

	invoices, total, err := model.GetAllInvoices(username, startTimestamp, endTimestamp, pageInfo.GetStartIdx(), pageInfo.GetPageSize())
	if err != nil {
		common.ApiError(c, err)
		return
	}
	pageInfo.SetTotal(int(total))
	pageInfo.SetItems(invoices)
	common.ApiSuccess(c, pageInfo)
}

func GetInvoice(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		common.ApiErrorMsg(c, "无效的账单 ID")
		return
	}
	invoice, err := model.GetInvoiceById(id)
	if err != nil {
		common.ApiErrorMsg(c, "账单不存在")
		return
	}
	common.ApiSuccess(c, invoice)
}

func DeleteInvoice(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		common.ApiErrorMsg(c, "无效的账单 ID")
		return
	}
	if err := model.DeleteInvoice(id); err != nil {
		common.ApiError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "",
	})
}

func ExportInvoiceCSV(c *gin.Context) {
	includeDetails, _ := strconv.ParseBool(c.DefaultQuery("include_details", "false"))
	exportInvoiceCSV(c, includeDetails)
}

func ExportInvoiceDetailCSV(c *gin.Context) {
	exportInvoiceCSV(c, true)
}

func exportInvoiceCSV(c *gin.Context, includeDetails bool) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		common.ApiErrorMsg(c, "无效的账单 ID")
		return
	}
	invoice, err := model.GetInvoiceById(id)
	if err != nil {
		common.ApiErrorMsg(c, "账单不存在")
		return
	}

	items, err := invoice.GetItems()
	if err != nil {
		common.ApiError(c, err)
		return
	}

	c.Header("Content-Type", "text/csv; charset=utf-8")
	c.Header("Content-Disposition", fmt.Sprintf("attachment; filename=%s.csv", invoice.InvoiceNo))
	// UTF-8 BOM for Excel compatibility
	_, _ = c.Writer.Write([]byte{0xEF, 0xBB, 0xBF})

	_, _ = c.Writer.WriteString("Invoice No,Username,Start Time,End Time,Total Quota,Total Amount (USD),Note\n")
	_, _ = c.Writer.WriteString(fmt.Sprintf("%s,%s,%d,%d,%d,%.6f,%s\n\n",
		invoice.InvoiceNo, invoice.Username,
		invoice.StartTimestamp, invoice.EndTimestamp,
		invoice.TotalQuota, invoice.TotalAmount, invoice.Note))

	_, _ = c.Writer.WriteString("Model Name,Request Count,Prompt Tokens,Completion Tokens,Quota,Amount (USD)\n")
	for _, item := range items {
		_, _ = c.Writer.WriteString(fmt.Sprintf("%s,%d,%d,%d,%d,%.6f\n",
			item.ModelName, item.RequestCount,
			item.PromptTokens, item.CompletionTokens,
			item.Quota, item.Amount))
	}

	if !includeDetails {
		return
	}

	const exportBatchSize = 1000
	_, _ = c.Writer.WriteString("\n")
	_, _ = c.Writer.WriteString("Detail ID,Request ID,Created At,Model Name,Token Name,Prompt Tokens,Completion Tokens,Quota,Content\n")
	err = model.IterateInvoiceLogDetails(invoice.UserId, invoice.StartTimestamp, invoice.EndTimestamp, exportBatchSize, func(batch []model.InvoiceLogDetail) error {
		for _, detail := range batch {
			if _, err = c.Writer.WriteString(fmt.Sprintf("%d,%s,%d,%s,%s,%d,%d,%d,%s\n",
				detail.Id, detail.RequestId, detail.CreatedAt, detail.ModelName, detail.TokenName,
				detail.PromptTokens, detail.CompletionTokens, detail.Quota, detail.Content)); err != nil {
				return err
			}
		}
		c.Writer.Flush()
		return nil
	})
	if err != nil {
		common.SysError("export invoice detail failed: " + err.Error())
	}
}
