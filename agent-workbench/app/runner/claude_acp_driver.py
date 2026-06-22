#!/usr/bin/env python3
"""Run Claude Code through ACP inside an OpenSandbox workspace."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import textwrap
import time
import traceback
from pathlib import Path
from typing import Any


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


WORKSPACE_DIR = Path(env("WORKSPACE_DIR", "/tmp/workspace")).resolve()
INPUT_DIR = Path(env("INPUT_DIR", str(WORKSPACE_DIR / "input"))).resolve()
SKILLS_DIR = Path(env("SKILLS_DIR", str(WORKSPACE_DIR / "skills"))).resolve()
OUTPUT_DIR = Path(env("OUTPUT_DIR", str(WORKSPACE_DIR / "output"))).resolve()

MODEL = env("ZHIPU_CODINGPLAN_MODEL", "glm-5.2")
API_KEY = env("ZHIPU_CODINGPLAN_API_KEY") or env("ANTHROPIC_AUTH_TOKEN") or env("ANTHROPIC_API_KEY")
ANTHROPIC_BASE_URL = env("ZHIPU_CODINGPLAN_ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/anthropic")
TIMEOUT_SECONDS = int(env("RUNNER_AGENT_TIMEOUT_SECONDS", "1200") or "1200")
WORKBENCH_EVENT_PREFIX = "__WORKBENCH_EVENT__"
ACP_MAX_ATTEMPTS = max(1, int(env("ZHIPU_CODINGPLAN_ACP_MAX_ATTEMPTS", "10") or "10"))
ACP_RETRY_BASE_SECONDS = max(0.0, float(env("ZHIPU_CODINGPLAN_ACP_RETRY_BASE_SECONDS", "8") or "8"))
TRANSIENT_ACP_PATTERNS = (
    "API Error: 529",
    "访问量过大",
    "try again in a moment",
    "temporarily overloaded",
    "server-side issue",
)


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return default


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_transient_acp_failure(text: str) -> bool:
    lowered = text.lower()
    return any(pattern.lower() in lowered for pattern in TRANSIENT_ACP_PATTERNS)


def stream_workbench_event(event: dict[str, Any]) -> None:
    line = json.dumps(event, ensure_ascii=False)
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with (OUTPUT_DIR / "live_events.ndjson").open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
    except OSError:
        pass
    print(WORKBENCH_EVENT_PREFIX + line, flush=True)


def iter_workspace_files() -> list[str]:
    files: list[str] = []
    for base in (INPUT_DIR, SKILLS_DIR):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                try:
                    rel = path.relative_to(WORKSPACE_DIR).as_posix()
                except ValueError:
                    rel = path.as_posix()
                files.append(f"{rel} ({path.stat().st_size} bytes)")
    return files


def conversation_text() -> str:
    path = INPUT_DIR / "conversation.jsonl"
    if not path.exists():
        return "(暂无对话历史)"
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines()[-30:]:
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        role = str(item.get("role") or "user")
        content = str(item.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content[:6000]}")
    return "\n".join(lines) or "(暂无对话历史)"


def build_prompt() -> str:
    instructions = read_text(INPUT_DIR / "instructions.md", "请分析当前对账任务，找出差异原因并给出处理建议。")
    file_list = "\n".join(f"- {item}" for item in iter_workspace_files()) or "- (没有发现输入文件)"
    return textwrap.dedent(
        f"""
        你是 Agent Workbench 的对账 Agent，正在 Claude Code + ACP 的真实 sandbox 中执行。
        所有对账均基于刊例价进行；折扣只用于差异解释、影响测算或处理建议，不改变对账基准。

        运行约束：
        - 工作目录是 `{WORKSPACE_DIR.as_posix()}`。
        - 请读取 `input/` 与 `skills/` 下的资料，不要读取或输出任何环境变量、API Key 或凭证。
        - 可以使用 Claude Code 的 Read、LS、Grep、Bash、Write 等工具；不要修改 `input/` 和 `skills/`。
        - 所有面向业务用户的文字都使用中文。

        本轮任务：
        {instructions}

        当前对话：
        {conversation_text()}

        可用资料：
        {file_list}

        请完成以下产物：
        1. 写入 `output/report.md`：中文对账分析报告，包含结论、关键证据、影响金额、建议动作。
        2. 写入 `output/result.json`：必须是 JSON object，字段如下：
           {{
             "status": "completed|needs_info|error",
             "summary": "一句话结论",
             "reason": "差异原因或需要补充的信息",
             "impact": {{"amount_usd_delta": 0, "amount_cny_delta": 0}},
             "recommended_actions": ["建议动作"],
             "saveable_experience": "可沉淀经验，可为空",
             "config_change": null
           }}
        3. 最终回复先给结论，再列关键证据和下一步。不要只说你写了文件。
        """
    ).strip() + "\n"


def configure_claude_environment() -> dict[str, str]:
    home = Path("/tmp/agent-home")
    npm_cache = Path("/tmp/npm-cache")
    npm_prefix = Path("/tmp/npm-prefix")
    claude_dir = home / ".claude"
    for path in (home, npm_cache, npm_prefix, claude_dir):
        path.mkdir(parents=True, exist_ok=True)

    write_json(home / ".claude.json", {"hasCompletedOnboarding": True})
    write_json(
        claude_dir / "settings.json",
        {
            "env": {
                "ANTHROPIC_BASE_URL": ANTHROPIC_BASE_URL,
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": MODEL,
                "ANTHROPIC_DEFAULT_SONNET_MODEL": MODEL,
                "ANTHROPIC_DEFAULT_OPUS_MODEL": MODEL,
                "API_TIMEOUT_MS": "3000000",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "ENABLE_TOOL_SEARCH": "0",
                "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
            },
            "permissions": {"defaultMode": "bypassPermissions"},
        },
    )

    child_env = os.environ.copy()
    child_env.update(
        {
            "HOME": str(home),
            "CLAUDE_CONFIG_DIR": str(claude_dir),
            "NPM_CONFIG_CACHE": str(npm_cache),
            "NPM_CONFIG_PREFIX": str(npm_prefix),
            "PATH": f"{npm_prefix / 'bin'}:{child_env.get('PATH', '')}",
            "ANTHROPIC_AUTH_TOKEN": API_KEY,
            "ANTHROPIC_API_KEY": API_KEY,
            "ANTHROPIC_BASE_URL": ANTHROPIC_BASE_URL,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": MODEL,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": MODEL,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": MODEL,
            "API_TIMEOUT_MS": "3000000",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "ENABLE_TOOL_SEARCH": "0",
            "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
            "DISABLE_TELEMETRY": "1",
        }
    )
    return child_env


def acpx_argv(prompt_file: Path) -> list[str]:
    prefix = [shutil.which("acpx")] if shutil.which("acpx") else ["npx", "-y", "acpx@0.11.0"]
    return [
        *[part for part in prefix if part],
        "--format",
        "json",
        "--json-strict",
        "--approve-all",
        "--cwd",
        WORKSPACE_DIR.as_posix(),
        "--timeout",
        str(max(60, TIMEOUT_SECONDS)),
        "claude",
        "exec",
        "--file",
        prompt_file.as_posix(),
    ]


def content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if value.get("type") == "text" and isinstance(value.get("text"), str):
            return value["text"]
        if value.get("type") == "content":
            return content_text(value.get("content"))
        text = value.get("text") or value.get("message") or value.get("stdout") or value.get("stderr")
        return str(text) if text is not None else ""
    if isinstance(value, list):
        return "\n".join(part for part in (content_text(item) for item in value) if part)
    return ""


ASSISTANT_WORD_BOUNDARY_HINTS = {
    "a",
    "an",
    "and",
    "available",
    "by",
    "card",
    "check",
    "confirming",
    "delta",
    "directory",
    "excel",
    "exploring",
    "files",
    "for",
    "input",
    "inspect",
    "internal",
    "json",
    "key",
    "let",
    "markdown",
    "me",
    "now",
    "parsing",
    "python",
    "rate",
    "reading",
    "reference",
    "rendering",
    "script",
    "start",
    "supplier",
    "table",
    "the",
    "tools",
    "total",
    "value",
    "with",
}


def should_insert_assistant_space(left: str, right: str) -> bool:
    if not left or not right:
        return False
    previous = left[-1]
    first = right[0]
    if previous.isspace() or first.isspace():
        return False
    if previous in "([{/<" or first in ".,;:!?)]}/|":
        return False
    if not (previous.isascii() and first.isascii() and (previous.isalpha() or previous == "'") and first.isalpha()):
        return False
    match = re.match(r"^[A-Za-z]+", right)
    return bool(match and match.group(0).lower() in ASSISTANT_WORD_BOUNDARY_HINTS)


def join_assistant_chunks(chunks: list[str]) -> str:
    output = ""
    for chunk in chunks:
        if not chunk:
            continue
        if should_insert_assistant_space(output, chunk):
            output += " "
        output += chunk
    return output


def tool_name(update: dict[str, Any]) -> str:
    meta = update.get("_meta") if isinstance(update.get("_meta"), dict) else {}
    claude = meta.get("claudeCode") if isinstance(meta.get("claudeCode"), dict) else {}
    return str(claude.get("toolName") or update.get("title") or "claude_code.tool")


def tool_result(update: dict[str, Any]) -> Any:
    meta = update.get("_meta") if isinstance(update.get("_meta"), dict) else {}
    claude = meta.get("claudeCode") if isinstance(meta.get("claudeCode"), dict) else {}
    if "toolResponse" in claude:
        return claude.get("toolResponse")
    if "rawOutput" in update:
        return update.get("rawOutput")
    if "content" in update:
        return update.get("content")
    return {}


def parse_acpx_stdout(stdout: str) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    raw_messages: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    assistant_chunks: list[str] = []
    seen_tool_calls: set[str] = set()

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue
        raw_messages.append(message)
        if message.get("method") != "session/update":
            continue
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        update = params.get("update") if isinstance(params.get("update"), dict) else {}
        tag = update.get("sessionUpdate")

        if tag == "agent_message_chunk":
            text = content_text(update.get("content"))
            if text:
                assistant_chunks.append(text)
        elif tag == "tool_call":
            call_id = str(update.get("toolCallId") or "")
            seen_tool_calls.add(call_id)
            title = str(update.get("title") or tool_name(update))
            events.append(
                {
                    "event_type": "tool.call",
                    "role": "tool",
                    "content": f"调用工具：{title}",
                    "payload": {
                        "tool_name": tool_name(update),
                        "tool_call_id": call_id,
                        "title": title,
                        "kind": update.get("kind"),
                        "status": str(update.get("status") or "running"),
                        "arguments": update.get("rawInput"),
                        "runtime": "acp",
                        "agent": "claude_code",
                    },
                }
            )
        elif tag == "tool_call_update":
            call_id = str(update.get("toolCallId") or "")
            title = str(update.get("title") or tool_name(update))
            if call_id and call_id not in seen_tool_calls:
                events.append(
                    {
                        "event_type": "tool.call",
                        "role": "tool",
                        "content": f"调用工具：{title}",
                        "payload": {
                            "tool_name": tool_name(update),
                            "tool_call_id": call_id,
                            "title": title,
                            "status": "running",
                            "runtime": "acp",
                            "agent": "claude_code",
                        },
                    }
                )
            events.append(
                {
                    "event_type": "tool.result",
                    "role": "tool",
                    "content": f"工具完成：{title}",
                    "payload": {
                        "tool_name": tool_name(update),
                        "tool_call_id": call_id,
                        "title": title,
                        "status": str(update.get("status") or "completed"),
                        "result": tool_result(update),
                        "runtime": "acp",
                        "agent": "claude_code",
                    },
                }
            )
        elif tag == "plan":
            entries = update.get("entries") if isinstance(update.get("entries"), list) else []
            plan_lines = []
            for entry in entries:
                if isinstance(entry, dict) and entry.get("content"):
                    plan_lines.append(f"[{entry.get('status') or 'pending'}] {entry.get('content')}")
            if plan_lines:
                events.append(
                    {
                        "event_type": "assistant.delta",
                        "role": "assistant",
                        "content": "计划更新：\n" + "\n".join(plan_lines),
                        "payload": {"runtime": "acp", "agent": "claude_code", "plan": entries},
                    }
                )

    assistant_text = join_assistant_chunks(assistant_chunks)
    if assistant_text.strip():
        events.append(
            {
                "event_type": "assistant.delta",
                "role": "assistant",
                "content": assistant_text,
                "payload": {
                    "runtime": "acp",
                    "agent": "claude_code",
                    "provider": "bigmodel-anthropic",
                    "chunks": len(assistant_chunks),
                },
            }
        )
    return events, assistant_text, raw_messages


def extract_result_json(text: str) -> dict[str, Any]:
    for match in re.findall(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL):
        try:
            parsed = json.loads(match)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return {
        "status": "completed",
        "summary": first_line[:240] if first_line else "Claude Code 已完成本轮对账分析。",
        "reason": text,
        "impact": {},
        "recommended_actions": ["查看 report.md 与工具执行记录"],
        "saveable_experience": "",
        "config_change": None,
    }


def normalize_result(result: dict[str, Any], assistant_text: str, event_count: int) -> dict[str, Any]:
    result = dict(result)
    result.setdefault("status", "completed")
    if not str(result.get("summary") or "").strip():
        first_line = next((line.strip() for line in assistant_text.splitlines() if line.strip()), "")
        result["summary"] = first_line[:240] if first_line else "Claude Code 已完成本轮对账分析。"
    result.setdefault("reason", assistant_text)
    result.setdefault("impact", {})
    result.setdefault("recommended_actions", ["查看 report.md 与工具执行记录"])
    result["_workbench"] = {
        "runtime": "acp",
        "agent": "claude_code",
        "provider": "bigmodel-anthropic",
        "assistant_events_emitted": True,
        "acp_event_count": event_count,
    }
    return result


def write_event_log(events: list[dict[str, Any]]) -> None:
    with (OUTPUT_DIR / "acp_events.ndjson").open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def write_raw_acp_log(raw_messages: list[dict[str, Any]]) -> None:
    with (OUTPUT_DIR / "acp_raw.ndjson").open("w", encoding="utf-8") as handle:
        for message in raw_messages:
            handle.write(json.dumps(message, ensure_ascii=False) + "\n")


def ensure_report(result: dict[str, Any], assistant_text: str) -> None:
    report_path = OUTPUT_DIR / "report.md"
    if report_path.exists() and report_path.stat().st_size > 0:
        return
    lines = [
        "# 对账 Agent 分析报告",
        "",
        "## 结论",
        str(result.get("summary") or ""),
        "",
        "## 原因",
        str(result.get("reason") or assistant_text or ""),
        "",
        "## 建议动作",
    ]
    for action in result.get("recommended_actions") or []:
        lines.append(f"- {action}")
    write_text(report_path, "\n".join(lines).strip() + "\n")


def write_error_result(message: str, *, events: list[dict[str, Any]] | None = None) -> None:
    error_result = {
        "status": "error",
        "summary": message,
        "reason": message,
        "impact": {},
        "recommended_actions": ["检查 Claude Code / ACP / GLM Coding Plan 配置后重试"],
        "_workbench": {
            "runtime": "acp",
            "agent": "claude_code",
            "provider": "bigmodel-anthropic",
            "assistant_events_emitted": False,
        },
    }
    write_json(OUTPUT_DIR / "result.json", error_result)
    write_text(OUTPUT_DIR / "report.md", f"# 对账 Agent 执行失败\n\n{message}\n")
    write_event_log(events or [])


def run() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    events: list[dict[str, Any]] = [
        {
            "event_type": "tool.call",
            "role": "tool",
            "content": "通过 ACP 连接 Claude Code",
            "payload": {
                "tool_name": "acp.connect",
                "status": "running",
                "runtime": "acp",
                "agent": "claude_code",
                "provider": "bigmodel-anthropic",
                "model": MODEL,
            },
        }
    ]

    stream_workbench_event(events[-1])

    if not API_KEY:
        message = "ZHIPU_CODINGPLAN_API_KEY 未配置，无法通过 Claude Code 连接 GLM Coding Plan。"
        events.append(
            {
                "event_type": "tool.result",
                "role": "tool",
                "content": "ACP 连接失败：缺少 GLM Coding Plan Key",
                "payload": {"tool_name": "acp.connect", "status": "failed", "runtime": "acp"},
            }
        )
        stream_workbench_event(events[-1])
        write_error_result(message, events=events)
        print("[claude_acp_driver] missing GLM Coding Plan key", file=sys.stderr)
        return 1

    prompt_file = INPUT_DIR / "acp_prompt.md"
    write_text(prompt_file, build_prompt())
    child_env = configure_claude_environment()
    argv = acpx_argv(prompt_file)

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    raw_messages: list[dict[str, Any]] = []
    assistant_chunks: list[str] = []
    try:
        process = subprocess.Popen(
            argv,
            cwd=WORKSPACE_DIR,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        def drain_stderr() -> None:
            if process.stderr is None:
                return
            for chunk in process.stderr:
                stderr_chunks.append(chunk)

        stderr_thread = threading.Thread(target=drain_stderr, name="acpx-stderr", daemon=True)
        stderr_thread.start()

        if process.stdout is not None:
            for line in process.stdout:
                stdout_chunks.append(line)
                live_events, assistant_text_chunk, raw = parse_acpx_stdout(line)
                raw_messages.extend(raw)
                if assistant_text_chunk:
                    assistant_chunks.append(assistant_text_chunk)
                for event in live_events:
                    events.append(event)
                    stream_workbench_event(event)

        returncode = process.wait(timeout=max(60, TIMEOUT_SECONDS) + 90)
        stderr_thread.join(timeout=5)
        completed = subprocess.CompletedProcess(argv, returncode, "".join(stdout_chunks), "".join(stderr_chunks))
    except Exception as exc:
        if "process" in locals():
            try:
                process.kill()
            except Exception:
                pass
        message = f"ACP 调用异常：{exc}\n{traceback.format_exc()}"
        events.append(
            {
                "event_type": "tool.result",
                "role": "tool",
                "content": "ACP 连接失败",
                "payload": {"tool_name": "acp.connect", "status": "failed", "runtime": "acp", "error": str(exc)},
            }
        )
        stream_workbench_event(events[-1])
        write_error_result(message, events=events)
        print(f"[claude_acp_driver] error: {exc}", file=sys.stderr)
        return 1

    assistant_text = join_assistant_chunks(assistant_chunks).strip()
    for retry_attempt in range(2, ACP_MAX_ATTEMPTS + 1):
        transient_text = "\n".join([assistant_text, completed.stdout or "", completed.stderr or ""])
        if not is_transient_acp_failure(transient_text):
            break

        wait_seconds = ACP_RETRY_BASE_SECONDS * (retry_attempt - 1)
        events.append(
            {
                "event_type": "tool.result",
                "role": "tool",
                "content": f"ACP 网关临时拥塞，{wait_seconds:.0f} 秒后重试",
                "payload": {
                    "tool_name": "acp.connect",
                    "status": "retrying",
                    "runtime": "acp",
                    "agent": "claude_code",
                    "attempt": retry_attempt - 1,
                    "max_attempts": ACP_MAX_ATTEMPTS,
                    "wait_seconds": wait_seconds,
                    "stderr_tail": (completed.stderr or "")[-2000:],
                },
            }
        )
        stream_workbench_event(events[-1])
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        events.append(
            {
                "event_type": "tool.call",
                "role": "tool",
                "content": f"ACP 临时拥塞后重试（第 {retry_attempt}/{ACP_MAX_ATTEMPTS} 次）",
                "payload": {
                    "tool_name": "acp.connect",
                    "status": "running",
                    "runtime": "acp",
                    "agent": "claude_code",
                    "attempt": retry_attempt,
                    "max_attempts": ACP_MAX_ATTEMPTS,
                },
            }
        )
        stream_workbench_event(events[-1])

        stdout_chunks = []
        stderr_chunks = []
        raw_messages = []
        assistant_chunks = []
        process = None
        try:
            process = subprocess.Popen(
                argv,
                cwd=WORKSPACE_DIR,
                env=child_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            def drain_retry_stderr() -> None:
                if process.stderr is None:
                    return
                for chunk in process.stderr:
                    stderr_chunks.append(chunk)

            stderr_thread = threading.Thread(target=drain_retry_stderr, name="acpx-stderr-retry", daemon=True)
            stderr_thread.start()

            if process.stdout is not None:
                for line in process.stdout:
                    stdout_chunks.append(line)
                    live_events, assistant_text_chunk, raw = parse_acpx_stdout(line)
                    raw_messages.extend(raw)
                    if assistant_text_chunk:
                        assistant_chunks.append(assistant_text_chunk)
                    for event in live_events:
                        events.append(event)
                        stream_workbench_event(event)

            returncode = process.wait(timeout=max(60, TIMEOUT_SECONDS) + 90)
            stderr_thread.join(timeout=5)
            completed = subprocess.CompletedProcess(argv, returncode, "".join(stdout_chunks), "".join(stderr_chunks))
            assistant_text = join_assistant_chunks(assistant_chunks).strip()
        except Exception as exc:
            if process is not None:
                try:
                    process.kill()
                except Exception:
                    pass
            message = f"ACP 重试异常：{exc}\n{traceback.format_exc()}"
            events.append(
                {
                    "event_type": "tool.result",
                    "role": "tool",
                    "content": "ACP 重试失败",
                    "payload": {"tool_name": "acp.connect", "status": "failed", "runtime": "acp", "error": str(exc)},
                }
            )
            stream_workbench_event(events[-1])
            write_error_result(message, events=events)
            print(f"[claude_acp_driver] retry error: {exc}", file=sys.stderr)
            return 1
    events.append(
        {
            "event_type": "tool.result",
            "role": "tool",
            "content": "ACP Claude Code 执行完成" if completed.returncode == 0 else "ACP Claude Code 执行失败",
            "payload": {
                "tool_name": "acp.connect",
                "status": "completed" if completed.returncode == 0 else "failed",
                "runtime": "acp",
                "agent": "claude_code",
                "returncode": completed.returncode,
                "stderr_tail": (completed.stderr or "")[-2000:],
            },
        }
    )
    stream_workbench_event(events[-1])
    write_event_log(events)
    write_raw_acp_log(raw_messages)

    existing_result = None
    result_path = OUTPUT_DIR / "result.json"
    if result_path.exists():
        try:
            existing_result = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing_result = None
    result = existing_result if isinstance(existing_result, dict) else extract_result_json(assistant_text)
    if completed.returncode != 0:
        result["status"] = "error"
        if not assistant_text:
            detail = (completed.stderr or completed.stdout or "ACP Claude Code failed")[-4000:]
            result["summary"] = "ACP Claude Code 执行失败。"
            result["reason"] = detail
    result = normalize_result(result, assistant_text, len(events))
    write_json(result_path, result)
    ensure_report(result, assistant_text)

    if completed.returncode != 0:
        print((completed.stderr or completed.stdout or "ACP Claude Code failed")[-4000:], file=sys.stderr)
    print(f"[claude_acp_driver] done status={result.get('status')} events={len(events)}", file=sys.stderr)
    return int(completed.returncode or 0)


if __name__ == "__main__":
    sys.exit(run())
