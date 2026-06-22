"""Agent 会话与流式输出业务逻辑。"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import psycopg2.extras
from fastapi import HTTPException

from ..runner import PersistentSession, send_message
from ..runner import config as runner_config
from .artifacts import artifacts
from .core import (
    content_type_for_filename,
    db_conn,
    dumps_json,
    ensure_agent_session,
    fetch_all,
    fetch_one,
    insert_agent_event,
    json_safe,
    new_id,
    normalize_reference_ids,
    public_job,
    slug,
    uri_to_prefix,
    utc_now,
)


def zhipu_codingplan_endpoint() -> str:
    return os.getenv("ZHIPU_CODINGPLAN_ENDPOINT", "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions")


def experience_context_for_sessions(cur, session_ids: list[str]) -> list[dict[str, Any]]:
    """已弃用：经验已统一为 Skills 知识库并自动注入（见 active_skills_for_context）。

    保留函数签名仅为兼容旧调用，不再被会话创建流程使用。
    """
    if not session_ids:
        return []
    rows = fetch_all(
        cur,
        """
        SELECT id, prompt, status, updated_at, created_at
        FROM agent_sessions
        WHERE id = ANY(%s)
        ORDER BY updated_at DESC
        LIMIT 12
        """,
        (session_ids,),
    )
    events = fetch_all(
        cur,
        """
        SELECT DISTINCT ON (session_id) session_id, content, event_type, created_at
        FROM agent_events
        WHERE session_id = ANY(%s)
          AND content <> ''
          AND event_type IN ('assistant.delta', 'run.completed', 'operator.message.received')
        ORDER BY session_id, seq DESC
        """,
        (session_ids,),
    )
    latest_by_session = {event["session_id"]: event for event in events}
    return [
        {
            "id": row["id"],
            "prompt": row.get("prompt") or "",
            "status": row.get("status"),
            "updated_at": row.get("updated_at"),
            "latest": (latest_by_session.get(row["id"]) or {}).get("content") or "",
        }
        for row in rows
    ]


def format_experience_reference_content(experiences: list[dict[str, Any]]) -> str:
    if not experiences:
        return "未引用历史经验。"
    lines = ["参考历史经验："]
    for index, item in enumerate(experiences, start=1):
        prompt = str(item.get("prompt") or "").strip().replace("\n", " ")[:140]
        latest = str(item.get("latest") or "").strip().replace("\n", " ")[:180]
        lines.append(f"{index}. {item['id']}：{prompt}")
        if latest:
            lines.append(f"   结论：{latest}")
    return "\n".join(lines)


def _skill_version_num(version: Any) -> int:
    match = re.fullmatch(r"v(\d+)", str(version or ""))
    return int(match.group(1)) if match else 0


def _skill_content_uri(row: dict[str, Any]) -> str | None:
    manifest = row.get("manifest") or {}
    uri = ((manifest.get("uris") or {}).get("skill"))
    if uri:
        return str(uri)
    prefix = str(row.get("s3_prefix") or "").rstrip("/")
    return f"{prefix}/SKILL.md" if prefix else None


def _latest_active_skill_rows(cur) -> list[dict[str, Any]]:
    """取所有 active 技能，并按 (category, name) 折叠到最高版本。"""
    rows = fetch_all(cur, "SELECT * FROM skills WHERE status = 'active' ORDER BY created_at DESC LIMIT 500")
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["category"], row["name"])
        current = latest.get(key)
        if current is None or _skill_version_num(row["version"]) > _skill_version_num(current["version"]):
            latest[key] = row
    return list(latest.values())


def skill_relevance_score(row: dict[str, Any], vendor: Any, bill_type: Any, month: Any) -> int:
    """相关性打分（分数越高越靠前）。

    按既定方案「默认注入所有启用技能、相关性只决定优先级」：所有 active 技能都会被
    注入（base=1），供应商 / 账单类型 / 关键词命中只是加分，不做硬性排除；会话需要时
    通过 excluded_skill_ids 手动排除个别技能。
    """
    manifest = row.get("manifest") or {}
    applies = manifest.get("applies_to") if isinstance(manifest.get("applies_to"), dict) else {}
    score = 1

    skill_vendor = str(row.get("vendor") or "*").strip()
    want_vendor = str(vendor or "").strip()
    if skill_vendor == "*":
        score += 1  # 全局技能，普遍适用
    elif skill_vendor and want_vendor:
        a, b = skill_vendor.lower(), want_vendor.lower()
        if a == b:
            score += 5
        elif a in b or b in a:
            score += 3  # 关联供应商，如 1001AI ⊂ 1001AI-Claude

    bill_types = applies.get("bill_type") or applies.get("bill_types") or []
    if isinstance(bill_types, str):
        bill_types = [bill_types]
    bill_types = [str(item).strip().lower() for item in bill_types if str(item).strip()]
    want_bill = str(bill_type or "").strip().lower()
    if bill_types and "all" not in bill_types and want_bill and want_bill in bill_types:
        score += 3

    keywords = [str(item).lower() for item in (applies.get("keywords") or [])]
    tags = [str(item).lower() for item in (row.get("tags") or [])]
    haystack = " ".join(str(value or "").lower() for value in (vendor, bill_type, month))
    if haystack.strip():
        for token in set(keywords + tags):
            if token and token in haystack:
                score += 1
    return score


def active_skills_for_context(
    cur,
    *,
    vendor: Any = None,
    bill_type: Any = None,
    month: Any = None,
    excluded_ids: list[str] | None = None,
    limit: int = 20,
    with_content: bool = True,
) -> list[dict[str, Any]]:
    """挑选要注入对账 Agent 的技能：active + 相关性匹配，按分数排序取前 limit。"""
    excluded = {str(item) for item in (excluded_ids or [])}
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in _latest_active_skill_rows(cur):
        if str(row["id"]) in excluded:
            continue
        score = skill_relevance_score(row, vendor, bill_type, month)
        scored.append((score, row))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("name") or "")))

    entries: list[dict[str, Any]] = []
    for score, row in scored[:limit]:
        entry: dict[str, Any] = {
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "version": row["version"],
            "vendor": row.get("vendor"),
            "tags": row.get("tags") or [],
            "score": score,
            "path": f"{slug(row['category'])}/{slug(row['name'])}/SKILL.md",
        }
        if with_content:
            uri = _skill_content_uri(row)
            try:
                entry["content"] = artifacts.get_bytes(uri).decode("utf-8") if uri else ""
            except Exception:
                continue  # 内容读取失败则跳过，避免注入空技能
        entries.append(entry)
    return entries


def build_agent_instructions(job: dict[str, Any], month: Any, vendor: Any, channel_id: Any) -> str:
    job_type = job.get("type") or "agent_conversation"
    payload = job.get("request_payload") if isinstance(job.get("request_payload"), dict) else {}
    prompt = payload.get("prompt") or payload.get("reason") or ""
    return "\n".join(
        [
            "# Agent Workbench 任务说明",
            "",
            f"- 任务类型：{job_type}",
            f"- 账期：{month or '未知'}",
            f"- 供应商：{vendor or '未知'}",
            f"- 渠道：{channel_id if channel_id is not None else '未知'}",
            "",
            "## 你的目标",
            prompt or "读取 input/ 下的账单结果、供应商资料与计费口径，核对差异并给出可处理建议。",
            "",
            "## 对账基准",
            "- 所有对账均基于刊例价进行。",
            "- 折扣只用于差异解释、影响测算或处理建议，不改变对账基准。",
            "",
            "## 可读上下文（input/）",
            "- job.json：任务元信息",
            "- billing_summary.json：本次账单结果摘要",
            "- config/pricing.json、config/discounts.json：本次计费口径快照",
            "- 其余文件：用户上传的供应商账单等资料",
            "",
            "## 产物契约（写入 output/）",
            "- report.md：调查报告",
            "- result.json：结构化结论（含 impact 影响金额、建议动作、结果文件）",
            "- config_change_request.json：配置变更建议（不要直接修改生产配置）",
            "- skill_draft/SKILL.md：可沉淀的经验",
            "- 证据文件（如 diff.csv、anomalies.csv）",
            "",
            "## 权限边界",
            "- 允许：读账单/供应商资料、查 Athena（只读）、写报告/建议/skill 草稿。",
            "- 禁止：写生产账务表、发布正式账单、改线上折扣、操作 Docker。",
            "",
        ]
    )


def build_agent_context(cur, job: dict[str, Any]) -> dict[str, Any]:
    from .config import get_latest_config, normalize_config_row

    payload = job.get("request_payload") if isinstance(job.get("request_payload"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    month = job.get("month") or payload.get("month") or metadata.get("month")
    vendor = job.get("vendor") or payload.get("vendor") or metadata.get("vendor")
    channel_id = job.get("channel_id") or payload.get("channel_id") or metadata.get("channel_id")
    bill_type = payload.get("bill_type") or metadata.get("bill_type")
    excluded_skill_ids = normalize_reference_ids(metadata.get("excluded_skill_ids"))

    billing_run_id = (
        payload.get("our_billing_run_id")
        or payload.get("billing_run_id")
        or metadata.get("billing_run_id")
        or job.get("billing_run_id")
    )
    billing_summary: dict[str, Any] | None = None
    config_row: dict[str, Any] | None = None
    if billing_run_id:
        run = fetch_one(cur, "SELECT * FROM billing_runs WHERE id = %s", (billing_run_id,))
        if run:
            billing_summary = run.get("summary") or {}
            if run.get("config_version_id"):
                config_row = fetch_one(cur, "SELECT * FROM billing_config_versions WHERE id = %s", (run["config_version_id"],))
    if config_row is None:
        try:
            config_row = get_latest_config(cur)
        except HTTPException:
            config_row = None
    config_row = normalize_config_row(config_row) if config_row else None
    pricing = config_row.get("pricing_snapshot") if config_row else {}
    discounts = config_row.get("discounts_snapshot") if config_row else {}

    supplier_files: list[dict[str, Any]] = []
    files = fetch_all(
        cur,
        "SELECT * FROM uploaded_files WHERE job_id = %s AND category <> 'billing-result' ORDER BY created_at DESC LIMIT 50",
        (job["id"],),
    )
    for file in files:
        try:
            data = artifacts.get_bytes(str(file["s3_uri"]))
        except Exception:
            continue
        supplier_files.append({"filename": file["filename"], "data": data, "category": file["category"]})

    return {
        "job": public_job(job),
        "instructions": build_agent_instructions(job, month, vendor, channel_id),
        "billing_summary": billing_summary if billing_summary is not None else {"month": month, "vendor": vendor, "channel_id": channel_id},
        "pricing": pricing or {},
        "discounts": discounts or {},
        "supplier_files": supplier_files,
        "experiences": [],
        "skills": active_skills_for_context(cur, vendor=vendor, bill_type=bill_type, month=month, excluded_ids=excluded_skill_ids),
        "_meta": {"month": month, "vendor": vendor, "channel_id": channel_id, "billing_run_id": billing_run_id, "config_version_id": (config_row or {}).get("id")},
    }


def ingest_change_request(cur, job: dict[str, Any], execution, context: dict[str, Any], artifact_uris: dict[str, str]) -> str | None:
    ccr_path = execution.output_dir / "config_change_request.json"
    if not ccr_path.exists():
        return None
    try:
        payload = json.loads(ccr_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None

    change_request_id = new_id("cr")
    impact = payload.get("impact_summary") or payload.get("impact") or {}
    reason = payload.get("reason") or "Agent 对账建议"
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
    evidence_links = [{"name": Path(str(item)).name, "ref": item} for item in evidence]
    for role in ("report", "config_change_request", "result"):
        uri = artifact_uris.get(role)
        if uri:
            evidence_links.append({"name": Path(uri).name, "ref": uri, "s3_uri": uri})
    before_config = {"pricing": context.get("pricing") or {}, "discounts": context.get("discounts") or {}}
    after_config = {
        "pricing": payload.get("pricing_json") or payload.get("after_pricing") or {},
        "discounts": payload.get("discounts_json") or payload.get("after_discounts") or {},
    }
    cur.execute(
        """
        INSERT INTO config_change_requests (
            id, type, status, proposed_by, job_id, reason, change_payload_json,
            impact_summary_json, evidence_json, before_config_json, after_config_json
        )
        VALUES (%s, %s, 'open', 'agent', %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            change_request_id,
            payload.get("type", "discount"),
            job["id"],
            reason,
            psycopg2.extras.Json(payload),
            psycopg2.extras.Json(impact),
            psycopg2.extras.Json(evidence_links),
            psycopg2.extras.Json(before_config),
            psycopg2.extras.Json(after_config),
        ),
    )
    return change_request_id


