#!/usr/bin/env python3
"""Deep analysis of 400 errors - sub-classify validation_exception_other."""

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
        if status_code == 400:
            resp_body = str(obj.get("response_body", ""))
            error_msg = ""
            try:
                resp_json = json.loads(resp_body)
                err = resp_json.get("error", {})
                error_msg = err.get("message", "")
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
                "filepath": filepath,
            }
    except Exception:
        pass
    return None


def sub_classify(msg: str) -> str:
    """Fine-grained sub-classification of error messages."""
    if not msg or msg.strip() == "":
        return "A_empty_message"

    lower = msg.lower()

    # Thinking/signature related
    if "thinking" in lower and "cannot be modified" in lower:
        return "B_thinking_block_cannot_be_modified"
    if "redacted_thinking" in lower and "cannot be modified" in lower:
        return "B_thinking_block_cannot_be_modified"
    if "invalid" in lower and "signature" in lower and "thinking" in lower:
        return "C_invalid_signature_in_thinking"

    # Bedrock ValidationException sub-types
    if "validationexception" in lower:
        if "does not support assistant message prefill" in lower:
            return "D_no_assistant_prefill"
        if "tool_use" in lower and "tool_result" in lower:
            return "E_tool_use_without_tool_result"
        if "must alternate" in lower or "must be" in lower and "role" in lower:
            return "F_message_role_alternation"
        if "max_tokens" in lower:
            return "G_max_tokens_issue"
        if "content" in lower and "empty" in lower:
            return "H_empty_content"
        return f"I_validation_other: {msg[:200]}"

    # Bedrock generic
    if "bad request" in lower and "bedrock" in lower:
        return "J_bedrock_bad_request"

    # Prompt too long
    if "prompt is too long" in lower or "prompt length" in lower:
        return "K_prompt_too_long"

    # API key issues
    if "api key" in lower or "incorrect api key" in lower:
        return "L_api_key_error"

    # Credit/billing
    if "credit balance" in lower:
        return "M_credit_balance"

    # Operation not allowed/unsupported
    if "operation not allowed" in lower or "unsupported" in lower:
        return "N_operation_unsupported"

    # Inference failed
    if "inference failed" in lower:
        return "O_inference_failed"

    return f"Z_other: {msg[:150]}"


