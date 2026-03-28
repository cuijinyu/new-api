"""
现金流预测表 — 2026年3月~6月
基于 logs_analysis.db 实际数据 + 用户提供的回款/付款计划
含供应商方案对比（MateCloud vs 知书万卷）+ 垫资需求分析

商业模型:
  收入端（客户付给我们）:
    - GMI:    刊例价 × 0.65
    - 神州数码: 刊例价 × 0.47 (flat_tier 低档价基准)
  成本端（我们付给供应商）:
    - MateCloud: 刊例价 × 0.40
    - 知书万卷:  刊例价 × 0.35

账期规则:
    - MateCloud: 月结，3月账单最迟可到5月付
    - 知书万卷:  4/15前周结，4/15后改月结
    - GMI 回款:  次月
    - 神州数码:  预付 (3/26 + 4/3 各$15万)
    - 所有回款按月底到账计算
"""
import xlsxwriter
from datetime import datetime

OUTPUT = "reconcile/现金流预测_2026Q1Q2_v5.xlsx"

# ══════════════════════════════════════════════════════════════════════════════
# 精确数据（来自 GMICloud_bill_2026-01/02.xlsx）
# ══════════════════════════════════════════════════════════════════════════════
GMI_JAN_BILLED = 25405;  GMI_FEB_BILLED = 48920
MC_JAN_BILLED  = 25435;  MC_FEB_BILLED  = 48085
GMI_JAN_REV    = 16513;  GMI_FEB_REV    = 31798   # billed × 0.65
MC_JAN_COST    = round(MC_JAN_BILLED * 0.40)   # 10,174
MC_FEB_COST    = round(MC_FEB_BILLED * 0.40)   # 19,234
GMI_12_REV     = 48311
MC_12_COST     = MC_JAN_COST + MC_FEB_COST      # 29,408

# ══════════════════════════════════════════════════════════════════════════════
# 近5天日均（3/18-3/22）— "保守"预估基准
# ══════════════════════════════════════════════════════════════════════════════
DAILY_GMI_BILLED    = 13383
DAILY_DRAGON_BILLED = 36517
DAILY_MC25_BILLED   = 23823
DAILY_MC24_BILLED   = 3667
DAILY_ZS54_BILLED   = 21050
DAILY_MC_BILLED     = DAILY_MC25_BILLED + DAILY_MC24_BILLED   # 27,490
DAILY_TOTAL_BILLED  = DAILY_MC_BILLED + DAILY_ZS54_BILLED     # 48,540

# ══════════════════════════════════════════════════════════════════════════════
# 3/22 单日实际数据 — "峰值"压力测试基准
# ══════════════════════════════════════════════════════════════════════════════
D22_TOTAL = 167337
D22_MC    = 105640
D22_ZS    = 61682
D22_MC_R  = 0.631
D22_ZS_R  = 0.369

# ══════════════════════════════════════════════════════════════════════════════
# 3月截至3/22已确认数据
# ══════════════════════════════════════════════════════════════════════════════
MAR_GMI_SOFAR    = 364638
MAR_DRAGON_SOFAR = 182583
MAR_MC_SOFAR     = 409280
MAR_ZS_SOFAR     = 105250
MAR_REMAIN       = 9   # 3/23 ~ 3/31

# 保守预估（5天日均外推）
EST_GMI_MAR    = MAR_GMI_SOFAR    + DAILY_GMI_BILLED    * MAR_REMAIN
EST_DRAGON_MAR = MAR_DRAGON_SOFAR + DAILY_DRAGON_BILLED * MAR_REMAIN
EST_MC_MAR     = MAR_MC_SOFAR     + DAILY_MC_BILLED     * MAR_REMAIN
EST_ZS_MAR     = MAR_ZS_SOFAR     + DAILY_ZS54_BILLED   * MAR_REMAIN
EST_TOTAL_MAR  = EST_MC_MAR + EST_ZS_MAR

# 峰值预估（按3/22量级外推）
EST_MC_MAR_PK    = MAR_MC_SOFAR + D22_MC * MAR_REMAIN
EST_ZS_MAR_PK    = MAR_ZS_SOFAR + D22_ZS * MAR_REMAIN
EST_TOTAL_MAR_PK = EST_MC_MAR_PK + EST_ZS_MAR_PK

# 4月预估
EST_GMI_APR    = DAILY_GMI_BILLED * 30
EST_DRAGON_APR = DAILY_DRAGON_BILLED * 30
EST_MC_APR     = DAILY_MC_BILLED * 30
EST_ZS_APR     = DAILY_ZS54_BILLED * 30
EST_TOTAL_APR  = EST_MC_APR + EST_ZS_APR

# 4月峰值
EST_MC_APR_PK    = D22_MC * 30
EST_ZS_APR_PK    = D22_ZS * 30
EST_TOTAL_APR_PK = D22_TOTAL * 30

DRAGON_FUND = 300000  # 神州已承诺垫资


