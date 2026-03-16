"""
MateCloud 上游对账脚本
- 用 (时间±2秒, 模型, completion_tokens) 做主键匹配
- 对整分钟时间戳扩展到 ±60秒窗口
- 输出：匹配统计 + 差异明细 Excel
"""
import sqlite3, csv, sys, time, os
from datetime import datetime, timezone, timedelta
from collections import defaultdict

import pandas as pd
import numpy as np
import xlsxwriter

DB_PATH = "logs_analysis.db"
CST = timezone(timedelta(hours=8))

MATECLOUD_FILES = {
    "2026-01": "reconcile/EZmodel渠道账单/[24-25]MateCloud/Ezmode1月账单-复核后_明细.csv",
}

QUOTA_PER_USD    = 500_000
COST_DISCOUNT    = 0.41
REVENUE_DISCOUNT = 0.65


def parse_mc_time(s: str) -> datetime | None:
    s = s.strip()
    for fmt in ("%m/%d/%y %H:%M:%S", "%m/%d/%y %H:%M"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=CST)
        except ValueError:
            pass
    return None


def load_matecloud(fpath: str) -> pd.DataFrame:
    rows = []
    with open(fpath, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            dt = parse_mc_time(r["时间"])
            if dt is None:
                continue
            rows.append({
                "mc_time":   dt,
                "mc_unix":   int(dt.timestamp()),
                "mc_cst":    dt.strftime("%Y-%m-%d %H:%M:%S"),
                "model":     r["模型"],
                "mc_pt":     int(r["提示"] or 0),
                "mc_ct":     int(r["补全"] or 0),
                "mc_usd":    float(r["额度"] or 0),   # 原价 USD
                "is_minute": dt.second == 0,
            })
    return pd.DataFrame(rows)


def load_db(ts_start: int, ts_end: int) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """SELECT id, created_at,
                  datetime(created_at,'unixepoch','+8 hours') AS cst,
                  model_name AS model,
                  quota, prompt_tokens AS pt, completion_tokens AS ct,
                  token_name
           FROM logs
           WHERE username='GMICloud' AND type=2
             AND created_at>=? AND created_at<?
             AND model_name LIKE '%claude%'
           ORDER BY created_at""",
        conn, params=(ts_start, ts_end)
    )
    conn.close()
    df["billed_usd"] = df["quota"] / QUOTA_PER_USD
    return df


