"""
Excel 报表生成器 — 月度账单、日报、异常报告、重算报告、对账报告

使用 xlsxwriter 生成带格式的 .xlsx 文件（对齐 gen_bill.py 样式）。
"""

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
                          upload_and_sign, QUOTA_TO_USD)
import queries
import pricing_engine

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
                          detail: bool = False,
                          customer_view: bool = False,
                          upload_s3: bool = False,
                          no_cache: bool = False) -> str | list[str] | dict:
    """Generate monthly bill Excel with xlsxwriter formatting.

    Uses fast aggregation queries (monthly_bill_full) with flat-tier applied
    at the summary level. For row-level precision, use generate_recalc_report.

    start_day / end_day: day-level boundary 'YYYY-MM-DD' (inclusive).
    start_time / end_time: 'YYYY-MM-DD HH:MM' UTC for sub-day precision;
        takes precedence over start_day / end_day when provided.

    When detail=True, also exports row-level data as compressed CSV alongside
    the summary Excel.

    When upload_s3=True, uploads all output files to S3 and returns a dict
    with local paths and presigned download URLs (24h expiry).
    """
    os.makedirs(output_dir, exist_ok=True)

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
    cv_suffix = "_customer" if customer_view else ""
    filename = f"bill_{year_month}{suffix}{ch_suffix}{tier_suffix}{from_suffix}{day_suffix}{cv_suffix}.xlsx"
    filepath = os.path.join(output_dir, filename)

    rate = exchange_rate if currency == "CNY" else 1.0
    symbol = "¥" if currency == "CNY" else "$"

    # Fast aggregation queries
    df_full = run_query_cached(
        queries.monthly_bill_full(year_month, user_id=user_id,
                                  channel_id=channel_id,
                                  channel_ids=channel_ids,
                                  start_day=start_day, end_day=end_day,
                                  start_time=start_time, end_time=end_time),
        no_cache=no_cache)
    df_trend = run_query_cached(
        queries.daily_trend(year_month, user_id=user_id,
                            channel_id=channel_id,
                            channel_ids=channel_ids,
                            start_day=start_day, end_day=end_day,
                            start_time=start_time, end_time=end_time),
        no_cache=no_cache)

    if df_full.empty:
        wb = xlsxwriter.Workbook(filepath)
        ws = wb.add_worksheet("无数据")
        ws.write(0, 0, "指定时间段内无数据")
        wb.close()
        return filepath

    # Apply four-tier pricing (with flat-tier if enabled)
    df_full = pricing_engine.apply_pricing_summary(
        df_full, flat_tier=flat_tier, flat_tier_since=flat_tier_since)

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

    wb = xlsxwriter.Workbook(filepath, {"constant_memory": False})

    # ── Tab 1: 按用户汇总 ──
    user_agg = df_full.groupby(["user_id", "username"]).agg({
        "call_count": "sum",
        "total_input_tokens": "sum",
        "total_output_tokens": "sum",
        "list_price_usd": "sum",
        "revenue_usd": "sum",
        "cost_usd": "sum",
        "profit_usd": "sum",
    }).reset_index().sort_values("list_price_usd", ascending=False)
    user_agg["margin"] = user_agg["profit_usd"] / user_agg["revenue_usd"].replace(0, np.nan)

    if customer_view:
        u_hdrs = [
            "用户 ID", "用户名", "调用次数",
            "输入 Tokens", "输出 Tokens",
            f"刊例价 ({symbol})", f"应付金额 ({symbol})",
        ]
        u_wids = [10, 16, 12, 14, 14, 16, 16]
        u_fmts = [TOK, None, TOK, TOK, TOK, USD2, USD2]
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
    u_tots = {c: float(user_agg[c].sum()) for c in u_tots_cols}
    u_tot = [
        "合计", "", int(u_tots["call_count"]),
        int(u_tots["total_input_tokens"]), int(u_tots["total_output_tokens"]),
        u_tots["list_price_usd"] * rate, u_tots["revenue_usd"] * rate,
    ]
    if not customer_view:
        u_tots.update({c: float(user_agg[c].sum()) for c in ["cost_usd", "profit_usd"]})
        u_tot_margin = u_tots["profit_usd"] / u_tots["revenue_usd"] if u_tots["revenue_usd"] else 0
        u_tot += [u_tots["cost_usd"] * rate, u_tots["profit_usd"] * rate, u_tot_margin]

    write_sheet(wb, f"API 账单 -- {year_month} (用户汇总){tier_tag}",
                "用户汇总", u_hdrs, u_wids, u_data, u_fmts,
                total_row=u_tot, total_fmts=u_fmts)

    # ── Tab 2: 按模型汇总（含 cache token 拆分）──
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
    model_agg["diff"] = model_agg["billed_usd"] - model_agg["list_price_usd"]
    model_agg["diff_pct"] = model_agg["diff"] / model_agg["list_price_usd"].replace(0, np.nan)
    model_agg["margin"] = model_agg["profit_usd"] / model_agg["revenue_usd"].replace(0, np.nan)

    if has_cache:
        model_agg["cw_5m_total"] = (model_agg["total_cw_5m"].astype(float)
                                    + model_agg["total_cw_remaining"].astype(float))

    price_label = "低档价" if flat_tier else "刊例"
    m_hdrs = ["模型名称", "调用次数"]
    m_wids = [28, 10]
    m_fmts = [None, TOK]

    if has_cache:
        m_hdrs += ["输入 Tokens", "输出 Tokens", "缓存命中",
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
        if has_cache:
            row_data += [
                int(r["total_input_tokens"]), int(r["total_output_tokens"]),
                int(r["total_cache_hit_tokens"]),
                int(r["cw_5m_total"]), int(r["total_cw_1h"]),
            ]
        else:
            row_data += [int(r["total_input_tokens"]), int(r["total_output_tokens"])]
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
        }).reset_index().sort_values("list_price_usd", ascending=False)
        d_hdrs = [
            "用户 ID", "用户名", "模型名称", "调用次数",
            "输入 Tokens", "输出 Tokens",
            f"刊例价 ({symbol})", f"应付金额 ({symbol})",
        ]
        d_wids = [10, 16, 28, 10, 14, 14, 16, 16]
        d_fmts = [TOK, None, None, TOK, TOK, TOK, USD4, USD4]

        d_data = []
        for _, r in df_cv.iterrows():
            d_data.append([
                int(r["user_id"]), r["username"],
                r["model_name"], int(r["call_count"]),
                int(r["total_input_tokens"]), int(r["total_output_tokens"]),
                float(r["list_price_usd"]) * rate,
                float(r["revenue_usd"]) * rate,
            ])
    else:
        # Internal view: keep channel dimension for cost analysis
        df_sorted = df_full.sort_values("list_price_usd", ascending=False)
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
            d_data.append([
                int(r["user_id"]), r["username"], int(r["channel_id"]),
                r["model_name"], int(r["call_count"]),
                int(r["total_input_tokens"]), int(r["total_output_tokens"]),
                lp, float(r["cost_discount"]),
                cost, float(r["revenue_discount"]),
                rev, profit, margin,
            ])

    write_sheet(wb, f"API 账单 -- {year_month} (定价明细){tier_tag}",
                "定价明细", d_hdrs, d_wids, d_data, d_fmts)

    # ── Tab 4: 每日趋势 ──
    if customer_view:
        t_hdrs = ["日期", "调用次数", "总 Tokens", f"刊例价 ({symbol})"]
        t_wids = [14, 12, 14, 14]
        t_fmts = [None, TOK, TOK, USD4]
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
            if not customer_view:
                row_data.append(int(r["total_quota"]))
            row_data.append(float(r["total_usd"]) * rate)
            t_data.append(row_data)
    write_sheet(wb, f"每日费用趋势 -- {year_month}",
                "每日趋势", t_hdrs, t_wids, t_data, t_fmts)

    wb.close()

    if not detail and not upload_s3:
        return filepath

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
                                         customer_view=customer_view)

    if upload_s3:
        result = _upload_results(filepath, detail_path)
        return result

    if detail_path:
        return [filepath, detail_path]
    return filepath


