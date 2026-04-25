"""
Athena 查询引擎 — 查询执行、结果解析、S3 缓存、自动分页

所有查询入口的公共基础设施。
"""

import hashlib
import io
import os
import re
import sys
import time
from datetime import datetime, timezone

if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import boto3
import pandas as pd
from botocore.config import Config

from logging_config import get_logger, log_query_complete, log_cache_hit, log_cache_miss, log_cache_write, log_error

logger = get_logger("athena_engine")

# Import cost monitor for Athena query cost tracking
try:
    from cost_monitor import (
        log_query_cost as cost_log_query_cost,
        log_cache_hit as cost_log_cache_hit,
        get_total_cost,
        get_cost_summary,
        reset_tracking,
        get_query_costs,
    )
    COST_MONITOR_AVAILABLE = True
except ImportError:
    # Cost monitor not available, use no-op functions
    COST_MONITOR_AVAILABLE = False

    def cost_log_query_cost(*args, **kwargs):
        return 0.0

    def cost_log_cache_hit(*args, **kwargs):
        pass

    def get_total_cost():
        return 0.0

    def get_cost_summary():
        return {}

    def reset_tracking():
        pass

    def get_query_costs():
        return {}

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REGION = os.getenv("AWS_REGION", os.getenv("RAW_LOG_S3_REGION", "ap-southeast-1"))
WORKGROUP = os.getenv("ATHENA_WORKGROUP", "primary")
RESULT_BUCKET = os.getenv("ATHENA_RESULT_BUCKET", "ezmodel-log")
RESULT_PREFIX = os.getenv("ATHENA_RESULT_PREFIX", "athena-results")
RESULT_LOCATION = f"s3://{RESULT_BUCKET}/{RESULT_PREFIX}/"

CACHE_BUCKET = os.getenv("ATHENA_CACHE_BUCKET", RESULT_BUCKET)
CACHE_PREFIX = os.getenv("ATHENA_CACHE_PREFIX", "athena-cache")
REPORT_PREFIX = os.getenv("REPORT_S3_PREFIX", "billing-reports")

AK = os.getenv("RAW_LOG_S3_ACCESS_KEY_ID", os.getenv("AWS_ACCESS_KEY_ID", ""))
SK = os.getenv("RAW_LOG_S3_SECRET_ACCESS_KEY", os.getenv("AWS_SECRET_ACCESS_KEY", ""))

QUOTA_TO_USD = 500_000.0

# ---------------------------------------------------------------------------
# Clients (lazy singletons)
# ---------------------------------------------------------------------------

_athena_client = None
_s3_client = None


def _get_athena():
    global _athena_client
    if _athena_client is None:
        kw = {"region_name": REGION}
        if AK and SK:
            kw["aws_access_key_id"] = AK
            kw["aws_secret_access_key"] = SK
        _athena_client = boto3.client("athena", **kw)
    return _athena_client


def _get_s3():
    global _s3_client
    if _s3_client is None:
        # 配置自动重试：最多重试 5 次，使用自适应模式
        config = Config(
            retries={
                'max_attempts': 5,      # 最多重试 5 次
                'mode': 'adaptive'       # 自适应重试模式（标准/legacy/adaptive）
            },
            connect_timeout=120,        # 连接超时 120 秒
            read_timeout=120,           # 读取超时 120 秒
        )
        kw = {"region_name": REGION, "config": config}
        if AK and SK:
            kw["aws_access_key_id"] = AK
            kw["aws_secret_access_key"] = SK
        endpoint = os.getenv("RAW_LOG_S3_ENDPOINT", "")
        if endpoint:
            kw["endpoint_url"] = endpoint
        _s3_client = boto3.client("s3", **kw)
    return _s3_client


# ---------------------------------------------------------------------------
# Raw query execution
# ---------------------------------------------------------------------------

