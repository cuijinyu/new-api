"""任务执行与调度逻辑：并发控制、入队、账单执行、Agent 执行。"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any

import psycopg2.extras
from fastapi import HTTPException

from ..runner import execute_agent
from .agent import build_agent_context, ingest_change_request
from .artifacts import artifacts, billing_artifacts
from .billing import (
    athena_worker_manifest,
    bill_document_idempotency,
    bill_document_status_for_type,
    build_athena_bill_command,
    execute_real_athena_bill,
    insert_file_index,
    normalize_kpi_payload,
    resolve_billing_run_status,
    sync_split_bill_documents,
    primary_bill_uri,
    summarize_batch_completion,
)
from .core import (
    STARTABLE_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
    acquire_guard_slot,
    content_type_for_filename,
    db_conn,
    dumps_json,
    env_int,
    expire_stale_running_jobs,
    fetch_all,
    fetch_one,
    filename_from_uri,
    job_concurrency_family,
    job_concurrency_guard,
    json_safe,
    new_id,
    public_job,
    running_jobs_count_for_family,
    try_advisory_run_lock,
    uri_to_prefix,
    utc_now,
    utc_now_iso,
)


def queued_job_response(cur, job: dict[str, Any], guard: dict[str, Any]) -> dict[str, Any]:
    cur.execute(
        "UPDATE jobs SET status = 'QUEUED', started_at = NULL, finished_at = NULL, error_message = NULL WHERE id = %s",
        (job["id"],),
    )
    if job.get("billing_run_id"):
        cur.execute(
            "UPDATE billing_runs SET status = 'QUEUED', started_at = NULL, finished_at = NULL WHERE id = %s",
            (job["billing_run_id"],),
        )
    return {
        "job_id": job["id"],
        "status": "QUEUED",
        "task_family": guard["family"],
        "concurrency_limit": guard["limit"],
        "message": f"已有{guard['label']}正在运行，本任务已进入队列。",
    }


def non_startable_job_response(job: dict[str, Any], status: str) -> dict[str, Any]:
    response: dict[str, Any] = {
        "job_id": job["id"],
        "status": status,
        "message": "任务正在运行，或当前状态不能直接启动。",
    }
    if status in TERMINAL_JOB_STATUSES:
        response["result"] = job.get("result") or {}
        response["message"] = "任务已完成，已返回当前结果。"
    return response


def enqueue_agent_job(cur, job: dict[str, Any]) -> dict[str, Any]:
    status = str(job.get("status") or "").upper()
    if status in TERMINAL_JOB_STATUSES:
        return {"job_id": job["id"], "status": status, "result": job.get("result") or {}, "message": "任务已完成，已返回当前结果。"}
    if status == "RUNNING":
        return {"job_id": job["id"], "status": "RUNNING", "message": "Agent 任务正在运行中。"}
    cur.execute(
        "UPDATE jobs SET status = 'QUEUED', started_at = NULL, finished_at = NULL, error_message = NULL WHERE id = %s",
        (job["id"],),
    )
    return {
        "job_id": job["id"],
        "status": "QUEUED",
        "task_family": "agent_work",
        "message": "Agent 任务已入队，由 agent worker 异步执行，可通过事件流/轮询查看进度。",
    }


def dispatch_job_now(cur, job: dict[str, Any]) -> dict[str, Any]:
    if job["type"] == "billing_run":
        return start_billing_job_background(cur, job)
    return run_agent_job(cur, job)


def _billing_job_worker(job_id: str) -> None:
    try:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                job = fetch_one(cur, "SELECT * FROM jobs WHERE id = %s", (job_id,))
                if not job or str(job.get("status") or "").upper() not in ("RUNNING", "QUEUED", "CREATED"):
                    return
                run_billing_job(cur, job)
            conn.commit()
    except Exception as exc:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                message = f"billing background worker failed: {exc}"[:2000]
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'FAILED', finished_at = NOW(), error_message = %s
                    WHERE id = %s AND status IN ('RUNNING', 'QUEUED', 'CREATED')
                    RETURNING billing_run_id
                    """,
                    (message, job_id),
                )
                failed_job = cur.fetchone()
                billing_run_id = failed_job.get("billing_run_id") if failed_job else None
                if billing_run_id:
                    cur.execute(
                        """
                        UPDATE billing_runs
                        SET status = 'FAILED',
                            finished_at = NOW(),
                            summary = COALESCE(summary, '{}'::jsonb) || jsonb_build_object('status', 'failed', 'reason', %s)
                        WHERE id = %s
                          AND status IN ('RUNNING', 'QUEUED', 'CREATED')
                        """,
                        (message, billing_run_id),
                    )
                    cur.execute(
                        """
                        UPDATE bill_documents
                        SET status = 'FAILED',
                            updated_at = NOW(),
                            summary = COALESCE(summary, '{}'::jsonb) || jsonb_build_object('error_message', %s)
                        WHERE (job_id = %s OR billing_run_id = %s)
                          AND status IN ('CREATED', 'DRAFT')
                        """,
                        (message, job_id, billing_run_id),
                    )
                    doc = fetch_one(
                        cur,
                        """
                        SELECT batch_id, schedule_run_id
                        FROM bill_documents
                        WHERE job_id = %s OR billing_run_id = %s
                        LIMIT 1
                        """,
                        (job_id, billing_run_id),
                    )
                    if doc:
                        reconcile_billing_batch(cur, batch_id=doc.get("batch_id"), schedule_run_id=doc.get("schedule_run_id"))
            conn.commit()
    finally:
        try:
            run_queued_jobs("billing_run", 1)
        except Exception:
            pass


