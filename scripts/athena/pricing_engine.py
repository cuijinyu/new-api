"""
四层价格计算引擎

价格层级:
  1. 刊例价 (list_price)    = quota / 500000 (USD)
  2. 成本价 (cost)          = 刊例价 × cost_discount(channel_id, model)
  3. 客户价 (revenue)       = 刊例价 × revenue_discount(user_id, model)
  4. 利润   (profit)        = revenue - cost

折扣匹配优先级（三级）:
  精确匹配 (channel×model) > 通配匹配 (channel×*) > 全局默认 (*)
"""

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

QUOTA_TO_USD = 500_000.0
_DISCOUNTS_PATH = Path(__file__).resolve().parent / "discounts.json"
_discounts_cache = None
_discounts_mtime = 0


def _load_discounts() -> dict:
    """Load discounts.json with file-mtime caching (auto-reload on edit)."""
    global _discounts_cache, _discounts_mtime
    path = os.getenv("DISCOUNTS_JSON", str(_DISCOUNTS_PATH))
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {"cost_discounts": {"defaults": {"*": 1.0}, "by_channel": {}},
                "revenue_discounts": {"defaults": {"*": 1.0}, "by_user": {}}}

    if _discounts_cache is not None and mtime == _discounts_mtime:
        return _discounts_cache

    with open(path, "r", encoding="utf-8") as f:
        _discounts_cache = json.load(f)
    _discounts_mtime = mtime
    return _discounts_cache


def save_discounts(data: dict):
    """Save discounts back to JSON file."""
    path = os.getenv("DISCOUNTS_JSON", str(_DISCOUNTS_PATH))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    global _discounts_cache, _discounts_mtime
    _discounts_cache = data
    _discounts_mtime = os.path.getmtime(path)


# ---------------------------------------------------------------------------
# Discount lookup
# ---------------------------------------------------------------------------

def _match_discount(lookup: dict, key: str, model: str) -> float:
    """Three-level discount matching: exact(key×model) > wildcard(key×*) > default(*)."""
    by_key = lookup.get("by_channel", lookup.get("by_user", {}))
    default_rate = lookup.get("defaults", {}).get("*", 1.0)

    key_str = str(key)
    entry = by_key.get(key_str)
    if entry is None:
        return default_rate

    # Exact model match
    if model in entry:
        return entry[model]

    # Model prefix match (e.g. "claude-*" matches "claude-opus-4-6")
    for pattern, rate in entry.items():
        if pattern.startswith("_"):
            continue
        if pattern.endswith("*") and model.startswith(pattern[:-1]):
            return rate

    # Wildcard
    if "*" in entry:
        return entry["*"]

    return default_rate


def get_cost_discount(channel_id, model: str) -> float:
    """Get cost discount for a channel×model combination."""
    d = _load_discounts()
    return _match_discount(d["cost_discounts"], channel_id, model)


def get_revenue_discount(user_id, model: str) -> float:
    """Get revenue discount for a user×model combination."""
    d = _load_discounts()
    return _match_discount(d["revenue_discounts"], user_id, model)


# ---------------------------------------------------------------------------
# DataFrame pricing
# ---------------------------------------------------------------------------

def apply_pricing(df: pd.DataFrame) -> pd.DataFrame:
    """Add pricing columns to a usage_logs DataFrame.

    Expects columns: quota, channel_id, user_id, model_name
    Adds columns: list_price_usd, cost_discount, cost_usd,
                  revenue_discount, revenue_usd, profit_usd, margin_pct
    """
    if df.empty:
        for col in ("list_price_usd", "cost_discount", "cost_usd",
                     "revenue_discount", "revenue_usd", "profit_usd", "margin_pct"):
            df[col] = pd.Series(dtype="float64")
        return df

    df = df.copy()

    df["list_price_usd"] = df["quota"].astype(float) / QUOTA_TO_USD

    df["cost_discount"] = df.apply(
        lambda r: get_cost_discount(r.get("channel_id", 0), r.get("model_name", "")),
        axis=1)
    df["cost_usd"] = df["list_price_usd"] * df["cost_discount"]

    df["revenue_discount"] = df.apply(
        lambda r: get_revenue_discount(r.get("user_id", 0), r.get("model_name", "")),
        axis=1)
    df["revenue_usd"] = df["list_price_usd"] * df["revenue_discount"]

    df["profit_usd"] = df["revenue_usd"] - df["cost_usd"]
    df["margin_pct"] = (df["profit_usd"] / df["revenue_usd"].replace(0, float("nan")) * 100).round(2)

    return df


