"""
渠道28对账：按天对比差异分析
比较 DB 明细 vs 供应商明细，找出差异最大的时间段
"""

import zipfile
import pandas as pd
import numpy as np
from pathlib import Path

DB_ZIP = Path(r"e:\new-api\scripts\athena\output\bill_2026-01_ch28_ch28_supplier_detail.csv.zip")
SUPPLIER_FILE = Path(r"c:\Users\Administrator\xwechat_files\wxid_8zd2avj7cixo22_b66d\msg\file\2026-05\uniaix_logs(2).xlsx")

START_DATE = "2026-03-01"
END_DATE = "2026-03-25"


def load_db_data():
    with zipfile.ZipFile(DB_ZIP) as z:
        with z.open(z.namelist()[0]) as f:
            df = pd.read_csv(f)
    df["datetime"] = pd.to_datetime(df["Time (UTC+8)"])
    df["date"] = df["datetime"].dt.date
    df = df[(df["date"] >= pd.Timestamp(START_DATE).date()) &
            (df["date"] <= pd.Timestamp(END_DATE).date())]
    return df


def load_supplier_data():
    df = pd.read_excel(SUPPLIER_FILE)
    df["date"] = pd.to_datetime(df["Date"]).dt.date
    df = df[(df["date"] >= pd.Timestamp(START_DATE).date()) &
            (df["date"] <= pd.Timestamp(END_DATE).date())]
    # 只保留 Claude 模型（供应商同时有 Gemini）
    claude_mask = df["ModelName"].str.contains("claude", case=False, na=False)
    df = df[claude_mask].copy()
    return df


MODEL_MAP_SUPPLIER_TO_DB = {
    "claude-opus-4-5-20251101": "claude-opus-4-5-20251101",
    "claude-sonnet-4-5-20250929": "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
    "claude-sonnet-4-20250514": "claude-sonnet-4-20250514",
    "claude-opus-4-1-20250805": "claude-opus-4-1-20250805",
    "claude-opus-4-6": "claude-opus-4-6",
    "claude-sonnet-4-6": "claude-sonnet-4-6",
}


def normalize_model(name, source="db"):
    if source == "supplier":
        return MODEL_MAP_SUPPLIER_TO_DB.get(name, name)
    return name


def analyze_daily(db, supplier):
    """按天汇总对比"""
    db_daily = db.groupby("date").agg(
        db_count=("Billed USD", "count"),
        db_cost=("Billed USD", "sum"),
    ).reset_index()

    sup_daily = supplier.groupby("date").agg(
        sup_count=("TotalPrice", "count"),
        sup_cost=("TotalPrice", "sum"),
    ).reset_index()

    merged = pd.merge(db_daily, sup_daily, on="date", how="outer").fillna(0)
    merged["cost_diff"] = merged["db_cost"] - merged["sup_cost"]
    merged["cost_diff_abs"] = merged["cost_diff"].abs()
    merged["cost_diff_pct"] = np.where(
        merged["sup_cost"] > 0,
        (merged["cost_diff"] / merged["sup_cost"] * 100),
        np.where(merged["db_cost"] > 0, 100.0, 0.0)
    )
    merged["count_diff"] = merged["db_count"] - merged["sup_count"]
    merged = merged.sort_values("cost_diff_abs", ascending=False)
    return merged


