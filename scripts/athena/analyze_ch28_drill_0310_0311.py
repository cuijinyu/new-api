"""
渠道28 对账下钻分析 - 3/10 & 3/11 逐条明细
"""

import zipfile
import io
import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUR_ZIP = Path(r"e:\new-api\scripts\athena\output\bill_2026-01_ch28_ch28_supplier_detail.csv.zip")
VENDOR_XLSX = Path(r"c:\Users\Administrator\xwechat_files\wxid_8zd2avj7cixo22_b66d\msg\file\2026-05\uniaix_logs(2).xlsx")
TARGET_DATES = ["2026-03-10", "2026-03-11"]
FOCUS_MODELS = ["claude-opus-4-6", "claude-sonnet-4-6"]


def load_our_data() -> pd.DataFrame:
    with zipfile.ZipFile(OUR_ZIP) as zf:
        with zf.open(zf.namelist()[0]) as f:
            df = pd.read_csv(f, encoding="utf-8-sig")
    df["date"] = df["Time (UTC+8)"].str[:10]
    df = df[df["date"].isin(TARGET_DATES)].copy()
    for col in ["Input Tokens", "Output Tokens", "Cache Hit Tokens", "Cache Write Tokens",
                 "Cache Write (5min)", "Cache Write (1h)", "Cache Write (remaining)", "Quota"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["Billed USD"] = pd.to_numeric(df["Billed USD"], errors="coerce").fillna(0)
    df["Use Time (s)"] = pd.to_numeric(df["Use Time (s)"], errors="coerce").fillna(0)
    return df


def load_vendor_data() -> pd.DataFrame:
    df = pd.read_excel(VENDOR_XLSX, sheet_name="Result 1")
    df["date"] = df["Date"].astype(str).str[:10]
    df = df[df["date"].isin(TARGET_DATES)].copy()
    for col in ["InputTokens", "OutputTokens", "CreateCacheTokens", "ReadCacheTokens", "TotalTokens"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    for col in ["InputPrice", "CreateCachePrice", "ReadCachePrice", "OutputPrice", "TotalPrice"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def print_sep(title: str):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")


def stat_series(s: pd.Series) -> dict:
    return {
        "count": len(s),
        "sum": int(s.sum()),
        "min": int(s.min()) if len(s) else 0,
        "max": int(s.max()) if len(s) else 0,
        "mean": round(s.mean(), 1) if len(s) else 0,
        "median": round(s.median(), 1) if len(s) else 0,
    }


def analyze_records(our: pd.DataFrame, vendor: pd.DataFrame):
    """Task 1 & 2: 记录数和 token 汇总对比"""
    print_sep("1. 各日期×模型 记录数 & Token 汇总对比")

    for date in TARGET_DATES:
        print(f"\n--- {date} ---")
        our_d = our[our["date"] == date]
        ven_d = vendor[vendor["date"] == date]

        all_models = sorted(set(our_d["Model"].unique()) | set(ven_d["ModelName"].unique()))
        for model in all_models:
            o = our_d[our_d["Model"] == model]
            v = ven_d[ven_d["ModelName"] == model]
            if len(o) == 0 and len(v) == 0:
                continue
            print(f"\n  模型: {model}")
            print(f"    记录数: 我方={len(o):,}  供应商={len(v):,}  差={len(o)-len(v):+,}")

            if len(o) > 0:
                o_input = int(o["Input Tokens"].sum())
                o_output = int(o["Output Tokens"].sum())
                o_cache_hit = int(o["Cache Hit Tokens"].sum())
                o_cache_write = int(o["Cache Write Tokens"].sum())
                o_billed = o["Billed USD"].sum()
            else:
                o_input = o_output = o_cache_hit = o_cache_write = 0
                o_billed = 0.0

            if len(v) > 0:
                v_input = int(v["InputTokens"].sum())
                v_output = int(v["OutputTokens"].sum())
                v_cache_create = int(v["CreateCacheTokens"].sum())
                v_cache_read = int(v["ReadCacheTokens"].sum())
                v_total_price = v["TotalPrice"].sum()
                v_input_price = v["InputPrice"].sum()
                v_output_price = v["OutputPrice"].sum()
                v_cache_create_price = v["CreateCachePrice"].sum()
                v_cache_read_price = v["ReadCachePrice"].sum()
            else:
                v_input = v_output = v_cache_create = v_cache_read = 0
                v_total_price = v_input_price = v_output_price = 0.0
                v_cache_create_price = v_cache_read_price = 0.0

            print(f"    --- Token 对比 ---")
            print(f"    我方 Input Tokens:       {o_input:>12,}")
            print(f"    供应商 InputTokens:       {v_input:>12,}")
            print(f"    供应商 CreateCacheTokens: {v_cache_create:>12,}")
            print(f"    供应商 ReadCacheTokens:   {v_cache_read:>12,}")
            print(f"    供应商 Input+Create+Read: {v_input+v_cache_create+v_cache_read:>12,}")
            print(f"    我方 Cache Hit Tokens:    {o_cache_hit:>12,}")
            print(f"    我方 Cache Write Tokens:  {o_cache_write:>12,}")
            print(f"    我方 Input+CacheHit:      {o_input+o_cache_hit:>12,}")
            print()
            print(f"    我方 Output Tokens:       {o_output:>12,}")
            print(f"    供应商 OutputTokens:      {v_output:>12,}")
            if o_output and v_output:
                print(f"    Output 差异比:            {(o_output-v_output)/v_output*100:>+11.1f}%")
            print()
            print(f"    --- 金额对比 ---")
            print(f"    我方 Billed USD:          ${o_billed:>12,.4f}")
            print(f"    供应商 TotalPrice:        ${v_total_price:>12,.4f}")
            if o_billed and v_total_price:
                print(f"    金额差异比:               {(o_billed-v_total_price)/v_total_price*100:>+11.1f}%")

            # token 口径验证
            if model in FOCUS_MODELS and len(o) > 0 and len(v) > 0:
                print(f"\n    --- Token 口径验证 ---")
                # 假设1: 供应商 InputTokens 不含 cache
                hyp1 = v_input + v_cache_read
                print(f"    假设1: 供应商 InputTokens 不含 cache_read")
                print(f"      供应商 InputTokens + ReadCacheTokens = {hyp1:,}")
                print(f"      我方 Input Tokens                    = {o_input:,}")
                if hyp1:
                    print(f"      差异比 = {(o_input-hyp1)/hyp1*100:+.2f}%")

                # 假设2: 供应商 InputTokens 已含 cache_read
                hyp2 = v_input
                print(f"    假设2: 供应商 InputTokens 已含 cache_read")
                print(f"      供应商 InputTokens                   = {hyp2:,}")
                print(f"      我方 Input Tokens                    = {o_input:,}")
                if hyp2:
                    print(f"      差异比 = {(o_input-hyp2)/hyp2*100:+.2f}%")

                # 假设3: 我方 Input Tokens = prompt_tokens (含 cache_read)
                hyp3_ours = o_input
                hyp3_vendor = v_input + v_cache_read
                print(f"    假设3: 我方 Input = prompt_tokens(含cache_read), 供应商需加上ReadCache")
                print(f"      我方 Input Tokens                    = {hyp3_ours:,}")
                print(f"      供应商 InputTokens + ReadCacheTokens = {hyp3_vendor:,}")
                if hyp3_vendor:
                    print(f"      差异比 = {(hyp3_ours-hyp3_vendor)/hyp3_vendor*100:+.2f}%")


def analyze_token_distribution(our: pd.DataFrame, vendor: pd.DataFrame):
    """Task 2 continued: 单条记录 token 分布"""
    print_sep("2. 单条记录 Token 分布对比 (min/max/mean/median)")

    for date in TARGET_DATES:
        for model in FOCUS_MODELS:
            o = our[(our["date"] == date) & (our["Model"] == model)]
            v = vendor[(vendor["date"] == date) & (vendor["ModelName"] == model)]
            if len(o) == 0 and len(v) == 0:
                continue
            print(f"\n--- {date} / {model} ---")

            if len(o) > 0:
                print(f"  我方 ({len(o):,} 条):")
                for col in ["Input Tokens", "Output Tokens", "Cache Hit Tokens", "Cache Write Tokens"]:
                    s = stat_series(o[col])
                    print(f"    {col:25s}: sum={s['sum']:>12,}  min={s['min']:>8,}  max={s['max']:>8,}  mean={s['mean']:>10,}  median={s['median']:>10,}")

            if len(v) > 0:
                print(f"  供应商 ({len(v):,} 条):")
                for col in ["InputTokens", "OutputTokens", "CreateCacheTokens", "ReadCacheTokens"]:
                    s = stat_series(v[col])
                    print(f"    {col:25s}: sum={s['sum']:>12,}  min={s['min']:>8,}  max={s['max']:>8,}  mean={s['mean']:>10,}  median={s['median']:>10,}")


def try_match_records(our: pd.DataFrame, vendor: pd.DataFrame):
    """Task 3: 尝试按记录匹配"""
    print_sep("3. 逐条记录匹配分析")

    for date in TARGET_DATES:
        for model in FOCUS_MODELS:
            o = our[(our["date"] == date) & (our["Model"] == model)].copy()
            v = vendor[(vendor["date"] == date) & (vendor["ModelName"] == model)].copy()
            if len(o) == 0 or len(v) == 0:
                continue

            print(f"\n--- {date} / {model} ---")
            print(f"  我方 {len(o):,} 条, 供应商 {len(v):,} 条, 差 {len(o)-len(v):+,}")

            # 方法: 按 Output Tokens 排序对齐
            o_sorted = o.sort_values("Output Tokens").reset_index(drop=True)
            v_sorted = v.sort_values("OutputTokens").reset_index(drop=True)

            min_len = min(len(o_sorted), len(v_sorted))
            o_match = o_sorted.head(min_len)
            v_match = v_sorted.head(min_len)

            # 比较 output tokens
            output_diff = o_match["Output Tokens"].values - v_match["OutputTokens"].values
            exact_match = (output_diff == 0).sum()
            close_match = (np.abs(output_diff) <= 5).sum()
            print(f"  按 Output Tokens 排序对齐后 ({min_len:,} 对):")
            print(f"    Output 完全匹配: {exact_match:,} ({exact_match/min_len*100:.1f}%)")
            print(f"    Output 近似匹配 (±5): {close_match:,} ({close_match/min_len*100:.1f}%)")

            # input tokens 对比
            input_diff = o_match["Input Tokens"].values - v_match["InputTokens"].values
            input_exact = (input_diff == 0).sum()
            print(f"    Input 完全匹配: {input_exact:,} ({input_exact/min_len*100:.1f}%)")

            # 看看 Input Tokens vs InputTokens + ReadCacheTokens
            v_input_plus_cache = v_match["InputTokens"].values + v_match["ReadCacheTokens"].values
            input_cache_diff = o_match["Input Tokens"].values - v_input_plus_cache
            input_cache_exact = (input_cache_diff == 0).sum()
            input_cache_close = (np.abs(input_cache_diff) <= 5).sum()
            print(f"    我方 Input == 供应商 Input+ReadCache 完全匹配: {input_cache_exact:,} ({input_cache_exact/min_len*100:.1f}%)")
            print(f"    我方 Input ≈ 供应商 Input+ReadCache (±5): {input_cache_close:,} ({input_cache_close/min_len*100:.1f}%)")

            # 分析多出/缺失的记录
            if len(o) > len(v):
                extra = len(o) - len(v)
                extra_records = o_sorted.tail(extra) if extra > 0 else pd.DataFrame()
                if len(extra_records) > 0:
                    print(f"  我方多出 {extra} 条记录:")
                    extra_input = int(extra_records["Input Tokens"].sum())
                    extra_output = int(extra_records["Output Tokens"].sum())
                    extra_billed = extra_records["Billed USD"].sum()
                    print(f"    Input Tokens 合计: {extra_input:,}")
                    print(f"    Output Tokens 合计: {extra_output:,}")
                    print(f"    Billed USD 合计: ${extra_billed:,.4f}")
            elif len(v) > len(o):
                extra = len(v) - len(o)
                extra_records = v_sorted.tail(extra)
                if len(extra_records) > 0:
                    print(f"  供应商多出 {extra} 条记录:")
                    extra_input = int(extra_records["InputTokens"].sum())
                    extra_output = int(extra_records["OutputTokens"].sum())
                    extra_price = extra_records["TotalPrice"].sum()
                    print(f"    InputTokens 合计: {extra_input:,}")
                    print(f"    OutputTokens 合计: {extra_output:,}")
                    print(f"    TotalPrice 合计: ${extra_price:,.4f}")


def analyze_token_calibration(our: pd.DataFrame, vendor: pd.DataFrame):
    """Task 4: Token 口径还原 - 逐条级别"""
    print_sep("4. Token 口径还原 - 逐条级别分析")

    for date in TARGET_DATES:
        for model in FOCUS_MODELS:
            o = our[(our["date"] == date) & (our["Model"] == model)].copy()
            v = vendor[(vendor["date"] == date) & (vendor["ModelName"] == model)].copy()
            if len(o) == 0 or len(v) == 0:
                continue

            print(f"\n--- {date} / {model} ---")

            # 按 output tokens 排序对齐
            o_sorted = o.sort_values(["Output Tokens", "Input Tokens"]).reset_index(drop=True)
            v_sorted = v.sort_values(["OutputTokens", "InputTokens"]).reset_index(drop=True)
            min_len = min(len(o_sorted), len(v_sorted))

            o_m = o_sorted.head(min_len)
            v_m = v_sorted.head(min_len)

            # 逐条比较不同假设
            o_input = o_m["Input Tokens"].values
            o_cache_hit = o_m["Cache Hit Tokens"].values
            o_cache_write = o_m["Cache Write Tokens"].values
            v_input = v_m["InputTokens"].values
            v_cache_create = v_m["CreateCacheTokens"].values
            v_cache_read = v_m["ReadCacheTokens"].values
            v_output = v_m["OutputTokens"].values
            o_output = o_m["Output Tokens"].values

            # 分析有 cache 和无 cache 的记录
            has_cache = (v_cache_read > 0) | (v_cache_create > 0)
            no_cache = ~has_cache
            print(f"  供应商有 Cache 的记录: {has_cache.sum():,} 条")
            print(f"  供应商无 Cache 的记录: {no_cache.sum():,} 条")

            # 无 cache 场景: 直接比较 Input
            if no_cache.sum() > 0:
                diff_no_cache = o_input[no_cache] - v_input[no_cache]
                print(f"\n  [无 Cache 记录] Input Tokens 差异 (我方 - 供应商):")
                print(f"    完全相等: {(diff_no_cache == 0).sum():,} / {no_cache.sum():,}")
                if len(diff_no_cache[diff_no_cache != 0]) > 0:
                    print(f"    不等记录差异: min={diff_no_cache[diff_no_cache!=0].min():,}  max={diff_no_cache[diff_no_cache!=0].max():,}  mean={diff_no_cache[diff_no_cache!=0].mean():.1f}")

            # 有 cache 场景
            if has_cache.sum() > 0:
                # 假设1: 我方 Input = 供应商 Input + ReadCache
                diff_hyp1 = o_input[has_cache] - (v_input[has_cache] + v_cache_read[has_cache])
                print(f"\n  [有 Cache 记录] 假设1: 我方 Input = 供应商 Input + ReadCache")
                print(f"    完全相等: {(diff_hyp1 == 0).sum():,} / {has_cache.sum():,}")
                if len(diff_hyp1) > 0:
                    print(f"    差异: min={diff_hyp1.min():,}  max={diff_hyp1.max():,}  mean={diff_hyp1.mean():.1f}  median={np.median(diff_hyp1):.1f}")

                # 假设2: 我方 Input = 供应商 Input (已含 cache)
                diff_hyp2 = o_input[has_cache] - v_input[has_cache]
                print(f"  [有 Cache 记录] 假设2: 我方 Input = 供应商 Input (已含 cache)")
                print(f"    完全相等: {(diff_hyp2 == 0).sum():,} / {has_cache.sum():,}")
                if len(diff_hyp2) > 0:
                    print(f"    差异: min={diff_hyp2.min():,}  max={diff_hyp2.max():,}  mean={diff_hyp2.mean():.1f}  median={np.median(diff_hyp2):.1f}")

                # 假设3: 我方 Input + CacheHit = 供应商 Input + ReadCache
                diff_hyp3 = (o_input[has_cache] + o_cache_hit[has_cache]) - (v_input[has_cache] + v_cache_read[has_cache])
                print(f"  [有 Cache 记录] 假设3: 我方 Input+CacheHit = 供应商 Input+ReadCache")
                print(f"    完全相等: {(diff_hyp3 == 0).sum():,} / {has_cache.sum():,}")
                if len(diff_hyp3) > 0:
                    print(f"    差异: min={diff_hyp3.min():,}  max={diff_hyp3.max():,}  mean={diff_hyp3.mean():.1f}  median={np.median(diff_hyp3):.1f}")

            # Output tokens 对比
            output_diff = o_output - v_output
            print(f"\n  Output Tokens 差异 (我方 - 供应商):")
            print(f"    完全相等: {(output_diff == 0).sum():,} / {min_len:,}")
            print(f"    差异: min={output_diff.min():,}  max={output_diff.max():,}  mean={output_diff.mean():.1f}  median={np.median(output_diff):.1f}")

            # 我方 CacheHit vs 供应商 ReadCache
            cache_diff = o_cache_hit - v_cache_read
            print(f"\n  CacheHit 对比 (我方 CacheHit - 供应商 ReadCache):")
            print(f"    完全相等: {(cache_diff == 0).sum():,} / {min_len:,}")
            print(f"    差异: min={cache_diff.min():,}  max={cache_diff.max():,}  mean={cache_diff.mean():.1f}")

            # 我方 CacheWrite vs 供应商 CreateCache
            cw_diff = o_cache_write - v_cache_create
            print(f"  CacheWrite 对比 (我方 CacheWrite - 供应商 CreateCache):")
            print(f"    完全相等: {(cw_diff == 0).sum():,} / {min_len:,}")
            print(f"    差异: min={cw_diff.min():,}  max={cw_diff.max():,}  mean={cw_diff.mean():.1f}")


def analyze_rates(our: pd.DataFrame, vendor: pd.DataFrame):
    """Task 5: 费率验证"""
    print_sep("5. 费率验证 - 逐条等效费率分析")

    for date in TARGET_DATES:
        for model in FOCUS_MODELS:
            o = our[(our["date"] == date) & (our["Model"] == model)].copy()
            v = vendor[(vendor["date"] == date) & (vendor["ModelName"] == model)].copy()
            if len(o) == 0 or len(v) == 0:
                continue

            print(f"\n--- {date} / {model} ---")

            # 我方等效费率 (各维度)
            o_total_tokens = o["Input Tokens"] + o["Output Tokens"]
            o_nonzero = o_total_tokens > 0
            if o_nonzero.sum() > 0:
                o_rate = o.loc[o_nonzero, "Billed USD"] / o_total_tokens[o_nonzero] * 1_000_000
                print(f"  我方等效费率 ($/M, Billed / (Input+Output)):")
                print(f"    min={o_rate.min():.4f}  max={o_rate.max():.4f}  mean={o_rate.mean():.4f}  median={o_rate.median():.4f}")

                # 分 input-only 和 output-only
                o_input_rate = o.loc[o["Input Tokens"] > 0, "Billed USD"] / o.loc[o["Input Tokens"] > 0, "Input Tokens"] * 1_000_000
                # 不太对，应该分拆 input/output 费用

            # 供应商等效费率
            v_nonzero = v["TotalTokens"] > 0
            if v_nonzero.sum() > 0:
                v_rate = v.loc[v_nonzero, "TotalPrice"] / v.loc[v_nonzero, "TotalTokens"] * 1_000_000
                print(f"  供应商等效费率 ($/M, TotalPrice / TotalTokens):")
                print(f"    min={v_rate.min():.4f}  max={v_rate.max():.4f}  mean={v_rate.mean():.4f}  median={v_rate.median():.4f}")

            # 供应商分项费率
            v_input_nz = v["InputTokens"] > 0
            if v_input_nz.sum() > 0:
                v_input_rate = v.loc[v_input_nz, "InputPrice"] / v.loc[v_input_nz, "InputTokens"] * 1_000_000
                print(f"  供应商 Input 费率 ($/M, InputPrice / InputTokens):")
                print(f"    min={v_input_rate.min():.4f}  max={v_input_rate.max():.4f}  mean={v_input_rate.mean():.4f}  median={v_input_rate.median():.4f}")

            v_output_nz = v["OutputTokens"] > 0
            if v_output_nz.sum() > 0:
                v_output_rate = v.loc[v_output_nz, "OutputPrice"] / v.loc[v_output_nz, "OutputTokens"] * 1_000_000
                print(f"  供应商 Output 费率 ($/M, OutputPrice / OutputTokens):")
                print(f"    min={v_output_rate.min():.4f}  max={v_output_rate.max():.4f}  mean={v_output_rate.mean():.4f}  median={v_output_rate.median():.4f}")

            v_cache_create_nz = v["CreateCacheTokens"] > 0
            if v_cache_create_nz.sum() > 0:
                v_cc_rate = v.loc[v_cache_create_nz, "CreateCachePrice"] / v.loc[v_cache_create_nz, "CreateCacheTokens"] * 1_000_000
                print(f"  供应商 CacheCreate 费率 ($/M):")
                print(f"    min={v_cc_rate.min():.4f}  max={v_cc_rate.max():.4f}  mean={v_cc_rate.mean():.4f}  median={v_cc_rate.median():.4f}")

            v_cache_read_nz = v["ReadCacheTokens"] > 0
            if v_cache_read_nz.sum() > 0:
                v_cr_rate = v.loc[v_cache_read_nz, "ReadCachePrice"] / v.loc[v_cache_read_nz, "ReadCacheTokens"] * 1_000_000
                print(f"  供应商 CacheRead 费率 ($/M):")
                print(f"    min={v_cr_rate.min():.4f}  max={v_cr_rate.max():.4f}  mean={v_cr_rate.mean():.4f}  median={v_cr_rate.median():.4f}")

            # 计算供应商等效 input 总费用 (input + cache)
            if len(v) > 0:
                v_input_total_cost = v["InputPrice"].sum() + v["CreateCachePrice"].sum() + v["ReadCachePrice"].sum()
                v_input_total_tokens = v["InputTokens"].sum() + v["CreateCacheTokens"].sum() + v["ReadCacheTokens"].sum()
                if v_input_total_tokens > 0:
                    v_blended_input_rate = v_input_total_cost / v_input_total_tokens * 1_000_000
                    print(f"  供应商 Input 侧混合费率 (Input+Cache全算): ${v_blended_input_rate:.4f}/M")

            # 我方费率拆解 - 用已知费率反推
            if len(o) > 0:
                total_billed = o["Billed USD"].sum()
                total_input = int(o["Input Tokens"].sum())
                total_output = int(o["Output Tokens"].sum())
                total_cache_hit = int(o["Cache Hit Tokens"].sum())
                print(f"\n  我方合计: Billed=${total_billed:.4f}  Input={total_input:,}  Output={total_output:,}  CacheHit={total_cache_hit:,}")


def deep_rate_analysis(our: pd.DataFrame, vendor: pd.DataFrame):
    """深度费率分析: 还原我方的定价逻辑"""
    print_sep("6. 深度费率分析 - 还原我方定价逻辑")

    # Anthropic 官方价格 (不降档)
    PRICES = {
        "claude-opus-4-6": {
            "input_low": 15.0,   # $/M, <=200K
            "input_high": 30.0,  # $/M, >200K
            "output": 75.0,
            "cache_read": 1.5,
            "cache_write": 18.75,
        },
        "claude-sonnet-4-6": {
            "input_low": 3.0,
            "input_high": 6.0,
            "output": 15.0,
            "cache_read": 0.30,
            "cache_write": 3.75,
        },
    }

    for date in TARGET_DATES:
        for model in FOCUS_MODELS:
            if model not in PRICES:
                continue
            o = our[(our["date"] == date) & (our["Model"] == model)].copy()
            if len(o) == 0:
                continue

            p = PRICES[model]
            print(f"\n--- {date} / {model} ---")
            print(f"  官方价格: Input(low)=${p['input_low']}/M  Input(high)=${p['input_high']}/M  Output=${p['output']}/M")
            print(f"            CacheRead=${p['cache_read']}/M  CacheWrite=${p['cache_write']}/M")

            # 按官方低档价重算
            recalc_low = (
                o["Input Tokens"] * p["input_low"] / 1e6
                + o["Output Tokens"] * p["output"] / 1e6
                + o["Cache Hit Tokens"] * p["cache_read"] / 1e6
                + o["Cache Write Tokens"] * p["cache_write"] / 1e6
            )
            print(f"  按低档价重算总额: ${recalc_low.sum():.4f}")
            print(f"  我方实际计费总额: ${o['Billed USD'].sum():.4f}")
            if recalc_low.sum() > 0:
                print(f"  差异比: {(o['Billed USD'].sum() - recalc_low.sum()) / recalc_low.sum() * 100:+.2f}%")

            # 逐条检验
            diff_pct = (o["Billed USD"] - recalc_low) / recalc_low.clip(lower=1e-10) * 100
            exact = (diff_pct.abs() < 0.1).sum()
            close = (diff_pct.abs() < 1).sum()
            print(f"  逐条匹配 (低档价): 精确(<0.1%)={exact:,}  近似(<1%)={close:,}  总={len(o):,}")

            # 尝试用 Quota/500000 还原
            recalc_quota = o["Quota"] / 500000.0
            diff_q = (o["Billed USD"] - recalc_quota).abs()
            quota_exact = (diff_q < 0.000001).sum()
            print(f"  Billed USD == Quota/500000: {quota_exact:,} / {len(o):,}")


def reconcile_pricing(our: pd.DataFrame, vendor: pd.DataFrame):
    """计费对比: 用供应商分项费用还原对比"""
    print_sep("7. 供应商分项定价验证")

    for date in TARGET_DATES:
        for model in FOCUS_MODELS:
            v = vendor[(vendor["date"] == date) & (vendor["ModelName"] == model)].copy()
            if len(v) == 0:
                continue

            print(f"\n--- {date} / {model} ---")

            # 供应商各项
            print(f"  供应商费用分项:")
            print(f"    InputPrice:       ${v['InputPrice'].sum():.6f}")
            print(f"    OutputPrice:      ${v['OutputPrice'].sum():.6f}")
            print(f"    CreateCachePrice: ${v['CreateCachePrice'].sum():.6f}")
            print(f"    ReadCachePrice:   ${v['ReadCachePrice'].sum():.6f}")
            print(f"    TotalPrice:       ${v['TotalPrice'].sum():.6f}")

            calc_total = v['InputPrice'].sum() + v['OutputPrice'].sum() + v['CreateCachePrice'].sum() + v['ReadCachePrice'].sum()
            print(f"    分项之和:          ${calc_total:.6f}")
            print(f"    差异:              ${v['TotalPrice'].sum() - calc_total:.6f}")

            # 验证 TotalTokens 构成
            v_total_calc = v["InputTokens"] + v["OutputTokens"] + v["CreateCacheTokens"] + v["ReadCacheTokens"]
            match = (v_total_calc == v["TotalTokens"]).sum()
            print(f"\n  TotalTokens = Input+Output+CreateCache+ReadCache: {match:,} / {len(v):,}")

            mismatch = v_total_calc != v["TotalTokens"]
            if mismatch.sum() > 0:
                # 尝试其他组合
                v_total_calc2 = v["InputTokens"] + v["OutputTokens"]
                match2 = (v_total_calc2 == v["TotalTokens"]).sum()
                print(f"  TotalTokens = Input+Output (不含Cache): {match2:,} / {len(v):,}")

                v_total_calc3 = v["InputTokens"] + v["OutputTokens"] + v["ReadCacheTokens"]
                match3 = (v_total_calc3 == v["TotalTokens"]).sum()
                print(f"  TotalTokens = Input+Output+ReadCache: {match3:,} / {len(v):,}")


def cost_comparison(our: pd.DataFrame, vendor: pd.DataFrame):
    """最终费用对比汇总"""
    print_sep("8. 最终费用对比汇总 (3/10 + 3/11)")

    rows = []
    for date in TARGET_DATES:
        for model in FOCUS_MODELS:
            o = our[(our["date"] == date) & (our["Model"] == model)]
            v = vendor[(vendor["date"] == date) & (vendor["ModelName"] == model)]

            o_billed = o["Billed USD"].sum() if len(o) else 0
            v_total = v["TotalPrice"].sum() if len(v) else 0
            v_input_cost = (v["InputPrice"].sum() + v["CreateCachePrice"].sum() + v["ReadCachePrice"].sum()) if len(v) else 0
            v_output_cost = v["OutputPrice"].sum() if len(v) else 0

            rows.append({
                "Date": date,
                "Model": model,
                "我方记录数": len(o),
                "供应商记录数": len(v),
                "记录差": len(o) - len(v),
                "我方 Billed USD": round(o_billed, 4),
                "供应商 TotalPrice": round(v_total, 4),
                "差额 USD": round(o_billed - v_total, 4),
                "差异%": round((o_billed - v_total) / v_total * 100 if v_total else 0, 2),
                "供应商 Input侧费用": round(v_input_cost, 4),
                "供应商 Output费用": round(v_output_cost, 4),
            })

    df = pd.DataFrame(rows)
    print(df.to_string(index=False))

    # 总计
    total_ours = df["我方 Billed USD"].sum()
    total_vendor = df["供应商 TotalPrice"].sum()
    print(f"\n  两天合计: 我方=${total_ours:.4f}  供应商=${total_vendor:.4f}  差=${total_ours-total_vendor:.4f} ({(total_ours-total_vendor)/total_vendor*100:+.2f}%)")


def main():
    print("加载我方数据...")
    our = load_our_data()
    print(f"  我方 3/10+3/11 记录数: {len(our):,}")

    print("加载供应商数据...")
    vendor = load_vendor_data()
    print(f"  供应商 3/10+3/11 记录数: {len(vendor):,}")

    analyze_records(our, vendor)
    analyze_token_distribution(our, vendor)
    try_match_records(our, vendor)
    analyze_token_calibration(our, vendor)
    analyze_rates(our, vendor)
    deep_rate_analysis(our, vendor)
    reconcile_pricing(our, vendor)
    cost_comparison(our, vendor)


if __name__ == "__main__":
    main()