def _compute_list_price_from_agg(model: str, input_tokens: float,
                                 output_tokens: float,
                                 cache_hit: float = 0,
                                 cache_write: float = 0,
                                 cw_5m: float = 0, cw_1h: float = 0,
                                 cw_remaining: float = 0,
                                 flat_tier: bool = False) -> float:
    """Compute list price from aggregated token counts using PRICING table.

    Uses cache token breakdown for precise pricing. For tiered models,
    flat_tier=True forces lowest-tier unit prices.
    Returns None if model not in PRICING.
    """
    pricing = PRICING.get(model)
    if pricing is None:
        return None

    if isinstance(pricing, list):
        tier = pricing[0] if flat_tier else pricing[-1]
    else:
        tier = pricing

    ip_rate  = tier["ip"]
    op_rate  = tier["op"]
    chp_rate = tier["chp"]
    cwp_rate = tier["cwp"]
    cwp_1h_rate = tier["cwp_1h"]

    net_input = max(input_tokens - cache_hit - cache_write, 0)
    cw_5m_total = cw_5m + cw_remaining

    cost = (net_input / 1e6 * ip_rate
            + output_tokens / 1e6 * op_rate
            + cache_hit / 1e6 * chp_rate
            + cw_5m_total / 1e6 * cwp_rate
            + cw_1h / 1e6 * cwp_1h_rate)
    return cost


def apply_pricing_summary(df_summary: pd.DataFrame,
                          flat_tier: bool = False,
                          flat_tier_since: str = None) -> pd.DataFrame:
    """Add pricing to a summary DataFrame (grouped by user/model/channel).

    Expects columns from monthly_bill_full:
      total_quota/total_usd, channel_id, user_id, model_name,
      total_input_tokens, total_output_tokens,
      total_cache_hit_tokens, total_cache_write_tokens,
      total_cw_5m, total_cw_1h, total_cw_remaining

    When flat_tier=True, tiered models use lowest-tier unit prices.
    Cache token breakdown enables precise pricing even on aggregated data.
    """
    if df_summary.empty:
        return df_summary

    if flat_tier_since:
        flat_tier = True

    df = df_summary.copy()

    # Default list price from quota
    if "total_usd" in df.columns:
        df["list_price_usd"] = df["total_usd"].astype(float)
    elif "total_quota" in df.columns:
        df["list_price_usd"] = df["total_quota"].astype(float) / QUOTA_TO_USD
    else:
        df["list_price_usd"] = 0.0

    # Recalculate list price from pricing table when cache token data is available
    has_cache = "total_cache_hit_tokens" in df.columns
    has_tokens = "total_input_tokens" in df.columns and "total_output_tokens" in df.columns

    if has_tokens:
        recalc_prices = []
        for idx, row in df.iterrows():
            model = row.get("model_name", "")
            use_flat = flat_tier and model in FLAT_TIER_MODELS

            ch  = float(row.get("total_cache_hit_tokens", 0) or 0) if has_cache else 0
            cw  = float(row.get("total_cache_write_tokens", 0) or 0) if has_cache else 0
            c5  = float(row.get("total_cw_5m", 0) or 0) if has_cache else 0
            c1h = float(row.get("total_cw_1h", 0) or 0) if has_cache else 0
            cr  = float(row.get("total_cw_remaining", 0) or 0) if has_cache else 0

            price = _compute_list_price_from_agg(
                model,
                float(row["total_input_tokens"]),
                float(row["total_output_tokens"]),
                cache_hit=ch, cache_write=cw,
                cw_5m=c5, cw_1h=c1h, cw_remaining=cr,
                flat_tier=use_flat)

            recalc_prices.append(price)

        for idx, price in zip(df.index, recalc_prices):
            if price is not None:
                df.at[idx, "list_price_usd"] = round(price, 6)

    if "channel_id" in df.columns:
        df["cost_discount"] = df.apply(
            lambda r: get_cost_discount(r["channel_id"], r.get("model_name", "*")),
            axis=1)
    else:
        df["cost_discount"] = 1.0

    if "user_id" in df.columns:
        df["revenue_discount"] = df.apply(
            lambda r: get_revenue_discount(r["user_id"], r.get("model_name", "*")),
            axis=1)
    else:
        df["revenue_discount"] = 1.0

    df["cost_usd"] = (df["list_price_usd"] * df["cost_discount"]).round(4)
    df["revenue_usd"] = (df["list_price_usd"] * df["revenue_discount"]).round(4)
    df["profit_usd"] = (df["revenue_usd"] - df["cost_usd"]).round(4)
    df["margin_pct"] = (df["profit_usd"] / df["revenue_usd"].replace(0, float("nan")) * 100).round(2)

    return df


