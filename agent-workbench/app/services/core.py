"""共用工具函数与常量：ID 生成、JSON 序列化、环境变量读取等。

从 main.py 提取，供 routers / services / worker / scheduler 共用。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
from fastapi import HTTPException


APP_ROOT = Path(__file__).resolve().parent.parent
WORKBENCH_ROOT = APP_ROOT.parent
SCHEMA_PATH = WORKBENCH_ROOT / "db" / "schema.sql"

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/agent_workbench")

JOB_CONCURRENCY_DEFAULTS = {
    "billing_run": 1,
    "agent_work": 1,
}
STARTABLE_JOB_STATUSES = {"CREATED", "QUEUED", "FAILED"}
TERMINAL_JOB_STATUSES = {"COMPLETED"}
BILL_TYPES = {
    "customer_invoice",
    "internal_customer_bill",
    "channel_cost_bill",
    "daily_channel_cost_snapshot",
}
DEFAULT_SCHEDULES = [
    {
        "id": "sch-daily-channel-cost",
        "name": "每日渠道成本快照",
        "schedule_type": "daily_channel_cost_snapshot",
        "cron_expr": "30 3 * * *",
        "timezone": "Asia/Hong_Kong",
        "payload": {"bill_type": "daily_channel_cost_snapshot", "target_type": "channel", "target_id": "all", "run_time": "03:30", "split_channels": True},
    },
    {
        "id": "sch-monthly-customer-invoices",
        "name": "每月客户版账单",
        "schedule_type": "monthly_customer_invoices",
        "cron_expr": "0 6 1 * *",
        "timezone": "Asia/Hong_Kong",
        "payload": {"bill_type": "customer_invoice", "target_type": "customer", "customer_view": True, "detail": True, "split_customers": True},
    },
    {
        "id": "sch-monthly-internal-channel-bills",
        "name": "每月内部版与渠道账单",
        "schedule_type": "monthly_internal_channel_bills",
        "cron_expr": "30 7 1 * *",
        "timezone": "Asia/Hong_Kong",
        "payload": {"bill_types": ["internal_customer_bill", "channel_cost_bill"], "target_type": "all", "detail": True, "split_internal_customers": True, "split_channels": True},
    },
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def dumps_json(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    return value


def checksum_config(pricing: dict[str, Any], discounts: dict[str, Any]) -> str:
    return hashlib.sha256(dumps_json({"pricing": pricing, "discounts": discounts}).encode("utf-8")).hexdigest()


@contextmanager
def db_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_one(cur, query: str, args: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cur.execute(query, args)
    row = cur.fetchone()
    return dict(row) if row else None


def fetch_all(cur, query: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(query, args)
    return [dict(row) for row in cur.fetchall()]


def env_int(name: str, default: int, minimum: int = 1, maximum: int = 64) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def clamp_int(value: int | None, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def fetch_scalar(cur, query: str, args: tuple[Any, ...] = ()) -> Any:
    cur.execute(query, args)
    row = cur.fetchone()
    if row is None:
        return None
    if hasattr(row, "keys"):
        return row[next(iter(row.keys()))]
    return row[0]


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def content_type_for_filename(filename: str) -> str:
    lowered = filename.lower()
    if lowered.endswith(".json"):
        return "application/json"
    if lowered.endswith(".csv"):
        return "text/csv; charset=utf-8"
    if lowered.endswith(".md"):
        return "text/markdown; charset=utf-8"
    return "application/octet-stream"


def content_type_for_path(path: Path) -> str:
    return content_type_for_filename(path.name)


def safe_filename(value: str) -> str:
    name = Path(value or "").name.strip()
    return re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "_", name)[:180]


def slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-")
    if not cleaned:
        raise HTTPException(status_code=400, detail="slug fields cannot be empty")
    return cleaned


def filename_from_uri(uri: str, fallback: str) -> str:
    if not uri:
        return fallback
    text = uri.rstrip("/")
    name = text.rsplit("/", 1)[-1]
    return safe_filename(name or fallback)


def uri_to_prefix(uri: str | None, local_dir: Path | None = None) -> str | None:
    if not uri:
        return None
    if uri.startswith("s3://"):
        parts = uri.removeprefix("s3://").split("/", 1)
        return parts[1].strip("/") if len(parts) == 2 else ""
    if uri.startswith("file://"):
        path = Path(uri.removeprefix("file://"))
        if local_dir:
            try:
                return path.relative_to(local_dir).as_posix().strip("/")
            except ValueError:
                return None
        return None
    return uri.strip("/")


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in job.items() if k not in {"pricing_snapshot", "discounts_snapshot"}}


def init_schema() -> None:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


def seed_default_schedules() -> None:
    with db_conn() as conn:
        with conn.cursor() as cur:
            for schedule in DEFAULT_SCHEDULES:
                cur.execute(
                    """
                    INSERT INTO schedules (
                        id, name, schedule_type, cron_expr, timezone, payload, created_by
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 'system')
                    ON CONFLICT (name) DO UPDATE
                    SET schedule_type = EXCLUDED.schedule_type,
                        cron_expr = EXCLUDED.cron_expr,
                        timezone = EXCLUDED.timezone,
                        payload = schedules.payload || EXCLUDED.payload,
                        updated_at = NOW()
                    """,
                    (
                        schedule["id"],
                        schedule["name"],
                        schedule["schedule_type"],
                        schedule["cron_expr"],
                        schedule["timezone"],
                        psycopg2.extras.Json(schedule["payload"]),
                    ),
                )


def normalize_reference_ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    ids: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            ids.append(text)
    return ids[:12]


def normalize_bill_type(value: str | None, metadata: dict[str, Any] | None = None, channel_id: int | None = None) -> str:
    metadata = metadata or {}
    raw = value or metadata.get("bill_type")
    if raw:
        bill_type = str(raw)
    elif metadata.get("customer_view"):
        bill_type = "customer_invoice"
    elif channel_id is not None:
        bill_type = "channel_cost_bill"
    else:
        bill_type = "internal_customer_bill"
    if bill_type not in BILL_TYPES:
        raise HTTPException(status_code=400, detail=f"unsupported bill_type: {bill_type}")
    return bill_type


def infer_target(bill_type: str, channel_id: int | None, metadata: dict[str, Any] | None = None) -> tuple[str, str | None]:
    metadata = metadata or {}
    target_type = str(metadata.get("target_type") or "").strip()
    target_id = metadata.get("target_id")
    if target_type:
        return target_type, str(target_id) if target_id is not None and str(target_id) != "" else None
    user_id = metadata.get("user_id")
    if bill_type == "customer_invoice":
        return "customer", str(user_id) if user_id is not None and str(user_id) != "" else "all"
    if bill_type == "channel_cost_bill":
        return "channel", str(channel_id) if channel_id is not None else "all"
    return "all", None


def job_run_timeout_seconds() -> int:
    return env_int("WORKBENCH_JOB_RUN_TIMEOUT_SECONDS", 60 * 60, minimum=1, maximum=24 * 60 * 60)


def billing_job_run_timeout_seconds() -> int:
    if os.getenv("WORKBENCH_BILLING_JOB_RUN_TIMEOUT_SECONDS") is not None:
        return env_int("WORKBENCH_BILLING_JOB_RUN_TIMEOUT_SECONDS", 6 * 60 * 60, minimum=60, maximum=24 * 60 * 60)
    if os.getenv("WORKBENCH_JOB_RUN_TIMEOUT_SECONDS") is not None:
        return env_int("WORKBENCH_JOB_RUN_TIMEOUT_SECONDS", 6 * 60 * 60, minimum=60, maximum=24 * 60 * 60)
    return 6 * 60 * 60


def agent_job_run_timeout_seconds() -> int:
    if os.getenv("WORKBENCH_AGENT_JOB_RUN_TIMEOUT_SECONDS") is not None:
        return env_int("WORKBENCH_AGENT_JOB_RUN_TIMEOUT_SECONDS", 60 * 60, minimum=60, maximum=24 * 60 * 60)
    return job_run_timeout_seconds()


def job_concurrency_family(job_type: str) -> str:
    normalized = (job_type or "").lower()
    if normalized == "billing_run":
        return "billing_run"
    return "agent_work"


def job_concurrency_guard(job_type: str) -> dict[str, Any]:
    family = job_concurrency_family(job_type)
    if family == "billing_run":
        env_names = ("WORKBENCH_JOB_CONCURRENCY_BILLING_RUN",)
        label = "账单生成任务"
    else:
        env_names = ("WORKBENCH_JOB_CONCURRENCY_AGENT_WORK", "WORKBENCH_JOB_CONCURRENCY_AGENT")
        label = "Agent 或对账任务"

    limit = JOB_CONCURRENCY_DEFAULTS[family]
    for env_name in env_names:
        if os.getenv(env_name) is not None:
            limit = env_int(env_name, limit)
            break
    return {"family": family, "label": label, "limit": limit}


def try_advisory_run_lock(cur, name: str, slot: int = 0) -> bool:
    acquired = fetch_scalar(
        cur,
        "SELECT pg_try_advisory_xact_lock(hashtext(%s), %s::int) AS acquired",
        (f"agent-workbench:job-run:{name}", slot),
    )
    return bool(acquired)


def acquire_guard_slot(cur, family: str, limit: int) -> int | None:
    for slot in range(limit):
        if try_advisory_run_lock(cur, f"family:{family}", slot):
            return slot
    return None


def running_jobs_count_for_family(cur, family: str) -> int:
    """Count RUNNING jobs for a concurrency family (survives background-thread commit)."""
    if family == "billing_run":
        sql = "SELECT COUNT(*) FROM jobs WHERE type = 'billing_run' AND status = 'RUNNING'"
        args: tuple[Any, ...] = ()
    else:
        sql = "SELECT COUNT(*) FROM jobs WHERE type <> 'billing_run' AND status = 'RUNNING'"
        args = ()
    return int(fetch_scalar(cur, sql, args) or 0)


def expire_stale_running_jobs(cur) -> None:
    def expire_family(type_predicate: str, timeout_seconds: int, label: str) -> None:
        message = f"{label} exceeded the {timeout_seconds}s run timeout and was released for retry."
        cur.execute(
            f"""
        WITH expired AS (
            UPDATE jobs
            SET status = 'FAILED',
                finished_at = NOW(),
                error_message = %s
            WHERE status = 'RUNNING'
              AND {type_predicate}
              AND started_at IS NOT NULL
              AND started_at < NOW() - (%s::int * INTERVAL '1 second')
            RETURNING id, billing_run_id
        )
        UPDATE billing_runs AS br
        SET status = 'FAILED',
            finished_at = NOW(),
            summary = COALESCE(br.summary, '{{}}'::jsonb) || jsonb_build_object('status', 'failed', 'reason', %s)
        FROM expired
        WHERE br.id = expired.billing_run_id
          AND br.status = 'RUNNING'
        """,
            (message, timeout_seconds, message),
        )

    expire_family("type = 'billing_run'", billing_job_run_timeout_seconds(), "Billing job")
    expire_family("type <> 'billing_run'", agent_job_run_timeout_seconds(), "Agent job")


def recover_interrupted_running_jobs(cur, family: str | None = None, worker_started_at: datetime | None = None) -> list[dict[str, Any]]:
    """Requeue RUNNING jobs that predate this worker process.

    A container restart kills the in-process billing thread/subprocess but leaves the
    committed RUNNING row behind. The normal timeout can be hours for real Athena
    billing, so a fresh worker needs to recover rows that clearly belonged to a
    previous process before they block the whole billing queue.
    """
    grace_seconds = env_int("WORKBENCH_RECOVER_RUNNING_GRACE_SECONDS", 30, minimum=0, maximum=3600)
    cutoff = (worker_started_at or utc_now()) - timedelta(seconds=grace_seconds)
    family_clause = ""
    if family:
        normalized = family.strip()
        if normalized == "billing_run":
            family_clause = " AND type = 'billing_run'"
        elif normalized == "agent_work":
            family_clause = " AND type <> 'billing_run'"
    cur.execute(
        f"""
        SELECT id, type, billing_run_id, started_at
        FROM jobs
        WHERE status = 'RUNNING'
          AND started_at IS NOT NULL
          AND started_at < %s
          {family_clause}
        ORDER BY started_at ASC
        FOR UPDATE
        """,
        (cutoff,),
    )
    rows = [dict(row) for row in cur.fetchall()]
    if not rows:
        return []

    message = "Recovered after worker restart: previous RUNNING process is no longer attached to this worker."
    job_ids = [row["id"] for row in rows]
    run_ids = [row["billing_run_id"] for row in rows if row.get("billing_run_id")]
    cur.execute(
        """
        UPDATE jobs
        SET status = 'QUEUED',
            started_at = NULL,
            finished_at = NULL,
            error_message = NULL,
            result = COALESCE(result, '{}'::jsonb) || jsonb_build_object('recovered_at', NOW(), 'recovered_reason', %s)
        WHERE id = ANY(%s)
        """,
        (message, job_ids),
    )
    if run_ids:
        cur.execute(
            """
            UPDATE billing_runs
            SET status = 'QUEUED',
                started_at = NULL,
                finished_at = NULL,
                summary = COALESCE(summary, '{}'::jsonb) || jsonb_build_object('recovered_at', NOW(), 'recovered_reason', %s)
            WHERE id = ANY(%s)
              AND status = 'RUNNING'
            """,
            (message, run_ids),
        )
    return rows


def insert_agent_event(
    cur,
    session_id: str,
    event_type: str,
    role: str | None,
    content: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_id = new_id("ae")
    cur.execute(
        """
        INSERT INTO agent_events (
            id, session_id, event_type, role, content, payload
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (event_id, session_id, event_type, role, content, psycopg2.extras.Json(payload or {})),
    )
    return dict(cur.fetchone())


def ensure_agent_session(cur, session_id: str) -> dict[str, Any]:
    session = fetch_one(cur, "SELECT * FROM agent_sessions WHERE id = %s", (session_id,))
    if not session:
        raise HTTPException(status_code=404, detail="agent session not found")
    return session
