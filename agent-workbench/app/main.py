"""Agent Workbench API — 精简入口。

路由拆分到 app/routers/，业务逻辑拆分到 app/services/，
runner 模块在 app/runner/。

此文件保留：
1. FastAPI app 初始化与中间件注册
2. include_router 汇总
3. 向后兼容导出（worker.py / scheduler.py 从 .main 导入的符号）
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import security
from .routers import agent, billing, config, files, jobs, rawlogs
from .services.artifacts import artifacts
from .services.core import (
    db_conn,
    env_int,
    init_schema,
    seed_default_schedules,
    utc_now_iso,
)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Agent Workbench API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=security.cors_origins(),
    allow_credentials=security.cors_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(security.AuthMiddleware)
app.add_middleware(security.RequestSizeLimitMiddleware)

# 注册路由
app.include_router(config.router)
app.include_router(jobs.router)
app.include_router(billing.router)
app.include_router(agent.router)
app.include_router(files.router)
app.include_router(rawlogs.router)


@app.on_event("startup")
def on_startup() -> None:
    init_schema()
    seed_default_schedules()


@app.get("/health")
def health() -> dict[str, Any]:
    db_ok = False
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            db_ok = cur.fetchone()[0] == 1
    return {"ok": True, "db": db_ok, "artifact_store": "s3" if artifacts.enabled else "local"}


@app.get("/api/status")
def api_status() -> dict[str, Any]:
    status = health()
    return {"success": status["ok"], **status}


# ---------------------------------------------------------------------------
# 向后兼容导出 — worker.py / scheduler.py 从 .main 导入这些符号
# ---------------------------------------------------------------------------
from .services.core import (  # noqa: E402, F401
    BILL_TYPES,
    DEFAULT_SCHEDULES,
    JOB_CONCURRENCY_DEFAULTS,
    STARTABLE_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
    WORKBENCH_ROOT,
    acquire_guard_slot,
    checksum_config,
    clamp_int,
    content_type_for_filename,
    content_type_for_path,
    dumps_json,
    ensure_agent_session,
    expire_stale_running_jobs,
    fetch_all,
    fetch_one,
    fetch_scalar,
    filename_from_uri,
    insert_agent_event,
    int_or_none,
    job_concurrency_family,
    job_concurrency_guard,
    job_run_timeout_seconds,
    json_safe,
    new_id,
    normalize_bill_type,
    normalize_reference_ids,
    public_job,
    read_json,
    safe_filename,
    slug,
    try_advisory_run_lock,
    uri_to_prefix,
    utc_now,
    infer_target,
)

from .services.config import (  # noqa: E402, F401
    ensure_config_version,
    get_config_by_version,
    get_latest_config,
    insert_config_version,
    load_seed_config,
    next_local_version,
    normalize_config_row,
    update_config_version,
    upsert_config_version,
)

from .services.jobs import (  # noqa: E402, F401
    dispatch_job_now,
    enqueue_agent_job,
    guarded_run_job,
    job_queue_snapshot,
    non_startable_job_response,
    queued_job_response,
    run_billing_job,
    run_agent_job,
    run_next_queued_job_once,
    run_queued_jobs,
)

from .services.billing import (  # noqa: E402, F401
    build_athena_bill_command,
    athena_worker_manifest,
    bill_document_idempotency,
    bill_document_status_for_type,
    execute_real_athena_bill,
    insert_file_index,
    period_bounds_for_month,
    previous_month_label,
    primary_bill_uri,
)

from .services.agent import (  # noqa: E402, F401
    agent_sse_generator,
    build_agent_context,
    build_agent_instructions,
    experience_context_for_sessions,
    format_experience_reference_content,
    ingest_change_request,
    sse,
    stream_mock_codingplan,
    stream_zhipu_codingplan,
    zhipu_codingplan_endpoint,
)

from .routers.billing import (  # noqa: E402, F401
    ScheduleRunRequest,
    trigger_schedule_run,
)