# ---------------------------------------------------------------------------
# Discount summary helpers
# ---------------------------------------------------------------------------

def get_all_cost_discounts() -> list[dict]:
    """Return all cost discount entries as a flat list for display."""
    d = _load_discounts()
    rows = []
    for ch_id, entry in d["cost_discounts"].get("by_channel", {}).items():
        name = entry.get("_name", "")
        for model, rate in entry.items():
            if model.startswith("_"):
                continue
            rows.append({"channel_id": ch_id, "channel_name": name,
                         "model": model, "discount": rate})
    return rows


def get_all_revenue_discounts() -> list[dict]:
    """Return all revenue discount entries as a flat list for display."""
    d = _load_discounts()
    rows = []
    for uid, entry in d["revenue_discounts"].get("by_user", {}).items():
        name = entry.get("_name", "")
        for model, rate in entry.items():
            if model.startswith("_"):
                continue
            rows.append({"user_id": uid, "user_name": name,
                         "model": model, "discount": rate})
    return rows


# ===========================================================================
# Tiered pricing recalculation (ported from gen_bill.py)
# ===========================================================================

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

FLAT_TIER_MODELS = {"claude-opus-4-6", "claude-sonnet-4-6"}

_TIER_ROWS, _FLAT_ROWS = [], []
for _m, _p in PRICING.items():
    if isinstance(_p, list):
        for _t in _p:
            _TIER_ROWS.append({"model": _m, **_t})
    else:
        _FLAT_ROWS.append({"model": _m, **_p})
TIER_DF = pd.DataFrame(_TIER_ROWS) if _TIER_ROWS else pd.DataFrame()
FLAT_DF = pd.DataFrame(_FLAT_ROWS) if _FLAT_ROWS else pd.DataFrame()


def _parse_other_batch(other_series: pd.Series) -> pd.DataFrame:
    """Parse the 'other' JSON column, extract cache token fields."""
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


