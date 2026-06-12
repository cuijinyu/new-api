#!/usr/bin/env python3
"""2026-04/05 全平台 Gemini 经营亏损 + 3.1-flash 定价偏低少收估算。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from athena_engine import run_query_cached
from pricing_engine import (
    QUOTA_TO_USD,
    get_cost_discount,
    get_pricing,
    get_revenue_discount,
)

MODEL_31 = "gemini-3.1-flash-image-preview"
GEMINI_FILTER = "LOWER(model_name) LIKE '%gemini%'"


def _agg_sql(year: str, month: str) -> str:
    return f"""
SELECT
    user_id,
    model_name,
    channel_id,
    COUNT(*) AS call_count,
    SUM(quota) AS total_quota,
    ROUND(SUM(quota) / {QUOTA_TO_USD}, 4) AS list_usd
FROM ezmodel_logs.usage_logs
WHERE year = '{year}' AND month = '{month}'
  AND {GEMINI_FILTER}
GROUP BY user_id, model_name, channel_id
ORDER BY list_usd DESC
"""


def _row_sql_31(year: str, month: str) -> str:
    return f"""
SELECT
    quota,
    prompt_tokens,
    completion_tokens,
    other
FROM ezmodel_logs.usage_logs
WHERE year = '{year}' AND month = '{month}'
  AND model_name = '{MODEL_31}'
