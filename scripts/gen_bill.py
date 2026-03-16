"""
GMICloud 内部账单生成器
- 以系统 billed (quota/500000 = 刊例价) 为基准
- GMI 应付 = 刊例价 × 0.65, 成本 = 刊例价 × 0.41, 利润 = 刊例价 × 0.24
- pricing.json 重算 + MateCloud 账单 作为交叉校验
- pandas 向量化 + xlsxwriter + multiprocessing
"""
import sqlite3, json, csv, os, sys, time
from datetime import datetime
from collections import defaultdict
from multiprocessing import Pool, cpu_count

import pandas as pd
import numpy as np
import xlsxwriter

# ── 常量 ──────────────────────────────────────────────────────────────────────
DB_PATH       = "logs_analysis.db"
QUOTA_PER_USD = 500_000
COST_DISCOUNT    = 0.41   # MateCloud → 我们（刊例价 × 0.41）
REVENUE_DISCOUNT = 0.65   # 我们 → GMICloud（刊例价 × 0.65）

MATECLOUD_BILLS = {
    "2026-01": "reconcile/EZmodel渠道账单/[24-25]MateCloud/Ezmode1月账单-复核后_明细.csv",
}

# ── 定价表 ────────────────────────────────────────────────────────────────────
PRICING = {
    "claude-opus-4-6": [
        {"min_k": 0,   "max_k": 200, "ip": 5,  "op": 25,   "chp": 0.5, "cwp": 6.25, "cwp_1h": 10},
        {"min_k": 200, "max_k": -1,  "ip": 10, "op": 37.5, "chp": 1.0, "cwp": 12.5, "cwp_1h": 20},
    ],
    "claude-opus-4-5-20251101": [
        {"min_k": 0,   "max_k": 200, "ip": 5,  "op": 25,   "chp": 0.5, "cwp": 6.25, "cwp_1h": 10},
        {"min_k": 200, "max_k": -1,  "ip": 10, "op": 37.5, "chp": 1.0, "cwp": 12.5, "cwp_1h": 20},
    ],
    "claude-sonnet-4-6": [
        {"min_k": 0,   "max_k": 200, "ip": 3, "op": 15,   "chp": 0.3, "cwp": 3.75, "cwp_1h": 6},
        {"min_k": 200, "max_k": -1,  "ip": 6, "op": 22.5, "chp": 0.6, "cwp": 7.5,  "cwp_1h": 12},
    ],
    "claude-sonnet-4-5-20250929": [
        {"min_k": 0,   "max_k": 200, "ip": 3, "op": 15,   "chp": 0.3, "cwp": 3.75, "cwp_1h": 6},
        {"min_k": 200, "max_k": -1,  "ip": 6, "op": 22.5, "chp": 0.6, "cwp": 7.5,  "cwp_1h": 12},
    ],
    "claude-sonnet-4-20250514": [
        {"min_k": 0,   "max_k": 200, "ip": 3, "op": 15,   "chp": 0.3, "cwp": 3.75, "cwp_1h": 6},
        {"min_k": 200, "max_k": -1,  "ip": 6, "op": 22.5, "chp": 0.6, "cwp": 7.5,  "cwp_1h": 12},
    ],
    "claude-haiku-4-5-20251001":  {"ip": 1,  "op": 5,  "chp": 0.1, "cwp": 1.25,  "cwp_1h": 1.25},
    "claude-3-7-sonnet-20250219": {"ip": 3,  "op": 15, "chp": 0.3, "cwp": 3.75,  "cwp_1h": 3.75},
    "claude-opus-4-1-20250805":   {"ip": 15, "op": 75, "chp": 1.5, "cwp": 18.75, "cwp_1h": 18.75},
    "claude-opus-4-20250514":     {"ip": 15, "op": 75, "chp": 1.5, "cwp": 18.75, "cwp_1h": 18.75},
}

# 展开分段定价
_TIER_ROWS, _FLAT_ROWS = [], []
for _model, _p in PRICING.items():
    if isinstance(_p, list):
        for _t in _p:
            _TIER_ROWS.append({"model": _model, **_t})
    else:
        _FLAT_ROWS.append({"model": _model, **_p})