def _assign_prices(df: pd.DataFrame, flat_tier: bool = False,
                   flat_tier_since_ts: int = None) -> pd.DataFrame:
    """Assign per-row tiered prices based on model and prompt_tokens."""
    df = df.copy()
    for col in ("ip", "op", "chp", "cwp", "cwp_1h"):
        df[col] = np.nan

    if not FLAT_DF.empty:
        flat_map = FLAT_DF.set_index("model")
        mask = df["model"].isin(flat_map.index)
        for col in ("ip", "op", "chp", "cwp", "cwp_1h"):
            df.loc[mask, col] = df.loc[mask, "model"].map(flat_map[col])

    if not TIER_DF.empty:
        tier_models = TIER_DF["model"].unique()
        mask = df["model"].isin(tier_models)
        sub = df.loc[mask, [c for c in df.columns
                            if c not in ("ip", "op", "chp", "cwp", "cwp_1h")]].copy()
        sub = sub.reset_index().rename(columns={"index": "_orig_idx"})

        if flat_tier:
            is_flat_model = sub["model"].isin(FLAT_TIER_MODELS)
            if flat_tier_since_ts is not None and "created_at" in sub.columns:
                is_after_cutoff = sub["created_at"].astype(int) >= flat_tier_since_ts
            else:
                is_after_cutoff = pd.Series(True, index=sub.index)

            flat_mask = is_flat_model & is_after_cutoff
            normal_mask = ~flat_mask
            results = []

            if flat_mask.any():
                sub_flat = sub[flat_mask].copy()
                base_tier = TIER_DF[TIER_DF["min_k"] == 0].copy()
                m_flat = sub_flat.merge(base_tier, on="model", how="left")
                m_flat = m_flat.groupby("_orig_idx").first()
                results.append(m_flat)

            if normal_mask.any():
                sub_normal = sub[normal_mask].copy()
                sub_normal["pt_k"] = sub_normal["prompt_tokens"].astype(int) // 1000
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
            sub["pt_k"] = sub["prompt_tokens"].astype(int) // 1000
            merged = sub.merge(TIER_DF, on="model", how="left")
            in_tier = (merged["pt_k"] >= merged["min_k"]) & \
                      ((merged["max_k"] == -1) | (merged["pt_k"] < merged["max_k"]))
            merged = merged[in_tier].groupby("_orig_idx").first()
            for col in ("ip", "op", "chp", "cwp", "cwp_1h"):
                df.loc[merged.index, col] = merged[col].values

    return df


def recalc_from_raw(df: pd.DataFrame,
                    flat_tier: bool = False,
                    flat_tier_since: str = None) -> pd.DataFrame:
    """Recalculate list price from row-level usage_logs using PRICING table.

    Input df must have: model_name, prompt_tokens, completion_tokens,
                        quota, other, created_at, channel_id, user_id
    Output adds: expected_usd (recalculated), billed_usd (quota-based),
                 cost_usd, revenue_usd, profit_usd
    """
    if df.empty:
        return df

    df = df.copy()

    # Normalize column name for pricing logic
    if "model_name" in df.columns and "model" not in df.columns:
        df["model"] = df["model_name"]

    # Parse flat_tier_since to unix timestamp
    flat_tier_since_ts = None
    if flat_tier_since:
        from datetime import datetime
        flat_tier_since_ts = int(datetime.strptime(flat_tier_since, "%Y-%m-%d").timestamp())
        flat_tier = True

    # Parse other JSON
    other_cols = _parse_other_batch(df["other"].fillna(""))
    df = pd.concat([df, other_cols], axis=1)

    # Assign tiered prices
    df = _assign_prices(df, flat_tier=flat_tier, flat_tier_since_ts=flat_tier_since_ts)

    # Compute expected_usd (recalculated from pricing table)
    is_new = df["is_new"]
    chp     = np.where(is_new & df["chp_new"].notna(),    df["chp_new"],    df["chp"])
    cwp_5m  = np.where(is_new & df["cwp_5m_new"].notna(), df["cwp_5m_new"], df["cwp"])
    cwp_1h  = np.where(is_new & df["cwp_1h_new"].notna(), df["cwp_1h_new"], df["cwp_1h"])

    pt = df["prompt_tokens"].astype(float)
    ct = df["completion_tokens"].astype(float)
    ch_tok = df["ch"].astype(float)
    cw_tok = df["cw"].astype(float)

    net_input   = np.maximum(pt - ch_tok - cw_tok, 0)
    cw_5m_total = df["cw_rem"].astype(float) + df["cw_5m"].astype(float)

    cost_input      = net_input / 1e6 * df["ip"]
    cost_output     = ct / 1e6 * df["op"]
    cost_cache_hit  = ch_tok / 1e6 * chp
    cost_cw_5m      = cw_5m_total / 1e6 * cwp_5m
    cost_cw_1h      = df["cw_1h"].astype(float) / 1e6 * cwp_1h
    expected_usd    = cost_input + cost_output + cost_cache_hit + cost_cw_5m + cost_cw_1h

    billed_usd = df["quota"].astype(float) / QUOTA_TO_USD

    # Choose price base
    if flat_tier:
        if flat_tier_since_ts is not None and "created_at" in df.columns:
            use_expected = (df["model"].isin(FLAT_TIER_MODELS) &
                           (df["created_at"].astype(int) >= flat_tier_since_ts))
            price_base = np.where(use_expected, expected_usd, billed_usd)
        else:
            price_base = expected_usd
    else:
        price_base = billed_usd

    df["expected_usd"]   = expected_usd
    df["billed_usd"]     = billed_usd
    df["recalc_usd"]     = price_base
    df["diff_usd"]       = billed_usd - expected_usd
    df["has_pricing"]    = df["ip"].notna()

    # Apply discounts
    df["cost_discount"] = df.apply(
        lambda r: get_cost_discount(r.get("channel_id", 0), r.get("model", "")),
        axis=1)
    df["revenue_discount"] = df.apply(
        lambda r: get_revenue_discount(r.get("user_id", 0), r.get("model", "")),
        axis=1)

    df["cost_usd"]    = pd.Series(price_base) * df["cost_discount"]
    df["revenue_usd"] = pd.Series(price_base) * df["revenue_discount"]
    df["profit_usd"]  = df["revenue_usd"] - df["cost_usd"]

    return df


