package common

import (
	"encoding/json"
	"testing"
)

func TestValidateTaskDurationRejectsInvalidSeconds(t *testing.T) {
	err := ValidateTaskDuration(TaskSubmitReq{Seconds: "999999999999999999999999"})
	if err == nil {
		t.Fatal("ValidateTaskDuration accepted an unparsable seconds value")
	}
}

func TestValidateTaskDurationRejectsMetadataDurationOverflow(t *testing.T) {
	err := ValidateTaskDuration(TaskSubmitReq{
		Metadata: map[string]interface{}{
			"duration": json.Number("601"),
		},
	})
	if err == nil {
		t.Fatal("ValidateTaskDuration accepted metadata.duration above the cap")
	}
}

func TestValidateTaskDurationAllowsFractionalMetadataDuration(t *testing.T) {
	err := ValidateTaskDuration(TaskSubmitReq{
		Metadata: map[string]interface{}{
			"duration": "12.5",
		},
	})
	if err != nil {
		t.Fatalf("ValidateTaskDuration rejected valid fractional metadata duration: %v", err)
	}
}
