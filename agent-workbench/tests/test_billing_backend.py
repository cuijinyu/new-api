"""Unit tests for billing backend pure helpers: discounts + artifact uri parsing."""

from __future__ import annotations

from app.services.artifacts import ArtifactStore, content_disposition
from app.services.discounts import apply_discount_rows, flatten_discounts


def test_flatten_discounts_roundtrip_shape():
    discounts = {
        "cost_discounts": {
            "by_channel": {
                "25": {"_name": "GMICloud", "*": 0.9, "claude-opus": 0.8},
            }
        },
        "revenue_discounts": {
            "by_user": {
                "89": {"_name": "acme", "*": 0.95},
            }
        },
    }
    flat = flatten_discounts(discounts)
    assert {"channel_id": "25", "channel_name": "GMICloud", "model": "*", "discount": 0.9} in flat["cost_rows"]
    assert {"channel_id": "25", "channel_name": "GMICloud", "model": "claude-opus", "discount": 0.8} in flat["cost_rows"]
    assert flat["revenue_rows"] == [
        {"user_id": "89", "user_name": "acme", "model": "*", "discount": 0.95}
    ]


def test_flatten_discounts_none_safe():
    assert flatten_discounts(None) == {"cost_rows": [], "revenue_rows": []}


def test_apply_discount_rows_builds_nested_structure():
    result = apply_discount_rows(
        {},
        cost_rows=[{"channel_id": 25, "channel_name": "GMICloud", "model": "*", "discount": 0.9}],
        revenue_rows=[{"user_id": 89, "user_name": "acme", "model": "gpt-4", "discount": 0.8}],
    )
    assert result["cost_discounts"]["by_channel"]["25"]["_name"] == "GMICloud"
    assert result["cost_discounts"]["by_channel"]["25"]["*"] == 0.9
    assert result["revenue_discounts"]["by_user"]["89"]["gpt-4"] == 0.8
    # round-trips back through flatten
    flat = flatten_discounts(result)
    assert any(r["channel_id"] == "25" for r in flat["cost_rows"])
    assert any(r["user_id"] == "89" for r in flat["revenue_rows"])


def test_split_s3_uri():
    assert ArtifactStore.split_s3_uri("s3://my-bucket/path/to/file.xlsx") == ("my-bucket", "path/to/file.xlsx")
    assert ArtifactStore.split_s3_uri("file:///tmp/x.csv") == ("", "")
    assert ArtifactStore.split_s3_uri("") == ("", "")


def test_parse_split_entity_from_filename():
    from app.services.billing import parse_split_artifact_entity_from_filename, parse_split_entity_from_filename

    assert parse_split_entity_from_filename("bill_2026-05_user123.xlsx") == ("customer", "123")
    assert parse_split_entity_from_filename("daily_report_2026-06-20_ch65.xlsx") == ("channel", "65")
    assert parse_split_entity_from_filename("bill_2026-05.xlsx") is None
    assert parse_split_entity_from_filename("bill_2026-05_detail_user123.zip") is None
    assert parse_split_artifact_entity_from_filename("bill_2026-05_user123_detail_customer.xlsx") == ("customer", "123")
    assert parse_split_artifact_entity_from_filename("bill_2026-05_ch65_detail.csv.zip") == ("channel", "65")
    assert parse_split_artifact_entity_from_filename("bill_2026-05_detail.csv.zip") is None


def test_split_generated_files_groups_target_detail_artifacts():
    from app.services.billing import _split_generated_files_by_target

    grouped = _split_generated_files_by_target(
        {
            "bill_2026-05.xlsx": "s3://bucket/bill.xlsx",
            "bill_2026-05_detail.csv.zip": "s3://bucket/detail.zip",
            "bill_2026-05_user42_customer.xlsx": "s3://bucket/user42.xlsx",
            "bill_2026-05_user42_detail_customer.xlsx": "s3://bucket/user42-detail.xlsx",
            "bill_2026-05_user7_customer.xlsx": "s3://bucket/user7.xlsx",
        }
    )

    by_target = {(target_type, target_id): child_generated for _, _, target_type, target_id, child_generated in grouped}
    assert by_target[("customer", "42")] == {
        "bill_2026-05_user42_customer.xlsx": "s3://bucket/user42.xlsx",
        "bill_2026-05_user42_detail_customer.xlsx": "s3://bucket/user42-detail.xlsx",
    }
    assert by_target[("customer", "7")] == {
        "bill_2026-05_user7_customer.xlsx": "s3://bucket/user7.xlsx",
    }


def test_build_athena_bill_command_always_requests_detail():
    from app.services.billing import build_athena_bill_command

    job = {
        "id": "job-1",
        "bill_type": "customer_invoice",
        "request_payload": {"metadata": {"detail": False}},
    }
    run = {"id": "run-1", "month": "2026-05", "bill_type": "customer_invoice"}
    config = {"id": "cfg-1", "version": "local-v0"}

    command = build_athena_bill_command(job, run, config, "bills/customer_invoice/2026/05/all/run-1")

    assert "--detail" in command["argv"]