def start_billing_job_background(cur, job: dict[str, Any]) -> dict[str, Any]:
    cur.execute(
        "UPDATE jobs SET status = 'RUNNING', started_at = NOW(), finished_at = NULL, error_message = NULL WHERE id = %s",
        (job["id"],),
    )
    if job.get("billing_run_id"):
        cur.execute(
            "UPDATE billing_runs SET status = 'RUNNING', started_at = NOW(), finished_at = NULL WHERE id = %s",
            (job["billing_run_id"],),
        )
    thread = threading.Thread(target=_billing_job_worker, args=(job["id"],), daemon=True)
    cur.connection.commit()
    thread.start()
    return {
        "job_id": job["id"],
        "status": "RUNNING",
        "message": "账单生成已在后台运行，请轮询任务状态。",
    }


def guarded_run_job(cur, job_id: str) -> dict[str, Any]:
    expire_stale_running_jobs(cur)

    if not try_advisory_run_lock(cur, f"job:{job_id}"):
        return {"job_id": job_id, "status": "RUNNING", "message": "这个任务已经在启动或运行中。"}

    job = fetch_one(cur, "SELECT * FROM jobs WHERE id = %s FOR UPDATE", (job_id,))
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    status = str(job.get("status") or "").upper()
    if status in TERMINAL_JOB_STATUSES or status == "RUNNING":
        return non_startable_job_response(job, status)
    if status not in STARTABLE_JOB_STATUSES:
        return non_startable_job_response(job, status)

    guard = job_concurrency_guard(str(job.get("type") or "unknown"))
    # Background billing threads commit before finishing; count RUNNING rows instead of xact locks alone.
    if running_jobs_count_for_family(cur, guard["family"]) >= guard["limit"]:
        return queued_job_response(cur, job, guard)
    slot = acquire_guard_slot(cur, guard["family"], guard["limit"])
    if slot is None:
        return queued_job_response(cur, job, guard)

    return dispatch_job_now(cur, job)


def job_queue_snapshot(cur) -> dict[str, Any]:
    rows = fetch_all(
        cur,
        """
        SELECT id, type, status, created_by, created_at, started_at, month, channel_id, vendor,
               billing_run_id, error_message
        FROM jobs
        WHERE status IN ('QUEUED', 'RUNNING')
        ORDER BY created_at ASC
        LIMIT 100
        """,
    )
    counts: dict[str, int] = {"queued": 0, "running": 0}
    families: dict[str, dict[str, int]] = {}
    for row in rows:
        status = str(row.get("status") or "").lower()
        family = job_concurrency_family(str(row.get("type") or "unknown"))
        if status in counts:
            counts[status] += 1
        families.setdefault(family, {"queued": 0, "running": 0})
        if status in families[family]:
            families[family][status] += 1
    return {"counts": counts, "families": families, "items": rows}


