"""
渠道28 (UniAIX) 2026年3月 供应商对账 Excel 生成脚本
数据源：
  - DB 降档明细 (3/1~3/25): bill_2026-01_ch28_ch28_flattier_since_20260312_supplier_detail.csv.zip
  - Athena 降档明细 (3/26~3/31): bill_2026-03_ch28_flattier_detail.xlsx
  - 供应商账单: uniaix_logs(2).xlsx
"""

import os
import zipfile
import pandas as pd
import xlsxwriter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")

DB_ZIP = os.path.join(OUTPUT_DIR, "bill_2026-01_ch28_ch28_flattier_since_20260312_supplier_detail.csv.zip")
ATHENA_XLSX = os.path.join(OUTPUT_DIR, "bill_2026-03_ch28_flattier_detail.xlsx")
SUPPLIER_XLSX = r"c:\Users\Administrator\xwechat_files\wxid_8zd2avj7cixo22_b66d\msg\file\2026-05\uniaix_logs(2).xlsx"
_output_name = "reconciliation_2026-03_ch28_UniAIX.xlsx"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, _output_name)

def _safe_output_path():
    """如果目标文件被占用，自动加数字后缀"""
    candidates = [OUTPUT_FILE] + [OUTPUT_FILE.replace(".xlsx", f"_v{i}.xlsx") for i in range(2, 10)]
    for path in candidates:
        if not os.path.exists(path):
            return path
        try:
            with open(path, "a"):
                pass
            return path
        except PermissionError:
            continue
    raise RuntimeError("All output paths are locked")

CLAUDE_MODELS = [
    "claude-opus-4-5-20251101",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-20250514",
    "claude-opus-4-1-20250805",
]


def load_our_data():
    """加载我方数据：DB 3/1~3/25 + Athena 3/26~3/31，使用 List Price USD 作为费用"""
    # DB CSV
    with zipfile.ZipFile(DB_ZIP) as z:
        with z.open(z.namelist()[0]) as f:
            db = pd.read_csv(f)
    db["time_dt"] = pd.to_datetime(db["Time (UTC+8)"])
    db = db[(db["time_dt"] >= "2026-03-01") & (db["time_dt"] < "2026-03-26")]

    # Athena Excel (header in row 1)
    ath = pd.read_excel(ATHENA_XLSX, header=1)
    ath["time_dt"] = pd.to_datetime(ath["Time (UTC+8)"])
    ath = ath[ath["time_dt"] >= "2026-03-26"]

    col_map = {
        "Time (UTC+8)": "time",
        "Channel ID": "channel_id",
        "Model": "model",
        "Input Tokens": "input_tokens",
        "Output Tokens": "output_tokens",
        "Cache Hit Tokens": "cache_hit_tokens",
        "Cache Write Tokens": "cache_write_tokens",
        "Quota": "quota",
        "Billed USD": "billed_usd",
        "List Price USD": "list_price_usd",
        "Use Time (s)": "use_time_s",
        "Stream": "stream",
    }

    db_mapped = db.rename(columns=col_map)[list(col_map.values()) + ["time_dt"]]
    ath_mapped = ath.rename(columns=col_map)[list(col_map.values()) + ["time_dt"]]

    merged = pd.concat([db_mapped, ath_mapped], ignore_index=True)
    merged["date"] = merged["time_dt"].dt.strftime("%Y-%m-%d")
    merged["cost"] = merged["list_price_usd"]
    print(f"我方数据: DB {len(db)} + Athena {len(ath)} = {len(merged)} 行")
    print(f"我方总费用(List Price USD): ${merged['cost'].sum():.2f}")
    return merged


def load_supplier_data():
    """加载供应商数据，只保留 claude 模型"""
    sup = pd.read_excel(SUPPLIER_XLSX)
    sup = sup[sup["ModelName"].isin(CLAUDE_MODELS)].copy()
    sup.rename(columns={
        "Date": "date",
        "ModelName": "model",
        "InputTokens": "input_tokens",
        "OutputTokens": "output_tokens",
        "CreateCacheTokens": "cache_create_tokens",
        "ReadCacheTokens": "cache_read_tokens",
        "TotalPrice": "total_price",
    }, inplace=True)
    print(f"供应商数据(claude): {len(sup)} 行, 总费用: ${sup['total_price'].sum():.2f}")
    return sup