def analyze_daily_model(db, supplier):
    """按天×模型交叉汇总"""
    db["model_norm"] = db["Model"].apply(lambda x: normalize_model(x, "db"))
    supplier["model_norm"] = supplier["ModelName"].apply(lambda x: normalize_model(x, "supplier"))

    db_dm = db.groupby(["date", "model_norm"]).agg(
        db_count=("Billed USD", "count"),
        db_cost=("Billed USD", "sum"),
        db_input_tokens=("Input Tokens", "sum"),
        db_output_tokens=("Output Tokens", "sum"),
    ).reset_index()

    sup_dm = supplier.groupby(["date", "model_norm"]).agg(
        sup_count=("TotalPrice", "count"),
        sup_cost=("TotalPrice", "sum"),
        sup_input_tokens=("InputTokens", "sum"),
        sup_output_tokens=("OutputTokens", "sum"),
    ).reset_index()

    merged = pd.merge(db_dm, sup_dm, on=["date", "model_norm"], how="outer").fillna(0)
    merged["cost_diff"] = merged["db_cost"] - merged["sup_cost"]
    merged["cost_diff_abs"] = merged["cost_diff"].abs()
    merged["cost_diff_pct"] = np.where(
        merged["sup_cost"] > 0,
        (merged["cost_diff"] / merged["sup_cost"] * 100),
        np.where(merged["db_cost"] > 0, 100.0, 0.0)
    )
    merged["count_diff"] = merged["db_count"] - merged["sup_count"]
    merged = merged.sort_values("cost_diff_abs", ascending=False)
    return merged


def analyze_top5_days(db, supplier, daily_diff):
    """对差异最大的 top 5 天，详细分析各模型 token 对比"""
    top5_dates = daily_diff.head(5)["date"].tolist()

    db["model_norm"] = db["Model"].apply(lambda x: normalize_model(x, "db"))
    supplier["model_norm"] = supplier["ModelName"].apply(lambda x: normalize_model(x, "supplier"))

    results = []
    for d in top5_dates:
        db_day = db[db["date"] == d]
        sup_day = supplier[supplier["date"] == d]

        db_models = db_day.groupby("model_norm").agg(
            db_count=("Billed USD", "count"),
            db_cost=("Billed USD", "sum"),
            db_input_tokens=("Input Tokens", "sum"),
            db_output_tokens=("Output Tokens", "sum"),
            db_cache_hit=("Cache Hit Tokens", "sum"),
        ).reset_index()

        sup_models = sup_day.groupby("model_norm").agg(
            sup_count=("TotalPrice", "count"),
            sup_cost=("TotalPrice", "sum"),
            sup_input_tokens=("InputTokens", "sum"),
            sup_output_tokens=("OutputTokens", "sum"),
            sup_cache_read=("ReadCacheTokens", "sum"),
            sup_cache_create=("CreateCacheTokens", "sum"),
        ).reset_index()

        merged = pd.merge(db_models, sup_models, on="model_norm", how="outer").fillna(0)
        merged["date"] = d
        merged["cost_diff"] = merged["db_cost"] - merged["sup_cost"]
        merged["input_token_diff"] = merged["db_input_tokens"] - merged["sup_input_tokens"]
        merged["output_token_diff"] = merged["db_output_tokens"] - merged["sup_output_tokens"]
        merged["input_token_diff_pct"] = np.where(
            merged["sup_input_tokens"] > 0,
            (merged["input_token_diff"] / merged["sup_input_tokens"] * 100),
            np.where(merged["db_input_tokens"] > 0, 100.0, 0.0)
        )
        merged["output_token_diff_pct"] = np.where(
            merged["sup_output_tokens"] > 0,
            (merged["output_token_diff"] / merged["sup_output_tokens"] * 100),
            np.where(merged["db_output_tokens"] > 0, 100.0, 0.0)
        )
        results.append(merged)

    return pd.concat(results, ignore_index=True)


