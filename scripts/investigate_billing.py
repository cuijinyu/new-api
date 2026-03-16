"""排查新模型计费异常高的原因"""
import sys, sqlite3, json, datetime as dt
sys.stdout.reconfigure(encoding="utf-8")

conn = sqlite3.connect("logs_analysis.db")
cur = conn.cursor()

ts_start = int(dt.datetime(2026, 1, 1).timestamp())
ts_end   = int(dt.datetime(2026, 2, 1).timestamp())

# ── 1. 对比正常模型 vs 异常模型的 token 结构 ─────────────────────────────────
print("=" * 80)
print("1. 逐条对比：正常模型 vs 异常模型的 token 结构")
print("=" * 80)

for model, label in [
    ("claude-3-7-sonnet-20250219", "正常(3-7-sonnet)"),
    ("claude-opus-4-1-20250805",   "正常(opus-4-1)"),
    ("claude-opus-4-5-20251101",   "异常(opus-4-5)"),
    ("claude-sonnet-4-5-20250929", "异常(sonnet-4-5)"),
    ("claude-haiku-4-5-20251001",  "异常(haiku-4-5)"),
]:
    cur.execute(
        """SELECT id, quota, prompt_tokens, completion_tokens, other
           FROM logs WHERE username='GMICloud' AND type=2
             AND created_at>=? AND created_at<?
             AND model_name=?
           LIMIT 3""",
        (ts_start, ts_end, model),
    )
    rows = cur.fetchall()
    if not rows:
        continue
    print(f"\n--- {label}: {model} ---")
    for rid, quota, pt, ct, other_raw in rows:
        billed = quota / 500000
        try:
            o = json.loads(other_raw) if other_raw else {}
        except:
            o = {}
        ch = o.get("cache_tokens", 0) or 0
        cw = o.get("cache_creation_tokens", 0) or 0
        print(f"  id={rid}: pt={pt:,} ct={ct:,} quota={quota:,} billed=${billed:.6f}")
        print(f"    other: cache_hit={ch:,} cache_write={cw:,} net_input={max(pt-ch-cw,0):,}")
        # 按刊例价算应该是多少
        prices = {
            "claude-3-7-sonnet-20250219": (3, 15),
            "claude-opus-4-1-20250805":   (15, 75),
            "claude-opus-4-5-20251101":   (5, 25),
            "claude-sonnet-4-5-20250929": (3, 15),
            "claude-haiku-4-5-20251001":  (1, 5),
        }
        ip, op = prices[model]
        # 方式A：用 prompt_tokens 直接算（包含cache）
        cost_a = pt / 1e6 * ip + ct / 1e6 * op
        # 方式B：用 net_input 算（扣除cache）
        net = max(pt - ch - cw, 0)
        cost_b = net / 1e6 * ip + ct / 1e6 * op
        # 方式C：分项算（net_input*ip + cache_hit*chp + cache_write*cwp + output*op）
        print(f"    cost_A(pt*ip+ct*op)=${cost_a:.6f}  cost_B(net*ip+ct*op)=${cost_b:.6f}  billed=${billed:.6f}")
        print(f"    billed/cost_A={billed/cost_a:.2f}x  billed/cost_B={billed/cost_b:.2f}x" if cost_a > 0 and cost_b > 0 else "")

# ── 2. 统计 prompt_tokens 与 cache tokens 的关系 ─────────────────────────────
print("\n" + "=" * 80)
print("2. 按模型统计 prompt_tokens vs cache tokens 的关系")
print("=" * 80)

