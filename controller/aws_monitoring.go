package controller

import (
	"context"
	"net/http"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/service"

	"github.com/gin-gonic/gin"
)

func GetAWSMonitoringOverview(c *gin.Context) {
	req := service.ParseAWSMonitoringRequest(
		c.Query("hours"),
		c.Query("period"),
		c.Query("channel_limit"),
	)

	ctx, cancel := context.WithTimeout(c.Request.Context(), 30*time.Second)
	defer cancel()

	overview, err := service.GetAWSMonitoringOverview(ctx, req)
	if err != nil {
		common.ApiError(c, err)
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "",
		"data":    overview,
	})
}

func QueryAWSMonitoringLogs(c *gin.Context) {
	var body struct {
		Hours int    `json:"hours"`
		Limit int    `json:"limit"`
		Query string `json:"query"`
	}
	_ = c.ShouldBindJSON(&body)
	req := service.ParseAWSLogQueryRequest(
		c.DefaultQuery("hours", ""),
		c.DefaultQuery("limit", ""),
		body.Query,
	)
	if body.Hours > 0 {
		req.Hours = body.Hours
	}
	if body.Limit > 0 {
		req.Limit = body.Limit
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 25*time.Second)
	defer cancel()

	result, err := service.GetAWSLogQuery(ctx, req)
	if err != nil {
		common.ApiError(c, err)
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "",
		"data":    result,
	})
}
