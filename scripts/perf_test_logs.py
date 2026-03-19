"""
Performance test for log query and export APIs.

Tests the enhanced /api/log/token endpoint and /api/log/self/export
against a local instance with seeded data.

Usage:
    pip install requests
    python scripts/perf_test_logs.py [--base-url URL]
"""

import argparse
import hashlib
import time
import requests
import sys


def gen_token_key(idx):
    return hashlib.md5(f"test-token-{idx}".encode()).hexdigest()[:32]


def test_log_by_key_paginated(base_url, key):
    """Test /api/log/token with pagination and filters."""
    now = int(time.time())
    week_ago = now - 7 * 86400

    print("\n=== Test: GET /api/log/token (paginated) ===")
    url = f"{base_url}/api/log/token"
    params = {
        "key": f"sk-{key}",
        "p": 1,
        "page_size": 20,
        "start_timestamp": week_ago,
        "end_timestamp": now,
    }

    start = time.time()
    resp = requests.get(url, params=params, timeout=30)
    elapsed = time.time() - start

    data = resp.json()
    success = data.get("success", False)
    total = data.get("data", {}).get("total", 0) if success else 0
    items = len(data.get("data", {}).get("items", [])) if success else 0

    print(f"  Status: {resp.status_code}, Success: {success}")
    print(f"  Total: {total}, Items returned: {items}")
    print(f"  Time: {elapsed:.3f}s")
    assert success, "Request failed"
    assert elapsed < 5.0, f"Too slow: {elapsed:.3f}s"
    print("  PASS")
    return elapsed


def test_log_by_key_with_model_filter(base_url, key):
    """Test /api/log/token with model filter."""
    now = int(time.time())
    week_ago = now - 7 * 86400

    print("\n=== Test: GET /api/log/token (model filter) ===")
    url = f"{base_url}/api/log/token"
    params = {
        "key": f"sk-{key}",
        "p": 1,
        "page_size": 20,
        "model_name": "gpt-4o",
        "start_timestamp": week_ago,
        "end_timestamp": now,
    }

    start = time.time()
    resp = requests.get(url, params=params, timeout=30)
    elapsed = time.time() - start

    data = resp.json()
    success = data.get("success", False)
    total = data.get("data", {}).get("total", 0) if success else 0

    print(f"  Status: {resp.status_code}, Success: {success}")
    print(f"  Total: {total}")
    print(f"  Time: {elapsed:.3f}s")
    assert success, "Request failed"
    assert elapsed < 5.0, f"Too slow: {elapsed:.3f}s"
    print("  PASS")
    return elapsed


def test_log_by_key_no_filter(base_url, key):
    """Test /api/log/token with only key (defaults to page 1, 10 items)."""
    print("\n=== Test: GET /api/log/token (minimal params) ===")
    url = f"{base_url}/api/log/token"
    params = {"key": f"sk-{key}"}

    start = time.time()
    resp = requests.get(url, params=params, timeout=30)
    elapsed = time.time() - start

    data = resp.json()
    success = data.get("success", False)
    total = data.get("data", {}).get("total", 0) if success else 0
    items = len(data.get("data", {}).get("items", [])) if success else 0

    print(f"  Status: {resp.status_code}, Success: {success}")
    print(f"  Total: {total}, Items returned: {items}")
    print(f"  Time: {elapsed:.3f}s")
    assert success, "Request failed"
    assert items <= 100, f"Items should be capped by page_size, got {items}"
    assert elapsed < 5.0, f"Too slow: {elapsed:.3f}s"
    print("  PASS")
    return elapsed


def test_export_requires_time_range(base_url, session_token):
    """Test that export rejects requests without time range."""
    print("\n=== Test: GET /api/log/self/export (no time range) ===")
    url = f"{base_url}/api/log/self/export"
    headers = {"Authorization": f"Bearer {session_token}"}

    start = time.time()
    resp = requests.get(url, headers=headers, timeout=30)
    elapsed = time.time() - start

    data = resp.json()
    success = data.get("success", False)

    print(f"  Status: {resp.status_code}, Success: {success}")
    print(f"  Message: {data.get('message', '')}")
    print(f"  Time: {elapsed:.3f}s")
    assert not success, "Should reject without time range"
    print("  PASS (correctly rejected)")
    return elapsed


def test_export_with_time_range(base_url, session_token):
    """Test that export works with valid time range."""
    now = int(time.time())
    day_ago = now - 86400

    print("\n=== Test: GET /api/log/self/export (1 day range) ===")
    url = f"{base_url}/api/log/self/export"
    headers = {"Authorization": f"Bearer {session_token}"}
    params = {
        "start_timestamp": day_ago,
        "end_timestamp": now,
    }

    start = time.time()
    resp = requests.get(url, headers=headers, params=params, timeout=60)
    elapsed = time.time() - start

    content_type = resp.headers.get("Content-Type", "")
    content_len = len(resp.content)
    lines = resp.text.count("\n")

    print(f"  Status: {resp.status_code}")
    print(f"  Content-Type: {content_type}")
    print(f"  Response size: {content_len} bytes, ~{lines} lines")
    print(f"  Time: {elapsed:.3f}s")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert "csv" in content_type, f"Expected CSV, got {content_type}"
    assert elapsed < 10.0, f"Too slow: {elapsed:.3f}s"
    print("  PASS")
    return elapsed


def main():
    parser = argparse.ArgumentParser(description="Performance test for log APIs")
    parser.add_argument("--base-url", default="http://localhost:3000")
    parser.add_argument("--session-token", default="",
                        help="User session token for export tests (cookie or bearer)")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    key = gen_token_key(1)

    print(f"Base URL: {base}")
    print(f"Test token key: sk-{key}")

    results = {}
    try:
        results["paginated"] = test_log_by_key_paginated(base, key)
        results["model_filter"] = test_log_by_key_with_model_filter(base, key)
        results["minimal"] = test_log_by_key_no_filter(base, key)

        if args.session_token:
            results["export_reject"] = test_export_requires_time_range(base, args.session_token)
            results["export_ok"] = test_export_with_time_range(base, args.session_token)
        else:
            print("\n(Skipping export tests - no --session-token provided)")

    except AssertionError as e:
        print(f"\n  FAIL: {e}")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"\nERROR: Cannot connect to {base}. Is the server running?")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("RESULTS SUMMARY")
    print("=" * 50)
    for name, elapsed in results.items():
        status = "OK" if elapsed < 5.0 else "SLOW"
        print(f"  {name:20s}: {elapsed:.3f}s [{status}]")
    print("\nAll tests passed!")


if __name__ == "__main__":
    main()
