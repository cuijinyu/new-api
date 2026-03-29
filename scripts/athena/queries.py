"""
预置 SQL 查询模板 — 参数化、类型安全、分区校验

所有函数返回 SQL 字符串，由 athena_engine 执行。
"""

import re

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _q(value) -> str:
    """Quote a value for SQL, with basic injection prevention."""
    s = str(value)
    if not re.match(r"^[\w\-.*% ]+$", s):
        raise ValueError(f"Invalid query parameter: {s!r}")
    return f"'{s}'"


def _year_month(year_month: str) -> tuple[str, str]:
    """Parse 'YYYY-MM' into (year, month) strings."""
    m = re.match(r"^(\d{4})-(\d{2})$", year_month)
    if not m:
        raise ValueError(f"Invalid year-month format: {year_month!r}, expected YYYY-MM")
    return m.group(1), m.group(2)


def _partition_filter(year: str, month: str, day: str = None, hour: str = None) -> str:
    parts = [f"year = {_q(year)}", f"month = {_q(month)}"]
    if day:
        parts.append(f"day = {_q(day)}")
    if hour:
        parts.append(f"hour = {_q(hour)}")
    return " AND ".join(parts)


# ---------------------------------------------------------------------------
# A. Billing queries (usage_logs)
# ---------------------------------------------------------------------------

def monthly_bill_by_user(year_month: str, user_id: int = None) -> str:
    year, month = _year_month(year_month)
    where = _partition_filter(year, month)
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    return f"""
SELECT
    user_id,
    username,
    COUNT(*)                                AS call_count,
    SUM(prompt_tokens)                      AS total_input_tokens,
    SUM(completion_tokens)                  AS total_output_tokens,
    SUM(prompt_tokens + completion_tokens)  AS total_tokens,
    SUM(quota)                              AS total_quota,
    ROUND(SUM(quota) / 500000.0, 4)         AS total_usd
FROM ezmodel_logs.usage_logs
WHERE {where}
GROUP BY user_id, username
ORDER BY total_usd DESC
"""


def monthly_bill_by_user_model(year_month: str, user_id: int = None) -> str:
    year, month = _year_month(year_month)
    where = _partition_filter(year, month)
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    return f"""
SELECT
    user_id,
    username,
    model_name,
    COUNT(*)                                AS call_count,
    SUM(prompt_tokens)                      AS total_input_tokens,
    SUM(completion_tokens)                  AS total_output_tokens,
    SUM(quota)                              AS total_quota,
    ROUND(SUM(quota) / 500000.0, 4)         AS total_usd
FROM ezmodel_logs.usage_logs
WHERE {where}
GROUP BY user_id, username, model_name
ORDER BY user_id, total_usd DESC
"""


def monthly_bill_full(year_month: str, user_id: int = None) -> str:
    """Full billing detail with cache token breakdown from other JSON.

    Extracts cache_tokens, cache_creation_tokens (5m/1h/remaining) and
    tiered pricing info from the 'other' JSON field via Athena json_extract,
    so the aggregation is done server-side for performance.
    """
    year, month = _year_month(year_month)
    where = _partition_filter(year, month)
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    return f"""
SELECT
    user_id,
    username,
    channel_id,
    model_name,
    COUNT(*)                                AS call_count,
    SUM(prompt_tokens)                      AS total_input_tokens,
    SUM(completion_tokens)                  AS total_output_tokens,
    SUM(quota)                              AS total_quota,
    ROUND(SUM(quota) / 500000.0, 4)         AS total_usd,
    SUM(COALESCE(CAST(json_extract_scalar(other, '$.cache_tokens') AS BIGINT), 0))
        AS total_cache_hit_tokens,
    SUM(COALESCE(CAST(json_extract_scalar(other, '$.cache_creation_tokens') AS BIGINT), 0))
        AS total_cache_write_tokens,
    SUM(COALESCE(CAST(json_extract_scalar(other, '$.tiered_cache_creation_tokens_5m')  AS BIGINT),
                 CAST(json_extract_scalar(other, '$.cache_creation_tokens_5m')  AS BIGINT), 0))
        AS total_cw_5m,
    SUM(COALESCE(CAST(json_extract_scalar(other, '$.tiered_cache_creation_tokens_1h')  AS BIGINT),
                 CAST(json_extract_scalar(other, '$.cache_creation_tokens_1h')  AS BIGINT), 0))
        AS total_cw_1h,
    SUM(COALESCE(CAST(json_extract_scalar(other, '$.tiered_cache_creation_tokens_remaining') AS BIGINT), 0))
        AS total_cw_remaining
FROM ezmodel_logs.usage_logs
WHERE {where}
GROUP BY user_id, username, channel_id, model_name
ORDER BY user_id, total_usd DESC
"""


