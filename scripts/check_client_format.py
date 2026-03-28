#!/usr/bin/env python3
"""Check if thinking/signature errors come from OpenAI or Claude native clients."""
import gzip, json, sys
from pathlib import Path
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

LOG_DIR = Path(__file__).parent / "reconcile/.cache/llm-raw-logs/2026/03/19"

def process_file(filepath):
    try:
        with gzip.open(filepath, "rt", encoding="utf-8", errors="replace") as f:
            data = f.read()
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(data.strip())
        if obj.get("status_code") != 400:
            return None
        error_msg = ""
        try:
            resp_json = json.loads(str(obj.get("response_body", "")))
            error_msg = resp_json.get("error", {}).get("message", "")
        except: pass
        lower = error_msg.lower()
        if not (("invalid" in lower and "signature" in lower and "thinking" in lower) or
                ("thinking" in lower and "cannot be modified" in lower)):
            return None

        path = obj.get("path", "")
        req_headers = obj.get("request_headers", {})

        # Detect client type from headers
        content_type = ""
        user_agent = ""
        anthropic_version = ""
        accept = ""
        for k, v in req_headers.items():
            kl = k.lower()
            if kl == "content-type":
                content_type = v[0] if isinstance(v, list) else v
            elif kl == "user-agent":
                user_agent = v[0] if isinstance(v, list) else v
            elif kl == "anthropic-version":
                anthropic_version = v[0] if isinstance(v, list) else v
            elif kl == "accept":
                accept = v[0] if isinstance(v, list) else v
            elif kl == "x-api-key":
                pass  # Claude native uses x-api-key

        has_anthropic_version = bool(anthropic_version)
        has_x_api_key = "X-Api-Key" in req_headers or "x-api-key" in req_headers
        has_authorization = "Authorization" in req_headers or "authorization" in req_headers

        # Determine format
        if "/v1/messages" in path:
            api_format = "claude_native"
        elif "/v1/chat/completions" in path:
            api_format = "openai_compat"
        else:
            api_format = f"other:{path}"

        # Parse request body to check structure
        req_body = {}
        try: req_body = json.loads(obj.get("request_body", "{}"))
        except: pass

        # Check signature values in the request
        sig_types = set()
        for msg in req_body.get("messages", []):
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if block.get("type") in ("thinking", "redacted_thinking"):
                        sig = block.get("signature", "")
                        if not sig:
                            sig_types.add("empty")
                        elif sig == "placeholder_signature":
                            sig_types.add("placeholder_signature")
                        elif sig == "sig-theta":
                            sig_types.add("sig-theta")
                        elif len(sig) > 100:
                            sig_types.add("real_signature")
                        else:
                            sig_types.add(f"other:{sig[:30]}")

        return {
            "request_id": obj.get("request_id", ""),
            "created_at": obj.get("created_at", ""),
            "model": obj.get("model", ""),
            "channel_name": obj.get("channel_name", ""),
            "api_format": api_format,
            "path": path,
            "user_agent": user_agent[:150],
            "has_anthropic_version": has_anthropic_version,
            "anthropic_version": anthropic_version,
            "has_x_api_key": has_x_api_key,
            "has_authorization": has_authorization,
            "sig_types": list(sig_types),
            "error_subtype": "cannot_be_modified" if "cannot be modified" in lower else "invalid_signature",
        }
    except:
        pass
    return None

if __name__ == "__main__":
    gz_files = list(LOG_DIR.rglob("*.ndjson.gz"))
    print(f"Scanning {len(gz_files)} files...")

    results = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        for r in ex.map(process_file, [str(f) for f in gz_files]):
            if r:
                results.append(r)

    print(f"\nTotal thinking/signature errors: {len(results)}\n")

    # === By API format ===
    print("=" * 90)
    print("BY API FORMAT (Claude native vs OpenAI compat)")
    print("=" * 90)
    by_format = defaultdict(list)
    for r in results:
        by_format[r["api_format"]].append(r)

    for fmt, errs in sorted(by_format.items(), key=lambda x: -len(x[1])):
        print(f"\n  {fmt}: {len(errs)} errors")
        # Sub-breakdown by sig type
        sig_counter = Counter()
        for e in errs:
            for st in e["sig_types"]:
                sig_counter[st] += 1
        if sig_counter:
            print(f"    Signature types: {dict(sig_counter)}")
        # Sub-breakdown by error subtype
        sub_counter = Counter(e["error_subtype"] for e in errs)
        print(f"    Error subtypes: {dict(sub_counter)}")

    # === By User-Agent ===
    print(f"\n{'=' * 90}")
    print("BY USER-AGENT")
    print("=" * 90)
    ua_counter = Counter()
    ua_sig_map = defaultdict(lambda: Counter())
    for r in results:
        ua = r["user_agent"] or "(empty)"
        ua_short = ua[:80]
        ua_counter[ua_short] += 1
        for st in r["sig_types"]:
            ua_sig_map[ua_short][st] += 1

    for ua, cnt in ua_counter.most_common(20):
        print(f"\n  [{cnt}x] {ua}")
        print(f"    Signature types: {dict(ua_sig_map[ua])}")

    # === Cross-tab: format x sig_type ===
    print(f"\n{'=' * 90}")
    print("CROSS-TAB: API Format x Signature Type")
    print("=" * 90)
    cross = defaultdict(lambda: Counter())
    for r in results:
        for st in r["sig_types"]:
            cross[r["api_format"]][st] += 1
    for fmt in sorted(cross.keys()):
        print(f"\n  {fmt}:")
        for st, cnt in cross[fmt].most_common():
            print(f"    {st}: {cnt}")

    # === Detailed: requests with no thinking blocks in body (sig_types empty) ===
    no_sig = [r for r in results if not r["sig_types"]]
    print(f"\n{'=' * 90}")
    print(f"REQUESTS WITH NO THINKING BLOCKS IN BODY: {len(no_sig)}")
    print("=" * 90)
    for r in no_sig[:10]:
        print(f"  req={r['request_id']} path={r['path']} ua={r['user_agent'][:60]} format={r['api_format']}")

    # === Summary ===
    print(f"\n{'=' * 90}")
    print("SUMMARY")
    print("=" * 90)
    total = len(results)
    for fmt, errs in sorted(by_format.items(), key=lambda x: -len(x[1])):
        pct = len(errs) / total * 100
        print(f"  {fmt}: {len(errs)} ({pct:.1f}%)")
