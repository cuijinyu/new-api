package controller

import (
	"bytes"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"strconv"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/model"

	"github.com/gin-gonic/gin"
)

type upstreamCSVRow struct {
	ReconDate             string `json:"recon_date"`
	ChannelId             int    `json:"channel_id"`
	Source                string `json:"source"`
	Model                 string `json:"model"`
	TotalRequests         int    `json:"total_requests"`
	TotalPromptTokens     int64  `json:"total_prompt_tokens"`
	TotalCompletionTokens int64  `json:"total_completion_tokens"`
	TotalAmountCent       int64  `json:"total_amount_cent"`
	Currency              string `json:"currency"`
}

func UploadUpstreamBill(c *gin.Context) {
	startDate := c.PostForm("start_date")
	endDate := c.PostForm("end_date")
	channelIdStr := c.PostForm("channel_id")
	source := c.PostForm("source")

	if startDate == "" || endDate == "" || source == "" || channelIdStr == "" {
		common.ApiErrorMsg(c, "start_date、end_date、channel_id 和 source 必填")
		return
	}
	if endDate < startDate {
		common.ApiErrorMsg(c, "结束日期不能早于开始日期")
		return
	}
	channelId, err := strconv.Atoi(channelIdStr)
	if err != nil || channelId <= 0 {
		common.ApiErrorMsg(c, "channel_id 无效")
		return
	}

	file, _, err := c.Request.FormFile("file")
	if err != nil {
		common.ApiErrorMsg(c, "文件上传失败: "+err.Error())
		return
	}
	defer file.Close()

	rawBytes, err := io.ReadAll(file)
	if err != nil {
		common.ApiErrorMsg(c, "读取文件失败")
		return
	}

	var rows []upstreamCSVRow
	if isJSON(rawBytes) {
		if err := json.Unmarshal(rawBytes, &rows); err != nil {
			common.ApiErrorMsg(c, "JSON 解析失败: "+err.Error())
			return
		}
	} else {
		rows, err = parseUpstreamCSV(rawBytes)
		if err != nil {
			common.ApiErrorMsg(c, "CSV 解析失败: "+err.Error())
			return
		}
	}

	if len(rows) == 0 {
		common.ApiErrorMsg(c, "文件内容为空")
		return
	}

	var upstreams []model.ReconUpstream
	var validationErrors []string
	for i, row := range rows {
		if row.Model == "" {
			validationErrors = append(validationErrors, fmt.Sprintf("第 %d 行缺少 model", i+1))
			continue
		}
		reconDate := row.ReconDate
		if reconDate == "" {
			reconDate = startDate
		}
		u := model.ReconUpstream{
			ReconDate:             reconDate,
			ChannelId:             channelId,
			Source:                source,
			Model:                 row.Model,
			TotalRequests:         row.TotalRequests,
			TotalPromptTokens:     row.TotalPromptTokens,
			TotalCompletionTokens: row.TotalCompletionTokens,
			TotalAmountCent:       row.TotalAmountCent,
			Currency:              row.Currency,
		}
		if u.Currency == "" {
			u.Currency = "USD"
		}
		upstreams = append(upstreams, u)
	}

	if len(validationErrors) > 0 {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": fmt.Sprintf("校验失败，共 %d 条错误", len(validationErrors)),
			"data":    validationErrors,
		})
		return
	}

	if err := model.DeleteUpstreamByDateRangeAndChannel(startDate, endDate, channelId, source); err != nil {
		common.ApiErrorMsg(c, "清理旧数据失败: "+err.Error())
		return
	}

	if err := model.InsertUpstreamBatch(upstreams); err != nil {
		common.ApiErrorMsg(c, "写入失败: "+err.Error())
		return
	}

	common.ApiSuccess(c, gin.H{"count": len(upstreams)})
}