def daily_trend(year_month: str, user_id: int = None) -> str:
    year, month = _year_month(year_month)
    where = _partition_filter(year, month)
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    return f"""
SELECT
    day,
    COUNT(*)                            AS call_count,
    SUM(prompt_tokens + completion_tokens) AS total_tokens,
    SUM(quota)                          AS total_quota,
    ROUND(SUM(quota) / 500000.0, 4)     AS total_usd
FROM ezmodel_logs.usage_logs
WHERE {where}
GROUP BY day
ORDER BY day
"""


def model_ranking(year_month: str) -> str:
    year, month = _year_month(year_month)
    where = _partition_filter(year, month)
    return f"""
SELECT
    model_name,
    COUNT(*)                                    AS call_count,
    SUM(prompt_tokens + completion_tokens)       AS total_tokens,
    ROUND(SUM(quota) / 500000.0, 2)             AS total_usd,
    ROUND(AVG(use_time_seconds), 1)             AS avg_latency_sec,
    ROUND(SUM(CASE WHEN is_stream THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS stream_pct
FROM ezmodel_logs.usage_logs
WHERE {where}
GROUP BY model_name
ORDER BY total_usd DESC
"""


def channel_summary(year_month: str) -> str:
    year, month = _year_month(year_month)
    where = _partition_filter(year, month)
    return f"""
SELECT
    channel_id,
    COUNT(*)                            AS call_count,
    COUNT(DISTINCT model_name)          AS model_count,
    COUNT(DISTINCT user_id)             AS user_count,
    ROUND(SUM(quota) / 500000.0, 2)     AS total_usd
FROM ezmodel_logs.usage_logs
WHERE {where}
GROUP BY channel_id
ORDER BY total_usd DESC
"""


def top_users(year_month: str, limit: int = 20) -> str:
    year, month = _year_month(year_month)
    where = _partition_filter(year, month)
    return f"""
SELECT
    user_id,
    username,
    COUNT(*)                            AS call_count,
    ROUND(SUM(quota) / 500000.0, 2)     AS total_usd,
    MIN(from_unixtime(created_at))      AS first_call,
    MAX(from_unixtime(created_at))      AS last_call
FROM ezmodel_logs.usage_logs
WHERE {where}
GROUP BY user_id, username
ORDER BY total_usd DESC
LIMIT {int(limit)}
"""


def hourly_distribution(year_month: str, day: str) -> str:
    year, month = _year_month(year_month)
    where = _partition_filter(year, month, day=day)
    return f"""
SELECT
    hour,
    COUNT(*)                                AS call_count,
    SUM(prompt_tokens + completion_tokens)  AS total_tokens,
    ROUND(SUM(quota) / 500000.0, 2)         AS total_usd
FROM ezmodel_logs.usage_logs
WHERE {where}
GROUP BY hour
ORDER BY hour
"""


def raw_usage_detail(start_date: str, end_date: str,
                     user_id: int = None, channel_id: int = None,
                     model: str = None) -> str:
    """Row-level usage_logs with all fields (incl. other) for local recalc.

    start_date / end_date: 'YYYY-MM-DD' inclusive range.
    Generates partition filters covering all months/days in the range.
    """
    import re as _re
    m1 = _re.match(r"^(\d{4})-(\d{2})-(\d{2})$", start_date)
    m2 = _re.match(r"^(\d{4})-(\d{2})-(\d{2})$", end_date)
    if not m1 or not m2:
        raise ValueError(f"Date format must be YYYY-MM-DD, got {start_date!r} / {end_date!r}")

    sy, sm, sd = m1.group(1), m1.group(2), m1.group(3)
    ey, em, ed = m2.group(1), m2.group(2), m2.group(3)

    if sy == ey and sm == em:
        where = (f"year = '{sy}' AND month = '{sm}' "
                 f"AND day >= '{sd}' AND day <= '{ed}'")
    elif sy == ey:
        where = (f"year = '{sy}' AND "
                 f"((month = '{sm}' AND day >= '{sd}') OR "
                 f"(month > '{sm}' AND month < '{em}') OR "
                 f"(month = '{em}' AND day <= '{ed}'))")
    else:
        where = (f"((year = '{sy}' AND ((month = '{sm}' AND day >= '{sd}') OR month > '{sm}')) OR "
                 f"(year > '{sy}' AND year < '{ey}') OR "
                 f"(year = '{ey}' AND ((month = '{em}' AND day <= '{ed}') OR month < '{em}')))")

    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    if channel_id is not None:
        where += f" AND channel_id = {int(channel_id)}"
    if model:
        where += f" AND model_name = {_q(model)}"

    return f"""
SELECT
    request_id,
    created_at,
    user_id,
    username,
    channel_id,
    model_name,
    token_name,
    prompt_tokens,
    completion_tokens,
    quota,
    other,
    use_time_seconds,
    is_stream
FROM ezmodel_logs.usage_logs
WHERE {where}
ORDER BY created_at
"""


# ---------------------------------------------------------------------------
# B. Anomaly detection (usage_logs)
# ---------------------------------------------------------------------------

