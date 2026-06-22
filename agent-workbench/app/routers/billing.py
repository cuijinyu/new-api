"""账单相关路由：定时计划、schedule runs、bill documents、KPI 预览、下载、折扣。"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import timedelta
from typing import Any

import psycopg2.extras
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.artifacts import artifacts, billing_artifacts, content_disposition, stream_download_response
from ..services.billing import (
    build_athena_bill_command,
    build_bill_document_rerun_payload,
    collect_bill_document_reference_artifacts,
    infer_target,
    insert_file_index,
    normalize_bill_type,
    period_bounds_for_month,
    previous_month_label,
    run_kpi_preview,
    structured_billing_prefix,
)
from ..services.config import (
    collapse_to_single_active,
    get_config_by_version,
    get_latest_config,
    insert_config_version,
    load_seed_config,
    update_active_discounts,
    update_active_pricing,
)
from ..services.discounts import apply_discount_rows, flatten_discounts
from ..services.pricing import apply_pricing_rows, flatten_pricing
from ..services.core import (
    db_conn,
    dumps_json,
    fetch_all,
    fetch_one,
    int_or_none,
    json_safe,
    new_id,
    utc_now,
    utc_now_iso,
)
from ..services.jobs import create_bill_document_record

router = APIRouter(tags=["billing"])


class KpiPreviewRequest(BaseModel):
    month: str
    channel_id: int | None = None
    user_id: int | None = None
    config_version: str | None = None
    no_cache: bool = False


class DiscountRow(BaseModel):
    channel_id: str | int | None = None
    channel_name: str | None = None
    user_id: str | int | None = None
    user_name: str | None = None
    model: str = "*"
    discount: float = 1.0


class UpdateDiscountsRequest(BaseModel):
    cost_rows: list[DiscountRow] = Field(default_factory=list)
    revenue_rows: list[DiscountRow] = Field(default_factory=list)
    created_by: str = "ops"


class PricingRow(BaseModel):
    model: str = ""
    type: str = "flat"
    flat_tier: bool | str | None = False
    tier_index: int | str | None = None
    min_k: float | str | None = None
    max_k: float | str | None = None
    ip: float | str | None = None
    op: float | str | None = None
    chp: float | str | None = None
    cwp: float | str | None = None
    cwp_1h: float | str | None = None
    op_text: float | str | None = None
    op_image: float | str | None = None
    note: str | None = None


class UpdatePricingRequest(BaseModel):
    rows: list[PricingRow] = Field(default_factory=list)
    created_by: str = "ops"


def _resolve_config(cur, version: str | None) -> dict[str, Any]:
    """Resolve a pricing-plan config row, auto-bootstrapping if none exists.

    Avoids the 409 dead-end: a missing/unknown version falls back to the
    current active plan, and an empty system is seeded with ``local-v0``.
    """
    row = get_config_by_version(cur, version) if version else None
    if row is None:
        try:
            row = get_latest_config(cur)
        except HTTPException:
            pricing, discounts, _ = load_seed_config(None)
            row = insert_config_version(cur, "local-v0", pricing, discounts, "auto-bootstrap", None)
    if not row:
        raise HTTPException(status_code=409, detail="no active pricing plan found")
    return row


@router.post("/api/billing/kpi-preview")
def kpi_preview(req: KpiPreviewRequest) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            config = _resolve_config(cur, req.config_version)
            return run_kpi_preview(
                config,
                req.month,
                channel_id=req.channel_id,
                user_id=req.user_id,
                no_cache=req.no_cache,
            )


@router.get("/api/billing/download")
def download_billing_file(
    file_id: str | None = Query(default=None, alias="file_id"),
    uri: str | None = Query(default=None),
):
    target_uri = uri
    filename = "download"
    if file_id:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                row = fetch_one(cur, "SELECT * FROM uploaded_files WHERE id = %s", (file_id,))
                if not row:
                    raise HTTPException(status_code=404, detail="file not found")
                target_uri = str(row.get("s3_uri") or "")
                filename = str(row.get("filename") or filename)
    if not target_uri:
        raise HTTPException(status_code=400, detail="file_id or uri is required")
    # 账单产物在专用账单桶，技术记录在主桶：按 URI 所属桶选择正确的 store/凭证。
    store = artifacts
    if billing_artifacts is not artifacts and target_uri.startswith(f"s3://{billing_artifacts.bucket}/"):
        store = billing_artifacts
    if not filename or filename == "download":
        filename = store.download_filename(target_uri, filename)
    # 浏览器下载统一走 API 流式响应，避免 302 跳到 Docker 内网 minio:9000 导致整页跳转。
    return stream_download_response(store, target_uri, filename)


@router.get("/api/billing/discounts")
def get_discounts(version: str | None = None) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            config = _resolve_config(cur, version)
            flat = flatten_discounts(config.get("discounts_snapshot"))
            return {
                "version": {
                    "id": config["id"],
                    "version": config["version"],
                    "status": config.get("status"),
                    "activated_at": config.get("activated_at"),
                },
                **flat,
            }


@router.get("/api/billing/pricing")
def get_pricing(version: str | None = None) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            config = _resolve_config(cur, version)
            flat = flatten_pricing(config.get("pricing_snapshot"))
            return {
                "version": {
                    "id": config["id"],
                    "version": config["version"],
                    "status": config.get("status"),
                    "activated_at": config.get("activated_at"),
                },
                **flat,
            }


@router.put("/api/billing/pricing")
def update_pricing(req: UpdatePricingRequest) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            base = _resolve_config(cur, None)
            try:
                new_pricing = apply_pricing_rows(
                    base.get("pricing_snapshot"),
                    [row.model_dump() for row in req.rows],
                )
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"invalid pricing rows: {exc}") from exc
    updated = update_active_pricing(new_pricing, req.created_by)
    flat = flatten_pricing(updated.get("pricing_snapshot"))
    return {
        "version": {
            "id": updated["id"],
            "version": updated["version"],
            "status": updated.get("status"),
            "activated_at": updated.get("activated_at"),
        },
        **flat,
    }


@router.put("/api/billing/discounts")
def update_discounts(req: UpdateDiscountsRequest) -> dict[str, Any]:
    # 折扣全局化：原地覆盖当前生效配置的折扣，保存即生效，不再生成新版本。
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            base = _resolve_config(cur, None)
            new_discounts = apply_discount_rows(
                base.get("discounts_snapshot"),
                [row.model_dump() for row in req.cost_rows],
                [row.model_dump() for row in req.revenue_rows],
            )
    updated = update_active_discounts(new_discounts, req.created_by)
    flat = flatten_discounts(updated.get("discounts_snapshot"))
    return {
        "version": {
            "id": updated["id"],
            "version": updated["version"],
            "status": updated.get("status"),
            "activated_at": updated.get("activated_at"),
        },
        **flat,
    }


@router.post("/api/config/collapse")
def collapse_config_versions() -> dict[str, Any]:
    """一次性收敛历史多条生效配置为唯一生效（清理 local-v0..vN 的重复 active）。"""
    return collapse_to_single_active()


@router.post("/api/billing/discounts/reseed")
def reseed_discounts(created_by: str = "seed-import") -> dict[str, Any]:
    """从 scripts/athena/discounts.json 重新导入折扣，整体覆盖当前生效配置的折扣。

    用于把仓库里的原始折扣口径同步进 workbench（首次启用或被误覆盖后恢复）。
    """
    _, seed_discounts, source = load_seed_config(None)
    updated = update_active_discounts(seed_discounts, created_by)
    flat = flatten_discounts(updated.get("discounts_snapshot"))
    return {
        "source": source.get("discounts"),
        "version": {
            "id": updated["id"],
            "version": updated["version"],
            "status": updated.get("status"),
            "activated_at": updated.get("activated_at"),
        },
        **flat,
    }


@router.post("/api/billing/pricing/reseed")
def reseed_pricing(created_by: str = "seed-import") -> dict[str, Any]:
    seed_pricing, _, source = load_seed_config(None)
    updated = update_active_pricing(seed_pricing, created_by)
    flat = flatten_pricing(updated.get("pricing_snapshot"))
    return {
        "source": source.get("pricing"),
        "version": {
            "id": updated["id"],
            "version": updated["version"],
            "status": updated.get("status"),
            "activated_at": updated.get("activated_at"),
        },
        **flat,
    }


class ScheduleRequest(BaseModel):
    name: str
    schedule_type: str
    cron_expr: str
    timezone: str = "Asia/Hong_Kong"
    enabled: bool = True
    payload: dict[str, Any] = Field(default_factory=dict)
    created_by: str = "user"


class ScheduleRunRequest(BaseModel):
    period: str | None = None
    config_version: str | None = None
    force: bool = False
    created_by: str = "user"
    payload: dict[str, Any] = Field(default_factory=dict)


class BillDocumentAction(BaseModel):
    actor: str = "ops"
    comment: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BillDocumentReferenceRequest(BaseModel):
    referenced_by: str = "ops"
    metadata: dict[str, Any] = Field(default_factory=dict)


class BillDocumentRerunRequest(BaseModel):
    actor: str = "ops"
    comment: str | None = None
    no_cache: bool = True
    run_immediately: bool = True
    config_version_id: str | None = None


def build_schedule_run_period(schedule: dict[str, Any], req: ScheduleRunRequest) -> str:
    if req.period:
        return req.period
    schedule_type = str(schedule.get("schedule_type") or "")
    if schedule_type == "daily_channel_cost_snapshot":
        return (utc_now() - timedelta(days=1)).date().isoformat()
    return previous_month_label()


def schedule_bill_types(schedule: dict[str, Any]) -> list[str]:
    payload = schedule.get("payload") if isinstance(schedule.get("payload"), dict) else {}
    raw_types = payload.get("bill_types")
    if isinstance(raw_types, list):
        types = [str(item) for item in raw_types]
    else:
        types = [str(payload.get("bill_type") or schedule.get("schedule_type") or "internal_customer_bill")]
    return [normalize_bill_type(item, payload) for item in types]


def create_manifest_artifact(prefix: str, manifest: dict[str, Any]) -> str:
    return artifacts.put_json(f"{prefix}/manifest.json", manifest)


def create_scheduled_billing_job(
    cur, *, schedule: dict[str, Any], schedule_run_id: str, batch_id: str,
    fact_id: str, period: str, month: str, bill_type: str, target_type: str,
    target_id: str | None, config: dict[str, Any], payload: dict[str, Any], created_by: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    job_id = new_id("job")
    run_id = new_id("run")
    job_prefix = f"jobs/{utc_now().date().isoformat()}/{job_id}"
    channel_id = int_or_none(payload.get("channel_id"))
    if bill_type == "channel_cost_bill" and target_type == "channel" and target_id not in (None, "all"):
        channel_id = int_or_none(target_id)
    billing_prefix = structured_billing_prefix(bill_type, month, target_type, target_id, run_id)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    schedule_type = str(schedule.get("schedule_type") or "")
    snapshot_date = period if schedule_type == "daily_channel_cost_snapshot" else None
    job_payload = {
        **payload, "bill_type": bill_type, "target_type": target_type, "target_id": target_id,
        "period": period, "month": month, "config_version": config["version"],
        "schedule_id": schedule["id"], "schedule_run_id": schedule_run_id,
        "batch_id": batch_id, "fact_manifest_id": fact_id,
        "metadata": {
            **metadata, "bill_type": bill_type, "target_type": target_type, "target_id": target_id,
            "period": period, "snapshot_date": snapshot_date, "schedule_id": schedule["id"],
            "schedule_run_id": schedule_run_id, "batch_id": batch_id, "fact_manifest_id": fact_id,
            "customer_view": bool(metadata.get("customer_view")) or bill_type == "customer_invoice",
            "split_customers": metadata.get("split_customers", payload.get("split_customers")),
            "split_channels": metadata.get("split_channels", payload.get("split_channels")),
            "split_internal_customers": metadata.get("split_internal_customers", payload.get("split_internal_customers")),
            "detail": bool(metadata.get("detail") or payload.get("detail")),
        },
    }
    vendor = payload.get("vendor")
    cur.execute(
        """
        INSERT INTO jobs (
            id, type, status, created_by, month, channel_id, vendor,
            bill_type, target_type, target_id,
            s3_prefix, billing_run_id, request_payload
        )
        VALUES (%s, 'billing_run', 'QUEUED', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (job_id, created_by, month, channel_id, vendor, bill_type, target_type, target_id,
         artifacts.uri_for_prefix(job_prefix), run_id, psycopg2.extras.Json(job_payload)),
    )
    job = dict(cur.fetchone())
    cur.execute(
        """
        INSERT INTO billing_runs (
            id, job_id, month, channel_id, vendor, bill_type, target_type, target_id,
            config_version_id, status, s3_prefix
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'QUEUED', %s)
        RETURNING *
        """,
        (run_id, job_id, month, channel_id, vendor, bill_type, target_type, target_id, config["id"], billing_artifacts.uri_for_prefix(billing_prefix)),
    )
    run = dict(cur.fetchone())
    from ..services.jobs import bill_document_idempotency
    command = build_athena_bill_command(job, run, config, billing_prefix)
    doc_summary = {
        "bill_type": bill_type, "target_type": target_type, "target_id": target_id,
        "job_id": job_id, "billing_run_id": run_id, "fact_manifest_id": fact_id,
        "schedule_id": schedule["id"], "schedule_run_id": schedule_run_id,
        "period": period, "snapshot_date": snapshot_date,
        "requires_execution": True, "real_execution_required": True,
    }
    from ..services.billing import bill_document_idempotency as bdi
    document = create_bill_document_record(
        cur, batch_id=batch_id, schedule_run_id=schedule_run_id, month=month,
        bill_type=bill_type, target_type=target_type, target_id=target_id,
        status="CREATED", s3_uri=None,
        idempotency_key=bdi(job, run, config, command), summary=doc_summary,
    )
    return job, run, document


