"""GMI April 2026 reconciliation analysis queries."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

os.chdir(os.path.dirname(__file__))

# Load env
from pathlib import Path
env_file = Path(__file__).parent.parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k] = v

from athena_engine import run_safe_query

queries = {
    "1_model_overview": """
SELECT
    model_name,
    COUNT(*) as total_requests,
    SUM(CASE WHEN prompt_tokens + completion_tokens <= 30 THEN 1 ELSE 0 END) as probe_requests,
    CAST(SUM(CAST(prompt_tokens AS BIGINT)) AS BIGINT) as total_prompt,
    CAST(SUM(CAST(completion_tokens AS BIGINT)) AS BIGINT) as total_completion
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '04' AND user_id = 18
GROUP BY model_name
ORDER BY total_prompt DESC
""",
    "2_timeout_analysis": """
SELECT
    model_name,
    COUNT(*) as requests,
    ROUND(AVG(CAST(use_time_seconds AS DOUBLE)), 1) as avg_time,
    MAX(use_time_seconds) as max_time,
    SUM(CASE WHEN use_time_seconds > 30 THEN 1 ELSE 0 END) as gt_30s,
    SUM(CASE WHEN use_time_seconds > 60 THEN 1 ELSE 0 END) as gt_60s,
    SUM(CASE WHEN use_time_seconds > 120 THEN 1 ELSE 0 END) as gt_120s,
    SUM(CASE WHEN use_time_seconds > 300 THEN 1 ELSE 0 END) as gt_300s,
    SUM(CASE WHEN use_time_seconds > 600 THEN 1 ELSE 0 END) as gt_600s
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '04' AND user_id = 18
GROUP BY model_name
ORDER BY requests DESC
""",
    "3_zero_completion": """
SELECT
    model_name,
    COUNT(*) as zero_completion_requests,
    CAST(SUM(CAST(prompt_tokens AS BIGINT)) AS BIGINT) as wasted_prompt_tokens,
    ROUND(AVG(CAST(use_time_seconds AS DOUBLE)), 1) as avg_time,
    MAX(use_time_seconds) as max_time
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '04' AND user_id = 18
    AND completion_tokens = 0
    AND prompt_tokens > 30
GROUP BY model_name
ORDER BY zero_completion_requests DESC
""",
    "4_daily_summary": """
SELECT
    day,
    COUNT(*) as requests,
    SUM(CASE WHEN prompt_tokens + completion_tokens <= 30 THEN 1 ELSE 0 END) as probes,
    SUM(CASE WHEN completion_tokens = 0 AND prompt_tokens > 30 THEN 1 ELSE 0 END) as zero_completion,
    CAST(SUM(CAST(prompt_tokens AS BIGINT)) AS BIGINT) as prompt_tokens,
    CAST(SUM(CAST(completion_tokens AS BIGINT)) AS BIGINT) as completion_tokens
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '04' AND user_id = 18
GROUP BY day
ORDER BY day
""",
    "5_zero_completion_daily": """
SELECT
    day,
    model_name,
    COUNT(*) as zero_completion_cnt,
    CAST(SUM(CAST(prompt_tokens AS BIGINT)) AS BIGINT) as wasted_prompt
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '04' AND user_id = 18
    AND completion_tokens = 0
    AND prompt_tokens > 30
GROUP BY day, model_name
ORDER BY day, zero_completion_cnt DESC
""",
    "6_channel_distribution": """
SELECT
    channel_id,
    model_name,
    COUNT(*) as requests,
    CAST(SUM(CAST(prompt_tokens AS BIGINT)) AS BIGINT) as prompt_tokens
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '04' AND user_id = 18
GROUP BY channel_id, model_name
ORDER BY requests DESC
""",
}

import pandas as pd
pd.set_option('display.max_columns', 20)
pd.set_option('display.width', 200)
pd.set_option('display.max_rows', 100)

for name, sql in queries.items():
    print(f"\n{'='*80}")
    print(f"  Query: {name}")
    print(f"{'='*80}")
    try:
        df = run_safe_query(sql.strip())
        if df is not None and not df.empty:
            print(df.to_string(index=False))
        else:
            print("  (no data)")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()
