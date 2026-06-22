"""Agent 会话路由：创建/查询/流式、建议处理、经验管理。"""

from __future__ import annotations

import os
import re
from typing import Any

import psycopg2.extras
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..runner import SandboxClient, create_persistent_session
from ..runner import config as runner_config
from ..services.agent import (
    active_skills_for_context,
    agent_sse_generator,
    zhipu_codingplan_endpoint,
)
from ..services.artifacts import artifacts
from ..services.billing import insert_file_index
from ..services.config import (
    get_latest_config,
    insert_config_version,
    next_local_version,
)
from ..services.core import (
    clamp_int,
    db_conn,
    dumps_json,
    ensure_agent_session,
    fetch_all,
    fetch_one,
    insert_agent_event,
    new_id,
    normalize_reference_ids,
    slug,
    utc_now_iso,
)

router = APIRouter(tags=["agent"])


BASE_RECONCILE_PRICE_RULE = "所有对账均基于刊例价进行。"


def with_base_agent_rules(prompt: str) -> str:
    prompt = (prompt or "").strip()
    if "刊例价" in prompt:
        return prompt
    base_rule = f"基础规则：{BASE_RECONCILE_PRICE_RULE}"
    return f"{prompt}\n\n{base_rule}".strip() if prompt else base_rule


class AgentSessionRequest(BaseModel):
    prompt: str
    provider: str = "claude_code"
    runtime: str = "codingplan"
    model: str | None = None
    job_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    live: bool = False


class AgentMessageRequest(BaseModel):
    content: str
    role: str = "user"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentExperienceReferenceRequest(BaseModel):
    session_ids: list[str] = Field(default_factory=list)
    updated_by: str = "operator"


class SkillExclusionRequest(BaseModel):
    excluded_skill_ids: list[str] = Field(default_factory=list)
    updated_by: str = "operator"


class FileReferenceRequest(BaseModel):
    file_ids: list[str] = Field(default_factory=list)
    referenced_by: str = "operator"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionUpdateRequest(BaseModel):
    title: str | None = None
    tags: list[str] | None = None
    favorite: bool | None = None
    vendor: str | None = None
    month: str | None = None


class ApplyChangeRequest(BaseModel):
    reviewer: str = "operator"
    review_comment: str | None = None
    change_payload: dict[str, Any] | None = None
    reason: str | None = None


class SkillPublishRequest(BaseModel):
    category: str
    name: str
    version: str | None = None
    vendor: str = "*"
    tags: list[str] = Field(default_factory=list)
    content: str | None = None
    manifest: dict[str, Any] = Field(default_factory=dict)
    applies_to: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    created_from_job: str | None = None


class SkillCreateRequest(BaseModel):
    category: str = "billing-experience"
    name: str
    vendor: str = "*"
    tags: list[str] = Field(default_factory=list)
    content: str
    applies_to: dict[str, Any] = Field(default_factory=dict)
    source: str = "manual"


class SkillEditRequest(BaseModel):
    name: str | None = None
    vendor: str | None = None
    tags: list[str] | None = None
    content: str | None = None
    applies_to: dict[str, Any] | None = None


class SkillStatusRequest(BaseModel):
    status: str = "active"


# --- Sessions ---

def _agent_event_sink(session_id: str):
    def sink(event_type: str, role: str, content: str, payload: dict[str, Any] | None = None) -> None:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                insert_agent_event(cur, session_id, event_type, role, content, payload or {})

    return sink


def _build_session_sandbox_context(
    session_id: str,
    req: AgentSessionRequest,
    metadata: dict[str, Any],
    referenced_experiences: list[dict[str, Any]],
) -> dict[str, Any]:
    prompt = with_base_agent_rules((req.prompt or "").strip() or "请开始对账任务。")
    month = metadata.get("month")
    vendor = metadata.get("vendor")
    channel_id = metadata.get("channel_id")
    bill_type = metadata.get("bill_type")
    excluded_skill_ids = normalize_reference_ids(metadata.get("excluded_skill_ids"))
    try:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                skills = active_skills_for_context(
                    cur, vendor=vendor, bill_type=bill_type, month=month, excluded_ids=excluded_skill_ids
                )
    except Exception:
        skills = []
    return {
        "job": {
            "id": session_id,
            "type": "agent_session",
            "status": "CREATED",
            "month": month,
            "channel_id": channel_id,
            "vendor": vendor,
            "request_payload": {"prompt": prompt, "metadata": metadata},
        },
        "instructions": prompt,
        "billing_summary": {
            "month": month,
            "vendor": vendor,
            "channel_id": channel_id,
            "session_id": session_id,
        },
        "pricing": {},
        "discounts": {},
        "supplier_files": [],
        "experiences": referenced_experiences,
        "skills": skills,
    }


