# -*- coding: utf-8 -*-
import sys, json, re
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd

df = pd.read_excel('output/fake_identity_raw.xlsx')
print(f"Total records: {len(df)}\n")

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

def classify(text):
    t = text.lower()
    if 'deepseek' in t or '\u6df1\u5ea6\u6c42\u7d22' in t:
        return 'DeepSeek'
    if 'kimi' in t or '\u6708\u4e4b\u6697\u9762' in t:
        return 'Kimi'
    if 'kiro' in t:
        return 'Kiro'
    return 'other'

df['text'] = df['resp'].apply(extract_text)
df['fake_type'] = df['text'].apply(classify)
df['date'] = pd.to_datetime(df['created_at']).dt.strftime('%m-%d')

# 1. Channel breakdown
print("=" * 65)
print("Channel x FakeType breakdown")
print("=" * 65)
ch_stats = df.groupby(['channel_id', 'channel_name', 'fake_type']).size().reset_index(name='count')
ch_stats = ch_stats.sort_values('count', ascending=False)
for _, r in ch_stats.iterrows():
    print(f"  ch{int(r['channel_id']):>3}  {str(r['channel_name']):<34} [{r['fake_type']:>8}]: {r['count']:>4}")

# 2. Date trend (fake only)
print("\n" + "=" * 65)
print("Date trend (fake identity only)")
print("=" * 65)
fake_only = df[df['fake_type'] != 'other']
trend = fake_only.groupby(['date', 'channel_id', 'fake_type']).size().reset_index(name='count')
for _, r in trend.sort_values(['date', 'channel_id']).iterrows():
    bar = chr(9608) * min(r['count'], 50)
    print(f"  {r['date']} ch{int(r['channel_id']):>3} [{r['fake_type']:>8}] {bar} ({r['count']})")

# 3. Sample records
print("\n" + "=" * 65)
print("Sample fake responses")
print("=" * 65)
for ft in ['DeepSeek', 'Kimi', 'Kiro']:
    subset = df[df['fake_type'] == ft]
    if len(subset) == 0:
        continue
    print(f"\n[{ft}] total={len(subset)}")
    for _, r in subset.head(4).iterrows():
        print(f"  {r['created_at']} ch{int(r['channel_id'])}({r['channel_name']}) {r['model']}")
        print(f"  >> {r['text'][:250]}")
        print()

# 4. Kiro system prompt analysis
print("=" * 65)
print("Kiro cases - system prompt check")
print("=" * 65)
kiro_df = df[df['fake_type'] == 'Kiro'].head(8)
for _, r in kiro_df.iterrows():
    try:
        req = json.loads(str(r['req']))
        msgs = req.get('messages', [])
        sys_msg = next((m.get('content', '') for m in msgs if m.get('role') == 'system'), None)
        if sys_msg:
            print(f"  ch{int(r['channel_id'])} HAS system prompt: {str(sys_msg)[:400]}")
        else:
            print(f"  ch{int(r['channel_id'])} NO system prompt in request (injected upstream) | model={r['model']}")
    except Exception as e:
        print(f"  ch{int(r['channel_id'])} parse error: {e}")

# 5. Summary stats
print("\n" + "=" * 65)
print("Summary")
print("=" * 65)
total_fake = len(df[df['fake_type'] != 'other'])
total_other = len(df[df['fake_type'] == 'other'])
print(f"  Confirmed fake identity responses : {total_fake}")
print(f"  Keyword match but not fake identity: {total_other}")
print(f"  Total scanned                      : {len(df)}")
type_counts = df[df['fake_type'] != 'other']['fake_type'].value_counts()
for k, v in type_counts.items():
    print(f"    {k}: {v}")
