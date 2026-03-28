#!/usr/bin/env python3
"""
Test that valid thinking blocks with real signatures are preserved (not stripped).

1. Send a request with extended thinking enabled to get a real thinking block + signature.
2. Replay that thinking block in a follow-up turn.
3. Verify the follow-up succeeds (200), proving the valid signature was kept intact.

Usage:
    API_KEY=sk-xxx python scripts/test_valid_thinking.py
"""

import json
import os
import sys
import httpx

BASE_URL = os.getenv("BASE_URL", "http://localhost:3001")
API_KEY = os.getenv("API_KEY", "")

if not API_KEY:
    print("API_KEY not set. Usage: API_KEY=sk-xxx python scripts/test_valid_thinking.py")
    sys.exit(1)

HEADERS = {
    "x-api-key": API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}

MODEL = "claude-sonnet-4-6"


def step1_get_thinking():
    """Send a request with extended thinking to get a real thinking block."""
    print("=" * 70)
    print("STEP 1: Get real thinking block from Claude")
    print("=" * 70)

    payload = {
        "model": MODEL,
        "max_tokens": 8000,
        "thinking": {
            "type": "enabled",
            "budget_tokens": 5000,
        },
        "messages": [
            {"role": "user", "content": "What is 137 * 251? Think step by step."},
        ],
    }

    resp = httpx.post(
        f"{BASE_URL}/v1/messages",
        headers=HEADERS,
        json=payload,
        timeout=120,
    )

    if resp.status_code != 200:
        print(f"  [FAIL] Status: {resp.status_code}")
        print(f"  Error: {resp.text[:500]}")
        return None

    body = resp.json()
    usage = body.get("usage", {})
    print(f"  [PASS] Status: 200")
    print(f"  Usage: input={usage.get('input_tokens',0)}, output={usage.get('output_tokens',0)}")

    thinking_block = None
    text_block = None
    for block in body.get("content", []):
        if block.get("type") == "thinking":
            thinking_block = block
            sig = block.get("signature", "")
            thinking_text = block.get("thinking", "")
            print(f"  Thinking block found:")
            print(f"    thinking length: {len(thinking_text)}")
            print(f"    signature length: {len(sig)}")
            print(f"    signature prefix: {sig[:40]}...")
        elif block.get("type") == "text":
            text_block = block
            print(f"  Text: {block.get('text', '')[:100]}...")

    if not thinking_block:
        print("  [FAIL] No thinking block in response!")
        return None

    return {"thinking": thinking_block, "text": text_block}


def step2_replay_valid(thinking_block, text_block):
    """Replay the real thinking block in a follow-up turn."""
    print()
    print("=" * 70)
    print("STEP 2: Replay valid thinking block in follow-up turn")
    print("=" * 70)

    sig = thinking_block.get("signature", "")
    print(f"  Replaying signature (len={len(sig)}): {sig[:40]}...")

    payload = {
        "model": MODEL,
        "max_tokens": 8000,
        "thinking": {
            "type": "enabled",
            "budget_tokens": 5000,
        },
        "messages": [
            {"role": "user", "content": "What is 137 * 251? Think step by step."},
            {"role": "assistant", "content": [
                thinking_block,
                text_block,
            ]},
            {"role": "user", "content": "Now what is 137 * 252?"},
        ],
    }

    resp = httpx.post(
        f"{BASE_URL}/v1/messages",
        headers=HEADERS,
        json=payload,
        timeout=120,
    )

    body = resp.json()
    usage = body.get("usage", {})

    if resp.status_code == 200:
        print(f"  [PASS] Status: 200")
        print(f"  Usage: input={usage.get('input_tokens',0)}, output={usage.get('output_tokens',0)}")
        for block in body.get("content", []):
            if block.get("type") == "text":
                print(f"  Response: {block.get('text', '')[:100]}...")
        return True
    else:
        error = body.get("error", {})
        print(f"  [FAIL] Status: {resp.status_code}")
        print(f"  Error: {error.get('message', '')[:300]}")
        return False


def step3_replay_corrupted(thinking_block, text_block):
    """Corrupt the signature and verify it gets stripped (not 400)."""
    print()
    print("=" * 70)
    print("STEP 3: Replay with CORRUPTED signature (should be stripped, not 400)")
    print("=" * 70)

    corrupted = dict(thinking_block)
    corrupted["signature"] = "placeholder_signature"
    print(f"  Corrupted signature to: 'placeholder_signature'")

    payload = {
        "model": MODEL,
        "max_tokens": 8000,
        "thinking": {
            "type": "enabled",
            "budget_tokens": 5000,
        },
        "messages": [
            {"role": "user", "content": "What is 137 * 251? Think step by step."},
            {"role": "assistant", "content": [
                corrupted,
                text_block,
            ]},
            {"role": "user", "content": "Now what is 137 * 252?"},
        ],
    }

    resp = httpx.post(
        f"{BASE_URL}/v1/messages",
        headers=HEADERS,
        json=payload,
        timeout=120,
    )

    body = resp.json()

    if resp.status_code == 200:
        print(f"  [PASS] Status: 200 (invalid block was stripped)")
        usage = body.get("usage", {})
        print(f"  Usage: input={usage.get('input_tokens',0)}, output={usage.get('output_tokens',0)}")
        return True
    else:
        error = body.get("error", {})
        print(f"  [FAIL] Status: {resp.status_code}")
        print(f"  Error: {error.get('message', '')[:300]}")
        return False


if __name__ == "__main__":
    print(f"Base URL: {BASE_URL}")
    print(f"API Key: {API_KEY[:8]}...{API_KEY[-4:]}")
    print(f"Model: {MODEL}")
    print()

    result1 = step1_get_thinking()
    if not result1:
        print("\nFailed to get thinking block. Aborting.")
        sys.exit(1)

    pass2 = step2_replay_valid(result1["thinking"], result1["text"])
    pass3 = step3_replay_corrupted(result1["thinking"], result1["text"])

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Step 1 - Get thinking block:        [PASS]")
    print(f"  Step 2 - Replay valid signature:     {'[PASS]' if pass2 else '[FAIL]'}")
    print(f"  Step 3 - Replay corrupted signature: {'[PASS]' if pass3 else '[FAIL]'}")

    if pass2 and pass3:
        print("\nAll tests passed! Valid signatures are preserved, invalid ones are stripped.")
        sys.exit(0)
    else:
        print("\nSome tests FAILED!")
        sys.exit(1)