def run_query(sql: str, poll_interval: float = 1.5) -> dict:
    """Execute an Athena query and return structured results.

    Returns dict with keys: headers, rows, row_count, scanned_bytes, exec_ms
    """
    client = _get_athena()
    resp = client.start_query_execution(
        QueryString=sql,
        ResultConfiguration={"OutputLocation": RESULT_LOCATION},
        WorkGroup=WORKGROUP,
    )
    exec_id = resp["QueryExecutionId"]

    while True:
        time.sleep(poll_interval)
        status = client.get_query_execution(QueryExecutionId=exec_id)
        state = status["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break

    if state != "SUCCEEDED":
        reason = status["QueryExecution"]["Status"].get("StateChangeReason", "")
        log_error(logger, "AthenaQueryError", f"Query {state}: {reason}",
                  query_id=exec_id, state=state)
        raise RuntimeError(f"Athena query {state}: {reason}")

    stats = status["QueryExecution"]["Statistics"]
    scanned = stats.get("DataScannedInBytes", 0)
    exec_ms = stats.get("EngineExecutionTimeInMillis", 0)

    headers, rows = _fetch_all_results(client, exec_id)

    log_query_complete(logger, exec_id, scanned, exec_ms, len(rows))

    # Track query cost
    query_name = _extract_query_name(sql)
    cost_log_query_cost(scanned, query_name, context={"exec_id": exec_id, "exec_ms": exec_ms})

    return {
        "headers": headers,
        "rows": rows,
        "row_count": len(rows),
        "scanned_bytes": scanned,
        "exec_ms": exec_ms,
    }


def _fetch_all_results(client, exec_id: str):
    """Paginate through all result rows."""
    headers = None
    rows = []
    next_token = None

    while True:
        kw = {"QueryExecutionId": exec_id, "MaxResults": 1000}
        if next_token:
            kw["NextToken"] = next_token
        resp = client.get_query_results(**kw)

        result_rows = resp["ResultSet"]["Rows"]
        for i, row in enumerate(result_rows):
            vals = [col.get("VarCharValue", "") for col in row["Data"]]
            if headers is None and i == 0:
                headers = vals
                continue
            rows.append(vals)

        next_token = resp.get("NextToken")
        if not next_token:
            break
        headers = headers  # already set, skip header row in subsequent pages

    return headers or [], rows


def _extract_query_name(sql: str) -> str:
    """Extract a meaningful query name from SQL for cost tracking.

    Uses patterns like:
    - FROM table_name -> "table_name scan"
    - aggregation type (COUNT/SUM/etc) -> "COUNT aggregation"
    Falls back to first 50 chars of SQL
    """
    sql_upper = sql.upper().strip()

    # Try to extract table name after FROM
    from_match = re.search(r'\bFROM\s+([^\s,(]+)', sql_upper, re.IGNORECASE)
    if from_match:
        table = from_match.group(1).strip('"`[]')
        # Check for aggregation
        if any(agg in sql_upper for agg in ('COUNT(', 'SUM(', 'AVG(', 'MAX(', 'MIN(')):
            agg = next((agg for agg in ('COUNT', 'SUM', 'AVG', 'MAX', 'MIN')
                       if f'{agg}(' in sql_upper), 'AGG')
            return f"{agg} on {table}"
        return f"{table} scan"

    # Try to identify query type
    if sql_upper.startswith('SELECT'):
        return 'SELECT query'
    elif sql_upper.startswith('WITH'):
        return 'CTE query'
    elif sql_upper.startswith('INSERT'):
        return 'INSERT query'
    elif sql_upper.startswith('CREATE'):
        return 'CREATE query'
    elif sql_upper.startswith('DROP'):
        return 'DROP query'
    elif sql_upper.startswith('ALTER'):
        return 'ALTER query'

    # Fallback: first 50 chars
    return sql[:50].strip()


def run_query_df(sql: str, poll_interval: float = 1.5) -> pd.DataFrame:
    """Execute query and return a pandas DataFrame."""
    result = run_query(sql, poll_interval)
    if not result["headers"]:
        return pd.DataFrame()
    df = pd.DataFrame(result["rows"], columns=result["headers"])
    df = _auto_convert_types(df)
    return df


def _auto_convert_types(df: pd.DataFrame) -> pd.DataFrame:
    """Best-effort numeric conversion for DataFrame columns."""
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass
    return df


# ---------------------------------------------------------------------------
# S3 cache layer
# ---------------------------------------------------------------------------

def _cache_key(sql: str) -> str:
    normalized = re.sub(r"\s+", " ", sql.strip()).lower()
    h = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return f"{CACHE_PREFIX}/{h}.parquet"


def _infer_cache_ttl(sql: str) -> int | None:
    """Infer TTL in seconds based on the date partitions in the query.

    - Historical months (not current): None (permanent)
    - Current month but not today: 3600 (1 hour)
    - Today: 600 (10 minutes)
    - Cannot determine: 600 (10 minutes, conservative)
    """
    now = datetime.now(timezone.utc)
    current_year = str(now.year)
    current_month = f"{now.month:02d}"
    current_day = f"{now.day:02d}"

    year_match = re.search(r"year\s*=\s*'(\d{4})'", sql, re.IGNORECASE)
    month_match = re.search(r"month\s*=\s*'(\d{1,2})'", sql, re.IGNORECASE)
    day_match = re.search(r"day\s*=\s*'(\d{1,2})'", sql, re.IGNORECASE)

    if not year_match or not month_match:
        return 600

    q_year = year_match.group(1)
    q_month = f"{int(month_match.group(1)):02d}"

    if q_year < current_year or (q_year == current_year and q_month < current_month):
        return None  # permanent

    if q_year == current_year and q_month == current_month:
        if day_match:
            q_day = f"{int(day_match.group(1)):02d}"
            if q_day == current_day:
                return 600  # 10 min
            elif q_day < current_day:
                return 3600  # 1 hour for past days in current month
        return 3600  # current month, no specific day

    return 600


def _cache_read(key: str, ttl: int | None) -> pd.DataFrame | None:
    """Try to read cached result from S3. Returns None on miss."""
    s3 = _get_s3()
    try:
        resp = s3.head_object(Bucket=CACHE_BUCKET, Key=key)
    except Exception:
        # Catch all exceptions (network, ClientError, etc.) to fail fast
        return None

    if ttl is not None:
        last_modified = resp["LastModified"]
        age = (datetime.now(timezone.utc) - last_modified).total_seconds()
        if age > ttl:
            return None

    try:
        obj = s3.get_object(Bucket=CACHE_BUCKET, Key=key)
        buf = io.BytesIO(obj["Body"].read())
        return pd.read_parquet(buf)
    except Exception:
        return None


def _cache_write(key: str, df: pd.DataFrame):
    """Write DataFrame to S3 as Parquet."""
    if df.empty:
        return
    s3 = _get_s3()
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    buf.seek(0)
    try:
        s3.put_object(Bucket=CACHE_BUCKET, Key=key, Body=buf.getvalue(),
                      ContentType="application/octet-stream")
        log_cache_write(logger, key, len(df))
    except Exception as e:
        log_error(logger, "CacheWriteError", str(e), cache_key=key)


def run_query_cached(sql: str, ttl: int | None = ..., no_cache: bool = False) -> pd.DataFrame:
    """Execute query with S3 caching.

    Args:
        sql: The SQL query
        ttl: Cache TTL in seconds. None=permanent, ...=auto-infer from query
        no_cache: Skip cache entirely
    """
    if ttl is ...:
        ttl = _infer_cache_ttl(sql)

    key = _cache_key(sql)
    query_name = _extract_query_name(sql)

    if not no_cache:
        cached = _cache_read(key, ttl)
        if cached is not None:
            log_cache_hit(logger, key, ttl)
            # Track cache hit (cost = 0)
            cost_log_cache_hit(query_name)
            return cached
        log_cache_miss(logger, key, ttl)

    df = run_query_df(sql)

    if not no_cache and not df.empty:
        _cache_write(key, df)

    return df


# ---------------------------------------------------------------------------
# Safety: raw_logs partition guard
# ---------------------------------------------------------------------------

_RAW_LOGS_RE = re.compile(r"\braw_logs\b", re.IGNORECASE)
_DAY_PARTITION_RE = re.compile(r"\bday\s*=\s*'", re.IGNORECASE)


def validate_raw_logs_partition(sql: str):
    """Raise ValueError if SQL queries raw_logs without a day partition filter."""
    if _RAW_LOGS_RE.search(sql) and not _DAY_PARTITION_RE.search(sql):
        raise ValueError(
            "查询 raw_logs 必须指定 day 分区过滤（如 AND day='29'），"
            "否则会扫描全月数据（~100 GB，约 $0.50/次）。\n"
            "如果确实需要全月查询，请使用 run_query_df() 跳过此检查。"
        )


def run_safe_query(sql: str, no_cache: bool = False) -> pd.DataFrame:
    """Run query with partition safety check + caching."""
    validate_raw_logs_partition(sql)
    return run_query_cached(sql, no_cache=no_cache)


# ---------------------------------------------------------------------------
# S3 direct CSV download (bypasses slow get_query_results pagination)
# ---------------------------------------------------------------------------

def _wait_for_query(exec_id: str, poll_interval: float = 2.0) -> dict:
    """Poll until query completes. Returns the QueryExecution dict."""
    client = _get_athena()
    while True:
        time.sleep(poll_interval)
        resp = client.get_query_execution(QueryExecutionId=exec_id)
        qe = resp["QueryExecution"]
        state = qe["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            if state != "SUCCEEDED":
                reason = qe["Status"].get("StateChangeReason", "")
                raise RuntimeError(f"Athena query {state}: {reason}")
            return qe


def _download_s3_csv(s3_uri: str) -> pd.DataFrame:
    """Download Athena result CSV directly from S3 into a DataFrame."""
    import urllib.parse
    parsed = urllib.parse.urlparse(s3_uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    s3 = _get_s3()
    obj = s3.get_object(Bucket=bucket, Key=key)
    df = pd.read_csv(io.BytesIO(obj["Body"].read()), low_memory=False)
    return _auto_convert_types(df)


def run_query_s3(sql: str, poll_interval: float = 2.0) -> pd.DataFrame:
    """Execute query and download results directly from S3 CSV.

    Much faster than get_query_results pagination for large result sets.
    For 200K+ rows this is 10-50x faster.
    """
    client = _get_athena()
    resp = client.start_query_execution(
        QueryString=sql,
        ResultConfiguration={"OutputLocation": RESULT_LOCATION},
        WorkGroup=WORKGROUP,
    )
    qe = _wait_for_query(resp["QueryExecutionId"], poll_interval)
    output_uri = qe["ResultConfiguration"]["OutputLocation"]
    return _download_s3_csv(output_uri)


# ---------------------------------------------------------------------------
# Parallel query execution (submit all, wait all, download all)
# ---------------------------------------------------------------------------

def run_queries_parallel(sqls: list[str], poll_interval: float = 3.0,
                         max_concurrent: int = 20) -> list[pd.DataFrame]:
    """Submit multiple Athena queries in parallel, download results via S3 CSV.

    Submits up to max_concurrent queries at once, polls until all complete,
    then downloads results. Total wall time ≈ slowest single query.
    """
    dfs = []
    for df in run_queries_parallel_iter(sqls, poll_interval, max_concurrent):
        dfs.append(df)
    return dfs


def run_queries_parallel_iter(sqls: list[str], poll_interval: float = 3.0,
                              max_concurrent: int = 20):
    """Submit queries in parallel, yield (index, DataFrame) as each completes.

    Yields tuples of (query_index, DataFrame) in completion order.
    Downloads happen in a background thread so that the caller's processing
    (pricing, CSV write) does not block downloads of other completed queries.
    """
    from collections import deque
    from concurrent.futures import ThreadPoolExecutor

    client = _get_athena()
    exec_ids = []

    for i in range(0, len(sqls), max_concurrent):
        batch = sqls[i:i + max_concurrent]
        for sql in batch:
            resp = client.start_query_execution(
                QueryString=sql,
                ResultConfiguration={"OutputLocation": RESULT_LOCATION},
                WorkGroup=WORKGROUP,
            )
            exec_ids.append(resp["QueryExecutionId"])

    pending = set(range(len(exec_ids)))
    ready_queue: deque = deque()
    download_pool = ThreadPoolExecutor(max_workers=4)
    active_downloads = {}

    def _bg_download(idx, uri):
        df = _download_s3_csv(uri)
        return idx, df

    while pending or active_downloads or ready_queue:
        if ready_queue:
            yield ready_queue.popleft()
            continue

        # Check for completed downloads
        done_keys = []
        for key, future in active_downloads.items():
            if future.done():
                done_keys.append(key)
                try:
                    ready_queue.append(future.result())
                except Exception as e:
                    log_error(logger, "ParallelDownloadError", str(e), query_index=key)
                    ready_queue.append((key, pd.DataFrame()))
        for key in done_keys:
            del active_downloads[key]

        if ready_queue:
            continue

        if not pending:
            time.sleep(0.1)
            continue

        time.sleep(poll_interval)
        for idx in list(pending):
            resp = client.get_query_execution(QueryExecutionId=exec_ids[idx])
            qe = resp["QueryExecution"]
            state = qe["Status"]["State"]
            if state == "SUCCEEDED":
                pending.discard(idx)
                output_uri = qe["ResultConfiguration"]["OutputLocation"]
                active_downloads[idx] = download_pool.submit(
                    _bg_download, idx, output_uri)
            elif state in ("FAILED", "CANCELLED"):
                reason = qe["Status"].get("StateChangeReason", "")
                log_error(logger, "ParallelQueryError", f"Query {state}: {reason}",
                         query_index=idx, state=state, reason=reason)
                pending.discard(idx)
                ready_queue.append((idx, pd.DataFrame()))

    download_pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# S3 report upload + presigned URL
# ---------------------------------------------------------------------------

def upload_to_s3(local_path: str, s3_key: str = None) -> str:
    """Upload a local file to S3. Returns the S3 key used.

    Default key: {REPORT_PREFIX}/{year_month}/{filename}
    where year_month is extracted from the filename (e.g. bill_2026-03_...).
    """
    filename = os.path.basename(local_path)
    if s3_key is None:
        ym = _extract_year_month(filename)
        s3_key = f"{REPORT_PREFIX}/{ym}/{filename}" if ym else f"{REPORT_PREFIX}/{filename}"

    s3 = _get_s3()
    content_type = "application/gzip" if filename.endswith(".gz") else \
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
                   if filename.endswith(".xlsx") else "application/octet-stream"

    s3.upload_file(local_path, RESULT_BUCKET, s3_key,
                   ExtraArgs={"ContentType": content_type})
    return s3_key


_s3_presign_client = None


def _get_s3_presign():
    """S3 client for presigned URL generation (SigV4 + virtual-hosted style)."""
    global _s3_presign_client
    if _s3_presign_client is None:
        from botocore.config import Config
        kw = {"region_name": REGION,
              "config": Config(signature_version="s3v4",
                               s3={"addressing_style": "virtual"})}
        if AK and SK:
            kw["aws_access_key_id"] = AK
            kw["aws_secret_access_key"] = SK
        _s3_presign_client = boto3.client("s3", **kw)
    return _s3_presign_client


def generate_presigned_url(s3_key: str, expires_in: int = 86400) -> str:
    """Generate a presigned download URL for an S3 object.

    Uses SigV4 with regional endpoint for cross-region compatibility.
    Default expiry: 24 hours (86400 seconds).
    """
    s3 = _get_s3_presign()
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": RESULT_BUCKET, "Key": s3_key},
        ExpiresIn=expires_in)


def upload_and_sign(local_path: str, s3_key: str = None,
                    expires_in: int = 86400) -> dict:
    """Upload file to S3 and return dict with key + presigned URL."""
    key = upload_to_s3(local_path, s3_key)
    url = generate_presigned_url(key, expires_in)
    return {"s3_key": key, "url": url}


def _extract_year_month(filename: str) -> str | None:
    """Extract YYYY-MM from a filename like bill_2026-03_user89.xlsx."""
    m = re.search(r"(\d{4}-\d{2})", filename)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Cost tracking convenience functions
# ---------------------------------------------------------------------------

def get_session_total_cost() -> float:
    """Get total cost for the current session.

    Returns the total USD cost of all Athena queries executed in this session.
    Cache hits are counted with zero cost.
    """
    return get_total_cost()


def get_session_cost_summary() -> dict:
    """Get detailed cost summary for the current session.

    Returns dict with keys:
        total_cost_usd: Total cost in USD
        total_scanned_tb: Total data scanned in TB
        query_count: Total number of queries
        cache_hits: Number of cache hits
        cache_hit_rate: Cache hit rate percentage
    """
    return get_cost_summary()
