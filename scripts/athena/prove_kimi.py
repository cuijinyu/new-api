# -*- coding: utf-8 -*-
"""
Prove whether Kimi/DeepSeek records are:
  A) Model self-identifying as Kimi/DeepSeek  (identity claim)
  B) User content mentioning Kimi/DeepSeek    (topic mention)
"""
import sys, json, re
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd

df = pd.read_excel('output/fake_identity_raw.xlsx')

# ── helpers ──────────────────────────────────────────────────────────────────

def extract_text(resp_str):
    s = str(resp_str)
    parts = re.findall(r'"text":"((?:[^"\\]|\\.)*)"', s)
    if parts:
        return ''.join(parts).replace('\\n', '\n').replace('\\"', '"')
    try:
        j = json.loads(s)
        return (j.get('choices') or [{}])[0].get('message', {}).get('content', '') or \
               (j.get('content') or [{}])[0].get('text', '')
    except:
        return ''

def extract_user_q(req_str):
    try:
        j = json.loads(str(req_str))
        msgs = j.get('messages', [])
        user_msgs = [m for m in msgs if m.get('role') == 'user']
        last = user_msgs[-1].get('content', '') if user_msgs else ''
        if isinstance(last, list):
            last = ' '.join(x.get('text', '') for x in last if isinstance(x, dict))
        return str(last)[:400]
    except:
        return ''

def is_identity_claim(text):
    """True if the model is saying IT IS Kimi/DeepSeek/Kiro."""
    t = text
    # Chinese self-intro patterns
    patterns_cn = [
        '\u6211\u662f Kimi', '\u6211\u662fKimi',
        '\u6211\u662f DeepSeek', '\u6211\u662fDeepSeek',
        '\u6211\u662f\u6df1\u5ea6\u6c42\u7d22',
        '\u6211\u662f Kiro', '\u6211\u662fKiro',
        '\u6211\u53eb Kimi', '\u6211\u53ebKimi',
        'Kimi\uff0c\u4e00\u4e2a', 'Kimi\uff0c\u4e00\u6b3e',
        'DeepSeek\uff0c\u4e00\u4e2a', 'DeepSeek\uff0c\u4e00\u6b3e',
    ]
    # English self-intro patterns
    patterns_en = [
        "I'm Kimi", "I am Kimi",
        "I'm DeepSeek", "I am DeepSeek",
        "I'm Kiro", "I am Kiro",
        "My name is Kimi", "My name is Kiro",
    ]
    for p in patterns_cn + patterns_en:
        if p.lower() in t.lower():
            return True
    return False

def topic_signal(text):
    """What is the main topic? Returns string."""
    t = text.lower()
    if 'kimi-k2' in t or 'kimi k2' in t:
        return 'kimi-k2 model deployment'
    if 'deepseek-v4' in t or 'deepseek v4' in t or 'v4\u9884\u89c8' in t:
        return 'deepseek-v4 news/content'
    if '\u9192\u6765' in text or '\u534a\u5e74' in text:
        return 'deepseek article/essay'
    if 'ray cluster' in t or 'h200' in t or '\u96c6\u7fa4' in text:
        return 'infrastructure/cluster work'
    return ''

df['text'] = df['resp'].apply(extract_text)
df['user_q'] = df['req'].apply(extract_user_q)
df['is_id_claim'] = df['text'].apply(is_identity_claim)

# ── Section 1: All confirmed identity claims ──────────────────────────────────
id_df = df[df['is_id_claim']]
print("=" * 70)
print(f"CONFIRMED IDENTITY CLAIMS: {len(id_df)} records")
print("=" * 70)
for _, r in id_df.iterrows():
    print(f"  {r['created_at']} | ch{int(r['channel_id'])}({r['channel_name']}) | {r['model']}")
    print(f"  Q: {r['user_q'][:100]}")
    print(f"  A: {r['text'][:300]}")
    print()

# ── Section 2: Kimi records breakdown ─────────────────────────────────────────
kimi_mask = df['text'].str.lower().str.contains('kimi', na=False)
kimi_df = df[kimi_mask]
print("=" * 70)
print(f"ALL KIMI-KEYWORD RECORDS: {len(kimi_df)} total")
print("=" * 70)

id_claims = kimi_df[kimi_df['is_id_claim']]
topic_mentions = kimi_df[~kimi_df['is_id_claim']]

print(f"  Identity claims (model says 'I am Kimi'): {len(id_claims)}")
print(f"  Topic mentions (user talking about Kimi): {len(topic_mentions)}\n")

print("-- Topic mention details --")
for _, r in topic_mentions.iterrows():
    sig = topic_signal(r['text'])
    print(f"  ch{int(r['channel_id'])} | {sig or 'misc'}")
    print(f"  Q: {r['user_q'][:120]}")
    print(f"  A: {r['text'][:180]}")
    print()

# ── Section 3: DeepSeek records breakdown ────────────────────────────────────
ds_mask = df['text'].str.lower().str.contains('deepseek', na=False)
ds_df = df[ds_mask]
print("=" * 70)
print(f"ALL DEEPSEEK-KEYWORD RECORDS: {len(ds_df)} total")
print("=" * 70)

ds_id = ds_df[ds_df['is_id_claim']]
ds_topic = ds_df[~ds_df['is_id_claim']]
print(f"  Identity claims: {len(ds_id)}")
print(f"  Topic mentions : {len(ds_topic)}\n")

# Sample 5 topic-mention responses
print("-- Topic mention samples (first 5) --")
for _, r in ds_topic.head(5).iterrows():
    sig = topic_signal(r['text'])
    print(f"  ch{int(r['channel_id'])} | {sig or 'misc'}")
    print(f"  Q: {r['user_q'][:120]}")
    print(f"  A: {r['text'][:200]}")
    print()

# ── Section 4: Final verdict ──────────────────────────────────────────────────
print("=" * 70)
print("VERDICT")
print("=" * 70)
total_id = len(df[df['is_id_claim']])
print(f"  True identity claims (model = DeepSeek/Kimi/Kiro): {total_id}")
print(f"  Keyword mentions (user content about these models): {len(df) - total_id}")
print()
print("  Channel breakdown of TRUE identity claims:")
if total_id > 0:
    for _, r in df[df['is_id_claim']].groupby(['channel_id','channel_name']).size().reset_index(name='n').iterrows():
        print(f"    ch{int(r['channel_id'])} {r['channel_name']}: {r['n']} claims")
else:
    print("    (none found with strict pattern matching)")
    print()
    print("  NOTE: The earlier 'Kimi' hits were users discussing Kimi-K2.6 deployment,")
    print("  not the model self-identifying. Need identity-question-triggered queries.")