TIER_DF = pd.DataFrame(_TIER_ROWS) if _TIER_ROWS else pd.DataFrame()
FLAT_DF = pd.DataFrame(_FLAT_ROWS) if _FLAT_ROWS else pd.DataFrame()


# ── 核心计算 ──────────────────────────────────────────────────────────────────
def parse_other_batch(other_series: pd.Series) -> pd.DataFrame:
    """批量解析 other JSON，返回 DataFrame（orjson 加速）"""
    try:
        import orjson as _json
        _loads = _json.loads
    except ImportError:
        _loads = json.loads

    records = []
    for s in other_series:
        try:
            o = _loads(s) if s else {}
        except Exception:
            o = {}
        ch    = o.get("cache_tokens", 0) or 0
        cw    = o.get("cache_creation_tokens", 0) or 0
        cw_5m = o.get("tiered_cache_creation_tokens_5m") or o.get("cache_creation_tokens_5m", 0) or 0
        cw_1h = o.get("tiered_cache_creation_tokens_1h") or o.get("cache_creation_tokens_1h", 0) or 0
        cw_rem_raw = o.get("tiered_cache_creation_tokens_remaining")
        cw_rem = cw_rem_raw if cw_rem_raw is not None else max(cw - cw_5m - cw_1h, 0)
        is_new = "tiered_cache_store_price" in o
        records.append({
            "ch": ch, "cw": cw,
            "cw_5m": cw_5m, "cw_1h": cw_1h, "cw_rem": cw_rem,
            "is_new": is_new,
            "chp_new":    o.get("tiered_cache_hit_price"),
            "cwp_5m_new": o.get("tiered_cache_store_price_5m") or o.get("tiered_cache_store_price"),
            "cwp_1h_new": o.get("tiered_cache_store_price_1h"),
        })
    return pd.DataFrame(records, index=other_series.index)


def assign_prices(df: pd.DataFrame) -> pd.DataFrame:
    """按模型和 prompt_tokens 分配价格（向量化）"""
    df = df.copy()
    for col in ("ip", "op", "chp", "cwp", "cwp_1h"):
        df[col] = np.nan

    # 固定价
    if not FLAT_DF.empty:
        flat_map = FLAT_DF.set_index("model")
        mask = df["model"].isin(flat_map.index)
        for col in ("ip", "op", "chp", "cwp", "cwp_1h"):
            df.loc[mask, col] = df.loc[mask, "model"].map(flat_map[col])

    # 分段价：先 drop 已有价格列避免 _x/_y 冲突
    if not TIER_DF.empty:
        mask = df["model"].isin(TIER_DF["model"].unique())
        sub = df.loc[mask, [c for c in df.columns
                             if c not in ("ip","op","chp","cwp","cwp_1h")]].copy()
        sub["pt_k"] = sub["prompt_tokens"] // 1000
        sub = sub.reset_index().rename(columns={"index": "_orig_idx"})
        merged = sub.merge(TIER_DF, on="model", how="left")
        in_tier = (merged["pt_k"] >= merged["min_k"]) & \
                  ((merged["max_k"] == -1) | (merged["pt_k"] < merged["max_k"]))
        merged = merged[in_tier].groupby("_orig_idx").first()
        for col in ("ip", "op", "chp", "cwp", "cwp_1h"):
            df.loc[merged.index, col] = merged[col].values

    return df


