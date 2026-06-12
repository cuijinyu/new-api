#!/usr/bin/env python3
"""
从本地 DB 备份（.sql.gz）提取 logs 表数据，按 Athena 出账单格式生成刊例价 Excel。

支持降档（flat-tier）模式：分段计费模型在指定日期后强制使用低档价。

用法:
    # 纯刊例价（quota / 500000）
    python export_db_bill.py --db data/new-api_2026032513132199gwf.sql.gz \
        --channel-id 38 -o output/

    # 降档模式：3月12日起降档
    python export_db_bill.py --db data/new-api_2026032513132199gwf.sql.gz \
        --channel-id 38 --flat-tier-since 2026-03-12 -o output/
"""

import argparse
import gzip
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import xlsxwriter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pricing_engine
from pricing_engine import QUOTA_TO_USD

BORDER_PROPS = {"border": 1, "border_color": "#B0C4DE"}
USD2 = '"$"#,##0.00'
USD4 = '"$"#,##0.0000'
USD6 = '"$"#,##0.000000'
TOK = "#,##0"
PCT = "0.00%"


def _fmt(wb, bold=False, bg=None, num_fmt=None, align="left"):
    props = {**BORDER_PROPS, "font_size": 10, "valign": "vcenter", "align": align}
    if bold:
        props["bold"] = True
    if bg:
        props["bg_color"] = bg
    if num_fmt:
        props["num_format"] = num_fmt
    return wb.add_format(props)


def write_sheet(wb, title, sheet_name, headers, col_widths, data_rows, num_fmts,
                total_row=None, total_fmts=None):
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


def extract_logs_from_sql(sql_gz_path: str, channel_id: int) -> pd.DataFrame:
    """Stream-parse the SQL dump to extract logs rows for the given channel_id."""
    print(f"  Parsing SQL dump: {sql_gz_path} (channel_id={channel_id}) ...")

    in_logs_section = False
    rows = []
    total_lines = 0

    opener = gzip.open if sql_gz_path.endswith('.gz') else open
    with opener(sql_gz_path, 'rt', encoding='utf-8', errors='replace') as f:
        for line in f:
            total_lines += 1
            if total_lines % 500000 == 0:
                print(f"    processed {total_lines:,} lines, extracted {len(rows):,} ch{channel_id} records ...")

            if line.startswith("INSERT INTO `logs`"):
                in_logs_section = True

            if not in_logs_section:
                if line.startswith("UNLOCK TABLES;") and len(rows) > 0:
                    break
                continue

            if line.startswith("UNLOCK TABLES;"):
                in_logs_section = False
                break

            if not line.startswith("INSERT INTO `logs`") and not line.startswith("("):
                if line.strip() == "" or line.startswith("--") or line.startswith("/*!"):
                    continue

            ch_str = f",{channel_id},"
            if ch_str not in line:
                continue

            _extract_tuples(line, channel_id, rows)

    print(f"  Done: {total_lines:,} lines, {len(rows):,} ch{channel_id} records")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=[
        "id", "user_id", "created_at", "type", "content", "username",
        "token_name", "model_name", "quota", "prompt_tokens",
        "completion_tokens", "use_time", "is_stream", "channel_id",
        "token_id", "group", "ip", "other", "request_id",
    ])

    for col in ["id", "user_id", "created_at", "type", "quota", "prompt_tokens",
                "completion_tokens", "use_time", "channel_id", "token_id"]:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    df["is_stream"] = df["is_stream"].astype(bool)

    # Billing-impacting rows. Task/video flows may write a consume precharge
    # followed by a refund/settlement adjustment; both must be included so
    # SUM(quota) reflects the final charged amount.
    df = df[df["type"].isin([2, 6])].copy()

    return df