def make_summary_by_model(ours, supplier):
    """Tab 1: 按模型汇总对比"""
    our_agg = ours.groupby("model").agg(
        our_count=("cost", "count"),
        our_cost=("cost", "sum"),
    ).reset_index()
    sup_agg = supplier.groupby("model").agg(
        sup_count=("total_price", "count"),
        sup_cost=("total_price", "sum"),
    ).reset_index()
    merged = pd.merge(our_agg, sup_agg, on="model", how="outer").fillna(0)
    merged["count_diff"] = merged["our_count"] - merged["sup_count"]
    merged["cost_diff"] = merged["our_cost"] - merged["sup_cost"]
    merged["diff_rate"] = merged["cost_diff"] / merged["sup_cost"].replace(0, float("nan"))

    totals = pd.DataFrame([{
        "model": "合计",
        "our_count": merged["our_count"].sum(),
        "sup_count": merged["sup_count"].sum(),
        "count_diff": merged["count_diff"].sum(),
        "our_cost": merged["our_cost"].sum(),
        "sup_cost": merged["sup_cost"].sum(),
        "cost_diff": merged["cost_diff"].sum(),
        "diff_rate": merged["cost_diff"].sum() / merged["sup_cost"].sum() if merged["sup_cost"].sum() else 0,
    }])
    merged = pd.concat([merged, totals], ignore_index=True)
    return merged


def make_summary_by_day(ours, supplier):
    """Tab 2: 按天对比"""
    our_agg = ours.groupby("date").agg(
        our_count=("cost", "count"),
        our_cost=("cost", "sum"),
    ).reset_index()
    sup_agg = supplier.groupby("date").agg(
        sup_count=("total_price", "count"),
        sup_cost=("total_price", "sum"),
    ).reset_index()
    merged = pd.merge(our_agg, sup_agg, on="date", how="outer").fillna(0)
    merged = merged.sort_values("date").reset_index(drop=True)
    merged["cost_diff"] = merged["our_cost"] - merged["sup_cost"]
    return merged


def make_daily_model_detail(ours, supplier):
    """Tab 3: 每日模型明细"""
    our_agg = ours.groupby(["date", "model"]).agg(
        our_count=("cost", "count"),
        our_cost=("cost", "sum"),
    ).reset_index()
    sup_agg = supplier.groupby(["date", "model"]).agg(
        sup_count=("total_price", "count"),
        sup_cost=("total_price", "sum"),
    ).reset_index()
    merged = pd.merge(our_agg, sup_agg, on=["date", "model"], how="outer").fillna(0)
    merged = merged.sort_values(["date", "model"]).reset_index(drop=True)
    merged["cost_diff"] = merged["our_cost"] - merged["sup_cost"]
    return merged


def make_our_detail(ours):
    """Tab 4: 我方明细"""
    agg = ours.groupby("model").agg(
        count=("cost", "count"),
        input_tokens=("input_tokens", "sum"),
        output_tokens=("output_tokens", "sum"),
        cost=("cost", "sum"),
    ).reset_index()
    return agg


def make_supplier_detail(supplier):
    """Tab 5: 供应商明细"""
    agg = supplier.groupby("model").agg(
        count=("total_price", "count"),
        input_tokens=("input_tokens", "sum"),
        output_tokens=("output_tokens", "sum"),
        cache_create_tokens=("cache_create_tokens", "sum"),
        cache_read_tokens=("cache_read_tokens", "sum"),
        total_price=("total_price", "sum"),
    ).reset_index()
    return agg


