"""Runner 配置与凭证注入。

凭证（LLM / AWS / GitHub）只在执行 agent 的瞬间作为环境变量注入沙箱或子进程，
绝不写入 DB、artifacts 或 result.json。这里集中读取，避免散落各处。
"""

from __future__ import annotations

import os
from pathlib import Path


VALID_AGENT_MODES = {"fake", "codex", "codingplan", "claude_acp"}
VALID_RUNNER_MODES = {"local", "sandbox"}


def agent_mode() -> str:
    # 真实 agent 运行时可插拔：fake（确定性）/ codex / codingplan（真实 LLM，需要凭证）。
    mode = (os.getenv("AGENT_MODE", "fake") or "fake").strip().lower()
    return mode if mode in VALID_AGENT_MODES else "fake"


def runner_mode() -> str:
    # local：在 worker 进程内的临时工作目录跑 agent（无沙箱降级，本地 E2E 默认）。
    # sandbox：真正接入 OpenSandbox Lifecycle + Execd。
    explicit = (os.getenv("RUNNER_MODE", "") or "").strip().lower()
    if explicit in VALID_RUNNER_MODES:
        return explicit
    # 未显式指定时，只有同时配置了 OpenSandbox 才默认走 sandbox。
    if sandbox_configured():
        return "sandbox"
    return "local"


def sandbox_configured() -> bool:
    return bool((os.getenv("OPEN_SANDBOX_URL") or "").strip()) and (
        os.getenv("RUNNER_SANDBOX_ENABLED", "").strip().lower() in {"1", "true", "yes"}
    )


def sandbox_url() -> str:
    return (os.getenv("OPEN_SANDBOX_URL", "") or "").strip().rstrip("/")


def sandbox_api_key() -> str:
    return (os.getenv("OPEN_SANDBOX_API_KEY", "") or "").strip()


def sandbox_image() -> str:
    return (os.getenv("RUNNER_SANDBOX_IMAGE", "langgenius/dify-api:1.11.4") or "").strip()


def workspace_root() -> Path:
    root = Path(os.getenv("RUNNER_WORKSPACE_ROOT", "/tmp/agent-workbench-runner"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def fake_agent_path() -> Path:
    # runner/fake_agent.py 与本包同属 agent-workbench，沿用相对定位以兼容容器内外路径。
    return Path(__file__).resolve().parents[2] / "runner" / "fake_agent.py"


def codingplan_driver_path() -> Path:
    """CodingPlan HTTP 驱动脚本路径（与本模块同目录）。"""
    return Path(__file__).resolve().parent / "codingplan_driver.py"


def claude_acp_driver_path() -> Path:
    return Path(__file__).resolve().parent / "claude_acp_driver.py"


def sandbox_timeout_seconds() -> int:
    raw = os.getenv("RUNNER_SANDBOX_TIMEOUT_SECONDS", "1800")
    try:
        value = int(raw)
    except ValueError:
        value = 1800
    return max(30, min(value, 7200))


def agent_exec_timeout_seconds() -> int:
    raw = os.getenv("RUNNER_AGENT_TIMEOUT_SECONDS", "4800")
    try:
        value = int(raw)
    except ValueError:
        value = 4800
    return max(10, min(value, 7200))


def credential_env() -> dict[str, str]:
    """收集需要注入 agent 运行时的凭证，调用方负责仅在执行瞬间使用、不落库。"""
    env: dict[str, str] = {}
    passthrough = [
        # LLM
        "ZHIPU_CODINGPLAN_API_KEY",
        "ZHIPU_CODINGPLAN_ENDPOINT",
        "ZHIPU_CODINGPLAN_ANTHROPIC_BASE_URL",
        "ZHIPU_CODINGPLAN_MODEL",
        "ZHIPU_CODINGPLAN_ACP_MAX_ATTEMPTS",
        "ZHIPU_CODINGPLAN_ACP_RETRY_BASE_SECONDS",
        "RUNNER_AGENT_TIMEOUT_SECONDS",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "API_TIMEOUT_MS",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
        "ENABLE_TOOL_SEARCH",
        "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS",
        "DISABLE_TELEMETRY",
        "CODEX_API_KEY",
        # AWS（只读 Athena 工具）
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        # GitHub（拉取 skills 等）
        "GITHUB_TOKEN",
    ]
    for name in passthrough:
        value = os.getenv(name)
        if value:
            env[name] = value
    return env