def _extract_tuples(line: str, channel_id: int, rows: list):
    """Parse MySQL INSERT VALUES(...),(...) syntax and filter by channel_id."""
    idx = line.find("VALUES ")
    if idx >= 0:
        data_part = line[idx + 7:]
    else:
        data_part = line

    i = 0
    n = len(data_part)
    while i < n:
        if data_part[i] != '(':
            i += 1
            continue
        i += 1
        fields = []
        current = []
        in_str = False
        escape = False

        while i < n:
            ch = data_part[i]
            if escape:
                current.append(ch)
                escape = False
                i += 1
                continue
            if ch == '\\':
                escape = True
                current.append(ch)
                i += 1
                continue
            if ch == "'" and not in_str:
                in_str = True
                i += 1
                continue
            if ch == "'" and in_str:
                if i + 1 < n and data_part[i + 1] == "'":
                    current.append("'")
                    i += 2
                    continue
                in_str = False
                i += 1
                continue
            if in_str:
                current.append(ch)
                i += 1
                continue
            if ch == ',':
                fields.append(''.join(current).strip())
                current = []
                i += 1
                continue
            if ch == ')':
                fields.append(''.join(current).strip())
                i += 1
                break
            current.append(ch)
            i += 1

        if len(fields) >= 14:
            try:
                ch_id = int(fields[13])
            except (ValueError, IndexError):
                continue
            if ch_id == channel_id:
                cleaned = []
                for f in fields:
                    f = f.replace('\\n', '\n').replace('\\r', '\r').replace("\\'", "'").replace('\\"', '"').replace('\\\\', '\\')
                    if f == 'NULL':
                        f = ''
                    cleaned.append(f)
                rows.append(cleaned)


def compute_list_price_with_recalc(df: pd.DataFrame,
                                   flat_tier: bool = False,
                                   flat_tier_since: str = None) -> pd.DataFrame:
    """Compute list_price_usd per row using pricing_engine.recalc_from_raw.

    For tiered models (opus/sonnet), this does per-row pricing based on
    prompt_tokens and cache token breakdown from the `other` JSON field.
    For flat models (haiku etc.), it uses the fixed pricing table.
    Models not in the pricing table fall back to quota / 500000.

    flat_tier_since: 'YYYY-MM-DD' -- before this date, normal tiered pricing;
    from this date on, force lowest-tier prices for tiered models.
    """
    print(f"  Recalculating prices (flat_tier={flat_tier}, flat_tier_since={flat_tier_since}) ...")

    df = df.copy()

    # Ensure model_name column exists (recalc_from_raw expects it)
    if "model_name" not in df.columns:
        return df

    # recalc_from_raw needs: model_name, prompt_tokens, completion_tokens,
    #                        quota, other, created_at, channel_id, user_id
    required = ["model_name", "prompt_tokens", "completion_tokens",
                "quota", "other", "created_at", "channel_id", "user_id"]
    for c in required:
        if c not in df.columns:
            print(f"    WARNING: missing column {c}, falling back to quota-based pricing")
            df["list_price_usd"] = df["quota"].astype(float) / QUOTA_TO_USD
            return df

    # Use pricing_engine.recalc_from_raw for per-row recalculation
    df_recalc = pricing_engine.recalc_from_raw(
        df, flat_tier=flat_tier, flat_tier_since=flat_tier_since)

    # recalc_usd is the "chosen" price base:
    #   - For flat_tier_since: before cutoff -> billed_usd (quota-based),
    #                          after cutoff on tiered models -> expected_usd (low-tier recalc)
    #   - For flat_tier (all): expected_usd for tiered models
    #   - For non-tiered models: billed_usd
    # For rows where pricing table doesn't match, has_pricing=False, use billed_usd
    df_recalc["list_price_usd"] = np.where(
        df_recalc["has_pricing"],
        df_recalc["recalc_usd"],
        df_recalc["billed_usd"],
    )

    return df_recalc