# ---------------------------------------------------------------------------
# Cross-check with vendor bills
# ---------------------------------------------------------------------------

def cross_check(our_data: pd.DataFrame, vendor_bill: pd.DataFrame,
                match_col: str = "model_name") -> pd.DataFrame:
    """Cross-check our billing data against a vendor bill.

    our_data: grouped by model_name with at least: call_count, total_usd or list_price_usd
    vendor_bill: must have 'model' and 'amount' columns (after normalization)
    Returns a merged DataFrame with diff columns.
    """
    ours = our_data.copy()
    vendor = vendor_bill.copy()

    # Normalize our side
    if "list_price_usd" in ours.columns:
        our_amount_col = "list_price_usd"
    elif "total_usd" in ours.columns:
        our_amount_col = "total_usd"
    elif "billed_usd" in ours.columns:
        our_amount_col = "billed_usd"
    else:
        our_amount_col = None

    if match_col in ours.columns:
        ours = ours.rename(columns={match_col: "model"})

    if our_amount_col:
        ours = ours.rename(columns={our_amount_col: "our_amount"})

    our_cols = ["model"]
    if "call_count" in ours.columns:
        our_cols.append("call_count")
    if "our_amount" in ours.columns:
        our_cols.append("our_amount")
    ours = ours[our_cols]

    # Normalize vendor side
    if "model" not in vendor.columns:
        for alt in ("模型", "model_name"):
            if alt in vendor.columns:
                vendor = vendor.rename(columns={alt: "model"})
                break

    # Detect amount column
    amt_col = None
    for candidate in ("vendor_amount", "amount", "额度", "total", "cost", "金额"):
        if candidate in vendor.columns:
            amt_col = candidate
            break
    if amt_col is None:
        raise ValueError(f"Cannot find amount column in vendor data. Columns: {list(vendor.columns)}")

    if amt_col != "amount":
        vendor = vendor.rename(columns={amt_col: "amount"})

    # Detect count column
    cnt_col = None
    for candidate in ("vendor_count", "count", "记录数"):
        if candidate in vendor.columns:
            cnt_col = candidate
            break

    agg_spec = {"vendor_amount": ("amount", "sum")}
    if cnt_col and cnt_col != "vendor_count":
        vendor = vendor.rename(columns={cnt_col: "vendor_count_raw"})
        agg_spec["vendor_count"] = ("vendor_count_raw", "sum")
    elif cnt_col == "vendor_count":
        agg_spec["vendor_count"] = ("vendor_count", "sum")
    else:
        agg_spec["vendor_count"] = ("amount", "count")

    vendor_agg = vendor.groupby("model").agg(**agg_spec).reset_index()

    merged = ours.merge(vendor_agg, on="model", how="outer").fillna(0)

    if "our_amount" in merged.columns:
        merged["diff"] = merged["our_amount"] - merged["vendor_amount"]
        merged["diff_pct"] = (merged["diff"] / merged["vendor_amount"].replace(0, float("nan")) * 100).round(2)

    return merged.sort_values("vendor_amount", ascending=False)
