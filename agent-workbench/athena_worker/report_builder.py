"""
Excel 报表生成器 — 月度账单、日报、异常报告、重算报告、对账报告

使用 xlsxwriter 生成带格式的 .xlsx 文件（对齐 gen_bill.py 样式）。
"""

import gc
import gzip
import zipfile
import os
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd
import xlsxwriter

from athena_engine import (run_query_cached, run_queries_parallel_iter,
                          upload_and_sign, QUOTA_TO_USD, get_session_cost_summary)
import queries
import pricing_engine
from logging_config import get_logger, log_report_complete, log_error

logger = get_logger("report_builder")


def _numeric_sum(df: pd.DataFrame, column: str) -> float:
    if column not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[column], errors="coerce").fillna(0).sum())


def _int_numeric_sum(df: pd.DataFrame, column: str) -> int:
    return int(round(_numeric_sum(df, column)))


def _summary_amount_column(bill_type: str | None) -> str:
    if bill_type in {"channel_cost_bill", "daily_channel_cost_snapshot"}:
        return "cost_usd"
    return "revenue_usd"


def _fallback_amount_column(df: pd.DataFrame, preferred: str) -> str | None:
    for column in (preferred, "revenue_usd", "cost_usd", "list_price_usd", "billed_usd", "expected_usd"):
        if column in df.columns:
            return column
    return None


def _metric_summary(df: pd.DataFrame, bill_type: str | None) -> dict:
    preferred = _summary_amount_column(bill_type)
    amount_column = _fallback_amount_column(df, preferred)
    total_usd = _numeric_sum(df, amount_column) if amount_column else 0.0
    payload = {
        "total_usd": round(total_usd, 4),
        "amount_metric": amount_column or preferred,
        "total_calls": _int_numeric_sum(df, "call_count") if "call_count" in df.columns else int(len(df)),
        "unique_users": int(df["user_id"].nunique()) if "user_id" in df.columns else 0,
        "unique_models": int(df["model_name"].nunique()) if "model_name" in df.columns else 0,
        "total_input_tokens": _int_numeric_sum(df, "total_input_tokens") if "total_input_tokens" in df.columns else 0,
        "total_output_tokens": _int_numeric_sum(df, "total_output_tokens") if "total_output_tokens" in df.columns else 0,
    }
    for column in ("revenue_usd", "cost_usd", "profit_usd", "list_price_usd", "billed_usd", "expected_usd"):
        if column in df.columns:
            payload[column] = round(_numeric_sum(df, column), 4)
    return payload


