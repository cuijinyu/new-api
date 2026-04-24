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


def _channel_where(channel_id: int = None, channel_ids: list[int] = None) -> str:
    """Build channel filter SQL for either one channel or a channel set."""
    if channel_ids:
        ids = sorted({int(x) for x in channel_ids if x is not None})
        if ids:
            return " AND channel_id IN (" + ", ".join(str(x) for x in ids) + ")"
    if channel_id is not None:
        return f" AND channel_id = {int(channel_id)}"
    return ""


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


def _parse_datetime(dt_str: str, utc_offset_hours: float = 0) -> tuple[str, str, str, str, int]:
    """Parse 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD HH' into (year, month, day, hour_str, unix_ts).

    Returns unix_ts as UTC epoch seconds. The input wall-clock time is
    interpreted in the fixed UTC offset supplied by utc_offset_hours.
    hour_str is zero-padded, e.g. '09'.
    """
    from datetime import datetime, timedelta, timezone
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2})(?::(\d{2}))?$", dt_str.strip())
    if not m:
        raise ValueError(
            f"datetime must be 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD HH', got {dt_str!r}"
        )
    year, month, day = m.group(1), m.group(2), m.group(3)
    hour = int(m.group(4))
    minute = int(m.group(5)) if m.group(5) else 0
    tz = timezone(timedelta(hours=float(utc_offset_hours)))
    dt = datetime(int(year), int(month), int(day), hour, minute, tzinfo=tz)
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
                      start_time: str = None, end_time: str = None,
                      time_zone_offset_hours: float = 0) -> str:
    """Build WHERE clause with partition pruning + optional created_at row filter.

    start_time / end_time: 'YYYY-MM-DD HH:MM'. When provided, they take
    precedence over start_day / end_day for the row-level created_at filter,
    and the hour partition is also pruned to minimize scan cost. The
    wall-clock time is interpreted in time_zone_offset_hours.

    Returns (partition_where, extra_row_conditions) combined into one string.
    """
    # Resolve effective day/hour boundaries
    s_day = s_hour = s_ts = None
    e_day = e_hour = e_ts = None

    if start_time:
        sy, sm, sd, sh, s_ts = _parse_datetime(start_time, time_zone_offset_hours)
        s_day, s_hour = f"{sy}-{sm}-{sd}", sh
        _validate_start_day(s_day, year_month)
    elif start_day:
        _validate_start_day(start_day, year_month)
        s_day = start_day

    if end_time:
        ey, em, ed, eh, e_ts = _parse_datetime(end_time, time_zone_offset_hours)
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
                         channel_ids: list[int] = None,
                         start_day: str = None, end_day: str = None,
                         start_time: str = None, end_time: str = None,
                         time_zone_offset_hours: float = 0) -> str:
    """start_time / end_time: 'YYYY-MM-DD HH:MM' interpreted in time_zone_offset_hours."""
    year, month = _year_month(year_month)
    where = _build_time_where(year, month, year_month,
                              start_day=start_day, end_day=end_day,
                              start_time=start_time, end_time=end_time,
                              time_zone_offset_hours=time_zone_offset_hours)
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    where += _channel_where(channel_id=channel_id, channel_ids=channel_ids)
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
                               channel_ids: list[int] = None,
                               start_day: str = None, end_day: str = None,
                               start_time: str = None, end_time: str = None,
                               time_zone_offset_hours: float = 0) -> str:
    """start_time / end_time: 'YYYY-MM-DD HH:MM' interpreted in time_zone_offset_hours."""
    year, month = _year_month(year_month)
    where = _build_time_where(year, month, year_month,
                              start_day=start_day, end_day=end_day,
                              start_time=start_time, end_time=end_time,
                              time_zone_offset_hours=time_zone_offset_hours)
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    where += _channel_where(channel_id=channel_id, channel_ids=channel_ids)
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
                      channel_ids: list[int] = None,
                      start_day: str = None, end_day: str = None,
                      start_time: str = None, end_time: str = None,
                      time_zone_offset_hours: float = 0) -> str:
    """Full billing detail with cache token breakdown from other JSON.

    Extracts cache_tokens, cache_creation_tokens (5m/1h/remaining) and
    tiered pricing info from the 'other' JSON field via Athena json_extract,
    so the aggregation is done server-side for performance.

    start_day / end_day: day-level boundary 'YYYY-MM-DD' (inclusive).
    start_time / end_time: 'YYYY-MM-DD HH:MM' for sub-day precision;
        takes precedence over start_day / end_day when provided.
        Interpreted in time_zone_offset_hours.
    """
    year, month = _year_month(year_month)
    where = _build_time_where(year, month, year_month,
                              start_day=start_day, end_day=end_day,
                              start_time=start_time, end_time=end_time,
                              time_zone_offset_hours=time_zone_offset_hours)
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    where += _channel_where(channel_id=channel_id, channel_ids=channel_ids)
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
                channel_ids: list[int] = None,
                start_day: str = None, end_day: str = None,
                start_time: str = None, end_time: str = None,
                time_zone_offset_hours: float = 0) -> str:
    """start_time / end_time is interpreted in time_zone_offset_hours."""
    year, month = _year_month(year_month)
    where = _build_time_where(year, month, year_month,
                              start_day=start_day, end_day=end_day,
                              start_time=start_time, end_time=end_time,
                              time_zone_offset_hours=time_zone_offset_hours)
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    where += _channel_where(channel_id=channel_id, channel_ids=channel_ids)
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