func RunReconciliation(c *gin.Context) {
	var req struct {
		StartDate string `json:"start_date" binding:"required"`
		EndDate   string `json:"end_date" binding:"required"`
		ChannelId int    `json:"channel_id"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "参数错误: "+err.Error())
		return
	}
	if req.EndDate < req.StartDate {
		common.ApiErrorMsg(c, "结束日期不能早于开始日期")
		return
	}

	systemRows, err := model.GetSystemSummary(req.StartDate, req.EndDate, req.ChannelId)
	if err != nil {
		common.ApiErrorMsg(c, "查询系统侧数据失败: "+err.Error())
		return
	}

	upstreamRows, err := model.GetUpstreamByDateRange(req.StartDate, req.EndDate, req.ChannelId)
	if err != nil {
		common.ApiErrorMsg(c, "查询上游侧数据失败: "+err.Error())
		return
	}

	discountMap := model.GetDiscountMap()

	type reconKey struct {
		ReconDate string
		ChannelId int
		Model     string
	}

	sysMap := make(map[reconKey]*model.SystemSummaryRow)
	for i := range systemRows {
		k := reconKey{systemRows[i].ReconDate, systemRows[i].ChannelId, systemRows[i].Model}
		sysMap[k] = &systemRows[i]
	}

	upMap := make(map[reconKey]*model.ReconUpstream)
	for i := range upstreamRows {
		k := reconKey{upstreamRows[i].ReconDate, upstreamRows[i].ChannelId, upstreamRows[i].Model}
		upMap[k] = &upstreamRows[i]
	}

	allKeys := make(map[reconKey]bool)
	for k := range sysMap {
		allKeys[k] = true
	}
	for k := range upMap {
		allKeys[k] = true
	}

	var results []model.ReconResult
	for k := range allKeys {
		sys := sysMap[k]
		up := upMap[k]

		dKey := fmt.Sprintf("%d:%s", k.ChannelId, k.Model)
		discountRate := 1.0
		if r, ok := discountMap[dKey]; ok && r > 0 {
			discountRate = r
		}

		r := model.ReconResult{
			ReconDate:    k.ReconDate,
			ChannelId:    k.ChannelId,
			Model:        k.Model,
			DiscountRate: discountRate,
		}

		if sys != nil {
			r.SystemRequests = sys.TotalRequests
			r.SystemPromptTokens = sys.TotalPromptTokens
			r.SystemCompletionTokens = sys.TotalCompletionTokens
			r.SystemQuota = sys.TotalQuota
		}

		if up != nil {
			r.Source = up.Source
			r.UpstreamRequests = up.TotalRequests
			r.UpstreamPromptTokens = up.TotalPromptTokens
			r.UpstreamCompletionTokens = up.TotalCompletionTokens
			r.UpstreamAmountCent = up.TotalAmountCent
		}

		expectedCent := int64(float64(r.SystemQuota) / common.QuotaPerUnit * 100.0 * discountRate)
		r.ExpectedAmountCent = expectedCent
		r.AmountDiffCent = expectedCent - r.UpstreamAmountCent

		sysTokens := r.SystemPromptTokens + r.SystemCompletionTokens
		upTokens := r.UpstreamPromptTokens + r.UpstreamCompletionTokens
		r.TokenDiffRate = diffRate(float64(sysTokens), float64(upTokens))
		r.AmountDiffRate = diffRate(float64(expectedCent), float64(r.UpstreamAmountCent))

		if sys == nil {
			r.Status = "missing_system"
		} else if up == nil {
			r.Status = "missing_upstream"
		} else if r.TokenDiffRate > 0.02 || r.AmountDiffRate > 0.02 {
			r.Status = "abnormal"
		} else {
			r.Status = "normal"
		}

		results = append(results, r)
	}

	if err := model.DeleteResultsByDateRange(req.StartDate, req.EndDate, req.ChannelId); err != nil {
		common.ApiErrorMsg(c, "清理旧结果失败: "+err.Error())
		return
	}

	if err := model.InsertResultsBatch(results); err != nil {
		common.ApiErrorMsg(c, "写入结果失败: "+err.Error())
		return
	}

	common.ApiSuccess(c, gin.H{
		"total":    len(results),
		"normal":   countStatus(results, "normal"),
		"abnormal": countStatus(results, "abnormal"),
		"missing":  countStatus(results, "missing_system") + countStatus(results, "missing_upstream"),
	})
}

func GetReconResults(c *gin.Context) {
	pageInfo := common.GetPageQuery(c)
	startDate := c.Query("start_date")
	endDate := c.Query("end_date")
	channelId, _ := strconv.Atoi(c.Query("channel_id"))
	status := c.Query("status")

	results, total, err := model.GetReconResults(startDate, endDate, channelId, status, pageInfo.GetPage(), pageInfo.GetPageSize())
	if err != nil {
		common.ApiError(c, err)
		return
	}
	pageInfo.SetTotal(int(total))
	pageInfo.SetItems(results)
	common.ApiSuccess(c, pageInfo)
}

func GetReconDiscounts(c *gin.Context) {
	discounts, err := model.GetAllDiscounts()
	if err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, discounts)
}

func SaveReconDiscount(c *gin.Context) {
	var req struct {
		ChannelId    int     `json:"channel_id" binding:"required"`
		Model        string  `json:"model" binding:"required"`
		DiscountRate float64 `json:"discount_rate" binding:"required"`
		Note         string  `json:"note"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		common.ApiErrorMsg(c, "参数错误: "+err.Error())
		return
	}
	if req.DiscountRate <= 0 || req.DiscountRate > 10 {
		common.ApiErrorMsg(c, "折扣比例应在 0~10 之间")
		return
	}

	d := &model.ReconDiscount{
		ChannelId:    req.ChannelId,
		Model:        req.Model,
		DiscountRate: req.DiscountRate,
		Note:         req.Note,
	}
	if err := model.UpsertDiscount(d); err != nil {
		common.ApiError(c, err)
		return
	}
	common.ApiSuccess(c, d)
}

