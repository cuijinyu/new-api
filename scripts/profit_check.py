import sys, sqlite3, datetime as dt
sys.stdout.reconfigure(encoding="utf-8")

# Anthropic 官方刊例价 (USD/M tokens) — 2025-2026
official = {
    "claude-opus-4-5-20251101":  {"ip": 5,  "op": 25},
    "claude-opus-4-6":           {"ip": 5,  "op": 25},
    "claude-sonnet-4-5-20250929":{"ip": 3,  "op": 15},
    "claude-sonnet-4-6":         {"ip": 3,  "op": 15},
    "claude-haiku-4-5-20251001": {"ip": 1,  "op": 5},
    "claude-3-7-sonnet-20250219":{"ip": 3,  "op": 15},
    "claude-opus-4-1-20250805":  {"ip": 15, "op": 75},
    "claude-opus-4-20250514":    {"ip": 15, "op": 75},
    "claude-sonnet-4-20250514":  {"ip": 3,  "op": 15},
}

ts_start = int(dt.datetime(2026, 1, 1).timestamp())
ts_end   = int(dt.datetime(2026, 2, 1).timestamp())

conn = sqlite3.connect("logs_analysis.db")
cur = conn.cursor()
cur.execute(
    """SELECT model_name,
              SUM(quota)*1.0/500000,
              SUM(prompt_tokens),
              SUM(completion_tokens),
              COUNT(*)
       FROM logs WHERE username='GMICloud' AND type=2
         AND created_at>=? AND created_at<?
         AND model_name LIKE '%claude%'
       GROUP BY model_name
       ORDER BY SUM(quota) DESC""",
    (ts_start, ts_end),
)
rows = cur.fetchall()
conn.close()

total_billed = 0.0
total_official = 0.0

print("1月 GMICloud Claude 各模型计费 vs 刊例价")
print(f"{'模型':35s} {'系统实收':>12s} {'刊例价':>12s} {'比值':>8s}")
print("-" * 75)

for model, billed, pt, ct, cnt in rows:
    off = official.get(model)
    if not off:
        print(f"{model:35s} ${billed:10,.2f}  (无官方价)")
        continue
    official_cost = pt / 1e6 * off["ip"] + ct / 1e6 * off["op"]
    ratio = billed / official_cost if official_cost else 0
    total_billed += billed
    total_official += official_cost
    print(f"{model:35s} ${billed:10,.2f}  ${official_cost:10,.2f}  {ratio:.4f}x")

print("-" * 75)
ratio_all = total_billed / total_official if total_official else 0
print(f"{'合计':35s} ${total_billed:10,.2f}  ${total_official:10,.2f}  {ratio_all:.4f}x")

print("\n=== 利润计算（两种理解） ===\n")

print("理解A：系统按刊例价收费（MateCloud额度=系统实收=刊例价）")
print(f"  收入 = 系统实收 = ${total_billed:,.2f}")
print(f"  成本 = 系统实收 * 0.41 = ${total_billed * 0.41:,.2f}")
print(f"  利润 = ${total_billed * 0.59:,.2f}")
print(f"  利润率 = 59.0%")

print()
print("理解B：我们收GMI 6.5折，付MateCloud 4.1折（都基于刊例价）")
rev_65 = total_official * 0.65
cost_41 = total_official * 0.41
print(f"  收入 = 刊例价 * 0.65 = ${rev_65:,.2f}")
print(f"  成本 = 刊例价 * 0.41 = ${cost_41:,.2f}")
print(f"  利润 = ${rev_65 - cost_41:,.2f}")
print(f"  利润率 = {(rev_65 - cost_41) / rev_65 * 100:.1f}%")

print()
print("理解B下，系统实收 vs 应收(6.5折):")
print(f"  系统实收: ${total_billed:,.2f}")
print(f"  应收6.5折: ${rev_65:,.2f}")
print(f"  差异: ${total_billed - rev_65:,.2f} (系统多收了)")