def generate_list_price_bill(df: pd.DataFrame, channel_id: int,
                             output_dir: str, channel_name: str = "AIDerby",
                             flat_tier: bool = False,
                             flat_tier_since: str = None,
                             supplier: bool = False):
    """Generate list-price bill Excel from DB logs DataFrame."""
    os.makedirs(output_dir, exist_ok=True)

    if df.empty:
        print("  (no data)")
        return

    ts_min = df["created_at"].min()
    ts_max = df["created_at"].max()
    dt_min = datetime.fromtimestamp(ts_min, tz=timezone.utc)
    dt_max = datetime.fromtimestamp(ts_max, tz=timezone.utc)
    month_label = dt_min.strftime("%Y-%m")
    date_range = f"{dt_min.strftime('%Y-%m-%d')} ~ {dt_max.strftime('%Y-%m-%d')}"

    print(f"  Date range: {date_range}")
    print(f"  Records: {len(df):,}")

    # Compute list price with recalculation (handles tiered + flat-tier)
    df = compute_list_price_with_recalc(df, flat_tier=flat_tier,
                                        flat_tier_since=flat_tier_since)

    # Add date column for daily aggregation
    df["date"] = pd.to_datetime(df["created_at"], unit="s", utc=True).dt.strftime("%Y-%m-%d")

    tier_tag = ""
    tier_suffix = ""
    if flat_tier_since:
        tier_tag = f" (flat-tier since {flat_tier_since})"
        tier_suffix = f"_flattier_since_{flat_tier_since.replace('-', '')}"
    elif flat_tier:
        tier_tag = " (flat-tier)"
        tier_suffix = "_flattier"

    # Show recalc vs billed comparison for tiered models
    if "has_pricing" in df.columns:
        tiered = df[df["has_pricing"] == True]
        if not tiered.empty:
            billed_sum = tiered["billed_usd"].sum()
            recalc_sum = tiered["list_price_usd"].sum()
            diff = billed_sum - recalc_sum
            print(f"  Tiered model recalc: billed=${billed_sum:,.2f} -> recalc=${recalc_sum:,.2f} (diff=${diff:,.2f})")

    # ── Aggregations ──

    user_agg = df.groupby(["user_id", "username"]).agg({
        "request_id": "count",
        "prompt_tokens": "sum",
        "completion_tokens": "sum",
        "quota": "sum",
        "list_price_usd": "sum",
    }).reset_index().rename(columns={"request_id": "call_count"})
    user_agg["billed_usd"] = user_agg["quota"].astype(float) / QUOTA_TO_USD
    user_agg = user_agg.sort_values("list_price_usd", ascending=False)

    model_agg = df.groupby("model_name").agg({
        "request_id": "count",
        "prompt_tokens": "sum",
        "completion_tokens": "sum",
        "quota": "sum",
        "list_price_usd": "sum",
    }).reset_index().rename(columns={"request_id": "call_count"})
    model_agg["billed_usd"] = model_agg["quota"].astype(float) / QUOTA_TO_USD
    model_agg["diff"] = model_agg["billed_usd"] - model_agg["list_price_usd"]
    model_agg = model_agg.sort_values("list_price_usd", ascending=False)

    detail_agg = df.groupby(["user_id", "username", "model_name"]).agg({
        "request_id": "count",
        "prompt_tokens": "sum",
        "completion_tokens": "sum",
        "quota": "sum",
        "list_price_usd": "sum",
    }).reset_index().rename(columns={"request_id": "call_count"})
    detail_agg["billed_usd"] = detail_agg["quota"].astype(float) / QUOTA_TO_USD
    detail_agg = detail_agg.sort_values("list_price_usd", ascending=False)

    daily_agg = df.groupby("date").agg({
        "request_id": "count",
        "prompt_tokens": "sum",
        "completion_tokens": "sum",
        "quota": "sum",
        "list_price_usd": "sum",
    }).reset_index().rename(columns={"request_id": "call_count"})
    daily_agg = daily_agg.sort_values("date")

    daily_model_agg = df.groupby(["date", "model_name"]).agg({
        "request_id": "count",
        "prompt_tokens": "sum",
        "completion_tokens": "sum",
        "quota": "sum",
        "list_price_usd": "sum",
    }).reset_index().rename(columns={"request_id": "call_count"})
    daily_model_agg = daily_model_agg.sort_values(["date", "list_price_usd"],
                                                   ascending=[True, False])

    supplier_suffix = "_supplier" if supplier else ""
    filename = f"bill_{month_label}_ch{channel_id}_{channel_name}{tier_suffix}{supplier_suffix}.xlsx"
    filepath = os.path.join(output_dir, filename)

    wb = xlsxwriter.Workbook(filepath, {"constant_memory": False})
    title_suffix = f"({channel_name} ch{channel_id}, {date_range}){tier_tag}"

    # ── Tab 1: User summary (skip in supplier mode) ──
    if not supplier:
        u_hdrs = ["User ID", "Username", "Calls", "Input Tokens", "Output Tokens",
                  "List Price ($)", "Billed ($)", "Diff ($)"]
        u_wids = [10, 20, 12, 16, 16, 18, 18, 14]
        u_fmts = [TOK, None, TOK, TOK, TOK, USD2, USD2, USD4]

        u_data = []
        for _, r in user_agg.iterrows():
            u_data.append([
                int(r["user_id"]), r["username"], int(r["call_count"]),
                int(r["prompt_tokens"]), int(r["completion_tokens"]),
                float(r["list_price_usd"]), float(r["billed_usd"]),
                float(r["billed_usd"] - r["list_price_usd"]),
            ])
        u_tot = [
            "Total", "", int(user_agg["call_count"].sum()),
            int(user_agg["prompt_tokens"].sum()), int(user_agg["completion_tokens"].sum()),
            float(user_agg["list_price_usd"].sum()), float(user_agg["billed_usd"].sum()),
            float(user_agg["billed_usd"].sum() - user_agg["list_price_usd"].sum()),
        ]
        write_sheet(wb, f"List Price Bill -- User Summary {title_suffix}",
                    "User Summary", u_hdrs, u_wids, u_data, u_fmts,
                    total_row=u_tot, total_fmts=u_fmts)

    # ── Tab 2: Model summary ──
    m_hdrs = ["Model", "Calls", "Input Tokens", "Output Tokens",
              "List Price ($)", "Billed ($)", "Diff ($)"]
    m_wids = [32, 12, 16, 16, 18, 18, 14]
    m_fmts = [None, TOK, TOK, TOK, USD2, USD2, USD4]

    m_data = []
    for _, r in model_agg.iterrows():
        m_data.append([
            r["model_name"], int(r["call_count"]),
            int(r["prompt_tokens"]), int(r["completion_tokens"]),
            float(r["list_price_usd"]), float(r["billed_usd"]),
            float(r["diff"]),
        ])
    m_tot = [
        "Total", int(model_agg["call_count"].sum()),
        int(model_agg["prompt_tokens"].sum()), int(model_agg["completion_tokens"].sum()),
        float(model_agg["list_price_usd"].sum()), float(model_agg["billed_usd"].sum()),
        float(model_agg["diff"].sum()),
    ]
    write_sheet(wb, f"List Price Bill -- Model Summary {title_suffix}",
                "Model Summary", m_hdrs, m_wids, m_data, m_fmts,
                total_row=m_tot, total_fmts=m_fmts)

    # ── Tab 3: User x Model detail (skip in supplier mode) ──
    if not supplier:
        d_hdrs = ["User ID", "Username", "Model", "Calls",
                  "Input Tokens", "Output Tokens",
                  "List Price ($)", "Billed ($)", "Diff ($)"]
        d_wids = [10, 20, 32, 12, 16, 16, 18, 18, 14]
        d_fmts = [TOK, None, None, TOK, TOK, TOK, USD4, USD4, USD4]

        d_data = []
        for _, r in detail_agg.iterrows():
            d_data.append([
                int(r["user_id"]), r["username"], r["model_name"],
                int(r["call_count"]),
                int(r["prompt_tokens"]), int(r["completion_tokens"]),
                float(r["list_price_usd"]), float(r["billed_usd"]),
                float(r["billed_usd"] - r["list_price_usd"]),
            ])
        write_sheet(wb, f"List Price Bill -- Detail {title_suffix}",
                    "Detail", d_hdrs, d_wids, d_data, d_fmts)

    # ── Tab 4: Daily trend ──
    t_hdrs = ["Date", "Calls", "Input Tokens", "Output Tokens",
              "Quota", "List Price ($)"]
    t_wids = [14, 12, 16, 16, 16, 18]
    t_fmts = [None, TOK, TOK, TOK, TOK, USD4]

    t_data = []
    for _, r in daily_agg.iterrows():
        t_data.append([
            r["date"], int(r["call_count"]),
            int(r["prompt_tokens"]), int(r["completion_tokens"]),
            int(r["quota"]), float(r["list_price_usd"]),
        ])
    write_sheet(wb, f"Daily Trend {title_suffix}",
                "Daily Trend", t_hdrs, t_wids, t_data, t_fmts)

    # ── Tab 5: Daily model detail ──
    dm_hdrs = ["Date", "Model", "Calls",
               "Input Tokens", "Output Tokens", "List Price ($)"]
    dm_wids = [14, 32, 12, 16, 16, 18]
    dm_fmts = [None, None, TOK, TOK, TOK, USD4]

    dm_data = []
    for _, r in daily_model_agg.iterrows():
        dm_data.append([
            r["date"], r["model_name"], int(r["call_count"]),
            int(r["prompt_tokens"]), int(r["completion_tokens"]),
            float(r["list_price_usd"]),
        ])
    write_sheet(wb, f"Daily Model Detail {title_suffix}",
                "Daily Model Detail", dm_hdrs, dm_wids, dm_data, dm_fmts)

    wb.close()

    total_usd = df["list_price_usd"].sum()
    billed_usd = df["quota"].astype(float).sum() / QUOTA_TO_USD
    print(f"\n  [OK] Bill generated: {filepath}")
    print(f"    List price total:  ${total_usd:,.2f}")
    print(f"    Billed total:      ${billed_usd:,.2f}")
    print(f"    Diff (billed-list): ${billed_usd - total_usd:,.2f}")
    print(f"    Users:  {len(user_agg)}")
    print(f"    Models: {len(model_agg)}")
    print(f"    Calls:  {len(df):,}")

    return filepath, df