def _try_create_session_sandbox(
    session_id: str,
    req: AgentSessionRequest,
    metadata: dict[str, Any],
    referenced_experiences: list[dict[str, Any]],
) -> tuple[dict[str, Any], str | None]:
    metadata = dict(metadata)
    metadata["sandbox_configured"] = runner_config.sandbox_configured()
    if not runner_config.sandbox_configured():
        return metadata, None

    try:
        persistent = create_persistent_session(
            _build_session_sandbox_context(session_id, req, metadata, referenced_experiences),
            event_sink=_agent_event_sink(session_id),
        )
        sandbox_id = persistent.sandbox_id
        metadata["sandbox"] = {
            "enabled": True,
            "status": "created",
            "sandbox_id": sandbox_id,
            "workdir": str(persistent.workdir),
            "runner_mode": runner_config.runner_mode(),
            "agent_mode": runner_config.agent_mode(),
        }
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "UPDATE agent_sessions SET sandbox_id = %s, status = 'SANDBOX_READY', metadata = %s, updated_at = NOW() WHERE id = %s",
                    (sandbox_id, psycopg2.extras.Json(metadata), session_id),
                )
                insert_agent_event(
                    cur,
                    session_id,
                    "sandbox.ready",
                    "system",
                    "沙箱已启动，Agent 可以在隔离环境中执行。",
                    {"sandbox_id": sandbox_id, "workdir": str(persistent.workdir)},
                )
        return metadata, sandbox_id
    except Exception as exc:
        metadata["sandbox"] = {"enabled": True, "status": "failed", "error": str(exc)}
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "UPDATE agent_sessions SET metadata = %s, updated_at = NOW() WHERE id = %s",
                    (psycopg2.extras.Json(metadata), session_id),
                )
                insert_agent_event(
                    cur,
                    session_id,
                    "run.warning",
                    "system",
                    f"沙箱创建失败：{exc}",
                    {"stage": "sandbox.create", "error": str(exc)},
                )
        return metadata, None

@router.post("/api/agent/sessions")
def create_agent_session(req: AgentSessionRequest) -> dict[str, Any]:
    session_id = new_id("as")
    model = req.model or os.getenv("ZHIPU_CODINGPLAN_MODEL", "glm-5.2")
    referenced_experiences: list[dict[str, Any]] = []
    metadata = {
        **req.metadata, "model": model, "live_requested": req.live,
        "coding_endpoint": zhipu_codingplan_endpoint(),
        "api_key_configured": bool(os.getenv("ZHIPU_CODINGPLAN_API_KEY")),
    }
    vendor = req.metadata.get("vendor")
    month = req.metadata.get("month")
    title = req.metadata.get("title") or (req.prompt or "").strip().splitlines()[0][:80] or "Agent 会话"
    # 经验已统一为 Skills 知识库，启动会话时按相关性自动注入（见 active_skills_for_context），
    # 不再引用历史会话作为“经验”。会话可通过 metadata.excluded_skill_ids 手动排除个别技能。
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "INSERT INTO agent_sessions (id, provider, runtime, status, job_id, prompt, metadata, title, vendor, month) VALUES (%s, %s, %s, 'CREATED', %s, %s, %s, %s, %s, %s)",
                (session_id, req.provider, req.runtime, req.job_id, req.prompt, psycopg2.extras.Json(metadata), title, vendor, month),
            )
            insert_agent_event(cur, session_id, "session.created", "system", "ClaudeCode CodingPlan session created.", {"provider": req.provider, "runtime": req.runtime, "model": model})
            injected = active_skills_for_context(cur, vendor=vendor, bill_type=req.metadata.get("bill_type"), month=month, excluded_ids=normalize_reference_ids(metadata.get("excluded_skill_ids")), with_content=False)
            if injected:
                insert_agent_event(cur, session_id, "skills.injected", "system", f"已按相关性注入 {len(injected)} 条经验/技能到对账 Agent。", {"skills": [{"id": item["id"], "name": item["name"], "score": item["score"]} for item in injected]})
            insert_agent_event(cur, session_id, "message", "user", req.prompt, {"source": "initial_prompt"})
    metadata, sandbox_id = _try_create_session_sandbox(session_id, req, metadata, referenced_experiences)
    return {
        "id": session_id,
        "session_id": session_id,
        "status": "SANDBOX_READY" if sandbox_id else "CREATED",
        "sandbox_id": sandbox_id,
        "metadata": metadata,
    }


