import pandas as pd
import json

csv_path = r'c:\Users\Administrator\xwechat_files\wxid_8zd2avj7cixo22_b66d\msg\file\2026-05\归档(1)\【aiderby 内对】bill_2026-03_ch38_AIDerby_flattier_since_20260312_detail.csv.csv'
xlsx_path = r'c:\Users\Administrator\xwechat_files\wxid_8zd2avj7cixo22_b66d\msg\file\2026-05\归档(1)\【AIDB】usage-jh@ai.com-202603(1)(9).xlsx'

df_us = pd.read_csv(csv_path, encoding='utf-8-sig')
df_sp = pd.read_excel(xlsx_path)

us_cols = ['time', 'channel_id', 'model', 'input_tokens', 'output_tokens',
           'cache_hit_tokens', 'cache_write_tokens', 'system_cost', 'flat_cost',
           'duration_sec', 'is_stream']
df_us.columns = us_cols

sp_cols = ['model', 'stop', 'input_tokens', 'output_tokens', 'cache_create_5m',
           'cache_create_1h', 'cache_read', 'cost', 'invoke_time']
df_sp.columns = sp_cols

model_map = {
    'claude-sonnet-4-6': 'Claude Sonnet 4.6',
    'claude-sonnet-4-5-20250929': 'Claude Sonnet 4.5',
    'claude-sonnet-4-20250514': 'Claude Sonnet 4',
    'claude-haiku-4-5-20251001': 'Claude Haiku 4.5',
    'claude-opus-4-6': 'Claude Opus 4.6',
    'claude-opus-4-5-20251101': 'Claude Opus 4.5',
    'claude-opus-4-1-20250805': 'Claude Opus 4.1',
}

df_us['model_norm'] = df_us['model'].map(model_map)
df_sp['model_norm'] = df_sp['model']
df_us['date'] = pd.to_datetime(df_us['time']).dt.strftime('%Y-%m-%d')
df_sp['date'] = pd.to_datetime(df_sp['invoke_time']).dt.strftime('%Y-%m-%d')

result = {}

# Overall totals
result['us_total'] = {
    'rows': int(len(df_us)),
    'input_tokens': int(df_us['input_tokens'].sum()),
    'output_tokens': int(df_us['output_tokens'].sum()),
    'cache_hit_tokens': int(df_us['cache_hit_tokens'].sum()),
    'cache_write_tokens': int(df_us['cache_write_tokens'].sum()),
    'system_cost': round(float(df_us['system_cost'].sum()), 4),
    'flat_cost': round(float(df_us['flat_cost'].sum()), 4),
}

result['sp_total_all'] = {
    'rows': int(len(df_sp)),
    'input_tokens': int(df_sp['input_tokens'].sum()),
    'output_tokens': int(df_sp['output_tokens'].sum()),
    'cache_create_5m': int(df_sp['cache_create_5m'].sum()),
    'cost': round(float(df_sp['cost'].sum()), 4),
}

df_sp_ok = df_sp[df_sp['stop'] == 0]
result['sp_total_ok'] = {
    'rows': int(len(df_sp_ok)),
    'input_tokens': int(df_sp_ok['input_tokens'].sum()),
    'output_tokens': int(df_sp_ok['output_tokens'].sum()),
    'cache_create_5m': int(df_sp_ok['cache_create_5m'].sum()),
    'cost': round(float(df_sp_ok['cost'].sum()), 4),
}

# Stop code distribution
result['stop_distribution'] = {str(k): int(v) for k, v in df_sp['stop'].value_counts().items()}

# By model comparison
us_by_model = df_us.groupby('model_norm').agg(
    rows=('model', 'count'),
    input_tokens=('input_tokens', 'sum'),
    output_tokens=('output_tokens', 'sum'),
    cache_hit=('cache_hit_tokens', 'sum'),
    cache_write=('cache_write_tokens', 'sum'),
    flat_cost=('flat_cost', 'sum'),
).reset_index()

sp_by_model_all = df_sp.groupby('model_norm').agg(
    rows=('model', 'count'),
    input_tokens=('input_tokens', 'sum'),
    output_tokens=('output_tokens', 'sum'),
    cache_create_5m=('cache_create_5m', 'sum'),
    cost=('cost', 'sum'),
).reset_index()

sp_by_model_ok = df_sp_ok.groupby('model_norm').agg(
    rows=('model', 'count'),
    input_tokens=('input_tokens', 'sum'),
    output_tokens=('output_tokens', 'sum'),
    cache_create_5m=('cache_create_5m', 'sum'),
    cost=('cost', 'sum'),
).reset_index()