def match_records(mc: pd.DataFrame, db: pd.DataFrame, tight_window=2, wide_window=60):
    """
    匹配策略：
    1. 非整分钟记录：±tight_window 秒
    2. 整分钟记录：±wide_window 秒
    返回 matched DataFrame 和 unmatched_mc, unmatched_db
    """
    # 建 DB 索引：(unix_ts, model, ct) -> list of db row indices
    db_index = defaultdict(list)
    for idx, row in db.iterrows():
        db_index[(int(row["created_at"]), row["model"], int(row["ct"]))].append(idx)

    matched_pairs = []   # (mc_idx, db_idx, delta_sec)
    used_db = set()

    def try_match(mc_idx, mc_unix, model, ct, window):
        for delta in range(0, window + 1):
            for sign in ([0] if delta == 0 else [delta, -delta]):
                key = (mc_unix + sign, model, ct)
                candidates = db_index.get(key, [])
                for db_idx in candidates:
                    if db_idx not in used_db:
                        return db_idx, sign
        return None, None

    for mc_idx, mc_row in mc.iterrows():
        window = wide_window if mc_row["is_minute"] else tight_window
        db_idx, delta = try_match(
            mc_idx, mc_row["mc_unix"], mc_row["model"], mc_row["mc_ct"], window
        )
        if db_idx is not None:
            matched_pairs.append((mc_idx, db_idx, delta))
            used_db.add(db_idx)

    matched_mc_idx  = {p[0] for p in matched_pairs}
    matched_db_idx  = {p[1] for p in matched_pairs}
    unmatched_mc    = mc[~mc.index.isin(matched_mc_idx)].copy()
    unmatched_db    = db[~db.index.isin(matched_db_idx)].copy()

    # 构建匹配结果 DataFrame
    if matched_pairs:
        mc_idx_list  = [p[0] for p in matched_pairs]
        db_idx_list  = [p[1] for p in matched_pairs]
        delta_list   = [p[2] for p in matched_pairs]
        mc_matched   = mc.loc[mc_idx_list].reset_index(drop=True)
        db_matched   = db.loc[db_idx_list].reset_index(drop=True)
        matched = pd.DataFrame({
            "db_id":       db_matched["id"],
            "db_cst":      db_matched["cst"],
            "model":       mc_matched["model"],
            "token_name":  db_matched["token_name"],
            "delta_sec":   delta_list,
            "mc_pt":       mc_matched["mc_pt"],
            "db_pt":       db_matched["pt"],
            "mc_ct":       mc_matched["mc_ct"],
            "db_ct":       db_matched["ct"],
            "mc_usd":      mc_matched["mc_usd"],          # MateCloud 原价
            "mc_cost":     mc_matched["mc_usd"] * COST_DISCOUNT,   # 我们的成本
            "db_billed":   db_matched["billed_usd"],      # 我们收 GMI 的实际金额
            "pt_diff":     db_matched["pt"].values - mc_matched["mc_pt"].values,
            "ct_diff":     db_matched["ct"].values - mc_matched["mc_ct"].values,
            "usd_diff":    db_matched["billed_usd"].values - mc_matched["mc_usd"].values * COST_DISCOUNT,
        })
    else:
        matched = pd.DataFrame()

    return matched, unmatched_mc, unmatched_db