def main():
    gz_files = list(LOG_DIR.rglob("*.ndjson.gz"))
    total_files = len(gz_files)
    print(f"Found {total_files} log files in {LOG_DIR}")
    hours = sorted(set(str(f.parent.name) for f in gz_files))
    print(f"Hours covered: {hours} ({len(hours)} hours)")
    print(f"Scanning...\n")

    all_errors = []
    workers = min(os.cpu_count() or 4, 8)

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_file, str(f)): f for f in gz_files}
        done = 0
        for future in as_completed(futures):
            done += 1
            if done % 3000 == 0:
                print(f"  {done}/{total_files}...", file=sys.stderr)
            r = future.result()
            if r is not None:
                all_errors.append(r)

    print(f"Total requests scanned: {total_files}")
    print(f"Total 400 errors: {len(all_errors)}")
    print(f"Error rate: {len(all_errors)/total_files*100:.2f}%\n")

    if not all_errors:
        return

    by_cat = defaultdict(list)
    for e in all_errors:
        cat = sub_classify(e["error_message"])
        by_cat[cat].append(e)

    print("=" * 95)
    print("DETAILED ERROR SUB-CLASSIFICATION")
    print("=" * 95)
    for cat, errs in sorted(by_cat.items(), key=lambda x: -len(x[1])):
        pct = len(errs) / len(all_errors) * 100
        print(f"  {cat}: {len(errs)} ({pct:.1f}%)")

    # Per-category detail
    for cat, errs in sorted(by_cat.items(), key=lambda x: -len(x[1])):
        print(f"\n{'─' * 95}")
        print(f"  {cat}: {len(errs)} errors")
        print(f"{'─' * 95}")

        # Channel breakdown
        ch_map = defaultdict(int)
        for e in errs:
            ch_map[f"{e['channel_name']}(id={e['channel_id']})"] += 1
        print("  Channels:", dict(sorted(ch_map.items(), key=lambda x: -x[1])))

        # Model breakdown
        m_map = defaultdict(int)
        for e in errs:
            m_map[e["model"]] += 1
        print("  Models:", dict(sorted(m_map.items(), key=lambda x: -x[1])))

        # User breakdown
        u_map = defaultdict(int)
        for e in errs:
            u_map[e["user_id"]] += 1
        print("  Users:", dict(sorted(u_map.items(), key=lambda x: -x[1])))

        # Hour distribution
        h_map = defaultdict(int)
        for e in errs:
            ts = e.get("created_at", "")
            if "T" in ts:
                h_map[ts.split("T")[1][:2]] += 1
        print("  Hours:", dict(sorted(h_map.items())))

        # 1-2 samples
        seen = set()
        samples = []
        for e in errs:
            k = e["error_message"][:200]
            if k not in seen:
                seen.add(k)
                samples.append(e)
            if len(samples) >= 2:
                break
        for i, s in enumerate(samples):
            print(f"  Sample[{i+1}]: req={s['request_id']} time={s['created_at']} model={s['model']} ch={s['channel_name']}")
            print(f"           msg={s['error_message'][:350]}")

    # ========== 你关心的两类错误的专项分析 ==========
    print(f"\n{'=' * 95}")
    print("FOCUS: 你关心的两类错误专项分析")
    print("=" * 95)

    # 错误1: empty_message_400
    empty_errs = by_cat.get("A_empty_message", [])
    print(f"\n[错误类型1] 空message的400错误: {len(empty_errs)} 次")
    if empty_errs:
        ch_map = defaultdict(int)
        m_map = defaultdict(int)
        for e in empty_errs:
            ch_map[e["channel_name"]] += 1
            m_map[e["model"]] += 1
        print(f"  渠道分布: {dict(ch_map)}")
        print(f"  模型分布: {dict(m_map)}")
        for i, e in enumerate(empty_errs[:3]):
            print(f"  样本[{i+1}]: req={e['request_id']} time={e['created_at']} model={e['model']} ch={e['channel_name']} user={e['user_id']}")

    # 错误2: thinking block cannot be modified
    think_errs = by_cat.get("B_thinking_block_cannot_be_modified", [])
    print(f"\n[错误类型2] thinking block cannot be modified: {len(think_errs)} 次")
    if think_errs:
        ch_map = defaultdict(int)
        m_map = defaultdict(int)
        for e in think_errs:
            ch_map[e["channel_name"]] += 1
            m_map[e["model"]] += 1
        print(f"  渠道分布: {dict(ch_map)}")
        print(f"  模型分布: {dict(m_map)}")
        h_map = defaultdict(int)
        for e in think_errs:
            ts = e.get("created_at", "")
            if "T" in ts:
                h_map[ts.split("T")[1][:2]] += 1
        print(f"  时间分布: {dict(sorted(h_map.items()))}")
        for i, e in enumerate(think_errs[:3]):
            print(f"  样本[{i+1}]: req={e['request_id']} time={e['created_at']} model={e['model']} ch={e['channel_name']} user={e['user_id']}")
            print(f"           msg={e['error_message'][:400]}")

    # 错误2b: invalid signature in thinking
    sig_errs = by_cat.get("C_invalid_signature_in_thinking", [])
    print(f"\n[错误类型2b] Invalid signature in thinking block: {len(sig_errs)} 次")
    if sig_errs:
        ch_map = defaultdict(int)
        m_map = defaultdict(int)
        for e in sig_errs:
            ch_map[e["channel_name"]] += 1
            m_map[e["model"]] += 1
        print(f"  渠道分布: {dict(ch_map)}")
        print(f"  模型分布: {dict(m_map)}")
        h_map = defaultdict(int)
        for e in sig_errs:
            ts = e.get("created_at", "")
            if "T" in ts:
                h_map[ts.split("T")[1][:2]] += 1
        print(f"  时间分布: {dict(sorted(h_map.items()))}")


if __name__ == "__main__":
    main()