# Merge by model
model_comp = us_by_model.merge(sp_by_model_all, on='model_norm', suffixes=('_us', '_sp_all'), how='outer')
model_comp = model_comp.merge(
    sp_by_model_ok[['model_norm', 'rows', 'input_tokens', 'output_tokens', 'cost']],
    on='model_norm', how='outer', suffixes=('', '_sp_ok')
)
model_comp.columns = [
    'model', 'us_rows', 'us_input', 'us_output', 'us_cache_hit', 'us_cache_write', 'us_cost',
    'sp_all_rows', 'sp_all_input', 'sp_all_output', 'sp_all_cache_5m', 'sp_all_cost',
    'sp_ok_rows', 'sp_ok_input', 'sp_ok_output', 'sp_ok_cost'
]
model_comp = model_comp.fillna(0)

result['by_model'] = []
for _, r in model_comp.iterrows():
    result['by_model'].append({
        'model': r['model'],
        'us_rows': int(r['us_rows']),
        'sp_all_rows': int(r['sp_all_rows']),
        'sp_ok_rows': int(r['sp_ok_rows']),
        'row_diff_vs_all': int(r['us_rows'] - r['sp_all_rows']),
        'row_diff_vs_ok': int(r['us_rows'] - r['sp_ok_rows']),
        'us_input': int(r['us_input']),
        'sp_all_input': int(r['sp_all_input']),
        'us_output': int(r['us_output']),
        'sp_all_output': int(r['sp_all_output']),
        'us_cost': round(float(r['us_cost']), 4),
        'sp_all_cost': round(float(r['sp_all_cost']), 4),
        'sp_ok_cost': round(float(r['sp_ok_cost']), 4),
        'cost_diff_vs_all': round(float(r['us_cost'] - r['sp_all_cost']), 4),
        'cost_diff_pct': round(float((r['us_cost'] - r['sp_all_cost']) / r['sp_all_cost'] * 100), 2) if r['sp_all_cost'] > 0 else 0,
    })

# By date comparison
us_by_date = df_us.groupby('date').agg(
    rows=('model', 'count'),
    input_tokens=('input_tokens', 'sum'),
    output_tokens=('output_tokens', 'sum'),
    flat_cost=('flat_cost', 'sum'),
).reset_index()

sp_by_date_all = df_sp.groupby('date').agg(
    rows=('model', 'count'),
    input_tokens=('input_tokens', 'sum'),
    output_tokens=('output_tokens', 'sum'),
    cost=('cost', 'sum'),
).reset_index()

sp_by_date_ok = df_sp_ok.groupby('date').agg(
    rows=('model', 'count'),
    input_tokens=('input_tokens', 'sum'),
    output_tokens=('output_tokens', 'sum'),
    cost=('cost', 'sum'),
).reset_index()

date_comp = us_by_date.merge(sp_by_date_all, on='date', suffixes=('_us', '_sp'), how='outer')
date_comp = date_comp.merge(
    sp_by_date_ok[['date', 'rows', 'cost']],
    on='date', how='outer', suffixes=('', '_sp_ok')
)
date_comp.columns = [
    'date', 'us_rows', 'us_input', 'us_output', 'us_cost',
    'sp_rows', 'sp_input', 'sp_output', 'sp_cost',
    'sp_ok_rows', 'sp_ok_cost'
]
date_comp = date_comp.fillna(0).sort_values('date')

result['by_date'] = []
for _, r in date_comp.iterrows():
    result['by_date'].append({
        'date': r['date'],
        'us_rows': int(r['us_rows']),
        'sp_rows': int(r['sp_rows']),
        'sp_ok_rows': int(r['sp_ok_rows']),
        'row_diff': int(r['us_rows'] - r['sp_rows']),
        'us_input': int(r['us_input']),
        'sp_input': int(r['sp_input']),
        'us_output': int(r['us_output']),
        'sp_output': int(r['sp_output']),
        'us_cost': round(float(r['us_cost']), 4),
        'sp_cost': round(float(r['sp_cost']), 4),
        'sp_ok_cost': round(float(r['sp_ok_cost']), 4),
        'cost_diff': round(float(r['us_cost'] - r['sp_cost']), 4),
    })

# Date range edge analysis
sp_before_our_start = df_sp[pd.to_datetime(df_sp['invoke_time']) < pd.to_datetime('2026-03-03 21:38:54')]
result['sp_before_our_start'] = {
    'rows': int(len(sp_before_our_start)),
    'cost': round(float(sp_before_our_start['cost'].sum()), 4),
}