def anomaly_zero_tokens(year_month: str, day: str = None) -> str:
    year, month = _year_month(year_month)
    where = _partition_filter(year, month, day=day)
    return f"""
SELECT
    request_id,
    from_unixtime(created_at)   AS created_time,
    user_id, username, model_name, channel_id,
    prompt_tokens, completion_tokens, quota,
    ROUND(quota / 500000.0, 6)  AS quota_usd,
    other
FROM ezmodel_logs.usage_logs
WHERE {where}
  AND quota > 0
  AND prompt_tokens = 0
  AND completion_tokens = 0
ORDER BY created_at
"""


def duplicate_billing(year_month: str) -> str:
    year, month = _year_month(year_month)
    where = _partition_filter(year, month)
    return f"""
WITH numbered AS (
    SELECT
        request_id, created_at, user_id, username, model_name,
        prompt_tokens, completion_tokens, quota, token_name,
        LAG(created_at) OVER (
            PARTITION BY user_id, model_name, prompt_tokens, completion_tokens, quota
            ORDER BY created_at
        ) AS prev_created_at
    FROM ezmodel_logs.usage_logs
    WHERE {where}
      AND quota > 0
)
SELECT
    request_id,
    from_unixtime(created_at)       AS created_time,
    user_id, username, model_name, token_name,
    prompt_tokens, completion_tokens, quota,
    ROUND(quota / 500000.0, 6)      AS quota_usd,
    created_at - prev_created_at    AS gap_seconds
FROM numbered
WHERE created_at - prev_created_at <= 10
ORDER BY user_id, model_name, created_at
"""


# ---------------------------------------------------------------------------
# C. KPI summary (usage_logs)
# ---------------------------------------------------------------------------

def kpi_summary(year_month: str) -> str:
    year, month = _year_month(year_month)
    where = _partition_filter(year, month)
    return f"""
SELECT
    COUNT(*)                            AS total_calls,
    COUNT(DISTINCT user_id)             AS unique_users,
    COUNT(DISTINCT model_name)          AS unique_models,
    SUM(prompt_tokens)                  AS total_input_tokens,
    SUM(completion_tokens)              AS total_output_tokens,
    SUM(quota)                          AS total_quota,
    ROUND(SUM(quota) / 500000.0, 2)     AS total_usd
FROM ezmodel_logs.usage_logs
WHERE {where}
"""


# ---------------------------------------------------------------------------
# D. Error analysis (error_logs — requires day)
# ---------------------------------------------------------------------------

def error_distribution(year_month: str, day: str) -> str:
    year, month = _year_month(year_month)
    where = _partition_filter(year, month, day=day)
    return f"""
SELECT
    status_code,
    model,
    channel_name,
    COUNT(*) AS error_count
FROM ezmodel_logs.error_logs
WHERE {where}
GROUP BY status_code, model, channel_name
ORDER BY error_count DESC
"""


def error_hourly(year_month: str, day: str) -> str:
    year, month = _year_month(year_month)
    where = _partition_filter(year, month, day=day)
    return f"""
SELECT
    hour,
    status_code,
    COUNT(*) AS error_count
FROM ezmodel_logs.error_logs
WHERE {where}
GROUP BY hour, status_code
ORDER BY hour, error_count DESC
"""


# ---------------------------------------------------------------------------
# E. Raw logs (requires day, hour recommended)
# ---------------------------------------------------------------------------

def raw_logs_sample(year_month: str, day: str, hour: str = None,
                    model: str = None, user_id: int = None,
                    status_code: int = None, limit: int = 50) -> str:
    year, month = _year_month(year_month)
    where = _partition_filter(year, month, day=day, hour=hour)
    if model:
        where += f" AND model = {_q(model)}"
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    if status_code is not None:
        where += f" AND status_code = {int(status_code)}"
    return f"""
SELECT
    request_id,
    created_at,
    model,
    channel_name,
    user_id,
    status_code,
    SUBSTR(response_body, 1, 500) AS response_preview,
    response_error
FROM ezmodel_logs.raw_logs
WHERE {where}
ORDER BY created_at DESC
LIMIT {int(limit)}
"""


# ---------------------------------------------------------------------------
# F. Cross-check: usage vs raw record count
# ---------------------------------------------------------------------------

def cross_check_counts(year_month: str, day: str) -> str:
    year, month = _year_month(year_month)
    where = _partition_filter(year, month, day=day)
    return f"""
SELECT 'usage_logs' AS source, COUNT(*) AS record_count
FROM ezmodel_logs.usage_logs WHERE {where}
UNION ALL
SELECT 'raw_logs' AS source, COUNT(*) AS record_count
FROM ezmodel_logs.raw_logs WHERE {where}
UNION ALL
SELECT 'error_logs' AS source, COUNT(*) AS record_count
FROM ezmodel_logs.error_logs WHERE {where}
"""