def main():
    print("=" * 80)
    print("渠道28对账差异分析 (2026-03-01 ~ 2026-03-25)")
    print("=" * 80)

    print("\n加载数据...")
    db = load_db_data()
    supplier = load_supplier_data()
    print(f"  DB 记录数: {len(db)}")
    print(f"  供应商记录数 (仅Claude): {len(supplier)}")
    print(f"  DB 模型: {sorted(db['Model'].unique())}")
    print(f"  供应商模型: {sorted(supplier['ModelName'].unique())}")

    # === 1. 按天对比 ===
    print("\n" + "=" * 80)
    print("1. 按天对比（按差异金额排序）")
    print("=" * 80)
    daily = analyze_daily(db, supplier)
    pd.set_option("display.float_format", lambda x: f"{x:.4f}")
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.width", 200)
    print(daily.to_string(index=False))
    print(f"\n总计: DB费用=${daily['db_cost'].sum():.4f}, 供应商费用=${daily['sup_cost'].sum():.4f}, "
          f"差异=${daily['cost_diff'].sum():.4f}")

    # === 2. 按天+模型对比 ===
    print("\n" + "=" * 80)
    print("2. 按天+模型对比 (Top 20 差异组合)")
    print("=" * 80)
    daily_model = analyze_daily_model(db, supplier)
    print(daily_model.head(20)[["date", "model_norm", "db_count", "sup_count",
                                 "db_cost", "sup_cost", "cost_diff", "cost_diff_pct",
                                 "count_diff"]].to_string(index=False))

    # === 3. 按天+模型对比调用次数 ===
    print("\n" + "=" * 80)
    print("3. 调用次数差异最大的日期+模型组合 (Top 20)")
    print("=" * 80)
    count_diff = daily_model.copy()
    count_diff["count_diff_abs"] = count_diff["count_diff"].abs()
    count_diff = count_diff.sort_values("count_diff_abs", ascending=False)
    print(count_diff.head(20)[["date", "model_norm", "db_count", "sup_count",
                                "count_diff", "db_cost", "sup_cost",
                                "cost_diff"]].to_string(index=False))

    # 记录数不一致的天
    inconsistent_days = count_diff[count_diff["count_diff"] != 0]["date"].nunique()
    print(f"\n记录数不一致的天数: {inconsistent_days}/{daily['date'].nunique()}")

    # === 4. Top5天详细分析 ===
    print("\n" + "=" * 80)
    print("4. Top 5 差异最大天的详细 Token 分析")
    print("=" * 80)
    top5 = analyze_top5_days(db, supplier, daily)
    for d in top5["date"].unique():
        day_data = top5[top5["date"] == d]
        print(f"\n--- {d} ---")
        print(day_data[["model_norm", "db_count", "sup_count",
                        "db_cost", "sup_cost", "cost_diff",
                        "db_input_tokens", "sup_input_tokens", "input_token_diff", "input_token_diff_pct",
                        "db_output_tokens", "sup_output_tokens", "output_token_diff", "output_token_diff_pct",
                        "db_cache_hit", "sup_cache_read", "sup_cache_create",
                        ]].to_string(index=False))

    # === 5. 差异模式总结 ===
    print("\n" + "=" * 80)
    print("5. 差异模式总结")
    print("=" * 80)
    daily_sorted = daily.sort_values("date")
    high_diff_days = daily[daily["cost_diff_abs"] > daily["cost_diff_abs"].median()]
    print(f"总差异: ${daily['cost_diff'].sum():.4f}")
    print(f"平均每天差异: ${daily['cost_diff'].mean():.4f}")
    print(f"差异最大的5天贡献: ${daily.head(5)['cost_diff'].sum():.4f} "
          f"({daily.head(5)['cost_diff_abs'].sum() / daily['cost_diff_abs'].sum() * 100:.1f}%)")
    print(f"\n差异方向:")
    print(f"  DB > 供应商的天数: {(daily['cost_diff'] > 0.001).sum()}")
    print(f"  DB < 供应商的天数: {(daily['cost_diff'] < -0.001).sum()}")
    print(f"  基本一致的天数: {((daily['cost_diff'].abs()) <= 0.001).sum()}")

    # 按模型汇总总差异
    print(f"\n按模型汇总总差异:")
    model_total = daily_model.groupby("model_norm").agg(
        total_db_cost=("db_cost", "sum"),
        total_sup_cost=("sup_cost", "sum"),
        total_cost_diff=("cost_diff", "sum"),
        total_db_count=("db_count", "sum"),
        total_sup_count=("sup_count", "sum"),
    ).reset_index()
    model_total["diff_pct"] = np.where(
        model_total["total_sup_cost"] > 0,
        model_total["total_cost_diff"] / model_total["total_sup_cost"] * 100,
        100.0
    )
    model_total = model_total.sort_values("total_cost_diff", key=abs, ascending=False)
    print(model_total.to_string(index=False))


if __name__ == "__main__":
    main()
