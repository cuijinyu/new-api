#!/usr/bin/env python3
"""Detailed analysis of thinking/signature 400 errors."""

import gzip
import json
import os
import re
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

LOG_DIR = Path(__file__).parent / "reconcile/.cache/llm-raw-logs/2026/03/19"


def process_file(filepath: str) -> dict | None:
    try:
        with gzip.open(filepath, "rt", encoding="utf-8", errors="replace") as f:
            data = f.read()
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(data.strip())

        status_code = obj.get("status_code", 0)
        if status_code != 400:
            return None

        resp_body = str(obj.get("response_body", ""))
        error_msg = ""
        try:
            resp_json = json.loads(resp_body)
            err = resp_json.get("error", {})
            error_msg = err.get("message", "")
        except (json.JSONDecodeError, TypeError, AttributeError):
            error_msg = resp_body[:500]

        lower = error_msg.lower()
        is_thinking = ("thinking" in lower and "cannot be modified" in lower) or \
                      ("invalid" in lower and "signature" in lower and "thinking" in lower)
        if not is_thinking:
            return None

        # Parse request body for details
        req_body_str = obj.get("request_body", "")
        req_body = {}
        try:
            req_body = json.loads(req_body_str) if isinstance(req_body_str, str) else req_body_str
        except:
            pass

        messages = req_body.get("messages", [])
        msg_count = len(messages)

        # Analyze thinking blocks in messages
        thinking_info = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                for j, block in enumerate(content):
                    btype = block.get("type", "")
                    if btype in ("thinking", "redacted_thinking"):
                        sig = block.get("signature", "")
                        thinking_text = block.get("thinking", "")
                        thinking_len = len(thinking_text) if thinking_text else 0
                        thinking_info.append({
                            "msg_idx": i,
                            "block_idx": j,
                            "role": role,
                            "type": btype,
                            "signature_prefix": sig[:60] if sig else "(none)",
                            "signature_len": len(sig) if sig else 0,
                            "thinking_len": thinking_len,
                        })

        # Extract the content position from error message (e.g., ***.***.content.0)
        content_pos = ""
        m = re.search(r'content\.(\d+)', error_msg)
        if m:
            content_pos = f"content.{m.group(1)}"

        # Extract error sub-type
        if "cannot be modified" in lower:
            error_subtype = "thinking_block_modified"
        else:
            error_subtype = "invalid_signature"

        # Check if stream or non-stream
        is_stream = req_body.get("stream", False)

        # Extract request chain IDs
        request_ids_in_error = re.findall(r'request id: ([A-Za-z0-9]+)', error_msg)

        # Check anthropic-beta header
        req_headers = obj.get("request_headers", {})
        anthropic_beta = req_headers.get("Anthropic-Beta", req_headers.get("anthropic-beta", []))

        return {
            "request_id": obj.get("request_id", ""),
            "created_at": obj.get("created_at", ""),
            "model": obj.get("model", ""),
            "channel_id": obj.get("channel_id", ""),
            "channel_name": obj.get("channel_name", ""),
            "user_id": obj.get("user_id", ""),
            "error_subtype": error_subtype,
            "error_message": error_msg[:500],
            "content_pos": content_pos,
            "msg_count": msg_count,
            "thinking_blocks": thinking_info,
            "thinking_block_count": len(thinking_info),
            "is_stream": is_stream,
            "request_chain_ids": request_ids_in_error[:5],
            "anthropic_beta": anthropic_beta,
            "filepath": filepath,
        }
    except Exception as e:
        return None