func DeleteReconDiscount(c *gin.Context) {
	idStr := c.Query("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil || id <= 0 {
		common.ApiErrorMsg(c, "无效的 ID")
		return
	}
	if err := model.DeleteDiscountById(id); err != nil {
		common.ApiError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "message": ""})
}

func DownloadUpstreamTemplate(c *gin.Context) {
	csvContent := "recon_date,model,total_requests,total_prompt_tokens,total_completion_tokens,total_amount_cent,currency\n" +
		"2026-03-01,gpt-4o,1000,2000000,500000,3500,USD\n" +
		"2026-03-01,gpt-4o-mini,5000,8000000,2000000,800,USD\n" +
		"2026-03-02,gpt-4o,1200,2400000,600000,4200,USD\n"

	c.Header("Content-Disposition", "attachment; filename=upstream_template.csv")
	c.Header("Content-Type", "text/csv; charset=utf-8")
	c.String(http.StatusOK, csvContent)
}

// --- helpers ---

func isJSON(data []byte) bool {
	var js json.RawMessage
	return json.Unmarshal(data, &js) == nil
}

func parseUpstreamCSV(data []byte) ([]upstreamCSVRow, error) {
	reader := csv.NewReader(bytes.NewReader(data))
	records, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}
	if len(records) < 2 {
		return nil, fmt.Errorf("CSV 至少需要表头+1行数据")
	}

	header := records[0]
	colIdx := make(map[string]int)
	for i, h := range header {
		colIdx[h] = i
	}

	required := []string{"model", "total_amount_cent"}
	for _, r := range required {
		if _, ok := colIdx[r]; !ok {
			return nil, fmt.Errorf("缺少必填列: %s", r)
		}
	}

	var rows []upstreamCSVRow
	for _, record := range records[1:] {
		row := upstreamCSVRow{
			ReconDate: getCSVCol(record, colIdx, "recon_date"),
			Model:     getCSVCol(record, colIdx, "model"),
			Currency:  getCSVCol(record, colIdx, "currency"),
		}
		if v := getCSVCol(record, colIdx, "total_requests"); v != "" {
			row.TotalRequests, _ = strconv.Atoi(v)
		}
		if v := getCSVCol(record, colIdx, "total_prompt_tokens"); v != "" {
			row.TotalPromptTokens, _ = strconv.ParseInt(v, 10, 64)
		}
		if v := getCSVCol(record, colIdx, "total_completion_tokens"); v != "" {
			row.TotalCompletionTokens, _ = strconv.ParseInt(v, 10, 64)
		}
		if v := getCSVCol(record, colIdx, "total_amount_cent"); v != "" {
			row.TotalAmountCent, _ = strconv.ParseInt(v, 10, 64)
		}
		rows = append(rows, row)
	}
	return rows, nil
}

func getCSVCol(row []string, idx map[string]int, col string) string {
	if i, ok := idx[col]; ok && i < len(row) {
		return row[i]
	}
	return ""
}

func diffRate(a, b float64) float64 {
	maxVal := math.Max(a, b)
	if maxVal == 0 {
		return 0
	}
	return math.Abs(a-b) / maxVal
}

func countStatus(results []model.ReconResult, status string) int {
	count := 0
	for _, r := range results {
		if r.Status == status {
			count++
		}
	}
	return count
}