def write_report(month_label, matched, unmatched_mc, unmatched_db, mc_total, db_total):
    fname = f"reconcile/matecloud_reconcile_{month_label}.xlsx"
    wb = xlsxwriter.Workbook(fname)

    BORDER = {"border": 1, "border_color": "#B0C4DE"}
    def fmt(bold=False, bg=None, nf=None, align="left", color=None):
        p = {**BORDER, "font_size": 10, "valign": "vcenter", "align": align}
        if bold:  p["bold"] = True
        if bg:    p["bg_color"] = bg
        if nf:    p["num_format"] = nf
        if color: p["font_color"] = color
        return wb.add_format(p)

    hdr_fmt = wb.add_format({**BORDER, "bold": True, "font_color": "#FFFFFF",
                              "bg_color": "#1F4E79", "align": "center",
                              "valign": "vcenter", "text_wrap": True, "font_size": 10})
    tot_fmt = wb.add_format({**BORDER, "bold": True, "bg_color": "#D6E4F0",
                              "font_size": 10, "valign": "vcenter"})
    alt_bg  = "#EBF3FB"

    def write_tab(sheet_name, title, headers, widths, rows, fmts, total_row=None):
        ws = wb.add_worksheet(sheet_name)
        ws.freeze_panes(2, 0)
        ws.set_row(0, 22); ws.set_row(1, 36)
        title_f = wb.add_format({"bold": True, "font_size": 13, "font_color": "#1F4E79",
                                  "align": "center", "valign": "vcenter"})
        ws.merge_range(0, 0, 0, len(headers)-1, title, title_f)
        for c, (h, w) in enumerate(zip(headers, widths)):
            ws.write(1, c, h, hdr_fmt)
            ws.set_column(c, c, w)
        fc = {}
        def gf(nf, ri, is_tot=False):
            key = (nf, ri&1, is_tot)
            if key not in fc:
                if is_tot:
                    fc[key] = wb.add_format({**BORDER, "bold": True, "bg_color": "#D6E4F0",
                                             "font_size": 10, "valign": "vcenter",
                                             "num_format": nf or "General",
                                             "align": "right" if nf else "left"})
                else:
                    bg = alt_bg if (ri&1)==0 else None
                    p = {**BORDER, "font_size": 10, "valign": "vcenter",
                         "num_format": nf or "General",
                         "align": "right" if nf else "left"}
                    if bg: p["bg_color"] = bg
                    fc[key] = wb.add_format(p)
            return fc[key]
        for ri, row in enumerate(rows):
            for ci, (v, nf) in enumerate(zip(row, fmts)):
                ws.write(ri+2, ci, v, gf(nf, ri))
        if total_row:
            for ci, (v, nf) in enumerate(zip(total_row, fmts)):
                ws.write(len(rows)+2, ci, v, gf(nf, 0, is_tot=True))

    USD4 = '"$"#,##0.0000'
    USD6 = '"$"#,##0.000000'
    TOK  = "#,##0"
    PCT  = "0.00%"

    # ── Tab1: 汇总统计 ────────────────────────────────────────────────────────
    n_mc   = mc_total
    n_db   = db_total
    n_mat  = len(matched)
    n_umc  = len(unmatched_mc)
    n_udb  = len(unmatched_db)
    mc_usd_total   = matched["mc_usd"].sum()   if not matched.empty else 0
    mc_cost_total  = mc_usd_total * COST_DISCOUNT
    db_billed_total= matched["db_billed"].sum() if not matched.empty else 0
    umc_usd        = unmatched_mc["mc_usd"].sum() if not unmatched_mc.empty else 0
    udb_billed     = unmatched_db["billed_usd"].sum() if not unmatched_db.empty else 0

    summary_rows = [
        ["MateCloud 账单总条数",   n_mc,   ""],
        ["DB 总条数",              n_db,   ""],
        ["成功匹配条数",           n_mat,  f"{n_mat/n_mc*100:.2f}%" if n_mc else ""],
        ["MateCloud 未匹配条数",   n_umc,  f"{n_umc/n_mc*100:.2f}%" if n_mc else ""],
        ["DB 未匹配条数",          n_udb,  f"{n_udb/n_db*100:.2f}%" if n_db else ""],
        ["", "", ""],
        ["匹配记录 MateCloud 原价 USD",  mc_usd_total,    ""],
        [f"匹配记录 我方成本 ({COST_DISCOUNT*10:.1f}折)", mc_cost_total, ""],
        ["匹配记录 DB 实收 USD",         db_billed_total, ""],
        ["匹配记录 差额 (实收-成本)",    db_billed_total - mc_cost_total, ""],
        ["", "", ""],
        ["MateCloud 未匹配原价 USD",  umc_usd,    "（MateCloud有但DB无）"],
        ["DB 未匹配实收 USD",         udb_billed, "（DB有但MateCloud无）"],
    ]
    write_tab("汇总", f"MateCloud 对账汇总 — {month_label}",
              ["指标", "数值", "备注"], [30, 18, 30],
              summary_rows, [None, USD4, None])

    # ── Tab2: 匹配明细（有差异的优先） ────────────────────────────────────────
    if not matched.empty:
        m = matched.copy()
        m["has_diff"] = (m["pt_diff"].abs() > 0) | (m["ct_diff"].abs() > 0)
        m = pd.concat([m[m["has_diff"]], m[~m["has_diff"]]]).reset_index(drop=True)

        mat_rows = []
        for _, r in m.iterrows():
            mat_rows.append([
                int(r["db_id"]), str(r["db_cst"]), str(r["model"]),
                str(r["token_name"] or ""), int(r["delta_sec"]),
                int(r["mc_pt"]), int(r["db_pt"]), int(r["pt_diff"]),
                int(r["mc_ct"]), int(r["db_ct"]), int(r["ct_diff"]),
                float(r["mc_usd"]), float(r["mc_cost"]), float(r["db_billed"]),
                float(r["usd_diff"]),
            ])
        mat_hdrs = ["DB记录ID","DB时间(CST)","模型","Token名称","时间偏移(秒)",
                    "MC输入Tokens","DB输入Tokens","输入差(DB-MC)",
                    "MC输出Tokens","DB输出Tokens","输出差(DB-MC)",
                    "MC原价USD","我方成本USD","DB实收USD","差额(实收-成本)"]
        mat_wids = [12,20,28,18,12,14,14,14,14,14,14,14,14,14,16]
        mat_fmts = [TOK,None,None,None,TOK,TOK,TOK,TOK,TOK,TOK,TOK,USD6,USD6,USD6,USD6]
        write_tab("匹配明细", f"匹配明细（有差异优先）— {month_label}",
                  mat_hdrs, mat_wids, mat_rows, mat_fmts)

    # ── Tab3: MateCloud 未匹配 ────────────────────────────────────────────────
    if not unmatched_mc.empty:
        umc_rows = []
        for _, r in unmatched_mc.iterrows():
            umc_rows.append([
                str(r["mc_cst"]), str(r["model"]),
                int(r["mc_pt"]), int(r["mc_ct"]),
                float(r["mc_usd"]), float(r["mc_usd"] * COST_DISCOUNT),
                "整分钟" if r["is_minute"] else "精确秒",
            ])
        write_tab("MC未匹配", f"MateCloud 未匹配记录 — {month_label}",
                  ["MC时间(CST)","模型","MC输入Tokens","MC输出Tokens",
                   "MC原价USD","我方成本USD","时间精度"],
                  [20,28,14,14,14,14,10],
                  umc_rows, [None,None,TOK,TOK,USD6,USD6,None])

    # ── Tab4: DB 未匹配 ───────────────────────────────────────────────────────
    if not unmatched_db.empty:
        udb_rows = []
        for _, r in unmatched_db.iterrows():
            udb_rows.append([
                int(r["id"]), str(r["cst"]), str(r["model"]),
                str(r["token_name"] or ""),
                int(r["pt"]), int(r["ct"]),
                float(r["billed_usd"]),
            ])
        write_tab("DB未匹配", f"DB 未匹配记录 — {month_label}",
                  ["DB记录ID","DB时间(CST)","模型","Token名称",
                   "输入Tokens","输出Tokens","DB实收USD"],
                  [12,20,28,18,14,14,14],
                  udb_rows, [TOK,None,None,None,TOK,TOK,USD6])

    wb.close()
    return fname


