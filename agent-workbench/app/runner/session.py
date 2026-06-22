"""持久沙箱会话数据模型。

与 execute_agent 的"一次性执行后销毁"不同，PersistentSession 让沙箱保持存活，
支持用户追问时在同一上下文中继续执行 agent，不重建沙箱。

生命周期函数在 agent_runner.py 中实现：
  create_persistent_session -> send_message (N次) -> pause/resume -> destroy_session
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PersistentSession:
    """持久沙箱会话对象。"""
    sandbox_id: str
    workdir: Path
    dirs: dict[str, Path]
    context: dict[str, Any]
    conversation: list[dict[str, str]] = field(default_factory=list)
    status: str = "active"  # active | paused | destroyed

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def add_message(self, role: str, content: str) -> None:
        """追加一条对话消息到历史。"""
        self.conversation.append({"role": role, "content": content})

    def to_dict(self) -> dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "workdir": str(self.workdir),
            "status": self.status,
            "conversation_count": len(self.conversation),
            "job_id": (self.context.get("job") or {}).get("id"),
        }

    def conversation_jsonl(self) -> str:
        """导出对话历史为 JSONL 格式字符串。"""
        return "\n".join(
            json.dumps(turn, ensure_ascii=False) for turn in self.conversation
        ) + ("\n" if self.conversation else "")