def test_build_daily_bill_command_requests_detail():
    from app.services.billing import build_athena_bill_command

    job = {
        "id": "job-1",
        "bill_type": "daily_channel_cost_snapshot",
        "request_payload": {"metadata": {"split_channels": True}},
    }
    run = {"id": "run-1", "month": "2026-06-20", "bill_type": "daily_channel_cost_snapshot"}
    config = {"id": "cfg-1", "version": "local-v0"}

    command = build_athena_bill_command(job, run, config, "bills/daily_channel_cost_snapshot/2026/06/all/run-1")

    assert command["original_cli"] == "python bill_cli.py daily"
    assert "--detail" in command["argv"]
    assert command["argv"][command["argv"].index("--date") + 1] == "2026-06-20"


def test_split_bill_summary_uses_target_metrics_not_parent_totals():
    from app.services.billing import _build_split_bill_document_summary

    summary = _build_split_bill_document_summary(
        {
            "status": "completed",
            "bill_type": "customer_invoice",
            "month": "2026-05",
            "total_usd": 100.0,
            "total_calls": 20,
            "generated_files": {"bill_2026-05.xlsx": "s3://bucket/parent.xlsx"},
            "real_execution": {"stdout": "s3://bucket/stdout.log", "stderr": "s3://bucket/stderr.log", "stderr_text": "large log"},
            "bill_summary": {
                "per_customer_summary": {
                    "42": {
                        "total_usd": 7.5,
                        "total_calls": 3,
                        "unique_models": 2,
                    }
                }
            },
        },
        child_generated={"bill_2026-05_user42.xlsx": "s3://bucket/user42.xlsx"},
        parent_document_id="billdoc-parent",
        target_type="customer",
        target_id="42",
        schedule_run_id="sr-1",
        batch_id="batch-1",
    )

    assert summary["total_usd"] == 7.5
    assert summary["total_calls"] == 3
    assert summary["parent_total_usd"] == 100.0
    assert summary["generated_files"] == {"bill_2026-05_user42.xlsx": "s3://bucket/user42.xlsx"}
    assert summary["split_metric_source"] == "bill_summary.per_customer_summary"
    assert summary["real_execution"] == {"stdout": "s3://bucket/stdout.log", "stderr": "s3://bucket/stderr.log"}


def test_split_bill_summary_marks_missing_metrics_without_copying_parent_totals():
    from app.services.billing import _build_split_bill_document_summary

    summary = _build_split_bill_document_summary(
        {
            "status": "completed",
            "bill_type": "channel_cost_bill",
            "month": "2026-05",
            "total_usd": 100.0,
            "total_calls": 20,
            "bill_summary": {"per_channel_summary": {}},
        },
        child_generated={"bill_2026-05_ch65.xlsx": "s3://bucket/ch65.xlsx"},
        parent_document_id="billdoc-parent",
        target_type="channel",
        target_id="65",
        schedule_run_id=None,
        batch_id=None,
    )

    assert "total_usd" not in summary
    assert "total_calls" not in summary
    assert summary["parent_total_usd"] == 100.0
    assert summary["metrics_missing"] is True
    assert summary["split_metric_source"] == "unavailable"


def test_presign_disabled_returns_none():
    store = ArtifactStore()
    store.bucket = None  # local file:// dev mode
    assert store.presign_url("s3://b/k") is None
    assert store.presign_url("file:///tmp/x") is None


def test_put_file_local_copy(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("hello file upload", encoding="utf-8")
    store = ArtifactStore(bucket="", local_dir=str(tmp_path / "artifacts"))

    uri = store.put_file("billing/run-1/source.txt", source, "text/plain")

    assert uri.startswith("file://")
    stored = tmp_path / "artifacts" / "billing" / "run-1" / "source.txt"
    assert stored.read_text(encoding="utf-8") == "hello file upload"


def test_content_disposition_non_ascii():
    header = content_disposition("月度账单.xlsx")
    assert header.startswith("attachment; filename=")
    assert "filename*=UTF-8''" in header


def test_collect_bill_document_reference_artifacts():
    from app.services.billing import collect_bill_document_reference_artifacts

    document = {
        "id": "billdoc-1",
        "s3_uri": "s3://agent-workbench-bills/billing/run-1/bill_2026-05.xlsx",
        "summary": {
            "generated_files": {
                "bill_summary.json": "s3://agent-workbench-bills/billing/run-1/bill_summary.json",
                "bill_2026-05.xlsx": "s3://agent-workbench-bills/billing/run-1/bill_2026-05.xlsx",
            },
            "real_execution": {
                "stdout": "s3://agent-workbench-bills/billing/run-1/stdout.log",
                "stderr": "s3://agent-workbench-bills/billing/run-1/stderr.log",
            },
        },
    }

    artifacts = collect_bill_document_reference_artifacts(document)

    assert [item["filename"] for item in artifacts] == [
        "bill_summary.json",
        "bill_2026-05.xlsx",
        "stdout.log",
        "stderr.log",
    ]
    assert all(item["s3_uri"].startswith("s3://agent-workbench-bills/") for item in artifacts)