def main():
    gz_files = list(LOG_DIR.rglob("*.ndjson.gz"))
    print(f"Scanning {len(gz_files)} log files for thinking/signature errors...\n")

    all_errors = []
    workers = min(os.cpu_count() or 4, 8)

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_file, str(f)): f for f in gz_files}
        done = 0
        for future in as_completed(futures):
            done += 1
            if done % 3000 == 0:
                print(f"  {done}/{len(gz_files)}...", file=sys.stderr)
            r = future.result()
            if r is not None:
                all_errors.append(r)

    all_errors.sort(key=lambda x: x["created_at"])
    print(f"Total thinking/signature errors: {len(all_errors)}\n")

    # Split by subtype
    modified_errs = [e for e in all_errors if e["error_subtype"] == "thinking_block_modified"]
    sig_errs = [e for e in all_errors if e["error_subtype"] == "invalid_signature"]

    # ==================== SECTION 1: thinking_block_modified ====================
    print("=" * 100)
    print(f"SECTION 1: thinking block cannot be modified ({len(modified_errs)} errors)")
    print("=" * 100)

    for i, e in enumerate(modified_errs):
        print(f"\n--- [{i+1}/{len(modified_errs)}] ---")
        print(f"  request_id:   {e['request_id']}")
        print(f"  time:         {e['created_at']}")
        print(f"  model:        {e['model']}")
        print(f"  channel:      {e['channel_name']} (id={e['channel_id']})")
        print(f"  user_id:      {e['user_id']}")
        print(f"  stream:       {e['is_stream']}")
        print(f"  msg_count:    {e['msg_count']}")
        print(f"  error_pos:    {e['content_pos']}")
        print(f"  thinking_blocks: {e['thinking_block_count']}")
        for tb in e["thinking_blocks"]:
            print(f"    msg[{tb['msg_idx']}].content[{tb['block_idx']}]: type={tb['type']}, "
                  f"sig_len={tb['signature_len']}, thinking_len={tb['thinking_len']}, "
                  f"sig_prefix={tb['signature_prefix']}")
        print(f"  error_msg:    {e['error_message'][:300]}")
        if e["request_chain_ids"]:
            print(f"  chain_ids:    {e['request_chain_ids']}")

    # ==================== SECTION 2: invalid_signature ====================
    print(f"\n\n{'=' * 100}")
    print(f"SECTION 2: Invalid signature in thinking block ({len(sig_errs)} errors)")
    print("=" * 100)

    # Summary first
    by_channel = defaultdict(int)
    by_model = defaultdict(int)
    by_hour = defaultdict(int)
    by_content_pos = defaultdict(int)
    by_thinking_count = defaultdict(int)
    by_msg_count_range = defaultdict(int)

    for e in sig_errs:
        by_channel[e["channel_name"]] += 1
        by_model[e["model"]] += 1
        ts = e.get("created_at", "")
        if "T" in ts:
            by_hour[ts.split("T")[1][:2]] += 1
        by_content_pos[e["content_pos"] or "unknown"] += 1
        by_thinking_count[e["thinking_block_count"]] += 1
        if e["msg_count"] <= 5:
            by_msg_count_range["1-5"] += 1
        elif e["msg_count"] <= 10:
            by_msg_count_range["6-10"] += 1
        elif e["msg_count"] <= 20:
            by_msg_count_range["11-20"] += 1
        elif e["msg_count"] <= 50:
            by_msg_count_range["21-50"] += 1
        else:
            by_msg_count_range["50+"] += 1

    print(f"\n  By Channel: {dict(sorted(by_channel.items(), key=lambda x: -x[1]))}")
    print(f"  By Model: {dict(sorted(by_model.items(), key=lambda x: -x[1]))}")
    print(f"  By Hour: {dict(sorted(by_hour.items()))}")
    print(f"  By Error Content Position: {dict(sorted(by_content_pos.items(), key=lambda x: -x[1]))}")
    print(f"  By Thinking Block Count in Request: {dict(sorted(by_thinking_count.items()))}")
    print(f"  By Message Count Range: {dict(sorted(by_msg_count_range.items()))}")

    # Print first 30 details
    print(f"\n  Detailed listing (first 30 of {len(sig_errs)}):")
    for i, e in enumerate(sig_errs[:30]):
        print(f"\n  --- [{i+1}] ---")
        print(f"    request_id:   {e['request_id']}")
        print(f"    time:         {e['created_at']}")
        print(f"    model:        {e['model']}")
        print(f"    channel:      {e['channel_name']} (id={e['channel_id']})")
        print(f"    stream:       {e['is_stream']}")
        print(f"    msg_count:    {e['msg_count']}")
        print(f"    error_pos:    {e['content_pos']}")
        print(f"    thinking_blocks: {e['thinking_block_count']}")
        for tb in e["thinking_blocks"]:
            print(f"      msg[{tb['msg_idx']}].content[{tb['block_idx']}]: type={tb['type']}, "
                  f"sig_len={tb['signature_len']}, thinking_len={tb['thinking_len']}")
        if e["request_chain_ids"]:
            print(f"    chain_ids:    {e['request_chain_ids']}")

    # ==================== SECTION 3: Pattern analysis ====================
    print(f"\n\n{'=' * 100}")
    print("SECTION 3: Pattern Analysis")
    print("=" * 100)

    # Check if errors correlate with retry chains (multiple request IDs)
    multi_chain = [e for e in all_errors if len(e["request_chain_ids"]) > 1]
    print(f"\n  Errors with multiple request chain IDs (retries): {len(multi_chain)}/{len(all_errors)}")

    # Check content position patterns
    print(f"\n  Content position distribution (which thinking block failed):")
    for pos, cnt in sorted(by_content_pos.items(), key=lambda x: -x[1]):
        print(f"    {pos}: {cnt}")

    # Check if signature is present but invalid vs missing
    sig_present = 0
    sig_missing = 0
    for e in sig_errs:
        has_sig = any(tb["signature_len"] > 0 for tb in e["thinking_blocks"])
        if has_sig:
            sig_present += 1
        else:
            sig_missing += 1
    print(f"\n  Signature analysis for invalid_signature errors:")
    print(f"    Requests WITH signature in thinking blocks: {sig_present}")
    print(f"    Requests WITHOUT any signature: {sig_missing}")

    # Check thinking block types
    type_counts = defaultdict(int)
    for e in all_errors:
        for tb in e["thinking_blocks"]:
            type_counts[tb["type"]] += 1
    print(f"\n  Thinking block types across all error requests:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}")

    # Time clustering - are errors bursty?
    print(f"\n  Time clustering (5-min buckets):")
    time_buckets = defaultdict(int)
    for e in all_errors:
        ts = e.get("created_at", "")
        if "T" in ts:
            hm = ts.split("T")[1][:5]  # HH:MM
            h = int(hm[:2])
            m = int(hm[3:5])
            bucket = f"{h:02d}:{(m // 5) * 5:02d}"
            time_buckets[bucket] += 1
    for bucket, cnt in sorted(time_buckets.items()):
        if cnt >= 3:
            print(f"    {bucket}: {cnt}")


if __name__ == "__main__":
    main()