@router.get("/api/agent/sessions")
def list_agent_sessions(q: str | None = None, vendor: str | None = None, month: str | None = None, tag: str | None = None, favorite: bool | None = None, limit: int = 50) -> dict[str, Any]:
    filters: list[str] = []
    args: list[Any] = []
    if q:
        filters.append("(COALESCE(title, '') ILIKE %s OR prompt ILIKE %s)")
        like = f"%{q}%"
        args.extend([like, like])
    if vendor:
        filters.append("vendor = %s")
        args.append(vendor)
    if month:
        filters.append("month = %s")
        args.append(month)
    if tag:
        filters.append("tags @> %s::jsonb")
        args.append(dumps_json([tag]))
    if favorite is not None:
        filters.append("favorite = %s")
        args.append(favorite)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    args.append(clamp_int(limit, 50, 1, 200))
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rows = fetch_all(cur, f"SELECT * FROM agent_sessions {where} ORDER BY favorite DESC, updated_at DESC LIMIT %s", tuple(args))
    return {"items": rows}


@router.patch("/api/agent/sessions/{session_id}")
def update_agent_session(session_id: str, req: SessionUpdateRequest) -> dict[str, Any]:
    sets: list[str] = []
    args: list[Any] = []
    if req.title is not None:
        sets.append("title = %s")
        args.append(req.title)
    if req.tags is not None:
        sets.append("tags = %s")
        args.append(psycopg2.extras.Json(req.tags))
    if req.favorite is not None:
        sets.append("favorite = %s")
        args.append(req.favorite)
    if req.vendor is not None:
        sets.append("vendor = %s")
        args.append(req.vendor)
    if req.month is not None:
        sets.append("month = %s")
        args.append(req.month)
    if not sets:
        raise HTTPException(status_code=400, detail="no fields to update")
    sets.append("updated_at = NOW()")
    args.append(session_id)
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            ensure_agent_session(cur, session_id)
            cur.execute(f"UPDATE agent_sessions SET {', '.join(sets)} WHERE id = %s RETURNING *", tuple(args))
            row = dict(cur.fetchone())
    return {"session": row}


