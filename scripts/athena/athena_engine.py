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
        kw = {"region_name": REGION}
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
        raise RuntimeError(f"Athena query {state}: {reason}")

    stats = status["QueryExecution"]["Statistics"]
    scanned = stats.get("DataScannedInBytes", 0)
    exec_ms = stats.get("EngineExecutionTimeInMillis", 0)

    headers, rows = _fetch_all_results(client, exec_id)

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
    except s3.exceptions.ClientError:
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
    except Exception as e:
        print(f"[cache] write failed: {e}", file=sys.stderr)


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

    if not no_cache:
        cached = _cache_read(key, ttl)
        if cached is not None:
            return cached

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

    results = [None] * len(exec_ids)
    pending = set(range(len(exec_ids)))

    while pending:
        time.sleep(poll_interval)
        for idx in list(pending):
            resp = client.get_query_execution(QueryExecutionId=exec_ids[idx])
            qe = resp["QueryExecution"]
            state = qe["Status"]["State"]
            if state == "SUCCEEDED":
                results[idx] = qe
                pending.discard(idx)
            elif state in ("FAILED", "CANCELLED"):
                reason = qe["Status"].get("StateChangeReason", "")
                print(f"[parallel] query {idx} {state}: {reason}", file=sys.stderr)
                results[idx] = None
                pending.discard(idx)

    dfs = []
    for qe in results:
        if qe is None:
            dfs.append(pd.DataFrame())
        else:
            output_uri = qe["ResultConfiguration"]["OutputLocation"]
            dfs.append(_download_s3_csv(output_uri))
    return dfs
