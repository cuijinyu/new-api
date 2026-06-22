"""Human-in-Loop handoff tests for persistent sandbox conversations."""

from __future__ import annotations

import json

from app.services.agent import conversation_turns_from_events


def test_conversation_turns_keep_agent_wait_and_human_handoff():
    events = [
        {"event_type": "session.created", "role": "system", "content": "created"},
        {"event_type": "message", "role": "user", "content": "先核对 6 月账单"},
        {"event_type": "assistant.delta", "role": "assistant", "content": "初步发现渠道 65 有差异。"},
        {"event_type": "human.input.waiting", "role": "system", "content": "请补充供应商折扣口径。"},
        {
            "event_type": "message",
            "role": "user",
            "content": "供应商折扣按 UTC+8 自然日结算。",
            "payload": {"continuation": True},
        },
        {"event_type": "run.completed", "role": "system", "content": "done"},
        {"event_type": "message", "role": "user", "content": "继续按这个口径复核差异。"},
    ]

    turns = conversation_turns_from_events(events)

    assert turns == [
        {"role": "user", "content": "先核对 6 月账单"},
        {"role": "assistant", "content": "初步发现渠道 65 有差异。"},
        {"role": "assistant", "content": "请补充供应商折扣口径。"},
        {"role": "user", "content": "供应商折扣按 UTC+8 自然日结算。"},
        {"role": "user", "content": "继续按这个口径复核差异。"},
    ]


def decode_jsonl(raw: bytes) -> list[dict[str, str]]:
    return [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
