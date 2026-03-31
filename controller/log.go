package controller

import (
	"fmt"
	"net/http"
	"strconv"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/model"

	"github.com/gin-gonic/gin"
)

func GetAllLogs(c *gin.Context) {
	pageInfo := common.GetPageQuery(c)
	logType, _ := strconv.Atoi(c.Query("type"))
	startTimestamp, _ := strconv.ParseInt(c.Query("start_timestamp"), 10, 64)
	endTimestamp, _ := strconv.ParseInt(c.Query("end_timestamp"), 10, 64)
	username := c.Query("username")
	tokenName := c.Query("token_name")
	modelName := c.Query("model_name")
	requestId := c.Query("request_id")
	channel, _ := strconv.Atoi(c.Query("channel"))
	group := c.Query("group")
	logs, total, err := model.GetAllLogs(logType, startTimestamp, endTimestamp, modelName, username, tokenName, requestId, pageInfo.GetStartIdx(), pageInfo.GetPageSize(), channel, group)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	pageInfo.SetTotal(int(total))
	pageInfo.SetItems(logs)
	common.ApiSuccess(c, pageInfo)
	return
}

func GetUserLogs(c *gin.Context) {
	pageInfo := common.GetPageQuery(c)
	userId := c.GetInt("id")
	logType, _ := strconv.Atoi(c.Query("type"))
	startTimestamp, _ := strconv.ParseInt(c.Query("start_timestamp"), 10, 64)
	endTimestamp, _ := strconv.ParseInt(c.Query("end_timestamp"), 10, 64)
	tokenName := c.Query("token_name")
	modelName := c.Query("model_name")
	requestId := c.Query("request_id")
	group := c.Query("group")
	logs, total, err := model.GetUserLogs(userId, logType, startTimestamp, endTimestamp, modelName, tokenName, requestId, pageInfo.GetStartIdx(), pageInfo.GetPageSize(), group)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	pageInfo.SetTotal(int(total))
	pageInfo.SetItems(logs)
	common.ApiSuccess(c, pageInfo)
	return
}

func SearchAllLogs(c *gin.Context) {
	keyword := c.Query("keyword")
	logs, err := model.SearchAllLogs(keyword)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "",
		"data":    logs,
	})
	return
}

func SearchUserLogs(c *gin.Context) {
	keyword := c.Query("keyword")
	userId := c.GetInt("id")
	logs, err := model.SearchUserLogs(userId, keyword)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "",
		"data":    logs,
	})
	return
}

func GetLogByKey(c *gin.Context) {
	key := c.Query("key")
	if key == "" {
		c.JSON(200, gin.H{
			"success": false,
			"message": "key is required",
		})
		return
	}
	startTimestamp, _ := strconv.ParseInt(c.Query("start_timestamp"), 10, 64)
	endTimestamp, _ := strconv.ParseInt(c.Query("end_timestamp"), 10, 64)
	if startTimestamp == 0 || endTimestamp == 0 {
		c.JSON(200, gin.H{
			"success": false,
			"message": "start_timestamp and end_timestamp are required",
		})
		return
	}
	pageInfo := common.GetPageQuery(c)
	if c.Query("p") == "" || c.Query("page_size") == "" {
		c.JSON(200, gin.H{
			"success": false,
			"message": "p and page_size are required",
		})
		return
	}
	logType, _ := strconv.Atoi(c.Query("type"))
	modelName := c.Query("model_name")
	requestId := c.Query("request_id")
	logs, total, err := model.GetLogByKey(key, logType, startTimestamp, endTimestamp, modelName, requestId, pageInfo.GetStartIdx(), pageInfo.GetPageSize())
	if err != nil {
		c.JSON(200, gin.H{
			"success": false,
			"message": err.Error(),
		})
		return
	}
	pageInfo.SetTotal(int(total))
	pageInfo.SetItems(logs)
	common.ApiSuccess(c, pageInfo)
}

func GetLogsStat(c *gin.Context) {
	logType, _ := strconv.Atoi(c.Query("type"))
	startTimestamp, _ := strconv.ParseInt(c.Query("start_timestamp"), 10, 64)
	endTimestamp, _ := strconv.ParseInt(c.Query("end_timestamp"), 10, 64)
	tokenName := c.Query("token_name")
	username := c.Query("username")
	modelName := c.Query("model_name")
	channel, _ := strconv.Atoi(c.Query("channel"))
	group := c.Query("group")
	stat := model.SumUsedQuota(logType, startTimestamp, endTimestamp, modelName, username, tokenName, channel, group)
	//tokenNum := model.SumUsedToken(logType, startTimestamp, endTimestamp, modelName, username, "")
	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "",
		"data": gin.H{
			"quota": stat.Quota,
			"rpm":   stat.Rpm,
			"tpm":   stat.Tpm,
		},
	})
	return
}

