package serviceinference

import (
	"testing"

	relaycommon "github.com/QuantumNous/new-api/relay/common"
)

func TestRequestDurationSecondsCapsLegacyMetadataDuration(t *testing.T) {
	req := &relaycommon.TaskSubmitReq{
		Metadata: map[string]interface{}{
			"duration": float64(relaycommon.MaxVideoDurationSeconds + 100),
		},
	}
	if got := requestDurationSeconds(req); got != relaycommon.MaxVideoDurationSeconds {
		t.Fatalf("requestDurationSeconds = %v, want %d", got, relaycommon.MaxVideoDurationSeconds)
	}
}
