"""任务管理路由：创建任务、运行、队列。"""

from __future__ import annotations

from typing import Any

import psycopg2.extras
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.artifacts import artifacts, billing_artifacts
from ..services.billing import infer_target, normalize_bill_type, structured_billing_prefix
from ..services.config import ensure_config_version, get_config_by_version, get_latest_config
from ..services.core import (
    db_conn,
    env_int,
    expire_stale_running_jobs,
    fetch_all,
    fetch_one,
    job_concurrency_family,
    new_id,
    uri_to_prefix,
    utc_now,
)
from ..services.jobs import (
    enqueue_agent_job,
    guarded_run_job,
    job_queue_snapshot,
    run_next_queued_job_once,
    run_queued_jobs,
)

router = APIRouter(tags=["jobs"])


class BillingRunRequest(BaseModel):
    month: str
    channel_id: int | None = None
    vendor: str | None = None
    bill_type: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    config_version: str = "local-v0"
    config_version_id: str | None = None
    created_by: str = "user"
    metadata: dict[str, Any] = Field(default_factory=dict)


class InvestigationJobRequest(BaseModel):
    month: str
    billing_run_id: str | None = None
    channel_id: int | None = None
    vendor: str = "1001AI"
    reason: str = "supplier_diff_over_threshold"
    created_by: str = "agent-workbench"
    metadata: dict[str, Any] = Field(default_factory=dict)


def _create_billing_run(req: BillingRunRequest) -> dict[str, Any]:
    # 折扣全局化：默认用当前生效配置，不再 pin 到固定的 local-v0。
    # 仅当显式提供 config_version_id 时才使用指定版本。
    config_ref = req.config_version_id
    if not config_ref:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                try:
                    config_ref = get_latest_config(cur)["version"]
                except HTTPException:
                    config_ref = req.config_version
    ensure_config_version(config_ref)
    job_id = new_id("job")
    run_id = new_id("run")
    job_prefix = f"jobs/{utc_now().date().isoformat()}/{job_id}"
    payload = req.model_dump()
    metadata = req.metadata if isinstance(req.metadata, dict) else {}
    bill_type = normalize_bill_type(req.bill_type, metadata, req.channel_id)
    target_type, target_id = infer_target(bill_type, req.channel_id, {**metadata, "target_type": req.target_type or metadata.get("target_type"), "target_id": req.target_id or metadata.get("target_id")})
    billing_prefix = structured_billing_prefix(bill_type, req.month, target_type, target_id, run_id)
    payload["bill_type"] = bill_type
    payload["target_type"] = target_type
    payload["target_id"] = target_id

    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            config = get_config_by_version(cur, config_ref)
            cur.execute(
                """
                INSERT INTO jobs (
                    id, type, status, created_by, month, channel_id, vendor,
                    bill_type, target_type, target_id,
                    s3_prefix, billing_run_id, request_payload
                )
                VALUES (%s, 'billing_run', 'CREATED', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    job_id, req.created_by, req.month, req.channel_id, req.vendor,
                    bill_type, target_type, target_id,
                    artifacts.uri_for_prefix(job_prefix), run_id,
                    psycopg2.extras.Json(payload),
                ),
            )
            cur.execute(
                """
                INSERT INTO billing_runs (
                    id, job_id, month, channel_id, vendor, bill_type, target_type, target_id, config_version_id,
                    status, s3_prefix
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'CREATED', %s)
                """,
                (run_id, job_id, req.month, req.channel_id, req.vendor, bill_type, target_type, target_id, config["id"], billing_artifacts.uri_for_prefix(billing_prefix)),
            )

    return {"job_id": job_id, "billing_run_id": run_id, "status": "CREATED", "bill_type": bill_type, "target_type": target_type, "target_id": target_id}


@router.post("/api/jobs/billing-run")
def create_billing_run(req: BillingRunRequest) -> dict[str, Any]:
    return _create_billing_run(req)


@router.post("/api/workbench/jobs")
def create_workbench_job(payload: dict[str, Any]) -> dict[str, Any]:
    job_type = payload.get("type") or payload.get("job_type") or "unknown"
    if job_type == "billing_run":
        config_ref = payload.get("config_version") or payload.get("config_version_id") or "local-v0"
        return _create_billing_run(
            BillingRunRequest(
                month=payload["month"], channel_id=payload.get("channel_id"),
                vendor=payload.get("vendor"), bill_type=payload.get("bill_type"),
                target_type=payload.get("target_type"), target_id=payload.get("target_id"),
                config_version=config_ref, created_by=payload.get("created_by", "e2e"), metadata=payload,
            )
        )

    job_id = new_id("job")
    job_prefix = f"jobs/{utc_now().date().isoformat()}/{job_id}"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO jobs (
                    id, type, status, created_by, month, channel_id, vendor,
                    s3_prefix, request_payload
                )
                VALUES (%s, %s, 'QUEUED', %s, %s, %s, %s, %s, %s)
                """,
                (job_id, job_type, payload.get("created_by", "e2e"), payload.get("month"),
                 payload.get("channel_id"), payload.get("vendor"),
                 artifacts.uri_for_prefix(job_prefix), psycopg2.extras.Json(payload)),
            )
    return {"id": job_id, "job_id": job_id, "status": "QUEUED", "type": job_type}