def run_next_queued_job_once(family: str | None = None) -> dict[str, Any]:
    requested_family = family.strip() if family else None
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            expire_stale_running_jobs(cur)
            queued = fetch_all(cur, "SELECT id, type FROM jobs WHERE status = 'QUEUED' ORDER BY created_at ASC LIMIT 50")
            for job in queued:
                job_family = job_concurrency_family(str(job.get("type") or "unknown"))
                if requested_family and requested_family != job_family:
                    continue
                result = guarded_run_job(cur, str(job["id"]))
                return {"status": result.get("status", "started"), "job_id": job["id"], "result": result}
            return {"status": "empty", "message": "当前没有可运行的排队任务。", "queue": job_queue_snapshot(cur)}


def run_queued_jobs(family: str | None = None, limit: int = 1) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for _ in range(max(0, limit)):
        result = run_next_queued_job_once(family)
        if result.get("status") == "empty":
            break
        results.append(result)
        if str(result.get("status") or "").upper() == "QUEUED":
            break
    return results


def _planned_job_ids(batch: dict[str, Any]) -> list[str]:
    summary = batch.get("summary") if isinstance(batch.get("summary"), dict) else {}
    jobs = summary.get("jobs") if isinstance(summary.get("jobs"), list) else []
    ids: list[str] = []
    seen: set[str] = set()
    for item in jobs:
        if not isinstance(item, dict):
            continue
        job_id = str(item.get("job_id") or "").strip()
        if job_id and job_id not in seen:
            ids.append(job_id)
            seen.add(job_id)
    return ids


def _first_batch_error(jobs: list[dict[str, Any]], documents: list[dict[str, Any]]) -> str | None:
    for job in jobs:
        text = str(job.get("error_message") or "").strip()
        if text:
            return text[:2000]
    for document in documents:
        summary = document.get("summary") if isinstance(document.get("summary"), dict) else {}
        text = str(summary.get("error_message") or summary.get("reason") or "").strip()
        if text:
            return text[:2000]
    return None


def _latest_child_finished_at(jobs: list[dict[str, Any]], documents: list[dict[str, Any]]) -> Any | None:
    job_values = [row.get("finished_at") for row in jobs if row.get("finished_at") is not None]
    if job_values:
        return max(job_values)
    document_values = [row.get("updated_at") for row in documents if row.get("updated_at") is not None]
    return max(document_values) if document_values else None