def compute_costs(df: pd.DataFrame) -> pd.DataFrame:
    """向量化计算所有费用列。以 billed_usd(刊例价) 为基准算折扣价。"""
    is_new  = df["is_new"]
    chp     = np.where(is_new & df["chp_new"].notna(),    df["chp_new"],    df["chp"])
    cwp_5m  = np.where(is_new & df["cwp_5m_new"].notna(), df["cwp_5m_new"], df["cwp"])
    cwp_1h  = np.where(is_new & df["cwp_1h_new"].notna(), df["cwp_1h_new"], df["cwp_1h"])

    net_input   = np.maximum(df["prompt_tokens"] - df["ch"] - df["cw"], 0)
    cw_5m_total = df["cw_rem"] + df["cw_5m"]

    cost_input      = net_input              / 1e6 * df["ip"]
    cost_output     = df["completion_tokens"] / 1e6 * df["op"]
    cost_cache_hit  = df["ch"]               / 1e6 * chp
    cost_cw_5m      = cw_5m_total            / 1e6 * cwp_5m
    cost_cw_1h      = df["cw_1h"]            / 1e6 * cwp_1h
    expected_usd    = cost_input + cost_output + cost_cache_hit + cost_cw_5m + cost_cw_1h

    df = df.copy()
    df["net_input"]      = net_input.astype(np.int64)
    df["cw_5m_total"]    = cw_5m_total.astype(np.int64)
    df["cost_input"]     = cost_input
    df["cost_output"]    = cost_output
    df["cost_cache_hit"] = cost_cache_hit
    df["cost_cw_5m"]     = cost_cw_5m
    df["cost_cw_1h"]     = cost_cw_1h
    df["expected_usd"]   = expected_usd
    df["billed_usd"]     = df["quota"] / QUOTA_PER_USD
    df["revenue"]        = df["billed_usd"] * REVENUE_DISCOUNT
    df["cost"]           = df["billed_usd"] * COST_DISCOUNT
    df["profit"]         = df["revenue"] - df["cost"]
    return df


def load_db(ts_start: int, ts_end: int) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """SELECT id, model_name AS model, quota, prompt_tokens, completion_tokens,
                  other, token_name,
                  datetime(created_at,'unixepoch','+8 hours') AS cst
           FROM logs
           WHERE username='GMICloud' AND type=2
             AND created_at>=? AND created_at<?
             AND model_name LIKE '%claude%'
           ORDER BY created_at""",
        conn, params=(ts_start, ts_end)
    )
    conn.close()
    return df



