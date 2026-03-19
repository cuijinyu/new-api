import sqlite3, json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

conn = sqlite3.connect('logs_analysis.db')
c = conn.cursor()

QPU = 500_000.0

print("quota 整数截断误差详解")
print("=" * 100)
print("""
平台计费流程 (service/quota.go):

  step 1:  model_price = input*价格 + output*价格 + cache*价格  (float64, 精确美元)
  step 2:  quota = int(model_price * 500000)     ← 这里 int() 截断小数
  step 3:  写入 DB logs 表的 quota 字段 (整数)

平台展示费用:
  cost = sum(quota) / 500000

问题: int() 会丢掉小数部分, 每条请求最多丢 1/500000 = $0.000002
""")

# 真实数据演示
c.execute("""SELECT quota, other FROM logs 
             WHERE type=2 AND model_name='claude-opus-4-6' 
             AND DATE(created_at, 'unixepoch')='2026-03-11' AND other IS NOT NULL
             AND quota > 1000
             LIMIT 8""")

print(f"{'model_price':>14} {'exact*500k':>16} {'int()截断':>12} {'还原/500k':>14} {'损失':>12}")
print("-" * 75)

for quota, other_json in c.fetchall():
    o = json.loads(other_json)
    mp = o.get("model_price", 0)
    if mp <= 0:
        continue
    exact = mp * QPU
    restored = quota / QPU
    loss = mp - restored
    print(f"${mp:>13.6f} {exact:>16.1f} {quota:>12,} ${restored:>13.6f} ${loss:>11.8f}")

print()
print("=" * 100)
print("3月11日全量统计:")
print("=" * 100)

c.execute("""SELECT model_name, quota, other FROM logs 
             WHERE type=2 AND DATE(created_at, 'unixepoch')='2026-03-11' AND other IS NOT NULL""")

model_stats = {}
for model, quota, other_json in c.fetchall():
    o = json.loads(other_json)
    mp = o.get("model_price", 0)
    if mp > 0:
        if model not in model_stats:
            model_stats[model] = {"mp": 0.0, "quota": 0, "cnt": 0}
        model_stats[model]["mp"] += mp
        model_stats[model]["quota"] += quota
        model_stats[model]["cnt"] += 1

grand_mp = 0.0
grand_quota = 0
print(f"\n{'Model':<35} {'条数':>8} {'model_price':>16} {'quota/500k':>16} {'截断损失':>12}")
print("-" * 92)

for model in sorted(model_stats.keys(), key=lambda m: model_stats[m]["mp"], reverse=True):
    s = model_stats[model]
    qc = s["quota"] / QPU
    diff = s["mp"] - qc
    grand_mp += s["mp"]
    grand_quota += s["quota"]
    print(f"{model:<35} {s['cnt']:>8,} ${s['mp']:>15,.6f} ${qc:>15,.6f} ${diff:>11.6f}")

grand_qc = grand_quota / QPU
grand_diff = grand_mp - grand_qc

print("-" * 92)
print(f"{'TOTAL':<35} {'':>8} ${grand_mp:>15,.6f} ${grand_qc:>15,.6f} ${grand_diff:>11.6f}")

print(f"""
结论:
  精确 model_price 合计: ${grand_mp:,.6f}
  int截断后 quota 合计:  ${grand_qc:,.6f}
  截断总损失:            ${grand_diff:,.6f}  (占比 {grand_diff/grand_mp*100:.6f}%)

  每条最多丢 $0.000002, 78000 条最多丢 ${78000*0.000002:.4f}
  实际损失 ${grand_diff:.4f} — 完全可忽略, 不是差异的主因
""")

conn.close()
