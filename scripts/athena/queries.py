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


def _validate_end_day(end_day: str, year_month: str) -> None:
    """Validate that end_day is a YYYY-MM-DD date within the given year_month."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", end_day)
    if not m:
        raise ValueError(f"end_day must be YYYY-MM-DD, got {end_day!r}")
    ym_prefix = f"{m.group(1)}-{m.group(2)}"
    if ym_prefix != year_month:
        raise ValueError(
            f"end_day {end_day!r} is not in month {year_month!r}"
        )


def _validate_start_day(start_day: str, year_month: str) -> None:
    """Validate that start_day is a YYYY-MM-DD date within the given year_month."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", start_day)
    if not m:
        raise ValueError(f"start_day must be YYYY-MM-DD, got {start_day!r}")
    ym_prefix = f"{m.group(1)}-{m.group(2)}"
    if ym_prefix != year_month:
        raise ValueError(
            f"start_day {start_day!r} is not in month {year_month!r}"
        )


def _partition_filter(year: str, month: str, day: str = None, hour: str = None) -> str:
    parts = [f"year = {_q(year)}", f"month = {_q(month)}"]
    if day:
        parts.append(f"day = {_q(day)}")
    if hour:
        parts.append(f"hour = {_q(hour)}")
    return " AND ".join(parts)


def _parse_datetime(dt_str: str) -> tuple[str, str, str, str, int]:
    """Parse 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD HH' into (year, month, day, hour_str, unix_ts).

    Returns unix_ts as UTC epoch seconds (treats input as UTC).
    hour_str is zero-padded, e.g. '09'.
    """
    from datetime import datetime, timezone
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2})(?::(\d{2}))?$", dt_str.strip())
    if not m:
        raise ValueError(
            f"datetime must be 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD HH', got {dt_str!r}"
        )
    year, month, day = m.group(1), m.group(2), m.group(3)
    hour = int(m.group(4))
    minute = int(m.group(5)) if m.group(5) else 0
    dt = datetime(int(year), int(month), int(day), hour, minute, tzinfo=timezone.utc)
    return year, month, day, f"{hour:02d}", int(dt.timestamp())


def _hour_range_filter(year: str, month: str,
                       start_day: str = None, start_hour: str = None,
                       end_day: str = None, end_hour: str = None) -> str:
    """Build partition WHERE clause covering [start_day/hour .. end_day/hour].

    When start_hour/end_hour are provided, uses >= / <= on the hour partition
    column (only valid when start_day == end_day; otherwise falls back to
    day-range filter to avoid over-pruning across day boundaries).
    """
    parts = [f"year = {_q(year)}", f"month = {_q(month)}"]

    same_day = (start_day and end_day and start_day == end_day)

    if same_day:
        parts.append(f"day = {_q(start_day.split('-')[2])}")
        if start_hour:
            parts.append(f"hour >= {_q(start_hour)}")
        if end_hour:
            parts.append(f"hour <= {_q(end_hour)}")
    else:
        if start_day:
            parts.append(f"day >= {_q(start_day.split('-')[2])}")
        if end_day:
            parts.append(f"day <= {_q(end_day.split('-')[2])}")

    return " AND ".join(parts)


# ---------------------------------------------------------------------------
# A. Billing queries (usage_logs)
# ---------------------------------------------------------------------------

def _build_time_where(year: str, month: str, year_month: str,
                      start_day: str = None, end_day: str = None,
                      start_time: str = None, end_time: str = None) -> str:
    """Build WHERE clause with partition pruning + optional created_at row filter.

    start_time / end_time: 'YYYY-MM-DD HH:MM' (UTC). When provided, they take
    precedence over start_day / end_day for the row-level created_at filter,
    and the hour partition is also pruned to minimize scan cost.

    Returns (partition_where, extra_row_conditions) combined into one string.
    """
    # Resolve effective day/hour boundaries
    s_day = s_hour = s_ts = None
    e_day = e_hour = e_ts = None

    if start_time:
        sy, sm, sd, sh, s_ts = _parse_datetime(start_time)
        s_day, s_hour = f"{sy}-{sm}-{sd}", sh
        _validate_start_day(s_day, year_month)
    elif start_day:
        _validate_start_day(start_day, year_month)
        s_day = start_day

    if end_time:
        ey, em, ed, eh, e_ts = _parse_datetime(end_time)
        e_day, e_hour = f"{ey}-{em}-{ed}", eh
        _validate_end_day(e_day, year_month)
    elif end_day:
        _validate_end_day(end_day, year_month)
        e_day = end_day

    # Partition pruning
    where = _hour_range_filter(year, month,
                               start_day=s_day, start_hour=s_hour,
                               end_day=e_day, end_hour=e_hour)

    # Row-level created_at filter (only when sub-day precision is needed)
    if s_ts is not None:
        where += f" AND created_at >= {s_ts}"
    if e_ts is not None:
        # end_time is inclusive to the minute: include all records in that minute
        where += f" AND created_at < {e_ts + 60}"

    return where


