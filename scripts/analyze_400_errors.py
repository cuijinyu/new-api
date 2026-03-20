#!/usr/bin/env python3
"""Analyze 400 errors in downloaded raw logs (2026/03/19)."""

import gzip
import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

LOG_DIR = Path(__file__).parent / "reconcile/.cache/llm-raw-logs/2026/03/19"


def process_file(filepath: str) -> dict | None:
    """Process a single .ndjson.gz file. Each file is one JSON object (possibly with trailing SSE data)."""
    try:
        with gzip.open(filepath, "rt", encoding="utf-8", errors="replace") as f:
            data = f.read()

        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(data.strip())

        status_code = obj.get("status_code", 0)
        if status_code == 400:
            resp_body = str(obj.get("response_body", ""))
            error_msg = ""
            error_type = ""
            try:
                resp_json = json.loads(resp_body)
                err = resp_json.get("error", {})
                error_msg = err.get("message", "")
                error_type = err.get("type", "")
            except (json.JSONDecodeError, TypeError, AttributeError):
                error_msg = resp_body[:500]

            return {
                "request_id": obj.get("request_id", ""),
                "created_at": obj.get("created_at", ""),
                "model": obj.get("model", ""),
                "channel_id": obj.get("channel_id", ""),
                "channel_name": obj.get("channel_name", ""),
                "channel_type": obj.get("channel_type", ""),
                "user_id": obj.get("user_id", ""),
                "path": obj.get("path", ""),
                "error_message": error_msg,
                "error_type": error_type,
                "filepath": filepath,
            }
    except Exception as e:
        return None
    return None


def classify_error(msg: str) -> str:
    if not msg or msg.strip() == "":
        return "empty_message_400"
    lower = msg.lower()
    if "thinking" in lower and "cannot be modified" in lower:
        return "thinking_block_cannot_be_modified"
    if "redacted_thinking" in lower and "cannot be modified" in lower:
        return "thinking_block_cannot_be_modified"
    if "invalid" in lower and "signature" in lower and "thinking" in lower:
        return "invalid_signature_in_thinking"
    if "validationexception" in lower:
        return "validation_exception_other"
    if "throttling" in lower:
        return "throttling"
    if "too many tokens" in lower or "token" in lower and "limit" in lower:
        return "token_limit"
    if "content filtering" in lower or "content_filter" in lower:
        return "content_filter"
    return f"other: {msg[:150]}"


def main():
    gz_files = list(LOG_DIR.rglob("*.ndjson.gz"))
    print(f"Found {len(gz_files)} log files in {LOG_DIR}")
    print(f"Hours covered: {sorted(set(str(f.parent.name) for f in gz_files))}")
    print(f"Scanning for status_code=400 errors...\n")

    all_errors = []
    workers = min(os.cpu_count() or 4, 8)

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_file, str(f)): f for f in gz_files}
        done_count = 0
        for future in as_completed(futures):
            done_count += 1
            if done_count % 2000 == 0:
                print(f"  Processed {done_count}/{len(gz_files)} files...", file=sys.stderr)
            result = future.result()
            if result is not None:
                all_errors.append(result)

    print(f"\nTotal 400 errors found: {len(all_errors)}\n")

    if not all_errors:
        print("No 400 errors found in the logs.")
        return

    by_category = defaultdict(list)
    for e in all_errors:
        cat = classify_error(e["error_message"])
        by_category[cat].append(e)

    print("=" * 90)
    print("ERROR CLASSIFICATION SUMMARY")
    print("=" * 90)
    for cat, errors in sorted(by_category.items(), key=lambda x: -len(x[1])):
        print(f"  [{cat}]: {len(errors)} occurrences")

    for cat, errors in sorted(by_category.items(), key=lambda x: -len(x[1])):
        print(f"\n{'=' * 90}")
        print(f"CATEGORY: {cat} ({len(errors)} errors)")
        print("=" * 90)

        by_channel = defaultdict(int)
        for e in errors:
            key = f"{e['channel_name']} (id={e['channel_id']}, type={e['channel_type']})"
            by_channel[key] += 1
        print("\n  By Channel:")
        for ch, cnt in sorted(by_channel.items(), key=lambda x: -x[1]):
            print(f"    {ch}: {cnt}")

        by_model = defaultdict(int)
        for e in errors:
            by_model[e["model"]] += 1
        print("\n  By Model:")
        for m, cnt in sorted(by_model.items(), key=lambda x: -x[1]):
            print(f"    {m}: {cnt}")

        by_user = defaultdict(int)
        for e in errors:
            by_user[e["user_id"]] += 1
        print("\n  By User ID:")
        for u, cnt in sorted(by_user.items(), key=lambda x: -x[1])[:15]:
            print(f"    user_id={u}: {cnt}")
        if len(by_user) > 15:
            print(f"    ... and {len(by_user) - 15} more users")

        by_hour = defaultdict(int)
        for e in errors:
            ts = e.get("created_at", "")
            if "T" in ts:
                hour = ts.split("T")[1][:2]
                by_hour[hour] += 1
        if by_hour:
            print("\n  By Hour (UTC+8):")
            for h, cnt in sorted(by_hour.items()):
                print(f"    {h}:00 - {cnt}")

        by_path = defaultdict(int)
        for e in errors:
            by_path[e["path"]] += 1
        print("\n  By API Path:")
        for p, cnt in sorted(by_path.items(), key=lambda x: -x[1]):
            print(f"    {p}: {cnt}")

        print(f"\n  Sample error messages (up to 5):")
        seen = set()
        count = 0
        for e in errors:
            msg_key = e["error_message"][:300]
            if msg_key not in seen:
                seen.add(msg_key)
                print(f"\n    [{count+1}] request_id={e['request_id']}")
                print(f"        time={e['created_at']}")
                print(f"        model={e['model']}, channel={e['channel_name']}, user_id={e['user_id']}")
                print(f"        error_type={e['error_type']}")
                print(f"        message={e['error_message'][:400]}")
                count += 1
                if count >= 5:
                    break

    print(f"\n{'=' * 90}")
    print("FINAL SUMMARY")
    print("=" * 90)
    print(f"Total log files scanned: {len(gz_files)}")
    print(f"Total 400 errors: {len(all_errors)}")
    print(f"Error rate: {len(all_errors)/len(gz_files)*100:.2f}%")
    print()
    for cat, errors in sorted(by_category.items(), key=lambda x: -len(x[1])):
        pct = len(errors) / len(all_errors) * 100
        print(f"  {cat}: {len(errors)} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
