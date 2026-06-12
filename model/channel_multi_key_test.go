package model

import (
	"testing"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/constant"
)

func TestHandlerMultiKeyUpdateDisablesOnlySelectedKey(t *testing.T) {
	channel := &Channel{
		Id:     1,
		Key:    "key-a\nkey-b",
		Status: common.ChannelStatusEnabled,
		ChannelInfo: ChannelInfo{
			IsMultiKey:             true,
			MultiKeyMode:           constant.MultiKeyModePolling,
			MultiKeyStatusList:     map[int]int{},
			MultiKeyDisabledTime:   map[int]int64{},
			MultiKeyDisabledReason: map[int]string{},
		},
	}

	handlerMultiKeyUpdate(channel, "key-a", common.ChannelStatusAutoDisabled, "rate limited")

	if got := channel.ChannelInfo.MultiKeyStatusList[0]; got != common.ChannelStatusAutoDisabled {
		t.Fatalf("key-a status = %d, want %d", got, common.ChannelStatusAutoDisabled)
	}
	if _, disabled := channel.ChannelInfo.MultiKeyStatusList[1]; disabled {
		t.Fatalf("key-b should remain enabled")
	}
	if channel.Status != common.ChannelStatusEnabled {
		t.Fatalf("channel status = %d, want enabled while one key remains available", channel.Status)
	}
	if channel.ChannelInfo.MultiKeyDisabledReason[0] != "rate limited" {
		t.Fatalf("disabled reason not recorded")
	}
}

func TestHandlerMultiKeyUpdateDisablesChannelWhenAllKeysDisabled(t *testing.T) {
	channel := &Channel{
		Id:     1,
		Key:    "key-a\nkey-b",
		Status: common.ChannelStatusEnabled,
		ChannelInfo: ChannelInfo{
			IsMultiKey:         true,
			MultiKeyMode:       constant.MultiKeyModePolling,
			MultiKeyStatusList: map[int]int{0: common.ChannelStatusAutoDisabled},
		},
	}

	handlerMultiKeyUpdate(channel, "key-b", common.ChannelStatusAutoDisabled, "rate limited")

	if channel.Status != common.ChannelStatusAutoDisabled {
		t.Fatalf("channel status = %d, want auto disabled when all keys are disabled", channel.Status)
	}
	if hasEnabledMultiKey(channel.GetKeys(), channel.ChannelInfo.MultiKeyStatusList) {
		t.Fatalf("expected no enabled keys")
	}
}
