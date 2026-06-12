"""
渠道 28 三月完整数据聚合与供应商对账（最终确定版）

关键发现:
  - DB "Billed USD" = Quota/500000 = 系统原始扣费（含分段高价）
  - DB "Expected USD" = 312降档后重算价
  - Athena "Billed USD" = Quota/500000 = 系统原始扣费
  - 两个数据源的 Billed USD 在重叠区间完全一致

对账方式:
  1. 系统原价对比: 用 Billed USD（Quota/500000）vs 供应商
  2. 312降档价对比: 用 DB Expected USD（3/12前原价, 3/12后降档）vs 供应商

聚合方案: DB 3/1~3/25 + Athena 3/26~3/31
"""
import pandas as pd
import numpy as np
import zipfile
import datetime
import json

DB_ZIP = "output/bill_2026-01_ch28_ch28_flattier_since_20260312_supplier_detail.csv.zip"
ATH_EXCEL = "output/bill_2026-03_ch28_flattier_detail.xlsx"
VENDOR_EXCEL = r"c:\Users\Administrator\xwechat_files\wxid_8zd2avj7cixo22_b66d\msg\file\2026-05\uniaix_logs(2).xlsx"


def load():
    with zipfile.ZipFile(DB_ZIP) as z:
        with z.open(z.namelist()[0]) as f:
            db = pd.read_csv(f, encoding="utf-8-sig")
    db["date"] = pd.to_datetime(db["Time (UTC+8)"]).dt.date
    for c in ["Billed USD", "Expected USD", "List Price USD", "Input Tokens", "Output Tokens", "Quota"]:
        db[c] = pd.to_numeric(db[c], errors="coerce").fillna(0)

    ath = pd.read_excel(ATH_EXCEL, header=1)
    ath["date"] = pd.to_datetime(ath["Time (UTC+8)"]).dt.date
    for c in ["Billed USD", "Expected USD", "List Price USD", "Input Tokens", "Output Tokens", "Quota"]:
        ath[c] = pd.to_numeric(ath[c], errors="coerce").fillna(0)

    vendor = pd.read_excel(VENDOR_EXCEL)
    vendor["date"] = pd.to_datetime(vendor["Date"]).dt.date
    return db, ath, vendor