def export_detail_csv(df: pd.DataFrame, channel_id: int, output_dir: str,
                      channel_name: str = "AIDerby",
                      flat_tier_since: str = None,
                      flat_tier: bool = False,
                      supplier: bool = False):
    """Export per-request detail as compressed CSV (zip) alongside the summary bill."""
    import zipfile
    import io as _io

    os.makedirs(output_dir, exist_ok=True)

    ts_min = df["created_at"].min()
    dt_min = datetime.fromtimestamp(ts_min, tz=timezone.utc)
    month_label = dt_min.strftime("%Y-%m")

    tier_suffix = ""
    if flat_tier_since:
        tier_suffix = f"_flattier_since_{flat_tier_since.replace('-', '')}"
    elif flat_tier:
        tier_suffix = "_flattier"

    supplier_suffix = "_supplier" if supplier else ""
    base = f"bill_{month_label}_ch{channel_id}_{channel_name}{tier_suffix}{supplier_suffix}_detail"

    df_out = df.copy()

    # Convert created_at to readable UTC+8
    if "created_at" in df_out.columns:
        df_out["time_utc8"] = (
            pd.to_datetime(df_out["created_at"], unit="s", utc=True)
            .dt.tz_convert("Asia/Shanghai")
            .dt.strftime("%Y-%m-%d %H:%M:%S")
        )

    # Parse cache tokens from `other` JSON if recalc columns exist
    has_cache = "ch" in df_out.columns  # recalc_from_raw adds 'ch' for cache_hit

    SENSITIVE_COLS = {"request_id", "user_id", "username", "token_name", "ip", "token_id"}

    # Select and order output columns
    if supplier:
        detail_cols = [
            ("time_utc8",           "Time (UTC+8)"),
            ("channel_id",          "Channel ID"),
            ("model_name",          "Model"),
            ("prompt_tokens",       "Input Tokens"),
            ("completion_tokens",   "Output Tokens"),
        ]
    else:
        detail_cols = [
            ("request_id",          "Request ID"),
            ("time_utc8",           "Time (UTC+8)"),
            ("user_id",             "User ID"),
            ("username",            "Username"),
            ("channel_id",          "Channel ID"),
            ("model_name",          "Model"),
            ("token_name",          "Token Name"),
            ("prompt_tokens",       "Input Tokens"),
            ("completion_tokens",   "Output Tokens"),
        ]

    if has_cache:
        detail_cols += [
            ("ch",              "Cache Hit Tokens"),
            ("cw",              "Cache Write Tokens"),
            ("cw_5m",           "Cache Write (5min)"),
            ("cw_1h",           "Cache Write (1h)"),
            ("cw_rem",          "Cache Write (remaining)"),
        ]

    detail_cols += [
        ("quota",               "Quota"),
        ("billed_usd",          "Billed USD"),
        ("expected_usd",        "Expected USD"),
        ("list_price_usd",      "List Price USD"),
        ("use_time",            "Use Time (s)"),
        ("is_stream",           "Stream"),
    ]

    available = [(col, hdr) for col, hdr in detail_cols if col in df_out.columns]
    cols = [c for c, _ in available]
    headers = [h for _, h in available]

    df_export = df_out[cols].copy()
    df_export.columns = headers
    df_export = df_export.sort_values("Time (UTC+8)" if "Time (UTC+8)" in df_export.columns else "Request ID")

    # Write as zip-compressed CSV
    zip_path = os.path.join(output_dir, base + ".csv.zip")
    csv_inner_name = base + ".csv"

    csv_buf = _io.StringIO()
    df_export.to_csv(csv_buf, index=False, lineterminator="\n")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zf:
        zf.writestr(csv_inner_name, csv_buf.getvalue().encode("utf-8-sig"))
    csv_buf.close()

    size_mb = os.path.getsize(zip_path) / 1024 / 1024
    print(f"  [OK] Detail exported: {zip_path}")
    print(f"    Rows: {len(df_export):,}")
    print(f"    Size: {size_mb:.1f} MB")

    return zip_path


