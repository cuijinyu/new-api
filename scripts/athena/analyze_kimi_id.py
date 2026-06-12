# -*- coding: utf-8 -*-
"""Find all Kimi self-identification cases (handles markdown formatting)."""
import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd

# Load both datasets
df1 = pd.read_excel('output/fake_identity_raw.xlsx')
df2 = pd.read_excel('output/kiro_records.xlsx')
df = pd.concat([df1, df2], ignore_index=True).drop_duplicates(subset=['created_at','channel_id'])
print(f"Total unique records: {len(df)}\n")

def extract_text_safe(resp_str):
    s = str(resp_str)
    texts = []
    for line in s.split('\\n'):
        if '"text":' in line:
            try:
                start = line.index('"text":') + 7
                rem = line[start:].strip().lstrip('"')
                end = 0
                while end < len(rem):
                    if rem[end] == '"' and (end == 0 or rem[end-1] != '\\'):
                        break
                    end += 1
                texts.append(rem[:end])
            except:
                pass
    if texts:
        return ''.join(texts).replace('\\n', '\n').replace('\\"', '"')
    try:
        j = json.loads(s)
        return (j.get('choices') or [{}])[0].get('message', {}).get('content', '') or \
               (j.get('content') or [{}])[0].get('text', '')
    except:
        return s[:500]

def extract_user_q(req_str):
    try:
        j = json.loads(str(req_str))
        msgs = j.get('messages', [])
        user_msgs = [m for m in msgs if m.get('role') == 'user']
        last = user_msgs[-1].get('content', '') if user_msgs else ''
        if isinstance(last, list):
            last = ' '.join(x.get('text', '') for x in last if isinstance(x, dict))
        return str(last)[:200]
    except:
        return ''

def is_kimi_id(text):
    """Check if model identifies itself as Kimi - handles markdown and spacing."""
    t = text
    # Strip markdown bold ** markers for checking
    t_clean = t.replace('**', '').replace('*', '').lower()
    patterns = [
        '\u6211\u662f kimi',       # 我是 Kimi
        '\u6211\u662fkimi',         # 我是Kimi
        '\u6211\u53eb kimi',        # 我叫 Kimi
        '\u6211\u53ebkimi',         # 我叫Kimi
        'i am kimi',
        "i'm kimi",
        'moonshot ai',              # 月之暗面的品牌名
        '\u6708\u4e4b\u6697\u9762\u5f00\u53d1',  # 月之暗面开发
        'kimi\uff0c\u4e00\u4e2a',  # Kimi，一个
        'kimi\uff0c\u7531moonshot', # Kimi，由Moonshot
        'kimi\u662f\u4e00\u4e2a',  # Kimi是一个
    ]
    return any(p in t_clean for p in patterns)

df['text'] = df['resp'].apply(extract_text_safe)
df['user_q'] = df['req'].apply(extract_user_q)
df['is_kimi_id'] = df['text'].apply(is_kimi_id)

kimi_id_df = df[df['is_kimi_id']].copy()
kimi_id_df = kimi_id_df.sort_values('created_at')

print("=" * 68)
print(f"KIMI SELF-IDENTIFICATION RECORDS: {len(kimi_id_df)}")
print("=" * 68)

for _, r in kimi_id_df.iterrows():
    print(f"  {r['created_at']}")
    print(f"  ch{int(r['channel_id'])}({r['channel_name']}) | {r['model']}")
    print(f"  Q: {r['user_q'][:120]}")
    print(f"  A: {r['text'][:350]}")
    print()

print("=" * 68)
print("Channel breakdown:")
if len(kimi_id_df) > 0:
    for ch, grp in kimi_id_df.groupby(['channel_id','channel_name']):
        print(f"  ch{int(ch[0])} {ch[1]}: {len(grp)} records")
        models = grp['model'].value_counts()
        for m, cnt in models.items():
            print(f"    {m}: {cnt}")
