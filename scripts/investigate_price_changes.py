"""排查系统迭代导致的计费差异：按天/按周分析 expected vs billed 的偏差"""
import sys, sqlite3, json, datetime as dt
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8")

QUOTA_PER_USD = 500_000

# pricing.json 当前价格（刊例价）
PRICING = {
    "claude-opus-4-5-20251101": [
        {"min_k": 0,   "max_k": 200, "ip": 5,  "op": 25,   "chp": 0.5, "cwp": 6.25, "cwp_1h": 10},
        {"min_k": 200, "max_k": -1,  "ip": 10, "op": 37.5, "chp": 1.0, "cwp": 12.5, "cwp_1h": 20},
    ],
    "claude-sonnet-4-5-20250929": [
        {"min_k": 0,   "max_k": 200, "ip": 3, "op": 15,   "chp": 0.3, "cwp": 3.75, "cwp_1h": 6},
        {"min_k": 200, "max_k": -1,  "ip": 6, "op": 22.5, "chp": 0.6, "cwp": 7.5,  "cwp_1h": 12},
    ],
    "claude-haiku-4-5-20251001": {"ip": 1, "op": 5, "chp": 0.1, "cwp": 1.25, "cwp_1h": 1.25},
    "claude-3-7-sonnet-20250219": {"ip": 3, "op": 15, "chp": 0.3, "cwp": 3.75, "cwp_1h": 3.75},
    "claude-opus-4-1-20250805":   {"ip": 15, "op": 75, "chp": 1.5, "cwp": 18.75, "cwp_1h": 18.75},
    "claude-opus-4-20250514":     {"ip": 15, "op": 75, "chp": 1.5, "cwp": 18.75, "cwp_1h": 18.75},
    "claude-sonnet-4-20250514": [
        {"min_k": 0,   "max_k": 200, "ip": 3, "op": 15,   "chp": 0.3, "cwp": 3.75, "cwp_1h": 6},
        {"min_k": 200, "max_k": -1,  "ip": 6, "op": 22.5, "chp": 0.6, "cwp": 7.5,  "cwp_1h": 12},
    ],
}


def get_tier(p, pt):
    if not isinstance(p, list):
        return p
    for t in p:
        if pt // 1000 >= t["min_k"] and (t["max_k"] == -1 or pt // 1000 < t["max_k"]):
            return t
    return p[-1]


def calc_expected(model, pt, ct, other_raw):
    """用当前 pricing.json 计算 expected USD"""
    try:
        o = json.loads(other_raw) if other_raw else {}
    except:
        o = {}
    p = PRICING.get(model)
    if not p:
        return None

    ch = o.get("cache_tokens", 0) or 0
    cw = o.get("cache_creation_tokens", 0) or 0
    cw_5m = o.get("tiered_cache_creation_tokens_5m") or o.get("cache_creation_tokens_5m", 0) or 0
    cw_1h = o.get("tiered_cache_creation_tokens_1h") or o.get("cache_creation_tokens_1h", 0) or 0
    cw_rem = max(cw - cw_5m - cw_1h, 0)
    net = max(pt - ch - cw, 0)

    tier = get_tier(p, pt)
    ip  = tier.get("ip", 0)
    op  = tier.get("op", 0)
    chp = tier.get("chp", 0)
    cwp = tier.get("cwp", 0)
    cwp_1h = tier.get("cwp_1h", cwp)

    is_new = "tiered_cache_store_price" in o
    if is_new:
        chp = o.get("tiered_cache_hit_price") or chp
        cwp_5m_price = o.get("tiered_cache_store_price_5m") or o.get("tiered_cache_store_price") or cwp
        cwp_1h_price = o.get("tiered_cache_store_price_1h") or cwp_1h
        cwp_rem_price = o.get("tiered_cache_store_price") or cwp
    else:
        cwp_5m_price = cwp
        cwp_1h_price = cwp_1h
        cwp_rem_price = cwp

    usd = (net / 1e6 * ip + ct / 1e6 * op + ch / 1e6 * chp
           + cw_5m / 1e6 * cwp_5m_price + cw_1h / 1e6 * cwp_1h_price
           + cw_rem / 1e6 * cwp_rem_price)
    return usd


def calc_from_ratios(pt, ct, other_raw):
    """用 other 字段里的 ratio 反推系统实际计费 USD"""
    try:
        o = json.loads(other_raw) if other_raw else {}
    except:
        o = {}
    mr  = o.get("model_ratio", 0)
    cr  = o.get("completion_ratio", 0)
    chr_ = o.get("cache_ratio", 0)
    ccr = o.get("cache_creation_ratio", 0)
    ccr_1h = o.get("cache_creation_ratio_1h", 0)
    gr  = o.get("group_ratio", 1)

    ch = o.get("cache_tokens", 0) or 0
    cw = o.get("cache_creation_tokens", 0) or 0
    cw_5m = o.get("tiered_cache_creation_tokens_5m") or o.get("cache_creation_tokens_5m", 0) or 0
    cw_1h = o.get("tiered_cache_creation_tokens_1h") or o.get("cache_creation_tokens_1h", 0) or 0
    cw_rem = max(cw - cw_5m - cw_1h, 0)
    net = max(pt - ch - cw, 0)

    # ratio 系统公式
    promptQuota = net + ch * chr_ + cw_5m * ccr + cw_1h * ccr_1h + cw_rem * ccr
    completionQuota = ct * cr
    ratio = mr * gr

    # 200K 检查
    totalInput = pt + ch + cw
    if totalInput > 200000:
        q = promptQuota * ratio * 2.0 + completionQuota * ratio * 1.5
    else:
        q = (promptQuota + completionQuota) * ratio

    return q / QUOTA_PER_USD