def reconcile_billing_batch(
    cur,
    *,
    batch_id: str | None = None,
    schedule_run_id: str | None = None,
) -> dict[str, Any] | None:
    if batch_id:
        batch = fetch_one(cur, "SELECT * FROM billing_batches WHERE id = %s FOR UPDATE", (batch_id,))
    elif schedule_run_id:
        batch = fetch_one(cur, "SELECT * FROM billing_batches WHERE schedule_run_id = %s FOR UPDATE", (schedule_run_id,))
    else:
        return None
    if not batch:
        return None

    documents = fetch_all(
        cur,
        """
        SELECT id, status, job_id, billing_run_id, summary, updated_at
        FROM bill_documents
        WHERE batch_id = %s
           OR (%s IS NOT NULL AND schedule_run_id = %s)
        """,
        (batch["id"], batch.get("schedule_run_id"), batch.get("schedule_run_id")),
    )
    planned_ids = _planned_job_ids(batch)
    job_ids = set(planned_ids)
    for document in documents:
        if document.get("job_id"):
            job_ids.add(str(document["job_id"]))

    jobs = fetch_all(
        cur,
        "SELECT id, status, error_message, billing_run_id, finished_at FROM jobs WHERE id = ANY(%s)",
        (list(job_ids),),
    ) if job_ids else []
    completion = summarize_batch_completion(
        [str(job.get("status") or "") for job in jobs],
        [str(document.get("status") or "") for document in documents],
        expected_jobs=len(planned_ids),
    )
    status = str(completion["status"])
    terminal = status in {"COMPLETED", "FAILED", "PARTIAL_FAILED"}
    error_message = _first_batch_error(jobs, documents) if status in {"FAILED", "PARTIAL_FAILED"} else None
    finished_at = _latest_child_finished_at(jobs, documents)
    summary = batch.get("summary") if isinstance(batch.get("summary"), dict) else {}
    merged_summary = {
        **json_safe(summary),
        "completion": completion,
        "error_message": error_message or "",
        "reconciled_at": utc_now_iso(),
    }

    cur.execute(
        """
        UPDATE billing_batches
        SET status = %s,
            finished_at = CASE WHEN %s THEN COALESCE(%s, finished_at, NOW()) ELSE NULL END,
            summary = %s
        WHERE id = %s
        RETURNING *
        """,
        (status, terminal, finished_at, psycopg2.extras.Json(json_safe(merged_summary)), batch["id"]),
    )
    updated = dict(cur.fetchone())

    schedule_run_id = batch.get("schedule_run_id") or schedule_run_id
    if schedule_run_id:
        cur.execute(
            """
            UPDATE schedule_runs
            SET status = %s,
                finished_at = CASE WHEN %s THEN COALESCE(%s, finished_at, NOW()) ELSE NULL END,
                summary = COALESCE(summary, '{}'::jsonb) || %s,
                error_message = %s
            WHERE id = %s
            """,
            (
                status if terminal else "RUNNING",
                terminal,
                finished_at,
                psycopg2.extras.Json({"batch_status": status, "completion": completion}),
                error_message,
                schedule_run_id,
            ),
        )
    if batch.get("fact_manifest_id"):
        fact_status = "COMPLETED" if status == "COMPLETED" else "FAILED" if terminal else "CREATED"
        cur.execute("UPDATE billing_fact_manifests SET status = %s WHERE id = %s", (fact_status, batch["fact_manifest_id"]))
    return updated


def reconcile_open_billing_batches(cur, limit: int = 100) -> list[dict[str, Any]]:
    rows = fetch_all(
        cur,
        """
        SELECT id
        FROM billing_batches
        WHERE status IN ('CREATED', 'MATERIALIZING_FACTS', 'RENDERING', 'RUNNING')
        ORDER BY created_at ASC
        LIMIT %s
        """,
        (limit,),
    )
    reconciled: list[dict[str, Any]] = []
    for row in rows:
        updated = reconcile_billing_batch(cur, batch_id=str(row["id"]))
        if updated:
            reconciled.append(updated)
    return reconciled


def create_bill_document_record(
    cur, *, batch_id: str, schedule_run_id: str, month: str, bill_type: str,
    target_type: str, target_id: str | None, status: str, s3_uri: str | None,
    idempotency_key: str, summary: dict[str, Any],
) -> dict[str, Any]:
    document_id = new_id("billdoc")
    cur.execute(
        """
        INSERT INTO bill_documents (
            id, batch_id, schedule_run_id, bill_type, target_type, target_id,
            month, status, s3_uri, summary, idempotency_key
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (idempotency_key) DO UPDATE
        SET updated_at = NOW()
        RETURNING *
        """,
        (document_id, batch_id, schedule_run_id, bill_type, target_type, target_id, month, status, s3_uri, psycopg2.extras.Json(summary), idempotency_key),
    )
    return dict(cur.fetchone())


def upsert_bill_document_for_run(
    cur, job: dict[str, Any], run: dict[str, Any], config: dict[str, Any],
    command: dict[str, Any], execution_mode: str, generated: dict[str, str], summary: dict[str, Any],
) -> dict[str, Any]:
    bill_type = str(run.get("bill_type") or job.get("bill_type") or "internal_customer_bill")
    target_type = str(run.get("target_type") or job.get("target_type") or "all")
    target_id = run.get("target_id") or job.get("target_id")
    idempotency = bill_document_idempotency(job, run, config, command)
    document_id = new_id("billdoc")
    cur.execute(
        """
        INSERT INTO bill_documents (
            id, job_id, billing_run_id, bill_type, target_type, target_id,
            month, status, s3_uri, summary, idempotency_key
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (idempotency_key) DO UPDATE
        SET status = EXCLUDED.status,
            s3_uri = EXCLUDED.s3_uri,
            summary = EXCLUDED.summary,
            job_id = EXCLUDED.job_id,
            billing_run_id = EXCLUDED.billing_run_id,
            updated_at = NOW()
        RETURNING *
        """,
        (
            document_id, job["id"], run["id"], bill_type, target_type, target_id,
            run["month"], bill_document_status_for_type(bill_type, execution_mode, generated, is_fixture=bool(summary.get("is_fixture"))),
            primary_bill_uri(generated), psycopg2.extras.Json(json_safe(summary)), idempotency,
        ),
    )
    return dict(cur.fetchone())