def model_ranking(year_month: str,
                  start_day: str = None, end_day: str = None,
                  start_time: str = None, end_time: str = None,
                  time_zone_offset_hours: float = 0) -> str:
    year, month = _year_month(year_month)
    where = _build_time_where(year, month, year_month,
                              start_day=start_day, end_day=end_day,
                              start_time=start_time, end_time=end_time,
                              time_zone_offset_hours=time_zone_offset_hours)
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


def channel_summary(year_month: str,
                    start_day: str = None, end_day: str = None,
                    start_time: str = None, end_time: str = None,
                    time_zone_offset_hours: float = 0) -> str:
    year, month = _year_month(year_month)
    where = _build_time_where(year, month, year_month,
                              start_day=start_day, end_day=end_day,
                              start_time=start_time, end_time=end_time,
                              time_zone_offset_hours=time_zone_offset_hours)
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
                     channel_ids: list[int] = None,
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
    where += _channel_where(channel_id=channel_id, channel_ids=channel_ids)
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
                              channel_ids: list[int] = None,
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

    where += _channel_where(channel_id=channel_id, channel_ids=channel_ids)
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
                                      channel_ids: list[int] = None,
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

    where += _channel_where(channel_id=channel_id, channel_ids=channel_ids)
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
                           channel_ids: list[int] = None,
                           model: str = None) -> str:
    """Row-level usage_logs for a single day with cache tokens extracted server-side.

    Returns one row per request with all fields needed for pricing.
    The 'other' JSON is NOT returned — cache tokens are extracted via json_extract.
    """
    year, month = _year_month(year_month)
    where = _partition_filter(year, month, day=day)

    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    where += _channel_where(channel_id=channel_id, channel_ids=channel_ids)
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
                    start_time: str = None, end_time: str = None,
                    time_zone_offset_hours: float = 0) -> list[str]:
    """Return list of day strings (01..N) for the given month.

    start_time / end_time ('YYYY-MM-DD HH:MM') take precedence over
    start_day / end_day when provided. The dates used for partition
    selection are the supplied wall-clock dates; epoch filtering elsewhere
    applies time_zone_offset_hours.
    Used by parallel detail export to generate per-day queries.
    """
    import calendar
    year, month = _year_month(year_month)
    _, ndays = calendar.monthrange(int(year), int(month))
    first_day = 1

    eff_start_day = start_day
    eff_end_day = end_day

    if start_time:
        sy, sm, sd, _sh, _ts = _parse_datetime(start_time, time_zone_offset_hours)
        eff_start_day = f"{sy}-{sm}-{sd}"
    if end_time:
        ey, em, ed, _eh, _ts = _parse_datetime(end_time, time_zone_offset_hours)
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

def anomaly_zero_tokens(year_month: str, day: str = None,
                        start_day: str = None, end_day: str = None,
                        start_time: str = None, end_time: str = None,
                        time_zone_offset_hours: float = 0) -> str:
    year, month = _year_month(year_month)
    where = _build_time_where(year, month, year_month,
                              start_day=start_day, end_day=end_day,
                              start_time=start_time, end_time=end_time,
                              time_zone_offset_hours=time_zone_offset_hours)
    # If day is specified (legacy), override with day filter
    if day:
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

