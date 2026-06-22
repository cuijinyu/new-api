"""折扣展开与写回单元测试。"""

from __future__ import annotations

from app.services.discounts import apply_discount_rows, flatten_discounts


def test_flatten_and_apply_discount_rows_roundtrip():
    discounts = {
        "cost_discounts": {
            "defaults": {"*": 1.0},
            "by_channel": {
                "25": {"_name": "MateCloud", "*": 0.35, "claude-3": 0.4},
            },
        },
        "revenue_discounts": {
            "defaults": {"*": 1.0},
            "by_user": {
                "89": {"_name": "客户A", "*": 0.8},
            },
        },
    }
    flat = flatten_discounts(discounts)
    assert len(flat["cost_rows"]) == 2
    assert len(flat["revenue_rows"]) == 1
    assert flat["cost_rows"][0]["channel_id"] == "25"

    updated_rows = [
        {"channel_id": "25", "channel_name": "MateCloud", "model": "*", "discount": 0.3},
        {"channel_id": "26", "channel_name": "Bedrock", "model": "*", "discount": 0.4},
    ]
    new_discounts = apply_discount_rows(discounts, updated_rows, flat["revenue_rows"])
    assert "26" in new_discounts["cost_discounts"]["by_channel"]
    assert new_discounts["cost_discounts"]["by_channel"]["25"]["*"] == 0.3


def test_normalize_kpi_payload_defaults():
    from app.services.billing import normalize_kpi_payload

    payload = normalize_kpi_payload(None)
    assert payload["total_usd"] == 0.0
    assert payload["total_calls"] == 0


def test_apply_discount_rows_drops_removed_channels():
    """全局折扣原地覆盖：未提交的渠道应被移除，而非累积。"""
    discounts = {
        "cost_discounts": {"defaults": {"*": 1.0}, "by_channel": {"25": {"*": 0.35}, "26": {"*": 0.4}}},
        "revenue_discounts": {"defaults": {"*": 1.0}, "by_user": {}},
    }
    new_discounts = apply_discount_rows(discounts, [{"channel_id": "25", "model": "*", "discount": 0.3}], [])
    by_channel = new_discounts["cost_discounts"]["by_channel"]
    assert "25" in by_channel and "26" not in by_channel


def test_bill_document_status_fixture_is_draft():
    from app.services.billing import bill_document_status_for_type

    status = bill_document_status_for_type("internal_customer_bill", "real", {"bill.xlsx": "s3://x"}, is_fixture=True)
    assert status == "DRAFT"
    status_real = bill_document_status_for_type("internal_customer_bill", "real", {"bill.xlsx": "s3://x"}, is_fixture=False)
    assert status_real == "GENERATED"


def test_bill_document_status_partial_artifacts():
    from app.services.billing import bill_document_status_for_type, resolve_billing_run_status

    assert bill_document_status_for_type("internal_customer_bill", "real", {"bill.xlsx": "s3://x"}) == "GENERATED"
    assert bill_document_status_for_type("internal_customer_bill", "real", {}) == "FAILED"
    assert resolve_billing_run_status("", {"bill.xlsx": "s3://x"}) == ("completed", "COMPLETED")
    assert resolve_billing_run_status("exit -9", {"bill.xlsx": "s3://x"}) == ("partial", "FAILED")
    assert resolve_billing_run_status("exit -9", {}) == ("failed", "FAILED")


def test_summarize_batch_completion_states():
    from app.services.billing import summarize_batch_completion

    assert summarize_batch_completion(["COMPLETED"], ["GENERATED"], expected_jobs=1)["status"] == "COMPLETED"
    assert summarize_batch_completion(["RUNNING"], ["CREATED"], expected_jobs=1)["status"] == "RENDERING"
    assert summarize_batch_completion(["FAILED"], ["FAILED"], expected_jobs=1)["status"] == "FAILED"
    assert summarize_batch_completion(["COMPLETED", "FAILED"], ["GENERATED", "FAILED"], expected_jobs=2)["status"] == "PARTIAL_FAILED"