# Failed requests analysis (stop != 0)
df_sp_fail = df_sp[df_sp['stop'] != 0]
fail_by_model = df_sp_fail.groupby('model_norm').agg(
    rows=('model', 'count'),
    cost=('cost', 'sum'),
).reset_index()

result['failed_requests'] = []
for _, r in fail_by_model.iterrows():
    result['failed_requests'].append({
        'model': r['model_norm'],
        'rows': int(r['rows']),
        'cost': round(float(r['cost']), 4),
    })

# Stop code by model
stop_by_model = df_sp.groupby(['model_norm', 'stop']).size().reset_index(name='count')
result['stop_by_model'] = []
for _, r in stop_by_model.iterrows():
    result['stop_by_model'].append({
        'model': r['model_norm'],
        'stop': int(r['stop']),
        'count': int(r['count']),
    })

# Cache tokens analysis
result['cache_analysis'] = {
    'us_cache_hit': int(df_us['cache_hit_tokens'].sum()),
    'us_cache_write': int(df_us['cache_write_tokens'].sum()),
    'sp_cache_create_5m': int(df_sp['cache_create_5m'].sum()),
    'sp_cache_create_1h': int(df_sp['cache_create_1h'].sum()),
    'sp_cache_read': int(df_sp['cache_read'].sum()),
}

# Top discrepancies by model-date
us_md = df_us.groupby(['model_norm', 'date']).agg(
    us_rows=('model', 'count'),
    us_cost=('flat_cost', 'sum'),
).reset_index()

sp_md = df_sp.groupby(['model_norm', 'date']).agg(
    sp_rows=('model', 'count'),
    sp_cost=('cost', 'sum'),
).reset_index()

md_comp = us_md.merge(sp_md, on=['model_norm', 'date'], how='outer').fillna(0)
md_comp['cost_diff'] = md_comp['us_cost'] - md_comp['sp_cost']
md_comp['cost_diff_abs'] = md_comp['cost_diff'].abs()

top_diff = md_comp.nlargest(15, 'cost_diff_abs')
result['top_discrepancies'] = []
for _, r in top_diff.iterrows():
    result['top_discrepancies'].append({
        'model': r['model_norm'],
        'date': r['date'],
        'us_rows': int(r['us_rows']),
        'sp_rows': int(r['sp_rows']),
        'us_cost': round(float(r['us_cost']), 4),
        'sp_cost': round(float(r['sp_cost']), 4),
        'cost_diff': round(float(r['cost_diff']), 4),
    })

# Check if our data has entries before 3/12 (the flat-tier since date)
us_before_0312 = df_us[pd.to_datetime(df_us['time']) < pd.to_datetime('2026-03-12')]
result['us_before_0312'] = {
    'rows': int(len(us_before_0312)),
    'cost': round(float(us_before_0312['flat_cost'].sum()), 4),
}
sp_before_0312 = df_sp[pd.to_datetime(df_sp['invoke_time']) < pd.to_datetime('2026-03-12')]
result['sp_before_0312'] = {
    'rows': int(len(sp_before_0312)),
    'cost': round(float(sp_before_0312['cost'].sum()), 4),
}

# Token field analysis: supplier has InputTokens which might map differently
# In our data: input_tokens = prompt tokens (not including cache)
# In supplier: InputTokens could include cache or not
# Let's compare total tokens (input + output) for context
result['token_totals'] = {
    'us_total_input': int(df_us['input_tokens'].sum()),
    'us_total_output': int(df_us['output_tokens'].sum()),
    'us_total_cache_hit': int(df_us['cache_hit_tokens'].sum()),
    'us_total_cache_write': int(df_us['cache_write_tokens'].sum()),
    'sp_total_input': int(df_sp['input_tokens'].sum()),
    'sp_total_output': int(df_sp['output_tokens'].sum()),
    'sp_total_cache_create_5m': int(df_sp['cache_create_5m'].sum()),
}

# Billing column analysis
result['billing_format'] = {}
for col_name in ['is_stream']:
    vc = df_us[col_name].value_counts()
    result['billing_format'][col_name] = {str(k): int(v) for k, v in vc.items()}

# Output
output_path = r'e:\new-api\scripts\athena\output\aidb_reconciliation_2026_03.json'
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

print(f"Results saved to {output_path}")
print(json.dumps(result, indent=2, ensure_ascii=False))