def kpi_summary(year_month: str,
                start_day: str = None, end_day: str = None,
                start_time: str = None, end_time: str = None,
                time_zone_offset_hours: float = 0) -> str:
    year, month = _year_month(year_month)
    where = _build_time_where(year, month, year_month,
                              start_day=start_day, end_day=end_day,
                              start_time=start_time, end_time=end_time,
                              time_zone_offset_hours=time_zone_offset_hours)
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


# ---------------------------------------------------------------------------
# G. Cache hit rate analysis (usage_logs)
# ---------------------------------------------------------------------------

def _tz_offset_interval(offset_hours: float) -> str:
    """Build a SQL INTERVAL literal for a timezone offset in hours.

    Examples: 8.0 -> "INTERVAL '8' HOUR", -5.5 -> "INTERVAL '-330' MINUTE"
    """
    if offset_hours == int(offset_hours):
        return f"INTERVAL '{int(offset_hours)}' HOUR"
    minutes = int(offset_hours * 60)
    return f"INTERVAL '{minutes}' MINUTE"


def monthly_bill_full_tz(year_month: str,
                         tz_offset_hours: float = 8.0,
                         user_id: int = None,
                         channel_id: int = None,
                         channel_ids: list[int] = None) -> str:
    """Full billing detail grouped by local-timezone date.

    Re-partitions records by applying tz_offset_hours to created_at, so each
    'local_date' row represents a wall-clock day in the target timezone.
    Used for timezone-shifted export / reconciliation with vendors on UTC+4, etc.
    """
    year, month = _year_month(year_month)
    where = _partition_filter(year, month)
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    where += _channel_where(channel_id=channel_id, channel_ids=channel_ids)
    interval = _tz_offset_interval(tz_offset_hours)
    return f"""
SELECT
    DATE_FORMAT(from_unixtime(created_at) + {interval}, '%Y-%m-%d') AS local_date,
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
GROUP BY DATE_FORMAT(from_unixtime(created_at) + {interval}, '%Y-%m-%d'),
         user_id, username, channel_id, model_name
ORDER BY local_date, user_id, total_usd DESC
"""


def daily_trend_tz(year_month: str,
                   tz_offset_hours: float = 8.0,
                   user_id: int = None,
                   channel_id: int = None,
                   channel_ids: list[int] = None,
                   start_day: str = None, end_day: str = None,
                   start_time: str = None, end_time: str = None) -> str:
    """Daily trend grouped by local-timezone date.

    start_day/end_day: 'YYYY-MM-DD' boundary in the target timezone.
    start_time/end_time: 'YYYY-MM-DD HH:MM' in the target timezone.
    """
    year, month = _year_month(year_month)
    # Build base partition filter
    where = _partition_filter(year, month)

    # Apply date/time range filters in the target timezone
    # Convert local datetime bounds to UTC timestamps for row-level filtering
    if start_day:
        # start_day 00:00 in target timezone -> UTC timestamp
        from datetime import datetime, timedelta, timezone as tz
        sy, sm, sd = start_day.split('-')
        local_start = datetime(int(sy), int(sm), int(sd), 0, 0,
                               tzinfo=tz(timedelta(hours=float(tz_offset_hours))))
        start_ts = int(local_start.timestamp())
        where += f" AND created_at >= {start_ts}"

    if end_day:
        # end_day 23:59:59 in target timezone -> UTC timestamp
        from datetime import datetime, timedelta, timezone as tz
        ey, em, ed = end_day.split('-')
        local_end = datetime(int(ey), int(em), int(ed), 23, 59, 59,
                              tzinfo=tz(timedelta(hours=float(tz_offset_hours))))
        end_ts = int(local_end.timestamp())
        where += f" AND created_at <= {end_ts}"

    if start_time:
        from datetime import datetime, timedelta, timezone as tz
        sy, sm, sd, sh, smm = _parse_datetime(start_time, tz_offset_hours)
        where += f" AND created_at >= {smm}"

    if end_time:
        from datetime import datetime, timedelta, timezone as tz
        ey, em, ed, eh, e_ts = _parse_datetime(end_time, tz_offset_hours)
        where += f" AND created_at < {e_ts + 60}"

    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    where += _channel_where(channel_id=channel_id, channel_ids=channel_ids)
    interval = _tz_offset_interval(tz_offset_hours)
    return f"""
SELECT
    DATE_FORMAT(from_unixtime(created_at) + {interval}, '%Y-%m-%d') AS local_date,
    COUNT(*)                            AS call_count,
    SUM(prompt_tokens + completion_tokens) AS total_tokens,
    SUM(quota)                          AS total_quota,
    ROUND(SUM(quota) / 500000.0, 4)     AS total_usd
FROM ezmodel_logs.usage_logs
WHERE {where}
GROUP BY DATE_FORMAT(from_unixtime(created_at) + {interval}, '%Y-%m-%d')
ORDER BY local_date
"""


