"""Focused tests for Athena report output helpers."""

from __future__ import annotations

import csv
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
ATHENA_WORKER_ROOT = WORKBENCH_ROOT / "athena_worker"
sys.path.insert(0, str(ATHENA_WORKER_ROOT))

import report_builder  # noqa: E402


def test_bill_summary_uses_channel_cost_and_target_maps(tmp_path):
    df = pd.DataFrame(
        {
            "user_id": [7, 7, 8],
            "username": ["alpha", "alpha", "beta"],
            "channel_id": [65, 65, 66],
            "model_name": ["m1", "m2", "m1"],
            "call_count": [2, 3, 5],
            "total_input_tokens": [20, 30, 50],
            "total_output_tokens": [4, 6, 10],
            "revenue_usd": [10.0, 30.0, 60.0],
            "cost_usd": [4.0, 6.0, 15.0],
            "profit_usd": [6.0, 24.0, 45.0],
        }
    )

    path = report_builder._write_bill_summary(
        str(tmp_path),
        "2026-05",
        df,
        bill_type="channel_cost_bill",
        xlsx_path=str(tmp_path / "bill_2026-05.xlsx"),
    )
    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    assert payload["amount_metric"] == "cost_usd"
    assert payload["total_usd"] == 25.0
    assert payload["revenue_usd"] == 100.0
    assert payload["per_channel_summary"]["65"]["total_usd"] == 10.0
    assert payload["per_channel_summary"]["65"]["total_calls"] == 5
    assert payload["per_customer_summary"]["7"]["total_usd"] == 10.0


def test_daily_report_writes_cost_summary_for_bill_library(tmp_path, monkeypatch):
    monkeypatch.setattr(report_builder, "COST_MONITOR_AVAILABLE", False)
    monkeypatch.setattr(report_builder.pricing_engine, "get_cost_discount", lambda channel_id, model: 0.5)
    monkeypatch.setattr(report_builder.pricing_engine, "get_revenue_discount", lambda user_id, model: 0.8)

    def fake_run_query_cached(sql: str, no_cache: bool = False):
        if "GROUP BY user_id, username, channel_id, model_name" in sql:
            return pd.DataFrame(
                {
                    "user_id": [7],
                    "username": ["alpha"],
                    "channel_id": [65],
                    "model_name": ["unpriced-model"],
                    "call_count": [3],
                    "total_input_tokens": [1000],
                    "total_output_tokens": [2000],
                    "total_quota": [5_000_000],
                    "total_usd": [10.0],
                    "total_cache_hit_tokens": [0],
                    "total_cache_write_tokens": [0],
                    "total_cw_5m": [0],
                    "total_cw_1h": [0],
                    "total_cw_remaining": [0],
                    "total_image_output_tokens": [0],
                    "total_image_input_tokens": [0],
                }
            )
        if "GROUP BY user_id, username" in sql:
            return pd.DataFrame({"user_id": [7], "username": ["alpha"], "call_count": [3], "total_usd": [10.0]})
        if "GROUP BY model_name" in sql:
            return pd.DataFrame(
                {
                    "model_name": ["unpriced-model"],
                    "call_count": [3],
                    "total_tokens": [3000],
                    "total_usd": [10.0],
                    "avg_latency_sec": [1.2],
                    "stream_pct": [100.0],
                }
            )
        if "GROUP BY hour" in sql:
            return pd.DataFrame({"hour": [1], "call_count": [3], "total_tokens": [3000], "total_usd": [10.0]})
        return pd.DataFrame(
            {
                "total_calls": [3],
                "unique_users": [1],
                "unique_models": [1],
                "total_input_tokens": [1000],
                "total_output_tokens": [2000],
                "total_quota": [5_000_000],
                "total_usd": [10.0],
            }
        )

    monkeypatch.setattr(report_builder, "run_query_cached", fake_run_query_cached)

    result = report_builder.generate_daily_report(
        "2026-06-20",
        str(tmp_path),
        detail=False,
        split_channels=False,
    )
    paths = result if isinstance(result, list) else [result]
    assert str(tmp_path / "bill_summary.json") in paths

    payload = json.loads((tmp_path / "bill_summary.json").read_text(encoding="utf-8"))

    assert payload["bill_type"] == "daily_channel_cost_snapshot"
    assert payload["snapshot_date"] == "2026-06-20"
    assert payload["amount_metric"] == "cost_usd"
    assert payload["total_usd"] == 5.0
    assert payload["cost_usd"] == 5.0
    assert payload["revenue_usd"] == 8.0
    assert payload["per_channel_summary"]["65"]["total_usd"] == 5.0
    assert payload["per_customer_summary"]["7"]["total_usd"] == 5.0


def test_detail_csv_zip_writes_readable_csv(tmp_path):
    df = pd.DataFrame(
        {
            "request_id": ["req-1", "req-2"],
            "created_at": [1_718_000_000, 1_718_000_060],
            "image_input_tokens": [123, 456],
            "billed_usd": [0.1, 0.2],
        }
    )

    zip_path = report_builder._write_detail_csv_zip(df, "bill_2026-05_detail", str(tmp_path))

    with zipfile.ZipFile(zip_path) as zf:
        assert zf.namelist() == ["bill_2026-05_detail.csv"]
        with zf.open("bill_2026-05_detail.csv") as handle:
            rows = list(csv.DictReader(line.decode("utf-8") for line in handle))

    assert rows == [
        {"request_id": "req-1", "created_at": "1718000000", "billed_usd": "0.1"},
        {"request_id": "req-2", "created_at": "1718000060", "billed_usd": "0.2"},
    ]


def test_customer_detail_large_fallback_streams_without_aggregation(tmp_path, monkeypatch):
    monkeypatch.setattr(report_builder, "DETAIL_XLSX_ROW_LIMIT", 1)

    def fail_aggregation(*args, **kwargs):
        raise AssertionError("large customer detail fallback should not aggregate")

    monkeypatch.setattr(report_builder, "_customer_daily_key_model_rows", fail_aggregation)
    df = pd.DataFrame(
        {
            "request_id": ["req-1", "req-2"],
            "created_at": [1_718_000_000, 1_718_000_060],
            "model_name": ["m", "m"],
            "token_name": ["t", "t"],
            "prompt_tokens": [10, 20],
            "completion_tokens": [3, 4],
            "cache_hit_tokens": [0, 0],
            "cw_5m": [1, 2],
            "cw_remaining": [2, 3],
            "cw_1h": [0, 0],
            "list_price_usd": [0.1, 0.2],
            "revenue_discount": [1.0, 1.0],
            "revenue_usd": [0.1, 0.2],
        }
    )

    zip_path = report_builder._write_detail_xlsx_customer(
        df, "2026-05", str(tmp_path)
    )

    assert zip_path.endswith(".csv.zip")
    with zipfile.ZipFile(zip_path) as zf:
        assert zf.namelist() == ["bill_2026-05_detail_customer.csv"]
        with zf.open("bill_2026-05_detail_customer.csv") as handle:
            rows = list(csv.DictReader(line.decode("utf-8") for line in handle))

    assert "cw_remaining" not in rows[0]
    assert rows[0]["created_at"].startswith("2024-")
    assert rows[0]["cw_5m"] == "3.0"
    assert rows[1]["cw_5m"] == "5.0"