conn = sqlite3.connect("logs_analysis.db")
cur = conn.cursor()

for month_label, ts_start, ts_end in [
    ("2026-01", int(dt.datetime(2026,1,1).timestamp()), int(dt.datetime(2026,2,1).timestamp())),
    ("2026-02", int(dt.datetime(2026,2,1).timestamp()), int(dt.datetime(2026,3,1).timestamp())),
]:
    cur.execute(
        """SELECT id, model_name, quota, prompt_tokens, completion_tokens, other,
                  date(created_at,'unixepoch','+8 hours') AS day
           FROM logs WHERE username='GMICloud' AND type=2
             AND created_at>=? AND created_at<?
             AND model_name LIKE '%claude%'
           ORDER BY created_at""",
        (ts_start, ts_end),
    )
    rows = cur.fetchall()

    print(f"\n{'='*80}")
    print(f"{month_label}: {len(rows):,} 条")
    print(f"{'='*80}")

    # 按天+模型统计差异
    daily = defaultdict(lambda: {"billed": 0, "expected": 0, "ratio_calc": 0, "count": 0})

    for rid, model, quota, pt, ct, other_raw, day in rows:
        billed = quota / QUOTA_PER_USD
        exp = calc_expected(model, pt, ct, other_raw)
        ratio_usd = calc_from_ratios(pt, ct, other_raw)
        if exp is None:
            continue
        k = (day, model)
        daily[k]["billed"] += billed
        daily[k]["expected"] += exp
        daily[k]["ratio_calc"] += ratio_usd
        daily[k]["count"] += 1

    # 找差异最大的天+模型
    diffs = []
    for (day, model), v in daily.items():
        diff_exp = v["billed"] - v["expected"]
        diff_ratio = v["billed"] - v["ratio_calc"]
        diffs.append((day, model, v["count"], v["billed"], v["expected"], diff_exp,
                       v["ratio_calc"], diff_ratio))

    diffs.sort(key=lambda x: abs(x[5]), reverse=True)

    print(f"\n--- 按天+模型：billed vs expected(pricing.json) 差异最大的 Top 15 ---")
    print(f"{'日期':12s} {'模型':35s} {'条数':>6s} {'实收':>12s} {'应收':>12s} {'差额':>12s} {'ratio重算':>12s} {'ratio差':>12s}")
    print("-" * 120)
    for day, model, cnt, billed, exp, diff_e, ratio_c, diff_r in diffs[:15]:
        print(f"{day:12s} {model:35s} {cnt:6,} ${billed:10,.2f} ${exp:10,.2f} ${diff_e:+10,.2f} ${ratio_c:10,.2f} ${diff_r:+10,.2f}")

    # 汇总
    total_billed = sum(v["billed"] for v in daily.values())
    total_exp = sum(v["expected"] for v in daily.values())
    total_ratio = sum(v["ratio_calc"] for v in daily.values())
    print(f"\n汇总:")
    print(f"  系统实收:          ${total_billed:,.2f}")
    print(f"  pricing.json重算:  ${total_exp:,.2f}  差额=${total_billed-total_exp:+,.2f}")
    print(f"  ratio公式重算:     ${total_ratio:,.2f}  差额=${total_billed-total_ratio:+,.2f}")

    # 按模型汇总差异
    model_diff = defaultdict(lambda: {"billed": 0, "expected": 0, "ratio_calc": 0})
    for (day, model), v in daily.items():
        model_diff[model]["billed"] += v["billed"]
        model_diff[model]["expected"] += v["expected"]
        model_diff[model]["ratio_calc"] += v["ratio_calc"]

    print(f"\n--- 按模型汇总差异 ---")
    for model in sorted(model_diff.keys(), key=lambda m: -abs(model_diff[m]["billed"] - model_diff[m]["expected"])):
        v = model_diff[model]
        diff_e = v["billed"] - v["expected"]
        diff_r = v["billed"] - v["ratio_calc"]
        print(f"  {model:35s} 实收=${v['billed']:10,.2f}  pricing差=${diff_e:+10,.2f}  ratio差=${diff_r:+10,.2f}")

    # 按周看趋势
    print(f"\n--- 按周看差异趋势 ---")
    weekly = defaultdict(lambda: {"billed": 0, "expected": 0, "ratio_calc": 0})
    for (day, model), v in daily.items():
        # 取周一
        d = dt.datetime.strptime(day, "%Y-%m-%d")
        week_start = (d - dt.timedelta(days=d.weekday())).strftime("%Y-%m-%d")
        weekly[week_start]["billed"] += v["billed"]
        weekly[week_start]["expected"] += v["expected"]
        weekly[week_start]["ratio_calc"] += v["ratio_calc"]

    for week in sorted(weekly.keys()):
        v = weekly[week]
        diff_e = v["billed"] - v["expected"]
        diff_r = v["billed"] - v["ratio_calc"]
        pct = diff_e / v["expected"] * 100 if v["expected"] else 0
        print(f"  周{week}: 实收=${v['billed']:8,.2f}  pricing差=${diff_e:+8,.2f} ({pct:+.1f}%)  ratio差=${diff_r:+8,.2f}")

conn.close()