def main():
    db, ath, vendor = load()

    MAR1 = datetime.date(2026, 3, 1)
    MAR11 = datetime.date(2026, 3, 11)
    MAR12 = datetime.date(2026, 3, 12)
    MAR25 = datetime.date(2026, 3, 25)
    MAR26 = datetime.date(2026, 3, 26)
    MAR31 = datetime.date(2026, 3, 31)

    db_mar = db[(db["date"] >= MAR1) & (db["date"] <= MAR25)].copy()
    ath_tail = ath[(ath["date"] >= MAR26) & (ath["date"] <= MAR31)].copy()
    v_mar = vendor[(vendor["date"] >= MAR1) & (vendor["date"] <= MAR31)].copy()
    v_1_25 = v_mar[v_mar["date"] <= MAR25]

    print("=" * 80)
    print("渠道 28 三月完整数据 — 聚合对账（最终确定版）")
    print("=" * 80)

    # ===== 1. Data overview =====
    print("\n## 1. 数据概况")
    print(f"  DB 3/1~3/25:     {len(db_mar):>6} rows")
    print(f"  Athena 3/26~3/31: {len(ath_tail):>4} rows")
    print(f"  聚合:             {len(db_mar) + len(ath_tail):>6} rows")
    print(f"  供应商 3月:       {len(v_mar):>6} rows")
    print(f"  行数差:           {len(db_mar) + len(ath_tail) - len(v_mar):>6} (缺 gemini 等模型)")

    # ===== 2. Cross-validation =====
    print("\n## 2. 交叉验证 (3/12~3/25)")
    db_ov = db_mar[(db_mar["date"] >= MAR12) & (db_mar["date"] <= MAR25)]
    ath_ov = ath[(ath["date"] >= MAR12) & (ath["date"] <= MAR25)]
    diff_rows = len(db_ov) - len(ath_ov)
    diff_usd = db_ov["Billed USD"].sum() - ath_ov["Billed USD"].sum()
    print(f"  DB={len(db_ov)} rows, Athena={len(ath_ov)} rows (行数差 {diff_rows})")
    print(f"  Billed USD: DB=${db_ov['Billed USD'].sum():.4f}, Athena=${ath_ov['Billed USD'].sum():.4f}")
    print(f"  金额差: ${diff_usd:.6f} ({'完全一致' if abs(diff_usd) < 0.01 else '有差异'})")

    # ===== 3. Merge & Compare: System Price (Billed USD = Quota/500000) =====
    print("\n## 3. 方案一: 系统原价 (不降档) vs 供应商")

    # Combine DB Billed + Athena Billed (note: Athena tail Billed=0 for monitoring)
    merged_billed = pd.concat([
        db_mar[["Model", "Billed USD", "Input Tokens", "Output Tokens"]].assign(source="DB"),
        ath_tail[["Model", "Billed USD", "Input Tokens", "Output Tokens"]].assign(source="Athena"),
    ], ignore_index=True)

    our_model_billed = merged_billed.groupby("Model").agg(
        count=("Model", "size"),
        our_usd=("Billed USD", "sum"),
        our_input=("Input Tokens", "sum"),
        our_output=("Output Tokens", "sum"),
    ).reset_index().rename(columns={"Model": "model"})

    vnd_model = v_mar.groupby("ModelName").agg(
        count=("ModelName", "size"),
        vnd_usd=("TotalPrice", "sum"),
        vnd_input=("InputTokens", "sum"),
        vnd_output=("OutputTokens", "sum"),
    ).reset_index().rename(columns={"ModelName": "model"})

    cmp1 = pd.merge(our_model_billed, vnd_model, on="model", how="outer", suffixes=("_our", "_vnd")).fillna(0)
    cmp1["diff"] = cmp1["our_usd"] - cmp1["vnd_usd"]
    cmp1["pct"] = np.where(cmp1["vnd_usd"] > 0, cmp1["diff"] / cmp1["vnd_usd"] * 100, 0)
    cmp1 = cmp1.sort_values("vnd_usd", ascending=False)

    print(f"  {'Model':<35} {'Our#':>6} {'Vnd#':>7} {'Our$':>12} {'Vnd$':>12} {'Diff$':>12} {'%':>8}")
    print("  " + "-" * 96)
    for _, r in cmp1.iterrows():
        co = int(r["count_our"])
        cv = int(r["count_vnd"])
        print(f"  {r['model']:<35} {co:>6} {cv:>7} "
              f"${r['our_usd']:>11.4f} ${r['vnd_usd']:>11.4f} "
              f"${r['diff']:>11.4f} {r['pct']:>+7.2f}%")

    ot1 = cmp1["our_usd"].sum()
    vt1 = cmp1["vnd_usd"].sum()
    print("  " + "-" * 96)
    oc1 = int(cmp1["count_our"].sum())
    vc1 = int(cmp1["count_vnd"].sum())
    print(f"  {'TOTAL':<35} {oc1:>6} {vc1:>7} "
          f"${ot1:>11.4f} ${vt1:>11.4f} "
          f"${ot1 - vt1:>11.4f} {(ot1 - vt1) / vt1 * 100:>+7.2f}%")

    # ===== 4. Merge & Compare: 312 Flat-tier (Expected USD) =====
    print("\n## 4. 方案二: 312降档 vs 供应商")

    # DB: use Expected USD (3/1-3/11 same as Billed, 3/12-3/25 flat-tier)
    # Athena tail: use Expected USD (flat-tier, but these are ~$0 monitoring requests)
    merged_expected = pd.concat([
        db_mar[["Model", "Expected USD", "Billed USD", "Input Tokens", "Output Tokens"]].rename(
            columns={"Expected USD": "flattier_usd"}
        ),
        ath_tail[["Model", "Expected USD", "Billed USD", "Input Tokens", "Output Tokens"]].rename(
            columns={"Expected USD": "flattier_usd"}
        ),
    ], ignore_index=True)

    our_model_ft = merged_expected.groupby("Model").agg(
        count=("Model", "size"),
        our_usd=("flattier_usd", "sum"),
        our_billed=("Billed USD", "sum"),
    ).reset_index().rename(columns={"Model": "model"})

    cmp2 = pd.merge(our_model_ft, vnd_model[["model", "count", "vnd_usd"]], on="model",
                     how="outer", suffixes=("_our", "_vnd")).fillna(0)
    cmp2["diff"] = cmp2["our_usd"] - cmp2["vnd_usd"]
    cmp2["pct"] = np.where(cmp2["vnd_usd"] > 0, cmp2["diff"] / cmp2["vnd_usd"] * 100, 0)
    cmp2["billed_diff"] = cmp2["our_billed"] - cmp2["vnd_usd"]
    cmp2 = cmp2.sort_values("vnd_usd", ascending=False)

    print(f"  {'Model':<35} {'Billed$':>12} {'312FT$':>12} {'Vnd$':>12} {'FT-Vnd':>12} {'%':>8}")
    print("  " + "-" * 96)
    for _, r in cmp2.iterrows():
        print(f"  {r['model']:<35} "
              f"${r['our_billed']:>11.4f} ${r['our_usd']:>11.4f} ${r['vnd_usd']:>11.4f} "
              f"${r['diff']:>11.4f} {r['pct']:>+7.2f}%")

    ot2 = cmp2["our_usd"].sum()
    bt2 = cmp2["our_billed"].sum()
    print("  " + "-" * 96)
    print(f"  {'TOTAL':<35} "
          f"${bt2:>11.4f} ${ot2:>11.4f} ${vt1:>11.4f} "
          f"${ot2 - vt1:>11.4f} {(ot2 - vt1) / vt1 * 100:>+7.2f}%")

    # ===== 5. Four-scheme comparison =====
    print("\n## 5. 四种方案汇总")

    # A: 不降档·仅DB (3/1~3/25) — Billed USD
    vnd_1_25 = v_1_25["TotalPrice"].sum()
    a_usd = db_mar["Billed USD"].sum()
    a_pct = (a_usd - vnd_1_25) / vnd_1_25 * 100

    # B: 312降档·仅DB (3/1~3/25) — Expected USD
    b_usd = db_mar["Expected USD"].sum()
    b_pct = (b_usd - vnd_1_25) / vnd_1_25 * 100

    # C: 不降档·聚合 (3/1~3/31) — Billed USD merged
    c_usd = ot1
    c_pct = (c_usd - vt1) / vt1 * 100

    # D: 312降档·聚合 (3/1~3/31) — Expected USD merged
    d_usd = ot2
    d_pct = (d_usd - vt1) / vt1 * 100

    print(f"\n  {'方案':<48} {'我方$':>14} {'供应商$':>14} {'差异$':>14} {'差异%':>8}")
    print("  " + "-" * 102)
    print(f"  {'A. 不降档·仅DB (3/1~3/25, 缺6天)':<48} ${a_usd:>13.4f} ${vnd_1_25:>13.4f} ${a_usd - vnd_1_25:>13.4f} {a_pct:>+7.2f}%")
    print(f"  {'B. 312降档·仅DB (3/1~3/25, 缺6天)':<48} ${b_usd:>13.4f} ${vnd_1_25:>13.4f} ${b_usd - vnd_1_25:>13.4f} {b_pct:>+7.2f}%")
    print(f"  {'C. 不降档·聚合 (3/1~3/31, 完整)':<48} ${c_usd:>13.4f} ${vt1:>13.4f} ${c_usd - vt1:>13.4f} {c_pct:>+7.2f}%")
    print(f"  {'D. 312降档·聚合 (3/1~3/31, 完整)':<48} ${d_usd:>13.4f} ${vt1:>13.4f} ${d_usd - vt1:>13.4f} {d_pct:>+7.2f}%")

    ft_effect = a_usd - b_usd
    print(f"\n  降档效果 (A→B): ${-ft_effect:.4f} ({-ft_effect / a_usd * 100:.2f}%)")
    print(f"  聚合增量 (A→C): ${c_usd - a_usd:.4f} (Athena补充的3/26~3/31基本为$0)")

    # ===== 6. Conclusion =====
    print("\n## 6. 结论")
    print(f"  ┌────────────────────────────────────────────────────┐")
    print(f"  │ 不降档对比 (方案C): 我方 ${c_usd:.2f} vs 供应商 ${vt1:.2f}  │")
    print(f"  │   差异: ${c_usd - vt1:.2f} ({c_pct:+.2f}%)                       │")
    print(f"  │                                                    │")
    print(f"  │ 312降档对比 (方案D): 我方 ${d_usd:.2f} vs 供应商 ${vt1:.2f}│")
    print(f"  │   差异: ${d_usd - vt1:.2f} ({d_pct:+.2f}%)                     │")
    print(f"  └────────────────────────────────────────────────────┘")
    print()
    print("  差异来源:")
    for _, r in cmp2.iterrows():
        if abs(r["diff"]) > 1:
            print(f"    {r['model']}: ${r['diff']:+.2f} ({r['pct']:+.1f}%)")
    print()
    print("  注意事项:")
    print("    - 我方缺少 gemini 系列模型 (占供应商 0.12%, $13.85)")
    print("    - 3/26~3/31 均为监控请求 (277行, $0.08), 对结果影响极小")
    print("    - opus-4-6 我方大幅低于供应商, sonnet-4-6 我方高于供应商")
    print("    - 定价差异核心在于分段计费逻辑不同")

    # Save
    results = {
        "schemes": [
            {"id": "A", "label": "不降档·仅DB", "scope": "3/1~3/25", "our": round(a_usd, 2), "vendor": round(vnd_1_25, 2), "diff": round(a_usd - vnd_1_25, 2), "pct": round(a_pct, 2)},
            {"id": "B", "label": "312降档·仅DB", "scope": "3/1~3/25", "our": round(b_usd, 2), "vendor": round(vnd_1_25, 2), "diff": round(b_usd - vnd_1_25, 2), "pct": round(b_pct, 2)},
            {"id": "C", "label": "不降档·聚合", "scope": "3/1~3/31", "our": round(c_usd, 2), "vendor": round(vt1, 2), "diff": round(c_usd - vt1, 2), "pct": round(c_pct, 2)},
            {"id": "D", "label": "312降档·聚合", "scope": "3/1~3/31", "our": round(d_usd, 2), "vendor": round(vt1, 2), "diff": round(d_usd - vt1, 2), "pct": round(d_pct, 2)},
        ],
        "by_model_system_price": [
            {"model": r["model"], "our_count": int(r["count_our"]), "vnd_count": int(r["count_vnd"]),
             "our_usd": round(float(r["our_usd"]), 2), "vnd_usd": round(float(r["vnd_usd"]), 2),
             "diff": round(float(r["diff"]), 2), "pct": round(float(r["pct"]), 2)}
            for _, r in cmp1.iterrows()
        ],
        "by_model_312ft": [
            {"model": r["model"],
             "billed_usd": round(float(r["our_billed"]), 2), "ft_usd": round(float(r["our_usd"]), 2),
             "vnd_usd": round(float(r["vnd_usd"]), 2),
             "diff": round(float(r["diff"]), 2), "pct": round(float(r["pct"]), 2)}
            for _, r in cmp2.iterrows()
        ],
        "totals": {
            "our_billed": round(bt2, 2), "our_312ft": round(ot2, 2),
            "vendor": round(vt1, 2),
            "billed_diff_pct": round(c_pct, 2), "ft_diff_pct": round(d_pct, 2),
            "our_rows": oc1, "vendor_rows": vc1,
        },
    }
    with open("output/ch28_march_definitive.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("\n  结果已保存到 output/ch28_march_definitive.json")


if __name__ == "__main__":
    main()
