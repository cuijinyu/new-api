"""
Generate March 2026 bill for Channel 38 (AIDerby).
Merge DB (3/1~3/11) + Athena (3/12~3/31), flat-tier since 3/12.

Output:
  - bill_2026-03_ch38_AIDerby_flattier_since_20260312.xlsx
  - bill_2026-03_ch38_AIDerby_flattier_since_20260312_detail.csv.zip
"""

import pandas as pd
import numpy as np
import zipfile
import io
import xlsxwriter
from pathlib import Path

OUTPUT_DIR = Path(r"e:\new-api\scripts\athena\output")
DB_FILE = OUTPUT_DIR / "bill_2026-02_ch38_AIDerby_flattier_since_20260312_supplier_detail.csv.zip"
ATHENA_FILE = OUTPUT_DIR / "bill_2026-03_ch38_flattier_detail.xlsx"

CHANNEL_ID = 38
CHANNEL_NAME = "AIDerby"
MONTH = "2026-03"
FLAT_TIER_SINCE = "2026-03-12"

HDR_COLOR = "#1F4E79"
ALT_COLOR = "#EBF3FB"

OUTPUT_XLSX = OUTPUT_DIR / f"bill_{MONTH}_ch{CHANNEL_ID}_{CHANNEL_NAME}_flattier_since_{FLAT_TIER_SINCE.replace('-', '')}.xlsx"
OUTPUT_CSV_ZIP = OUTPUT_DIR / f"bill_{MONTH}_ch{CHANNEL_ID}_{CHANNEL_NAME}_flattier_since_{FLAT_TIER_SINCE.replace('-', '')}_detail.csv.zip"


def load_and_merge():
    """Load DB (3/1~3/11) + Athena (3/12~3/31)."""
    print("加载 DB 明细 ...")
    with zipfile.ZipFile(DB_FILE) as z:
        with z.open(z.namelist()[0]) as f:
            db = pd.read_csv(f)
    db["Time (UTC+8)"] = pd.to_datetime(db["Time (UTC+8)"])
    db_march = db[
        (db["Time (UTC+8)"] >= "2026-03-01") & (db["Time (UTC+8)"] < "2026-03-12")
    ].copy()
    print(f"  DB 3/1~3/11: {len(db_march):,} 条")

    print("加载 Athena 明细 ...")
    ath = pd.read_excel(ATHENA_FILE, header=1)
    ath["Time (UTC+8)"] = pd.to_datetime(ath["Time (UTC+8)"])
    ath_post = ath[ath["Time (UTC+8)"] >= "2026-03-12"].copy()
    print(f"  Athena 3/12~3/31: {len(ath_post):,} 条")

    common_cols = [
        "Time (UTC+8)", "Channel ID", "Model", "Input Tokens", "Output Tokens",
        "Cache Hit Tokens", "Cache Write Tokens",
        "Billed USD", "List Price USD", "Use Time (s)", "Stream",
    ]
    for col in common_cols:
        if col not in db_march.columns:
            db_march[col] = 0
        if col not in ath_post.columns:
            ath_post[col] = 0

    merged = pd.concat([db_march[common_cols], ath_post[common_cols]], ignore_index=True)

    for c in ["Input Tokens", "Output Tokens", "Cache Hit Tokens", "Cache Write Tokens"]:
        merged[c] = pd.to_numeric(merged[c], errors="coerce").fillna(0).astype(int)
    for c in ["Billed USD", "List Price USD", "Use Time (s)"]:
        merged[c] = pd.to_numeric(merged[c], errors="coerce").fillna(0)
    merged["Channel ID"] = pd.to_numeric(merged["Channel ID"], errors="coerce").fillna(CHANNEL_ID).astype(int)
    merged["Stream"] = merged["Stream"].astype(str).str.strip().str.lower().map(
        {"true": "是", "false": "否", "1": "是", "0": "否", "yes": "是", "no": "否"}
    ).fillna("否")

    merged["Date"] = merged["Time (UTC+8)"].dt.strftime("%Y-%m-%d")
    merged = merged.sort_values("Time (UTC+8)").reset_index(drop=True)

    print(f"\n合并后: {len(merged):,} 条")
    print(f"日期范围: {merged['Date'].min()} ~ {merged['Date'].max()}")
    print(f"降档后总费用: ${merged['List Price USD'].sum():,.2f}")
    print(f"系统原价总计: ${merged['Billed USD'].sum():,.2f}")

    return merged