# ══════════════════════════════════════════════════════════════════════════════
# 格式工厂
# ══════════════════════════════════════════════════════════════════════════════
def _fmt(wb):
    B = {"border": 1, "border_color": "#B0C4DE"}
    f = {}
    f["title"]   = wb.add_format({"bold": True, "font_size": 14, "font_color": "#1F4E79",
                                   "align": "center", "valign": "vcenter"})
    f["sub"]     = wb.add_format({"italic": True, "font_color": "#666666", "font_size": 9,
                                   "align": "right"})
    f["hdr"]     = wb.add_format({**B, "bold": True, "font_color": "#FFF",
                                   "bg_color": "#1F4E79", "align": "center",
                                   "valign": "vcenter", "text_wrap": True, "font_size": 10})
    f["hdr_g"]   = wb.add_format({**B, "bold": True, "font_color": "#FFF",
                                   "bg_color": "#2E7D32", "align": "center",
                                   "valign": "vcenter", "text_wrap": True, "font_size": 10})
    f["hdr_o"]   = wb.add_format({**B, "bold": True, "font_color": "#FFF",
                                   "bg_color": "#E65100", "align": "center",
                                   "valign": "vcenter", "text_wrap": True, "font_size": 10})
    f["sec"]     = wb.add_format({**B, "bold": True, "bg_color": "#D6E4F0",
                                   "font_size": 10, "align": "left"})
    f["r"]       = wb.add_format({**B, "font_size": 10})
    f["ra"]      = wb.add_format({**B, "font_size": 10, "bg_color": "#F2F7FC"})
    f["$"]       = wb.add_format({**B, "font_size": 10, "num_format": '"$"#,##0'})
    f["$a"]      = wb.add_format({**B, "font_size": 10, "num_format": '"$"#,##0',
                                   "bg_color": "#F2F7FC"})
    f["$b"]      = wb.add_format({**B, "bold": True, "font_size": 10,
                                   "num_format": '"$"#,##0', "bg_color": "#D6E4F0"})
    f["$g"]      = wb.add_format({**B, "bold": True, "font_size": 11,
                                   "num_format": '"$"#,##0', "font_color": "#006600",
                                   "bg_color": "#E2EFDA"})
    f["$R"]      = wb.add_format({**B, "bold": True, "font_size": 11,
                                   "num_format": '"$"#,##0', "font_color": "#CC0000",
                                   "bg_color": "#FCE4EC"})
    f["n"]       = wb.add_format({**B, "font_size": 9, "text_wrap": True,
                                   "font_color": "#555"})
    f["na"]      = wb.add_format({**B, "font_size": 9, "text_wrap": True,
                                   "font_color": "#555", "bg_color": "#F2F7FC"})
    f["%"]       = wb.add_format({**B, "font_size": 10, "num_format": "0.0%"})
    f["%a"]      = wb.add_format({**B, "font_size": 10, "num_format": "0.0%",
                                   "bg_color": "#F2F7FC"})
    f["neg"]     = wb.add_format({**B, "bold": True, "font_size": 10,
                                   "num_format": '"$"#,##0', "font_color": "#CC0000"})
    f["txt"]     = wb.add_format({"font_size": 11, "text_wrap": True, "valign": "top"})
    f["txts"]    = wb.add_format({"font_size": 11, "bold": True, "font_color": "#1F4E79"})
    return f


def _write_events(ws, events, f, start=3):
    bal = 0
    r = start
    for i, (dt, ev, inc, out, note) in enumerate(events):
        bal += inc - out
        a = i % 2 == 1
        ws.write(r, 0, dt,   f["ra"] if a else f["r"])
        ws.write(r, 1, ev,   f["ra"] if a else f["r"])
        ws.write(r, 2, inc if inc else "", f["$a"] if a else f["$"] if inc else f["ra"] if a else f["r"])
        ws.write(r, 3, out if out else "", f["$a"] if a else f["$"] if out else f["ra"] if a else f["r"])
        ws.write(r, 4, bal,  f["$g"] if bal > 0 else f["$R"])
        ws.write(r, 5, note, f["na"] if a else f["n"])
        ws.set_row(r, max(30, 15 * (note.count("\n") + 1)))
        r += 1
    ti = sum(e[2] for e in events)
    to = sum(e[3] for e in events)
    ws.write(r, 0, "", f["sec"]); ws.write(r, 1, "合计", f["sec"])
    ws.write(r, 2, ti, f["$b"]); ws.write(r, 3, to, f["$b"])
    ws.write(r, 4, ti - to, f["$g"] if ti - to > 0 else f["$R"])
    ws.write(r, 5, "", f["sec"])
    return bal, r + 1


def _tl_setup(ws, title, f):
    ws.hide_gridlines(2); ws.set_landscape()
    ws.set_column(0, 0, 14); ws.set_column(1, 1, 30)
    ws.set_column(2, 2, 14); ws.set_column(3, 3, 14)
    ws.set_column(4, 4, 14); ws.set_column(5, 5, 58)
    ws.merge_range(0, 0, 0, 5, title, f["title"]); ws.set_row(0, 28)
    ws.merge_range(1, 0, 1, 5,
                   f"生成: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
                   "余额起点: $0  |  数据截至: 2026-03-22 22:21  |  "
                   "所有回款按月底到账", f["sub"])
    for c, h in enumerate(["日期", "事项", "收入 (USD)", "支出 (USD)", "累计余额", "说明"]):
        ws.write(2, c, h, f["hdr"])
    ws.set_row(2, 22); ws.freeze_panes(3, 0)


