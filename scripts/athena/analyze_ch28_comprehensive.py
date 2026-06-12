"""
渠道 28 综合对账脚本：合并 Athena + DB 数据，与 UniAIX 供应商对比
"""

import pandas as pd
import numpy as np
import zipfile
import json
from pathlib import Path
from datetime import date

OUTPUT_DIR = Path("output")

ATHENA_FILE = OUTPUT_DIR / "bill_2026-03_ch28_flattier_detail.xlsx"
DB_NO_FLAT_ZIP = OUTPUT_DIR / "bill_2026-01_ch28_ch28_supplier_detail.csv.zip"
DB_312_FLAT_ZIP = OUTPUT_DIR / "bill_2026-01_ch28_ch28_flattier_since_20260312_supplier_detail.csv.zip"
SUPPLIER_FILE = Path(r"c:\Users\Administrator\xwechat_files\wxid_8zd2avj7cixo22_b66d\msg\file\2026-05\uniaix_logs(2).xlsx")


def read_zip_csv(zip_path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path, "r") as zf:
        csv_name = zf.namelist()[0]
        with zf.open(csv_name) as f:
            return pd.read_csv(f)


def load_all():
    print("=" * 70)
    print("Loading data...")
    print("=" * 70)

    athena = pd.read_excel(ATHENA_FILE, header=1)
    athena = athena.dropna(subset=["Time (UTC+8)"])
    print(f"  Athena:  {len(athena):,} rows")

    db_nf = read_zip_csv(DB_NO_FLAT_ZIP)
    print(f"  DB (no flat): {len(db_nf):,} rows")

    db312 = read_zip_csv(DB_312_FLAT_ZIP)
    print(f"  DB (312 flat): {len(db312):,} rows")

    sup = pd.read_excel(SUPPLIER_FILE)
    print(f"  Supplier: {len(sup):,} rows")

    # Parse dates
    athena["date"] = pd.to_datetime(athena["Time (UTC+8)"]).dt.date
    db_nf["date"] = pd.to_datetime(db_nf["Time (UTC+8)"]).dt.date
    db312["date"] = pd.to_datetime(db312["Time (UTC+8)"]).dt.date
    sup["date"] = pd.to_datetime(sup["Date"]).dt.date

    return athena, db_nf, db312, sup


def part1_completeness(athena, db_nf, sup):
    """数据完整性分析"""
    print("\n" + "=" * 70)
    print("1. DATA COMPLETENESS")
    print("=" * 70)

    mar1, mar31, mar25 = date(2026, 3, 1), date(2026, 3, 31), date(2026, 3, 25)

    db_mar = db_nf[(db_nf["date"] >= mar1) & (db_nf["date"] <= mar31)]
    db_mar25 = db_nf[(db_nf["date"] >= mar1) & (db_nf["date"] <= mar25)]
    sup_mar = sup[(sup["date"] >= mar1) & (sup["date"] <= mar31)]

    print(f"\n  Athena 3月: {len(athena):,} (range {athena['date'].min()} ~ {athena['date'].max()})")
    print(f"  DB 3月: {len(db_mar):,} (from full DB {len(db_nf):,})")
    print(f"  DB 3/1~3/25: {len(db_mar25):,}")
    print(f"  Supplier 3月: {len(sup_mar):,}")

    # Daily breakdown
    athena_daily = athena.groupby("date").size().reset_index(name="athena")
    db_daily = db_mar.groupby("date").size().reset_index(name="db")
    sup_daily = sup_mar.groupby("date").size().reset_index(name="supplier")

    daily = pd.merge(db_daily, athena_daily, on="date", how="outer")
    daily = pd.merge(daily, sup_daily, on="date", how="outer")
    daily = daily.fillna(0).astype({"db": int, "athena": int, "supplier": int})
    daily = daily.sort_values("date").reset_index(drop=True)

    print(f"\n  {'Date':<12} {'DB':>6} {'Athena':>8} {'Supplier':>10} {'Athena Gap':>12}")
    print("  " + "-" * 50)

    missing_dates = []
    partial_dates = []
    for _, r in daily.iterrows():
        gap = int(r["db"] - r["athena"])
        marker = ""
        if r["athena"] == 0 and r["db"] > 0:
            marker = " << MISSING"
            missing_dates.append(str(r["date"]))
        elif gap > 10 and r["athena"] > 0:
            marker = " < partial"
            partial_dates.append(str(r["date"]))
        print(f"  {r['date']}  {int(r['db']):>6} {int(r['athena']):>8} {int(r['supplier']):>10} {gap:>+12}{marker}")

    print(f"\n  Athena 完全缺失: {missing_dates}")
    print(f"  Athena 部分缺失: {partial_dates}")

    return daily, missing_dates


