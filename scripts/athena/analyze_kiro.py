# -*- coding: utf-8 -*-
import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd

df = pd.read_excel('output/kiro_records.xlsx')
print(f"Total Kiro records: {len(df)}\n")

KIRO_ID_PATTERNS = [
    'I am Kiro', "I'm Kiro", "I'm kiro",
    '\u6211\u662fKiro', '\u6211\u662f Kiro',
    '\u6211\u662fkiro', '\u6211\u662f kiro',
    '\u6211\u53ebKiro', '\u6211\u53eb Kiro',
    'Kiro\uff0c\u4e00\u4e2a', 'Kiro\u662f',
    'as Kiro,', 'named Kiro',
    # Kiro intro style
    '\u4e00\u4e2aAI\u52a9\u624b\u548cIDE', 'AI\u52a9\u624b\u548cIDE',
    'AI assistant and IDE',
]

def extract_text_safe(resp_str):
    """Extract text without regex to avoid bracket issues."""
    s = str(resp_str)
    # parse SSE line by line
    texts = []
    for line in s.split('\\n'):
        line = line.strip()
        if '"text":' in line:
            try:
                # find value between "text":" and next "
                start = line.index('"text":') + 7
                remainder = line[start:].strip()
                if remainder.startswith('"'):
                    remainder = remainder[1:]
                    end = 0
                    while end < len(remainder):
                        if remainder[end] == '"' and (end == 0 or remainder[end-1] != '\\'):
                            break
                        end += 1
                    texts.append(remainder[:end])
            except:
                pass
    if texts:
        return ''.join(texts).replace('\\n', '\n').replace('\\"', '"')
    # try JSON
    try:
        j = json.loads(s)
        return (j.get('choices') or [{}])[0].get('message', {}).get('content', '') or \
               (j.get('content') or [{}])[0].get('text', '')
    except:
        # last resort: just grep the raw string for Kiro context
        idx = s.find('Kiro')
        if idx >= 0:
            return s[max(0,idx-100):idx+300]
        return ''

def extract_system_safe(req_str):
    s = str(req_str)
    try:
        j = json.loads(s)
        msgs = j.get('messages', [])
        for m in msgs:
            if m.get('role') == 'system':
                content = m.get('content', '')
                if isinstance(content, list):
                    content = ' '.join(x.get('text','') for x in content if isinstance(x,dict))
                return str(content)[:600]
        return None
    except:
        # find system in raw
        if '"system"' in s:
            idx = s.find('"system"')
            return s[idx:idx+400]
        return None

def extract_user_q_safe(req_str):
    s = str(req_str)
    try:
        j = json.loads(s)
        msgs = j.get('messages', [])
        user_msgs = [m for m in msgs if m.get('role') == 'user']
        if not user_msgs:
            return ''
        last = user_msgs[-1].get('content', '')
        if isinstance(last, list):
            last = ' '.join(x.get('text', '') for x in last if isinstance(x, dict))
        return str(last)[:300]
    except:
        return ''

results = []
for _, r in df.iterrows():
    text = extract_text_safe(str(r['resp']))
    user_q = extract_user_q_safe(str(r['req']))
    sys_p = extract_system_safe(str(r['req']))
    text_l = text.lower()
    is_id = any(p.lower() in text_l for p in KIRO_ID_PATTERNS)
    results.append({
        'time': r['created_at'],
        'ch': int(r['channel_id']),
        'ch_name': r['channel_name'],
        'model': r['model'],
        'is_id': is_id,
        'text': text,
        'user_q': user_q,
        'sys_p': sys_p,
    })

id_claims = [x for x in results if x['is_id']]
mentions   = [x for x in results if not x['is_id']]

print("=" * 68)
print(f"KIRO IDENTITY CLAIMS: {len(id_claims)}")
print("=" * 68)
for r in id_claims:
    print(f"  {r['time']} | ch{r['ch']}({r['ch_name']}) | {r['model']}")
    if r['sys_p']:
        print(f"  [SYSTEM PROMPT]: {r['sys_p'][:500]}")
    else:
        print("  [SYSTEM PROMPT]: none in request (injected upstream)")
    print(f"  Q: {r['user_q'][:150]}")
    print(f"  A: {r['text'][:400]}")
    print()

print("=" * 68)
print(f"KIRO TOPIC MENTIONS: {len(mentions)}")
print("=" * 68)
# channel breakdown
from collections import Counter
ch_cnt = Counter(f"ch{r['ch']}({r['ch_name']})" for r in mentions)
for ch, cnt in ch_cnt.most_common():
    print(f"  {ch}: {cnt}")

print()
print("Sample topic-mention responses:")
for r in mentions[:3]:
    print(f"  ch{r['ch']} | {r['time']}")
    print(f"  Q: {r['user_q'][:100]}")
    print(f"  A: {r['text'][:200]}")
    print()
