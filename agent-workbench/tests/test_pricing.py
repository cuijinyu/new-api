from __future__ import annotations

from app.services.pricing import apply_pricing_rows, flatten_pricing


def test_flatten_pricing_handles_all_model_types():
    pricing = {
        "version": "1.0.0",
        "updated_at": "2026-01-01T00:00:00Z",
        "models": [
            {"name": "flat-a", "type": "flat", "flat_tier": False, "ip": 1, "op": 2, "chp": 0.1, "cwp": 0.2, "cwp_1h": 0.3},
            {"name": "mm-a", "type": "multimodal", "ip": 0.3, "op_text": 2.5, "op_image": 30, "note": "image"},
            {
                "name": "tier-a",
                "type": "tiered",
                "flat_tier": True,
                "tiers": [
                    {"min_k": 0, "max_k": 200, "ip": 3, "op": 15, "chp": 0.3, "cwp": 3.75, "cwp_1h": 6},
                    {"min_k": 200, "max_k": -1, "ip": 6, "op": 22.5, "chp": 0.6, "cwp": 7.5, "cwp_1h": 12},
                ],
            },
        ],
    }

    flat = flatten_pricing(pricing)

    assert flat["metadata"]["version"] == "1.0.0"
    assert len(flat["rows"]) == 4
    assert flat["rows"][0]["model"] == "flat-a"
    assert flat["rows"][1]["op_image"] == 30
    assert [row["tier_index"] for row in flat["rows"] if row["model"] == "tier-a"] == [0, 1]


def test_apply_pricing_rows_replaces_models_and_preserves_metadata():
    pricing = {
        "version": "1.0.0",
        "updated_at": "2026-01-01T00:00:00Z",
        "models": [
            {"name": "removed", "type": "flat", "ip": 1, "op": 1},
            {"name": "kept-extra", "type": "flat", "ip": 1, "op": 1, "provider": "x"},
        ],
    }
    rows = [
        {"model": "kept-extra", "type": "flat", "flat_tier": False, "ip": "2", "op": "4", "chp": "0.2", "cwp": "1", "cwp_1h": "1"},
        {"model": "new-mm", "type": "multimodal", "ip": "0.3", "op_text": "2.5", "op_image": "30", "note": "alias"},
    ]

    updated = apply_pricing_rows(pricing, rows)

    assert updated["version"] == "1.0.0"
    assert [model["name"] for model in updated["models"]] == ["kept-extra", "new-mm"]
    assert updated["models"][0]["provider"] == "x"
    assert updated["models"][0]["op"] == 4
    assert updated["models"][1]["op_image"] == 30


def test_apply_pricing_rows_roundtrips_tiered_rows():
    pricing = {"models": []}
    rows = [
        {"model": "tier-a", "type": "tiered", "flat_tier": True, "tier_index": 1, "min_k": 200, "max_k": -1, "ip": 6, "op": 22.5},
        {"model": "tier-a", "type": "tiered", "flat_tier": True, "tier_index": 0, "min_k": 0, "max_k": 200, "ip": 3, "op": 15},
    ]

    updated = apply_pricing_rows(pricing, rows)

    assert updated["models"][0]["type"] == "tiered"
    assert updated["models"][0]["flat_tier"] is True
    assert [tier["min_k"] for tier in updated["models"][0]["tiers"]] == [0, 200]
    assert updated["models"][0]["tiers"][1]["cwp_1h"] == 0