def monthly_bill_by_user(year_month: str, user_id: int = None,
                         channel_id: int = None,
                         start_day: str = None, end_day: str = None,
                         start_time: str = None, end_time: str = None) -> str:
    """start_time / end_time: 'YYYY-MM-DD HH:MM' UTC for sub-day precision."""
    year, month = _year_month(year_month)
    where = _build_time_where(year, month, year_month,
                              start_day=start_day, end_day=end_day,
                              start_time=start_time, end_time=end_time)
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    if channel_id is not None:
        where += f" AND channel_id = {int(channel_id)}"
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


def monthly_bill_by_user_model(year_month: str, user_id: int = None,
                               channel_id: int = None,
                               start_day: str = None, end_day: str = None,
                               start_time: str = None, end_time: str = None) -> str:
    """start_time / end_time: 'YYYY-MM-DD HH:MM' UTC for sub-day precision."""
    year, month = _year_month(year_month)
    where = _build_time_where(year, month, year_month,
                              start_day=start_day, end_day=end_day,
                              start_time=start_time, end_time=end_time)
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    if channel_id is not None:
        where += f" AND channel_id = {int(channel_id)}"
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


def monthly_bill_full(year_month: str, user_id: int = None,
                      channel_id: int = None,
                      start_day: str = None, end_day: str = None,
                      start_time: str = None, end_time: str = None) -> str:
    """Full billing detail with cache token breakdown from other JSON.

    Extracts cache_tokens, cache_creation_tokens (5m/1h/remaining) and
    tiered pricing info from the 'other' JSON field via Athena json_extract,
    so the aggregation is done server-side for performance.

    start_day / end_day: day-level boundary 'YYYY-MM-DD' (inclusive).
    start_time / end_time: 'YYYY-MM-DD HH:MM' UTC for sub-day precision;
        takes precedence over start_day / end_day when provided.
    """
    year, month = _year_month(year_month)
    where = _build_time_where(year, month, year_month,
                              start_day=start_day, end_day=end_day,
                              start_time=start_time, end_time=end_time)
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    if channel_id is not None:
        where += f" AND channel_id = {int(channel_id)}"
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


def daily_trend(year_month: str, user_id: int = None,
                channel_id: int = None,
                start_day: str = None, end_day: str = None,
                start_time: str = None, end_time: str = None) -> str:
    """start_time / end_time: 'YYYY-MM-DD HH:MM' UTC for sub-day precision."""
    year, month = _year_month(year_month)
    where = _build_time_where(year, month, year_month,
                              start_day=start_day, end_day=end_day,
                              start_time=start_time, end_time=end_time)
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    if channel_id is not None:
        where += f" AND channel_id = {int(channel_id)}"
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
# A1b. Row-level query by created_at range (for vendor crosscheck)
# ---------------------------------------------------------------------------

def usage_by_created_at_range(ts_min: int, ts_max: int,
                              channel_id: int = None,
                              user_id: int = None) -> str:
    """Row-level usage_logs filtered by created_at unix timestamp range.

    Derives partition filters from timestamps to enable partition pruning.
    Returns per-request data suitable for request_id-level crosscheck.
    """
    from datetime import datetime, timezone

    dt_min = datetime.fromtimestamp(ts_min, tz=timezone.utc)
    dt_max = datetime.fromtimestamp(ts_max, tz=timezone.utc)

    # Build partition filter covering all months/days in range
    if dt_min.year == dt_max.year and dt_min.month == dt_max.month:
        where = (f"year = '{dt_min.year}' AND month = '{dt_min.month:02d}' "
                 f"AND day >= '{dt_min.day:02d}' AND day <= '{dt_max.day:02d}'")
    elif dt_min.year == dt_max.year:
        where = (f"year = '{dt_min.year}' AND "
                 f"((month = '{dt_min.month:02d}' AND day >= '{dt_min.day:02d}') OR "
                 f"(month > '{dt_min.month:02d}' AND month < '{dt_max.month:02d}') OR "
                 f"(month = '{dt_max.month:02d}' AND day <= '{dt_max.day:02d}'))")
    else:
        where = (f"year >= '{dt_min.year}' AND year <= '{dt_max.year}'")

    where += f" AND created_at >= {int(ts_min)} AND created_at < {int(ts_max)}"

    if channel_id is not None:
        where += f" AND channel_id = {int(channel_id)}"
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"

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
    ROUND(quota / 500000.0, 6) AS billed_usd,
    use_time_seconds,
    is_stream