def run_billing_job(cur, job: dict[str, Any]) -> dict[str, Any]:
    run = fetch_one(cur, "SELECT * FROM billing_runs WHERE id = %s FOR UPDATE", (job["billing_run_id"],))
    if not run:
        raise HTTPException(status_code=409, detail="billing run row missing")
    config = fetch_one(cur, "SELECT * FROM billing_config_versions WHERE id = %s", (run["config_version_id"],))
    if not config:
        raise HTTPException(status_code=409, detail="billing config version missing")

    cur.execute("UPDATE jobs SET status = 'RUNNING', started_at = NOW(), finished_at = NULL, error_message = NULL WHERE id = %s", (job["id"],))
    cur.execute("UPDATE billing_runs SET status = 'RUNNING', started_at = NOW(), finished_at = NULL WHERE id = %s", (run["id"],))
    # Long Athena/XLSX runs must not hold an idle Postgres transaction open.
    cur.connection.commit()

    billing_prefix = uri_to_prefix(run["s3_prefix"]) or f"billing/{run['month']}/{run['id']}"
    job_prefix = uri_to_prefix(job["s3_prefix"]) or f"jobs/{utc_now().date().isoformat()}/{job['id']}"
    worker_manifest = athena_worker_manifest()
    command = build_athena_bill_command(job, run, config, billing_prefix)
    command_hash = hashlib.sha256(dumps_json(command).encode("utf-8")).hexdigest()
    # 默认尝试真实出账；显式设为 dry-run 才跳过 Athena。
    execution_mode = os.getenv("WORKBENCH_ATHENA_EXECUTION", "real")
    real_execution = execution_mode.lower() == "real"
    athena_e2e_mode = (os.getenv("ATHENA_E2E_MODE", "") or "").lower()
    real_result: dict[str, Any] | None = None
    generated: dict[str, str] = {}
    failed_message = ""
    if real_execution:
        try:
            real_result = execute_real_athena_bill(command, config, billing_prefix)
            generated = real_result.get("generated", {}) if isinstance(real_result.get("generated"), dict) else {}
            if int(real_result.get("returncode") or 0) != 0:
                stderr_tail = str(real_result.get("stderr_text") or "").strip()[-800:]
                failed_message = f"Athena billing command exited with {real_result.get('returncode')}"
                if stderr_tail:
                    failed_message += f": {stderr_tail}"
            elif not generated:
                failed_message = "Athena billing command produced no output files (check credentials / data availability)"
        except Exception as exc:
            failed_message = f"Athena billing command failed: {exc}"
    bill_summary = {}
    if real_result and isinstance(real_result.get("bill_summary"), dict):
        bill_summary = real_result["bill_summary"]
    payload = job.get("request_payload") if isinstance(job.get("request_payload"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    summary_status, job_db_status = resolve_billing_run_status(failed_message, generated)
    summary = {
        "status": summary_status,
        "mode": "athena-worker-integrated",
        "execution_mode": execution_mode,
        "athena_e2e_mode": athena_e2e_mode or "real",
        "is_fixture": athena_e2e_mode == "fixture",
        "bill_type": command.get("bill_type"),
        "target_type": command.get("target_type"),
        "target_id": command.get("target_id"),
        "month": run["month"],
        "period": payload.get("period") or metadata.get("period"),
        "snapshot_date": command.get("snapshot_date") or metadata.get("snapshot_date"),
        "channel_id": run["channel_id"],
        "vendor": run["vendor"],
        "config_version": config["version"],
        "pricing_models": len(config["pricing_snapshot"].get("models", [])) if isinstance(config["pricing_snapshot"], dict) else None,
        "generated_files": generated,
        "real_execution": real_result or {},
        "command_hash": command_hash,
        "error_message": failed_message,
        "generated_at": utc_now_iso(),
        "total_usd": bill_summary.get("total_usd", 0),
        "total_calls": bill_summary.get("total_calls", 0),
        "unique_users": bill_summary.get("unique_users", 0),
        "unique_models": bill_summary.get("unique_models", 0),
        "total_input_tokens": bill_summary.get("total_input_tokens", 0),
        "total_output_tokens": bill_summary.get("total_output_tokens", 0),
        "note": "WORKBENCH_ATHENA_EXECUTION=real executes bill_cli.py and archives generated files; dry-run skips Athena execution.",
    }
    if real_result and isinstance(real_result.get("bill_summary"), dict):
        bill_totals = normalize_kpi_payload(real_result["bill_summary"])
        summary.update(bill_totals)
        summary["bill_summary"] = real_result["bill_summary"]
    report = (
        f"# Billing run {run['id']}\n\n"
        f"- Month: {run['month']}\n"
        f"- Channel: {run['channel_id']}\n"
        f"- Bill type: {command.get('bill_type')}\n"
        f"- Config version: {config['version']}\n"
        f"- Worker: agent-workbench/athena_worker/bill_cli.py\n"
        f"- Execution mode: {execution_mode}\n"
        f"- Command: `{command['shell']}`\n"
        f"- Status: {summary['status']}\n"
    )
    # 账单产物（billing_prefix）落到专用账单 store（结构化路径/独立桶）；
    # 任务执行记录（job_prefix）保留在主 store。
    uris = {
        "command": billing_artifacts.put_json(f"{billing_prefix}/command.json", command),
        "worker_manifest": billing_artifacts.put_json(f"{billing_prefix}/athena_worker_manifest.json", worker_manifest),
        "summary": billing_artifacts.put_json(f"{billing_prefix}/summary.json", summary),
        "pricing": billing_artifacts.put_json(f"{billing_prefix}/config/pricing.json", config["pricing_snapshot"]),
        "discounts": billing_artifacts.put_json(f"{billing_prefix}/config/discounts.json", config["discounts_snapshot"]),
        "report": billing_artifacts.put_text(f"{billing_prefix}/report.md", report, "text/markdown; charset=utf-8"),
        "job": artifacts.put_json(f"{job_prefix}/job.json", {"job": public_job(job), "command": command, "worker_manifest": worker_manifest}),
        "result": artifacts.put_json(f"{job_prefix}/output/result.json", {"status": summary["status"], "summary": summary}),
    }
    if real_result:
        if real_result.get("stdout"):
            uris["stdout"] = str(real_result["stdout"])
        if real_result.get("stderr"):
            uris["stderr"] = str(real_result["stderr"])
        for name, uri in generated.items():
            uris[f"generated/{name}"] = uri
    document = upsert_bill_document_for_run(cur, job, run, config, command, execution_mode.lower(), generated, summary)
    bill_documents = sync_split_bill_documents(
        cur,
        job=job,
        run=run,
        config=config,
        command=command,
        execution_mode=execution_mode.lower(),
        generated=generated,
        parent_document=document,
        base_summary=summary,
    )
    document = bill_documents[0]
    billing_directory = f"账单结果/{run['month']}/{run['id']}"
    artifact_directories = {
        "command": billing_directory,
        "worker_manifest": billing_directory,
        "summary": billing_directory,
        "detail": billing_directory,
        "pricing": f"{billing_directory}/价格方案",
        "discounts": f"{billing_directory}/价格方案",
        "job": f"{billing_directory}/任务记录",
        "report": f"{billing_directory}/任务记录",
        "result": f"{billing_directory}/任务记录",
    }
    for role, uri in uris.items():
        insert_file_index(
            cur, filename=filename_from_uri(uri, f"{role}.json"), s3_uri=uri,
            category="billing-result", job_id=job["id"], uploaded_by="billing",
            metadata={
                "source": "billing_run", "role": role, "directory_path": artifact_directories.get(role, billing_directory),
                "month": run["month"], "channel_id": run["channel_id"], "vendor": run["vendor"],
                "billing_run_id": run["id"], "job_id": job["id"], "bill_type": command.get("bill_type"),
                "target_type": command.get("target_type"), "target_id": command.get("target_id"),
                "bill_document_id": document["id"], "execution_mode": execution_mode,
            },
            content_type=content_type_for_filename(filename_from_uri(uri, f"{role}.json")),
        )
    result = {"status": summary["status"], "summary": summary, "artifacts": uris, "bill_document": document}
    cur.execute("UPDATE billing_runs SET status = %s, finished_at = NOW(), summary = %s, artifacts = %s WHERE id = %s", (job_db_status, psycopg2.extras.Json(json_safe(summary)), psycopg2.extras.Json(json_safe(uris)), run["id"]))
    cur.execute("UPDATE jobs SET status = %s, finished_at = NOW(), result = %s, error_message = %s WHERE id = %s", (job_db_status, psycopg2.extras.Json(json_safe(result)), failed_message or None, job["id"]))
    batch_id = document.get("batch_id") if isinstance(document, dict) else None
    schedule_run_id = document.get("schedule_run_id") if isinstance(document, dict) else None
    reconciled_batch = reconcile_billing_batch(cur, batch_id=batch_id, schedule_run_id=schedule_run_id)
    if reconciled_batch:
        result["batch"] = reconciled_batch
    return {"job_id": job["id"], "billing_run_id": run["id"], **result}


def run_agent_job(cur, job: dict[str, Any]) -> dict[str, Any]:
    job_prefix = uri_to_prefix(job["s3_prefix"]) or f"jobs/{utc_now().date().isoformat()}/{job['id']}"
    cur.execute("UPDATE jobs SET status = 'RUNNING', started_at = NOW(), finished_at = NULL, error_message = NULL WHERE id = %s", (job["id"],))
    context = build_agent_context(cur, job)

    try:
        execution = execute_agent(context)
    except Exception as exc:
        message = f"agent runner failed: {exc}"
        cur.execute("UPDATE jobs SET status = 'FAILED', finished_at = NOW(), error_message = %s WHERE id = %s", (message, job["id"]))
        return {"job_id": job["id"], "status": "failed", "error": message}

    artifact_uris: dict[str, str] = {}
    indexed_files: list[dict[str, Any]] = []
    for rel, path in execution.output_files:
        key = f"{job_prefix}/output/{rel}"
        try:
            uri = artifacts.put_bytes(key, path.read_bytes(), content_type_for_filename(rel))
        except Exception:
            continue
        role = Path(rel).stem if "/" not in rel else rel.split("/", 1)[0]
        artifact_uris[role] = uri
        artifact_uris[rel] = uri
        indexed_files.append({"rel": rel, "uri": uri})

    if execution.sandbox_id:
        cur.execute("UPDATE jobs SET sandbox_id = %s WHERE id = %s", (execution.sandbox_id, job["id"]))

    change_request_id = ingest_change_request(cur, job, execution, context, artifact_uris)

    for item in indexed_files:
        insert_file_index(
            cur, filename=Path(item["rel"]).name, s3_uri=item["uri"],
            category="agent-output", job_id=job["id"], uploaded_by="agent",
            metadata={"source": "agent_job", "rel": item["rel"], "job_id": job["id"], "mode": execution.mode},
            content_type=content_type_for_filename(item["rel"]),
        )

    result_json = execution.result_json or {}
    status = "completed" if execution.succeeded else "failed"
    result = {
        "status": status, "mode": execution.mode, "sandbox_id": execution.sandbox_id,
        "change_request_id": change_request_id, "config_change_request_id": change_request_id,
        "result": result_json, "impact": result_json.get("impact") or {},
        "input_manifest": execution.input_manifest, "artifacts": artifact_uris,
        "stdout_tail": (execution.stdout or "")[-2000:],
    }
    db_status = "COMPLETED" if execution.succeeded else "FAILED"
    error_message = None if execution.succeeded else (execution.stderr or "agent returned non-zero exit code")[:2000]
    cur.execute("UPDATE jobs SET status = %s, finished_at = NOW(), result = %s, error_message = %s WHERE id = %s", (db_status, psycopg2.extras.Json(json_safe(result)), error_message, job["id"]))
    return {"job_id": job["id"], **result}
