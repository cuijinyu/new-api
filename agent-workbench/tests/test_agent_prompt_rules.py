"""Prompt rule coverage for Agent reconciliation basis."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.routers.agent import AgentSessionRequest, _build_session_sandbox_context, with_base_agent_rules
from app.runner.claude_acp_driver import build_prompt
from app.runner.codingplan_driver import build_system_prompt
from app.services.agent import build_agent_instructions


def test_agent_instructions_include_rate_card_basis():
    instructions = build_agent_instructions(
        {"type": "agent_conversation", "request_payload": {"prompt": "请核对本月账单。"}},
        "2026-06",
        "vendor-a",
        12,
    )

    assert "所有对账均基于刊例价进行" in instructions


def test_session_sandbox_context_adds_base_rule_for_custom_prompt():
    req = AgentSessionRequest(prompt="请核对供应商账单。")

    with patch("app.routers.agent.db_conn", side_effect=RuntimeError("no db")):
        context = _build_session_sandbox_context("as-test", req, {}, [])

    assert "请核对供应商账单。" in context["instructions"]
    assert "所有对账均基于刊例价进行" in context["instructions"]
    assert context["job"]["request_payload"]["prompt"] == context["instructions"]


def test_session_prompt_rule_is_not_duplicated():
    prompt = "所有对账均基于刊例价进行。请核对供应商账单。"

    assert with_base_agent_rules(prompt) == prompt


def test_runner_prompts_include_rate_card_basis():
    assert "所有对账均基于刊例价进行" in build_system_prompt()
    assert "所有对账均基于刊例价进行" in build_prompt()


def test_web_default_agent_prompt_mentions_rate_card_basis():
    web_hook = Path(__file__).resolve().parents[1] / "web" / "src" / "hooks" / "useWorkbench.ts"

    assert "所有对账均基于刊例价进行" in web_hook.read_text(encoding="utf-8")