@router.post("/api/jobs/{job_id}/run")
def run_job(job_id: str) -> dict[str, Any]:
    family: str | None = None
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            job_row = fetch_one(cur, "SELECT * FROM jobs WHERE id = %s", (job_id,))
            if not job_row:
                raise HTTPException(status_code=404, detail="job not found")
            family = job_concurrency_family(str(job_row.get("type") or "unknown"))
            if family == "agent_work":
                return enqueue_agent_job(cur, job_row)
            result = guarded_run_job(cur, job_id)
    if str(result.get("status") or "").lower() == "completed" and os.getenv("WORKBENCH_QUEUE_AUTO_DRAIN", "true").lower() != "false":
        drained = run_queued_jobs(family, env_int("WORKBENCH_QUEUE_AUTO_DRAIN_LIMIT", 1, minimum=1, maximum=10))
        if drained:
            result["auto_started"] = drained
    return result


@router.post("/api/workbench/jobs/{job_id}/run")
def run_workbench_job(job_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return run_job(job_id)


@router.get("/api/jobs")
def list_jobs(
    limit: int = Query(500, ge=1, le=1000),
    status: str | None = None,
    type: str | None = None,
) -> dict[str, Any]:
    filters: list[str] = []
    params: list[Any] = []
    if status:
        filters.append("UPPER(status) = UPPER(%s)")
        params.append(status)
    if type:
        filters.append("type = %s")
        params.append(type)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.append(limit)
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rows = fetch_all(cur, f"SELECT * FROM jobs {where} ORDER BY created_at DESC LIMIT %s", tuple(params))
    return {"items": rows}


@router.get("/api/jobs/queue")
def get_job_queue() -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            expire_stale_running_jobs(cur)
            return job_queue_snapshot(cur)


@router.post("/api/jobs/queue/run-next")
def run_next_queued_job(family: str | None = None) -> dict[str, Any]:
    return run_next_queued_job_once(family)


@router.post("/api/jobs/codex-investigation")
def create_codex_investigation(req: InvestigationJobRequest) -> dict[str, Any]:
    job_id = new_id("job")
    job_prefix = f"jobs/{utc_now().date().isoformat()}/{job_id}"
    payload = req.model_dump()
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO jobs (
                    id, type, status, created_by, month, channel_id, vendor,
                    s3_prefix, billing_run_id, request_payload
                )
                VALUES (%s, 'codex_investigation', 'QUEUED', %s, %s, %s, %s, %s, %s, %s)
                """,
                (job_id, req.created_by, req.month, req.channel_id, req.vendor,
                 artifacts.uri_for_prefix(job_prefix), req.billing_run_id,
                 psycopg2.extras.Json(payload)),
            )
    return {"job_id": job_id, "status": "QUEUED"}


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            job = fetch_one(cur, "SELECT * FROM jobs WHERE id = %s", (job_id,))
            if not job:
                raise HTTPException(status_code=404, detail="job not found")
            billing_run = fetch_one(cur, "SELECT * FROM billing_runs WHERE job_id = %s", (job_id,))
            change_requests = fetch_all(cur, "SELECT * FROM config_change_requests WHERE job_id = %s ORDER BY created_at", (job_id,))
    return {"job": job, "billing_run": billing_run, "change_requests": change_requests}


@router.get("/api/workbench/jobs/{job_id}")
def get_workbench_job(job_id: str) -> dict[str, Any]:
    return get_job(job_id)


@router.get("/api/jobs/{job_id}/artifacts")
def get_job_artifacts(job_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            job = fetch_one(cur, "SELECT * FROM jobs WHERE id = %s", (job_id,))
            if not job:
                raise HTTPException(status_code=404, detail="job not found")
            billing_run = fetch_one(cur, "SELECT * FROM billing_runs WHERE job_id = %s", (job_id,))

    prefixes = [uri_to_prefix(job.get("s3_prefix"))]
    if billing_run:
        prefixes.append(uri_to_prefix(billing_run.get("s3_prefix")))
    listed = []
    for prefix in [p for p in prefixes if p]:
        listed.extend(artifacts.list_prefix(prefix))

    return {
        "job_id": job_id,
        "s3_prefix": job.get("s3_prefix"),
        "billing_prefix": billing_run.get("s3_prefix") if billing_run else None,
        "artifacts": job.get("result", {}).get("artifacts", {}),
        "listed": listed,
    }


@router.get("/api/workbench/jobs/{job_id}/artifacts")
def get_workbench_job_artifacts(job_id: str) -> dict[str, Any]:
    return get_job_artifacts(job_id)


import os
