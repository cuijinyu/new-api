#!/usr/bin/env python3
"""
Test that invalid thinking block signatures are stripped by new-api.

Sends requests with various invalid signatures via Claude native format (/v1/messages)
and verifies that the upstream doesn't return 400 errors.

Usage:
    python scripts/test_thinking_sanitize.py
"""

import json
import os
import sys
import httpx

BASE_URL = os.getenv("BASE_URL", "http://localhost:3001")
API_KEY = os.getenv("API_KEY", "")

if not API_KEY:
    # Try to read from .env or prompt
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    print(f"API_KEY not set. Please set it via environment variable.")
    print(f"  export API_KEY=sk-xxx")
    print(f"  python {sys.argv[0]}")
    sys.exit(1)

HEADERS = {
    "x-api-key": API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}

def make_request(description: str, messages: list, model: str = "claude-sonnet-4-6") -> dict:
    """Send a request and return the response."""
    payload = {
        "model": model,
        "max_tokens": 100,
        "messages": messages,
    }
    print(f"\n{'='*70}")
    print(f"TEST: {description}")
    print(f"{'='*70}")

    # Count thinking blocks in request
    thinking_count = 0
    for msg in messages:
        if isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if block.get("type") in ("thinking", "redacted_thinking"):
                    sig = block.get("signature", "")
                    sig_desc = f"len={len(sig)}" if len(sig) > 30 else f"'{sig}'"
                    print(f"  thinking block: type={block['type']}, signature={sig_desc}")
                    thinking_count += 1
    print(f"  Total thinking blocks in request: {thinking_count}")

    try:
        resp = httpx.post(
            f"{BASE_URL}/v1/messages",
            headers=HEADERS,
            json=payload,
            timeout=60,
        )
        status = resp.status_code
        body = resp.json()

        if status == 200:
            content_text = ""
            for block in body.get("content", []):
                if block.get("type") == "text":
                    content_text = block.get("text", "")[:80]
            print(f"  [PASS] Status: {status}")
            print(f"  Response: {content_text}...")
            usage = body.get("usage", {})
            print(f"  Usage: input={usage.get('input_tokens',0)}, output={usage.get('output_tokens',0)}")
        else:
            error = body.get("error", {})
            print(f"  [FAIL] Status: {status}")
            print(f"  Error: {error.get('message', '')[:200]}")

        return {"status": status, "body": body}
    except Exception as e:
        print(f"  [FAIL] Exception: {e}")
        return {"status": 0, "error": str(e)}


def test_placeholder_signature():
    """Test: assistant message with placeholder_signature should succeed (block stripped)."""
    messages = [
        {"role": "user", "content": "What is 2+2?"},
        {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "Let me calculate 2+2. It's 4.", "signature": "placeholder_signature"},
            {"type": "text", "text": "2+2 = 4"},
        ]},
        {"role": "user", "content": "And what is 3+3?"},
    ]
    return make_request("placeholder_signature (should be stripped)", messages)


def test_sig_theta():
    """Test: assistant message with sig-theta should succeed (block stripped)."""
    messages = [
        {"role": "user", "content": "What is 5+5?"},
        {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "5+5 is 10.", "signature": "sig-theta"},
            {"type": "text", "text": "5+5 = 10"},
        ]},
        {"role": "user", "content": "And what is 6+6?"},
    ]
    return make_request("sig-theta (should be stripped)", messages)


def test_empty_signature():
    """Test: assistant message with empty signature should succeed (block stripped)."""
    messages = [
        {"role": "user", "content": "What is 7+7?"},
        {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "7+7 is 14.", "signature": ""},
            {"type": "text", "text": "7+7 = 14"},
        ]},
        {"role": "user", "content": "And what is 8+8?"},
    ]
    return make_request("empty signature (should be stripped)", messages)


def test_no_signature_field():
    """Test: thinking block without signature field at all."""
    messages = [
        {"role": "user", "content": "What is 9+9?"},
        {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "9+9 is 18."},
            {"type": "text", "text": "9+9 = 18"},
        ]},
        {"role": "user", "content": "And what is 10+10?"},
    ]
    return make_request("no signature field (should be stripped)", messages)


def test_short_random_signature():
    """Test: thinking block with short random signature."""
    messages = [
        {"role": "user", "content": "What is 11+11?"},
        {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "11+11 is 22.", "signature": "54922078421544399847d6c1"},
            {"type": "text", "text": "11+11 = 22"},
        ]},
        {"role": "user", "content": "And what is 12+12?"},
    ]
    return make_request("short random signature (should be stripped)", messages)


def test_no_thinking_block():
    """Test: normal request without thinking blocks should work fine."""
    messages = [
        {"role": "user", "content": "What is 1+1?"},
        {"role": "assistant", "content": "1+1 = 2"},
        {"role": "user", "content": "And what is 2+3?"},
    ]
    return make_request("no thinking block (baseline, should always work)", messages)


def test_multiple_thinking_blocks():
    """Test: multiple thinking blocks with mixed valid/invalid signatures."""
    messages = [
        {"role": "user", "content": "Step 1"},
        {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "Thinking about step 1...", "signature": "placeholder_signature"},
            {"type": "text", "text": "Done step 1"},
        ]},
        {"role": "user", "content": "Step 2"},
        {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "Thinking about step 2...", "signature": ""},
            {"type": "text", "text": "Done step 2"},
        ]},
        {"role": "user", "content": "Step 3"},
    ]
    return make_request("multiple invalid thinking blocks (all should be stripped)", messages)


if __name__ == "__main__":
    print(f"Base URL: {BASE_URL}")
    print(f"API Key: {API_KEY[:8]}...{API_KEY[-4:]}")

    results = []

    # Run all tests
    tests = [
        ("baseline", test_no_thinking_block),
        ("placeholder_signature", test_placeholder_signature),
        ("sig-theta", test_sig_theta),
        ("empty_signature", test_empty_signature),
        ("no_signature_field", test_no_signature_field),
        ("short_random", test_short_random_signature),
        ("multiple_blocks", test_multiple_thinking_blocks),
    ]

    for name, test_fn in tests:
        result = test_fn()
        results.append((name, result["status"]))

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    all_pass = True
    for name, status in results:
        passed = status == 200
        mark = "[PASS]" if passed else "[FAIL]"
        print(f"  {mark} {name}: {status}")
        if not passed:
            all_pass = False

    if all_pass:
        print(f"\nAll {len(results)} tests passed!")
    else:
        failed = sum(1 for _, s in results if s != 200)
        print(f"\n{failed}/{len(results)} tests FAILED")
    sys.exit(0 if all_pass else 1)