def _summary_key(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return str(int(value))
    return str(value)


def _first_non_empty(df: pd.DataFrame, column: str) -> str | None:
    if column not in df.columns:
        return None
    values = df[column].dropna()
    if values.empty:
        return None
    value = str(values.iloc[0]).strip()
    return value or None


def _target_summary_map(df: pd.DataFrame, key_column: str, bill_type: str | None) -> dict[str, dict]:
    if key_column not in df.columns or df.empty:
        return {}
    result: dict[str, dict] = {}
    for key, group in df.groupby(key_column, dropna=True):
        target_id = _summary_key(key)
        if not target_id:
            continue
        summary = _metric_summary(group, bill_type)
        if key_column == "user_id":
            label = _first_non_empty(group, "username")
            if label:
                summary["username"] = label
        if key_column == "channel_id":
            label = _first_non_empty(group, "channel_name")
            if label:
                summary["channel_name"] = label
        result[target_id] = summary
    return result


def _infer_monthly_bill_type(
    bill_type: str | None,
    *,
    customer_view: bool,
    channel_id: int | None,
    channel_ids: list[int] | None,
) -> str:
    if bill_type:
        return bill_type
    if customer_view:
        return "customer_invoice"
    if channel_id is not None or channel_ids:
        return "channel_cost_bill"
    return "internal_customer_bill"


def _write_bill_summary(
    output_dir: str,
    year_month: str,
    df_full: pd.DataFrame | None = None,
    *,
    bill_type: str | None = None,
    detail_path: str | None = None,
    xlsx_path: str | None = None,
    per_customer_paths: list[str] | None = None,
    per_channel_paths: list[str] | None = None,
    extra: dict | None = None,
) -> str:
    import json

    if df_full is not None and not df_full.empty:
        payload = {
            "month": year_month,
            "bill_type": bill_type,
            "xlsx": os.path.basename(xlsx_path) if xlsx_path else None,
            "detail": os.path.basename(detail_path) if detail_path else None,
            "per_customer": [os.path.basename(path) for path in (per_customer_paths or [])],
            "per_channel": [os.path.basename(path) for path in (per_channel_paths or [])],
            "per_customer_summary": _target_summary_map(df_full, "user_id", bill_type),
            "per_channel_summary": _target_summary_map(df_full, "channel_id", bill_type),
        }
        payload.update(_metric_summary(df_full, bill_type))
    else:
        payload = {
            "month": year_month,
            "bill_type": bill_type,
            "total_usd": 0.0,
            "amount_metric": _summary_amount_column(bill_type),
            "total_calls": 0,
            "unique_users": 0,
            "unique_models": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "xlsx": os.path.basename(xlsx_path) if xlsx_path else None,
            "detail": None,
            "per_customer": [],
            "per_channel": [],
            "per_customer_summary": {},
            "per_channel_summary": {},
        }
    if extra:
        payload.update(extra)
    path = os.path.join(output_dir, "bill_summary.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path

# Import cost monitor for query cost tracking
try:
    from cost_monitor import (
        get_total_cost,
        get_cost_summary,
        get_query_costs,
        COST_PER_TB,
    )
    COST_MONITOR_AVAILABLE = True
except ImportError:
    COST_MONITOR_AVAILABLE = False

    def get_total_cost():
        return 0.0

    def get_cost_summary():
        return {}

    def get_query_costs():
        return {}

    COST_PER_TB = 5.0

# ---------------------------------------------------------------------------
# xlsxwriter style system (ported from gen_bill.py)
# ---------------------------------------------------------------------------

BORDER_PROPS = {"border": 1, "border_color": "#B0C4DE"}

USD2 = '"$"#,##0.00'
USD4 = '"$"#,##0.0000'
USD6 = '"$"#,##0.000000'
TOK  = "#,##0"
PCT  = "0.00%"


def _fmt(wb, bold=False, bg=None, num_fmt=None, align="left"):
    props = {**BORDER_PROPS, "font_size": 10, "valign": "vcenter", "align": align}
    if bold:
        props["bold"] = True
    if bg:
        props["bg_color"] = bg
    if num_fmt:
        props["num_format"] = num_fmt
    return wb.add_format(props)


EXCEL_MAX_DATA_ROWS = 500_000


def _normalize_channel_ids(channel_id: int = None, channel_ids: list[int] = None) -> list[int]:
    ids = []
    if channel_ids:
        ids.extend(int(x) for x in channel_ids if x is not None)
    elif channel_id is not None:
        ids.append(int(channel_id))
    return sorted(set(ids))


def _channel_suffix(channel_id: int = None, channel_ids: list[int] = None) -> str:
    ids = _normalize_channel_ids(channel_id=channel_id, channel_ids=channel_ids)
    if not ids:
        return ""
    if len(ids) == 1:
        return f"_ch{ids[0]}"
    return "_chs" + "-".join(str(x) for x in ids)


def write_sheet(wb, title, sheet_name, headers, col_widths, data_rows, num_fmts,
                total_row=None, total_fmts=None):
    total_data = len(data_rows)
    if total_data <= EXCEL_MAX_DATA_ROWS:
        _write_single_sheet(wb, title, sheet_name, headers, col_widths,
                            data_rows, num_fmts, total_row, total_fmts)
    else:
        part = 1
        for offset in range(0, total_data, EXCEL_MAX_DATA_ROWS):
            chunk = data_rows[offset:offset + EXCEL_MAX_DATA_ROWS]
            sname = f"{sheet_name} ({part})"
            stitle = f"{title} [第{part}部分]"
            is_last = offset + EXCEL_MAX_DATA_ROWS >= total_data
            _write_single_sheet(
                wb, stitle, sname, headers, col_widths, chunk, num_fmts,
                total_row=total_row if is_last else None,
                total_fmts=total_fmts if is_last else None)
            part += 1


def _write_single_sheet(wb, title, sheet_name, headers, col_widths, data_rows,
                        num_fmts, total_row=None, total_fmts=None):
    ws = wb.add_worksheet(sheet_name)
    ws.freeze_panes(2, 0)
    ws.set_row(0, 22)
    ws.set_row(1, 38)

    ncols = len(headers)
    title_fmt = wb.add_format({
        "bold": True, "font_size": 13, "font_color": "#1F4E79",
        "align": "center", "valign": "vcenter",
    })
    ws.merge_range(0, 0, 0, ncols - 1, title, title_fmt)

    hdr_fmt = wb.add_format({
        **BORDER_PROPS, "bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E79",
        "align": "center", "valign": "vcenter", "text_wrap": True, "font_size": 10,
    })
    for c, (h, w) in enumerate(zip(headers, col_widths)):
        ws.write(1, c, h, hdr_fmt)
        ws.set_column(c, c, w)

    fmt_cache = {}

    def get_fmt(nf, row_idx, is_total=False):
        key = (nf, row_idx & 1, is_total)
        if key not in fmt_cache:
            if is_total:
                fmt_cache[key] = _fmt(wb, bold=True, bg="#D6E4F0", num_fmt=nf,
                                      align="right" if nf else "left")
            else:
                bg = "#EBF3FB" if (row_idx & 1) == 0 else None
                fmt_cache[key] = _fmt(wb, bg=bg, num_fmt=nf,
                                      align="right" if nf else "left")
        return fmt_cache[key]

    for ri, row_data in enumerate(data_rows):
        er = ri + 2
        for ci, (val, nf) in enumerate(zip(row_data, num_fmts)):
            ws.write(er, ci, val, get_fmt(nf, ri))

    if total_row:
        tr = len(data_rows) + 2
        tfmts = total_fmts or num_fmts
        for ci, (val, nf) in enumerate(zip(total_row, tfmts)):
            ws.write(tr, ci, val, get_fmt(nf, 0, is_total=True))


def _write_info_sheet(wb, ws, row, items):
    """Write key-value info rows. Returns next row."""
    bold_fmt = wb.add_format({"bold": True, "font_size": 10, "valign": "vcenter"})
    val_fmt = wb.add_format({"font_size": 10, "valign": "vcenter"})
    for label, value in items:
        ws.write(row, 0, label, bold_fmt)
        ws.write(row, 1, str(value), val_fmt)
        row += 1
    return row + 1


def _add_cost_worksheet(wb, title: str):
    """Add a worksheet showing Athena query costs for this report generation.

    Args:
        wb: xlsxwriter Workbook object
        title: Title for the worksheet
    """
    try:
        from cost_monitor import (
            get_cost_summary,
            get_query_costs,
            format_bytes,
            COST_PER_TB,
        )
    except ImportError:
        # Cost monitor not available, skip this worksheet
        return

    summary = get_cost_summary()
    query_costs = get_query_costs()

    # If no queries were tracked, skip this worksheet
    if summary.get("query_count", 0) == 0:
        return

    ws = wb.add_worksheet("查询成本")
    ws.freeze_panes(1, 0)
    ws.set_row(0, 22)

    # Title
    title_fmt = wb.add_format({
        "bold": True, "font_size": 13, "font_color": "#1F4E79",
        "align": "center", "valign": "vcenter",
    })
    ws.merge_range(0, 0, 0, 4, title, title_fmt)

    # Summary section
    row = 2
    bold_fmt = wb.add_format({"bold": True, "font_size": 11, "valign": "vcenter"})
    val_fmt = wb.add_format({"font_size": 11, "valign": "vcenter", "num_format": '"$"#,##0.00'})
    int_fmt = wb.add_format({"font_size": 11, "valign": "vcenter", "num_format": '#,##0'})

    ws.write(row, 0, "成本摘要", bold_fmt)
    row += 1

    ws.write(row, 0, "总查询次数:", bold_fmt)
    ws.write(row, 1, summary.get("query_count", 0), int_fmt)
    row += 1

    ws.write(row, 0, "缓存命中次数:", bold_fmt)
    ws.write(row, 1, summary.get("cache_hits", 0), int_fmt)
    row += 1

    ws.write(row, 0, "缓存命中率:", bold_fmt)
    ws.write(row, 1, f"{summary.get('cache_hit_rate', 0)}%", wb.add_format({"font_size": 11, "valign": "vcenter"}))
    row += 1

    ws.write(row, 0, "总扫描数据量:", bold_fmt)
    ws.write(row, 1, format_bytes(summary.get("total_scanned_bytes", 0)), wb.add_format({"font_size": 11, "valign": "vcenter"}))
    row += 1

    ws.write(row, 0, "预估总成本:", bold_fmt)
    ws.write(row, 1, summary.get("total_cost_usd", 0), val_fmt)
    row += 1

    ws.write(row, 0, "单价 (USD/TB):", bold_fmt)
    ws.write(row, 1, COST_PER_TB, val_fmt)
    row += 2

    # Query breakdown section
    if query_costs:
        ws.write(row, 0, "查询明细（按成本排序）", bold_fmt)
        row += 1

        # Header
        hdr_fmt = wb.add_format({
            "bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E79",
            "align": "center", "valign": "vcenter", "font_size": 10,
        })
        ws.write(row, 0, "查询名称", hdr_fmt)
        ws.write(row, 1, "次数", hdr_fmt)
        ws.write(row, 2, "扫描量", hdr_fmt)
        ws.write(row, 3, "成本 (USD)", hdr_fmt)
        ws.write(row, 4, "缓存命中", hdr_fmt)
        ws.set_column(0, 0, 40)
        ws.set_column(1, 1, 10)
        ws.set_column(2, 2, 14)
        ws.set_column(3, 3, 14)
        ws.set_column(4, 4, 12)
        row += 1

        # Data rows
        data_fmt = wb.add_format({"font_size": 10, "valign": "vcenter"})
        cost_fmt = wb.add_format({"font_size": 10, "valign": "vcenter", "num_format": '"$"#,##0.0000'})
        int_fmt2 = wb.add_format({"font_size": 10, "valign": "vcenter", "num_format": '#,##0'})

        sorted_costs = sorted(
            query_costs.items(),
            key=lambda x: x[1]["total_cost"],
            reverse=True
        )[:50]  # Top 50 queries

        for name, data in sorted_costs:
            count = data["count"] - data["cache_hits"]
            cache_hits = data["cache_hits"]

            ws.write(row, 0, name[:50], data_fmt)  # Limit name length
            ws.write(row, 1, count, int_fmt2)
            ws.write(row, 2, format_bytes(data["total_bytes"]), data_fmt)
            ws.write(row, 3, data["total_cost"], cost_fmt)
            ws.write(row, 4, cache_hits, int_fmt2)
            row += 1


def _add_discount_anomaly_sheet(wb, anomalies: pd.DataFrame, year_month: str):
    """Add a 对账告警 worksheet listing cost_discount > revenue_discount hits.

    Only added when anomalies is non-empty (no empty sheet otherwise).
    """
    if anomalies is None or anomalies.empty:
        return

    a_hdrs = ["渠道 ID", "模型名称", "成本折扣", "客户折扣",
              f"刊例额 ($)", f"亏损额 ($)", "命中条数"]
    a_wids = [10, 32, 12, 12, 16, 16, 10]
    a_fmts = [TOK, None, PCT, PCT, USD4, USD4, TOK]

    a_data = []
    for _, r in anomalies.iterrows():
        a_data.append([
            int(r["channel_id"]) if pd.notna(r["channel_id"]) else 0,
            r["model_name"],
            float(r["cost_discount"]), float(r["revenue_discount"]),
            float(r["list_price_usd"]), float(r["loss_usd"]),
            int(r["row_count"]),
        ])

    a_tot = [
        "合计", "", "", "",
        float(anomalies["list_price_usd"].sum()),
        float(anomalies["loss_usd"].sum()),
        int(anomalies["row_count"].sum()),
    ]

    write_sheet(wb, f"对账告警 -- {year_month} (cost_discount > revenue_discount，疑似未配置成本折扣)",
                "对账告警", a_hdrs, a_wids, a_data, a_fmts,
                total_row=a_tot, total_fmts=a_fmts)


# ---------------------------------------------------------------------------
# Monthly bill (fast aggregation path + flat-tier support)
# ---------------------------------------------------------------------------

def generate_monthly_bill(year_month: str, output_dir: str,
                          user_id: int = None,
                          channel_id: int = None,
                          channel_ids: list[int] = None,
                          currency: str = "USD",
                          exchange_rate: float = 7.3,
                          flat_tier: bool = False,
                          flat_tier_since: str = None,
                          start_day: str = None,
                          end_day: str = None,
                          start_time: str = None,
                          end_time: str = None,
                          time_zone_offset_hours: float = 0,
                          detail: bool = False,
                          customer_view: bool = False,
                          upload_s3: bool = False,
                          no_cache: bool = False,
                          bill_type: str | None = None,
                          split_customers: bool = True,
                          split_internal_customers: bool = False,
                          split_channels: bool = False) -> str | list[str] | dict:
    """Generate monthly bill Excel with xlsxwriter formatting.

    Uses fast aggregation queries (monthly_bill_full) with flat-tier applied
    at the summary level. For row-level precision, use generate_recalc_report.

    When customer_view=True and user_id is not set, split_customers=True will
    additionally emit one invoice workbook (and optional detail export) per user.

    When split_internal_customers=True and user_id is not set, emits one internal
    bill workbook per user (full cost/profit view).

    When split_channels=True and channel_id is not set, emits one bill workbook
    per upstream channel.

    start_day / end_day: day-level boundary 'YYYY-MM-DD' (inclusive).
    start_time / end_time: 'YYYY-MM-DD HH:MM' for sub-day precision;
        takes precedence over start_day / end_day when provided and is
        interpreted in time_zone_offset_hours.

    When detail=True, also exports row-level data as compressed CSV alongside
    the summary Excel.

    When upload_s3=True, uploads all output files to S3 and returns a dict
    with local paths and presigned download URLs (24h expiry).
    """
    os.makedirs(output_dir, exist_ok=True)
    bill_type = _infer_monthly_bill_type(
        bill_type,
        customer_view=customer_view,
        channel_id=channel_id,
        channel_ids=channel_ids,
    )

    if flat_tier_since:
        flat_tier = True

    # Resolve effective display labels for filename / tier_tag
    eff_start = start_time or start_day
    eff_end = end_time or end_day

    suffix = f"_user{user_id}" if user_id else ""
    ch_suffix = _channel_suffix(channel_id=channel_id, channel_ids=channel_ids)
    tier_suffix = "_flattier" if flat_tier else ""
    from_suffix = f"_from{eff_start.replace('-', '').replace(' ', '').replace(':', '')}" if eff_start else ""
    day_suffix = f"_to{eff_end.replace('-', '').replace(' ', '').replace(':', '')}" if eff_end else ""
    tz_suffix = "" if not time_zone_offset_hours else f"_utc{float(time_zone_offset_hours):+g}"
    cv_suffix = "_customer" if customer_view else ""
    filename = f"bill_{year_month}{suffix}{ch_suffix}{tier_suffix}{from_suffix}{day_suffix}{tz_suffix}{cv_suffix}.xlsx"
    filepath = os.path.join(output_dir, filename)

    rate = exchange_rate if currency == "CNY" else 1.0
    symbol = "¥" if currency == "CNY" else "$"

    # Fast aggregation queries
    df_full = run_query_cached(
        queries.monthly_bill_full(year_month, user_id=user_id,
                                  channel_id=channel_id,
                                  channel_ids=channel_ids,
                                  start_day=start_day, end_day=end_day,
                                  start_time=start_time, end_time=end_time,
                                  time_zone_offset_hours=time_zone_offset_hours),
        no_cache=no_cache)
    df_trend = run_query_cached(
        queries.daily_trend(year_month, user_id=user_id,
                            channel_id=channel_id,
                            channel_ids=channel_ids,
                            start_day=start_day, end_day=end_day,
                            start_time=start_time, end_time=end_time,
                            time_zone_offset_hours=time_zone_offset_hours),
        no_cache=no_cache)
    df_trend_model = run_query_cached(
        queries.daily_trend_by_model(year_month, user_id=user_id,
                                     channel_id=channel_id,
                                     channel_ids=channel_ids,
                                     start_day=start_day, end_day=end_day,
                                     start_time=start_time, end_time=end_time,
                                     time_zone_offset_hours=time_zone_offset_hours),
        no_cache=no_cache)

    if df_full.empty:
        wb = xlsxwriter.Workbook(filepath)
        ws = wb.add_worksheet("无数据")
        ws.write(0, 0, "指定时间段内无数据")
        wb.close()
        _write_bill_summary(output_dir, year_month, None, bill_type=bill_type, xlsx_path=filepath)
        return filepath

    # Apply four-tier pricing (with flat-tier if enabled)
    df_full = pricing_engine.apply_pricing_summary(
        df_full, flat_tier=flat_tier, flat_tier_since=flat_tier_since)

    discount_anomalies = pricing_engine.detect_discount_anomalies(df_full)
    pricing_engine.log_discount_anomalies(discount_anomalies)

    tier_tag = ""
    if flat_tier:
        if flat_tier_since:
            tier_tag = f"（降档自 {flat_tier_since}）"
        else:
            tier_tag = "（统一低档价）"
    if eff_start:
        tier_tag += f"（自 {eff_start}）"
    if eff_end:
        tier_tag += f"（截至 {eff_end}）"

    if time_zone_offset_hours:
        tier_tag += f" (UTC{float(time_zone_offset_hours):+g})"

    wb = xlsxwriter.Workbook(filepath, {"constant_memory": False})

    # ── Tab 1: 按用户汇总 ──
    has_cache = "total_cache_hit_tokens" in df_full.columns
    cache_agg_cols = {}
    if has_cache:
        cache_agg_cols = {
            "total_cache_hit_tokens": "sum",
            "total_cache_write_tokens": "sum",
            "total_cw_5m": "sum",
            "total_cw_1h": "sum",
            "total_cw_remaining": "sum",
        }

    user_agg = df_full.groupby(["user_id", "username"]).agg({
        "call_count": "sum",
        "total_input_tokens": "sum",
        "total_output_tokens": "sum",
        "list_price_usd": "sum",
        "revenue_usd": "sum",
        "cost_usd": "sum",
        "profit_usd": "sum",
        **cache_agg_cols,
    }).reset_index().sort_values("list_price_usd", ascending=False)
    user_agg["margin"] = user_agg["profit_usd"] / user_agg["revenue_usd"].replace(0, np.nan)
    if has_cache:
        user_agg["cw_5m_total"] = (user_agg["total_cw_5m"].astype(float)
                                   + user_agg["total_cw_remaining"].astype(float))

    if customer_view:
        u_hdrs = [
            "用户 ID", "用户名", "调用次数",
            "输入 Tokens", "输出 Tokens", "缓存命中 Tokens",
            "缓存写入 Tokens\n(5min)", "缓存写入 Tokens\n(1h)",
            f"刊例价 ({symbol})", f"应付金额 ({symbol})",
        ]
        u_wids = [10, 16, 12, 14, 14, 14, 14, 14, 16, 16]
        u_fmts = [TOK, None, TOK, TOK, TOK, TOK, TOK, TOK, USD2, USD2]
    else:
        u_hdrs = [
            "用户 ID", "用户名", "调用次数",
            "输入 Tokens", "输出 Tokens",
            f"刊例价 ({symbol})", f"客户应付 ({symbol})",
            f"成本 ({symbol})", f"利润 ({symbol})", "利润率",
        ]
        u_wids = [10, 16, 12, 14, 14, 16, 16, 16, 14, 10]
        u_fmts = [TOK, None, TOK, TOK, TOK, USD2, USD2, USD2, USD2, PCT]

    u_data = []
    for _, r in user_agg.iterrows():
        row = [
            int(r["user_id"]), r["username"], int(r["call_count"]),
            int(r["total_input_tokens"]), int(r["total_output_tokens"]),
        ]
        if customer_view and has_cache:
            row += [
                int(r["total_cache_hit_tokens"]),
                int(r["cw_5m_total"]),
                int(r["total_cw_1h"]),
            ]
        row += [
            float(r["list_price_usd"]) * rate,
            float(r["revenue_usd"]) * rate,
        ]
        if not customer_view:
            row += [
                float(r["cost_usd"]) * rate,
                float(r["profit_usd"]) * rate,
                float(r["margin"]) if pd.notna(r["margin"]) else 0,
            ]
        u_data.append(row)

    u_tots_cols = ["call_count", "total_input_tokens", "total_output_tokens",
                   "list_price_usd", "revenue_usd"]
    if has_cache:
        u_tots_cols += ["total_cache_hit_tokens", "cw_5m_total", "total_cw_1h"]
    u_tots = {c: float(user_agg[c].sum()) for c in u_tots_cols}
    u_tot = [
        "合计", "", int(u_tots["call_count"]),
        int(u_tots["total_input_tokens"]), int(u_tots["total_output_tokens"]),
    ]
    if customer_view and has_cache:
        u_tot += [
            int(u_tots["total_cache_hit_tokens"]),
            int(u_tots["cw_5m_total"]),
            int(u_tots["total_cw_1h"]),
        ]
    u_tot += [u_tots["list_price_usd"] * rate, u_tots["revenue_usd"] * rate]
    if not customer_view:
        u_tots.update({c: float(user_agg[c].sum()) for c in ["cost_usd", "profit_usd"]})
        u_tot_margin = u_tots["profit_usd"] / u_tots["revenue_usd"] if u_tots["revenue_usd"] else 0
        u_tot += [u_tots["cost_usd"] * rate, u_tots["profit_usd"] * rate, u_tot_margin]

    write_sheet(wb, f"API 账单 -- {year_month} (用户汇总){tier_tag}",
                "用户汇总", u_hdrs, u_wids, u_data, u_fmts,
                total_row=u_tot, total_fmts=u_fmts)

    # ── Tab 2: 按模型汇总（含 cache token 拆分 + image token）──
    show_cache_in_model_summary = has_cache
    has_image = "total_image_output_tokens" in df_full.columns
    image_agg_cols = {}
    if has_image:
        image_agg_cols = {
            "total_image_output_tokens": "sum",
            "total_image_input_tokens": "sum",
        }

    model_agg = df_full.groupby("model_name").agg({
        "call_count": "sum",
        "total_input_tokens": "sum",
        "total_output_tokens": "sum",
        "total_quota": "sum",
        "list_price_usd": "sum",
        "revenue_usd": "sum",
        "cost_usd": "sum",
        "profit_usd": "sum",
        **cache_agg_cols,
        **image_agg_cols,
    }).reset_index().sort_values("list_price_usd", ascending=False)
    model_agg["billed_usd"] = model_agg["total_quota"].astype(float) / QUOTA_TO_USD
    model_agg["diff"] = model_agg["billed_usd"] - model_agg["list_price_usd"]
    model_agg["diff_pct"] = model_agg["diff"] / model_agg["list_price_usd"].replace(0, np.nan)
    model_agg["margin"] = model_agg["profit_usd"] / model_agg["revenue_usd"].replace(0, np.nan)

    if has_cache:
        model_agg["cw_5m_total"] = (model_agg["total_cw_5m"].astype(float)
                                    + model_agg["total_cw_remaining"].astype(float))

    # Temporarily hide image token columns (Gemini non-stream recording bug)
    show_image_cols = False

    price_label = "低档价" if flat_tier else "刊例"
    m_hdrs = ["模型名称", "调用次数"]
    m_wids = [28, 10]
    m_fmts = [None, TOK]

    if show_cache_in_model_summary:
        m_hdrs += ["输入 Tokens", "输出 Tokens", "缓存命中 Tokens",
                   "缓存写入\n(5min)", "缓存写入\n(1h)"]
        m_wids += [14, 14, 14, 14, 14]
        m_fmts += [TOK, TOK, TOK, TOK, TOK]
    else:
        m_hdrs += ["输入 Tokens", "输出 Tokens"]
        m_wids += [14, 14]
        m_fmts += [TOK, TOK]

    if show_image_cols:
        m_hdrs += ["图片输出\nTokens", "文本输出\nTokens"]
        m_wids += [14, 14]
        m_fmts += [TOK, TOK]

    if customer_view:
        m_hdrs += [f"刊例价 ({symbol})", f"应付金额 ({symbol})"]
        m_wids += [16, 16]
        m_fmts += [USD2, USD2]
    else:
        m_hdrs += [
            f"{price_label}价\n(pricing重算)",
            "系统扣费\n(quota)", "差额", "差额 %",
            f"客户应付", f"成本", "利润", "利润率",
        ]
        m_wids += [16, 16, 13, 10, 16, 16, 14, 10]
        m_fmts += [USD2, USD2, USD4, PCT, USD2, USD2, USD2, PCT]

    m_data = []
    for _, r in model_agg.iterrows():
        row_data = [r["model_name"], int(r["call_count"])]
        if show_cache_in_model_summary:
            row_data += [
                int(r["total_input_tokens"]), int(r["total_output_tokens"]),
                int(r["total_cache_hit_tokens"]),
                int(r["cw_5m_total"]), int(r["total_cw_1h"]),
            ]
        else:
            row_data += [int(r["total_input_tokens"]), int(r["total_output_tokens"])]
        if show_image_cols:
            img_out = int(r.get("total_image_output_tokens", 0) or 0)
            text_out = max(int(r["total_output_tokens"]) - img_out, 0)
            row_data += [img_out, text_out]
        if customer_view:
            row_data += [
                float(r["list_price_usd"]) * rate,
                float(r["revenue_usd"]) * rate,
            ]
        else:
            row_data += [
                float(r["list_price_usd"]) * rate,
                float(r["billed_usd"]) * rate,
                float(r["diff"]) * rate,
                float(r["diff_pct"]) if pd.notna(r["diff_pct"]) else 0,
                float(r["revenue_usd"]) * rate,
                float(r["cost_usd"]) * rate,
                float(r["profit_usd"]) * rate,
                float(r["margin"]) if pd.notna(r["margin"]) else 0,
            ]
        m_data.append(row_data)

    write_sheet(wb, f"API 账单 -- {year_month} (模型汇总){tier_tag}",
                "模型汇总", m_hdrs, m_wids, m_data, m_fmts)

    # ── Tab 3: 定价明细 ──
    if customer_view:
        # Customer view: aggregate by (user, model) — hide channel dimension
        df_cv = df_full.groupby(["user_id", "username", "model_name"]).agg({
            "call_count": "sum",
            "total_input_tokens": "sum",
            "total_output_tokens": "sum",
            "list_price_usd": "sum",
            "revenue_usd": "sum",
            **cache_agg_cols,
        }).reset_index().sort_values("list_price_usd", ascending=False)
        if has_cache:
            df_cv["cw_5m_total"] = (df_cv["total_cw_5m"].astype(float)
                                    + df_cv["total_cw_remaining"].astype(float))
        d_hdrs = [
            "用户 ID", "用户名", "模型名称", "调用次数",
            "输入 Tokens", "输出 Tokens", "缓存命中 Tokens",
            "缓存写入 Tokens\n(5min)", "缓存写入 Tokens\n(1h)",
            f"刊例价 ({symbol})", f"应付金额 ({symbol})",
        ]
        d_wids = [10, 16, 28, 10, 14, 14, 14, 14, 14, 16, 16]
        d_fmts = [TOK, None, None, TOK, TOK, TOK, TOK, TOK, TOK, USD4, USD4]

        d_data = []
        for _, r in df_cv.iterrows():
            row = [
                int(r["user_id"]), r["username"],
                r["model_name"], int(r["call_count"]),
                int(r["total_input_tokens"]), int(r["total_output_tokens"]),
            ]
            if has_cache:
                row += [
                    int(r["total_cache_hit_tokens"]),
                    int(r["cw_5m_total"]),
                    int(r["total_cw_1h"]),
                ]
            row += [
                float(r["list_price_usd"]) * rate,
                float(r["revenue_usd"]) * rate,
            ]
            d_data.append(row)
    else:
        # Internal view: keep channel dimension for cost analysis
        df_sorted = df_full.sort_values("list_price_usd", ascending=False)
        # Temporarily hide image token columns (Gemini non-stream recording bug)
        detail_has_image = False
        if detail_has_image:
            d_hdrs = [
                "用户 ID", "用户名", "渠道 ID", "模型名称", "调用次数",
                "输入 Tokens", "输出 Tokens", "图片输出\nTokens", "文本输出\nTokens",
                f"刊例价 ({symbol})", "成本折扣", f"成本 ({symbol})",
                "客户折扣", f"客户应付 ({symbol})",
                f"利润 ({symbol})", "利润率",
            ]
            d_wids = [10, 16, 10, 28, 10, 14, 14, 14, 14, 16, 10, 16, 10, 16, 14, 10]
            d_fmts = [TOK, None, TOK, None, TOK, TOK, TOK, TOK, TOK, USD4, PCT, USD4, PCT, USD4, USD4, PCT]
        else:
            d_hdrs = [
                "用户 ID", "用户名", "渠道 ID", "模型名称", "调用次数",
                "输入 Tokens", "输出 Tokens",
                f"刊例价 ({symbol})", "成本折扣", f"成本 ({symbol})",
                "客户折扣", f"客户应付 ({symbol})",
                f"利润 ({symbol})", "利润率",
            ]
            d_wids = [10, 16, 10, 28, 10, 14, 14, 16, 10, 16, 10, 16, 14, 10]
            d_fmts = [TOK, None, TOK, None, TOK, TOK, TOK, USD4, PCT, USD4, PCT, USD4, USD4, PCT]

        d_data = []
        for _, r in df_sorted.iterrows():
            lp = float(r["list_price_usd"]) * rate
            rev = float(r["revenue_usd"]) * rate
            cost = float(r["cost_usd"]) * rate
            profit = float(r["profit_usd"]) * rate
            margin = profit / rev if rev else 0
            row = [
                int(r["user_id"]), r["username"], int(r["channel_id"]),
                r["model_name"], int(r["call_count"]),
                int(r["total_input_tokens"]), int(r["total_output_tokens"]),
            ]
            if detail_has_image:
                img_out = int(r.get("total_image_output_tokens", 0) or 0)
                text_out = max(int(r["total_output_tokens"]) - img_out, 0)
                row += [img_out, text_out]
            row += [lp, float(r["cost_discount"]), cost, float(r["revenue_discount"]),
                    rev, profit, margin]
            d_data.append(row)

    write_sheet(wb, f"API 账单 -- {year_month} (定价明细){tier_tag}",
                "定价明细", d_hdrs, d_wids, d_data, d_fmts)

    # ── Tab 4: 每日趋势 ──
    if customer_view:
        t_hdrs = ["日期", "调用次数", "输入+输出 Tokens",
                  "缓存命中 Tokens", "缓存写入 Tokens\n(5min)", "缓存写入 Tokens\n(1h)",
                  f"刊例价 ({symbol})"]
        t_wids = [14, 12, 16, 14, 14, 14, 14]
        t_fmts = [None, TOK, TOK, TOK, TOK, TOK, USD4]
    else:
        t_hdrs = ["日期", "调用次数", "总 Tokens", "总额度", f"刊例价 ({symbol})"]
        t_wids = [14, 12, 14, 14, 14]
        t_fmts = [None, TOK, TOK, TOK, USD4]
    t_data = []
    if not df_trend.empty:
        for _, r in df_trend.iterrows():
            row_data = [
                f"{year_month}-{int(r['day']):02d}",
                int(r["call_count"]), int(r["total_tokens"]),
            ]
            if customer_view and "total_cache_hit_tokens" in df_trend.columns:
                row_data += [
                    int(r["total_cache_hit_tokens"]),
                    int(r["total_cw_5m"]) + int(r["total_cw_remaining"]),
                    int(r["total_cw_1h"]),
                ]
            if not customer_view:
                row_data.append(int(r["total_quota"]))
            row_data.append(float(r["total_usd"]) * rate)
            t_data.append(row_data)
    write_sheet(wb, f"每日费用趋势 -- {year_month}",
                "每日趋势", t_hdrs, t_wids, t_data, t_fmts)

    # ── Tab 5: 每日模型明细 ──
    if customer_view:
        dm_hdrs = ["日期", "Token 名称", "模型名称", "调用次数",
                   "输入 Tokens", "输出 Tokens", "缓存命中 Tokens",
                   "缓存写入 Tokens\n(5min)", "缓存写入 Tokens\n(1h)",
                   f"刊例价 ({symbol})"]
        dm_wids = [14, 18, 28, 12, 14, 14, 14, 14, 14, 16]
        dm_fmts = [None, None, None, TOK, TOK, TOK, TOK, TOK, TOK, USD4]
    else:
        dm_hdrs = ["日期", "Token 名称", "模型名称", "调用次数",
                   "输入 Tokens", "输出 Tokens", "总额度",
                   f"刊例价 ({symbol})"]
        dm_wids = [14, 18, 28, 12, 14, 14, 14, 16]
        dm_fmts = [None, None, None, TOK, TOK, TOK, TOK, USD4]
    dm_data = []
    if not df_trend_model.empty:
        for _, r in df_trend_model.iterrows():
            row_data = [
                f"{year_month}-{int(r['day']):02d}",
                r.get("token_name", ""),
                r["model_name"],
                int(r["call_count"]),
                int(r["total_input_tokens"]),
                int(r["total_output_tokens"]),
            ]
            if customer_view and "total_cache_hit_tokens" in df_trend_model.columns:
                row_data += [
                    int(r["total_cache_hit_tokens"]),
                    int(r["total_cw_5m"]) + int(r["total_cw_remaining"]),
                    int(r["total_cw_1h"]),
                ]
            if not customer_view:
                row_data.append(int(r["total_quota"]))
            row_data.append(float(r["total_usd"]) * rate)
            dm_data.append(row_data)
    write_sheet(wb, f"每日模型明细 -- {year_month}",
                "每日模型明细", dm_hdrs, dm_wids, dm_data, dm_fmts)

    # --- 对账告警 / 查询成本: internal-only sheets ---
    if not customer_view:
        _add_discount_anomaly_sheet(wb, discount_anomalies, year_month)
        if COST_MONITOR_AVAILABLE:
            _add_cost_worksheet(wb, f"月度账单 -- {year_month} (查询成本)")

    wb.close()

    detail_path = None
    if detail:
        detail_path = _export_detail_csv(year_month, output_dir, user_id=user_id,
                                         channel_id=channel_id,
                                         channel_ids=channel_ids,
                                         flat_tier=flat_tier,
                                         flat_tier_since=flat_tier_since,
                                         start_day=start_day,
                                         end_day=end_day,
                                         start_time=start_time,
                                         end_time=end_time,
                                         time_zone_offset_hours=time_zone_offset_hours,
                                         customer_view=customer_view)
        gc.collect()

    per_customer_paths: list[str] = []
    if split_customers and customer_view and user_id is None and not df_full.empty:
        for uid in sorted(int(value) for value in user_agg["user_id"].unique()):
            username = str(user_agg.loc[user_agg["user_id"] == uid, "username"].iloc[0])
            logger.info(
                "Generating per-customer invoice",
                extra={"event": "split_customer_bill", "user_id": uid, "username": username},
            )
            user_result = generate_monthly_bill(
                year_month,
                output_dir,
                user_id=uid,
                channel_id=channel_id,
                channel_ids=channel_ids,
                currency=currency,
                exchange_rate=exchange_rate,
                flat_tier=flat_tier,
                flat_tier_since=flat_tier_since,
                start_day=start_day,
                end_day=end_day,
                start_time=start_time,
                end_time=end_time,
                time_zone_offset_hours=time_zone_offset_hours,
                detail=detail,
                customer_view=True,
                upload_s3=False,
                no_cache=no_cache,
                bill_type=bill_type,
                split_customers=False,
                split_internal_customers=False,
                split_channels=False,
            )
            if isinstance(user_result, list):
                per_customer_paths.extend(str(path) for path in user_result)
            elif isinstance(user_result, str):
                per_customer_paths.append(user_result)
            del user_result
            gc.collect()

    per_channel_paths: list[str] = []
    if (
        split_channels
        and channel_id is None
        and not channel_ids
        and user_id is None
        and "channel_id" in df_full.columns
        and not df_full.empty
    ):
        for ch in sorted(int(value) for value in df_full["channel_id"].unique()):
            logger.info(
                "Generating per-channel bill",
                extra={"event": "split_channel_bill", "channel_id": ch},
            )
            channel_result = generate_monthly_bill(
                year_month,
                output_dir,
                user_id=user_id,
                channel_id=ch,
                channel_ids=channel_ids,
                currency=currency,
                exchange_rate=exchange_rate,
                flat_tier=flat_tier,
                flat_tier_since=flat_tier_since,
                start_day=start_day,
                end_day=end_day,
                start_time=start_time,
                end_time=end_time,
                time_zone_offset_hours=time_zone_offset_hours,
                detail=detail,
                customer_view=customer_view,
                upload_s3=False,
                no_cache=no_cache,
                bill_type=bill_type,
                split_customers=False,
                split_internal_customers=False,
                split_channels=False,
            )
            if isinstance(channel_result, list):
                per_channel_paths.extend(str(path) for path in channel_result)
            elif isinstance(channel_result, str):
                per_channel_paths.append(channel_result)
            del channel_result
            gc.collect()

    if (
        split_internal_customers
        and not customer_view
        and user_id is None
        and channel_id is None
        and not channel_ids
        and not df_full.empty
    ):
        for uid in sorted(int(value) for value in user_agg["user_id"].unique()):
            username = str(user_agg.loc[user_agg["user_id"] == uid, "username"].iloc[0])
            logger.info(
                "Generating per-customer internal bill",
                extra={"event": "split_internal_customer_bill", "user_id": uid, "username": username},
            )
            user_result = generate_monthly_bill(
                year_month,
                output_dir,
                user_id=uid,
                channel_id=channel_id,
                channel_ids=channel_ids,
                currency=currency,
                exchange_rate=exchange_rate,
                flat_tier=flat_tier,
                flat_tier_since=flat_tier_since,
                start_day=start_day,
                end_day=end_day,
                start_time=start_time,
                end_time=end_time,
                time_zone_offset_hours=time_zone_offset_hours,
                detail=detail,
                customer_view=False,
                upload_s3=False,
                no_cache=no_cache,
                bill_type=bill_type,
                split_customers=False,
                split_internal_customers=False,
                split_channels=False,
            )
            if isinstance(user_result, list):
                per_customer_paths.extend(str(path) for path in user_result)
            elif isinstance(user_result, str):
                per_customer_paths.append(user_result)
            del user_result
            gc.collect()

    _write_bill_summary(
        output_dir,
        year_month,
        df_full,
        bill_type=bill_type,
        detail_path=detail_path,
        xlsx_path=filepath,
        per_customer_paths=per_customer_paths,
        per_channel_paths=per_channel_paths,
    )

    output_paths = [filepath]
    if detail_path:
        output_paths.append(detail_path)
    output_paths.extend(per_customer_paths)
    output_paths.extend(per_channel_paths)

    if not detail and not upload_s3 and len(output_paths) == 1:
        return filepath

    if upload_s3:
        result = _upload_results(filepath, detail_path)
        return result

    return output_paths if len(output_paths) > 1 else filepath


# ---------------------------------------------------------------------------
# S3 upload helper
# ---------------------------------------------------------------------------

def _upload_results(xlsx_path: str, detail_path: str = None) -> dict:
    """Upload generated files to S3 and return paths + presigned URLs."""
    result = {"xlsx": xlsx_path}

    logger.info("Uploading summary bill to S3", extra={"event": "upload_start", "file": xlsx_path})
    info = upload_and_sign(xlsx_path)
    result["xlsx_url"] = info["url"]
    result["xlsx_s3_key"] = info["s3_key"]

    if detail_path:
        result["detail_csv"] = detail_path
        logger.info("Uploading detail data to S3", extra={"event": "upload_detail", "file": detail_path})
        info = upload_and_sign(detail_path)
        result["detail_csv_url"] = info["url"]
        result["detail_csv_s3_key"] = info["s3_key"]

    logger.info("Upload completed", extra={"event": "upload_complete"})
    return result


# ---------------------------------------------------------------------------
# Detail CSV export (parallel per-day queries + S3 direct download)
# ---------------------------------------------------------------------------

def _export_detail_csv(year_month: str, output_dir: str,
                       user_id: int = None, channel_id: int = None,
                       channel_ids: list[int] = None,
                       model: str = None,
                       flat_tier: bool = False,
                       flat_tier_since: str = None,
                       start_day: str = None,
                       end_day: str = None,
                       start_time: str = None,
                       end_time: str = None,
                       time_zone_offset_hours: float = 0,
                       customer_view: bool = False) -> str:
    """Export row-level detail as xlsx (customer_view) or zip-compressed CSV.

    customer_view=True:
      - Outputs .xlsx with auto-split sheets (≤500K rows each)
      - Chinese column headers, UTC+8 timestamps
      - Hides cost/profit/channel/discount columns
    customer_view=False:
      - Outputs .csv.zip (internal full-field format)

    start_day / end_day: day-level boundary 'YYYY-MM-DD' (inclusive).
    start_time / end_time: 'YYYY-MM-DD HH:MM' for sub-day precision,
    interpreted in time_zone_offset_hours.
    """
    eff_start = start_time or start_day
    eff_end = end_time or end_day

    suffix = f"_user{user_id}" if user_id else ""
    ch_suffix = _channel_suffix(channel_id=channel_id, channel_ids=channel_ids)
    tier_suffix = "_flattier" if flat_tier else ""
    from_suffix = f"_from{eff_start.replace('-', '').replace(' ', '').replace(':', '')}" if eff_start else ""
    day_suffix = f"_to{eff_end.replace('-', '').replace(' ', '').replace(':', '')}" if eff_end else ""
    cv_suffix = "_customer" if customer_view else ""

    days = queries.detail_day_list(year_month, start_day=start_day, end_day=end_day,
                                   start_time=start_time, end_time=end_time,
                                   time_zone_offset_hours=time_zone_offset_hours)
    sqls = [
        queries.raw_usage_detail_daily(year_month, day=d,
                                       user_id=user_id,
                                       channel_id=channel_id,
                                       channel_ids=channel_ids,
                                       model=model)
        for d in days
    ]

    # Pre-compute unix timestamps for sub-day row filtering on boundary days
    _start_ts = _end_ts = None
    _start_day_str = _end_day_str = None
    if start_time:
        sy, sm, sd, _sh, _start_ts = queries._parse_datetime(
            start_time, time_zone_offset_hours)
        _start_day_str = f"{sy}-{sm}-{sd}"
    if end_time:
        ey, em, ed, _eh, _end_ts = queries._parse_datetime(
            end_time, time_zone_offset_hours)
        _end_day_str = f"{ey}-{em}-{ed}"

    logger.info("Submitting daily queries (parallel)",
                extra={"event": "detail_start", "query_count": len(sqls)})
    t0 = time.time()
    total_rows = 0
    days_done = 0
    all_chunks: list[pd.DataFrame] = []

    for idx, df_day in run_queries_parallel_iter(sqls):
        days_done += 1
        if df_day.empty:
            continue

        # Sub-day row filter: trim boundary days to exact minute
        cur_day = days[idx]  # e.g. '15'
        cur_day_full = f"{year_month}-{cur_day}"
        if _start_ts is not None and cur_day_full == _start_day_str:
            df_day = df_day[df_day["created_at"] >= _start_ts]
        if _end_ts is not None and cur_day_full == _end_day_str:
            df_day = df_day[df_day["created_at"] < _end_ts + 60]

        if df_day.empty:
            continue

        df_day = _apply_detail_pricing(df_day, flat_tier=flat_tier,
                                       flat_tier_since=flat_tier_since)
        total_rows += len(df_day)
        all_chunks.append(df_day)

        elapsed = time.time() - t0
        logger.debug("Day query completed",
                     extra={
                         "event": "detail_day",
                         "day": days[idx],
                         "rows": len(df_day),
                         "days_done": days_done,
                         "total_days": len(sqls),
                         "total_rows": total_rows,
                         "elapsed_s": elapsed,
                     })

    elapsed = time.time() - t0

    if total_rows == 0:
        logger.warning("No detail data found", extra={"event": "detail_no_data"})
        all_chunks = [pd.DataFrame()]

    df_all = pd.concat(all_chunks, ignore_index=True) if all_chunks else pd.DataFrame()
    df_all = pricing_engine.dedupe_usage_log_rows(df_all)

    if customer_view:
        df_all = pricing_engine.collapse_postpaid_detail_rows(df_all)
        out_path = _write_detail_xlsx_customer(
            df_all, year_month, output_dir, user_id=user_id,
            channel_id=channel_id, channel_ids=channel_ids,
            flat_tier=flat_tier,
            start_day=start_time or start_day,
            end_day=end_time or end_day,
            tier_suffix=tier_suffix, from_suffix=from_suffix, day_suffix=day_suffix)
    else:
        out_path = _write_detail_csv_internal(
            df_all, year_month, output_dir,
            suffix=suffix, ch_suffix=ch_suffix, tier_suffix=tier_suffix,
            from_suffix=from_suffix, day_suffix=day_suffix)

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    logger.info("Detail export completed",
                extra={
                    "event": "detail_complete",
                    "total_rows": total_rows,
                    "size_mb": size_mb,
                    "elapsed_s": elapsed,
                })

    return out_path


# Temporarily hidden from Excel/CSV output (query fields retained for future restore)
_SHOW_IMAGE_TOKEN_COLS = False
_HIDDEN_IMAGE_TOKEN_COLS = frozenset({
    "image_output_tokens", "image_input_tokens",
    "image_output_ratio", "image_input_ratio",
})


# Column spec for internal detail xlsx (full fields, English headers)
_INTERNAL_DETAIL_COLS = [
    # (internal_col,            header,                     width,  num_fmt)
    ("request_id",              "Request ID",               36,     None),
    ("created_at",              "Time (UTC+8)",             20,     None),
    ("user_id",                 "User ID",                  10,     TOK),
    ("username",                "Username",                 18,     None),
    ("channel_id",              "Channel ID",               12,     TOK),
    ("model_name",              "Model",                    32,     None),
    ("token_name",              "Token Name",               18,     None),
    ("prompt_tokens",           "Input Tokens",             14,     TOK),
    ("completion_tokens",       "Output Tokens",            14,     TOK),
    ("cache_hit_tokens",        "Cache Hit Tokens",         16,     TOK),
    ("cache_write_tokens",      "Cache Write Tokens",       16,     TOK),
    ("cw_5m",                   "Cache Write (5min)",       16,     TOK),
    ("cw_1h",                   "Cache Write (1h)",         16,     TOK),
    ("cw_remaining",            "Cache Write (remaining)",  18,     TOK),
    ("quota",                   "Quota",                    14,     TOK),
    ("billed_usd",              "Billed USD",               14,     USD6),
    ("expected_usd",            "Expected USD",             14,     USD6),
    ("list_price_usd",          "List Price USD",           14,     USD6),
    ("cost_discount",           "Cost Discount",            13,     PCT),
    ("cost_usd",                "Cost USD",                 14,     USD6),
    ("revenue_discount",        "Revenue Discount",         15,     PCT),
    ("revenue_usd",             "Revenue USD",              14,     USD6),
    ("profit_usd",              "Profit USD",               14,     USD6),
    ("use_time_seconds",        "Use Time (s)",             12,     None),
    ("is_stream",               "Stream",                   8,      None),
    ("tiered_ip",               "Tiered Input Price",       16,     None),
    ("tiered_op",               "Tiered Output Price",      16,     None),
]


DETAIL_XLSX_ROW_LIMIT = 500_000   # above this, fall back to csv.zip


def _write_detail_csv_internal(df: pd.DataFrame, year_month: str,
                               output_dir: str, suffix: str = "",
                               ch_suffix: str = "",
                               tier_suffix: str = "", from_suffix: str = "",
                               day_suffix: str = "") -> str:
    """Write internal full-field detail.

    Uses xlsx when row count <= DETAIL_XLSX_ROW_LIMIT (500K); falls back to
    zip-compressed CSV for larger datasets where xlsx would be impractically slow.
    """
    base = f"bill_{year_month}{suffix}{ch_suffix}{tier_suffix}{from_suffix}{day_suffix}_detail"

    if df.empty or len(df) <= DETAIL_XLSX_ROW_LIMIT:
        return _write_detail_xlsx_internal(df, base, output_dir, year_month,
                                           tier_suffix, from_suffix, day_suffix)
    else:
        logger.info(
            "Detail row count exceeds xlsx limit, using csv.zip",
            extra={"event": "detail_format_fallback",
                   "rows": len(df), "limit": DETAIL_XLSX_ROW_LIMIT})
        return _write_detail_csv_zip(df, base, output_dir)


def _write_detail_xlsx_internal(df: pd.DataFrame, base: str, output_dir: str,
                                year_month: str, tier_suffix: str = "",
                                from_suffix: str = "", day_suffix: str = "") -> str:
    """Write internal detail as xlsx with auto-split sheets (≤500K rows)."""
    xlsx_path = os.path.join(output_dir, base + ".xlsx")

    if df.empty:
        wb = xlsxwriter.Workbook(xlsx_path)
        ws = wb.add_worksheet("No Data")
        ws.write(0, 0, "No data found for the specified period.")
        wb.close()
        return xlsx_path

    df = df.copy()
    if "created_at" in df.columns:
        df["created_at"] = (
            pd.to_datetime(df["created_at"], unit="s", utc=True)
            .dt.tz_convert("Asia/Shanghai")
            .dt.strftime("%Y-%m-%d %H:%M:%S")
        )

    col_spec = [(ic, hdr, w, nf) for ic, hdr, w, nf in _INTERNAL_DETAIL_COLS
                if ic in df.columns and ic not in _HIDDEN_IMAGE_TOKEN_COLS]
    internal_cols = [c[0] for c in col_spec]
    headers    = [c[1] for c in col_spec]
    col_widths = [c[2] for c in col_spec]
    num_fmts   = [c[3] for c in col_spec]

    df_out = df[internal_cols].fillna("")
    data_rows = df_out.values.tolist()
    title = f"API Detail -- {year_month}{tier_suffix}{from_suffix}{day_suffix}"

    wb = xlsxwriter.Workbook(xlsx_path, {"constant_memory": False})
    write_sheet(wb, title, "Detail", headers, col_widths, data_rows, num_fmts)
    wb.close()
    return xlsx_path


def _write_detail_csv_zip(df: pd.DataFrame, base: str, output_dir: str) -> str:
    """Write internal detail as zip-compressed CSV (fallback for large datasets)."""
    import io as _io
    zip_path = os.path.join(output_dir, base + ".csv.zip")
    csv_inner_name = base + ".csv"

    drop_cols = [c for c in _HIDDEN_IMAGE_TOKEN_COLS if c in df.columns]
    df_out = df.drop(columns=drop_cols) if drop_cols else df
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zf:
        with zf.open(csv_inner_name, "w") as raw:
            with _io.TextIOWrapper(raw, encoding="utf-8", newline="") as text:
                df_out.to_csv(text, index=False, lineterminator="\n",
                              chunksize=50_000)
    return zip_path


def _write_customer_detail_csv_zip(
    df: pd.DataFrame,
    base: str,
    output_dir: str,
    internal_cols: list[str],
) -> str:
    """Write customer-facing detail as chunked zip-compressed CSV."""
    import io as _io

    zip_path = os.path.join(output_dir, base + ".csv.zip")
    csv_inner_name = base + ".csv"
    chunk_size = 50_000

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zf:
        with zf.open(csv_inner_name, "w") as raw:
            with _io.TextIOWrapper(raw, encoding="utf-8", newline="") as text:
                wrote_header = False
                for start in range(0, len(df), chunk_size):
                    source = df.iloc[start:start + chunk_size]
                    chunk = source.loc[:, internal_cols].copy()
                    if "created_at" in chunk.columns:
                        chunk["created_at"] = (
                            pd.to_datetime(chunk["created_at"], unit="s", utc=True)
                            .dt.tz_convert("Asia/Shanghai")
                            .dt.strftime("%Y-%m-%d %H:%M:%S")
                        )
                    if "cw_5m" in chunk.columns and "cw_remaining" in source.columns:
                        chunk["cw_5m"] = (
                            chunk["cw_5m"].fillna(0).astype(float)
                            + source["cw_remaining"].fillna(0).astype(float)
                        )
                    chunk = chunk.fillna("")
                    chunk.to_csv(
                        text,
                        index=False,
                        header=not wrote_header,
                        lineterminator="\n",
                    )
                    wrote_header = True
    return zip_path


# Column spec for customer-facing detail xlsx
_CUSTOMER_DETAIL_COLS = [
    # (internal_col, chinese_header, width, num_fmt_or_None)
    ("request_id",          "记录 ID",              20, None),
    ("created_at",          "时间 (UTC+8)",         20, None),
    ("model_name",          "模型名称",             28, None),
    ("token_name",          "Token 名称",           16, None),
    ("prompt_tokens",       "输入 Tokens",          14, TOK),
    ("completion_tokens",   "输出 Tokens",          14, TOK),
    ("cache_hit_tokens",    "缓存命中 Tokens",      14, TOK),
    ("cw_5m",               "缓存写入 Tokens\n(5min)", 14, TOK),
    ("cw_1h",               "缓存写入 Tokens\n(1h)",   14, TOK),
    ("list_price_usd",      "刊例价 ($)",           14, USD6),
    ("revenue_discount",    "折扣",                 10, PCT),
    ("revenue_usd",         "应付金额 ($)",         14, USD6),
]


def _customer_daily_key_model_rows(df: pd.DataFrame, year_month: str):
    """Build customer-facing daily rows grouped by date, token key, and model."""
    required = {"created_at", "model_name"}
    if df.empty or not required.issubset(df.columns):
        return [], None

    work = df.copy()
    if "local_date" not in work.columns:
        created = work["created_at"]
        if pd.api.types.is_numeric_dtype(created):
            work["local_date"] = (
                pd.to_datetime(created, unit="s", utc=True)
                .dt.tz_convert("Asia/Shanghai")
                .dt.strftime("%Y-%m-%d")
            )
        else:
            work["local_date"] = created.astype(str).str.slice(0, 10)
    if "token_name" not in work.columns:
        work["token_name"] = ""
    if "request_id" not in work.columns:
        work["request_id"] = work.index.astype(str)

    sum_cols = [
        "prompt_tokens", "completion_tokens",
        "cache_hit_tokens", "cw_5m", "cw_1h",
        "list_price_usd", "revenue_usd",
    ]
    agg_spec = {c: "sum" for c in sum_cols if c in work.columns}
    if not agg_spec:
        return [], None

    grouped = (
        work.groupby(["local_date", "token_name", "model_name"], dropna=False)
        .agg({**agg_spec, "request_id": "count"})
        .rename(columns={"request_id": "call_count"})
        .reset_index()
    )

    if "list_price_usd" in grouped.columns:
        grouped = grouped.sort_values(
            ["local_date", "token_name", "list_price_usd"],
            ascending=[True, True, False],
        )
    else:
        grouped = grouped.sort_values(["local_date", "token_name", "model_name"])

    headers = ["日期 (UTC+8)", "Token 名称", "模型名称", "调用次数"]
    widths = [14, 18, 30, 12]
    fmts = [None, None, None, TOK]
    metric_cols = []

    for col, header, width, fmt in [
        ("prompt_tokens", "输入 Tokens", 14, TOK),
        ("completion_tokens", "输出 Tokens", 14, TOK),
        ("cache_hit_tokens", "缓存命中 Tokens", 14, TOK),
        ("cw_5m", "缓存写入 Tokens\n(5min)", 14, TOK),
        ("cw_1h", "缓存写入 Tokens\n(1h)", 14, TOK),
        ("list_price_usd", "刊例价 ($)", 14, USD6),
        ("revenue_usd", "应付金额 ($)", 14, USD6),
    ]:
        if col in grouped.columns:
            metric_cols.append(col)
            headers.append(header)
            widths.append(width)
            fmts.append(fmt)

    rows = []
    for _, r in grouped.iterrows():
        row = [
            r["local_date"],
            "" if pd.isna(r["token_name"]) else r["token_name"],
            r["model_name"],
            int(r["call_count"]),
        ]
        for col in metric_cols:
            value = r[col]
            if col in {"list_price_usd", "revenue_usd"}:
                row.append(float(value))
            else:
                row.append(int(value))
        rows.append(row)

    return rows, (headers, widths, fmts)


def _write_detail_xlsx_customer(df: pd.DataFrame, year_month: str,
                                output_dir: str, user_id: int = None,
                                channel_id: int = None,
                                channel_ids: list[int] = None,
                                flat_tier: bool = False,
                                start_day: str = None, end_day: str = None,
                                tier_suffix: str = "", from_suffix: str = "",
                                day_suffix: str = "") -> str:
    """Write customer-facing detail as xlsx with auto-split sheets."""
    suffix = f"_user{user_id}" if user_id else ""
    ch_suffix = _channel_suffix(channel_id=channel_id, channel_ids=channel_ids)
    xlsx_filename = f"bill_{year_month}{suffix}{ch_suffix}{tier_suffix}{from_suffix}{day_suffix}_detail_customer.xlsx"
    xlsx_path = os.path.join(output_dir, xlsx_filename)

    tier_tag = ""
    if flat_tier:
        tier_tag = "（统一低档价）"
    if start_day:
        tier_tag += f"（自 {start_day}）"
    if end_day:
        tier_tag += f"（截至 {end_day}）"

    if df.empty:
        wb = xlsxwriter.Workbook(xlsx_path)
        ws = wb.add_worksheet("无数据")
        ws.write(0, 0, "指定时间段内无数据")
        wb.close()
        return xlsx_path

    col_spec = [(ic, ch, w, nf) for ic, ch, w, nf in _CUSTOMER_DETAIL_COLS
                if ic in df.columns and ic not in _HIDDEN_IMAGE_TOKEN_COLS]
    internal_cols = [c[0] for c in col_spec]
    headers = [c[1] for c in col_spec]
    col_widths = [c[2] for c in col_spec]
    num_fmts = [c[3] for c in col_spec]

    if len(df) > DETAIL_XLSX_ROW_LIMIT:
        logger.info(
            "Customer detail row count exceeds xlsx limit, using csv.zip",
            extra={"event": "detail_format_fallback",
                   "rows": len(df), "limit": DETAIL_XLSX_ROW_LIMIT})
        base = os.path.splitext(os.path.basename(xlsx_path))[0]
        return _write_customer_detail_csv_zip(df, base, output_dir, internal_cols)

    # Convert created_at (unix timestamp) to UTC+8 readable string
    if "created_at" in df.columns:
        df = df.copy()
        df["created_at"] = (
            pd.to_datetime(df["created_at"], unit="s", utc=True)
            .dt.tz_convert("Asia/Shanghai")
            .dt.strftime("%Y-%m-%d %H:%M:%S")
        )

    # Build column mapping — only include columns that exist in df
    if "cw_5m" in df.columns and "cw_remaining" in df.columns:
        df = df.copy()
        df["cw_5m"] = (
            df["cw_5m"].fillna(0).astype(float)
            + df["cw_remaining"].fillna(0).astype(float)
        )

    agg_rows, agg_sheet = _customer_daily_key_model_rows(df, year_month)

    df_out = df[internal_cols].copy()
    df_out = df_out.fillna("")

    user_label = f"User{user_id} " if user_id else ""
    title_base = f"{user_label}API 账单 -- {year_month} (调用明细){tier_tag}"

    data_rows = df_out.values.tolist()

    wb = xlsxwriter.Workbook(xlsx_path, {"constant_memory": False})
    if agg_sheet:
        agg_headers, agg_widths, agg_fmts = agg_sheet
        write_sheet(
            wb,
            f"{user_label}API 账单 -- {year_month} (每日模型明细，按日期×Token×模型){tier_tag}",
            "每日模型明细",
            agg_headers,
            agg_widths,
            agg_rows,
            agg_fmts,
        )
    write_sheet(wb, title_base, "调用明细", headers, col_widths,
                data_rows, num_fmts)
    wb.close()
    return xlsx_path


def _vectorized_discount(df: pd.DataFrame, key_col: str, model_col: str,
                         lookup_fn) -> pd.Series:
    """Vectorized discount lookup — compute per unique (key, model) pair, then map back.

    Instead of calling lookup_fn per row (slow for 500K+ rows), we deduplicate
    the (key, model) combinations, look up once per combo, and broadcast back.
    Typically reduces 500K lookups to ~50.
    """
    if key_col not in df.columns:
        return pd.Series(1.0, index=df.index)

    pairs = df[[key_col, model_col]].drop_duplicates()
    cache = {}
    for _, row in pairs.iterrows():
        cache[(row[key_col], row[model_col])] = lookup_fn(row[key_col], row[model_col])

    return pd.Series(
        [cache.get((k, m), 1.0) for k, m in zip(df[key_col], df[model_col])],
        index=df.index)


def _apply_detail_pricing(df: pd.DataFrame,
                          flat_tier: bool = False,
                          flat_tier_since: str = None) -> pd.DataFrame:
    """Apply pricing to detail DataFrame with Athena-extracted cache tokens.

    Unlike recalc_from_raw which parses JSON locally, this uses the cache token
    columns already extracted by Athena SQL (cache_hit_tokens, cw_5m, etc.).
    """
    if df.empty:
        return df

    df = df.copy()

    flat_tier_since_ts = None
    if flat_tier_since:
        flat_tier_since_ts = int(datetime.strptime(flat_tier_since, "%Y-%m-%d").timestamp())
        flat_tier = True

    if "model_name" in df.columns and "model" not in df.columns:
        df["model"] = df["model_name"]

    # Compute cw_remaining if not already present
    if "cw_remaining" not in df.columns:
        cw = df.get("cache_write_tokens", pd.Series(0, index=df.index)).astype(float)
        cw5 = df.get("cw_5m", pd.Series(0, index=df.index)).astype(float)
        cw1h = df.get("cw_1h", pd.Series(0, index=df.index)).astype(float)
        df["cw_remaining"] = np.maximum(cw - cw5 - cw1h, 0)

    df = pricing_engine._assign_prices(df, flat_tier=flat_tier,
                                       flat_tier_since_ts=flat_tier_since_ts)

    # Prefer system-recorded tiered prices when available
    has_sys_ip = "tiered_ip" in df.columns
    ip = df["ip"].copy()
    op = df["op"].copy()
    if has_sys_ip and not flat_tier:
        sys_ip = df["tiered_ip"]
        sys_op = df.get("tiered_op", pd.Series(dtype="float64"))
        ip = np.where(sys_ip.notna(), sys_ip, ip)
        if sys_op is not None:
            op = np.where(sys_op.notna(), sys_op, op)

    pt = df["prompt_tokens"].astype(float)
    ct = df["completion_tokens"].astype(float)
    ch_tok = df.get("cache_hit_tokens", pd.Series(0, index=df.index)).astype(float)

    cw_5m_total = df["cw_remaining"].astype(float) + df.get("cw_5m", pd.Series(0, index=df.index)).astype(float)

    cost_input = pt / 1e6 * ip
    cost_output = ct / 1e6 * op
    cost_cache_hit = ch_tok / 1e6 * df["chp"]
    cost_cw_5m = cw_5m_total / 1e6 * df["cwp"]
    cost_cw_1h = df.get("cw_1h", pd.Series(0, index=df.index)).astype(float) / 1e6 * df["cwp_1h"]
    expected_usd = cost_input + cost_output + cost_cache_hit + cost_cw_5m + cost_cw_1h

    # Multimodal override for Gemini image generation models
    pricing_map = pricing_engine.get_pricing()
    if "image_output_tokens" in df.columns:
        for mm_model, mm_pricing in pricing_map.items():
            if not (isinstance(mm_pricing, dict) and mm_pricing.get("_type") == "multimodal"):
                continue
            mm_mask = df["model"] == mm_model
            if not mm_mask.any():
                continue
            mm_ip       = mm_pricing.get("ip", 0)
            mm_op_text  = mm_pricing.get("op_text", 0)
            mm_op_image = mm_pricing.get("op_image", 0)
            mm_pt  = df.loc[mm_mask, "prompt_tokens"].astype(float)
            mm_ct  = df.loc[mm_mask, "completion_tokens"].astype(float)
            mm_img = df.loc[mm_mask, "image_output_tokens"].fillna(0).astype(float)
            mm_text_out = (mm_ct - mm_img).clip(lower=0)
            mm_cost = (mm_pt / 1e6 * mm_ip
                       + mm_text_out / 1e6 * mm_op_text
                       + mm_img / 1e6 * mm_op_image)
            expected_usd = expected_usd.copy()
            expected_usd.loc[mm_mask] = mm_cost.values

    billed_usd = df["quota"].astype(float) / pricing_engine.QUOTA_TO_USD

    if flat_tier:
        if flat_tier_since_ts is not None and "created_at" in df.columns:
            use_expected = (df["model"].isin(pricing_engine.FLAT_TIER_MODELS()) &
                           (df["created_at"].astype(int) >= flat_tier_since_ts))
            price_base = np.where(use_expected, expected_usd, billed_usd)
        else:
            price_base = expected_usd
    else:
        price_base = billed_usd

    df["expected_usd"] = expected_usd.round(6)
    df["billed_usd"] = billed_usd.round(6)
    df["list_price_usd"] = pd.Series(price_base).round(6)

    df["cost_discount"] = _vectorized_discount(
        df, "channel_id", "model", pricing_engine.get_cost_discount)
    df["revenue_discount"] = _vectorized_discount(
        df, "user_id", "model", pricing_engine.get_revenue_discount)

    df["cost_usd"] = (pd.Series(price_base) * df["cost_discount"]).round(6)
    df["revenue_usd"] = (pd.Series(price_base) * df["revenue_discount"]).round(6)
    df["profit_usd"] = (df["revenue_usd"] - df["cost_usd"]).round(6)

    # Drop internal pricing columns
    drop_cols = [c for c in ("ip", "op", "chp", "cwp", "cwp_1h", "model")
                 if c in df.columns and c != "model_name"]
    df = df.drop(columns=drop_cols, errors="ignore")

    # Reorder columns for readability
    priority_cols = [
        "request_id", "created_at", "user_id", "username", "channel_id",
        "model_name", "token_name", "prompt_tokens", "completion_tokens",
        "cache_hit_tokens", "cache_write_tokens", "cw_5m", "cw_1h", "cw_remaining",
        "billed_usd", "expected_usd", "list_price_usd",
        "cost_discount", "cost_usd", "revenue_discount", "revenue_usd", "profit_usd",
        "use_time_seconds", "is_stream",
    ]
    ordered = [c for c in priority_cols if c in df.columns]
    remaining = [c for c in df.columns if c not in ordered]
    df = df[ordered + remaining]

    return df


# ---------------------------------------------------------------------------
# Daily report
# ---------------------------------------------------------------------------

def generate_daily_report(date: str, output_dir: str,
                          channel_id: int = None,
                          no_cache: bool = False,
                          detail: bool = False,
                          split_channels: bool = True,
                          write_summary: bool = True) -> str | list[str]:
    """Generate daily report Excel with xlsxwriter formatting.

    When split_channels=True and channel_id is not set, also emits one workbook
    per upstream channel for the same date.
    """
    os.makedirs(output_dir, exist_ok=True)
    ch_suffix = _channel_suffix(channel_id=channel_id)
    filepath = os.path.join(output_dir, f"daily_report_{date}{ch_suffix}.xlsx")

    parts = date.split("-")
    year_month = f"{parts[0]}-{parts[1]}"
    day = parts[2]

    df_models = run_query_cached(
        queries.model_ranking(year_month, start_day=date, end_day=date, channel_id=channel_id),
        no_cache=no_cache,
    )
    df_users = run_query_cached(
        queries.monthly_bill_by_user(year_month, start_day=date, end_day=date, channel_id=channel_id),
        no_cache=no_cache,
    )
    df_hourly = run_query_cached(
        queries.hourly_distribution(year_month, day, channel_id=channel_id),
        no_cache=no_cache,
    )
    df_kpi = run_query_cached(
        queries.kpi_summary(year_month, start_day=date, end_day=date, channel_id=channel_id),
        no_cache=no_cache,
    )

    wb = xlsxwriter.Workbook(filepath)

    # --- Hourly distribution ---
    h_hdrs = ["小时 (UTC)", "调用次数", "总 Tokens", "费用 (USD)"]
    h_wids = [14, 12, 14, 14]
    h_fmts = [None, TOK, TOK, USD4]
    h_data = []
    for _, r in df_hourly.iterrows():
        h_data.append([
            f"{int(r['hour']):02d}:00", int(r["call_count"]),
            int(r["total_tokens"]), float(r["total_usd"]),
        ])
    write_sheet(wb, f"日报 -- {date} (按小时分布)", "按小时分布",
                h_hdrs, h_wids, h_data, h_fmts)

    # --- Model ranking ---
    m_hdrs = ["模型", "调用次数", "总 Tokens", "费用 (USD)", "平均延迟 (s)", "流式占比 (%)"]
    m_wids = [28, 12, 14, 14, 14, 14]
    m_fmts = [None, TOK, TOK, USD2, "0.0", PCT]
    m_data = []
    for _, r in df_models.iterrows():
        m_data.append([
            r["model_name"], int(r["call_count"]), int(r["total_tokens"]),
            float(r["total_usd"]), float(r["avg_latency_sec"]),
            float(r["stream_pct"]) / 100.0,
        ])
    write_sheet(wb, f"日报 -- {date} (模型排行)", "模型排行",
                m_hdrs, m_wids, m_data, m_fmts)

    # --- User ranking ---
    u_hdrs = ["用户 ID", "用户名", "调用次数", "费用 (USD)"]
    u_wids = [12, 20, 12, 14]
    u_fmts = [TOK, None, TOK, USD2]
    u_data = []
    for _, r in df_users.iterrows():
        u_data.append([
            int(r["user_id"]), r["username"],
            int(r["call_count"]), float(r["total_usd"]),
        ])
    write_sheet(wb, f"日报 -- {date} (用户排行)", "用户排行",
                u_hdrs, u_wids, u_data, u_fmts)

    # --- Query Cost Summary ---
    if COST_MONITOR_AVAILABLE:
        _add_cost_worksheet(wb, f"日报 -- {date} (查询成本)")

    wb.close()

    detail_path = None
    if detail:
        detail_path = _export_detail_csv(
            year_month,
            output_dir,
            channel_id=channel_id,
            start_day=date,
            end_day=date,
        )
        gc.collect()

    per_channel_paths: list[str] = []
    if split_channels and channel_id is None:
        df_channels = run_query_cached(
            queries.channel_summary(year_month, start_day=date, end_day=date),
            no_cache=no_cache,
        )
        if not df_channels.empty:
            for ch in sorted(int(value) for value in df_channels["channel_id"].unique()):
                logger.info(
                    "Generating per-channel daily snapshot",
                    extra={"event": "split_channel_daily", "channel_id": ch, "date": date},
                )
                ch_result = generate_daily_report(
                    date,
                    output_dir,
                    channel_id=ch,
                    no_cache=no_cache,
                    detail=detail,
                    split_channels=False,
                    write_summary=False,
                )
                if isinstance(ch_result, list):
                    per_channel_paths.extend(str(path) for path in ch_result)
                else:
                    per_channel_paths.append(str(ch_result))

    output_paths = [filepath]
    if detail_path:
        output_paths.append(detail_path)
    output_paths.extend(per_channel_paths)
    if write_summary:
        df_full = run_query_cached(
            queries.monthly_bill_full(year_month, start_day=date, end_day=date, channel_id=channel_id),
            no_cache=no_cache,
        )
        if not df_full.empty:
            df_full = pricing_engine.apply_pricing_summary(df_full)
        summary_path = _write_bill_summary(
            output_dir,
            date,
            df_full,
            bill_type="daily_channel_cost_snapshot",
            detail_path=detail_path,
            xlsx_path=filepath,
            per_channel_paths=per_channel_paths,
            extra={"period": date, "snapshot_date": date},
        )
        output_paths.append(summary_path)
    return output_paths if len(output_paths) > 1 else filepath


# ---------------------------------------------------------------------------
# Anomaly report
# ---------------------------------------------------------------------------

def generate_anomaly_report(year_month: str, output_dir: str,
                            no_cache: bool = False) -> str:
    """Generate anomaly detection report with xlsxwriter formatting."""
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"anomaly_{year_month}.xlsx")

    df_zero = run_query_cached(queries.anomaly_zero_tokens(year_month), no_cache=no_cache)
    df_dup = run_query_cached(queries.duplicate_billing(year_month), no_cache=no_cache)

    wb = xlsxwriter.Workbook(filepath)

    # --- Zero tokens ---
    z_hdrs = ["Request ID", "时间", "用户 ID", "用户名", "模型", "渠道 ID", "费用 (USD)"]
    z_wids = [16, 22, 10, 16, 28, 10, 14]
    z_fmts = [None, None, TOK, None, None, TOK, USD6]
    z_data = []
    if not df_zero.empty:
        for _, r in df_zero.iterrows():
            z_data.append([
                r["request_id"], str(r["created_time"]),
                int(r["user_id"]), r["username"], r["model_name"],
                int(r["channel_id"]), float(r["quota_usd"]),
            ])
        total_loss = sum(d[6] for d in z_data)
        z_tot = ["合计", "", "", "", "", "", total_loss]
        write_sheet(wb, f"异常扣费 -- {year_month} (quota>0, tokens=0)",
                    "异常扣费", z_hdrs, z_wids, z_data, z_fmts,
                    total_row=z_tot, total_fmts=z_fmts)
    else:
        ws = wb.add_worksheet("异常扣费")
        ws.write(0, 0, f"异常检测报告 — {year_month}：无异常扣费记录")

    # --- Duplicate billing ---
    d_hdrs = ["Request ID", "时间", "用户 ID", "用户名", "模型",
              "Token 名", "输入", "输出", "费用 (USD)", "间隔 (秒)"]
    d_wids = [16, 22, 10, 16, 28, 18, 12, 12, 14, 10]
    d_fmts = [None, None, TOK, None, None, None, TOK, TOK, USD6, TOK]
    d_data = []
    if not df_dup.empty:
        for _, r in df_dup.iterrows():
            d_data.append([
                r["request_id"], str(r["created_time"]),
                int(r["user_id"]), r["username"], r["model_name"],
                r["token_name"],
                int(r["prompt_tokens"]), int(r["completion_tokens"]),
                float(r["quota_usd"]), int(r["gap_seconds"]),
            ])
        write_sheet(wb, f"疑似重复计费 -- {year_month}",
                    "疑似重复计费", d_hdrs, d_wids, d_data, d_fmts)
    else:
        ws = wb.add_worksheet("疑似重复计费")
        ws.write(0, 0, f"疑似重复计费 — {year_month}：无疑似记录")

    wb.close()
    return filepath


# ---------------------------------------------------------------------------
# Recalc report (tiered pricing recalculation)
# ---------------------------------------------------------------------------

def generate_recalc_report(start_date: str, end_date: str, output_dir: str,
                           user_id: int = None, channel_id: int = None,
                           flat_tier: bool = False, flat_tier_since: str = None,
                           no_cache: bool = False) -> str:
    """Generate recalculation report with xlsxwriter formatting."""
    os.makedirs(output_dir, exist_ok=True)
    suffix_parts = [start_date, end_date]
    if user_id:
        suffix_parts.append(f"u{user_id}")
    if flat_tier:
        suffix_parts.append("flat")
    filename = f"recalc_{'_'.join(suffix_parts)}.xlsx"
    filepath = os.path.join(output_dir, filename)

    df_raw = run_query_cached(
        queries.raw_usage_detail(start_date, end_date,
                                 user_id=user_id, channel_id=channel_id),
        no_cache=no_cache)

    if df_raw.empty:
        wb = xlsxwriter.Workbook(filepath)
        ws = wb.add_worksheet("无数据")
        ws.write(0, 0, "指定时间段内无数据")
        wb.close()
        return filepath

    df = pricing_engine.recalc_from_raw(df_raw, flat_tier=flat_tier,
                                        flat_tier_since=flat_tier_since)

    has_pricing = df[df["has_pricing"] == True]

    tier_tag = ""
    if flat_tier:
        tier_tag = f"（降档自 {flat_tier_since}）" if flat_tier_since else "（统一低档价）"

    wb = xlsxwriter.Workbook(filepath)

    # ── Tab 1: 按用户×模型汇总 ──
    if not has_pricing.empty:
        grp = has_pricing.groupby(["user_id", "username", "model"]).agg({
            "expected_usd": "sum",
            "billed_usd": "sum",
            "diff_usd": "sum",
            "cost_usd": "sum",
            "revenue_usd": "sum",
            "profit_usd": "sum",
            "request_id": "count",
        }).reset_index().rename(columns={"request_id": "call_count"})
        grp["margin"] = grp["profit_usd"] / grp["revenue_usd"].replace(0, np.nan)
        grp = grp.sort_values("billed_usd", ascending=False)

        s_hdrs = ["用户 ID", "用户名", "模型", "调用数",
                  "重算刊例价", "系统扣费", "差额",
                  "客户应付", "成本", "利润", "利润率"]
        s_wids = [10, 16, 28, 10, 16, 16, 14, 16, 16, 14, 10]
        s_fmts = [TOK, None, None, TOK, USD4, USD4, USD4, USD4, USD4, USD4, PCT]

        s_data = []
        for _, r in grp.iterrows():
            s_data.append([
                int(r["user_id"]), r["username"], r["model"],
                int(r["call_count"]),
                float(r["expected_usd"]), float(r["billed_usd"]),
                float(r["diff_usd"]),
                float(r["revenue_usd"]), float(r["cost_usd"]),
                float(r["profit_usd"]),
                float(r["margin"]) if pd.notna(r["margin"]) else 0,
            ])

        sum_cols = ["call_count", "expected_usd", "billed_usd", "diff_usd",
                    "revenue_usd", "cost_usd", "profit_usd"]
        tots = {c: float(grp[c].sum()) for c in sum_cols}
        tot_margin = tots["profit_usd"] / tots["revenue_usd"] if tots["revenue_usd"] else 0
        s_tot = [
            "合计", "", "", int(tots["call_count"]),
            tots["expected_usd"], tots["billed_usd"], tots["diff_usd"],
            tots["revenue_usd"], tots["cost_usd"], tots["profit_usd"],
            tot_margin,
        ]

        write_sheet(wb, f"重算报告 -- {start_date}~{end_date} (汇总){tier_tag}",
                    "汇总", s_hdrs, s_wids, s_data, s_fmts,
                    total_row=s_tot, total_fmts=s_fmts)
    else:
        ws = wb.add_worksheet("汇总")
        ws.write(0, 0, "无定价表匹配的记录")

    # ── Tab 2: 差异分析 ──
    if not has_pricing.empty:
        big_diff = has_pricing[has_pricing["diff_usd"].abs() > 0.001].sort_values(
            "diff_usd", ascending=False, key=abs).head(500)
        if not big_diff.empty:
            dd_hdrs = ["Request ID", "模型", "用户 ID", "渠道 ID",
                       "Prompt Tokens", "重算价", "系统扣费", "差额"]
            dd_wids = [16, 28, 10, 10, 14, 16, 16, 14]
            dd_fmts = [None, None, TOK, TOK, TOK, USD6, USD6, USD6]
            dd_data = []
            for _, r in big_diff.iterrows():
                dd_data.append([
                    str(r["request_id"]), r["model"],
                    int(r.get("user_id", 0)), int(r.get("channel_id", 0)),
                    int(r["prompt_tokens"]),
                    float(r["expected_usd"]), float(r["billed_usd"]),
                    float(r["diff_usd"]),
                ])
            write_sheet(wb, f"差异分析 -- 系统扣费 vs 重算 (差额>{0.001}$)",
                        "差异分析", dd_hdrs, dd_wids, dd_data, dd_fmts)

    wb.close()
    return filepath


# ---------------------------------------------------------------------------
# Cross-check report (our data vs vendor bill)
# ---------------------------------------------------------------------------

def generate_crosscheck_report(year_month: str, vendor_bill_path: str,
                               output_dir: str,
                               channel_id: int = None,
                               column_mapping: dict = None,
                               no_cache: bool = False) -> str:
    """Generate cross-check report with xlsxwriter formatting."""
    import cost_import

    os.makedirs(output_dir, exist_ok=True)
    vendor_name = os.path.basename(vendor_bill_path)
    filename = f"crosscheck_{year_month}_{vendor_name.split('.')[0]}.xlsx"
    filepath = os.path.join(output_dir, filename)

    vendor_df = cost_import.import_and_summarize(
        vendor_bill_path, column_mapping=column_mapping,
        channel_id=channel_id, month=year_month)

    our_sql = queries.monthly_bill_full(year_month)
    our_df = run_query_cached(our_sql, no_cache=no_cache)

    if not our_df.empty:
        our_df = pricing_engine.apply_pricing_summary(our_df)
        if channel_id is not None:
            our_df = our_df[our_df["channel_id"].astype(int) == int(channel_id)]
        our_agg = our_df.groupby("model_name").agg({
            "call_count": "sum",
            "list_price_usd": "sum",
        }).reset_index()
    else:
        our_agg = pd.DataFrame(columns=["model_name", "call_count", "list_price_usd"])

    merged = pricing_engine.cross_check(our_agg, vendor_df, match_col="model_name")

    wb = xlsxwriter.Workbook(filepath)

    # ── Tab 1: 对账汇总 ──
    c_hdrs = ["模型名称",
              "我方记录数", "供应商记录数",
              "我方刊例价", "供应商金额",
              "差额", "差额 %"]
    c_wids = [28, 12, 12, 16, 16, 14, 10]
    c_fmts = [None, TOK, TOK, USD2, USD2, USD4, PCT]

    c_data = []
    for _, r in merged.iterrows():
        our_cnt = int(r.get("call_count", 0))
        v_cnt = int(r.get("vendor_count", 0))
        our_amt = float(r.get("our_amount", 0))
        v_amt = float(r.get("vendor_amount", 0))
        diff = float(r.get("diff", our_amt - v_amt))
        diff_pct = float(r.get("diff_pct", 0)) / 100.0 if "diff_pct" in r.index else 0
        c_data.append([
            r["model"], our_cnt, v_cnt,
            our_amt, v_amt, diff, diff_pct,
        ])

    sum_our = sum(d[3] for d in c_data)
    sum_v = sum(d[4] for d in c_data)
    sum_diff = sum(d[5] for d in c_data)
    tot_pct = sum_diff / sum_v if sum_v else 0
    c_tot = [
        "合计",
        sum(d[1] for d in c_data), sum(d[2] for d in c_data),
        sum_our, sum_v, sum_diff, tot_pct,
    ]

    write_sheet(wb, f"对账报告 -- {year_month} (我方 vs 供应商)",
                "对账汇总", c_hdrs, c_wids, c_data, c_fmts,
                total_row=c_tot, total_fmts=c_fmts)

    # ── Tab 2: 供应商原始数据 ──
    v_hdrs = list(vendor_df.columns)
    v_wids = [max(12, len(h) + 4) for h in v_hdrs]
    v_fmts = [None] * len(v_hdrs)
    v_data = []
    for _, r in vendor_df.iterrows():
        v_data.append([r[c] for c in vendor_df.columns])
    write_sheet(wb, f"供应商原始数据 -- {vendor_name}",
                "供应商原始数据", v_hdrs, v_wids, v_data, v_fmts)

    wb.close()
    return filepath


# ---------------------------------------------------------------------------
# Row-level crosscheck report (request_id matching)
# ---------------------------------------------------------------------------

def generate_tz_offset_export(year_month: str, output_dir: str,
                              tz_offset_hours: float = 8.0,
                              user_id: int = None,
                              channel_id: int = None,
                              channel_ids: list[int] = None,
                              currency: str = "USD",
                              exchange_rate: float = 7.3,
                              flat_tier: bool = False,
                              flat_tier_since: str = None,
                              detail: bool = False,
                              customer_view: bool = False,
                              upload_s3: bool = False,
                              no_cache: bool = False) -> str | list[str] | dict:
    """Generate monthly bill with dates re-partitioned by timezone offset.

    Unlike generate_monthly_bill which uses UTC partition boundaries,
    this groups all data by local-date (created_at + tz_offset), so each
    date row reflects a wall-clock day in the target timezone.
    """
    os.makedirs(output_dir, exist_ok=True)

    if flat_tier_since:
        flat_tier = True

    tz_label = f"utc{float(tz_offset_hours):+g}"
    suffix = f"_user{user_id}" if user_id else ""
    ch_suffix = _channel_suffix(channel_id=channel_id, channel_ids=channel_ids)
    tier_suffix = "_flattier" if flat_tier else ""
    cv_suffix = "_customer" if customer_view else ""
    filename = f"bill_{year_month}{suffix}{ch_suffix}{tier_suffix}_{tz_label}{cv_suffix}.xlsx"
    filepath = os.path.join(output_dir, filename)

    rate = exchange_rate if currency == "CNY" else 1.0
    symbol = "¥" if currency == "CNY" else "$"

    # Query with tz-shifted grouping
    df_full = run_query_cached(
        queries.monthly_bill_full_tz(year_month, tz_offset_hours=tz_offset_hours,
                                     user_id=user_id,
                                     channel_id=channel_id,
                                     channel_ids=channel_ids),
        no_cache=no_cache)
    df_trend = run_query_cached(
        queries.daily_trend_tz(year_month, tz_offset_hours=tz_offset_hours,
                               user_id=user_id,
                               channel_id=channel_id,
                               channel_ids=channel_ids),
        no_cache=no_cache)

    if df_full.empty:
        wb = xlsxwriter.Workbook(filepath)
        ws = wb.add_worksheet("无数据")
        ws.write(0, 0, "指定时间段内无数据")
        wb.close()
        return filepath

    df_full = pricing_engine.apply_pricing_summary(
        df_full, flat_tier=flat_tier, flat_tier_since=flat_tier_since)

    discount_anomalies = pricing_engine.detect_discount_anomalies(df_full)
    pricing_engine.log_discount_anomalies(discount_anomalies)

    tier_tag = ""
    if flat_tier:
        tier_tag = f"（降档自 {flat_tier_since}）" if flat_tier_since else "（统一低档价）"
    tz_display = f"UTC{float(tz_offset_hours):+g}"
    tier_tag += f" ({tz_display} 时区划分)"

    wb = xlsxwriter.Workbook(filepath, {"constant_memory": False})

    # ── Tab 1: 按用户汇总 ──
    has_cache = "total_cache_hit_tokens" in df_full.columns
    cache_agg_cols = {}
    if has_cache:
        cache_agg_cols = {
            "total_cache_hit_tokens": "sum",
            "total_cache_write_tokens": "sum",
            "total_cw_5m": "sum",
            "total_cw_1h": "sum",
            "total_cw_remaining": "sum",
        }

    user_agg = df_full.groupby(["user_id", "username"]).agg({
        "call_count": "sum",
        "total_input_tokens": "sum",
        "total_output_tokens": "sum",
        "list_price_usd": "sum",
        "revenue_usd": "sum",
        "cost_usd": "sum",
        "profit_usd": "sum",
        **cache_agg_cols,
    }).reset_index().sort_values("list_price_usd", ascending=False)
    user_agg["margin"] = user_agg["profit_usd"] / user_agg["revenue_usd"].replace(0, np.nan)
    if has_cache:
        user_agg["cw_5m_total"] = (user_agg["total_cw_5m"].astype(float)
                                   + user_agg["total_cw_remaining"].astype(float))

    if customer_view:
        u_hdrs = ["用户 ID", "用户名", "调用次数",
                  "输入 Tokens", "输出 Tokens", "缓存命中 Tokens",
                  "缓存写入 Tokens\n(5min)", "缓存写入 Tokens\n(1h)",
                  f"刊例价 ({symbol})", f"应付金额 ({symbol})"]
        u_wids = [10, 16, 12, 14, 14, 14, 14, 14, 16, 16]
        u_fmts = [TOK, None, TOK, TOK, TOK, TOK, TOK, TOK, USD2, USD2]
    else:
        u_hdrs = ["用户 ID", "用户名", "调用次数",
                  "输入 Tokens", "输出 Tokens",
                  f"刊例价 ({symbol})", f"客户应付 ({symbol})",
                  f"成本 ({symbol})", f"利润 ({symbol})", "利润率"]
        u_wids = [10, 16, 12, 14, 14, 16, 16, 16, 14, 10]
        u_fmts = [TOK, None, TOK, TOK, TOK, USD2, USD2, USD2, USD2, PCT]

    u_data = []
    for _, r in user_agg.iterrows():
        row = [int(r["user_id"]), r["username"], int(r["call_count"]),
               int(r["total_input_tokens"]), int(r["total_output_tokens"]),
        ]
        if customer_view and has_cache:
            row += [
                int(r["total_cache_hit_tokens"]),
                int(r["cw_5m_total"]),
                int(r["total_cw_1h"]),
            ]
        row += [float(r["list_price_usd"]) * rate,
                float(r["revenue_usd"]) * rate]
        if not customer_view:
            row += [float(r["cost_usd"]) * rate,
                    float(r["profit_usd"]) * rate,
                    float(r["margin"]) if pd.notna(r["margin"]) else 0]
        u_data.append(row)

    u_tots = {c: float(user_agg[c].sum()) for c in
              ["call_count", "total_input_tokens", "total_output_tokens",
               "list_price_usd", "revenue_usd"]}
    if has_cache:
        u_tots.update({c: float(user_agg[c].sum()) for c in
                       ["total_cache_hit_tokens", "cw_5m_total", "total_cw_1h"]})
    u_tot = ["合计", "", int(u_tots["call_count"]),
             int(u_tots["total_input_tokens"]), int(u_tots["total_output_tokens"]),
    ]
    if customer_view and has_cache:
        u_tot += [
            int(u_tots["total_cache_hit_tokens"]),
            int(u_tots["cw_5m_total"]),
            int(u_tots["total_cw_1h"]),
        ]
    u_tot += [u_tots["list_price_usd"] * rate, u_tots["revenue_usd"] * rate]
    if not customer_view:
        u_tots.update({c: float(user_agg[c].sum()) for c in ["cost_usd", "profit_usd"]})
        u_tot_margin = u_tots["profit_usd"] / u_tots["revenue_usd"] if u_tots["revenue_usd"] else 0
        u_tot += [u_tots["cost_usd"] * rate, u_tots["profit_usd"] * rate, u_tot_margin]

    write_sheet(wb, f"API 账单 -- {year_month} (用户汇总){tier_tag}",
                "用户汇总", u_hdrs, u_wids, u_data, u_fmts,
                total_row=u_tot, total_fmts=u_fmts)

    # ── Tab 2: 按模型汇总 ──
    show_cache_in_model_summary = has_cache
    model_agg = df_full.groupby("model_name").agg({
        "call_count": "sum",
        "total_input_tokens": "sum",
        "total_output_tokens": "sum",
        "total_quota": "sum",
        "list_price_usd": "sum",
        "revenue_usd": "sum",
        "cost_usd": "sum",
        "profit_usd": "sum",
        **cache_agg_cols,
    }).reset_index().sort_values("list_price_usd", ascending=False)
    model_agg["billed_usd"] = model_agg["total_quota"].astype(float) / QUOTA_TO_USD
    model_agg["margin"] = model_agg["profit_usd"] / model_agg["revenue_usd"].replace(0, np.nan)

    if has_cache:
        model_agg["cw_5m_total"] = (model_agg["total_cw_5m"].astype(float)
                                    + model_agg["total_cw_remaining"].astype(float))

    m_hdrs = ["模型名称", "调用次数"]
    m_wids = [28, 10]
    m_fmts = [None, TOK]
    if show_cache_in_model_summary:
        m_hdrs += ["输入 Tokens", "输出 Tokens", "缓存命中 Tokens",
                   "缓存写入\n(5min)", "缓存写入\n(1h)"]
        m_wids += [14, 14, 14, 14, 14]
        m_fmts += [TOK, TOK, TOK, TOK, TOK]
    else:
        m_hdrs += ["输入 Tokens", "输出 Tokens"]
        m_wids += [14, 14]
        m_fmts += [TOK, TOK]
    if customer_view:
        m_hdrs += [f"刊例价 ({symbol})", f"应付金额 ({symbol})"]
        m_wids += [16, 16]
        m_fmts += [USD2, USD2]
    else:
        m_hdrs += [f"刊例价\n(pricing重算)", "系统扣费\n(quota)",
                   f"客户应付", f"成本", "利润", "利润率"]
        m_wids += [16, 16, 16, 16, 14, 10]
        m_fmts += [USD2, USD2, USD2, USD2, USD2, PCT]

    m_data = []
    for _, r in model_agg.iterrows():
        row_data = [r["model_name"], int(r["call_count"])]
        if show_cache_in_model_summary:
            row_data += [int(r["total_input_tokens"]), int(r["total_output_tokens"]),
                         int(r["total_cache_hit_tokens"]),
                         int(r["cw_5m_total"]), int(r["total_cw_1h"])]
        else:
            row_data += [int(r["total_input_tokens"]), int(r["total_output_tokens"])]
        if customer_view:
            row_data += [float(r["list_price_usd"]) * rate,
                         float(r["revenue_usd"]) * rate]
        else:
            row_data += [float(r["list_price_usd"]) * rate,
                         float(r["billed_usd"]) * rate,
                         float(r["revenue_usd"]) * rate,
                         float(r["cost_usd"]) * rate,
                         float(r["profit_usd"]) * rate,
                         float(r["margin"]) if pd.notna(r["margin"]) else 0]
        m_data.append(row_data)

    write_sheet(wb, f"API 账单 -- {year_month} (模型汇总){tier_tag}",
                "模型汇总", m_hdrs, m_wids, m_data, m_fmts)

    # ── Tab 3: 按日期×模型明细 ──
    if "local_date" in df_full.columns:
        if customer_view:
            date_model_agg = df_full.groupby(["local_date", "model_name"]).agg({
                "call_count": "sum",
                "total_input_tokens": "sum",
                "total_output_tokens": "sum",
                "list_price_usd": "sum",
                "revenue_usd": "sum",
                **cache_agg_cols,
            }).reset_index().sort_values(["local_date", "list_price_usd"], ascending=[True, False])
            if has_cache:
                date_model_agg["cw_5m_total"] = (date_model_agg["total_cw_5m"].astype(float)
                                                 + date_model_agg["total_cw_remaining"].astype(float))
            dm_hdrs = [f"日期 ({tz_display})", "模型名称", "调用次数",
                       "输入 Tokens", "输出 Tokens", "缓存命中 Tokens",
                       "缓存写入 Tokens\n(5min)", "缓存写入 Tokens\n(1h)",
                       f"刊例价 ({symbol})", f"应付金额 ({symbol})"]
            dm_wids = [14, 28, 10, 14, 14, 14, 14, 14, 16, 16]
            dm_fmts = [None, None, TOK, TOK, TOK, TOK, TOK, TOK, USD4, USD4]
        else:
            date_model_agg = df_full.groupby(["local_date", "model_name"]).agg({
                "call_count": "sum",
                "total_input_tokens": "sum",
                "total_output_tokens": "sum",
                "list_price_usd": "sum",
                "revenue_usd": "sum",
                "cost_usd": "sum",
                "profit_usd": "sum",
            }).reset_index().sort_values(["local_date", "list_price_usd"], ascending=[True, False])
            dm_hdrs = [f"日期 ({tz_display})", "模型名称", "调用次数",
                       "输入 Tokens", "输出 Tokens",
                       f"刊例价 ({symbol})", f"客户应付 ({symbol})",
                       f"成本 ({symbol})", f"利润 ({symbol})"]
            dm_wids = [14, 28, 10, 14, 14, 16, 16, 16, 14]
            dm_fmts = [None, None, TOK, TOK, TOK, USD4, USD4, USD4, USD4]

        dm_data = []
        for _, r in date_model_agg.iterrows():
            row = [r["local_date"], r["model_name"], int(r["call_count"]),
                   int(r["total_input_tokens"]), int(r["total_output_tokens"]),
            ]
            if customer_view and has_cache:
                row += [
                    int(r["total_cache_hit_tokens"]),
                    int(r["cw_5m_total"]),
                    int(r["total_cw_1h"]),
                ]
            row += [float(r["list_price_usd"]) * rate,
                    float(r["revenue_usd"]) * rate]
            if not customer_view:
                row += [float(r["cost_usd"]) * rate,
                        float(r["profit_usd"]) * rate]
            dm_data.append(row)

        write_sheet(wb, f"API 账单 -- {year_month} (日期×模型){tier_tag}",
                    "日期×模型", dm_hdrs, dm_wids, dm_data, dm_fmts)

    # ── Tab 4: 每日趋势 ──
    if customer_view:
        t_hdrs = [f"日期 ({tz_display})", "调用次数", "输入+输出 Tokens",
                  "缓存命中 Tokens", "缓存写入 Tokens\n(5min)", "缓存写入 Tokens\n(1h)",
                  f"刊例价 ({symbol})"]
        t_wids = [14, 12, 16, 14, 14, 14, 14]
        t_fmts = [None, TOK, TOK, TOK, TOK, TOK, USD4]
    else:
        t_hdrs = [f"日期 ({tz_display})", "调用次数", "总 Tokens", "总额度", f"刊例价 ({symbol})"]
        t_wids = [14, 12, 14, 14, 14]
        t_fmts = [None, TOK, TOK, TOK, USD4]
    t_data = []
    if not df_trend.empty:
        for _, r in df_trend.iterrows():
            row_data = [r["local_date"], int(r["call_count"]), int(r["total_tokens"])]
            if customer_view and "total_cache_hit_tokens" in df_trend.columns:
                row_data += [
                    int(r["total_cache_hit_tokens"]),
                    int(r["total_cw_5m"]) + int(r["total_cw_remaining"]),
                    int(r["total_cw_1h"]),
                ]
            if not customer_view:
                row_data.append(int(r["total_quota"]))
            row_data.append(float(r["total_usd"]) * rate)
            t_data.append(row_data)
    write_sheet(wb, f"每日费用趋势 -- {year_month}{tier_tag}",
                "每日趋势", t_hdrs, t_wids, t_data, t_fmts)

    # --- 对账告警: internal-only sheet ---
    if not customer_view:
        _add_discount_anomaly_sheet(wb, discount_anomalies, year_month)

    wb.close()

    bill_summary = {
        "month": year_month,
        "total_usd": round(float(df_full["revenue_usd"].sum()), 2),
        "total_calls": int(df_full["call_count"].sum()),
        "unique_users": int(df_full["user_id"].nunique()),
        "unique_models": int(df_full["model_name"].nunique()),
        "total_input_tokens": int(df_full["total_input_tokens"].sum()),
        "total_output_tokens": int(df_full["total_output_tokens"].sum()),
        "xlsx": os.path.basename(filepath),
        "currency": currency,
    }
    summary_path = os.path.join(output_dir, "bill_summary.json")
    with open(summary_path, "w", encoding="utf-8") as fh:
        import json as _json
        _json.dump(bill_summary, fh, ensure_ascii=False, indent=2)

    if not detail and not upload_s3:
        return filepath

    detail_path = None
    if detail:
        detail_path = _export_detail_csv_tz(
            year_month, output_dir,
            tz_offset_hours=tz_offset_hours,
            user_id=user_id,
            channel_id=channel_id,
            channel_ids=channel_ids,
            flat_tier=flat_tier,
            flat_tier_since=flat_tier_since,
            customer_view=customer_view)

    if upload_s3:
        return _upload_results(filepath, detail_path)

    if detail_path:
        return [filepath, detail_path]
    return filepath


def _export_detail_csv_tz(year_month: str, output_dir: str,
                          tz_offset_hours: float = 8.0,
                          user_id: int = None,
                          channel_id: int = None,
                          channel_ids: list[int] = None,
                          model: str = None,
                          flat_tier: bool = False,
                          flat_tier_since: str = None,
                          customer_view: bool = False) -> str:
    """Export row-level detail with dates partitioned by timezone offset."""
    tz_label = f"utc{float(tz_offset_hours):+g}"
    suffix = f"_user{user_id}" if user_id else ""
    ch_suffix = _channel_suffix(channel_id=channel_id, channel_ids=channel_ids)
    tier_suffix = "_flattier" if flat_tier else ""
    cv_suffix = "_customer" if customer_view else ""

    local_dates = queries.detail_day_list_tz(year_month, tz_offset_hours=tz_offset_hours)
    sqls = [
        queries.raw_usage_detail_daily_tz(year_month, local_date=ld,
                                          tz_offset_hours=tz_offset_hours,
                                          user_id=user_id,
                                          channel_id=channel_id,
                                          channel_ids=channel_ids,
                                          model=model)
        for ld in local_dates
    ]

    logger.info("Submitting daily queries with timezone",
                extra={"event": "detail_tz_start", "query_count": len(sqls), "timezone": tz_label})
    t0 = time.time()
    total_rows = 0
    days_done = 0
    all_chunks: list[pd.DataFrame] = []

    for idx, df_day in run_queries_parallel_iter(sqls):
        days_done += 1
        if df_day.empty:
            continue

        df_day = _apply_detail_pricing(df_day, flat_tier=flat_tier,
                                       flat_tier_since=flat_tier_since)
        total_rows += len(df_day)
        all_chunks.append(df_day)

        elapsed = time.time() - t0
        logger.debug("Day query completed (timezone)",
                     extra={
                         "event": "detail_tz_day",
                         "local_date": local_dates[idx],
                         "rows": len(df_day),
                         "days_done": days_done,
                         "total_days": len(sqls),
                         "total_rows": total_rows,
                         "elapsed_s": elapsed,
                     })

    elapsed = time.time() - t0

    if total_rows == 0:
        logger.warning("No detail data found (timezone)", extra={"event": "detail_tz_no_data"})
        all_chunks = [pd.DataFrame()]

    df_all = pd.concat(all_chunks, ignore_index=True) if all_chunks else pd.DataFrame()
    df_all = pricing_engine.dedupe_usage_log_rows(df_all)

    if customer_view:
        df_all = pricing_engine.collapse_postpaid_detail_rows(df_all)
        out_path = _write_detail_xlsx_customer(
            df_all, year_month, output_dir, user_id=user_id,
            channel_id=channel_id, channel_ids=channel_ids,
            flat_tier=flat_tier,
            tier_suffix=tier_suffix, from_suffix=f"_{tz_label}",
            day_suffix=cv_suffix)
    else:
        out_path = _write_detail_csv_internal(
            df_all, year_month, output_dir,
            suffix=suffix, ch_suffix=ch_suffix, tier_suffix=tier_suffix,
            from_suffix=f"_{tz_label}", day_suffix="")

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    logger.info("Detail export completed (timezone)",
                extra={
                    "event": "detail_tz_complete",
                    "total_rows": total_rows,
                    "size_mb": size_mb,
                    "elapsed_s": elapsed,
                })

    return out_path


def generate_row_level_crosscheck_report(
        vendor_files: list[str],
        output_dir: str,
        channel_id: int = None,
        no_cache: bool = False) -> str:
    """Generate row-level crosscheck report against vendor bills.

    Supports the channel-25 逐条明细 format: each row is one API request
    with request_id, model_name, quota, prompt_tokens, etc.

    Multiple vendor files can be provided (e.g. split by time range).

    Steps:
      1. Import all vendor files, detect created_at range
      2. Query our Athena data for the same time range + channel
      3. Match by request_id, report differences
    """
    import cost_import

    os.makedirs(output_dir, exist_ok=True)

    # 1. Import vendor data
    logger.info("Importing vendor bills",
                extra={"event": "crosscheck_import", "file_count": len(vendor_files)})
    vendor_df = cost_import.import_row_level_bill(
        vendor_files, channel_id=channel_id)
    vendor_amount = float(vendor_df['vendor_usd'].sum())
    logger.info("Vendor data imported",
                extra={"event": "crosscheck_vendor_imported", "vendor_rows": len(vendor_df), "vendor_amount": vendor_amount})

    # 2. Detect time range from vendor data
    if "created_at" not in vendor_df.columns:
        raise ValueError("供应商账单缺少 created_at 列，无法确定时间范围")

    ts_min = int(vendor_df["created_at"].min())
    ts_max = int(vendor_df["created_at"].max()) + 1

    from datetime import datetime as _dt, timezone as _tz
    dt_min = _dt.fromtimestamp(ts_min, tz=_tz.utc)
    dt_max = _dt.fromtimestamp(ts_max, tz=_tz.utc)
    logger.info("Time range detected",
                extra={"event": "crosscheck_time_range", "dt_min": dt_min.isoformat(), "dt_max": dt_max.isoformat()})

    # 3. Query our data from Athena
    logger.info("Querying our Athena data",
                extra={"event": "crosscheck_our_query", "channel_id": channel_id})
    our_sql = queries.usage_by_created_at_range(
        ts_min, ts_max, channel_id=channel_id)
    our_df = run_query_cached(our_sql, no_cache=no_cache)
    if not our_df.empty and "upstream_task_id" in our_df.columns:
        vendor_ids = set(vendor_df["request_id"].astype(str))
        upstream_ids = our_df["upstream_task_id"].fillna("").astype(str)
        use_upstream_id = upstream_ids.isin(vendor_ids)
        if use_upstream_id.any():
            our_df = our_df.copy()
            our_df.loc[use_upstream_id, "request_id"] = upstream_ids[use_upstream_id]
    our_amount = float(our_df['billed_usd'].sum()) if not our_df.empty else 0.0
    logger.info("Our data queried",
                extra={"event": "crosscheck_our_queried", "our_rows": len(our_df), "our_amount": our_amount})

    if our_df.empty:
        our_df = pd.DataFrame(columns=["request_id", "model_name", "quota",
                                        "billed_usd", "prompt_tokens",
                                        "completion_tokens"])

    # 4. Row-level crosscheck
    logger.info("Performing row-level crosscheck", extra={"event": "crosscheck_match"})
    result = pricing_engine.cross_check_row_level(our_df, vendor_df)
    stats = result["stats"]

    # 5. Generate report
    time_label = f"{dt_min:%Y%m%d_%H%M}-{dt_max:%Y%m%d_%H%M}"
    ch_label = f"_ch{channel_id}" if channel_id else ""
    filename = f"crosscheck_rowlevel_{time_label}{ch_label}.xlsx"
    filepath = os.path.join(output_dir, filename)

    wb = xlsxwriter.Workbook(filepath, {"constant_memory": False})

    # ── Tab 0: 对账概览 ──
    ws_info = wb.add_worksheet("对账概览")
    ws_info.set_column(0, 0, 24)
    ws_info.set_column(1, 1, 30)
    row = _write_info_sheet(wb, ws_info, 0, [
        ("对账类型", "逐条 request_id 对账"),
        ("时间范围 (UTC)", f"{dt_min:%Y-%m-%d %H:%M} ~ {dt_max:%Y-%m-%d %H:%M}"),
        ("渠道 ID", str(channel_id or "全部")),
        ("供应商文件数", str(len(vendor_files))),
        ("", ""),
        ("我方总记录数", f"{stats['total_our_records']:,}"),
        ("供应商总记录数", f"{stats['total_vendor_records']:,}"),
        ("匹配记录数", f"{stats['matched_records']:,}"),
        ("仅我方有", f"{stats['only_ours_records']:,}"),
        ("仅供应商有", f"{stats['only_vendor_records']:,}"),
        ("金额不一致", f"{stats['quota_mismatched']:,}"),
        ("", ""),
        ("我方总金额 (USD)", f"${stats['our_total_usd']:,.4f}"),
        ("供应商总金额 (USD)", f"${stats['vendor_total_usd']:,.4f}"),
        ("总差额 (USD)", f"${stats['our_total_usd'] - stats['vendor_total_usd']:,.4f}"),
        ("匹配部分我方 (USD)", f"${stats['matched_our_usd']:,.4f}"),
        ("匹配部分供应商 (USD)", f"${stats['matched_vendor_usd']:,.4f}"),
        ("仅我方金额 (USD)", f"${stats['only_ours_usd']:,.4f}"),
        ("仅供应商金额 (USD)", f"${stats['only_vendor_usd']:,.4f}"),
    ])

    # ── Tab 1: 模型汇总对比 ──
    summary = result["summary"]
    s_hdrs = ["模型名称", "我方记录数", "供应商记录数", "记录差",
              "我方金额 ($)", "供应商金额 ($)", "差额 ($)", "差额 %"]
    s_wids = [28, 14, 14, 10, 16, 16, 14, 10]
    s_fmts = [None, TOK, TOK, TOK, USD2, USD2, USD4, PCT]
    s_data = []
    for _, r in summary.iterrows():
        s_data.append([
            r["model_name"], int(r["our_count"]), int(r["vendor_count"]),
            int(r["count_diff"]),
            float(r["our_usd"]), float(r["vendor_usd"]),
            float(r["usd_diff"]),
            float(r["diff_pct"]) / 100 if pd.notna(r["diff_pct"]) else 0,
        ])
    s_tot = [
        "合计",
        int(summary["our_count"].sum()), int(summary["vendor_count"].sum()),
        int(summary["count_diff"].sum()),
        float(summary["our_usd"].sum()), float(summary["vendor_usd"].sum()),
        float(summary["usd_diff"].sum()),
        float(summary["usd_diff"].sum()) / float(summary["vendor_usd"].sum())
        if float(summary["vendor_usd"].sum()) else 0,
    ]
    write_sheet(wb, "模型汇总对比", "模型汇总",
                s_hdrs, s_wids, s_data, s_fmts,
                total_row=s_tot, total_fmts=s_fmts)

    # ── Tab 2: 金额不一致记录 ──
    matched = result["matched"]
    mismatched = matched[matched["quota_diff"].abs() > 0] if not matched.empty else matched
    if not mismatched.empty:
        mismatched = mismatched.sort_values("usd_diff", ascending=False, key=abs).head(10000)
        mm_hdrs = ["Request ID", "模型", "我方 Quota", "供应商 Quota",
                   "Quota 差", "我方 ($)", "供应商 ($)", "差额 ($)"]
        mm_wids = [24, 28, 14, 14, 14, 14, 14, 14]
        mm_fmts = [None, None, TOK, TOK, TOK, USD6, USD6, USD6]
        mm_data = []
        for _, r in mismatched.iterrows():
            mm_data.append([
                str(r["request_id"]), r["model_name"],
                int(r["our_quota"]), int(r["vendor_quota"]),
                int(r["quota_diff"]),
                float(r["our_usd"]), float(r["vendor_usd"]),
                float(r["usd_diff"]),
            ])
        write_sheet(wb, "金额不一致记录 (quota 差异)",
                    "金额不一致", mm_hdrs, mm_wids, mm_data, mm_fmts)
    else:
        ws = wb.add_worksheet("金额不一致")
        ws.write(0, 0, "所有匹配记录的 quota 完全一致")

    # ── Tab 3: 仅我方有的记录 ──
    only_ours = result["only_ours"]
    if not only_ours.empty:
        oo_show = only_ours.head(50000)
        oo_hdrs = ["Request ID", "模型", "Quota", "USD",
                   "Prompt Tokens", "Completion Tokens"]
        oo_wids = [24, 28, 14, 14, 14, 14]
        oo_fmts = [None, None, TOK, USD6, TOK, TOK]
        oo_data = []
        for _, r in oo_show.iterrows():
            oo_data.append([
                str(r.get("request_id", "")), str(r.get("model_name", "")),
                int(r.get("quota", 0)), float(r.get("billed_usd", 0)),
                int(r.get("prompt_tokens", 0)), int(r.get("completion_tokens", 0)),
            ])
        oo_tot = [
            f"合计 ({len(only_ours):,} 条)", "", "",
            float(only_ours["billed_usd"].sum()), "", "",
        ]
        write_sheet(wb, f"仅我方有 ({len(only_ours):,} 条)",
                    "仅我方", oo_hdrs, oo_wids, oo_data, oo_fmts,
                    total_row=oo_tot, total_fmts=oo_fmts)
    else:
        ws = wb.add_worksheet("仅我方")
        ws.write(0, 0, "无仅我方有的记录")

    # ── Tab 4: 仅供应商有的记录 ──
    only_vendor = result["only_vendor"]
    if not only_vendor.empty:
        ov_show = only_vendor.head(50000)
        ov_hdrs = ["Request ID", "模型", "Quota", "USD",
                   "Prompt Tokens", "Completion Tokens"]
        ov_wids = [24, 28, 14, 14, 14, 14]
        ov_fmts = [None, None, TOK, USD6, TOK, TOK]
        ov_data = []
        for _, r in ov_show.iterrows():
            ov_data.append([
                str(r.get("request_id", "")), str(r.get("model_name", "")),
                int(r.get("quota", 0)), float(r.get("vendor_usd", 0)),
                int(r.get("prompt_tokens", 0)), int(r.get("completion_tokens", 0)),
            ])
        ov_tot = [
            f"合计 ({len(only_vendor):,} 条)", "", "",
            float(only_vendor["vendor_usd"].sum()), "", "",
        ]
        write_sheet(wb, f"仅供应商有 ({len(only_vendor):,} 条)",
                    "仅供应商", ov_hdrs, ov_wids, ov_data, ov_fmts,
                    total_row=ov_tot, total_fmts=ov_fmts)
    else:
        ws = wb.add_worksheet("仅供应商")
        ws.write(0, 0, "无仅供应商有的记录")

    wb.close()

    # Log summary
    logger.info("Row-level crosscheck completed",
                extra={
                    "event": "crosscheck_complete",
                    "matched_records": stats['matched_records'],
                    "total_our_records": stats['total_our_records'],
                    "total_vendor_records": stats['total_vendor_records'],
                    "only_ours_records": stats['only_ours_records'],
                    "only_vendor_records": stats['only_vendor_records'],
                    "quota_mismatched": stats['quota_mismatched'],
                    "total_diff": stats['our_total_usd'] - stats['vendor_total_usd'],
                    "our_total_usd": stats['our_total_usd'],
                    "vendor_total_usd": stats['vendor_total_usd'],
                })

    return filepath