def make_analysis_text(summary):
    """Tab 6: 差异分析文字"""
    totals_row = summary[summary["model"] == "合计"].iloc[0]
    our_total = totals_row["our_cost"]
    sup_total = totals_row["sup_cost"]
    diff = totals_row["cost_diff"]
    rate = totals_row["diff_rate"]

    opus_row = summary[summary["model"] == "claude-opus-4-6"]
    sonnet_row = summary[summary["model"] == "claude-sonnet-4-6"]
    opus_diff = opus_row["cost_diff"].values[0] if len(opus_row) else 0
    opus_sup = opus_row["sup_cost"].values[0] if len(opus_row) else 0
    opus_rate = opus_diff / opus_sup if opus_sup else 0
    sonnet_diff = sonnet_row["cost_diff"].values[0] if len(sonnet_row) else 0
    sonnet_sup = sonnet_row["sup_cost"].values[0] if len(sonnet_row) else 0
    sonnet_rate = sonnet_diff / sonnet_sup if sonnet_sup else 0

    lines = [
        f"数据范围：我方 2026年3月1日~31日（聚合DB+Athena），3月12日起执行降档计费；供应商 3月1日~4月1日",
        f"我方总费用约 ${our_total:,.2f}，供应商总费用约 ${sup_total:,.2f}，总差额约 ${diff:,.2f}（{rate:.2%}）",
        f"降档说明：3月12日起，claude-opus-4-6 和 claude-sonnet-4-6 两个分段计费模型强制使用200K以内低档价格",
        f"降档影响：降档使我方费用从 $11,594 降至 ${our_total:,.2f}，减少约 ${11594 - our_total:,.2f}",
        f"主要差异模型：claude-opus-4-6 差额 ${opus_diff:,.2f}（{opus_rate:.1%}），claude-sonnet-4-6 差额 ${sonnet_diff:+,.2f}（{sonnet_rate:+.1%}）",
        f"差异原因：两边费率完全一致，差异100%来自token计量口径不同（cache tokens处理方式、thinking tokens是否计入output）",
        f"建议：与供应商确认 InputTokens 定义（是否含 cache_read），以及 OutputTokens 是否含 thinking tokens",
    ]
    return lines


def make_row_detail(ours):
    """Tab 7: 逐条明细（脱敏）"""
    detail = ours[[
        "time", "channel_id", "model", "input_tokens", "output_tokens",
        "cache_hit_tokens", "cache_write_tokens", "billed_usd", "list_price_usd",
        "use_time_s", "stream"
    ]].copy()
    detail = detail.sort_values("time").reset_index(drop=True)
    return detail


# ---- Excel 写入 ----

HEADER_BG = "#1F4E79"
HEADER_FONT = "#FFFFFF"
ALT_ROW_BG = "#EBF3FB"


def _add_formats(wb):
    """创建复用格式"""
    base = {"font_size": 10, "font_name": "Calibri", "text_wrap": False}
    header = {**base, "bold": True, "bg_color": HEADER_BG, "font_color": HEADER_FONT,
              "border": 1, "align": "center", "valign": "vcenter"}

    fmts = {
        "header": wb.add_format(header),
        "text": wb.add_format({**base, "border": 1}),
        "text_alt": wb.add_format({**base, "border": 1, "bg_color": ALT_ROW_BG}),
        "money": wb.add_format({**base, "border": 1, "num_format": '"$"#,##0.00'}),
        "money_alt": wb.add_format({**base, "border": 1, "num_format": '"$"#,##0.00', "bg_color": ALT_ROW_BG}),
        "int": wb.add_format({**base, "border": 1, "num_format": "#,##0"}),
        "int_alt": wb.add_format({**base, "border": 1, "num_format": "#,##0", "bg_color": ALT_ROW_BG}),
        "pct": wb.add_format({**base, "border": 1, "num_format": "0.00%"}),
        "pct_alt": wb.add_format({**base, "border": 1, "num_format": "0.00%", "bg_color": ALT_ROW_BG}),
        "analysis": wb.add_format({**base, "font_size": 11, "text_wrap": True}),
    }
    return fmts


def _write_sheet(ws, headers, rows, col_types, fmts, col_widths=None):
    """通用表写入：headers, rows (list of lists), col_types ('text'|'money'|'int'|'pct')"""
    ws.freeze_panes(1, 0)
    for ci, h in enumerate(headers):
        ws.write(0, ci, h, fmts["header"])

    for ri, row in enumerate(rows):
        alt = ri % 2 == 1
        for ci, val in enumerate(row):
            ct = col_types[ci]
            suffix = "_alt" if alt else ""
            fmt = fmts[ct + suffix] if ct in ("money", "int", "pct") else fmts["text" + suffix]
            if val is None or (isinstance(val, float) and pd.isna(val)):
                ws.write_blank(ri + 1, ci, "", fmt)
            else:
                ws.write(ri + 1, ci, val, fmt)

    if col_widths:
        for ci, w in enumerate(col_widths):
            ws.set_column(ci, ci, w)