def write_excel(df):
    """Generate final Excel with 4 tabs + detail CSV.zip."""
    wb = xlsxwriter.Workbook(str(OUTPUT_XLSX), {"nan_inf_to_errors": True})

    hdr_fmt = wb.add_format({
        "bold": True, "bg_color": HDR_COLOR, "font_color": "white",
        "border": 1, "text_wrap": True, "valign": "vcenter", "align": "center",
        "font_size": 10,
    })
    money_fmt = wb.add_format({"num_format": '"$"#,##0.00', "border": 1, "font_size": 10})
    money_fmt_alt = wb.add_format({"num_format": '"$"#,##0.00', "border": 1, "bg_color": ALT_COLOR, "font_size": 10})
    money4_fmt = wb.add_format({"num_format": '"$"#,##0.0000', "border": 1, "font_size": 10})
    money4_fmt_alt = wb.add_format({"num_format": '"$"#,##0.0000', "border": 1, "bg_color": ALT_COLOR, "font_size": 10})
    int_fmt = wb.add_format({"num_format": "#,##0", "border": 1, "font_size": 10})
    int_fmt_alt = wb.add_format({"num_format": "#,##0", "border": 1, "bg_color": ALT_COLOR, "font_size": 10})
    text_fmt = wb.add_format({"border": 1, "valign": "vcenter", "font_size": 10})
    text_fmt_alt = wb.add_format({"border": 1, "valign": "vcenter", "bg_color": ALT_COLOR, "font_size": 10})
    total_fmt = wb.add_format({
        "bold": True, "bg_color": "#D6E4F0", "border": 1, "top": 2,
        "num_format": '"$"#,##0.00', "font_size": 10,
    })
    total_int_fmt = wb.add_format({
        "bold": True, "bg_color": "#D6E4F0", "border": 1, "top": 2,
        "num_format": "#,##0", "font_size": 10,
    })
    total_text_fmt = wb.add_format({
        "bold": True, "bg_color": "#D6E4F0", "border": 1, "top": 2, "font_size": 10,
    })

    def get_fmt(row_idx, money=False, money4=False, integer=False):
        alt = row_idx % 2 == 1
        if money:
            return money_fmt_alt if alt else money_fmt
        if money4:
            return money4_fmt_alt if alt else money4_fmt
        if integer:
            return int_fmt_alt if alt else int_fmt
        return text_fmt_alt if alt else text_fmt

    # ── Tab 1: 模型汇总 ──
    model_agg = df.groupby("Model").agg(
        calls=("List Price USD", "count"),
        input_tok=("Input Tokens", "sum"),
        output_tok=("Output Tokens", "sum"),
        list_price=("List Price USD", "sum"),
        billed=("Billed USD", "sum"),
    ).reset_index()
    model_agg["diff"] = model_agg["billed"] - model_agg["list_price"]
    model_agg = model_agg.sort_values("list_price", ascending=False)

    ws1 = wb.add_worksheet("模型汇总")
    ws1.freeze_panes(1, 0)
    ws1.set_tab_color(HDR_COLOR)

    h1 = ["模型", "调用次数", "输入Token", "输出Token", "降档后费用($)", "系统原价($)", "差额($)"]
    w1 = [35, 12, 16, 16, 16, 16, 14]
    for c, (h, w) in enumerate(zip(h1, w1)):
        ws1.write(0, c, h, hdr_fmt)
        ws1.set_column(c, c, w)

    for i, (_, r) in enumerate(model_agg.iterrows()):
        row = 1 + i
        ws1.write(row, 0, r["Model"], get_fmt(i))
        ws1.write(row, 1, int(r["calls"]), get_fmt(i, integer=True))
        ws1.write(row, 2, int(r["input_tok"]), get_fmt(i, integer=True))
        ws1.write(row, 3, int(r["output_tok"]), get_fmt(i, integer=True))
        ws1.write(row, 4, r["list_price"], get_fmt(i, money=True))
        ws1.write(row, 5, r["billed"], get_fmt(i, money=True))
        ws1.write(row, 6, r["diff"], get_fmt(i, money=True))

    tr = 1 + len(model_agg)
    ws1.write(tr, 0, "合计", total_text_fmt)
    ws1.write(tr, 1, int(model_agg["calls"].sum()), total_int_fmt)
    ws1.write(tr, 2, int(model_agg["input_tok"].sum()), total_int_fmt)
    ws1.write(tr, 3, int(model_agg["output_tok"].sum()), total_int_fmt)
    ws1.write(tr, 4, model_agg["list_price"].sum(), total_fmt)
    ws1.write(tr, 5, model_agg["billed"].sum(), total_fmt)
    ws1.write(tr, 6, model_agg["diff"].sum(), total_fmt)

    # ── Tab 2: 按天趋势 ──
    daily_agg = df.groupby("Date").agg(
        calls=("List Price USD", "count"),
        input_tok=("Input Tokens", "sum"),
        output_tok=("Output Tokens", "sum"),
        list_price=("List Price USD", "sum"),
    ).reset_index().sort_values("Date")

    ws2 = wb.add_worksheet("按天趋势")
    ws2.freeze_panes(1, 0)
    ws2.set_tab_color("#548235")

    h2 = ["日期", "调用次数", "输入Token", "输出Token", "降档后费用($)"]
    w2 = [14, 12, 16, 16, 16]
    for c, (h, w) in enumerate(zip(h2, w2)):
        ws2.write(0, c, h, hdr_fmt)
        ws2.set_column(c, c, w)

    for i, (_, r) in enumerate(daily_agg.iterrows()):
        row = 1 + i
        ws2.write(row, 0, r["Date"], get_fmt(i))
        ws2.write(row, 1, int(r["calls"]), get_fmt(i, integer=True))
        ws2.write(row, 2, int(r["input_tok"]), get_fmt(i, integer=True))
        ws2.write(row, 3, int(r["output_tok"]), get_fmt(i, integer=True))
        ws2.write(row, 4, r["list_price"], get_fmt(i, money=True))

    tr2 = 1 + len(daily_agg)
    ws2.write(tr2, 0, "合计", total_text_fmt)
    ws2.write(tr2, 1, int(daily_agg["calls"].sum()), total_int_fmt)
    ws2.write(tr2, 2, int(daily_agg["input_tok"].sum()), total_int_fmt)
    ws2.write(tr2, 3, int(daily_agg["output_tok"].sum()), total_int_fmt)
    ws2.write(tr2, 4, daily_agg["list_price"].sum(), total_fmt)

    # ── Tab 3: 每日模型明细 ──
    daily_model = df.groupby(["Date", "Model"]).agg(
        calls=("List Price USD", "count"),
        input_tok=("Input Tokens", "sum"),
        output_tok=("Output Tokens", "sum"),
        list_price=("List Price USD", "sum"),
    ).reset_index().sort_values(["Date", "list_price"], ascending=[True, False])

    ws3 = wb.add_worksheet("每日模型明细")
    ws3.freeze_panes(1, 0)
    ws3.set_tab_color("#BF8F00")

    h3 = ["日期", "模型", "调用次数", "输入Token", "输出Token", "降档后费用($)"]
    w3 = [14, 35, 12, 16, 16, 16]
    for c, (h, w) in enumerate(zip(h3, w3)):
        ws3.write(0, c, h, hdr_fmt)
        ws3.set_column(c, c, w)

    for i, (_, r) in enumerate(daily_model.iterrows()):
        row = 1 + i
        ws3.write(row, 0, r["Date"], get_fmt(i))
        ws3.write(row, 1, r["Model"], get_fmt(i))
        ws3.write(row, 2, int(r["calls"]), get_fmt(i, integer=True))
        ws3.write(row, 3, int(r["input_tok"]), get_fmt(i, integer=True))
        ws3.write(row, 4, int(r["output_tok"]), get_fmt(i, integer=True))
        ws3.write(row, 5, r["list_price"], get_fmt(i, money=True))

    tr3 = 1 + len(daily_model)
    ws3.write(tr3, 0, "合计", total_text_fmt)
    ws3.write(tr3, 1, "", total_text_fmt)
    ws3.write(tr3, 2, int(daily_model["calls"].sum()), total_int_fmt)
    ws3.write(tr3, 3, int(daily_model["input_tok"].sum()), total_int_fmt)
    ws3.write(tr3, 4, int(daily_model["output_tok"].sum()), total_int_fmt)
    ws3.write(tr3, 5, daily_model["list_price"].sum(), total_fmt)

    # ── Tab 4: 逐条明细 ──
    ws4 = wb.add_worksheet("逐条明细")
    ws4.freeze_panes(1, 0)
    ws4.set_tab_color("#7030A0")

    h4 = [
        "时间(UTC+8)", "渠道ID", "模型", "输入Token", "输出Token",
        "缓存命中Token", "缓存写入Token", "系统扣费($)", "降档后费用($)",
        "使用时间(秒)", "是否流式",
    ]
    w4 = [20, 8, 35, 14, 14, 14, 14, 14, 14, 12, 8]
    for c, (h, w) in enumerate(zip(h4, w4)):
        ws4.write(0, c, h, hdr_fmt)
        ws4.set_column(c, c, w)

    for i in range(len(df)):
        r = df.iloc[i]
        row = 1 + i
        time_str = str(r["Time (UTC+8)"])[:19] if pd.notna(r["Time (UTC+8)"]) else ""
        ws4.write(row, 0, time_str, get_fmt(i))
        ws4.write(row, 1, int(r["Channel ID"]), get_fmt(i, integer=True))
        ws4.write(row, 2, str(r["Model"]) if pd.notna(r["Model"]) else "", get_fmt(i))
        ws4.write(row, 3, int(r["Input Tokens"]), get_fmt(i, integer=True))
        ws4.write(row, 4, int(r["Output Tokens"]), get_fmt(i, integer=True))
        ws4.write(row, 5, int(r["Cache Hit Tokens"]), get_fmt(i, integer=True))
        ws4.write(row, 6, int(r["Cache Write Tokens"]), get_fmt(i, integer=True))
        ws4.write(row, 7, float(r["Billed USD"]), get_fmt(i, money4=True))
        ws4.write(row, 8, float(r["List Price USD"]), get_fmt(i, money4=True))
        ws4.write(row, 9, float(r["Use Time (s)"]), get_fmt(i, integer=True))
        ws4.write(row, 10, str(r["Stream"]), get_fmt(i))

    wb.close()
    print(f"\n[OK] Excel 生成: {OUTPUT_XLSX}")
    import os
    size_mb = os.path.getsize(OUTPUT_XLSX) / (1024 * 1024)
    print(f"  文件大小: {size_mb:.2f} MB")


