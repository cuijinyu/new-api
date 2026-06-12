package controller

import "testing"

func TestBuildModelsDevTieredPricing(t *testing.T) {
	var tier modelsDevTier
	tier.Input = 10
	tier.Output = 45
	tier.CacheRead = 1
	tier.Tier.Type = "context"
	tier.Tier.Size = 272000

	cfg := buildModelsDevTieredPricing(5, 30, 0.5, 0, []modelsDevTier{tier})
	if cfg == nil || !cfg.Enabled {
		t.Fatal("expected enabled tiered pricing")
	}
	if len(cfg.Tiers) != 2 {
		t.Fatalf("tier count = %d, want 2", len(cfg.Tiers))
	}
	if cfg.Tiers[0].MinTokens != 0 || cfg.Tiers[0].MaxTokens != 272 {
		t.Fatalf("base tier range = %d-%d, want 0-272", cfg.Tiers[0].MinTokens, cfg.Tiers[0].MaxTokens)
	}
	if cfg.Tiers[1].MinTokens != 272 || cfg.Tiers[1].MaxTokens != -1 {
		t.Fatalf("upper tier range = %d-%d, want 272--1", cfg.Tiers[1].MinTokens, cfg.Tiers[1].MaxTokens)
	}
	if cfg.Tiers[1].InputPrice != 10 || cfg.Tiers[1].OutputPrice != 45 || cfg.Tiers[1].CacheHitPrice != 1 {
		t.Fatalf("upper tier prices = %#v", cfg.Tiers[1])
	}
}

func TestBuildLiteLLMTieredPricing(t *testing.T) {
	cfg := buildLiteLLMTieredPricing(2, 12, 0.2, 0, map[int]*liteLLMThresholdCost{
		200: {
			Input:     4,
			Output:    18,
			CacheRead: 0.4,
		},
	})
	if cfg == nil || !cfg.Enabled {
		t.Fatal("expected enabled tiered pricing")
	}
	if len(cfg.Tiers) != 2 {
		t.Fatalf("tier count = %d, want 2", len(cfg.Tiers))
	}
	if cfg.Tiers[0].MaxTokens != 200 || cfg.Tiers[1].MinTokens != 200 || cfg.Tiers[1].MaxTokens != -1 {
		t.Fatalf("unexpected tier ranges: %#v", cfg.Tiers)
	}
	if cfg.Tiers[1].InputPrice != 4 || cfg.Tiers[1].OutputPrice != 18 || cfg.Tiers[1].CacheHitPrice != 0.4 {
		t.Fatalf("unexpected upper tier prices: %#v", cfg.Tiers[1])
	}
}