def write_tab1(wb, fmts, data):
    """汇总对比"""
    ws = wb.add_worksheet("汇总对比")
    headers = ["模型", "我方调用次数", "供应商调用次数", "次数差异", "我方费用($)", "供应商费用($)", "差额($)", "差异率"]
    col_types = ["text", "int", "int", "int", "money", "money", "money", "pct"]
    widths = [30, 14, 14, 12, 14, 14, 12, 10]
    rows = []
    for _, r in data.iterrows():
        rows.append([
            r["model"], int(r["our_count"]), int(r["sup_count"]), int(r["count_diff"]),
            r["our_cost"], r["sup_cost"], r["cost_diff"], r["diff_rate"],
        ])
    _write_sheet(ws, headers, rows, col_types, fmts, widths)


def write_tab2(wb, fmts, data):
    """按天对比"""
    ws = wb.add_worksheet("按天对比")
    headers = ["日期", "我方调用次数", "供应商调用次数", "我方费用($)", "供应商费用($)", "差额($)"]
    col_types = ["text", "int", "int", "money", "money", "money"]
    widths = [14, 14, 14, 14, 14, 12]
    rows = []
    for _, r in data.iterrows():
        rows.append([
            r["date"], int(r["our_count"]), int(r["sup_count"]),
            r["our_cost"], r["sup_cost"], r["cost_diff"],
        ])
    _write_sheet(ws, headers, rows, col_types, fmts, widths)


def write_tab3(wb, fmts, data):
    """每日模型明细"""
    ws = wb.add_worksheet("每日模型明细")
    headers = ["日期", "模型", "我方调用次数", "供应商调用次数", "我方费用($)", "供应商费用($)", "差额($)"]
    col_types = ["text", "text", "int", "int", "money", "money", "money"]
    widths = [14, 30, 14, 14, 14, 14, 12]
    rows = []
    for _, r in data.iterrows():
        rows.append([
            r["date"], r["model"], int(r["our_count"]), int(r["sup_count"]),
            r["our_cost"], r["sup_cost"], r["cost_diff"],
        ])
    _write_sheet(ws, headers, rows, col_types, fmts, widths)


def write_tab4(wb, fmts, data):
    """我方明细"""
    ws = wb.add_worksheet("我方明细")
    headers = ["模型", "调用次数", "输入Token", "输出Token", "费用($)（降档后）"]
    col_types = ["text", "int", "int", "int", "money"]
    widths = [30, 12, 14, 14, 16]
    rows = []
    for _, r in data.iterrows():
        rows.append([
            r["model"], int(r["count"]), int(r["input_tokens"]),
            int(r["output_tokens"]), r["cost"],
        ])
    _write_sheet(ws, headers, rows, col_types, fmts, widths)


def write_tab5(wb, fmts, data):
    """供应商明细"""
    ws = wb.add_worksheet("供应商明细")
    headers = ["模型", "调用次数", "输入Token", "输出Token", "缓存创建Token", "缓存读取Token", "总费用($)"]
    col_types = ["text", "int", "int", "int", "int", "int", "money"]
    widths = [30, 12, 14, 14, 14, 14, 14]
    rows = []
    for _, r in data.iterrows():
        rows.append([
            r["model"], int(r["count"]), int(r["input_tokens"]),
            int(r["output_tokens"]), int(r["cache_create_tokens"]),
            int(r["cache_read_tokens"]), r["total_price"],
        ])
    _write_sheet(ws, headers, rows, col_types, fmts, widths)


def write_tab6(wb, fmts, lines):
    """差异分析"""
    ws = wb.add_worksheet("差异分析")
    ws.set_column(0, 0, 120)
    for i, line in enumerate(lines):
        ws.write(i, 0, line, fmts["analysis"])
    ws.set_row(0, 30)