func GetLogsSelfStat(c *gin.Context) {
	username := c.GetString("username")
	logType, _ := strconv.Atoi(c.Query("type"))
	startTimestamp, _ := strconv.ParseInt(c.Query("start_timestamp"), 10, 64)
	endTimestamp, _ := strconv.ParseInt(c.Query("end_timestamp"), 10, 64)
	tokenName := c.Query("token_name")
	modelName := c.Query("model_name")
	channel, _ := strconv.Atoi(c.Query("channel"))
	group := c.Query("group")
	quotaNum := model.SumUsedQuota(logType, startTimestamp, endTimestamp, modelName, username, tokenName, channel, group)
	//tokenNum := model.SumUsedToken(logType, startTimestamp, endTimestamp, modelName, username, tokenName)
	c.JSON(200, gin.H{
		"success": true,
		"message": "",
		"data": gin.H{
			"quota": quotaNum.Quota,
			"rpm":   quotaNum.Rpm,
			"tpm":   quotaNum.Tpm,
			//"token": tokenNum,
		},
	})
	return
}

func DeleteHistoryLogs(c *gin.Context) {
	targetTimestamp, _ := strconv.ParseInt(c.Query("target_timestamp"), 10, 64)
	if targetTimestamp == 0 {
		c.JSON(http.StatusOK, gin.H{
			"success": false,
			"message": "target timestamp is required",
		})
		return
	}
	count, err := model.DeleteOldLog(c.Request.Context(), targetTimestamp, 100)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "",
		"data":    count,
	})
	return
}

func writeLogsCSV(c *gin.Context, logs []*model.Log) {
	filename := fmt.Sprintf("logs_%s.csv", time.Now().Format("20060102_150405"))
	c.Header("Content-Type", "text/csv; charset=utf-8")
	c.Header("Content-Disposition", fmt.Sprintf("attachment; filename=%s", filename))
	// UTF-8 BOM for Excel compatibility
	c.Writer.Write([]byte{0xEF, 0xBB, 0xBF})

	c.Writer.WriteString("Time,Type,Username,Token,Model,Prompt Tokens,Completion Tokens,Quota,Use Time(s),Stream,Group,IP\n")
	for _, log := range logs {
		ts := time.Unix(log.CreatedAt, 0).Format("2006-01-02 15:04:05")
		typeName := logTypeName(log.Type)
		c.Writer.WriteString(fmt.Sprintf("%s,%s,%s,%s,%s,%d,%d,%d,%d,%t,%s,%s\n",
			ts, typeName, csvEscape(log.Username), csvEscape(log.TokenName),
			csvEscape(log.ModelName), log.PromptTokens, log.CompletionTokens,
			log.Quota, log.UseTime, log.IsStream, csvEscape(log.Group), log.Ip))
	}
}

func logTypeName(t int) string {
	switch t {
	case model.LogTypeTopup:
		return "topup"
	case model.LogTypeConsume:
		return "consume"
	case model.LogTypeManage:
		return "manage"
	case model.LogTypeSystem:
		return "system"
	case model.LogTypeError:
		return "error"
	case model.LogTypeRefund:
		return "refund"
	default:
		return "unknown"
	}
}

func csvEscape(s string) string {
	for _, ch := range s {
		if ch == ',' || ch == '"' || ch == '\n' || ch == '\r' {
			return "\"" + fmt.Sprintf("%s", s) + "\""
		}
	}
	return s
}

func ExportUserLogs(c *gin.Context) {
	userId := c.GetInt("id")
	logType, _ := strconv.Atoi(c.Query("type"))
	startTimestamp, _ := strconv.ParseInt(c.Query("start_timestamp"), 10, 64)
	endTimestamp, _ := strconv.ParseInt(c.Query("end_timestamp"), 10, 64)
	tokenName := c.Query("token_name")
	modelName := c.Query("model_name")
	group := c.Query("group")

	if startTimestamp == 0 || endTimestamp == 0 {
		common.ApiErrorMsg(c, "start_timestamp and end_timestamp are required")
		return
	}
	maxRange := int64(31 * 24 * 3600)
	if endTimestamp-startTimestamp > maxRange {
		common.ApiErrorMsg(c, "time range cannot exceed 31 days")
		return
	}

	logs, err := model.ExportLogsByUser(userId, logType, startTimestamp, endTimestamp, modelName, tokenName, group)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	writeLogsCSV(c, logs)
}

func ExportAllLogs(c *gin.Context) {
	logType, _ := strconv.Atoi(c.Query("type"))
	startTimestamp, _ := strconv.ParseInt(c.Query("start_timestamp"), 10, 64)
	endTimestamp, _ := strconv.ParseInt(c.Query("end_timestamp"), 10, 64)
	username := c.Query("username")
	tokenName := c.Query("token_name")
	modelName := c.Query("model_name")
	channel, _ := strconv.Atoi(c.Query("channel"))
	group := c.Query("group")

	if startTimestamp == 0 || endTimestamp == 0 {
		common.ApiErrorMsg(c, "start_timestamp and end_timestamp are required")
		return
	}
	maxRange := int64(31 * 24 * 3600)
	if endTimestamp-startTimestamp > maxRange {
		common.ApiErrorMsg(c, "time range cannot exceed 31 days")
		return
	}

	logs, err := model.ExportAllLogs(logType, startTimestamp, endTimestamp, modelName, username, tokenName, channel, group)
	if err != nil {
		common.ApiError(c, err)
		return
	}
	writeLogsCSV(c, logs)
}
