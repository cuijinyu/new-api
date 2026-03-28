"""
内部账单生成器（支持多客户）
- 以系统 billed (quota/500000 = 刊例价) 为基准
- 应付 = 刊例价 × revenue_discount, 成本 = 刊例价 × cost_discount
- pricing.json 重算 + MateCloud 账单 作为交叉校验
- pandas 向量化 + xlsxwriter + multiprocessing

用法示例:
  python gen_bill.py                                          # GMICloud 默认账单
  python gen_bill.py --username 神州数码 --revenue-discount 0.47 --month 2026-03
  python gen_bill.py --user-id 89 --month 2026-03
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

# 默认折扣（GMICloud）
DEFAULT_COST_DISCOUNT    = 0.41   # MateCloud → 我们（刊例价 × 0.41）
DEFAULT_REVENUE_DISCOUNT = 0.65   # 我们 → 客户（刊例价 × 0.65）

# 兼容旧代码的全局引用（make_bill 内部使用局部变量覆盖）
COST_DISCOUNT    = DEFAULT_COST_DISCOUNT
REVENUE_DISCOUNT = DEFAULT_REVENUE_DISCOUNT

MATECLOUD_BILLS = {
    "2026-01": "reconcile/EZmodel渠道账单/[24-25]MateCloud/Ezmode1月账单-复核后_明细.csv",
    "2026-02": "reconcile/EZmodel渠道账单/[24-25]MateCloud/Ezmodel2月账单_明细.csv",
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


# flat_tier 降档只作用于这两个模型，其他分段模型仍按实际 prompt_tokens 匹配
FLAT_TIER_MODELS = {"claude-opus-4-6", "claude-sonnet-4-6"}


def assign_prices(df: pd.DataFrame, flat_tier: bool = False,
                   flat_tier_since_ts: int = None) -> pd.DataFrame:
    """
    按模型和 prompt_tokens 分配价格（向量化）。

    flat_tier=True: 仅对 FLAT_TIER_MODELS（opus-4-6 / sonnet-4-6）剔除分段计费，
                    一律使用 min_k=0 低档价；其他分段模型仍按实际 prompt_tokens 匹配。
    flat_tier_since_ts: 仅对 created_at >= 此时间戳的行启用降档（需要 df 含 created_at 列）。
                        为 None 时等同于全量降档。
    """
    df = df.copy()
    for col in ("ip", "op", "chp", "cwp", "cwp_1h"):
        df[col] = np.nan

    # 固定价模型
    if not FLAT_DF.empty:
        flat_map = FLAT_DF.set_index("model")
        mask = df["model"].isin(flat_map.index)
        for col in ("ip", "op", "chp", "cwp", "cwp_1h"):
            df.loc[mask, col] = df.loc[mask, "model"].map(flat_map[col])

    # 分段价模型
    if not TIER_DF.empty:
        tier_models = TIER_DF["model"].unique()
        mask = df["model"].isin(tier_models)
        sub = df.loc[mask, [c for c in df.columns
                             if c not in ("ip","op","chp","cwp","cwp_1h")]].copy()
        sub = sub.reset_index().rename(columns={"index": "_orig_idx"})

        if flat_tier:
            # 判断哪些行需要降档
            is_flat_model = sub["model"].isin(FLAT_TIER_MODELS)
            if flat_tier_since_ts is not None and "created_at" in sub.columns:
                is_after_cutoff = sub["created_at"] >= flat_tier_since_ts
            else:
                is_after_cutoff = pd.Series(True, index=sub.index)

            flat_mask = is_flat_model & is_after_cutoff
            normal_mask = ~flat_mask

            results = []

            # ── 降档部分 ──
            if flat_mask.any():
                sub_flat = sub[flat_mask].copy()
                base_tier = TIER_DF[TIER_DF["min_k"] == 0].copy()
                m_flat = sub_flat.merge(base_tier, on="model", how="left")
                m_flat = m_flat.groupby("_orig_idx").first()
                results.append(m_flat)

            # ── 正常分段部分 ──
            if normal_mask.any():
                sub_normal = sub[normal_mask].copy()
                sub_normal["pt_k"] = sub_normal["prompt_tokens"] // 1000
                m_normal = sub_normal.merge(TIER_DF, on="model", how="left")
                in_tier = (m_normal["pt_k"] >= m_normal["min_k"]) & \
                          ((m_normal["max_k"] == -1) | (m_normal["pt_k"] < m_normal["max_k"]))
                m_normal = m_normal[in_tier].groupby("_orig_idx").first()
                results.append(m_normal)

            if results:
                merged = pd.concat(results)
                for col in ("ip", "op", "chp", "cwp", "cwp_1h"):
                    df.loc[merged.index, col] = merged[col].values
        else:
            sub["pt_k"] = sub["prompt_tokens"] // 1000
            merged = sub.merge(TIER_DF, on="model", how="left")
            in_tier = (merged["pt_k"] >= merged["min_k"]) & \
                      ((merged["max_k"] == -1) | (merged["pt_k"] < merged["max_k"]))
            merged = merged[in_tier].groupby("_orig_idx").first()
            for col in ("ip", "op", "chp", "cwp", "cwp_1h"):
                df.loc[merged.index, col] = merged[col].values

    return df


def compute_costs(df: pd.DataFrame,
                  revenue_discount: float = DEFAULT_REVENUE_DISCOUNT,
                  cost_discount: float    = DEFAULT_COST_DISCOUNT,
                  flat_tier: bool         = False,
                  flat_tier_since_ts: int = None) -> pd.DataFrame:
    """
    向量化计算所有费用列。

    flat_tier=False（默认）：应付/成本/利润以系统 billed_usd（quota）为基准。
    flat_tier=True：应付/成本/利润以 expected_usd（低档价重算）为基准，
                    即剔除 200k 分段溢价后的刊例价。
    flat_tier_since_ts: 仅对 created_at >= 此时间戳 且属于 FLAT_TIER_MODELS 的行
                        使用 expected_usd 作为 price_base，其余行仍用 billed_usd。
    """
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

    billed_usd = df["quota"] / QUOTA_PER_USD

    if flat_tier:
        if flat_tier_since_ts is not None and "created_at" in df.columns:
            use_expected = (df["model"].isin(FLAT_TIER_MODELS) &
                           (df["created_at"] >= flat_tier_since_ts))
            price_base = np.where(use_expected, expected_usd, billed_usd)
        else:
            price_base = expected_usd
    else:
        price_base = billed_usd

    df = df.copy()
    df["net_input"]      = net_input.astype(np.int64)
    df["cw_5m_total"]    = cw_5m_total.astype(np.int64)
    df["cost_input"]     = cost_input
    df["cost_output"]    = cost_output
    df["cost_cache_hit"] = cost_cache_hit
    df["cost_cw_5m"]     = cost_cw_5m
    df["cost_cw_1h"]     = cost_cw_1h
    df["expected_usd"]   = expected_usd
    df["billed_usd"]     = billed_usd
    df["revenue"]        = price_base * revenue_discount
    df["cost"]           = price_base * cost_discount
    df["profit"]         = df["revenue"] - df["cost"]
    return df


def load_db(ts_start: int, ts_end: int,
            user_id: int = None, username: str = None,
            channel_id: int = None) -> pd.DataFrame:
    """
    按时间范围加载 logs。
    - user_id: 按 user_id 过滤（不限模型）
    - username: 按 username 过滤（不限模型，为空时默认 GMICloud 且只取 claude 模型）
    - channel_id: 额外按 channel_id 过滤
    - 两者都为 None: 默认 GMICloud + claude 模型（向后兼容）
    """
    conn = sqlite3.connect(DB_PATH)

    base_cols = """id, model_name AS model, quota, prompt_tokens, completion_tokens,
                      other, token_name, created_at,
                      datetime(created_at,'unixepoch','+8 hours') AS cst"""
    ch_clause = " AND channel_id=?" if channel_id is not None else ""

    if user_id is not None:
        sql = f"""SELECT {base_cols}
               FROM logs
               WHERE user_id=? AND type=2
                 AND created_at>=? AND created_at<?{ch_clause}
               ORDER BY created_at"""
        params = [user_id, ts_start, ts_end]
        if channel_id is not None:
            params.append(channel_id)
        df = pd.read_sql_query(sql, conn, params=params)
    elif username is not None:
        sql = f"""SELECT {base_cols}
               FROM logs
               WHERE username=? AND type=2
                 AND created_at>=? AND created_at<?{ch_clause}
               ORDER BY created_at"""
        params = [username, ts_start, ts_end]
        if channel_id is not None:
            params.append(channel_id)
        df = pd.read_sql_query(sql, conn, params=params)
    elif channel_id is not None:
        sql = f"""SELECT {base_cols}
               FROM logs
               WHERE channel_id=? AND type=2
                 AND created_at>=? AND created_at<?
               ORDER BY created_at"""
        params = [channel_id, ts_start, ts_end]
        df = pd.read_sql_query(sql, conn, params=params)
    else:
        sql = f"""SELECT {base_cols}
               FROM logs
               WHERE username='GMICloud' AND type=2
                 AND created_at>=? AND created_at<?
                 AND model_name LIKE '%claude%'
               ORDER BY created_at"""
        params = [ts_start, ts_end]
        df = pd.read_sql_query(sql, conn, params=params)
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
    """
    args 可以是以下格式（均支持）：
      (month_label, ts_start, ts_end)
      (month_label, ts_start, ts_end, user_id)
      (month_label, ts_start, ts_end, user_id, username, revenue_discount, cost_discount)
    也可以直接传 dict:
      {"month": ..., "ts_start": ..., "ts_end": ...,
       "user_id": ..., "username": ...,
       "revenue_discount": ..., "cost_discount": ...}
    """
    if isinstance(args, dict):
        month_label        = args["month"]
        ts_start           = args["ts_start"]
        ts_end             = args["ts_end"]
        user_id            = args.get("user_id")
        username           = args.get("username")
        display_name       = args.get("display_name")
        revenue_discount   = args.get("revenue_discount", DEFAULT_REVENUE_DISCOUNT)
        cost_discount      = args.get("cost_discount",    DEFAULT_COST_DISCOUNT)
        flat_tier          = args.get("flat_tier",        False)
        flat_tier_since_ts = args.get("flat_tier_since_ts")
        channel_id         = args.get("channel_id")
    elif len(args) == 7:
        month_label, ts_start, ts_end, user_id, username, revenue_discount, cost_discount = args
        display_name       = None
        flat_tier          = False
        flat_tier_since_ts = None
        channel_id         = None
    elif len(args) == 4:
        month_label, ts_start, ts_end, user_id = args
        username           = None
        display_name       = None
        revenue_discount   = DEFAULT_REVENUE_DISCOUNT
        cost_discount      = DEFAULT_COST_DISCOUNT
        flat_tier          = False
        flat_tier_since_ts = None
        channel_id         = None
    else:
        month_label, ts_start, ts_end = args
        user_id            = None
        username           = None
        display_name       = None
        revenue_discount   = DEFAULT_REVENUE_DISCOUNT
        cost_discount      = DEFAULT_COST_DISCOUNT
        flat_tier          = False
        flat_tier_since_ts = None
        channel_id         = None

    # label 用于日志和文件名（用数据库字段值）
    # bill_title 用于 Excel 显示（优先 display_name）
    if display_name:
        bill_title = display_name
        label      = display_name
    elif username:
        bill_title = username
        label      = username
    elif user_id:
        bill_title = f"User{user_id}"
        label      = f"user{user_id}"
    else:
        bill_title = "GMICloud"
        label      = "GMICloud"

    ch_label = f" ch={channel_id}" if channel_id else ""
    t0 = time.time()
    print(f"[{month_label}/{label}{ch_label}] loading...", flush=True)

    raw = load_db(ts_start, ts_end, user_id=user_id, username=username,
                  channel_id=channel_id)
    if raw.empty:
        print(f"[{month_label}] no data, skip")
        return

    print(f"[{month_label}/{label}{ch_label}] {len(raw):,} rows, parsing other...", flush=True)
    other_df = parse_other_batch(raw["other"])
    df = pd.concat([raw.drop(columns=["other"]), other_df], axis=1)

    tier_note = ""
    if flat_tier:
        if flat_tier_since_ts:
            from datetime import datetime as _dt
            tier_note = f" [降档自 {_dt.fromtimestamp(flat_tier_since_ts).strftime('%m-%d')}]"
        else:
            tier_note = " [统一低档价]"
    print(f"[{month_label}/{label}{ch_label}] pricing + costs{tier_note}...", flush=True)
    df = assign_prices(df, flat_tier=flat_tier, flat_tier_since_ts=flat_tier_since_ts)
    df = df.dropna(subset=["ip"])
    df = compute_costs(df, revenue_discount=revenue_discount, cost_discount=cost_discount,
                       flat_tier=flat_tier, flat_tier_since_ts=flat_tier_since_ts)

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

    print(f"[{month_label}/{label}{ch_label}] writing Excel...", flush=True)
    safe_label = label.replace("/", "_").replace("\\", "_")
    tier_suffix = "_flattier" if flat_tier else ""
    ch_suffix = f"_ch{channel_id}" if channel_id else ""
    fname = f"reconcile/{safe_label}_bill_{month_label}{tier_suffix}{ch_suffix}.xlsx"
    wb = xlsxwriter.Workbook(fname, {"constant_memory": True})
    # 汇总 Tab 标题附注
    tier_tag = "（统一低档价，不计 200k 分段）" if flat_tier else ""

    USD2 = '"$"#,##0.00'
    USD4 = '"$"#,##0.0000'
    USD6 = '"$"#,##0.000000'
    TOK  = "#,##0"
    PCT  = "0.00%"

    # ── Tab1: 按模型汇总 ──
    price_base_label = "低档价" if flat_tier else "刊例"
    s_hdrs = [
        "模型名称", "调用次数",
        "输入 Tokens", "输出 Tokens", "缓存命中 Tokens",
        "缓存写入 Tokens\n(5min)", "缓存写入 Tokens\n(1h)",
        "输入费用", "输出费用", "缓存命中费用",
        "缓存写入费用\n(5min)", "缓存写入费用\n(1h)",
        "刊例价合计\n(pricing.json 低档)" if flat_tier else "刊例价合计\n(pricing.json)",
        "刊例价合计\n(系统 billed)",
        "pricing 差额", "差额 %",
        f"{bill_title} 应付\n({price_base_label} x{revenue_discount})",
        f"我方成本\n({price_base_label} x{cost_discount})",
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

    write_sheet(wb, f"{bill_title} API 账单 -- {month_label} (模型汇总){tier_tag}",
                "按模型汇总", s_hdrs, s_wids, s_data, s_fmts,
                total_row=s_tot, total_fmts=s_fmts)

    # ── Tab2: 调用明细 ──
    d_hdrs = [
        "记录 ID", "时间 (UTC+8)", "模型名称", "Token 名称",
        "输入 Tokens", "输出 Tokens", "缓存命中 Tokens",
        "缓存写入 Tokens\n(5min)", "缓存写入 Tokens\n(1h)",
        "输入费用", "输出费用", "缓存命中费用",
        "缓存写入费用\n(5min)", "缓存写入费用\n(1h)",
        "刊例价\n(pricing.json 低档)" if flat_tier else "刊例价\n(pricing.json)",
        "刊例价\n(系统 billed)",
        f"{bill_title} 应付\n({price_base_label} x{revenue_discount})",
        f"成本\n({price_base_label} x{cost_discount})",
        "利润",
    ]
    d_wids = [12, 20, 28, 18, 14, 14, 16, 16, 16,
              15, 15, 18, 20, 20,
              15, 15, 14, 14, 13]
    d_fmts = [TOK, None, None, None, TOK, TOK, TOK, TOK, TOK,
              USD6, USD6, USD6, USD6, USD6,
              USD6, USD6, USD6, USD6, USD6]

    XLSX_MAX_ROWS = 1_048_574  # Excel 行上限减去标题行

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

    if len(d_data) <= XLSX_MAX_ROWS:
        write_sheet(wb, f"{bill_title} API 账单 -- {month_label} (调用明细){tier_tag}",
                    "明细", d_hdrs, d_wids, d_data, d_fmts)
    else:
        n_sheets = (len(d_data) + XLSX_MAX_ROWS - 1) // XLSX_MAX_ROWS
        for si in range(n_sheets):
            chunk = d_data[si * XLSX_MAX_ROWS : (si + 1) * XLSX_MAX_ROWS]
            sname = f"明细_{si+1}" if n_sheets > 1 else "明细"
            write_sheet(wb, f"{bill_title} API 账单 -- {month_label} (调用明细 {si+1}/{n_sheets}){tier_tag}",
                        sname, d_hdrs, d_wids, chunk, d_fmts)
        print(f"  明细数据 {len(d_data):,} 行，分 {n_sheets} 个 sheet 写入", flush=True)

    # ── Tab3: 三方对比（有 MateCloud 账单时） ──
    mc = load_matecloud(month_label)
    mc_info = ""
    if not mc.empty:
        cmp = grp[["model", "count", "expected_usd", "billed_usd", "revenue", "cost", "profit"]].copy()
        cmp = cmp.merge(mc, on="model", how="outer").fillna(0)
        cmp["mc_cost_41"] = cmp["mc_total"] * cost_discount
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
            f"{bill_title} 应付\n(x{revenue_discount})",
            f"MC 成本\n(MC x{cost_discount})",
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
    print(f"[{month_label}/{label}{ch_label}] OK {fname}  {len(df):,} rows / {len(grp)} models  {elapsed:.1f}s",
          flush=True)
    print(f"  billed(list)=${tots['billed_usd']:,.2f}  "
          f"revenue(x{revenue_discount})=${tots['revenue']:,.2f}  "
          f"cost(x{cost_discount})=${tots['cost']:,.2f}  "
          f"profit=${tots['profit']:,.2f}  "
          f"margin={tots['profit']/tots['revenue']*100:.1f}%",
          flush=True)
    if mc_info:
        print(mc_info, flush=True)


def _month_range(month_str: str):
    """返回 (ts_start, ts_end) 给定 'YYYY-MM'"""
    import calendar as _cal
    y, m = map(int, month_str.split("-"))
    ts_start = int(datetime(y, m, 1).timestamp())
    _, last_day = _cal.monthrange(y, m)
    from datetime import timedelta
    next_first = datetime(y, m, last_day) + timedelta(days=1)
    ts_end = int(datetime(next_first.year, next_first.month, 1).timestamp())
    return ts_start, ts_end


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="内部账单生成器")
    parser.add_argument("--user-id",          type=int,   default=None,
                        help="按 user_id 过滤（与 --username 二选一）")
    parser.add_argument("--username",          type=str,   default=None,
                        help="按数据库 username 字段过滤，例如 'Dragon'")
    parser.add_argument("--display-name",      type=str,   default=None,
                        help="账单中显示的客户名称（不填则与 --username 相同）")
    parser.add_argument("--month",             type=str,   default=None,
                        help="指定月份 YYYY-MM，不填则生成所有默认月份")
    parser.add_argument("--revenue-discount",  type=float, default=None,
                        help=f"应付折扣（默认 {DEFAULT_REVENUE_DISCOUNT}，神州数码用 0.47）")
    parser.add_argument("--cost-discount",     type=float, default=None,
                        help=f"成本折扣（默认 {DEFAULT_COST_DISCOUNT}）")
    parser.add_argument("--flat-tier",         action="store_true", default=False,
                        help="剔除分段计费：分段模型（如 claude-opus/sonnet-4-6）一律按 200k 以内低档价计算")
    parser.add_argument("--flat-tier-since",   type=str,   default=None,
                        help="降档起始日期 YYYY-MM-DD（含），之前的仍按正常分段计费。隐含 --flat-tier")
    parser.add_argument("--channel-id",        type=int,   default=None,
                        help="按 channel_id 过滤")
    parser.add_argument("--end-time",          type=str,   default=None,
                        help="截止时间 'YYYY-MM-DD HH:MM'（北京时间），覆盖月末")
    args_cli = parser.parse_args()

    rev_disc     = args_cli.revenue_discount if args_cli.revenue_discount is not None else DEFAULT_REVENUE_DISCOUNT
    cost_disc    = args_cli.cost_discount    if args_cli.cost_discount    is not None else DEFAULT_COST_DISCOUNT
    display_name = args_cli.display_name
    flat_tier    = args_cli.flat_tier
    channel_id   = args_cli.channel_id

    flat_tier_since_ts = None
    if args_cli.flat_tier_since:
        flat_tier = True
        flat_tier_since_ts = int(datetime.strptime(args_cli.flat_tier_since, "%Y-%m-%d").timestamp())

    end_time_override = None
    if args_cli.end_time:
        end_time_override = int(datetime.strptime(args_cli.end_time, "%Y-%m-%d %H:%M").timestamp())

    # 默认月份列表（GMICloud 历史账单）
    default_months = ["2026-01", "2026-02"]

    months = [args_cli.month] if args_cli.month else default_months

    if args_cli.user_id or args_cli.username:
        for mo in months:
            ts_s, ts_e = _month_range(mo)
            if end_time_override:
                ts_e = end_time_override
            make_bill({
                "month":              mo,
                "ts_start":           ts_s,
                "ts_end":             ts_e,
                "user_id":            args_cli.user_id,
                "username":           args_cli.username,
                "display_name":       display_name,
                "revenue_discount":   rev_disc,
                "cost_discount":      cost_disc,
                "flat_tier":          flat_tier,
                "flat_tier_since_ts": flat_tier_since_ts,
                "channel_id":        channel_id,
            })
    else:
        tasks = []
        for mo in months:
            ts_s, ts_e = _month_range(mo)
            if end_time_override:
                ts_e = end_time_override
            tasks.append({
                "month":              mo,
                "ts_start":           ts_s,
                "ts_end":             ts_e,
                "user_id":            None,
                "username":           None,
                "display_name":       display_name,
                "revenue_discount":   rev_disc,
                "cost_discount":      cost_disc,
                "flat_tier":          flat_tier,
                "flat_tier_since_ts": flat_tier_since_ts,
                "channel_id":        channel_id,
            })
        t0 = time.time()
        with Pool(min(2, cpu_count())) as pool:
            pool.map(make_bill, tasks)
        print(f"全部完成，总耗时 {time.time()-t0:.1f}s")