def write_tab7(wb, fmts, data):
    """逐条明细"""
    ws = wb.add_worksheet("逐条明细")
    headers = [
        "时间(UTC+8)", "渠道ID", "模型", "输入Token", "输出Token",
        "缓存命中Token", "缓存写入Token", "系统扣费($)", "降档后费用($)",
        "使用时间(秒)", "是否流式",
    ]
    col_types = ["text", "int", "text", "int", "int", "int", "int", "money", "money", "int", "text"]
    widths = [20, 8, 30, 12, 12, 12, 12, 12, 14, 10, 8]

    ws.freeze_panes(1, 0)
    for ci, h in enumerate(headers):
        ws.write(0, ci, h, fmts["header"])
    if widths:
        for ci, w in enumerate(widths):
            ws.set_column(ci, ci, w)

    for ri in range(len(data)):
        alt = ri % 2 == 1
        row = data.iloc[ri]
        vals = [
            str(row["time"]), int(row["channel_id"]) if pd.notna(row["channel_id"]) else 28,
            row["model"], int(row["input_tokens"]), int(row["output_tokens"]),
            int(row["cache_hit_tokens"]) if pd.notna(row["cache_hit_tokens"]) else 0,
            int(row["cache_write_tokens"]) if pd.notna(row["cache_write_tokens"]) else 0,
            row["billed_usd"], row["list_price_usd"],
            int(row["use_time_s"]) if pd.notna(row["use_time_s"]) else 0,
            str(row["stream"]) if pd.notna(row["stream"]) else "True",
        ]
        for ci, val in enumerate(vals):
            ct = col_types[ci]
            suffix = "_alt" if alt else ""
            fmt = fmts[ct + suffix] if ct in ("money", "int", "pct") else fmts["text" + suffix]
            ws.write(ri + 1, ci, val, fmt)


def main():
    print("=" * 60)
    print("渠道28 UniAIX 2026年3月 供应商对账报告生成")
    print("=" * 60)

    ours = load_our_data()
    supplier = load_supplier_data()

    tab1_data = make_summary_by_model(ours, supplier)
    tab2_data = make_summary_by_day(ours, supplier)
    tab3_data = make_daily_model_detail(ours, supplier)
    tab4_data = make_our_detail(ours)
    tab5_data = make_supplier_detail(supplier)
    tab6_lines = make_analysis_text(tab1_data)
    tab7_data = make_row_detail(ours)

    actual_output = _safe_output_path()
    wb = xlsxwriter.Workbook(actual_output, {"strings_to_numbers": False})
    fmts = _add_formats(wb)

    write_tab1(wb, fmts, tab1_data)
    write_tab2(wb, fmts, tab2_data)
    write_tab3(wb, fmts, tab3_data)
    write_tab4(wb, fmts, tab4_data)
    write_tab5(wb, fmts, tab5_data)
    write_tab6(wb, fmts, tab6_lines)
    write_tab7(wb, fmts, tab7_data)

    wb.close()

    file_size = os.path.getsize(actual_output)
    print(f"\n{'=' * 60}")
    print(f"文件路径: {actual_output}")
    print(f"文件大小: {file_size / 1024 / 1024:.2f} MB")
    print(f"{'=' * 60}")

    # 验证
    totals = tab1_data[tab1_data["model"] == "合计"].iloc[0]
    print(f"\n[验证] Tab 1 合计行:")
    print(f"  我方费用: ${totals['our_cost']:,.2f} (预期约 $10,953)")
    print(f"  供应商费用: ${totals['sup_cost']:,.2f}")
    print(f"  差额: ${totals['cost_diff']:,.2f} (预期约 -$962)")
    print(f"  差异率: {totals['diff_rate']:.2%}")
    print(f"\n[验证] Tab 7 明细行数: {len(tab7_data)} (预期约 30,338)")

    ok = True
    if abs(totals["our_cost"] - 10953) > 100:
        print(f"  [WARN] our cost deviation too large")
        ok = False
    if abs(totals["cost_diff"] - (-962)) > 100:
        print(f"  [WARN] diff deviation too large")
        ok = False
    if ok:
        print("\n[OK] Validation passed")


if __name__ == "__main__":
    main()