def sse(event: dict[str, Any]) -> str:
    event_name = str(event.get("event_type") or "message").replace("\n", " ")
    data = json.dumps(json_safe(event), ensure_ascii=False)
    return f"event: {event_name}\ndata: {data}\n\n"


def recent_agent_messages(cur, session_id: str) -> list[dict[str, str]]:
    rows = fetch_all(
        cur,
        """
        SELECT role, content FROM agent_events
        WHERE session_id = %s AND event_type IN ('message', 'experience.reference', 'file.reference')
        ORDER BY seq ASC
        """,
        (session_id,),
    )
    return [{"role": row.get("role") or "user", "content": row.get("content") or ""} for row in rows]


def conversation_turns_from_events(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build durable conversation history for Human-in-Loop sandbox handoff."""
    turns: list[dict[str, str]] = []
    for event in events:
        event_type = str(event.get("event_type") or "")
        content = str(event.get("content") or "").strip()
        if not content:
            continue
        role = str(event.get("role") or "").lower()
        if event_type == "message":
            turns.append({"role": "user" if role in {"user", "operator"} else role or "user", "content": content})
        elif event_type == "assistant.delta":
            turns.append({"role": "assistant", "content": content})
        elif event_type == "human.input.waiting":
            turns.append({"role": "assistant", "content": content})
        elif event_type == "file.reference":
            turns.append({"role": "system", "content": content})
    return turns


def conversation_turns_for_session(cur, session_id: str) -> list[dict[str, str]]:
    events = fetch_all(
        cur,
        """
        SELECT event_type, role, content, payload, seq FROM agent_events
        WHERE session_id = %s
          AND event_type IN ('message', 'assistant.delta', 'human.input.waiting', 'file.reference')
        ORDER BY seq ASC
        LIMIT 500
        """,
        (session_id,),
    )
    return conversation_turns_from_events(events)


def latest_user_message(cur, session_id: str) -> str:
    rows = fetch_all(
        cur,
        """
        SELECT content FROM agent_events
        WHERE session_id = %s AND event_type = 'message' AND role = 'user'
        ORDER BY CASE WHEN payload->>'source' = 'operator' THEN 0 ELSE 1 END, seq DESC
        LIMIT 1
        """,
        (session_id,),
    )
    if not rows:
        return ""
    return rows[0].get("content") or ""


def restore_persistent_session(session: dict[str, Any]) -> PersistentSession | None:
    sandbox_id = session.get("sandbox_id")
    metadata = session.get("metadata") or {}
    sandbox_meta = metadata.get("sandbox") if isinstance(metadata.get("sandbox"), dict) else {}
    workdir_raw = sandbox_meta.get("workdir") or metadata.get("sandbox_workdir")
    if not sandbox_id or not workdir_raw:
        return None
    workdir = Path(str(workdir_raw))
    dirs = {"input": workdir / "input", "skills": workdir / "skills", "output": workdir / "output"}
    return PersistentSession(
        sandbox_id=str(sandbox_id),
        workdir=workdir,
        dirs=dirs,
        context={"job": {"id": session.get("id"), "type": "agent_session"}},
    )


def _reference_run_segment(uri: str) -> str:
    """从 s3 uri 提取 run-xxx / job-xxx 区段用于分组，避免不同账单的同名文件互相覆盖。"""
    match = re.search(r"/(run-[0-9a-zA-Z]+)/", uri) or re.search(r"/(job-[0-9a-zA-Z]+)/", uri)
    if match:
        return match.group(1)
    return "ref"


def session_reference_input_files(
    session_id: str, *, max_files: int = 40, max_bytes: int = 6_000_000
) -> list[dict[str, Any]]:
    """收集会话引用/上传的资料并下载字节，供注入沙箱 input/，让对账 Agent 真正读到数据。

    数据来源与 /history 接口一致：
    - agent_file_references：显式引用的资料（如账单产物 summary.json / xlsx）；
    - uploaded_files.session_id：随会话上传的资料（如供应商账单 Excel）。
    账单产物分组到 ``reference_bills/<run>/<filename>``，上传资料放到 ``supplier/<filename>``，
    避免不同来源的同名文件冲突。
    """
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 最新引用优先：持久会话会累积多轮引用，max_files 截断时必须保证
            # “本轮刚引用的账单产物（含 generated/bill_summary.json 逐模型明细、xlsx）”
            # 先注入，否则历史旧账单（如早期 fixture run）会挤占名额、明细被截断。
            referenced = fetch_all(
                cur,
                """
                SELECT uf.*, 'reference' AS _origin FROM agent_file_references afr
                JOIN uploaded_files uf ON uf.id = afr.file_id
                WHERE afr.session_id = %s ORDER BY afr.created_at DESC
                """,
                (session_id,),
            )
            uploaded = fetch_all(
                cur,
                "SELECT *, 'upload' AS _origin FROM uploaded_files WHERE session_id = %s ORDER BY created_at DESC",
                (session_id,),
            )
    seen_ids: set[str] = set()
    out: list[dict[str, Any]] = []
    # 上传的供应商资料优先，其次是引用的账单产物。
    for row in [*uploaded, *referenced]:
        file_id = row.get("id")
        if file_id in seen_ids:
            continue
        seen_ids.add(file_id)
        uri = str(row.get("s3_uri") or "")
        filename = str(row.get("filename") or "file")
        category = str(row.get("category") or "")
        if not uri:
            continue
        try:
            data = artifacts.get_bytes(uri)
        except Exception:
            continue
        if len(data) > max_bytes:
            data = data[:max_bytes]
        if category == "billing-result" or row.get("_origin") == "reference":
            rel = f"reference_bills/{_reference_run_segment(uri)}/{filename}"
        else:
            rel = f"supplier/{filename}"
        base_rel = rel
        suffix = 1
        while any(item["path"] == rel for item in out):
            stem, dot, ext = base_rel.rpartition(".")
            rel = f"{stem}_{suffix}{dot}{ext}" if dot else f"{base_rel}_{suffix}"
            suffix += 1
        out.append({"path": rel, "data": data, "filename": filename, "category": category})
        if len(out) >= max_files:
            break

    if out:
        lines = ["# 本次对账可用资料（已注入 input/ 目录）", ""]
        suppliers = [item for item in out if item["path"].startswith("supplier/")]
        bills = [item for item in out if item["path"].startswith("reference_bills/")]
        if suppliers:
            lines.append("## 供应商/上传资料")
            lines.extend(f"- input/{item['path']}（{item['filename']}）" for item in suppliers)
            lines.append("")
        if bills:
            lines.append("## 内部账单产物（用于对照）")
            lines.extend(f"- input/{item['path']}（{item['filename']}，{item['category']}）" for item in bills)
            lines.append("")
        index = "\n".join(lines).strip() + "\n"
        out.append(
            {"path": "reference_index.md", "data": index.encode("utf-8"), "filename": "reference_index.md", "category": "index"}
        )
    return out


def collecting_agent_event_sink(session_id: str, emitted: list[dict[str, Any]]):
    def sink(event_type: str, role: str, content: str, payload: dict[str, Any] | None = None) -> None:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                event = insert_agent_event(cur, session_id, event_type, role, content, payload or {})
                emitted.append(event)

    return sink


def agent_sse_generator(session_id: str, live: bool = False):
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            session = ensure_agent_session(cur, session_id)
            cur.execute("UPDATE agent_sessions SET status = 'RUNNING', updated_at = NOW() WHERE id = %s", (session_id,))
            start_event = insert_agent_event(
                cur,
                session_id,
                "run.started",
                "system",
                "Agent stream started.",
                {"live": live, "provider": session["provider"], "runtime": session["runtime"]},
            )
            last_seen_seq = int(start_event["seq"])
            messages = recent_agent_messages(cur, session_id)
            latest_message = latest_user_message(cur, session_id)
            conversation_turns = conversation_turns_for_session(cur, session_id)
    yield sse(start_event)

    sandbox_id = session.get("sandbox_id")
    if sandbox_id and runner_config.sandbox_configured():
        yield from stream_sandbox_agent_session(session, latest_message, last_seen_seq, conversation_turns)
    elif live and os.getenv("ZHIPU_CODINGPLAN_API_KEY"):
        yield from stream_zhipu_codingplan(session_id, messages, last_seen_seq)
    else:
        yield from stream_mock_codingplan(session_id, last_seen_seq)


def stream_sandbox_agent_session(
    session: dict[str, Any],
    latest_message: str,
    last_seen_seq: int,
    conversation_turns: list[dict[str, str]] | None = None,
):
    session_id = session["id"]
    persistent = restore_persistent_session(session)
    if persistent is None:
        yield from stream_agent_error(session_id, "沙箱会话缺少 workdir，无法恢复执行。")
        return
    message = (latest_message or session.get("prompt") or "请继续当前对账任务。").strip()
    emitted: list[dict[str, Any]] = []
    try:
        extra_input_files = session_reference_input_files(session_id)
    except Exception:
        extra_input_files = []
    if extra_input_files:
        injected = [item for item in extra_input_files if item.get("category") != "index"]
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                insert_agent_event(
                    cur,
                    session_id,
                    "context.injected",
                    "system",
                    f"已将 {len(injected)} 份资料注入沙箱 input/ 供对账核对。",
                    {"files": [{"path": item["path"], "filename": item["filename"], "category": item["category"]} for item in injected]},
                )
    thread = threading.Thread(
        target=run_sandbox_agent_session_worker,
        args=(session_id, persistent, message, extra_input_files, conversation_turns),
        name=f"agent-session-{session_id}",
        daemon=True,
    )
    thread.start()
    yield from stream_agent_events_tail(
        session_id,
        last_seen_seq,
        max_wait_seconds=runner_config.agent_exec_timeout_seconds() + 180,
        complete_on_timeout=False,
    )
    return
    try:
        result = send_message(
            persistent,
            message,
            event_sink=collecting_agent_event_sink(session_id, emitted),
            extra_input_files=extra_input_files,
            conversation_turns=conversation_turns,
        )
    except Exception as exc:
        yield from stream_agent_error(session_id, f"沙箱执行失败：{exc}")
        return

    result_json = result.result_json or {}
    summary = str(result_json.get("summary") or "").strip()
    if not summary and result.stdout:
        summary = result.stdout[-1200:].strip()
    if not summary:
        summary = "沙箱执行完成，未生成摘要。"

    workbench_meta = result_json.get("_workbench") if isinstance(result_json.get("_workbench"), dict) else {}
    assistant_event = None
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not workbench_meta.get("assistant_events_emitted"):
                assistant_event = insert_agent_event(
                    cur,
                    session_id,
                    "assistant.delta",
                    "assistant",
                    summary,
                    {"mode": result.mode, "sandbox_id": result.sandbox_id, "result": result_json},
                )
            if result.succeeded:
                done = insert_agent_event(
                    cur,
                    session_id,
                    "run.completed",
                    "system",
                    "沙箱 Agent 执行完成。",
                    {
                        "mode": result.mode,
                        "sandbox_id": result.sandbox_id,
                        "output_files": [rel for rel, _ in result.output_files],
                        "result": result_json,
                    },
                )
                # 结论回填到会话 metadata.result，前端结论卡片在 /result 不存在时据此渲染。
                session_row = fetch_one(cur, "SELECT metadata FROM agent_sessions WHERE id = %s", (session_id,))
                session_metadata = dict((session_row or {}).get("metadata") or {})
                session_metadata["result"] = result_json
                cur.execute(
                    "UPDATE agent_sessions SET status = 'COMPLETED', metadata = %s, updated_at = NOW() WHERE id = %s",
                    (psycopg2.extras.Json(json_safe(session_metadata)), session_id),
                )
                final_event = done
            else:
                final_event = insert_agent_event(
                    cur,
                    session_id,
                    "run.error",
                    "system",
                    (result.stderr or summary or "沙箱 Agent 返回非零退出码。")[:2000],
                    {"mode": result.mode, "sandbox_id": result.sandbox_id, "returncode": result.returncode, "result": result_json},
                )
                cur.execute("UPDATE agent_sessions SET status = 'FAILED', updated_at = NOW() WHERE id = %s", (session_id,))
    replay_events = [*emitted]
    if assistant_event is not None:
        replay_events.append(assistant_event)
    replay_events.append(final_event)
    for event in sorted(replay_events, key=lambda item: int(item.get("seq") or 0)):
        if int(event.get("seq") or 0) > last_seen_seq:
            yield sse(event)
            last_seen_seq = int(event.get("seq") or last_seen_seq)


def run_sandbox_agent_session_worker(
    session_id: str,
    persistent: PersistentSession,
    message: str,
    extra_input_files: list[dict[str, Any]],
    conversation_turns: list[dict[str, str]] | None,
) -> None:
    emitted: list[dict[str, Any]] = []
    try:
        result = send_message(
            persistent,
            message,
            event_sink=collecting_agent_event_sink(session_id, emitted),
            extra_input_files=extra_input_files,
            conversation_turns=conversation_turns,
        )
    except Exception as exc:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                insert_agent_event(cur, session_id, "run.error", "system", f"沙箱执行失败：{exc}", {"error": str(exc)})
                cur.execute("UPDATE agent_sessions SET status = 'FAILED', updated_at = NOW() WHERE id = %s", (session_id,))
        return

    persist_sandbox_agent_result(session_id, result)


def persist_sandbox_agent_result(session_id: str, result: Any) -> None:
    result_json = result.result_json or {}
    summary = str(result_json.get("summary") or "").strip()
    if not summary and result.stdout:
        summary = result.stdout[-1200:].strip()
    if not summary:
        summary = "沙箱执行完成，未生成摘要。"

    workbench_meta = result_json.get("_workbench") if isinstance(result_json.get("_workbench"), dict) else {}
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not workbench_meta.get("assistant_events_emitted"):
                insert_agent_event(
                    cur,
                    session_id,
                    "assistant.delta",
                    "assistant",
                    summary,
                    {"mode": result.mode, "sandbox_id": result.sandbox_id, "result": result_json},
                )
            if result.succeeded:
                done = insert_agent_event(
                    cur,
                    session_id,
                    "run.completed",
                    "system",
                    "沙箱 Agent 执行完成。",
                    {
                        "mode": result.mode,
                        "sandbox_id": result.sandbox_id,
                        "output_files": [rel for rel, _ in result.output_files],
                        "result": result_json,
                    },
                )
                session_row = fetch_one(cur, "SELECT metadata FROM agent_sessions WHERE id = %s", (session_id,))
                session_metadata = dict((session_row or {}).get("metadata") or {})
                session_metadata["result"] = result_json
                cur.execute(
                    "UPDATE agent_sessions SET status = 'COMPLETED', metadata = %s, updated_at = NOW() WHERE id = %s",
                    (psycopg2.extras.Json(json_safe(session_metadata)), session_id),
                )
            else:
                insert_agent_event(
                    cur,
                    session_id,
                    "run.error",
                    "system",
                    (result.stderr or summary or "沙箱 Agent 返回非零退出码。")[:2000],
                    {"mode": result.mode, "sandbox_id": result.sandbox_id, "returncode": result.returncode, "result": result_json},
                )
                cur.execute("UPDATE agent_sessions SET status = 'FAILED', updated_at = NOW() WHERE id = %s", (session_id,))


def stream_agent_events_tail(
    session_id: str,
    last_seen_seq: int,
    max_wait_seconds: int = 120,
    *,
    complete_on_timeout: bool = True,
):
    deadline = time.monotonic() + max_wait_seconds
    while time.monotonic() < deadline:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                events = fetch_all(
                    cur,
                    "SELECT * FROM agent_events WHERE session_id = %s AND seq > %s ORDER BY seq ASC LIMIT 200",
                    (session_id, last_seen_seq),
                )
        for event in events:
            yield sse(event)
            last_seen_seq = max(last_seen_seq, int(event["seq"]))
            if event.get("event_type") in {"run.completed", "run.error"}:
                return
        time.sleep(0.5)
    if not complete_on_timeout:
        return
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            done = insert_agent_event(cur, session_id, "run.completed", "system", "会话流读取超时结束。", {"tail_timeout": True})
    yield sse(done)


def stream_mock_codingplan(session_id: str, last_seen_seq: int):
    steps = [
        {"message": "我已经接入本次对账资料，可以开始核对账单差异。", "tool": None},
        {"message": "我正在查看本次账单、供应商资料和计费口径。", "tool": {"name": "athena.billing_context.load", "title": "读取本次账单背景", "args": {"month": "2026-06", "channel_id": 65, "vendor": "1001AI-Claude"}, "result": {"billing_run_found": True, "files": 1, "config_version": "local-v0"}, "duration_ms": 186}},
        {"message": "我正在核对价格和折扣口径，判断是否需要给出处理建议。", "tool": {"name": "pricing.discounts.inspect", "title": "检查价格和折扣", "args": {"config_version": "local-v0", "models": ["claude-opus-4-6"]}, "result": {"pricing_models": 3, "discount_rules": 2, "needs_review": False}, "duration_ms": 142}},
        {"message": "我已经整理出本轮核验思路：先对比供应商账单，再给出可处理建议。", "tool": {"name": "reconcile.diff.generate", "title": "生成差异摘要", "args": {"match_keys": ["model", "day"], "tolerance_usd": 0.01}, "result": {"diff_rows": 0, "max_delta_usd": 0, "suggestion": "可继续人工复核或保存为经验"}, "duration_ms": 233}},
    ]
    acknowledged_user_events: set[int] = set()
    for index, step in enumerate(steps, start=1):
        time.sleep(0.2)
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                event = insert_agent_event(cur, session_id, "assistant.delta", "assistant", step["message"], {"chunk_index": index, "mock": True})
                tool_call = None
                tool_result = None
                tool = step.get("tool")
                if tool:
                    tool_call = insert_agent_event(cur, session_id, "tool.call", "tool", f"开始检查：{tool['title']}", {"tool_name": tool["name"], "title": tool["title"], "arguments": tool["args"], "status": "running", "mock": True})
                    tool_result = insert_agent_event(cur, session_id, "tool.result", "tool", f"检查完成：{tool['title']}", {"tool_name": tool["name"], "title": tool["title"], "arguments": tool["args"], "result": tool["result"], "status": "completed", "duration_ms": tool["duration_ms"], "mock": True})
                new_messages = fetch_all(cur, "SELECT * FROM agent_events WHERE session_id = %s AND event_type = 'message' AND seq > %s ORDER BY seq ASC", (session_id, last_seen_seq))
        yield sse(event)
        if tool_call:
            yield sse(tool_call)
        if tool_result:
            yield sse(tool_result)
        last_seen_seq = max(last_seen_seq, int(event["seq"]))
        if tool_call:
            last_seen_seq = max(last_seen_seq, int(tool_call["seq"]))
        if tool_result:
            last_seen_seq = max(last_seen_seq, int(tool_result["seq"]))
        for message in new_messages:
            seq = int(message["seq"])
            if seq in acknowledged_user_events:
                continue
            acknowledged_user_events.add(seq)
            with db_conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    ack = insert_agent_event(cur, session_id, "operator.message.received", "system", f"已收到运行中消息：{message['content']}", {"source_seq": seq})
            yield sse(ack)
            last_seen_seq = max(last_seen_seq, seq)

    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            waiting = insert_agent_event(cur, session_id, "human.input.waiting", "system", "我需要你补充供应商账单口径、折扣调整或异常行号，才能继续判断。", {"mock": True, "wait_seconds": 8})
    yield sse(waiting)
    last_seen_seq = max(last_seen_seq, int(waiting["seq"]))

    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        time.sleep(0.5)
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                new_messages = fetch_all(cur, "SELECT * FROM agent_events WHERE session_id = %s AND event_type = 'message' AND seq > %s ORDER BY seq ASC", (session_id, last_seen_seq))
        for message in new_messages:
            seq = int(message["seq"])
            if seq in acknowledged_user_events:
                continue
            acknowledged_user_events.add(seq)
            with db_conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    ack = insert_agent_event(cur, session_id, "operator.message.received", "system", f"已收到补充信息：{message['content']}", {"source_seq": seq, "supplemental_input": True})
                    followup = insert_agent_event(cur, session_id, "assistant.delta", "assistant", "我会把这条补充信息纳入本轮核验，并优先检查对应账单口径与折扣影响。", {"mock": True, "source_seq": seq, "supplemental_input": True})
            yield sse(ack)
            yield sse(followup)
            last_seen_seq = max(last_seen_seq, seq, int(ack["seq"]), int(followup["seq"]))

    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            closing = insert_agent_event(cur, session_id, "assistant.delta", "assistant", "补充信息窗口已结束。本地 mock 流结束，真实模式会持续读取 Agent 的增量回复。", {"mock": True, "supplemental_input": True})
    yield sse(closing)

    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            done = insert_agent_event(cur, session_id, "run.completed", "system", "Agent stream completed.", {"mock": True})
            cur.execute("UPDATE agent_sessions SET status = 'COMPLETED', updated_at = NOW() WHERE id = %s", (session_id,))
    yield sse(done)


def stream_zhipu_codingplan(session_id: str, messages: list[dict[str, str]], last_seen_seq: int):
    api_key = os.getenv("ZHIPU_CODINGPLAN_API_KEY")
    if not api_key:
        yield from stream_mock_codingplan(session_id, last_seen_seq)
        return

    payload = {
        "model": os.getenv("ZHIPU_CODINGPLAN_MODEL", "glm-5.2"),
        "messages": messages,
        "stream": True,
        "temperature": float(os.getenv("ZHIPU_CODINGPLAN_TEMPERATURE", "0.2")),
    }
    request = urllib.request.Request(
        zhipu_codingplan_endpoint(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            for raw in response:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data:"):
                    line = line.removeprefix("data:").strip()
                content = parse_zhipu_stream_content(line)
                if not content:
                    continue
                with db_conn() as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        event = insert_agent_event(cur, session_id, "assistant.delta", "assistant", content, {"live": True})
                yield sse(event)
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                done = insert_agent_event(cur, session_id, "run.completed", "system", "CodingPlan stream completed.", {"live": True})
                cur.execute("UPDATE agent_sessions SET status = 'COMPLETED', updated_at = NOW() WHERE id = %s", (session_id,))
        yield sse(done)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        yield from stream_agent_error(session_id, f"CodingPlan HTTP {exc.code}: {detail}")
    except Exception as exc:
        yield from stream_agent_error(session_id, f"CodingPlan request failed: {exc}")


def parse_zhipu_stream_content(line: str) -> str:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return line
    choices = payload.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    if isinstance(delta.get("content"), str):
        return delta["content"]
    message = choices[0].get("message") or {}
    return message.get("content") if isinstance(message.get("content"), str) else ""


def stream_agent_error(session_id: str, message: str):
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            event = insert_agent_event(cur, session_id, "run.error", "system", message, {})
            cur.execute("UPDATE agent_sessions SET status = 'FAILED', updated_at = NOW() WHERE id = %s", (session_id,))
    yield sse(event)