def trigger_schedule_run(cur, schedule: dict[str, Any], req: ScheduleRunRequest) -> dict[str, Any]:
    period = build_schedule_run_period(schedule, req)
    payload = schedule.get("payload") if isinstance(schedule.get("payload"), dict) else {}
    merged_payload = {**payload, **req.payload}
    # 定时出账默认使用当前生效配置（全局折扣），不再 pin 到可能为空的 local-v0。
    config_ref = req.config_version or (str(merged_payload["config_version"]) if merged_payload.get("config_version") else None)
    if config_ref:
        config = get_config_by_version(cur, config_ref)
        if not config:
            raise HTTPException(status_code=409, detail=f"config version {config_ref} not found; run /api/config/bootstrap first")
    else:
        config = get_latest_config(cur)
    config_id = config["id"]
    period_start, period_end = period_bounds_for_month(period if len(period) == 7 else period[:7])
    run_hash_payload = {"schedule_id": schedule["id"], "period": period, "config_version_id": config_id, "payload": merged_payload}
    idempotency_key = hashlib.sha256(dumps_json(run_hash_payload).encode("utf-8")).hexdigest()
    if req.force:
        idempotency_key = f"{idempotency_key}:{uuid.uuid4().hex[:8]}"

    existing = fetch_one(cur, "SELECT * FROM schedule_runs WHERE idempotency_key = %s", (idempotency_key,))
    if existing:
        batch = fetch_one(cur, "SELECT * FROM billing_batches WHERE schedule_run_id = %s", (existing["id"],))
        documents = fetch_all(cur, "SELECT * FROM bill_documents WHERE schedule_run_id = %s ORDER BY created_at ASC", (existing["id"],))
        return {"schedule_run": existing, "batch": batch, "documents": documents, "reused": True}

    schedule_run_id = new_id("schrun")
    batch_id = new_id("batch")
    fact_id = new_id("fact")
    cur.execute(
        """
        INSERT INTO schedule_runs (
            id, schedule_id, status, period, period_start, period_end,
            idempotency_key, config_version_id, started_at
        )
        VALUES (%s, %s, 'RUNNING', %s, %s, %s, %s, %s, NOW())
        RETURNING *
        """,
        (schedule_run_id, schedule["id"], period, period_start, period_end, idempotency_key, config_id),
    )
    schedule_run = dict(cur.fetchone())
    cur.execute(
        """
        INSERT INTO billing_batches (
            id, schedule_run_id, month, status, config_version_id, started_at
        )
        VALUES (%s, %s, %s, 'MATERIALIZING_FACTS', %s, NOW())
        RETURNING *
        """,
        (batch_id, schedule_run_id, period if len(period) == 7 else period[:7], config_id),
    )
    batch = dict(cur.fetchone())

    fact_prefix = f"billing-facts/{batch['month']}/{batch_id}"
    fact_manifest = {
        "batch_id": batch_id, "schedule_run_id": schedule_run_id, "month": batch["month"],
        "config_version_id": config_id, "mode": "pending-athena-worker",
        "note": "Scheduler created the batch and billing jobs; Athena/billing workers must execute the real bill generation before any document is reviewable.",
        "generated_at": utc_now_iso(),
    }
    fact_uri = create_manifest_artifact(fact_prefix, fact_manifest)
    cur.execute(
        """
        INSERT INTO billing_fact_manifests (
            id, batch_id, month, status, config_version_id, s3_uri, manifest
        )
        VALUES (%s, %s, %s, 'CREATED', %s, %s, %s)
        RETURNING *
        """,
        (fact_id, batch_id, batch["month"], config_id, fact_uri, psycopg2.extras.Json(fact_manifest)),
    )
    fact = dict(cur.fetchone())
    cur.execute("UPDATE billing_batches SET fact_manifest_id = %s, status = 'RENDERING' WHERE id = %s", (fact_id, batch_id))

    default_target_type = "channel" if str(schedule.get("schedule_type") or "") == "daily_channel_cost_snapshot" else "all"
    target_type = str(merged_payload.get("target_type") or default_target_type)
    target_id = str(merged_payload.get("target_id")) if merged_payload.get("target_id") is not None else None
    documents = []
    jobs = []
    for bill_type in schedule_bill_types(schedule):
        job, run, document = create_scheduled_billing_job(
            cur, schedule=schedule, schedule_run_id=schedule_run_id, batch_id=batch_id,
            fact_id=fact_id, period=period, month=batch["month"], bill_type=bill_type,
            target_type=target_type, target_id=target_id, config=config,
            payload=merged_payload, created_by=req.created_by,
        )
        jobs.append({"job_id": job["id"], "billing_run_id": run["id"], "bill_type": bill_type})
        documents.append(document)

    summary = {"documents": len(documents), "jobs_created": len(jobs), "jobs": jobs, "fact_manifest_id": fact_id, "batch_id": batch_id}
    cur.execute("UPDATE schedule_runs SET status = 'RUNNING', summary = %s WHERE id = %s", (psycopg2.extras.Json(summary), schedule_run_id))
    cur.execute("UPDATE billing_batches SET status = 'RENDERING', summary = %s WHERE id = %s", (psycopg2.extras.Json(summary), batch_id))
    schedule_run["status"] = "RUNNING"
    schedule_run["summary"] = summary
    batch["status"] = "RENDERING"
    batch["summary"] = summary
    return {"schedule_run": schedule_run, "batch": batch, "fact_manifest": fact, "documents": documents, "jobs": jobs, "reused": False}


