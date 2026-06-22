"""Agent 执行编排：本地子进程（无沙箱降级）或 OpenSandbox 真实沙箱。

职责：组装工作目录 -> 执行 agent（fake/codex/codingplan，可插拔）-> 回收 output/。
不直接读写 DB / S3：上下文由调用方（app.main 的 run_agent_job）准备，
产物归档与 config_change_request 落库也由调用方完成。
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import config, workspace
from .sandbox_client import SandboxClient, SandboxError
from .session import PersistentSession


EventSink = Callable[[str, str, str, dict[str, Any]], None]
WORKBENCH_EVENT_PREFIX = "__WORKBENCH_EVENT__"


class RunnerError(RuntimeError):
    pass


@dataclass
class AgentExecutionResult:
    mode: str
    returncode: int
    stdout: str
    stderr: str
    workdir: Path
    output_dir: Path
    output_files: list[tuple[str, Path]] = field(default_factory=list)
    input_manifest: dict[str, Any] = field(default_factory=dict)
    sandbox_id: str | None = None
    result_json: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


def _emit(sink: EventSink | None, event_type: str, role: str, content: str, payload: dict[str, Any] | None = None) -> None:
    if sink is None:
        return
    try:
        sink(event_type, role, content, payload or {})
    except Exception:
        pass


def _workbench_event_signature(event: dict[str, Any]) -> str:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    return json.dumps(
        {
            "event_type": event.get("event_type"),
            "role": event.get("role"),
            "content": event.get("content"),
            "payload": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _emit_workbench_event_dict(
    event_sink: EventSink | None,
    event: dict[str, Any],
    seen_signatures: set[str] | None = None,
) -> bool:
    if not isinstance(event, dict):
        return False
    signature = _workbench_event_signature(event)
    if seen_signatures is not None:
        if signature in seen_signatures:
            return False
        seen_signatures.add(signature)
    _emit(
        event_sink,
        str(event.get("event_type") or "assistant.delta"),
        str(event.get("role") or "assistant"),
        str(event.get("content") or ""),
        event.get("payload") if isinstance(event.get("payload"), dict) else {},
    )
    return True


def _workbench_stdout_event_parser(
    event_sink: EventSink | None,
    seen_signatures: set[str] | None = None,
) -> Callable[[str], None]:
    buffer = ""

    def feed(text: str) -> None:
        nonlocal buffer
        if not text:
            return
        buffer += text
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if not line.startswith(WORKBENCH_EVENT_PREFIX):
                continue
            try:
                event = json.loads(line.removeprefix(WORKBENCH_EVENT_PREFIX))
            except json.JSONDecodeError:
                continue
            if _emit_workbench_event_dict(event_sink, event, seen_signatures):
                feed.event_count += 1

    feed.event_count = 0  # type: ignore[attr-defined]
    return feed


def _start_live_event_file_tailer(
    client: SandboxClient,
    sandbox_id: str,
    remote_path: str,
    event_sink: EventSink | None,
    seen_signatures: set[str],
) -> tuple[threading.Event, threading.Thread, dict[str, int]]:
    state = {"event_count": 0}
    stop_event = threading.Event()

    def poll_once() -> None:
        try:
            raw = client.read_file(sandbox_id, remote_path)
        except Exception:
            return
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw or "")
        except UnicodeDecodeError:
            return
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if _emit_workbench_event_dict(event_sink, event, seen_signatures):
                state["event_count"] += 1

    def run() -> None:
        while not stop_event.wait(0.75):
            poll_once()
        poll_once()

    thread = threading.Thread(target=run, name=f"sandbox-live-events-{sandbox_id}", daemon=True)
    thread.start()
    return stop_event, thread, state


def _load_result_json(output_dir: Path) -> dict[str, Any]:
    result_path = output_dir / "result.json"
    if not result_path.exists():
        return {}
    try:
        return json.loads(result_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _emit_output_events(output_dir: Path, event_sink: EventSink | None) -> None:
    if event_sink is None:
        return
    events_path = output_dir / "acp_events.ndjson"
    if not events_path.exists():
        return
    try:
        lines = events_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("event_type") or "assistant.delta")
        role = str(event.get("role") or "assistant")
        content = str(event.get("content") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        _emit(event_sink, event_type, role, content, payload)


def _fake_agent_env(dirs: dict[str, Path], workdir: Path) -> dict[str, str]:
    return {
        "WORKSPACE_DIR": str(workdir),
        "INPUT_DIR": str(dirs["input"]),
        "SKILLS_DIR": str(dirs["skills"]),
        "OUTPUT_DIR": str(dirs["output"]),
    }


def execute_agent(context: dict[str, Any], *, event_sink: EventSink | None = None) -> AgentExecutionResult:
    """单轮执行入口（向后兼容）：执行完毕后自动回收并销毁沙箱。"""
    mode = config.runner_mode()
    if mode == "sandbox":
        try:
            return _run_in_sandbox(context, event_sink=event_sink)
        except SandboxError as exc:
            _emit(event_sink, "run.warning", "system", f"沙箱执行失败，降级本地执行：{exc}", {"error": str(exc)})
    return _run_local(context, event_sink=event_sink)


# ---------------------------------------------------------------------------
# 持久会话 API：长生命周期 pause/resume 追问
# ---------------------------------------------------------------------------

def create_persistent_session(context: dict[str, Any], *, event_sink: EventSink | None = None) -> PersistentSession:
    """创建沙箱但不销毁，返回可 pause/resume 的 session 对象。"""
    client = SandboxClient()
    workdir = config.workspace_root() / f"session-{uuid.uuid4().hex[:12]}"
    dirs = workspace.prepare_workspace(workdir)
    workspace.build_input(context, dirs)

    env = config.credential_env()
    _emit(event_sink, "tool.call", "tool", "创建持久沙箱", {"tool_name": "sandbox.create", "status": "running"})
    created = client.create_sandbox(env=env, metadata={"session": True, "job_id": (context.get("job") or {}).get("id")})
    sandbox_id = str(created.get("id") or created.get("sandbox_id") or "")
    if not sandbox_id:
        raise RunnerError(f"create_sandbox did not return an id: {created}")
    _emit(event_sink, "tool.result", "tool", "持久沙箱已创建", {"tool_name": "sandbox.create", "result": {"sandbox_id": sandbox_id}, "status": "completed"})

    _upload_workspace_to_sandbox(client, sandbox_id, workdir, dirs)

    session = PersistentSession(
        sandbox_id=sandbox_id,
        workdir=workdir,
        dirs=dirs,
        context=context,
    )
    return session


def send_message(
    session: PersistentSession,
    message: str,
    *,
    event_sink: EventSink | None = None,
    extra_input_files: list[dict[str, Any]] | None = None,
    conversation_turns: list[dict[str, str]] | None = None,
) -> AgentExecutionResult:
    """在已有沙箱中执行追问：将 message 追加到 input/conversation.jsonl，再次运行 agent。

    ``extra_input_files`` 用于把会话引用/上传的资料（供应商账单、内部账单产物等）
    在每轮运行前同步进沙箱 input/，让对账 Agent 能真正读到业务数据。每项形如
    ``{"path": "supplier/bill.xlsx", "data": b"..."}``，相对 input/ 目录。
    """
    if session.status != "active":
        raise RunnerError(f"session is {session.status}, cannot send message")

    if conversation_turns is None:
        session.add_message("user", message)
        turns = session.conversation
    else:
        turns = [
            {"role": str(turn.get("role") or "user"), "content": str(turn.get("content") or "")}
            for turn in conversation_turns
            if str(turn.get("content") or "").strip()
        ]
        if not turns:
            turns = [{"role": "user", "content": message}]
        session.conversation = turns

    # 沙箱会话的本地暂存目录可能因容器重启 / 临时目录清理而丢失；
    # resume 追问会从数据库历史重建 conversation.jsonl，再上传沙箱。
    conversation_path = session.dirs["input"] / "conversation.jsonl"
    conversation_path.parent.mkdir(parents=True, exist_ok=True)
    conversation_path.write_text(
        "".join(json.dumps(turn, ensure_ascii=False) + "\n" for turn in turns),
        encoding="utf-8",
    )

    client = SandboxClient()
    sandbox_root = "/tmp/workspace"
    _upload_runner_scripts(client, session.sandbox_id, sandbox_root)

    client.write_file(
        session.sandbox_id,
        f"{sandbox_root}/input/conversation.jsonl",
        conversation_path.read_bytes(),
    )

    for item in extra_input_files or []:
        rel = str(item.get("path") or "").strip().lstrip("/")
        data = item.get("data")
        if not rel or data is None:
            continue
        if isinstance(data, str):
            data = data.encode("utf-8")
        local_target = session.dirs["input"] / rel
        local_target.parent.mkdir(parents=True, exist_ok=True)
        local_target.write_bytes(data)
        client.write_file(session.sandbox_id, f"{sandbox_root}/input/{rel}", data)

    agent = config.agent_mode()
    argv = _sandbox_agent_argv(agent, sandbox_root)
    env = config.credential_env()
    _emit(
        event_sink,
        "tool.call",
        "tool",
        "在沙箱中执行 Agent",
        {"tool_name": "sandbox.exec", "arguments": {"argv": argv, "cwd": sandbox_root}, "status": "running"},
    )
    _emit(event_sink, "assistant.delta", "assistant", "继续执行追问。", {"mode": f"sandbox-{agent}"})

    seen_live_event_signatures: set[str] = set()
    stdout_event_parser = _workbench_stdout_event_parser(event_sink, seen_live_event_signatures)
    live_event_state = {"event_count": 0}
    live_event_stop: threading.Event | None = None
    live_event_thread: threading.Thread | None = None
    if event_sink is not None:
        live_event_stop, live_event_thread, live_event_state = _start_live_event_file_tailer(
            client,
            session.sandbox_id,
            f"{sandbox_root}/output/live_events.ndjson",
            event_sink,
            seen_live_event_signatures,
        )
    try:
        exec_result = client.exec_command(
            session.sandbox_id,
            argv,
            cwd=sandbox_root,
            env={
                "WORKSPACE_DIR": sandbox_root,
                "INPUT_DIR": f"{sandbox_root}/input",
                "SKILLS_DIR": f"{sandbox_root}/skills",
                "OUTPUT_DIR": f"{sandbox_root}/output",
                **env,
            },
            stdout_callback=stdout_event_parser,
        )
    finally:
        if live_event_stop is not None:
            live_event_stop.set()
        if live_event_thread is not None:
            live_event_thread.join(timeout=3)
    returncode = int(exec_result.get("returncode") or exec_result.get("exit_code") or 0)
    stdout = str(exec_result.get("stdout") or "")
    stderr = str(exec_result.get("stderr") or "")
    try:
        remote_files = client.list_files(session.sandbox_id, f"{sandbox_root}/output")
    except SandboxError:
        remote_files = []
    for remote in remote_files:
        rel = remote.split(f"{sandbox_root}/output/", 1)[-1]
        data = client.read_file(session.sandbox_id, remote)
        target = session.dirs["output"] / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    if getattr(stdout_event_parser, "event_count", 0) + live_event_state.get("event_count", 0) == 0:
        _emit_output_events(session.dirs["output"], event_sink)
    output_files = workspace.collect_output(session.dirs["output"])
    result_json = _load_result_json(session.dirs["output"])
    result_status = str(result_json.get("status") or "").strip().lower()
    exec_failed = returncode != 0 or not result_status or result_status in {"error", "failed", "failure", "cancelled", "canceled"}
    _emit(
        event_sink,
        "tool.result",
        "tool",
        "沙箱 Agent 执行失败" if exec_failed else "沙箱 Agent 执行完成",
        {
            "tool_name": "sandbox.exec",
            "result": {
                "returncode": returncode,
                "result_status": result_json.get("status"),
                "stdout_tail": stdout[-2000:],
                "stderr_tail": stderr[-2000:],
            },
            "status": "failed" if exec_failed else "completed",
        },
    )

    if result_json.get("summary"):
        session.add_message("assistant", result_json["summary"])

    return AgentExecutionResult(
        mode=f"sandbox-{agent}",
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        workdir=session.workdir,
        output_dir=session.dirs["output"],
        output_files=output_files,
        input_manifest={},
        sandbox_id=session.sandbox_id,
        result_json=result_json,
    )


def pause_session(session: PersistentSession) -> None:
    """暂停沙箱（保留状态，释放计算资源）。"""
    if session.status != "active":
        raise RunnerError(f"session is {session.status}, cannot pause")
    client = SandboxClient()
    client.pause_sandbox(session.sandbox_id)
    session.status = "paused"


def resume_session(session: PersistentSession) -> None:
    """恢复已暂停的沙箱。"""
    if session.status != "paused":
        raise RunnerError(f"session is {session.status}, cannot resume")
    client = SandboxClient()
    client.resume_sandbox(session.sandbox_id)
    session.status = "active"


def destroy_session(session: PersistentSession, *, event_sink: EventSink | None = None) -> list[tuple[str, Path]]:
    """回收 output 后删除沙箱并清理本地工作目录。"""
    output_files = workspace.collect_output(session.dirs["output"])
    try:
        client = SandboxClient()
        client.delete_sandbox(session.sandbox_id)
        _emit(event_sink, "tool.result", "tool", "持久沙箱已销毁", {"tool_name": "sandbox.delete", "result": {"sandbox_id": session.sandbox_id}, "status": "completed"})
    except SandboxError:
        pass
    session.status = "destroyed"
    workspace.cleanup(session.workdir)
    return output_files


# ---------------------------------------------------------------------------
# 本地执行（无沙箱降级）
# ---------------------------------------------------------------------------

def _run_local(context: dict[str, Any], *, event_sink: EventSink | None) -> AgentExecutionResult:
    workdir = config.workspace_root() / f"job-{uuid.uuid4().hex[:12]}"
    dirs = workspace.prepare_workspace(workdir)
    manifest = workspace.build_input(context, dirs)
    _emit(event_sink, "tool.call", "tool", "组装沙箱上下文", {"tool_name": "workspace.build", "arguments": manifest, "status": "running"})

    agent = config.agent_mode()
    import os

    env = os.environ.copy()
    env.update(_fake_agent_env(dirs, workdir))
    env.update(config.credential_env())

    if agent == "fake" or not _agent_cli_available(agent):
        argv = [sys.executable, str(config.fake_agent_path())]
        effective_mode = f"local-fake" if agent == "fake" else f"local-fake(fallback:{agent})"
    else:
        argv = _agent_cli_argv(agent, dirs)
        effective_mode = f"local-{agent}"

    _emit(event_sink, "tool.result", "tool", "上下文已就绪", {"tool_name": "workspace.build", "result": manifest, "status": "completed"})
    _emit(event_sink, "assistant.delta", "assistant", "我已读取本次账单、供应商资料和计费口径，开始核对。", {"mode": effective_mode})

    try:
        completed = subprocess.run(
            argv,
            cwd=str(workdir),
            env=env,
            capture_output=True,
            text=True,
            timeout=config.agent_exec_timeout_seconds(),
        )
        returncode = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = f"agent execution timed out after {config.agent_exec_timeout_seconds()}s"

    output_files = workspace.collect_output(dirs["output"])
    result_json = _load_result_json(dirs["output"])
    return AgentExecutionResult(
        mode=effective_mode,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        workdir=workdir,
        output_dir=dirs["output"],
        output_files=output_files,
        input_manifest=manifest,
        sandbox_id=None,
        result_json=result_json,
    )


def _agent_cli_available(agent: str) -> bool:
    import shutil

    if agent == "codex":
        return shutil.which("codex") is not None
    if agent == "codingplan":
        import os

        return bool(os.getenv("ZHIPU_CODINGPLAN_API_KEY"))
    if agent == "claude_acp":
        import os

        return bool(os.getenv("ZHIPU_CODINGPLAN_API_KEY")) and shutil.which("acpx") is not None
    return False


def _agent_cli_argv(agent: str, dirs: dict[str, Path]) -> list[str]:
    if agent == "codex":
        return [
            "codex",
            "exec",
            "--cd",
            str(dirs["input"].parent),
            "--output-dir",
            str(dirs["output"]),
            "--instructions",
            str(dirs["input"] / "instructions.md"),
        ]
    if agent == "codingplan":
        return [sys.executable, str(config.codingplan_driver_path())]
    if agent == "claude_acp":
        return [sys.executable, str(config.claude_acp_driver_path())]
    return [sys.executable, str(config.fake_agent_path())]


# ---------------------------------------------------------------------------
# 沙箱执行（OpenSandbox Lifecycle + Execd）
# ---------------------------------------------------------------------------

def _upload_workspace_to_sandbox(client: SandboxClient, sandbox_id: str, workdir: Path, dirs: dict[str, Path]) -> None:
    """上传 input/、skills/ 以及 runner 脚本到沙箱。"""
    sandbox_root = "/tmp/workspace"

    for base in ("input", "skills"):
        base_dir = dirs[base]
        for file_path in sorted(base_dir.rglob("*")):
            if file_path.is_file():
                rel = file_path.relative_to(workdir).as_posix()
                client.write_file(sandbox_id, f"{sandbox_root}/{rel}", file_path.read_bytes())

    _upload_runner_scripts(client, sandbox_id, sandbox_root)


def _upload_runner_scripts(client: SandboxClient, sandbox_id: str, sandbox_root: str) -> None:
    """上传 fake_agent.py 和 codingplan_driver.py 到沙箱的 /workspace/runner/。"""
    scripts = [
        ("fake_agent.py", config.fake_agent_path()),
        ("codingplan_driver.py", config.codingplan_driver_path()),
        ("claude_acp_driver.py", config.claude_acp_driver_path()),
    ]
    for filename, local_path in scripts:
        if local_path.exists():
            client.write_file(
                sandbox_id,
                f"{sandbox_root}/runner/{filename}",
                local_path.read_bytes(),
            )


def _run_in_sandbox(context: dict[str, Any], *, event_sink: EventSink | None) -> AgentExecutionResult:
    client = SandboxClient()
    workdir = config.workspace_root() / f"job-{uuid.uuid4().hex[:12]}"
    dirs = workspace.prepare_workspace(workdir)
    manifest = workspace.build_input(context, dirs)

    sandbox_root = "/tmp/workspace"
    env = config.credential_env()
    _emit(event_sink, "tool.call", "tool", "创建沙箱", {"tool_name": "sandbox.create", "status": "running"})
    created = client.create_sandbox(env=env, metadata={"job_id": (context.get("job") or {}).get("id")})
    sandbox_id = str(created.get("id") or created.get("sandbox_id") or "")
    if not sandbox_id:
        raise SandboxError(f"create_sandbox did not return an id: {created}")
    _emit(event_sink, "tool.result", "tool", "沙箱已创建", {"tool_name": "sandbox.create", "result": {"sandbox_id": sandbox_id}, "status": "completed"})

    try:
        _upload_workspace_to_sandbox(client, sandbox_id, workdir, dirs)

        agent = config.agent_mode()
        argv = _sandbox_agent_argv(agent, sandbox_root)
        _emit(event_sink, "assistant.delta", "assistant", "沙箱内 agent 开始执行核对。", {"mode": f"sandbox-{agent}"})
        exec_result = client.exec_command(
            sandbox_id,
            argv,
            cwd=sandbox_root,
            env={
                "WORKSPACE_DIR": sandbox_root,
                "INPUT_DIR": f"{sandbox_root}/input",
                "SKILLS_DIR": f"{sandbox_root}/skills",
                "OUTPUT_DIR": f"{sandbox_root}/output",
                **env,
            },
        )
        returncode = int(exec_result.get("returncode") or exec_result.get("exit_code") or 0)
        stdout = str(exec_result.get("stdout") or "")
        stderr = str(exec_result.get("stderr") or "")

        try:
            remote_files = client.list_files(sandbox_id, f"{sandbox_root}/output")
        except SandboxError:
            remote_files = []
        for remote in remote_files:
            rel = remote.split(f"{sandbox_root}/output/", 1)[-1]
            data = client.read_file(sandbox_id, remote)
            target = dirs["output"] / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        _emit_output_events(dirs["output"], event_sink)
    finally:
        try:
            client.delete_sandbox(sandbox_id)
            _emit(event_sink, "tool.result", "tool", "沙箱已销毁", {"tool_name": "sandbox.delete", "result": {"sandbox_id": sandbox_id}, "status": "completed"})
        except SandboxError:
            pass

    output_files = workspace.collect_output(dirs["output"])
    return AgentExecutionResult(
        mode=f"sandbox-{config.agent_mode()}",
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        workdir=workdir,
        output_dir=dirs["output"],
        output_files=output_files,
        input_manifest=manifest,
        sandbox_id=sandbox_id,
        result_json=_load_result_json(dirs["output"]),
    )


def _sandbox_agent_argv(agent: str, sandbox_root: str) -> list[str]:
    if agent == "fake":
        return ["python", f"{sandbox_root}/runner/fake_agent.py"]
    if agent == "codex":
        return ["codex", "exec", "--cd", sandbox_root, "--output-dir", f"{sandbox_root}/output"]
    if agent == "codingplan":
        return ["python", f"{sandbox_root}/runner/codingplan_driver.py"]
    if agent == "claude_acp":
        return ["python", f"{sandbox_root}/runner/claude_acp_driver.py"]
    return ["python", f"{sandbox_root}/runner/fake_agent.py"]
