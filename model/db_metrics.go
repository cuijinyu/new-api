package model

import (
	"time"

	"gorm.io/gorm"
)

// DBMetricsEmitter is set by the middleware package to avoid import cycles.
var DBMetricsEmitter func(operation string, latencyMs float64, isSlow bool)

const dbSlowThresholdMs = 100.0

type dbMetricsStartKey struct{}

func RegisterDBMetricsCallbacks(db *gorm.DB) {
	if db == nil {
		return
	}
	_ = db.Callback().Query().Before("gorm:query").Register("metrics:before_query", beforeQuery)
	_ = db.Callback().Query().After("gorm:query").Register("metrics:after_query", afterQueryCallback("Query"))
	_ = db.Callback().Create().Before("gorm:create").Register("metrics:before_create", beforeQuery)
	_ = db.Callback().Create().After("gorm:create").Register("metrics:after_create", afterQueryCallback("Create"))
	_ = db.Callback().Update().Before("gorm:update").Register("metrics:before_update", beforeQuery)
	_ = db.Callback().Update().After("gorm:update").Register("metrics:after_update", afterQueryCallback("Update"))
	_ = db.Callback().Delete().Before("gorm:delete").Register("metrics:before_delete", beforeQuery)
	_ = db.Callback().Delete().After("gorm:delete").Register("metrics:after_delete", afterQueryCallback("Delete"))
}

func beforeQuery(db *gorm.DB) {
	db.InstanceSet("metrics:start_time", time.Now())
}

func afterQueryCallback(operation string) func(*gorm.DB) {
	return func(db *gorm.DB) {
		if DBMetricsEmitter == nil {
			return
		}
		val, ok := db.InstanceGet("metrics:start_time")
		if !ok {
			return
		}
		start, ok := val.(time.Time)
		if !ok {
			return
		}
		latencyMs := float64(time.Since(start).Microseconds()) / 1000.0
		isSlow := latencyMs >= dbSlowThresholdMs
		DBMetricsEmitter(operation, latencyMs, isSlow)
	}
}
