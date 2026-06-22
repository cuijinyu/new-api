"""Runner tests for Human-in-Loop continuation."""

from __future__ import annotations

from unittest.mock import patch

from app.runner import workspace
from app.runner.agent_runner import send_message
from app.runner.session import PersistentSession
from tests.test_agent_handoff import decode_jsonl


class FakeSandboxClient:
    def __init__(self):
        self.writes: dict[str, bytes] = {}

    def write_file(self, sandbox_id: str, path: str, data: bytes):
        self.writes[path] = data
        return {"ok": True}

    def exec_command(
        self,
        sandbox_id: str,
        argv: list[str],
        *,
        cwd: str | None = None,
        env: dict | None = None,
        timeout: int | None = None,
        stdout_callback=None,
        stderr_callback=None,
    ):
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    def list_files(self, sandbox_id: str, path: str):
        return []


def test_send_message_uploads_full_handoff_history(tmp_path):
    dirs = workspace.prepare_workspace(tmp_path / "session")
    session = PersistentSession(sandbox_id="sb-1", workdir=tmp_path / "session", dirs=dirs, context={"job": {"id": "as-1"}})
    fake = FakeSandboxClient()
    turns = [
        {"role": "user", "content": "先核对账单。"},
        {"role": "assistant", "content": "需要人工补充折扣口径。"},
        {"role": "user", "content": "折扣按 UTC+8 自然日结算。"},
        {"role": "user", "content": "请接着继续复核。"},
    ]

    with patch("app.runner.agent_runner.SandboxClient", return_value=fake):
        send_message(session, "请接着继续复核。", conversation_turns=turns)

    uploaded = decode_jsonl(fake.writes["/tmp/workspace/input/conversation.jsonl"])
    assert uploaded == turns
    assert [turn["content"] for turn in uploaded].count("请接着继续复核。") == 1