def main():
    parser = argparse.ArgumentParser(description="Export channel list-price bill from DB backup")
    parser.add_argument("--db", required=True, help="SQL backup path (.sql.gz or .sql)")
    parser.add_argument("--channel-id", type=int, required=True, help="Channel ID")
    parser.add_argument("--channel-name", default=None, help="Channel name (for filename)")
    parser.add_argument("--flat-tier", action="store_true",
                        help="Force lowest-tier prices for tiered models (all records)")
    parser.add_argument("--flat-tier-since", type=str,
                        help="Flat-tier start date YYYY-MM-DD (before: normal tiered, after: low-tier)")
    parser.add_argument("--detail", action="store_true",
                        help="Also export per-request detail as CSV.zip")
    parser.add_argument("--supplier", action="store_true",
                        help="Supplier reconciliation mode: strip sensitive columns "
                             "(user_id, username, token_name, request_id, ip) from "
                             "detail CSV and remove User Summary / Detail tabs from Excel")
    parser.add_argument("-o", "--output", default="output/", help="Output directory")
    args = parser.parse_args()

    channel_name = args.channel_name or f"ch{args.channel_id}"
    flat_tier = args.flat_tier or bool(args.flat_tier_since)

    df = extract_logs_from_sql(args.db, args.channel_id)
    if df.empty:
        print(f"  Channel {args.channel_id}: no data")
        return

    result = generate_list_price_bill(df, args.channel_id, args.output,
                                      channel_name=channel_name,
                                      flat_tier=flat_tier,
                                      flat_tier_since=args.flat_tier_since,
                                      supplier=args.supplier)

    if args.detail and result:
        _, df_priced = result
        export_detail_csv(df_priced, args.channel_id, args.output,
                          channel_name=channel_name,
                          flat_tier=flat_tier,
                          flat_tier_since=args.flat_tier_since,
                          supplier=args.supplier)


if __name__ == "__main__":
    main()