def raw_usage_detail_daily_tz(year_month: str, local_date: str,
                              tz_offset_hours: float = 8.0,
                              user_id: int = None,
                              channel_id: int = None,
                              channel_ids: list[int] = None,
                              model: str = None) -> str:
    """Row-level usage_logs for a single local-timezone date.

    Computes the UTC partition day range that could contain records for the
    given local_date under tz_offset_hours, then filters rows by
    created_at range corresponding to [local_date 00:00, local_date+1 00:00)
    in the target timezone.
    """
    from datetime import datetime, timedelta, timezone

    # Parse local_date and compute UTC boundaries
    ld = datetime.strptime(local_date, "%Y-%m-%d")
    tz = timezone(timedelta(hours=tz_offset_hours))
    local_start = ld.replace(tzinfo=tz)
    local_end = local_start + timedelta(days=1)
    ts_start = int(local_start.timestamp())
    ts_end = int(local_end.timestamp())

    # UTC day range for partition pruning
    utc_start = datetime.fromtimestamp(ts_start, tz=timezone.utc)
    utc_end = datetime.fromtimestamp(ts_end, tz=timezone.utc)

    year, month = _year_month(year_month)
    # Use broad partition filter covering the UTC month + day range
    where = f"year = {_q(year)} AND month = {_q(month)}"
    day_lo = f"{utc_start.day:02d}"
    day_hi = f"{utc_end.day:02d}"
    if utc_start.month == utc_end.month:
        where += f" AND day >= {_q(day_lo)} AND day <= {_q(day_hi)}"

    where += f" AND created_at >= {ts_start} AND created_at < {ts_end}"

    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    where += _channel_where(channel_id=channel_id, channel_ids=channel_ids)
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


def detail_day_list_tz(year_month: str,
                       tz_offset_hours: float = 8.0) -> list[str]:
    """Return list of local-date strings for a month under given timezone offset.

    Covers all local dates whose UTC footprint overlaps with the given month.
    For UTC+8, 2026-03 covers local dates 2026-03-01 through 2026-03-31.
    (The UTC partition for the month may miss the last few hours of the last
    local date, but those will be caught by the previous UTC month.)
    """
    import calendar
    from datetime import datetime, timedelta, timezone

    ym_year, ym_month = int(year_month.split("-")[0]), int(year_month.split("-")[1])
    _, ndays = calendar.monthrange(ym_year, ym_month)
    return [f"{ym_year}-{ym_month:02d}-{d:02d}" for d in range(1, ndays + 1)]