def part2_reconcile(db312, db_nf, sup):
    """对账: 312降档 + 不降档 vs 供应商"""
    print("\n" + "=" * 70)
    print("2. RECONCILIATION (3/1 ~ 3/25)")
    print("=" * 70)

    start, end = date(2026, 3, 1), date(2026, 3, 25)

    d312 = db312[(db312["date"] >= start) & (db312["date"] <= end)].copy()
    dnf = db_nf[(db_nf["date"] >= start) & (db_nf["date"] <= end)].copy()
    s = sup[(sup["date"] >= start) & (sup["date"] <= end)].copy()

    # Filter supplier to Claude only
    s_claude = s[s["ModelName"].str.contains("claude", case=False, na=False)].copy()

    print(f"\n  DB-312: {len(d312):,} | DB-NF: {len(dnf):,} | Supplier(all): {len(s):,} | Supplier(Claude): {len(s_claude):,}")

    # Summarize by model
    def summarize_db(df, prefix):
        return df.groupby("Model").agg(**{
            f"{prefix}_count": ("date", "count"),
            f"{prefix}_input": ("Input Tokens", "sum"),
            f"{prefix}_output": ("Output Tokens", "sum"),
            f"{prefix}_cost": ("List Price USD", "sum"),
        }).reset_index().rename(columns={"Model": "model"})

    sum312 = summarize_db(d312, "d312")
    sum_nf = summarize_db(dnf, "dnf")

    sum_sup = s_claude.groupby("ModelName").agg(
        sup_count=("date", "count"),
        sup_input=("InputTokens", "sum"),
        sup_output=("OutputTokens", "sum"),
        sup_cost=("TotalPrice", "sum"),
        sup_cache_create=("CreateCacheTokens", "sum"),
        sup_cache_read=("ReadCacheTokens", "sum"),
        sup_cache_create_price=("CreateCachePrice", "sum"),
        sup_cache_read_price=("ReadCachePrice", "sum"),
    ).reset_index().rename(columns={"ModelName": "model"})

    m = pd.merge(sum312, sum_sup, on="model", how="outer")
    m = pd.merge(m, sum_nf, on="model", how="outer")
    m = m.fillna(0).sort_values("sup_cost", ascending=False)

    m["diff312"] = m["d312_cost"] - m["sup_cost"]
    m["pct312"] = np.where(m["sup_cost"] != 0, m["diff312"] / m["sup_cost"] * 100, 0)
    m["diff_nf"] = m["dnf_cost"] - m["sup_cost"]
    m["pct_nf"] = np.where(m["sup_cost"] != 0, m["diff_nf"] / m["sup_cost"] * 100, 0)
    m["input_pct"] = np.where(m["sup_input"] != 0, (m["d312_input"] - m["sup_input"]) / m["sup_input"] * 100, 0)
    m["output_pct"] = np.where(m["sup_output"] != 0, (m["d312_output"] - m["sup_output"]) / m["sup_output"] * 100, 0)

    print(f"\n  {'Model':<35} {'Ours':>7} {'Sup':>7}  {'312Cost':>9} {'SupCost':>9} {'312Diff':>9} {'312%':>7}  {'NFCost':>9} {'NF%':>7}")
    print("  " + "-" * 110)
    for _, r in m.iterrows():
        print(f"  {r['model']:<35} {int(r['d312_count']):>7,} {int(r['sup_count']):>7,}  "
              f"${r['d312_cost']:>8,.2f} ${r['sup_cost']:>8,.2f} ${r['diff312']:>+8,.2f} {r['pct312']:>+6.1f}%  "
              f"${r['dnf_cost']:>8,.2f} {r['pct_nf']:>+6.1f}%")

    t312 = m["d312_cost"].sum()
    tnf = m["dnf_cost"].sum()
    tsup = m["sup_cost"].sum()
    print("  " + "-" * 110)
    print(f"  {'TOTAL':<35} {int(m['d312_count'].sum()):>7,} {int(m['sup_count'].sum()):>7,}  "
          f"${t312:>8,.2f} ${tsup:>8,.2f} ${t312 - tsup:>+8,.2f} {(t312 - tsup) / tsup * 100:>+6.1f}%  "
          f"${tnf:>8,.2f} {(tnf - tsup) / tsup * 100:>+6.1f}%")

    print(f"\n  Token comparison:")
    print(f"  {'Model':<35} {'OurInput':>14} {'SupInput':>14} {'In%':>7} {'OurOutput':>14} {'SupOutput':>14} {'Out%':>7}")
    print("  " + "-" * 100)
    for _, r in m.iterrows():
        if r["sup_count"] > 0:
            print(f"  {r['model']:<35} {int(r['d312_input']):>14,} {int(r['sup_input']):>14,} {r['input_pct']:>+6.1f}% "
                  f"{int(r['d312_output']):>14,} {int(r['sup_output']):>14,} {r['output_pct']:>+6.1f}%")

    print(f"\n  Supplier cache breakdown:")
    for _, r in m.iterrows():
        cc, cr = int(r["sup_cache_create"]), int(r["sup_cache_read"])
        ccp, crp = r["sup_cache_create_price"], r["sup_cache_read_price"]
        if cc > 0 or cr > 0:
            print(f"  {r['model']:<35} Create: {cc:>12,} (${ccp:>8,.2f})  Read: {cr:>12,} (${crp:>8,.2f})  Total: ${ccp + crp:>8,.2f}")

    return m, {"d312": t312, "dnf": tnf, "sup": tsup}