# ══════════════════════════════════════════════════════════════════════════════
def build_workbook():
    wb = xlsxwriter.Workbook(OUTPUT, {"constant_memory": False})
    f = _fmt(wb)

    # ── 各方案下的月度成本 ──
    # 方案A: 全走 MC (×0.40)
    mar_cost_A = round(EST_TOTAL_MAR * 0.40)
    apr_cost_A = round(EST_TOTAL_APR * 0.40)
    # 方案B: 全走知书 (×0.35)
    mar_cost_B = round(EST_TOTAL_MAR * 0.35)
    apr_cost_B = round(EST_TOTAL_APR * 0.35)
    # 方案C: 当前混合
    mar_cost_C = round(EST_MC_MAR * 0.40 + EST_ZS_MAR * 0.35)
    apr_cost_C = round(EST_MC_APR * 0.40 + EST_ZS_APR * 0.35)

    # 知书万卷 4/15前周结部分 (3/23~4/14 = 23天，按日均)
    zs_pre415_billed = DAILY_ZS54_BILLED * 23
    zs_pre415_cost   = round(zs_pre415_billed * 0.35)
    # 知书万卷 4/15后月结部分 (4/15~4/30 = 16天)
    zs_post415_billed = DAILY_ZS54_BILLED * 16
    zs_post415_cost   = round(zs_post415_billed * 0.35)

    # GMI 3月回款（5月到）
    gmi_mar_rev = round(EST_GMI_MAR * 0.65)

    # 神州回款（垫资从回款中扣除）
    dragon_mar_rev_gross = round(EST_DRAGON_MAR * 0.47)
    dragon_apr_rev_gross = round(EST_DRAGON_APR * 0.47)
    # 3月回款先抵扣垫资
    if dragon_mar_rev_gross >= DRAGON_FUND:
        dragon_mar_rev_net = dragon_mar_rev_gross - DRAGON_FUND
        dragon_apr_deduct  = 0
    else:
        dragon_mar_rev_net = 0
        dragon_apr_deduct  = DRAGON_FUND - dragon_mar_rev_gross
    dragon_apr_rev_net = dragon_apr_rev_gross - dragon_apr_deduct

    # ══════════════════════════════════════════════════════════════════════════
    # Sheet 1: 方案A — 全走 MateCloud
    # ══════════════════════════════════════════════════════════════════════════
    ws_a = wb.add_worksheet("方案A-全走MateCloud")
    _tl_setup(ws_a, "方案 A：全部流量走 MateCloud（成本 ×0.40）", f)

    # 神州回款说明文字
    dragon_deduct_note = (
        f"神州 3月应收 ${dragon_mar_rev_gross:,} (billed ${EST_DRAGON_MAR:,} x 0.47)\n"
        f"扣除垫资 ${DRAGON_FUND:,}，3月净回款 ${dragon_mar_rev_net:,}"
    )
    if dragon_apr_deduct > 0:
        dragon_deduct_note += f"\n3月不够抵扣，剩余 ${dragon_apr_deduct:,} 从4月扣"

    events_a = [
        ("3月底", "神州数码 垫资（预付款）", DRAGON_FUND, 0,
         "神州数码 3/26 $15万 + 4/3 $15万 = $30万\n"
         "性质: 预付款，后续从神州月结回款中扣除"),
        ("4月底", "神州数码 回款（3月·扣垫资）", dragon_mar_rev_net, 0,
         dragon_deduct_note + "\n神州月结次月: 3月账单→4月底回款"),
        ("4月底", "GMI 回款（1-2月）", GMI_12_REV, 0,
         f"GMI 1月 ${GMI_JAN_REV:,} + 2月 ${GMI_FEB_REV:,} = ${GMI_12_REV:,}"),
        ("4月底", "支付 MateCloud（1-2月欠款）", 0, MC_12_COST,
         f"MC 1月 ${MC_JAN_COST:,} + 2月 ${MC_FEB_COST:,} = ${MC_12_COST:,}"),
        ("5月底", "神州数码 回款（4月·扣剩余垫资）", dragon_apr_rev_net, 0,
         f"神州 4月应收 ${dragon_apr_rev_gross:,} (billed ${EST_DRAGON_APR:,} x 0.47)\n"
         f"扣除剩余垫资 ${dragon_apr_deduct:,}，净回款 ${dragon_apr_rev_net:,}\n"
         "神州月结次月: 4月账单→5月底回款"),
        ("5月底", "GMI 回款（3月）", gmi_mar_rev, 0,
         f"GMI 3月 billed ${EST_GMI_MAR:,} x 0.65 = ${gmi_mar_rev:,}"),
        ("5月底", "支付 MateCloud（3月账单）", 0, mar_cost_A,
         f"全走MC: 3月总 billed ${EST_TOTAL_MAR:,} x 0.40 = ${mar_cost_A:,}\n"
         "MC 3月账期推迟到5月"),
        ("6月底", "GMI 回款（4月）", round(EST_GMI_APR * 0.65), 0,
         f"GMI 4月 billed ${EST_GMI_APR:,} x 0.65"),
        ("6月底", "支付 MateCloud（4月账单）", 0, apr_cost_A,
         f"4月总 billed ${EST_TOTAL_APR:,} x 0.40 = ${apr_cost_A:,}"),
    ]
    _write_events(ws_a, events_a, f)

    # ══════════════════════════════════════════════════════════════════════════
    # Sheet 2: 方案B — 全走知书万卷
    # ══════════════════════════════════════════════════════════════════════════
    ws_b = wb.add_worksheet("方案B-全走知书万卷")
    _tl_setup(ws_b, "方案 B：全部流量走知书万卷（成本 ×0.35）", f)

    # 全走知书: 3月成本 = 全量 x 0.35
    # 4/15前周结: (3/23~4/14) 23天的量 x 0.35，在4月中旬付
    # 4/15后月结: (4/15~4/30) 16天的量 x 0.35，在5月底付
    zs_mar_all = round(EST_TOTAL_MAR * 0.35)
    zs_pre415_all  = round(DAILY_TOTAL_BILLED * 23 * 0.35)  # 全量走知书
    zs_post415_all = round(DAILY_TOTAL_BILLED * 16 * 0.35)
    zs_apr_all     = round(EST_TOTAL_APR * 0.35)

    events_b = [
        ("3月底", "神州数码 垫资（预付款）", DRAGON_FUND, 0,
         "神州数码 3/26 $15万 + 4/3 $15万 = $30万\n"
         "性质: 预付款，后续从神州月结回款中扣除"),
        ("4月中旬", "支付知书万卷（3月全量·周结）", 0, zs_mar_all,
         f"全走知书: 3月总 billed ${EST_TOTAL_MAR:,} x 0.35 = ${zs_mar_all:,}\n"
         "3月仍为周结，4月中旬付清"),
        ("4月底", "神州数码 回款（3月·扣垫资）", dragon_mar_rev_net, 0,
         dragon_deduct_note + "\n神州月结次月: 3月账单→4月底回款"),
        ("4月底", "GMI 回款（1-2月）", GMI_12_REV, 0,
         f"${GMI_12_REV:,}"),
        ("4月底", "支付 MateCloud（1-2月欠款）", 0, MC_12_COST,
         f"历史欠款 ${MC_12_COST:,}，无论哪种方案都必须还"),
        ("4月底", "支付知书万卷（4/1~4/14·周结）", 0, zs_pre415_all,
         f"4/15前仍为周结: 14天 x ${DAILY_TOTAL_BILLED:,}/天 x 0.35\n"
         f"= ${zs_pre415_all:,}"),
        ("5月底", "神州数码 回款（4月·扣剩余垫资）", dragon_apr_rev_net, 0,
         f"应收 ${dragon_apr_rev_gross:,}，扣剩余垫资 ${dragon_apr_deduct:,}，净 ${dragon_apr_rev_net:,}\n"
         "神州月结次月: 4月账单→5月底回款"),
        ("5月底", "GMI 回款（3月）", gmi_mar_rev, 0,
         f"${gmi_mar_rev:,}"),
        ("5月底", "支付知书万卷（4/15~4/30·月结）", 0, zs_post415_all,
         f"4/15后月结: 16天 x ${DAILY_TOTAL_BILLED:,}/天 x 0.35\n"
         f"= ${zs_post415_all:,}"),
        ("6月底", "GMI 回款（4月）", round(EST_GMI_APR * 0.65), 0, ""),
        ("6月底", "支付知书万卷（5月·月结）", 0, zs_apr_all,
         f"5月全量月结: ${EST_TOTAL_APR:,} x 0.35 = ${zs_apr_all:,}\n"
         "(简化为与4月量级相同)"),
    ]
    _write_events(ws_b, events_b, f)

    # ══════════════════════════════════════════════════════════════════════════
    # Sheet 3: 方案C — 当前混合
    # ══════════════════════════════════════════════════════════════════════════
    ws_c = wb.add_worksheet("方案C-当前混合")
    _tl_setup(ws_c, "方案 C：当前混合（MC 63% + 知书 37%）", f)

    mc_mar_mix = round(EST_MC_MAR * 0.40)
    zs_mar_mix = round(EST_ZS_MAR * 0.35)
    mc_apr_mix = round(EST_MC_APR * 0.40)
    zs_apr_mix_pre  = round(DAILY_ZS54_BILLED * 14 * 0.35)  # 4/1~4/14 周结
    zs_apr_mix_post = round(DAILY_ZS54_BILLED * 16 * 0.35)  # 4/15~4/30 月结

    events_c = [
        ("3月底", "神州数码 垫资（预付款）", DRAGON_FUND, 0,
         "神州数码 3/26 $15万 + 4/3 $15万 = $30万\n"
         "性质: 预付款，后续从神州月结回款中扣除"),
        ("4月中旬", "支付知书万卷（3月份额·周结）", 0, zs_mar_mix,
         f"知书 3月 billed ${EST_ZS_MAR:,} x 0.35 = ${zs_mar_mix:,}\n"
         "3月仍为周结，4月中旬付清"),
        ("4月底", "神州数码 回款（3月·扣垫资）", dragon_mar_rev_net, 0,
         dragon_deduct_note + "\n神州月结次月: 3月账单→4月底回款"),
        ("4月底", "GMI 回款（1-2月）", GMI_12_REV, 0,
         f"${GMI_12_REV:,}"),
        ("4月底", "支付 MateCloud（1-2月欠款）", 0, MC_12_COST,
         f"${MC_12_COST:,}"),
        ("4月底", "支付知书万卷（4/1~4/14·周结）", 0, zs_apr_mix_pre,
         f"知书 4/1~4/14: 14天 x ${DAILY_ZS54_BILLED:,}/天 x 0.35 = ${zs_apr_mix_pre:,}"),
        ("5月底", "神州数码 回款（4月·扣剩余垫资）", dragon_apr_rev_net, 0,
         f"应收 ${dragon_apr_rev_gross:,}，扣剩余垫资 ${dragon_apr_deduct:,}，净 ${dragon_apr_rev_net:,}\n"
         "神州月结次月: 4月账单→5月底回款"),
        ("5月底", "GMI 回款（3月）", gmi_mar_rev, 0,
         f"${gmi_mar_rev:,}"),
        ("5月底", "支付 MateCloud（3月份额）", 0, mc_mar_mix,
         f"MC 3月 billed ${EST_MC_MAR:,} x 0.40 = ${mc_mar_mix:,}\n"
         "MC 3月账期推迟到5月"),
        ("5月底", "支付知书万卷（4/15~4/30·月结）", 0, zs_apr_mix_post,
         f"知书 4/15~4/30: 16天 x ${DAILY_ZS54_BILLED:,}/天 x 0.35 = ${zs_apr_mix_post:,}"),
        ("6月底", "GMI 回款（4月）", round(EST_GMI_APR * 0.65), 0, ""),
        ("6月底", "支付 MateCloud（4月份额）", 0, mc_apr_mix,
         f"MC 4月 billed ${EST_MC_APR:,} x 0.40 = ${mc_apr_mix:,}"),
        ("6月底", "支付知书万卷（5月·月结）", 0, round(EST_ZS_APR * 0.35),
         f"知书 5月月结 (量级同4月): ${EST_ZS_APR:,} x 0.35"),
    ]
    _write_events(ws_c, events_c, f)

    # ══════════════════════════════════════════════════════════════════════════
    # Sheet 4: 供应商方案对比
    # ══════════════════════════════════════════════════════════════════════════
    ws4 = wb.add_worksheet("供应商方案对比")
    ws4.hide_gridlines(2)
    ws4.set_column(0, 0, 38); ws4.set_column(1, 3, 20); ws4.set_column(4, 4, 55)

    ws4.merge_range(0, 0, 0, 4,
                    "供应商方案对比 — 基于 3/22 数据量级", f["title"])
    ws4.set_row(0, 28)
    ws4.merge_range(1, 0, 1, 4,
                    f"3/22: MC ${D22_MC:,} ({D22_MC_R:.0%}) + "
                    f"知书 ${D22_ZS:,} ({D22_ZS_R:.0%}) = "
                    f"${D22_TOTAL:,}/天  |  所有回款按月底到账", f["sub"])

    for c, h in enumerate(["指标", "A: 全走MC (x0.40)", "B: 全走知书 (x0.35)",
                            "C: 当前混合", "说明"]):
        hf = f["hdr_o"] if c == 1 else (f["hdr_g"] if c == 2 else f["hdr"])
        ws4.write(2, c, h, hf)
    ws4.set_row(2, 30); ws4.freeze_panes(3, 1)

    d22_cA = round(D22_TOTAL * 0.40)
    d22_cB = round(D22_TOTAL * 0.35)
    d22_cC = round(D22_MC * 0.40 + D22_ZS * 0.35)

    rows4 = [
        ("sec", "【单日对比 (3/22实际)】", None, None, None, ""),
        ("row", "  日 billed", D22_TOTAL, D22_TOTAL, D22_TOTAL,
         "客户消费总量不变"),
        ("row", "  日成本", d22_cA, d22_cB, d22_cC,
         f"B比A每天省 ${d22_cA - d22_cB:,}"),
        ("row", "  日成本率", 0.40, 0.35, d22_cC / D22_TOTAL, ""),

        ("sec", "【3月成本 (保守)】", None, None, None, ""),
        ("row", "  3月总 billed", EST_TOTAL_MAR, EST_TOTAL_MAR, EST_TOTAL_MAR, ""),
        ("row", "  3月成本", mar_cost_A, mar_cost_B, mar_cost_C,
         f"B比A省 ${mar_cost_A - mar_cost_B:,}"),
        ("row", "  3月付款时间", None, None, None,
         "A: MC可推迟到5月 | B: 周结4月中付 | C: 知书4月中付+MC5月付"),

        ("sec", "【4月成本 (保守)】", None, None, None, ""),
        ("row", "  4月总 billed", EST_TOTAL_APR, EST_TOTAL_APR, EST_TOTAL_APR, ""),
        ("row", "  4月成本", apr_cost_A, apr_cost_B, apr_cost_C,
         f"B比A省 ${apr_cost_A - apr_cost_B:,}/月"),
        ("row", "  4月付款节奏", None, None, None,
         "A: 5月付 | B: 4/1-14周结4月底付, 4/15-30月结5月底付 | C: 同B但知书仅37%"),

        ("sec", "【收入端 (与供应商无关)】", None, None, None, ""),
        ("row", "  神州垫资（预付款）", DRAGON_FUND, DRAGON_FUND, DRAGON_FUND,
         "3月底到账，后续从神州回款中扣除"),
        ("row", "  神州 3月应收 (x0.47)", dragon_mar_rev_gross, dragon_mar_rev_gross,
         dragon_mar_rev_gross,
         f"月结次月: 4月底到账，但需先扣垫资 ${DRAGON_FUND:,}"),
        ("row", "  神州 3月净回款", dragon_mar_rev_net, dragon_mar_rev_net,
         dragon_mar_rev_net,
         f"应收 ${dragon_mar_rev_gross:,} - 垫资 ${DRAGON_FUND:,} = ${dragon_mar_rev_net:,}"
         + (f"\n不够扣，剩余 ${dragon_apr_deduct:,} 从4月扣" if dragon_apr_deduct > 0 else "")),
        ("row", "  GMI 3月收入 (x0.65)", gmi_mar_rev, gmi_mar_rev, gmi_mar_rev,
         "GMI 月结次月: 5月底到账"),
        ("row", "  神州 4月净回款", dragon_apr_rev_net, dragon_apr_rev_net,
         dragon_apr_rev_net,
         f"应收 ${dragon_apr_rev_gross:,} - 剩余垫资 ${dragon_apr_deduct:,} = ${dragon_apr_rev_net:,}\n"
         "月结次月: 5月底到账"),
        ("row", "  GMI 4月收入 (x0.65)", round(EST_GMI_APR*0.65), round(EST_GMI_APR*0.65),
         round(EST_GMI_APR*0.65), "月结次月: 6月底到账"),
    ]

    # 4月底现金余额（关键节点）
    # 收入: 神州垫资 $30万 + 神州3月净回款 + GMI 1-2月 $48K
    # 支出: MC 1-2月欠款 + 各方案3月成本(如需在4月付)
    apr_end_in = DRAGON_FUND + dragon_mar_rev_net + GMI_12_REV
    apr_end_out_A = MC_12_COST
    apr_end_out_B = MC_12_COST + mar_cost_B + round(DAILY_TOTAL_BILLED * 14 * 0.35)
    apr_end_out_C = MC_12_COST + zs_mar_mix + zs_apr_mix_pre

    rows4 += [
        ("sec", "【4月底现金余额（关键节点）】", None, None, None, ""),
        ("row", "  4月底前总收入",
         apr_end_in, apr_end_in, apr_end_in,
         f"垫资 ${DRAGON_FUND:,} + 神州3月净回款 ${dragon_mar_rev_net:,} + GMI 1-2月 ${GMI_12_REV:,}"),
        ("row", "  4月底前总支出",
         apr_end_out_A, apr_end_out_B, apr_end_out_C,
         "A: 仅MC欠款 | B: MC欠款+3月全量+4月前半周结 | C: MC欠款+知书3月+知书4月前半"),
        ("row", "  4月底余额",
         apr_end_in - apr_end_out_A,
         apr_end_in - apr_end_out_B,
         apr_end_in - apr_end_out_C,
         "A方案因MC账期延长，4月底现金最充裕"),
    ]

    r4 = 3
    for i, (rt, label, va, vb, vc, note) in enumerate(rows4):
        a = i % 2 == 1
        if rt == "sec":
            ws4.write(r4, 0, label, f["sec"])
            for c, v in enumerate([va, vb, vc], 1):
                ws4.write(r4, c, round(v) if isinstance(v, (int, float)) and v is not None else "",
                          f["$b"] if v is not None else f["sec"])
            ws4.write(r4, 4, note, f["sec"])
        else:
            rf = f["ra"] if a else f["r"]
            nf = f["na"] if a else f["n"]
            ws4.write(r4, 0, label, rf)
            for c, v in enumerate([va, vb, vc], 1):
                if isinstance(v, float) and 0 < v < 1:
                    ws4.write(r4, c, v, f["%a"] if a else f["%"])
                elif isinstance(v, (int, float)) and v is not None:
                    ws4.write(r4, c, v, f["$a"] if a else f["$"])
                else:
                    ws4.write(r4, c, "" if v is None else v, rf)
            ws4.write(r4, 4, note, nf)
        r4 += 1

    # ══════════════════════════════════════════════════════════════════════════
    # Sheet 5: 垫资需求 & 安全量级
    # ══════════════════════════════════════════════════════════════════════════
    ws5 = wb.add_worksheet("垫资需求与安全量级")
    ws5.hide_gridlines(2)
    ws5.set_column(0, 0, 40); ws5.set_column(1, 2, 22); ws5.set_column(3, 3, 58)

    ws5.merge_range(0, 0, 0, 3,
                    "垫资需求 & 安全量级分析", f["title"])
    ws5.set_row(0, 28)
    ws5.merge_range(1, 0, 1, 3,
                    "MC 3月账期可推迟到5月 | 知书 4/15后改月结 | 所有回款按月底", f["sub"])

    for c, h in enumerate(["指标", "A: 全走MC (x0.40)", "B: 全走知书 (x0.35)", "说明"]):
        hf = f["hdr_o"] if c == 1 else (f["hdr_g"] if c == 2 else f["hdr"])
        ws5.write(2, c, h, hf)
    ws5.set_row(2, 26); ws5.freeze_panes(3, 1)

    # ── 关键窗口重新定义 ──
    # 神州月结次月: 3月账单→4月底回款（扣垫资），4月账单→5月底回款（扣剩余垫资）
    # 方案A: MC 3月推到5月，4月底前只需付 MC 1-2月欠款
    # 方案B: 知书3月周结4月中付 + 4/1~4/14周结4月底付

    NET_FIXED = GMI_12_REV - MC_12_COST

    # 5月收入: 神州4月净回款 + GMI 3月回款
    # 5月支出: 各方案不同
    may_in_A  = dragon_apr_rev_net + gmi_mar_rev
    may_out_A = mar_cost_A  # MC 3月账单5月付（MC 4月账单也5月付？不，MC月结次月付）
    # MC月结: 3月账单最迟5月付，4月账单6月付
    may_in_B  = dragon_apr_rev_net + gmi_mar_rev
    may_out_B = round(DAILY_TOTAL_BILLED * 16 * 0.35)  # 知书4/15~4/30月结部分

    cap_rows = [
        ("sec", "【4月底前 — 现金流窗口】", None, None, ""),
        ("row", "  收入: 神州垫资（预付款）", DRAGON_FUND, DRAGON_FUND,
         "3月底到账，性质为预付款"),
        ("row", "  收入: 神州3月回款（扣垫资后）", dragon_mar_rev_net, dragon_mar_rev_net,
         f"应收 ${dragon_mar_rev_gross:,} - 垫资 ${DRAGON_FUND:,} = ${dragon_mar_rev_net:,}\n"
         "月结次月: 4月底到账"),
        ("row", "  收入: GMI 1-2月回款", GMI_12_REV, GMI_12_REV, "4月到账"),
        ("row", "  支出: MC 1-2月欠款", MC_12_COST, MC_12_COST, "必须偿还"),
        ("row", "  支出: 3月供应商成本",
         0, mar_cost_B,
         "A: MC 3月推迟到5月付\nB: 知书3月周结，4月中旬付清"),
        ("row", "  支出: 4月前半供应商成本 (4/1~4/14)",
         0, round(DAILY_TOTAL_BILLED * 14 * 0.35),
         "A: MC月结，4月不付\nB: 知书周结部分，4月底前付"),
        ("row", "  4月底余额",
         apr_end_in - apr_end_out_A,
         apr_end_in - apr_end_out_B,
         "A方案因MC账期延长，4月底余额远高于B"),

        ("sec", "【5月 — 第二个压力窗口】", None, None, ""),
        ("row", "  收入: 神州4月回款（扣剩余垫资）", dragon_apr_rev_net, dragon_apr_rev_net,
         f"应收 ${dragon_apr_rev_gross:,} - 剩余垫资 ${dragon_apr_deduct:,} = ${dragon_apr_rev_net:,}\n"
         "月结次月: 5月底到账"),
        ("row", "  收入: GMI 3月回款 (x0.65)", gmi_mar_rev, gmi_mar_rev,
         "月结次月: 5月底到账"),
        ("row", "  5月总收入", may_in_A, may_in_B, ""),
        ("row", "  支出: MC 3月账单",
         mar_cost_A, 0,
         "A: MC 3月账单5月付 | B: 已在4月付清"),
        ("row", "  支出: 知书4/15~4/30月结",
         0, may_out_B,
         "B: 知书4/15后月结部分"),
        ("row", "  5月净现金流",
         may_in_A - mar_cost_A,
         may_in_B - may_out_B,
         ""),

        ("sec", "【累计到5月底的总余额】", None, None, ""),
    ]

    # 累计到5月底 (MC 4月账单6月才付，不在5月窗口内)
    cum5_A = (apr_end_in - apr_end_out_A) + may_in_A - mar_cost_A
    cum5_B = (apr_end_in - apr_end_out_B) + may_in_B - may_out_B
    cap_rows.append(("row", "  5月底累计余额", cum5_A, cum5_B,
                     f"A: ${cum5_A:,} | B: ${cum5_B:,}"))

    # ── 不同量级下的分析 ──
    cap_rows.append(("sec", "【如果神州不垫资 — 最大安全量级】", None, None, ""))

    # 方案A不垫资: 4月底前只需付MC欠款，收入仅GMI 1-2月
    # 余额 = GMI_12_REV - MC_12_COST = $17,838 (与量级无关！因为MC 3月推到5月)
    # 但5月要付MC 3月+4月成本，收入是GMI+神州3月回款
    # 5月: gmi_mar_rev + dragon_apr_rev_net - total_mar*0.40 >= ?
    # 即: total_billed 的约束来自5月
    cap_rows.append(("row", "  A: 4月底余额 (不垫资)",
                     NET_FIXED, None,
                     "A方案4月底余额与日量级无关（MC全推到5月）\n"
                     f"= GMI回款 ${GMI_12_REV:,} - MC欠款 ${MC_12_COST:,} = ${NET_FIXED:,}"))

    # 方案B不垫资: 4月底前要付 MC欠款 + 3月知书 + 4月前14天知书
    # GMI_12_REV - MC_12_COST - total_mar*0.35 - daily*14*0.35 >= 0
    # NET_FIXED >= (mar_sofar + daily*(9+14)) * 0.35
    # daily <= (NET_FIXED/0.35 - mar_sofar) / 23    (3月剩9天+4月前14天)
    # 但 mar_sofar 已经确认了，不能改
    # 实际: NET_FIXED - mar_sofar_already*0.35 - daily*23*0.35 >= 0 不对
    # 准确: 4月底支出 = MC_12_COST + (MAR_ZS_SOFAR + daily_zs*9 + daily_total*14)*0.35
    # 但全走知书时 3月已确认部分也要付
    # 简化: 假设从现在起日量级为 D
    # 4月底余额 = GMI_12_REV - MC_12_COST - (MAR_MC_SOFAR+MAR_ZS_SOFAR)*0.35 - D*23*0.35
    # 但已确认的3月数据不能改了
    mar_sofar_total = MAR_MC_SOFAR + MAR_ZS_SOFAR  # 514,530
    mar_sofar_cost_B = round(mar_sofar_total * 0.35)  # 180,086

    # 不垫资方案B: NET_FIXED - mar_sofar_cost_B - D*23*0.35 >= 0
    # D <= (NET_FIXED - mar_sofar_cost_B) / (23*0.35)
    # NET_FIXED - mar_sofar_cost_B = 17838 - 180086 = -162,248 已经是负的！
    # 说明即使日量级为0，已确认的3月成本就已经超过自有资金了
    cap_rows.append(("row", "  B: 3月已确认成本 (x0.35)",
                     None, mar_sofar_cost_B,
                     f"3月截至3/22已确认 billed ${mar_sofar_total:,} x 0.35\n"
                     f"= ${mar_sofar_cost_B:,}，已超过自有资金 ${NET_FIXED:,}"))
    cap_rows.append(("row", "  B: 不垫资已无法运营",
                     None, NET_FIXED - mar_sofar_cost_B,
                     "仅3月已确认成本就产生缺口，B方案必须有垫资"))

    # ── 有$30万垫资时 ──
    cap_rows.append(("sec", "【有神州$30万垫资 — 各方案安全量级】", None, None, ""))

    avail_30 = NET_FIXED + DRAGON_FUND  # 317,838

    # 方案A: 4月底余额 = 317,838（与量级无关）
    # 5月压力: 317838 + gmi_3m_rev + dragon_3m_rev - total_mar*0.40 - total_apr*0.40 >= 0
    # 收入端: GMI 3月 = (MAR_GMI_SOFAR + D_gmi * 9) * 0.65, 但GMI量级和供应商量级不完全一样
    # 简化: 假设 GMI 和 神州 的收入比例不变
    # 每日收入 = D_gmi * 0.65 + D_dragon * 0.47 (但这些是客户侧，和供应商侧量级不同)
    # 供应商侧每日成本 = D_supplier * 0.40
    # 这里的 D_supplier 和 D_gmi/D_dragon 不是同一个数
    # 实际上: 供应商成本 = 客户消费的底层成本
    # GMI 的消费走的是 MC/知书渠道，所以 GMI billed ≈ 供应商 billed 的一部分
    # 简化假设: 供应商总 billed = GMI billed + 神州 billed (因为他们是客户)

    cap_rows.append(("row", "  A: 4月底余额 (有$30万)",
                     avail_30, None,
                     f"${DRAGON_FUND:,} + ${GMI_12_REV:,} - ${MC_12_COST:,} = ${avail_30:,}\n"
                     "MC 3月推到5月，4月底余额与当前量级无关"))

    # A方案5月: 余额 + GMI3月rev + 神州3月rev - MC3月cost - MC4月cost >= 0
    # 317838 + (364638+D*9)*0.65 + (182583+D_drg*9)*0.47 - (total_mar+total_apr)*0.40 >= 0
    # 太复杂了，用数值方式计算不同量级
    cap_rows.append(("row", "  B: 4月底余额 (有$30万)",
                     None, avail_30 - mar_sofar_cost_B,
                     f"${avail_30:,} - 3月已确认成本 ${mar_sofar_cost_B:,}\n"
                     f"= ${avail_30 - mar_sofar_cost_B:,} (还需覆盖剩余天数成本)"))

    # B方案: 4月底余额 = 317838 - mar_sofar_cost_B - D*23*0.35
    # 要 >= 0: D <= (317838 - 180086) / (23*0.35) = 137752 / 8.05 = $17,112/天
    max_d_B_30 = (avail_30 - mar_sofar_cost_B) / (23 * 0.35)
    cap_rows.append(("row", "  B: $30万垫资下安全日量级",
                     None, round(max_d_B_30),
                     f"4月底不穿: D <= (${avail_30:,} - ${mar_sofar_cost_B:,}) / (23天 x 0.35)\n"
                     f"= ${max_d_B_30:,.0f}/天 (月 ${max_d_B_30*30:,.0f})"))

    cap_rows.append(("row", "  3/22量级 vs B安全线",
                     None, D22_TOTAL / max_d_B_30 if max_d_B_30 > 0 else 99,
                     f"${D22_TOTAL:,}/天 是安全线的 {D22_TOTAL/max_d_B_30:.1f}x"))

    # ── 垫资额度表 ──
    cap_rows.append(("sec", "【不同垫资额度 — B方案4月底不穿的安全日量级】", None, None, ""))
    for label, fund in [
        ("$0", 0), ("$10万", 100000), ("$20万", 200000),
        ("$30万 (已承诺)", 300000), ("$50万", 500000),
        ("$75万", 750000), ("$100万", 1000000),
        ("$150万", 1500000), ("$200万", 2000000),
    ]:
        avail = NET_FIXED + fund
        remain_for_new = avail - mar_sofar_cost_B
        if remain_for_new > 0:
            max_d = remain_for_new / (23 * 0.35)
            pct = D22_TOTAL / max_d
            cap_rows.append(("row", f"  垫资 {label}",
                             round(max_d * 0.40 / 0.35),  # A方案等效
                             round(max_d),
                             f"月 ${max_d*30:,.0f}，3/22量级占 {pct:.0%}"))
        else:
            cap_rows.append(("row", f"  垫资 {label}",
                             None, None,
                             f"不足以覆盖3月已确认成本 (缺 ${-remain_for_new:,})"))

    # 覆盖3/22峰值需要多少垫资
    # avail - mar_sofar_cost_B - D22_TOTAL * 23 * 0.35 >= 0
    # fund >= mar_sofar_cost_B + D22_TOTAL*23*0.35 - NET_FIXED
    need_peak = mar_sofar_cost_B + round(D22_TOTAL * 23 * 0.35) - NET_FIXED
    cap_rows.append(("sec",
                     f"【覆盖3/22峰值需垫资 (B方案)】",
                     None, need_peak,
                     f"3月已确认 ${mar_sofar_cost_B:,} + 23天x${D22_TOTAL:,}x0.35 - 自有 ${NET_FIXED:,}"))

    # A方案特殊: 4月底不穿与量级无关，压力在5月
    cap_rows.append(("sec", "【A方案: 5月压力分析 (MC 3月+4月账单集中到付)】", None, None, ""))
    # 5月余额 = 4月底余额 + 5月收入 - 5月支出
    # = avail_30 + 5月收入(神州4月净+GMI3月) - MC3月成本
    may_bal_A_conservative = avail_30 + gmi_mar_rev + dragon_apr_rev_net - mar_cost_A
    cap_rows.append(("row", "  5月底余额 (保守量级)",
                     may_bal_A_conservative, None,
                     f"4月底 ${avail_30:,} + GMI3月 ${gmi_mar_rev:,} + 神州4月净 ${dragon_apr_rev_net:,}\n"
                     f"- MC3月 ${mar_cost_A:,} (MC4月账单6月付，不在此窗口)"))
    cap_rows.append(("row", "  结论",
                     None, None,
                     "A方案: MC账期延长让4月非常安全，但5月集中付款压力大\n"
                     "B方案: 4月就要付知书3月+4月前半成本，但5月压力小\n"
                     "核心区别: 付款节奏不同，总成本B更低"))

    rc = 3
    for i, (rt, label, va, vb, note) in enumerate(cap_rows):
        a = i % 2 == 1
        if rt == "sec":
            ws5.write(rc, 0, label, f["sec"])
            for c, v in enumerate([va, vb], 1):
                if isinstance(v, (int, float)) and v is not None:
                    ws5.write(rc, c, v, f["$b"])
                else:
                    ws5.write(rc, c, "", f["sec"])
            ws5.write(rc, 3, note, f["sec"])
        else:
            rf = f["ra"] if a else f["r"]
            nf = f["na"] if a else f["n"]
            ws5.write(rc, 0, label, rf)
            for c, v in enumerate([va, vb], 1):
                if isinstance(v, float) and 0 < v < 1:
                    ws5.write(rc, c, v, f["%a"] if a else f["%"])
                elif isinstance(v, float) and v >= 1 and v < 100:
                    ws5.write(rc, c, f"{v:.1f}x", rf)
                elif isinstance(v, (int, float)) and v is not None:
                    ws5.write(rc, c, v, f["neg"] if v < 0 else (f["$a"] if a else f["$"]))
                else:
                    ws5.write(rc, c, "", rf)
            ws5.write(rc, 3, note, nf)
            ws5.set_row(rc, max(18, 15 * (note.count("\n") + 1)))
        rc += 1

    # ══════════════════════════════════════════════════════════════════════════
    # Sheet 6: 假设与说明
    # ══════════════════════════════════════════════════════════════════════════
    ws6 = wb.add_worksheet("假设与说明")
    ws6.hide_gridlines(2); ws6.set_column(0, 0, 90)
    ws6.write(0, 0, "现金流预测 — 假设条件与数据来源", f["title"])
    ws6.set_row(0, 28)

    notes = [
        "【商业模型】",
        "  收入端（客户付给我们）:",
        "    - GMI:    刊例价 x 0.65",
        "    - 神州数码: 刊例价 x 0.47 (flat_tier 低档价基准)",
        "  成本端（我们付给供应商）:",
        "    - MateCloud: 刊例价 x 0.40 (上游供应商, 渠道 ch24+ch25)",
        "    - 知书万卷:  刊例价 x 0.35 (上游供应商, 渠道 ch54, 比MC便宜5个点)",
        "",
        "【账期规则】",
        "  - MateCloud: 月结次月付，3月账单最迟可推迟到5月付",
        "  - 知书万卷: 4/15前周结（约1-2周后付），4/15后改为月结次月付",
        "  - GMI: 月结次月（3月账单→5月底到账）",
        "  - 神州数码: 月结次月（3月账单→4月底到账）",
        "  - 神州垫资 $30万 = 预付款，从后续神州回款中扣除",
        f"    3月应收 ${dragon_mar_rev_gross:,}，扣垫资后净回款 ${dragon_mar_rev_net:,}",
        f"    不够扣的 ${dragon_apr_deduct:,} 从4月回款中继续扣",
        "  - 所有回款统一按月底到账计算（保守）",
        "",
        "【数据来源】",
        "  - 1-2月: GMICloud_bill_2026-01.xlsx / 02.xlsx（精确值）",
        "  - 3月: logs_analysis.db，截至 2026-03-22 22:21 CST",
        "  - 保守预估: 3/18-3/22 近5天日均外推",
        "  - 峰值预估: 3/22 单日实际数据外推",
        "",
        "【已确认账单】",
        f"  - GMI 1月: billed ${GMI_JAN_BILLED:,} -> 收入 ${GMI_JAN_REV:,} (x0.65)",
        f"  - GMI 2月: billed ${GMI_FEB_BILLED:,} -> 收入 ${GMI_FEB_REV:,} (x0.65)",
        f"  - MC  1月: billed ${MC_JAN_BILLED:,} -> 成本 ${MC_JAN_COST:,} (x0.40)",
        f"  - MC  2月: billed ${MC_FEB_BILLED:,} -> 成本 ${MC_FEB_COST:,} (x0.40)",
        "",
        "【3/22 单日实际数据】",
        f"  - 全渠道总 billed:    ${D22_TOTAL:>10,}/天",
        f"  - MateCloud (ch24+25): ${D22_MC:>10,}/天 ({D22_MC_R:.0%})",
        f"  - 知书万卷 (ch54):     ${D22_ZS:>10,}/天 ({D22_ZS_R:.0%})",
        f"  - 全走MC日成本:        ${round(D22_TOTAL*0.40):>10,}/天",
        f"  - 全走知书日成本:       ${round(D22_TOTAL*0.35):>10,}/天",
        f"  - 日节省 (B vs A):     ${round(D22_TOTAL*0.05):>10,}/天",
        "",
        "【知书万卷 ch54 增长趋势】",
        "  - 3/19: $4,657/天 (上线首日)",
        "  - 3/20: $16,180/天 (+248%)",
        "  - 3/21: $22,731/天 (+40%)",
        "  - 3/22: $61,682/天 (+171%) <- 4天增长 13 倍",
        "",
        "【核心结论】",
        "  - A方案 (全走MC): 4月非常安全（MC 3月推到5月），但5月集中付款压力大",
        "  - B方案 (全走知书): 总成本低6个点，但4月就要付3月+4月前半成本",
        "  - 关键差异不在总成本（B始终更低），而在付款节奏",
        f"  - $30万垫资下B方案安全日量级仅 ~${max_d_B_30:,.0f}/天，3/22量级远超",
        f"  - 覆盖3/22峰值B方案需垫资 ${need_peak:,}",
        "",
        "【风险提示】",
        "  - 知书万卷增速极快（4天13倍），量级可能继续攀升",
        "  - A方案5月付MC 3月账单，需确保GMI+神州回款及时（MC 4月账单6月付）",
        "  - B方案4月现金流紧张，需要更多垫资或控制量级",
        "  - 两种方案可混合使用：大量走MC延账期，小量走知书降成本",
    ]

    for i, line in enumerate(notes):
        ws6.write(i + 1, 0, line, f["txts"] if line.startswith("【") else f["txt"])
        ws6.set_row(i + 1, 18)

    wb.close()
    print(f"[OK] {OUTPUT}")


if __name__ == "__main__":
    build_workbook()