# ---------------------------------------------------------------------------
# S3 upload helper
# ---------------------------------------------------------------------------

def _upload_results(xlsx_path: str, detail_path: str = None) -> dict:
    """Upload generated files to S3 and return paths + presigned URLs."""
    result = {"xlsx": xlsx_path}

    print(f"[upload] 上传汇总账单到 S3...", file=sys.stderr)
    info = upload_and_sign(xlsx_path)
    result["xlsx_url"] = info["url"]
    result["xlsx_s3_key"] = info["s3_key"]

    if detail_path:
        result["detail_csv"] = detail_path
        print(f"[upload] 上传明细数据到 S3...", file=sys.stderr)
        info = upload_and_sign(detail_path)
        result["detail_csv_url"] = info["url"]
        result["detail_csv_s3_key"] = info["s3_key"]

    print(f"[upload] 上传完成", file=sys.stderr)
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
                       customer_view: bool = False) -> str:
    """Export row-level detail as xlsx (customer_view) or zip-compressed CSV.

    customer_view=True:
      - Outputs .xlsx with auto-split sheets (≤500K rows each)
      - Chinese column headers, UTC+8 timestamps
      - Hides cost/profit/channel/discount columns
    customer_view=False:
      - Outputs .csv.zip (internal full-field format)

    start_day / end_day: day-level boundary 'YYYY-MM-DD' (inclusive).
    start_time / end_time: 'YYYY-MM-DD HH:MM' UTC for sub-day precision.
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
                                   start_time=start_time, end_time=end_time)
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
        sy, sm, sd, _sh, _start_ts = queries._parse_datetime(start_time)
        _start_day_str = f"{sy}-{sm}-{sd}"
    if end_time:
        ey, em, ed, _eh, _end_ts = queries._parse_datetime(end_time)
        _end_day_str = f"{ey}-{em}-{ed}"

    print(f"[detail] 提交 {len(sqls)} 个每日查询（并行）...", file=sys.stderr)
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
        print(f"[detail] day {days[idx]}: +{len(df_day):,} 行 "
              f"({days_done}/{len(sqls)} done, "
              f"累计 {total_rows:,}, {elapsed:.0f}s)",
              file=sys.stderr)

    elapsed = time.time() - t0

    if total_rows == 0:
        print("[detail] 无数据", file=sys.stderr)
        all_chunks = [pd.DataFrame()]

    df_all = pd.concat(all_chunks, ignore_index=True) if all_chunks else pd.DataFrame()

    if customer_view:
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
    print(f"[detail] 完成: {total_rows:,} 行, {size_mb:.1f} MB, "
          f"耗时 {elapsed:.1f}s", file=sys.stderr)

    return out_path


def _write_detail_csv_internal(df: pd.DataFrame, year_month: str,
                               output_dir: str, suffix: str = "",
                               ch_suffix: str = "",
                               tier_suffix: str = "", from_suffix: str = "",
                               day_suffix: str = "") -> str:
    """Write internal full-field detail as zip-compressed CSV."""
    import io as _io

    zip_filename = f"bill_{year_month}{suffix}{ch_suffix}{tier_suffix}{from_suffix}{day_suffix}_detail.csv.zip"
    csv_inner_name = zip_filename.replace(".zip", "")
    zip_path = os.path.join(output_dir, zip_filename)

    csv_buf = _io.StringIO()
    if df.empty:
        csv_buf.write("no data\n")
    else:
        df.to_csv(csv_buf, index=False, lineterminator="\n")

    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6) as zf:
            zf.writestr(csv_inner_name, csv_buf.getvalue().encode("utf-8"))
    finally:
        csv_buf.close()

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

    # Convert created_at (unix timestamp) to UTC+8 readable string
    if "created_at" in df.columns:
        df = df.copy()
        df["created_at"] = (
            pd.to_datetime(df["created_at"], unit="s", utc=True)
            .dt.tz_convert("Asia/Shanghai")
            .dt.strftime("%Y-%m-%d %H:%M:%S")
        )

    # Build column mapping — only include columns that exist in df
    col_spec = [(ic, ch, w, nf) for ic, ch, w, nf in _CUSTOMER_DETAIL_COLS
                if ic in df.columns]
    internal_cols = [c[0] for c in col_spec]
    headers = [c[1] for c in col_spec]
    col_widths = [c[2] for c in col_spec]
    num_fmts = [c[3] for c in col_spec]

    df_out = df[internal_cols].copy()
    df_out = df_out.fillna("")

    user_label = f"User{user_id} " if user_id else ""
    title_base = f"{user_label}API 账单 -- {year_month} (调用明细){tier_tag}"

    data_rows = df_out.values.tolist()

    wb = xlsxwriter.Workbook(xlsx_path, {"constant_memory": False})
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

    billed_usd = df["quota"].astype(float) / pricing_engine.QUOTA_TO_USD

    if flat_tier:
        if flat_tier_since_ts is not None and "created_at" in df.columns:
            use_expected = (df["model"].isin(pricing_engine.FLAT_TIER_MODELS) &
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
                          no_cache: bool = False) -> str:
    """Generate daily report Excel with xlsxwriter formatting."""
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"daily_report_{date}.xlsx")

    parts = date.split("-")
    year_month = f"{parts[0]}-{parts[1]}"
    day = parts[2]

    df_models = run_query_cached(queries.model_ranking(year_month), no_cache=no_cache)
    df_users = run_query_cached(queries.monthly_bill_by_user(year_month), no_cache=no_cache)
    df_hourly = run_query_cached(queries.hourly_distribution(year_month, day), no_cache=no_cache)
    df_kpi = run_query_cached(queries.kpi_summary(year_month), no_cache=no_cache)

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

    wb.close()
    return filepath


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
    print(f"[crosscheck] 导入供应商账单 ({len(vendor_files)} 个文件)...", file=sys.stderr)
    vendor_df = cost_import.import_row_level_bill(
        vendor_files, channel_id=channel_id)
    print(f"[crosscheck] 供应商记录: {len(vendor_df):,} 条, "
          f"${vendor_df['vendor_usd'].sum():,.2f}", file=sys.stderr)

    # 2. Detect time range from vendor data
    if "created_at" not in vendor_df.columns:
        raise ValueError("供应商账单缺少 created_at 列，无法确定时间范围")

    ts_min = int(vendor_df["created_at"].min())
    ts_max = int(vendor_df["created_at"].max()) + 1

    from datetime import datetime as _dt, timezone as _tz
    dt_min = _dt.fromtimestamp(ts_min, tz=_tz.utc)
    dt_max = _dt.fromtimestamp(ts_max, tz=_tz.utc)
    print(f"[crosscheck] 时间范围: {dt_min:%Y-%m-%d %H:%M} ~ "
          f"{dt_max:%Y-%m-%d %H:%M} UTC", file=sys.stderr)

    # 3. Query our data from Athena
    print(f"[crosscheck] 查询我方 Athena 数据 (channel_id={channel_id})...",
          file=sys.stderr)
    our_sql = queries.usage_by_created_at_range(
        ts_min, ts_max, channel_id=channel_id)
    our_df = run_query_cached(our_sql, no_cache=no_cache)
    print(f"[crosscheck] 我方记录: {len(our_df):,} 条, "
          f"${our_df['billed_usd'].sum():,.2f}" if not our_df.empty else
          "[crosscheck] 我方记录: 0 条", file=sys.stderr)

    if our_df.empty:
        our_df = pd.DataFrame(columns=["request_id", "model_name", "quota",
                                        "billed_usd", "prompt_tokens",
                                        "completion_tokens"])

    # 4. Row-level crosscheck
    print(f"[crosscheck] 逐条对账中...", file=sys.stderr)
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

    # Print summary
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  逐条对账完成", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  匹配: {stats['matched_records']:,} / "
          f"我方 {stats['total_our_records']:,} / "
          f"供应商 {stats['total_vendor_records']:,}", file=sys.stderr)
    print(f"  仅我方: {stats['only_ours_records']:,} 条 "
          f"(${stats['only_ours_usd']:,.4f})", file=sys.stderr)
    print(f"  仅供应商: {stats['only_vendor_records']:,} 条 "
          f"(${stats['only_vendor_usd']:,.4f})", file=sys.stderr)
    print(f"  金额不一致: {stats['quota_mismatched']:,} 条", file=sys.stderr)
    print(f"  总差额: ${stats['our_total_usd'] - stats['vendor_total_usd']:,.4f}",
          file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    return filepath