def reconcile(month_label: str, ts_start: int, ts_end: int):
    t0 = time.time()
    fpath = MATECLOUD_FILES.get(month_label)
    if not fpath or not os.path.exists(fpath):
        print(f"[{month_label}] 无 MateCloud 账单文件，跳过")
        return

    print(f"[{month_label}] 加载 MateCloud 账单...", flush=True)
    mc = load_matecloud(fpath)
    mc_claude = mc[mc["model"].str.contains("claude", case=False, na=False)].copy()
    print(f"[{month_label}] MateCloud: {len(mc)}条 (Claude: {len(mc_claude)}条)", flush=True)

    print(f"[{month_label}] 加载 DB...", flush=True)
    db = load_db(ts_start, ts_end)
    print(f"[{month_label}] DB: {len(db)}条", flush=True)

    print(f"[{month_label}] 匹配中...", flush=True)
    matched, unmatched_mc, unmatched_db = match_records(mc_claude, db)

    n_mat = len(matched)
    n_mc  = len(mc_claude)
    print(f"[{month_label}] 匹配率: {n_mat}/{n_mc} ({n_mat/n_mc*100:.1f}%)", flush=True)

    if not matched.empty:
        mc_cost = float(matched["mc_usd"].sum()) * COST_DISCOUNT
        db_rev  = float(matched["db_billed"].sum())
        print(f"[{month_label}] 成本=${mc_cost:,.2f}  实收=${db_rev:,.2f}  差额=${db_rev-mc_cost:,.2f}",
              flush=True)

    print(f"[{month_label}] 写入报告...", flush=True)
    fname = write_report(month_label, matched, unmatched_mc, unmatched_db,
                         len(mc_claude), len(db))
    print(f"[{month_label}] OK {fname}  耗时{time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    reconcile("2026-01",
              int(datetime(2026, 1, 1).timestamp()),
              int(datetime(2026, 2, 1).timestamp()))