def write_detail_csv(df):
    """Export detail as CSV.zip."""
    csv_df = df[[
        "Time (UTC+8)", "Channel ID", "Model", "Input Tokens", "Output Tokens",
        "Cache Hit Tokens", "Cache Write Tokens", "Billed USD", "List Price USD",
        "Use Time (s)", "Stream",
    ]].copy()
    csv_df.columns = [
        "时间(UTC+8)", "渠道ID", "模型", "输入Token", "输出Token",
        "缓存命中Token", "缓存写入Token", "系统扣费($)", "降档后费用($)",
        "使用时间(秒)", "是否流式",
    ]

    buf = io.StringIO()
    csv_df.to_csv(buf, index=False, lineterminator="\n")
    with zipfile.ZipFile(OUTPUT_CSV_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr(OUTPUT_CSV_ZIP.stem + ".csv", buf.getvalue().encode("utf-8-sig"))

    import os
    size_mb = os.path.getsize(OUTPUT_CSV_ZIP) / (1024 * 1024)
    print(f"[OK] 明细 CSV.zip 生成: {OUTPUT_CSV_ZIP}")
    print(f"  行数: {len(csv_df):,}")
    print(f"  大小: {size_mb:.2f} MB")


if __name__ == "__main__":
    df = load_and_merge()

    print(f"\n{'='*60}")
    print("数据概况")
    print(f"{'='*60}")
    print(f"总记录数: {len(df):,}")
    print(f"时间范围: {df['Date'].min()} ~ {df['Date'].max()}")
    print(f"模型数: {df['Model'].nunique()}")
    print(f"降档后总费用: ${df['List Price USD'].sum():,.2f}")
    print(f"系统原价总计: ${df['Billed USD'].sum():,.2f}")
    print(f"差额（降档节省）: ${df['Billed USD'].sum() - df['List Price USD'].sum():,.2f}")
    print()

    print("按天记录数:")
    for d, cnt in df.groupby("Date").size().items():
        print(f"  {d}: {cnt:,}")
    print()

    print("生成 Excel ...")
    write_excel(df)

    print("\n生成明细 CSV.zip ...")
    write_detail_csv(df)

    print(f"\n{'='*60}")
    print("最终账单关键数据")
    print(f"{'='*60}")
    total_list = df["List Price USD"].sum()
    total_billed = df["Billed USD"].sum()
    print(f"总费用（降档后）: ${total_list:,.2f}")
    print(f"系统原价: ${total_billed:,.2f}")
    print(f"降档节省: ${total_billed - total_list:,.2f}")
    print(f"调用次数: {len(df):,}")
    print(f"模型数: {df['Model'].nunique()}")
    print()

    print("模型费用明细:")
    for _, r in df.groupby("Model").agg(
        calls=("List Price USD", "count"),
        list_price=("List Price USD", "sum"),
        billed=("Billed USD", "sum"),
    ).reset_index().sort_values("list_price", ascending=False).iterrows():
        print(f"  {r['Model']:40s}  calls={int(r['calls']):>6,}  list=${r['list_price']:>10,.2f}  billed=${r['billed']:>10,.2f}")

    print(f"\n生成文件:")
    print(f"  1. {OUTPUT_XLSX}")
    print(f"  2. {OUTPUT_CSV_ZIP}")