def cache_hit_rate_by_user(year_month: str, user_id: int = None,
                           channel_id: int = None,
                           channel_ids: list[int] = None,
                           model: str = None,
                           start_day: str = None, end_day: str = None,
                           start_time: str = None, end_time: str = None) -> str:
    """Cache hit rate aggregated by user_id, channel_id, model_name.

    Reports total requests, cache-hit request count, cached token totals,
    cache creation token totals, and hit-rate percentages.

    start_time / end_time: 'YYYY-MM-DD HH:MM' UTC for sub-day precision.
    """
    year, month = _year_month(year_month)
    where = _build_time_where(year, month, year_month,
                              start_day=start_day, end_day=end_day,
                              start_time=start_time, end_time=end_time)
    if user_id is not None:
        where += f" AND user_id = {int(user_id)}"
    where += _channel_where(channel_id=channel_id, channel_ids=channel_ids)
    if model:
        where += f" AND model_name = {_q(model)}"
    return f"""
SELECT
    user_id,
    username,
    channel_id,
    model_name,
    COUNT(*)  AS total_requests,
    SUM(CASE WHEN COALESCE(CAST(json_extract_scalar(other, '$.cache_tokens') AS BIGINT), 0) > 0
             THEN 1 ELSE 0 END)
        AS cache_hit_requests,
    ROUND(SUM(CASE WHEN COALESCE(CAST(json_extract_scalar(other, '$.cache_tokens') AS BIGINT), 0) > 0
                   THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2)
        AS cache_hit_rate_pct,
    SUM(prompt_tokens)  AS total_prompt_tokens,
    SUM(COALESCE(CAST(json_extract_scalar(other, '$.cache_tokens') AS BIGINT), 0))
        AS total_cached_tokens,
    ROUND(SUM(COALESCE(CAST(json_extract_scalar(other, '$.cache_tokens') AS BIGINT), 0)) * 100.0
          / NULLIF(SUM(prompt_tokens), 0), 2)
        AS cached_token_ratio_pct,
    SUM(COALESCE(CAST(json_extract_scalar(other, '$.cache_creation_tokens') AS BIGINT), 0))
        AS total_cache_creation_tokens,
    SUM(CASE WHEN COALESCE(CAST(json_extract_scalar(other, '$.cache_creation_tokens') AS BIGINT), 0) > 0
             THEN 1 ELSE 0 END)
        AS cache_creation_requests,
    SUM(COALESCE(CAST(json_extract_scalar(other, '$.cache_creation_tokens_5m') AS BIGINT), 0))
        AS total_cache_creation_5m_tokens,
    SUM(COALESCE(CAST(json_extract_scalar(other, '$.cache_creation_tokens_1h') AS BIGINT), 0))
        AS total_cache_creation_1h_tokens
FROM ezmodel_logs.usage_logs
WHERE {where}
GROUP BY user_id, username, channel_id, model_name
HAVING SUM(COALESCE(CAST(json_extract_scalar(other, '$.cache_tokens') AS BIGINT), 0)) > 0
    OR SUM(COALESCE(CAST(json_extract_scalar(other, '$.cache_creation_tokens') AS BIGINT), 0)) > 0
ORDER BY total_cached_tokens DESC
"""


def cache_hit_rate_summary(year_month: str,
                           channel_id: int = None,
                           channel_ids: list[int] = None,
                           start_day: str = None, end_day: str = None,
                           start_time: str = None, end_time: str = None) -> str:
    """Cache hit rate aggregated by channel_id and model_name (no user dimension).

    Useful for overall cache effectiveness monitoring per channel/model.
    """
    year, month = _year_month(year_month)
    where = _build_time_where(year, month, year_month,
                              start_day=start_day, end_day=end_day,
                              start_time=start_time, end_time=end_time)
    where += _channel_where(channel_id=channel_id, channel_ids=channel_ids)
    return f"""
SELECT
    channel_id,
    model_name,
    COUNT(*)  AS total_requests,
    SUM(CASE WHEN COALESCE(CAST(json_extract_scalar(other, '$.cache_tokens') AS BIGINT), 0) > 0
             THEN 1 ELSE 0 END)
        AS cache_hit_requests,
    ROUND(SUM(CASE WHEN COALESCE(CAST(json_extract_scalar(other, '$.cache_tokens') AS BIGINT), 0) > 0
                   THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2)
        AS cache_hit_rate_pct,
    SUM(prompt_tokens)  AS total_prompt_tokens,
    SUM(COALESCE(CAST(json_extract_scalar(other, '$.cache_tokens') AS BIGINT), 0))
        AS total_cached_tokens,
    ROUND(SUM(COALESCE(CAST(json_extract_scalar(other, '$.cache_tokens') AS BIGINT), 0)) * 100.0
          / NULLIF(SUM(prompt_tokens), 0), 2)
        AS cached_token_ratio_pct,
    SUM(COALESCE(CAST(json_extract_scalar(other, '$.cache_creation_tokens') AS BIGINT), 0))
        AS total_cache_creation_tokens,
    SUM(COALESCE(CAST(json_extract_scalar(other, '$.cache_creation_tokens_5m') AS BIGINT), 0))
        AS total_cache_creation_5m_tokens,
    SUM(COALESCE(CAST(json_extract_scalar(other, '$.cache_creation_tokens_1h') AS BIGINT), 0))
        AS total_cache_creation_1h_tokens
FROM ezmodel_logs.usage_logs
WHERE {where}
GROUP BY channel_id, model_name
ORDER BY total_cached_tokens DESC
"""