def save_json(m, daily, missing_dates, totals, athena_count, db_mar_count, sup_mar_count):
    """Save results as JSON for Canvas consumption"""
    result = {
        "completeness": {
            "athena_count": athena_count,
            "db_march_count": db_mar_count,
            "supplier_march_count": sup_mar_count,
            "missing_dates": missing_dates,
            "daily": [
                {"date": str(r["date"]), "db": int(r["db"]), "athena": int(r["athena"]), "supplier": int(r["supplier"])}
                for _, r in daily.iterrows()
            ],
        },
        "models": [],
        "totals": {
            "d312": round(totals["d312"], 2),
            "dnf": round(totals["dnf"], 2),
            "sup": round(totals["sup"], 2),
            "diff312": round(totals["d312"] - totals["sup"], 2),
            "pct312": round((totals["d312"] - totals["sup"]) / totals["sup"] * 100, 1),
            "diff_nf": round(totals["dnf"] - totals["sup"], 2),
            "pct_nf": round((totals["dnf"] - totals["sup"]) / totals["sup"] * 100, 1),
        },
    }

    for _, r in m.iterrows():
        result["models"].append({
            "model": r["model"],
            "d312_count": int(r["d312_count"]),
            "sup_count": int(r["sup_count"]),
            "d312_cost": round(float(r["d312_cost"]), 2),
            "dnf_cost": round(float(r["dnf_cost"]), 2),
            "sup_cost": round(float(r["sup_cost"]), 2),
            "diff312": round(float(r["diff312"]), 2),
            "pct312": round(float(r["pct312"]), 1),
            "diff_nf": round(float(r["diff_nf"]), 2),
            "pct_nf": round(float(r["pct_nf"]), 1),
            "d312_input": int(r["d312_input"]),
            "sup_input": int(r["sup_input"]),
            "input_pct": round(float(r["input_pct"]), 1),
            "d312_output": int(r["d312_output"]),
            "sup_output": int(r["sup_output"]),
            "output_pct": round(float(r["output_pct"]), 1),
            "sup_cache_create": int(r["sup_cache_create"]),
            "sup_cache_read": int(r["sup_cache_read"]),
            "sup_cache_create_price": round(float(r["sup_cache_create_price"]), 2),
            "sup_cache_read_price": round(float(r["sup_cache_read_price"]), 2),
        })

    out = OUTPUT_DIR / "ch28_comprehensive_reconciliation.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved: {out}")
    return result


def main():
    athena, db_nf, db312, sup = load_all()

    daily, missing_dates = part1_completeness(athena, db_nf, sup)

    m, totals = part2_reconcile(db312, db_nf, sup)

    mar1, mar31 = date(2026, 3, 1), date(2026, 3, 31)
    db_mar_count = int(len(db_nf[(db_nf["date"] >= mar1) & (db_nf["date"] <= mar31)]))
    sup_mar_count = int(len(sup[(sup["date"] >= mar1) & (sup["date"] <= mar31)]))
    result = save_json(m, daily, missing_dates, totals, len(athena), db_mar_count, sup_mar_count)

    print("\n" + "=" * 70)
    print("3. SUMMARY")
    print("=" * 70)
    t = result["totals"]
    print(f"\n  312-flat: ${t['d312']:,.2f} vs Supplier ${t['sup']:,.2f} -> diff ${t['diff312']:+,.2f} ({t['pct312']:+.1f}%)")
    print(f"  No-flat:  ${t['dnf']:,.2f} vs Supplier ${t['sup']:,.2f} -> diff ${t['diff_nf']:+,.2f} ({t['pct_nf']:+.1f}%)")
    print(f"  Flat impact: ${t['d312'] - t['dnf']:+,.2f}")


if __name__ == "__main__":
    main()