FROM ezmodel_logs.usage_logs
WHERE {where}
ORDER BY created_at
"""


def usage_summary_by_created_at_range(ts_min: int, ts_max: int,
                                      channel_id: int = None,
                                      user_id: int = None) -> str:
    """Aggregated usage by model for a created_at timestamp range.

    Used for model-level crosscheck against vendor bills.
    """
    from datetime import datetime, timezone

    dt_min = datetime.fromtimestamp(ts_min, tz=timezone.utc)
    dt_max = datetime.fromtimestamp(ts_max, tz=timezone.utc)

    if dt_min.year == dt_max.year and dt_min.month == dt_max.month:
        where = (f"year = '{dt_min.year}' AND month = '{dt_min.month:02d}' "
                 f"AND day >= '{dt_min.day:02d}' AND day <= '{dt_max.day:02d}'")
    elif dt_min.year == dt_max.year:
        where = (f"year = '{dt_min.year}' AND "
                 f"((month = '{dt_min.month:02d}' AND day >= '{dt_min.day:02d}') OR "
                 f"(month > '{dt_min.month:02d}' AND month < '{dt_max.month:02d}') OR "
                 f"(month = '{dt_max.month:02d}' AND day <= '{dt_max.day:02d}'))")
    else:
        where = (f"year >= '{dt_min.year}' AND year <= '{dt_max.year}'")

    where += f" AND created_at >= {int(ts_min)} AND created_at < {int(ts_max)}"

    if channel_id is not None:
        where += f" AND channel_id = {int(channel_id)}"
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"

    return f"""
SELECT
    model_name,
    COUNT(*)                                AS call_count,
    SUM(prompt_tokens)                      AS total_input_tokens,
    SUM(completion_tokens)                  AS total_output_tokens,
    SUM(quota)                              AS total_quota,
    ROUND(SUM(quota) / 500000.0, 4)         AS total_usd
FROM ezmodel_logs.usage_logs
WHERE {where}
GROUP BY model_name
ORDER BY total_usd DESC
"""


# ---------------------------------------------------------------------------
# A2. Detail export — per-day row-level with Athena-side json_extract
# ---------------------------------------------------------------------------

def raw_usage_detail_daily(year_month: str, day: str,
                           user_id: int = None, channel_id: int = None,
                           model: str = None) -> str:
    """Row-level usage_logs for a single day with cache tokens extracted server-side.

    Returns one row per request with all fields needed for pricing.
    The 'other' JSON is NOT returned — cache tokens are extracted via json_extract.
    """
    year, month = _year_month(year_month)
    where = _partition_filter(year, month, day=day)

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
    ROUND(quota / 500000.0, 6)  AS billed_usd,
    use_time_seconds,
    is_stream,
    COALESCE(CAST(json_extract_scalar(other, '$.cache_tokens') AS BIGINT), 0)
        AS cache_hit_tokens,
    COALESCE(CAST(json_extract_scalar(other, '$.cache_creation_tokens') AS BIGINT), 0)
        AS cache_write_tokens,
    COALESCE(CAST(json_extract_scalar(other, '$.tiered_cache_creation_tokens_5m')  AS BIGINT),
             CAST(json_extract_scalar(other, '$.cache_creation_tokens_5m')  AS BIGINT), 0)
        AS cw_5m,
    COALESCE(CAST(json_extract_scalar(other, '$.tiered_cache_creation_tokens_1h')  AS BIGINT),
             CAST(json_extract_scalar(other, '$.cache_creation_tokens_1h')  AS BIGINT), 0)
        AS cw_1h,
    COALESCE(CAST(json_extract_scalar(other, '$.tiered_cache_creation_tokens_remaining') AS BIGINT), 0)
        AS cw_remaining,
    CAST(json_extract_scalar(other, '$.tiered_input_price') AS DOUBLE)
        AS tiered_ip,
    CAST(json_extract_scalar(other, '$.tiered_output_price') AS DOUBLE)
        AS tiered_op
FROM ezmodel_logs.usage_logs
WHERE {where}
ORDER BY created_at
"""


def detail_day_list(year_month: str, start_day: str = None, end_day: str = None,
                    start_time: str = None, end_time: str = None) -> list[str]:
    """Return list of day strings (01..N) for the given month.

    start_time / end_time ('YYYY-MM-DD HH:MM') take precedence over
    start_day / end_day when provided.
    Used by parallel detail export to generate per-day queries.
    """
    import calendar
    year, month = _year_month(year_month)
    _, ndays = calendar.monthrange(int(year), int(month))
    first_day = 1

    eff_start_day = start_day
    eff_end_day = end_day

    if start_time:
        sy, sm, sd, _sh, _ts = _parse_datetime(start_time)
        eff_start_day = f"{sy}-{sm}-{sd}"
    if end_time:
        ey, em, ed, _eh, _ts = _parse_datetime(end_time)
        eff_end_day = f"{ey}-{em}-{ed}"

    if eff_start_day:
        _validate_start_day(eff_start_day, year_month)
        first_day = int(eff_start_day.split("-")[2])
    if eff_end_day:
        _validate_end_day(eff_end_day, year_month)
        ndays = int(eff_end_day.split("-")[2])
    return [f"{d:02d}" for d in range(first_day, ndays + 1)]


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