for model in [
    "claude-opus-4-5-20251101",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
    "claude-3-7-sonnet-20250219",
]:
    cur.execute(
        """SELECT id, prompt_tokens, completion_tokens, quota, other
           FROM logs WHERE username='GMICloud' AND type=2
             AND created_at>=? AND created_at<?
             AND model_name=?""",
        (ts_start, ts_end, model),
    )
    rows = cur.fetchall()
    if not rows:
        continue

    total_pt = 0
    total_ct = 0
    total_ch = 0
    total_cw = 0
    total_quota = 0
    cnt = 0

    for rid, pt, ct, quota, other_raw in rows:
        try:
            o = json.loads(other_raw) if other_raw else {}
        except:
            o = {}
        ch = o.get("cache_tokens", 0) or 0
        cw = o.get("cache_creation_tokens", 0) or 0
        total_pt += pt
        total_ct += ct
        total_ch += ch
        total_cw += cw
        total_quota += quota
        cnt += 1

    total_net = max(total_pt - total_ch - total_cw, 0)
    billed = total_quota / 500000

    print(f"\n{model} ({cnt:,}条)")
    print(f"  prompt_tokens总计: {total_pt:>15,}")
    print(f"  cache_hit总计:     {total_ch:>15,}")
    print(f"  cache_write总计:   {total_cw:>15,}")
    print(f"  net_input:         {total_net:>15,}")
    print(f"  completion_tokens: {total_ct:>15,}")
    print(f"  cache占prompt比:   {(total_ch+total_cw)/total_pt*100:.1f}%" if total_pt else "  N/A")
    print(f"  系统实收(USD):     ${billed:>14,.2f}")

# ── 3. 查看 quota 的计算逻辑 ─────────────────────────────────────────────────
print("\n" + "=" * 80)
print("3. 查看 other 字段中是否有 quota 计算相关信息")
print("=" * 80)

cur.execute(
    """SELECT id, model_name, quota, prompt_tokens, completion_tokens, other
       FROM logs WHERE username='GMICloud' AND type=2
         AND created_at>=? AND created_at<?
         AND model_name='claude-opus-4-5-20251101'
       LIMIT 1""",
    (ts_start, ts_end),
)
row = cur.fetchone()
if row:
    rid, model, quota, pt, ct, other_raw = row
    print(f"\nid={rid} model={model}")
    print(f"quota={quota:,} billed=${quota/500000:.6f}")
    print(f"pt={pt:,} ct={ct:,}")
    try:
        o = json.loads(other_raw)
        print(f"\nother 字段完整内容:")
        for k, v in sorted(o.items()):
            print(f"  {k}: {v}")
    except:
        print(f"other: {other_raw[:200]}")

# ── 4. 检查 quota 与各种计算方式的对应关系 ────────────────────────────────────
print("\n" + "=" * 80)
print("4. 尝试反推 quota 的计算公式")
print("=" * 80)

cur.execute(
    """SELECT id, model_name, quota, prompt_tokens, completion_tokens, other
       FROM logs WHERE username='GMICloud' AND type=2
         AND created_at>=? AND created_at<?
         AND model_name IN ('claude-opus-4-5-20251101','claude-sonnet-4-5-20250929')
       LIMIT 10""",
    (ts_start, ts_end),
)

QUOTA_PER_USD = 500000
for rid, model, quota, pt, ct, other_raw in cur.fetchall():
    try:
        o = json.loads(other_raw) if other_raw else {}
    except:
        o = {}
    ch = o.get("cache_tokens", 0) or 0
    cw = o.get("cache_creation_tokens", 0) or 0
    net = max(pt - ch - cw, 0)

    # 各种假设
    prices = {"claude-opus-4-5-20251101": (5, 25, 0.5, 6.25),
              "claude-sonnet-4-5-20250929": (3, 15, 0.3, 3.75)}
    ip, op, chp, cwp = prices[model]

    # 假设1：quota = (net*ip + ct*op + ch*chp + cw*cwp) / 1e6 * QUOTA_PER_USD
    expected_1 = (net/1e6*ip + ct/1e6*op + ch/1e6*chp + cw/1e6*cwp) * QUOTA_PER_USD

    # 假设2：quota = (pt*ip + ct*op) / 1e6 * QUOTA_PER_USD（把cache也按input价算）
    expected_2 = (pt/1e6*ip + ct/1e6*op) * QUOTA_PER_USD

    # 假设3：quota 直接等于 token 数的某个倍数？
    ratio_pt = quota / pt if pt else 0

    print(f"id={rid} {model[:20]:20s} quota={quota:>10,} pt={pt:>8,} ct={ct:>6,} ch={ch:>8,} cw={cw:>8,}")
    print(f"  假设1(分项计费): {expected_1:>10,.0f}  差={quota-expected_1:>+10,.0f}  比={quota/expected_1:.4f}x" if expected_1 else "")
    print(f"  假设2(pt全按ip):  {expected_2:>10,.0f}  差={quota-expected_2:>+10,.0f}  比={quota/expected_2:.4f}x" if expected_2 else "")
    print(f"  quota/pt={ratio_pt:.4f}")

conn.close()