def load_matecloud(month_label: str) -> pd.DataFrame:
    """加载 MateCloud 账单明细，按模型汇总返回"""
    fpath = MATECLOUD_BILLS.get(month_label)
    if not fpath or not os.path.exists(fpath):
        return pd.DataFrame()
    rows = []
    with open(fpath, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append({
                "model": r.get("模型", ""),
                "mc_amount": float(r.get("额度", 0) or 0),
            })
    if not rows:
        return pd.DataFrame()
    mc = pd.DataFrame(rows)
    return mc.groupby("model").agg(
        mc_count=("mc_amount", "count"),
        mc_total=("mc_amount", "sum"),
    ).reset_index()


# ── xlsxwriter 写入 ───────────────────────────────────────────────────────────
BORDER_PROPS = {"border": 1, "border_color": "#B0C4DE"}

def _fmt(wb, bold=False, bg=None, num_fmt=None, align="left"):
    props = {**BORDER_PROPS, "font_size": 10, "valign": "vcenter", "align": align}
    if bold:    props["bold"] = True
    if bg:      props["bg_color"] = bg
    if num_fmt: props["num_format"] = num_fmt
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

    # 预建格式：(num_fmt, is_alt, is_total)
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

    for ri, row in enumerate(data_rows):
        er = ri + 2
        for ci, (val, nf) in enumerate(zip(row, num_fmts)):
            ws.write(er, ci, val, get_fmt(nf, ri))

    if total_row:
        tr = len(data_rows) + 2
        tfmts = total_fmts or num_fmts
        for ci, (val, nf) in enumerate(zip(total_row, tfmts)):
            ws.write(tr, ci, val, get_fmt(nf, 0, is_total=True))


# ── 主流程 ────────────────────────────────────────────────────────────────────
def make_bill(args):
    month_label, ts_start, ts_end = args
    t0 = time.time()
    print(f"[{month_label}] loading...", flush=True)

    raw = load_db(ts_start, ts_end)
    if raw.empty:
        print(f"[{month_label}] no data, skip")
        return

    print(f"[{month_label}] {len(raw):,} rows, parsing other...", flush=True)
    other_df = parse_other_batch(raw["other"])
    df = pd.concat([raw.drop(columns=["other"]), other_df], axis=1)

    print(f"[{month_label}] pricing + costs...", flush=True)
    df = assign_prices(df)
    df = df.dropna(subset=["ip"])
    df = compute_costs(df)

    # ── 汇总 ──
    grp = df.groupby("model").agg(
        count          = ("id", "count"),
        net_input      = ("net_input", "sum"),
        output_tokens  = ("completion_tokens", "sum"),
        cache_hit      = ("ch", "sum"),
        cw_5m_total    = ("cw_5m_total", "sum"),
        cw_1h          = ("cw_1h", "sum"),
        cost_input     = ("cost_input", "sum"),
        cost_output    = ("cost_output", "sum"),
        cost_cache_hit = ("cost_cache_hit", "sum"),
        cost_cw_5m     = ("cost_cw_5m", "sum"),
        cost_cw_1h     = ("cost_cw_1h", "sum"),
        expected_usd   = ("expected_usd", "sum"),
        billed_usd     = ("billed_usd", "sum"),
        revenue        = ("revenue", "sum"),
        cost           = ("cost", "sum"),
        profit         = ("profit", "sum"),
    ).reset_index().sort_values("billed_usd", ascending=False)

    grp["diff"]     = grp["billed_usd"] - grp["expected_usd"]
    grp["diff_pct"] = grp["diff"] / grp["expected_usd"].replace(0, np.nan)
    grp["margin"]   = grp["profit"] / grp["revenue"].replace(0, np.nan)

    print(f"[{month_label}] writing Excel...", flush=True)
    fname = f"reconcile/GMICloud_bill_{month_label}.xlsx"
    wb = xlsxwriter.Workbook(fname, {"constant_memory": True})

    USD2 = '"$"#,##0.00'
    USD4 = '"$"#,##0.0000'
    USD6 = '"$"#,##0.000000'
    TOK  = "#,##0"
    PCT  = "0.00%"

    # ── Tab1: 按模型汇总 ──
    s_hdrs = [
        "模型名称", "调用次数",
        "输入 Tokens", "输出 Tokens", "缓存命中 Tokens",
        "缓存写入 Tokens\n(5min)", "缓存写入 Tokens\n(1h)",
        "输入费用", "输出费用", "缓存命中费用",
        "缓存写入费用\n(5min)", "缓存写入费用\n(1h)",
        "刊例价合计\n(pricing.json)", "刊例价合计\n(系统 billed)",
        "pricing 差额", "差额 %",
        f"GMI 应付\n(刊例 x{REVENUE_DISCOUNT})",
        f"我方成本\n(刊例 x{COST_DISCOUNT})",
        "利润", "利润率",
    ]
    s_wids = [28, 10, 14, 14, 16, 16, 16,
              14, 14, 16, 18, 18,
              16, 16, 13, 10,
              16, 16, 14, 10]
    s_fmts = [None, TOK, TOK, TOK, TOK, TOK, TOK,
              USD4, USD4, USD4, USD4, USD4,
              USD2, USD2, USD4, PCT,
              USD2, USD2, USD2, PCT]

    s_data = []
    for _, r in grp.iterrows():
        s_data.append([
            r["model"], int(r["count"]),
            int(r["net_input"]), int(r["output_tokens"]),
            int(r["cache_hit"]), int(r["cw_5m_total"]), int(r["cw_1h"]),
            float(r["cost_input"]), float(r["cost_output"]), float(r["cost_cache_hit"]),
            float(r["cost_cw_5m"]), float(r["cost_cw_1h"]),
            float(r["expected_usd"]), float(r["billed_usd"]),
            float(r["diff"]), float(r["diff_pct"]) if pd.notna(r["diff_pct"]) else 0,
            float(r["revenue"]), float(r["cost"]),
            float(r["profit"]), float(r["margin"]) if pd.notna(r["margin"]) else 0,
        ])

    sum_cols = ["count", "net_input", "output_tokens", "cache_hit", "cw_5m_total", "cw_1h",
                "cost_input", "cost_output", "cost_cache_hit", "cost_cw_5m", "cost_cw_1h",
                "expected_usd", "billed_usd", "diff", "revenue", "cost", "profit"]
    tots = {c: float(grp[c].sum()) for c in sum_cols}
    tot_margin   = tots["profit"] / tots["revenue"] if tots["revenue"] else 0
    tot_diff_pct = tots["diff"] / tots["expected_usd"] if tots["expected_usd"] else 0
    s_tot = [
        "合计", int(tots["count"]),
        int(tots["net_input"]), int(tots["output_tokens"]),
        int(tots["cache_hit"]), int(tots["cw_5m_total"]), int(tots["cw_1h"]),
        tots["cost_input"], tots["cost_output"],
        tots["cost_cache_hit"], tots["cost_cw_5m"], tots["cost_cw_1h"],
        tots["expected_usd"], tots["billed_usd"],
        tots["diff"], tot_diff_pct,
        tots["revenue"], tots["cost"],
        tots["profit"], tot_margin,
    ]

    write_sheet(wb, f"GMICloud API 账单 -- {month_label} (Claude 模型汇总)",
                "按模型汇总", s_hdrs, s_wids, s_data, s_fmts,
                total_row=s_tot, total_fmts=s_fmts)

    # ── Tab2: 调用明细 ──
    d_hdrs = [
        "记录 ID", "时间 (UTC+8)", "模型名称", "Token 名称",
        "输入 Tokens", "输出 Tokens", "缓存命中 Tokens",
        "缓存写入 Tokens\n(5min)", "缓存写入 Tokens\n(1h)",
        "输入费用", "输出费用", "缓存命中费用",
        "缓存写入费用\n(5min)", "缓存写入费用\n(1h)",
        "刊例价\n(pricing.json)", "刊例价\n(系统 billed)",
        f"GMI 应付\n(x{REVENUE_DISCOUNT})",
        f"成本\n(x{COST_DISCOUNT})",
        "利润",
    ]
    d_wids = [12, 20, 28, 18, 14, 14, 16, 16, 16,
              15, 15, 18, 20, 20,
              15, 15, 14, 14, 13]
    d_fmts = [TOK, None, None, None, TOK, TOK, TOK, TOK, TOK,
              USD6, USD6, USD6, USD6, USD6,
              USD6, USD6, USD6, USD6, USD6]

    d_data = []
    for _, r in df.iterrows():
        d_data.append([
            int(r["id"]), str(r["cst"]), str(r["model"]), str(r["token_name"] or ""),
            int(r["net_input"]), int(r["completion_tokens"]),
            int(r["ch"]), int(r["cw_5m_total"]), int(r["cw_1h"]),
            float(r["cost_input"]), float(r["cost_output"]), float(r["cost_cache_hit"]),
            float(r["cost_cw_5m"]), float(r["cost_cw_1h"]),
            float(r["expected_usd"]), float(r["billed_usd"]),
            float(r["revenue"]), float(r["cost"]),
            float(r["profit"]),
        ])

    write_sheet(wb, f"GMICloud API 账单 -- {month_label} (调用明细)",
                "明细", d_hdrs, d_wids, d_data, d_fmts)

    # ── Tab3: 三方对比（有 MateCloud 账单时） ──
    mc = load_matecloud(month_label)
    mc_info = ""
    if not mc.empty:
        cmp = grp[["model", "count", "expected_usd", "billed_usd", "revenue", "cost", "profit"]].copy()
        cmp = cmp.merge(mc, on="model", how="outer").fillna(0)
        cmp["mc_cost_41"] = cmp["mc_total"] * COST_DISCOUNT
        cmp["diff_billed_mc"] = cmp["billed_usd"] - cmp["mc_total"]
        cmp["diff_pct_mc"] = cmp["diff_billed_mc"] / cmp["mc_total"].replace(0, np.nan)
        cmp["profit_vs_mc"] = cmp["revenue"] - cmp["mc_cost_41"]
        cmp["margin_vs_mc"] = cmp["profit_vs_mc"] / cmp["revenue"].replace(0, np.nan)
        cmp = cmp.sort_values("billed_usd", ascending=False)

        c_hdrs = [
            "模型名称",
            "我方记录数", "MC 记录数", "记录差",
            "刊例价\n(pricing.json)", "刊例价\n(系统 billed)", "刊例价\n(MateCloud)",
            "系统-MC 差额", "差额 %",
            f"GMI 应付\n(x{REVENUE_DISCOUNT})",
            f"MC 成本\n(MC x{COST_DISCOUNT})",
            "利润\n(vs MC)", "利润率\n(vs MC)",
        ]
        c_wids = [28, 12, 12, 10, 16, 16, 16, 14, 10, 16, 16, 14, 10]
        c_fmts = [None, TOK, TOK, TOK, USD2, USD2, USD2, USD4, PCT, USD2, USD2, USD2, PCT]

        c_data = []
        for _, r in cmp.iterrows():
            c_data.append([
                r["model"],
                int(r["count"]), int(r["mc_count"]), int(r["count"] - r["mc_count"]),
                float(r["expected_usd"]), float(r["billed_usd"]), float(r["mc_total"]),
                float(r["diff_billed_mc"]),
                float(r["diff_pct_mc"]) if pd.notna(r["diff_pct_mc"]) else 0,
                float(r["revenue"]),
                float(r["mc_cost_41"]),
                float(r["profit_vs_mc"]),
                float(r["margin_vs_mc"]) if pd.notna(r["margin_vs_mc"]) else 0,
            ])

        ct_cols = ["count", "mc_count", "expected_usd", "billed_usd", "mc_total",
                   "diff_billed_mc", "revenue", "mc_cost_41", "profit_vs_mc"]
        ct = {c: float(cmp[c].sum()) for c in ct_cols}
        ct_diff_pct = ct["diff_billed_mc"] / ct["mc_total"] if ct["mc_total"] else 0
        ct_margin = ct["profit_vs_mc"] / ct["revenue"] if ct["revenue"] else 0
        c_tot = [
            "合计",
            int(ct["count"]), int(ct["mc_count"]), int(ct["count"] - ct["mc_count"]),
            ct["expected_usd"], ct["billed_usd"], ct["mc_total"],
            ct["diff_billed_mc"], ct_diff_pct,
            ct["revenue"],
            ct["mc_cost_41"],
            ct["profit_vs_mc"], ct_margin,
        ]

        write_sheet(wb, f"三方对比 -- {month_label} (系统 vs pricing.json vs MateCloud)",
                    "三方对比", c_hdrs, c_wids, c_data, c_fmts,
                    total_row=c_tot, total_fmts=c_fmts)

        mc_total = ct["mc_total"]
        mc_cost_41 = ct["mc_cost_41"]
        profit_mc = ct["profit_vs_mc"]
        mc_info = (f"  MC total=${mc_total:,.2f}  "
                   f"MC cost(x0.41)=${mc_cost_41:,.2f}  "
                   f"profit(vs MC)=${profit_mc:,.2f}  "
                   f"margin={profit_mc/tots['revenue']*100:.1f}%")

    wb.close()
    elapsed = time.time() - t0
    print(f"[{month_label}] OK {fname}  {len(df):,} rows / {len(grp)} models  {elapsed:.1f}s",
          flush=True)
    print(f"  billed(list)=${tots['billed_usd']:,.2f}  "
          f"GMI pays=${tots['revenue']:,.2f}  "
          f"cost=${tots['cost']:,.2f}  "
          f"profit=${tots['profit']:,.2f}  "
          f"margin={tots['profit']/tots['revenue']*100:.1f}%",
          flush=True)
    if mc_info:
        print(mc_info, flush=True)


if __name__ == "__main__":
    tasks = [
        ("2026-01", int(datetime(2026, 1, 1).timestamp()), int(datetime(2026, 2, 1).timestamp())),
        ("2026-02", int(datetime(2026, 2, 1).timestamp()), int(datetime(2026, 3, 1).timestamp())),
    ]
    t0 = time.time()
    with Pool(min(2, cpu_count())) as pool:
        pool.map(make_bill, tasks)
    print(f"全部完成，总耗时 {time.time()-t0:.1f}s")
