package operation_setting

import (
	"os"
	"strconv"

	"github.com/QuantumNous/new-api/setting/config"
)

type MonitorSetting struct {
	AutoTestChannelEnabled     bool    `json:"auto_test_channel_enabled"`
	AutoTestChannelMinutes     float64 `json:"auto_test_channel_minutes"`
	FingerprintEnabled         bool    `json:"fingerprint_enabled"`
	FingerprintIntervalMinutes float64 `json:"fingerprint_interval_minutes"`
}

// 默认配置
var monitorSetting = MonitorSetting{
	AutoTestChannelEnabled:     false,
	AutoTestChannelMinutes:     10,
	FingerprintEnabled:         false,
	FingerprintIntervalMinutes: 60,
}

func init() {
	// 注册到全局配置管理器
	config.GlobalConfig.Register("monitor_setting", &monitorSetting)
}

func GetMonitorSetting() *MonitorSetting {
	if os.Getenv("CHANNEL_TEST_FREQUENCY") != "" {
		frequency, err := strconv.Atoi(os.Getenv("CHANNEL_TEST_FREQUENCY"))
		if err == nil && frequency > 0 {
			monitorSetting.AutoTestChannelEnabled = true
			monitorSetting.AutoTestChannelMinutes = float64(frequency)
		}
	}
	if os.Getenv("FINGERPRINT_INTERVAL") != "" {
		interval, err := strconv.Atoi(os.Getenv("FINGERPRINT_INTERVAL"))
		if err == nil && interval > 0 {
			monitorSetting.FingerprintEnabled = true
			monitorSetting.FingerprintIntervalMinutes = float64(interval)
		}
	}
	return &monitorSetting
}