def insert_publish_record(cur, document_id: str, action: str, req: BillDocumentAction) -> None:
    cur.execute(
        """
        INSERT INTO bill_publish_records (id, bill_document_id, action, actor, comment, metadata)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (new_id("pub"), document_id, action, req.actor, req.comment, psycopg2.extras.Json(req.metadata)),
    )


# --- Schedules ---

@router.get("/api/schedules")
def list_schedules() -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rows = fetch_all(cur, "SELECT * FROM schedules ORDER BY created_at ASC")
    return {"items": rows}


@router.post("/api/schedules")
def create_schedule(req: ScheduleRequest) -> dict[str, Any]:
    schedule_id = new_id("sch")
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO schedules (id, name, schedule_type, cron_expr, timezone, enabled, payload, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (schedule_id, req.name, req.schedule_type, req.cron_expr, req.timezone, req.enabled, psycopg2.extras.Json(req.payload), req.created_by),
            )
            row = dict(cur.fetchone())
    return {"schedule": row}


@router.post("/api/schedules/{schedule_id}/run")
def run_schedule(schedule_id: str, req: ScheduleRunRequest | None = None) -> dict[str, Any]:
    req = req or ScheduleRunRequest()
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            schedule = fetch_one(cur, "SELECT * FROM schedules WHERE id = %s", (schedule_id,))
            if not schedule:
                raise HTTPException(status_code=404, detail="schedule not found")
            result = trigger_schedule_run(cur, schedule, req)
            cur.execute("UPDATE schedules SET last_run_at = NOW(), updated_at = NOW() WHERE id = %s", (schedule_id,))
    return result


@router.get("/api/schedule-runs")
def list_schedule_runs() -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rows = fetch_all(cur, """
                SELECT sr.*, s.name AS schedule_name, s.schedule_type
                FROM schedule_runs sr
                LEFT JOIN schedules s ON s.id = sr.schedule_id
                ORDER BY sr.created_at DESC
                LIMIT 100
            """)
    return {"items": rows}


@router.post("/api/schedule-runs/{schedule_run_id}/retry-failed")
def retry_failed_schedule_run(schedule_run_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            failed = fetch_all(cur, "SELECT * FROM bill_documents WHERE schedule_run_id = %s AND status IN ('FAILED', 'PARTIAL_FAILED')", (schedule_run_id,))
            job_ids = [row["job_id"] for row in failed if row.get("job_id")]
            run_ids = [row["billing_run_id"] for row in failed if row.get("billing_run_id")]
            if job_ids:
                cur.execute("UPDATE jobs SET status = 'QUEUED', started_at = NULL, finished_at = NULL, error_message = NULL WHERE id = ANY(%s)", (job_ids,))
            if run_ids:
                cur.execute("UPDATE billing_runs SET status = 'QUEUED', started_at = NULL, finished_at = NULL WHERE id = ANY(%s)", (run_ids,))
            cur.execute(
                """
                UPDATE bill_documents
                SET status = 'CREATED', s3_uri = NULL, updated_at = NOW(),
                    summary = COALESCE(summary, '{}'::jsonb) || jsonb_build_object('retried_at', NOW(), 'retry_job_status', 'QUEUED')
                WHERE schedule_run_id = %s AND status IN ('FAILED', 'PARTIAL_FAILED')
                RETURNING *
                """,
                (schedule_run_id,),
            )
            rows = [dict(row) for row in cur.fetchall()]
    return {"status": "retry_scheduled", "items": rows, "count": len(rows)}


# --- Billing batches ---

@router.get("/api/billing-batches")
def list_billing_batches() -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rows = fetch_all(cur, "SELECT * FROM billing_batches ORDER BY created_at DESC LIMIT 100")
    return {"items": rows}


@router.get("/api/billing-batches/{batch_id}")
def get_billing_batch(batch_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            batch = fetch_one(cur, "SELECT * FROM billing_batches WHERE id = %s", (batch_id,))
            if not batch:
                raise HTTPException(status_code=404, detail="batch not found")
            facts = fetch_all(cur, "SELECT * FROM billing_fact_manifests WHERE batch_id = %s ORDER BY created_at DESC", (batch_id,))
            documents = fetch_all(cur, "SELECT * FROM bill_documents WHERE batch_id = %s ORDER BY created_at ASC", (batch_id,))
    return {"batch": batch, "fact_manifests": facts, "documents": documents}


# --- Bill documents ---

@router.get("/api/bill-documents")
def list_bill_documents(month: str | None = None, bill_type: str | None = None, status: str | None = None) -> dict[str, Any]:
    clauses = []
    args: list[Any] = []
    if month:
        clauses.append("month = %s")
        args.append(month)
    if bill_type:
        clauses.append("bill_type = %s")
        args.append(bill_type)
    if status:
        clauses.append("status = %s")
        args.append(status)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rows = fetch_all(cur, f"SELECT * FROM bill_documents {where} ORDER BY created_at DESC LIMIT 200", tuple(args))
    return {"items": rows}


@router.post("/api/bill-documents/{document_id}/reference-files")
def prepare_bill_document_reference_files(document_id: str, req: BillDocumentReferenceRequest) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            document = fetch_one(cur, "SELECT * FROM bill_documents WHERE id = %s", (document_id,))
            if not document:
                raise HTTPException(status_code=404, detail="bill document not found")
            artifact_entries = collect_bill_document_reference_artifacts(document)
            if not artifact_entries:
                raise HTTPException(status_code=409, detail="bill document has no referenceable artifacts")
            base_metadata = {
                "source": "bill_library",
                "bill_document_id": document["id"],
                "billing_run_id": document.get("billing_run_id"),
                "bill_type": document.get("bill_type"),
                "target_type": document.get("target_type"),
                "target_id": document.get("target_id"),
                "month": document.get("month"),
            }
            files = [
                insert_file_index(
                    cur,
                    filename=entry["filename"],
                    s3_uri=entry["s3_uri"],
                    category="billing-result",
                    job_id=document.get("job_id"),
                    uploaded_by=req.referenced_by,
                    content_type=entry["content_type"],
                    metadata={**base_metadata, **entry["metadata"], **req.metadata},
                )
                for entry in artifact_entries
            ]
    return {"status": "ready", "bill_document": document, "files": files}


@router.post("/api/bill-documents/{document_id}/rerun")
def rerun_bill_document(document_id: str, req: BillDocumentRerunRequest | None = None) -> dict[str, Any]:
    from .jobs import BillingRunRequest, _create_billing_run
    from ..services.jobs import guarded_run_job

    req = req or BillDocumentRerunRequest()
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            document = fetch_one(cur, "SELECT * FROM bill_documents WHERE id = %s", (document_id,))
            if not document:
                raise HTTPException(status_code=404, detail="bill document not found")
            source_job = (
                fetch_one(cur, "SELECT * FROM jobs WHERE id = %s", (document["job_id"],))
                if document.get("job_id")
                else None
            )
            source_run = (
                fetch_one(cur, "SELECT * FROM billing_runs WHERE id = %s", (document["billing_run_id"],))
                if document.get("billing_run_id")
                else None
            )
            payload = build_bill_document_rerun_payload(
                document,
                source_job=source_job,
                source_run=source_run,
                actor=req.actor,
                comment=req.comment,
                no_cache=req.no_cache,
                config_version_id=req.config_version_id,
            )

    created = _create_billing_run(BillingRunRequest(**payload))
    response: dict[str, Any] = {
        "status": "rerun_created",
        "source_bill_document": document,
        **created,
    }
    if req.run_immediately:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                run_result = guarded_run_job(cur, str(created["job_id"]))
        response["status"] = "rerun_started"
        response["run"] = run_result
    return response


@router.post("/api/bill-documents/{document_id}/approve")
def approve_bill_document(document_id: str, req: BillDocumentAction) -> dict[str, Any]:
    return publish_bill_document(document_id, req)


@router.post("/api/bill-documents/{document_id}/publish")
def publish_bill_document(document_id: str, req: BillDocumentAction) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            document = fetch_one(cur, "SELECT * FROM bill_documents WHERE id = %s FOR UPDATE", (document_id,))
            if not document:
                raise HTTPException(status_code=404, detail="bill document not found")
            cur.execute("UPDATE bill_documents SET status = 'DELIVERED', published_by = %s, published_at = NOW(), updated_at = NOW() WHERE id = %s RETURNING *", (req.actor, document_id))
            updated = dict(cur.fetchone())
            insert_publish_record(cur, document_id, "publish", req)
    return {"bill_document": updated}