"""


def apply_profit_agg(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["cost_discount"] = out.apply(
        lambda r: get_cost_discount(r["channel_id"], r["model_name"]), axis=1
    )
    out["revenue_discount"] = out.apply(
        lambda r: get_revenue_discount(r["user_id"], r["model_name"]), axis=1
    )
    out["cost_usd"] = out["list_usd"] * out["cost_discount"]
    out["revenue_usd"] = out["list_usd"] * out["revenue_discount"]
    out["profit_usd"] = out["revenue_usd"] - out["cost_usd"]
    return out


def summarize_month(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "list_usd": 0.0,
            "cost_usd": 0.0,
            "revenue_usd": 0.0,
            "profit_usd": 0.0,
        }
    return {
        "list_usd": float(df["list_usd"].sum()),
        "cost_usd": float(df["cost_usd"].sum()),
        "revenue_usd": float(df["revenue_usd"].sum()),
        "profit_usd": float(df["profit_usd"].sum()),
    }


def top_loss_combos(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    neg = df[df["profit_usd"] < 0].copy()
    if neg.empty:
        return neg
    neg["cost_discount"] = neg.apply(
        lambda r: get_cost_discount(r["channel_id"], r["model_name"]), axis=1
    )
    neg["revenue_discount"] = neg.apply(
        lambda r: get_revenue_discount(r["user_id"], r["model_name"]), axis=1
    )
    return neg.sort_values("profit_usd").head(n)


def _parse_other(s) -> dict:
    if not s or (isinstance(s, float) and np.isnan(s)):
        return {}
    try:
        return json.loads(s) if isinstance(s, str) else {}
    except Exception:
        return {}


def fair_list_usd_31_row(
    quota: float,
    pt: int,
    ct: int,
    other_raw,
    pricing: dict,
) -> tuple[float, float, str]:
    """返回 (actual_usd, fair_usd, method)。"""
    actual = quota / QUOTA_TO_USD
    o = _parse_other(other_raw)
    cond_mult = float(o.get("billing_cond_multiplier") or 1.0)
    if cond_mult <= 0:
        cond_mult = 1.0

    mm = pricing.get(MODEL_31, {})
    ip = mm.get("ip", 0.5)
    op_text = mm.get("op_text", 3.0)
    op_image = mm.get("op_image", 60.0)

    img_out = int(o.get("image_completion_tokens") or 0)
    pt_f, ct_f = float(pt), float(ct)

    if img_out > 0:
        text_out = max(ct_f - img_out, 0)
        fair = (
            pt_f / 1e6 * ip
            + text_out / 1e6 * op_text
            + img_out / 1e6 * op_image
        ) * cond_mult
        method = "multimodal_split"
    else:
        # 无 image_completion_tokens：全部 completion 按 $60/M 图价
        fair = (pt_f / 1e6 * ip + ct_f / 1e6 * op_image) * cond_mult
        method = "all_completion_cr60"

    return actual, fair, method


def analyze_31_undercharge(year: str, month: str) -> dict:
    df = run_query_cached(_row_sql_31(year, month), no_cache=False)
    if df.empty:
        return {
            "rows": 0,
            "actual_usd": 0.0,
            "fair_usd": 0.0,
            "shortfall_usd": 0.0,
            "no_img_token_rows": 0,
            "no_img_token_shortfall": 0.0,
        }

    pricing = get_pricing()
    actuals, fairs, methods = [], [], []
    for _, r in df.iterrows():
        a, f, m = fair_list_usd_31_row(
            float(r["quota"]),
            int(r["prompt_tokens"] or 0),
            int(r["completion_tokens"] or 0),
            r.get("other"),
            pricing,
        )
        actuals.append(a)
        fairs.append(f)
        methods.append(m)

    df = df.copy()
    df["actual_usd"] = actuals
    df["fair_usd"] = fairs
    df["shortfall_usd"] = df["fair_usd"] - df["actual_usd"]
    df["method"] = methods

    no_img = df["method"] == "all_completion_cr60"
    return {
        "rows": len(df),
        "actual_usd": float(df["actual_usd"].sum()),
        "fair_usd": float(df["fair_usd"].sum()),
        "shortfall_usd": float(df["shortfall_usd"].sum()),
        "no_img_token_rows": int(no_img.sum()),
        "no_img_token_shortfall": float(df.loc[no_img, "shortfall_usd"].sum()),
    }


def fmt_usd(x: float) -> str:
    return f"${x:,.2f}"


def print_table(title: str, rows: list[list], headers: list[str]) -> None:
    print(f"\n### {title}")
    widths = [max(len(h), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    hdr = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep = "-+-".join("-" * widths[i] for i in range(len(headers)))
    print(hdr)
    print(sep)
    for row in rows:
        print(" | ".join(str(row[i]).ljust(widths[i]) for i in range(len(headers))))


def main():
    months = [("2026", "04", "2026-04"), ("2026", "05", "2026-05")]
    all_dfs = []
    month_summaries = {}
    month_31 = {}

    for year, mon, label in months:
        raw = run_query_cached(_agg_sql(year, mon), no_cache=False)
        raw["month"] = label
        priced = apply_profit_agg(raw)
        month_summaries[label] = summarize_month(priced)
        all_dfs.append(priced)
        month_31[label] = analyze_31_undercharge(year, mon)

    combined = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
    combined_agg = (
        combined.groupby(["user_id", "model_name", "channel_id"], as_index=False)
        .agg(
            list_usd=("list_usd", "sum"),
            cost_usd=("cost_usd", "sum"),
            revenue_usd=("revenue_usd", "sum"),
            profit_usd=("profit_usd", "sum"),
        )
    )
    # re-apply discounts on combined for display consistency (already summed)
    total = summarize_month(combined_agg)

    print("=" * 72)
    print("2026年4-5月 全平台 Gemini 亏损分析")
    print("=" * 72)

    rows_a = []
    for label in ["2026-04", "2026-05"]:
        s = month_summaries[label]
        rows_a.append(
            [
                label,
                fmt_usd(s["list_usd"]),
                fmt_usd(s["cost_usd"]),
                fmt_usd(s["revenue_usd"]),
                fmt_usd(s["profit_usd"]),
            ]
        )
    rows_a.append(
        [
            "合计",
            fmt_usd(total["list_usd"]),
            fmt_usd(total["cost_usd"]),
            fmt_usd(total["revenue_usd"]),
            fmt_usd(total["profit_usd"]),
        ]
    )
    print_table(
        "A. 经营利润（profit = 客户应付 - 成本）",
        rows_a,
        ["月份", "刊例总额", "成本总额", "客户应付", "利润"],
    )

    top = top_loss_combos(combined_agg, 10)
    if not top.empty:
        rows_top = []
        for _, r in top.iterrows():
            rows_top.append(
                [
                    int(r["user_id"]),
                    int(r["channel_id"]),
                    r["model_name"][:40],
                    fmt_usd(r["profit_usd"]),
                    f"{r['revenue_discount']:.2f}",
                    f"{r['cost_discount']:.2f}",
                ]
            )
        print_table(
            "A. 亏损 Top10（user × channel × model，4-5月合计）",
            rows_top,
            ["user_id", "channel_id", "model", "亏损", "rev_disc", "cost_disc"],
        )
    else:
        print("\n### A. 无 profit<0 组合")

    rows_b = []
    shortfall_total = 0.0
    for label in ["2026-04", "2026-05"]:
        s = month_31[label]
        shortfall_total += s["shortfall_usd"]
        rows_b.append(
            [
                label,
                s["rows"],
                fmt_usd(s["actual_usd"]),
                fmt_usd(s["fair_usd"]),
                fmt_usd(s["shortfall_usd"]),
                s["no_img_token_rows"],
                fmt_usd(s["no_img_token_shortfall"]),
            ]
        )
    rows_b.append(
        [
            "合计",
            sum(month_31[l]["rows"] for l in ["2026-04", "2026-05"]),
            fmt_usd(sum(month_31[l]["actual_usd"] for l in ["2026-04", "2026-05"])),
            fmt_usd(sum(month_31[l]["fair_usd"] for l in ["2026-04", "2026-05"])),
            fmt_usd(shortfall_total),
            sum(month_31[l]["no_img_token_rows"] for l in ["2026-04", "2026-05"]),
            fmt_usd(
                sum(month_31[l]["no_img_token_shortfall"] for l in ["2026-04", "2026-05"])
            ),
        ]
    )
    print_table(
        f"B. {MODEL_31} 少收刊例（应按 completion @$60/M）",
        rows_b,
        [
            "月份",
            "请求数",
            "实际刊例",
            "重算刊例",
            "少收",
            "无img_token行数",
            "其中少收",
        ],
    )

    profit_loss = total["profit_usd"]
    print("\n### C. 一句话结论")
    if profit_loss >= 0:
        print(
            f"4-5月 Gemini 经营利润为 {fmt_usd(profit_loss)}（未亏损）；"
            f"若存在定价问题，3.1-flash 少收刊例合计约 {fmt_usd(shortfall_total)}。"
        )
    elif abs(profit_loss) > shortfall_total * 0.5:
        print(
            f"主要亏在「渠道 cost≈1.0 + 客户 revenue 折扣」："
            f"经营亏损 {fmt_usd(profit_loss)}，远大于 3.1-flash 少收刊例 {fmt_usd(shortfall_total)}。"
        )
    else:
        print(
            f"经营亏损 {fmt_usd(profit_loss)} 与 3.1-flash 少收 {fmt_usd(shortfall_total)} 同量级，"
            f"渠道折扣与定价偏低均有贡献。"
        )

    # 按模型汇总利润（辅助）
    if not combined.empty:
        by_model = (
            combined.groupby("model_name", as_index=False)
            .agg(profit_usd=("profit_usd", "sum"), list_usd=("list_usd", "sum"))
            .sort_values("profit_usd")
        )
        print("\n### 附：按模型利润（4-5月）")
        for _, r in by_model.head(15).iterrows():
            print(f"  {r['model_name'][:50]:50s}  profit={fmt_usd(r['profit_usd'])}  list={fmt_usd(r['list_usd'])}")


if __name__ == "__main__":
    main()