@router.post("/api/agent/sessions/{session_id}/favorite")
def toggle_session_favorite(session_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    favorite = True
    if isinstance(payload, dict) and "favorite" in payload:
        favorite = bool(payload["favorite"])
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            ensure_agent_session(cur, session_id)
            cur.execute("UPDATE agent_sessions SET favorite = %s, updated_at = NOW() WHERE id = %s RETURNING *", (favorite, session_id))
            row = dict(cur.fetchone())
    return {"session": row}


@router.get("/api/agent/sessions/{session_id}")
def get_agent_session(session_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            session = ensure_agent_session(cur, session_id)
    return {"session": session}


@router.get("/api/agent/sessions/{session_id}/events")
def get_agent_events(session_id: str, after_seq: int = 0) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            ensure_agent_session(cur, session_id)
            events = fetch_all(cur, "SELECT * FROM agent_events WHERE session_id = %s AND seq > %s ORDER BY seq ASC LIMIT 500", (session_id, after_seq))
    return {"session_id": session_id, "items": events}


@router.get("/api/agent/sessions/{session_id}/history")
def get_agent_history(session_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            session = ensure_agent_session(cur, session_id)
            events = fetch_all(
                cur,
                """
                SELECT * FROM (
                    SELECT * FROM agent_events
                    WHERE session_id = %s
                    ORDER BY seq DESC
                    LIMIT 1000
                ) recent_events
                ORDER BY seq ASC
                """,
                (session_id,),
            )
            files = fetch_all(cur, "SELECT * FROM uploaded_files WHERE session_id = %s ORDER BY created_at DESC LIMIT 100", (session_id,))
            referenced_files = fetch_all(cur, """
                SELECT uf.* FROM agent_file_references afr
                JOIN uploaded_files uf ON uf.id = afr.file_id
                WHERE afr.session_id = %s ORDER BY afr.created_at DESC LIMIT 100
            """, (session_id,))
    seen_files: set[str] = set()
    merged_files: list[dict[str, Any]] = []
    for file in [*referenced_files, *files]:
        if file["id"] in seen_files:
            continue
        seen_files.add(file["id"])
        merged_files.append(file)
    messages = [e for e in events if e.get("event_type") in {"message", "assistant.delta", "operator.message.received", "run.completed", "run.error"}]
    return {"session": session, "events": events, "messages": messages, "files": merged_files}


@router.post("/api/agent/sessions/{session_id}/messages")
def send_agent_message(session_id: str, req: AgentMessageRequest) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            session = ensure_agent_session(cur, session_id)
            session_status = str(session.get("status") or "").upper()
            continuation = session_status in {"COMPLETED", "FAILED", "PAUSED"}
            payload = {"source": "operator", **req.metadata, "continuation": continuation, "previous_status": session_status}
            event = insert_agent_event(cur, session_id, "message", req.role, req.content, payload)
            next_status = "HUMAN_REPLIED" if continuation else (session_status or "CREATED")
            cur.execute("UPDATE agent_sessions SET status = %s, updated_at = NOW() WHERE id = %s", (next_status, session_id))
    return {"status": "accepted", "session_id": session_id, "event": event, "continuation": continuation}


@router.post("/api/agent/sessions/{session_id}/experience-references")
def update_agent_experience_references(session_id: str, req: AgentExperienceReferenceRequest) -> dict[str, Any]:
    """已弃用：经验改为 Skills 知识库自动注入，引用历史会话的机制不再生效。"""
    raise HTTPException(status_code=410, detail="experience references are deprecated; experiences are now injected automatically from the Skills library")


@router.post("/api/agent/sessions/{session_id}/skill-exclusions")
def update_agent_skill_exclusions(session_id: str, req: SkillExclusionRequest) -> dict[str, Any]:
    """记录本次会话需要排除的技能 id（写入 metadata.excluded_skill_ids）。"""
    excluded = normalize_reference_ids(req.excluded_skill_ids)
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            session = ensure_agent_session(cur, session_id)
            metadata = dict(session.get("metadata") or {})
            metadata["excluded_skill_ids"] = excluded
            cur.execute("UPDATE agent_sessions SET metadata = %s, updated_at = NOW() WHERE id = %s", (psycopg2.extras.Json(metadata), session_id))
    return {"status": "saved", "session_id": session_id, "excluded_skill_ids": excluded}


@router.post("/api/agent/sessions/{session_id}/files/reference")
def reference_agent_files(session_id: str, req: FileReferenceRequest) -> dict[str, Any]:
    file_ids = normalize_reference_ids(req.file_ids)
    if not file_ids:
        raise HTTPException(status_code=400, detail="file_ids is required")
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            ensure_agent_session(cur, session_id)
            files = fetch_all(cur, "SELECT * FROM uploaded_files WHERE id = ANY(%s)", (file_ids,))
            found_ids = {file["id"] for file in files}
            missing = [fid for fid in file_ids if fid not in found_ids]
            if missing:
                raise HTTPException(status_code=404, detail=f"files not found: {', '.join(missing)}")
            referenced: list[dict[str, Any]] = []
            for file in files:
                ref_id = new_id("afr")
                cur.execute(
                    "INSERT INTO agent_file_references (id, session_id, file_id, created_by, metadata) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (session_id, file_id) DO UPDATE SET created_at = NOW(), created_by = EXCLUDED.created_by, metadata = EXCLUDED.metadata RETURNING *",
                    (ref_id, session_id, file["id"], req.referenced_by, psycopg2.extras.Json({"source": "file_reference", **req.metadata})),
                )
                referenced.append(file)
            content = "\n".join(f"已引用资料：{file['filename']}，类型：{file['category']}，地址：{file['s3_uri']}" for file in referenced)
            event = insert_agent_event(cur, session_id, "file.reference", "system", content, {"source": "file_reference", "file_ids": [file["id"] for file in referenced], "files": [{"id": file["id"], "filename": file["filename"], "category": file["category"], "s3_uri": file["s3_uri"], "metadata": file.get("metadata") or {}} for file in referenced]})
            cur.execute("UPDATE agent_sessions SET updated_at = NOW() WHERE id = %s", (session_id,))
    return {"status": "referenced", "session_id": session_id, "files": referenced, "event": event}


@router.get("/api/agent/sessions/{session_id}/stream")
def stream_agent_session(session_id: str, live: bool = False):
    return StreamingResponse(agent_sse_generator(session_id, live=live), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/api/agent/sessions/{session_id}/pause")
def pause_agent_session(session_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            session = ensure_agent_session(cur, session_id)
            sandbox_id = session.get("sandbox_id")
            paused = False
            if sandbox_id and runner_config.sandbox_configured():
                try:
                    SandboxClient().pause_sandbox(sandbox_id)
                    paused = True
                except Exception as exc:
                    insert_agent_event(cur, session_id, "run.warning", "system", f"暂停沙箱失败：{exc}", {})
            cur.execute("UPDATE agent_sessions SET status = 'PAUSED', updated_at = NOW() WHERE id = %s", (session_id,))
    return {"status": "paused", "session_id": session_id, "sandbox_paused": paused}


@router.post("/api/agent/sessions/{session_id}/resume")
def resume_agent_session(session_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            session = ensure_agent_session(cur, session_id)
            sandbox_id = session.get("sandbox_id")
            resumed = False
            if sandbox_id and runner_config.sandbox_configured():
                try:
                    SandboxClient().resume_sandbox(sandbox_id)
                    resumed = True
                except Exception as exc:
                    insert_agent_event(cur, session_id, "run.warning", "system", f"恢复沙箱失败：{exc}", {})
            cur.execute("UPDATE agent_sessions SET status = 'RUNNING', updated_at = NOW() WHERE id = %s", (session_id,))
    return {"status": "resumed", "session_id": session_id, "sandbox_resumed": resumed}


# --- Change requests ---

def change_request_detail(cur, change: dict[str, Any]) -> dict[str, Any]:
    before = change.get("before_config_json") or {}
    after = change.get("after_config_json") or {}
    impact = change.get("impact_summary_json") or {}
    evidence = change.get("evidence_json") or []
    source_job = None
    if change.get("job_id"):
        source_job = fetch_one(cur, "SELECT id, type, month, channel_id, vendor, billing_run_id FROM jobs WHERE id = %s", (change["job_id"],))
    return {**change, "diff": {"before": before, "after": after}, "impact": impact, "evidence": evidence, "source_job": source_job}


@router.get("/api/change-requests")
def list_change_requests(status: str | None = None) -> dict[str, Any]:
    where = ""
    args: tuple[Any, ...] = ()
    if status:
        where = "WHERE status = %s"
        args = (status,)
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rows = fetch_all(cur, f"SELECT * FROM config_change_requests {where} ORDER BY created_at DESC LIMIT 100", args)
    return {"items": rows}


@router.get("/api/change-requests/{change_request_id}")
def get_change_request(change_request_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            change = fetch_one(cur, "SELECT * FROM config_change_requests WHERE id = %s", (change_request_id,))
            if not change:
                raise HTTPException(status_code=404, detail="change request not found")
            detail = change_request_detail(cur, change)
    return {"change_request": detail}


@router.post("/api/change-requests/{change_request_id}/rerun-billing")
def rerun_billing_after_change(change_request_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from .jobs import BillingRunRequest, _create_billing_run
    from ..services.core import int_or_none
    payload = payload or {}
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            change = fetch_one(cur, "SELECT * FROM config_change_requests WHERE id = %s", (change_request_id,))
            if not change:
                raise HTTPException(status_code=404, detail="change request not found")
            source_job = fetch_one(cur, "SELECT * FROM jobs WHERE id = %s", (change.get("job_id"),)) if change.get("job_id") else None
            config_version_id = change.get("generated_config_version_id")
            if not config_version_id:
                latest = get_latest_config(cur)
                config_version_id = latest["id"]
    month = payload.get("month") or (source_job or {}).get("month")
    if not month:
        raise HTTPException(status_code=400, detail="month is required to rerun billing")
    impact = change.get("impact_summary_json") or {}
    channel_id = payload.get("channel_id")
    if channel_id is None:
        channel_id = (source_job or {}).get("channel_id") or impact.get("channel_id")
    result = _create_billing_run(
        BillingRunRequest(
            month=str(month), channel_id=int_or_none(channel_id),
            vendor=(source_job or {}).get("vendor") or impact.get("vendor"),
            config_version_id=config_version_id, created_by="billing-rerun",
            metadata={"source": "billing_rerun_after_suggestion", "change_request_id": change_request_id},
        )
    )
    return {"status": "billing_rerun_created", "change_request_id": change_request_id, **result}


def _create_inline_change_request(cur, change_request_id: str, req: ApplyChangeRequest) -> dict[str, Any]:
    payload = req.change_payload or {}
    cur.execute(
        "INSERT INTO config_change_requests (id, type, status, proposed_by, reason, change_payload_json) VALUES (%s, %s, 'open', 'user', %s, %s) RETURNING *",
        (change_request_id, payload.get("type", "discount"), req.reason or payload.get("reason"), psycopg2.extras.Json(payload)),
    )
    return dict(cur.fetchone())


def _apply_config_suggestion(change_request_id: str, req: ApplyChangeRequest) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            change = fetch_one(cur, "SELECT * FROM config_change_requests WHERE id = %s FOR UPDATE", (change_request_id,))
            if not change:
                if not req.change_payload:
                    raise HTTPException(status_code=404, detail="change request not found")
                change = _create_inline_change_request(cur, change_request_id, req)
            if change["status"] in {"approved", "applied", "ignored", "rejected"}:
                raise HTTPException(status_code=409, detail=f"change request is already {change['status']}")
            latest = get_latest_config(cur)
            payload = dict(change["change_payload_json"] or {})
            pricing = payload.get("pricing_json") or payload.get("pricing_snapshot") or latest["pricing_snapshot"]
            discounts = payload.get("discounts_json") or payload.get("discounts_snapshot") or latest["discounts_snapshot"]
            next_version = next_local_version(cur)
            cur.execute("UPDATE config_change_requests SET reviewer = %s, review_comment = %s, reviewed_at = NOW() WHERE id = %s", (req.reviewer, req.review_comment, change_request_id))
            config_version = insert_config_version(cur=cur, version=next_version, pricing=pricing, discounts=discounts, created_by=req.reviewer, source_change_request_id=change_request_id)
            cur.execute("UPDATE config_change_requests SET status = 'applied', applied_at = NOW(), generated_config_version_id = %s WHERE id = %s", (config_version["id"], change_request_id))
    return {"status": "applied", "change_request_id": change_request_id, "config_version": config_version}


@router.post("/api/change-requests/{change_request_id}/apply")
def apply_change_request(change_request_id: str, req: ApplyChangeRequest) -> dict[str, Any]:
    return _apply_config_suggestion(change_request_id, req)


@router.post("/api/change-requests/{change_request_id}/approve")
def legacy_change_request_apply_alias(change_request_id: str, req: ApplyChangeRequest) -> dict[str, Any]:
    return _apply_config_suggestion(change_request_id, req)


@router.post("/api/workbench/config-change-requests/{change_request_id}/approve")
def legacy_workbench_apply_alias(change_request_id: str, req: ApplyChangeRequest) -> dict[str, Any]:
    result = _apply_config_suggestion(change_request_id, req)
    cv = result["config_version"]
    return {**result, "id": cv["id"], "config_version_id": cv["id"], "version_id": cv["id"], "version_name": cv["version"]}


@router.post("/api/workbench/config-change-requests/{change_request_id}/apply")
def apply_workbench_change_request(change_request_id: str, req: ApplyChangeRequest) -> dict[str, Any]:
    return legacy_workbench_apply_alias(change_request_id, req)


@router.post("/api/change-requests/{change_request_id}/ignore")
def ignore_change_request(change_request_id: str, req: ApplyChangeRequest) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            change = fetch_one(cur, "SELECT * FROM config_change_requests WHERE id = %s FOR UPDATE", (change_request_id,))
            if not change:
                raise HTTPException(status_code=404, detail="change request not found")
            if change["status"] in {"applied", "ignored", "rejected"}:
                raise HTTPException(status_code=409, detail=f"change request is already {change['status']}")
            cur.execute("UPDATE config_change_requests SET status = 'ignored', reviewer = %s, review_comment = %s, reviewed_at = NOW() WHERE id = %s RETURNING *", (req.reviewer, req.review_comment or req.reason, change_request_id))
            row = dict(cur.fetchone())
    return {"status": "ignored", "change_request": row}


@router.post("/api/workbench/config-change-requests/{change_request_id}/ignore")
def ignore_workbench_change_request(change_request_id: str, req: ApplyChangeRequest) -> dict[str, Any]:
    return ignore_change_request(change_request_id, req)


@router.post("/api/change-requests/{change_request_id}/save-experience")
def save_change_request_experience(change_request_id: str, req: ApplyChangeRequest) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            change = fetch_one(cur, "SELECT * FROM config_change_requests WHERE id = %s", (change_request_id,))
            if not change:
                raise HTTPException(status_code=404, detail="change request not found")
    payload = change.get("change_payload_json") or {}
    impact = change.get("impact_summary_json") or {}
    title = f"{change.get('type') or 'billing'}-{change_request_id}"
    content = "\n".join([f"# {title}", "", "## 场景", change.get("reason") or req.reason or "对账建议", "", "## 建议", dumps_json(payload), "", "## 影响", dumps_json(impact), "", "## 处理记录", req.review_comment or "保存为历史经验。", ""])
    skill = _publish_skill(SkillPublishRequest(
        category="billing-experience", name=title, vendor="*",
        tags=["agent-workbench", "reconcile", str(change.get("type") or "billing")],
        content=content, manifest={"source": "config_change_request", "change_request_id": change_request_id, "job_id": change.get("job_id")},
        created_from_job=change.get("job_id"),
    ))
    return {"status": "saved", "change_request_id": change_request_id, "skill": skill}


@router.post("/api/workbench/config-change-requests/{change_request_id}/save-experience")
def save_workbench_change_request_experience(change_request_id: str, req: ApplyChangeRequest) -> dict[str, Any]:
    return save_change_request_experience(change_request_id, req)


# --- Skills ---

def _next_skill_version(cur, category: str, name: str) -> str:
    rows = fetch_all(cur, "SELECT version FROM skills WHERE category = %s AND name = %s", (category, name))
    max_n = 0
    for row in rows:
        match = re.fullmatch(r"v(\d+)", row["version"])
        if match:
            max_n = max(max_n, int(match.group(1)))
    return f"v{max_n + 1}"


def _publish_skill(req: SkillPublishRequest) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            version = req.version or _next_skill_version(cur, req.category, req.name)
            skill_id = new_id("skill")
            # 路径加入 skill_id 兜底，避免不同经验在 slug(name) 折叠（如纯中文名）后 S3 路径冲突互相覆盖。
            prefix = f"skills/{slug(req.category) or 'misc'}/{slug(req.name) or 'skill'}-{skill_id}/{version}"
            now = utc_now_iso()
            content = req.content or f"# {req.name}\n\nCategory: {req.category}\n\nLocal MVP placeholder skill.\n"
            manifest = {"name": req.name, "version": version, "category": req.category, "vendor": req.vendor, "tags": req.tags, "entrypoint": "SKILL.md", "created_from_job": req.created_from_job, "created_at": now, "status": "active", "applies_to": req.applies_to, "source": req.source or "agent", **req.manifest}
            skill_uri = artifacts.put_text(f"{prefix}/SKILL.md", content, "text/markdown; charset=utf-8")
            manifest_uri = artifacts.put_json(f"{prefix}/manifest.json", manifest)
            latest_uri = artifacts.put_json(f"skills/{slug(req.category)}/{slug(req.name)}/latest.json", {"version": version, "manifest": manifest_uri, "skill": skill_uri, "updated_at": now})
            cur.execute(
                "INSERT INTO skills (id, category, name, version, vendor, status, tags, manifest, s3_prefix, created_from_job) VALUES (%s, %s, %s, %s, %s, 'active', %s, %s, %s, %s)",
                (skill_id, req.category, req.name, version, req.vendor, psycopg2.extras.Json(req.tags), psycopg2.extras.Json({**manifest, "uris": {"skill": skill_uri, "manifest": manifest_uri, "latest": latest_uri}}), artifacts.uri_for_prefix(prefix), req.created_from_job),
            )
    return {"id": skill_id, "category": req.category, "name": req.name, "version": version, "s3_prefix": artifacts.uri_for_prefix(prefix), "uris": {"skill": skill_uri, "manifest": manifest_uri, "latest": latest_uri}}


@router.get("/api/skills")
def list_skills() -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rows = fetch_all(cur, "SELECT * FROM skills ORDER BY created_at DESC LIMIT 100")
    return {"items": rows}


@router.post("/api/skills/publish")
def publish_skill(req: SkillPublishRequest) -> dict[str, Any]:
    return _publish_skill(req)


@router.post("/api/workbench/skills/publish")
def publish_workbench_skill(payload: dict[str, Any]) -> dict[str, Any]:
    category = payload.get("category") or payload.get("family") or "misc"
    result = _publish_skill(SkillPublishRequest(
        category=category, name=payload["name"], version=payload.get("version"),
        vendor=payload.get("vendor", "*"), tags=payload.get("tags", []),
        content=payload.get("content"),
        manifest={k: v for k, v in payload.items() if k not in {"content", "tags"}},
        created_from_job=payload.get("created_from_job") or payload.get("source_job_id"),
    ))
    return {"status": "published", "skill": result, **result}


def _skill_row_content(row: dict[str, Any]) -> str:
    manifest = row.get("manifest") or {}
    uri = (manifest.get("uris") or {}).get("skill")
    if not uri:
        prefix = str(row.get("s3_prefix") or "").rstrip("/")
        uri = f"{prefix}/SKILL.md" if prefix else None
    if not uri:
        return ""
    try:
        return artifacts.get_bytes(uri).decode("utf-8")
    except Exception:
        return ""


@router.post("/api/skills")
def create_skill(req: SkillCreateRequest) -> dict[str, Any]:
    """人工手动沉淀经验（写入 skills 知识库）。"""
    result = _publish_skill(SkillPublishRequest(
        category=req.category, name=req.name, vendor=req.vendor, tags=req.tags,
        content=req.content, applies_to=req.applies_to, source=req.source or "manual",
    ))
    return {"status": "created", "skill": result, **result}


@router.get("/api/skills/preview")
def preview_skills(vendor: str | None = None, bill_type: str | None = None, month: str | None = None, excluded: str | None = None) -> dict[str, Any]:
    """预览：在给定会话上下文下会注入哪些经验/技能（按相关性排序）。"""
    excluded_ids = [item for item in (excluded or "").split(",") if item.strip()]
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            items = active_skills_for_context(
                cur, vendor=vendor, bill_type=bill_type, month=month,
                excluded_ids=excluded_ids, with_content=False,
            )
    return {"items": items}


@router.get("/api/skills/{skill_id}")
def get_skill(skill_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            row = fetch_one(cur, "SELECT * FROM skills WHERE id = %s", (skill_id,))
    if not row:
        raise HTTPException(status_code=404, detail="skill not found")
    row["content"] = _skill_row_content(row)
    return row


@router.put("/api/skills/{skill_id}")
def update_skill(skill_id: str, req: SkillEditRequest) -> dict[str, Any]:
    """就地编辑经验/技能（同版本覆盖 SKILL.md 与 manifest）。"""
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            row = fetch_one(cur, "SELECT * FROM skills WHERE id = %s", (skill_id,))
            if not row:
                raise HTTPException(status_code=404, detail="skill not found")
            manifest = dict(row.get("manifest") or {})
            name = req.name if req.name is not None else row["name"]
            vendor = req.vendor if req.vendor is not None else row["vendor"]
            tags = req.tags if req.tags is not None else (row.get("tags") or [])
            if req.applies_to is not None:
                manifest["applies_to"] = req.applies_to
            manifest.update({"name": name, "vendor": vendor, "tags": tags, "updated_at": utc_now_iso()})
            # 与 _publish_skill 保持一致的路径，确保编辑就地覆盖同一份 SKILL.md / manifest.json。
            prefix = f"skills/{slug(row['category']) or 'misc'}/{slug(row['name']) or 'skill'}-{row['id']}/{row['version']}"
            content = req.content if req.content is not None else _skill_row_content(row)
            skill_uri = artifacts.put_text(f"{prefix}/SKILL.md", content, "text/markdown; charset=utf-8")
            manifest_uri = artifacts.put_json(f"{prefix}/manifest.json", manifest)
            manifest["uris"] = {**(manifest.get("uris") or {}), "skill": skill_uri, "manifest": manifest_uri}
            cur.execute(
                "UPDATE skills SET name = %s, vendor = %s, tags = %s, manifest = %s WHERE id = %s",
                (name, vendor, psycopg2.extras.Json(tags), psycopg2.extras.Json(manifest), skill_id),
            )
    return {"status": "updated", "id": skill_id}


@router.patch("/api/skills/{skill_id}")
def set_skill_status(skill_id: str, req: SkillStatusRequest) -> dict[str, Any]:
    status = (req.status or "").strip().lower()
    if status not in {"active", "disabled"}:
        raise HTTPException(status_code=400, detail="status must be 'active' or 'disabled'")
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("UPDATE skills SET status = %s WHERE id = %s", (status, skill_id))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="skill not found")
    return {"status": status, "id": skill_id}


@router.delete("/api/skills/{skill_id}")
def delete_skill(skill_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("DELETE FROM skills WHERE id = %s", (skill_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="skill not found")
    return {"status": "deleted", "id": skill_id}
