#!/usr/bin/env python3
"""Check what sig_len=21 signatures actually look like."""
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

        req_body = {}
        try: req_body = json.loads(obj.get("request_body", "{}"))
        except: pass

        sigs = []
        for msg in req_body.get("messages", []):
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if block.get("type") in ("thinking", "redacted_thinking"):
                        sig = block.get("signature", "")
                        sigs.append({
                            "sig_len": len(sig),
                            "sig_value": sig[:100] if sig else "(none)",
                            "sig_full": sig if len(sig) <= 50 else "",
                            "thinking_len": len(block.get("thinking", "") or ""),
                            "type": block.get("type"),
                        })
        if sigs:
            return {
                "request_id": obj.get("request_id", ""),
                "model": obj.get("model", ""),
                "channel_name": obj.get("channel_name", ""),
                "sigs": sigs,
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

    print(f"\nFound {len(results)} error requests with thinking blocks\n")

    sig_lens = Counter()
    sig_samples = defaultdict(list)
    for r in results:
        for s in r["sigs"]:
            sig_lens[s["sig_len"]] += 1
            if len(sig_samples[s["sig_len"]]) < 5:
                sig_samples[s["sig_len"]].append({
                    "request_id": r["request_id"],
                    "model": r["model"],
                    "channel": r["channel_name"],
                    "sig_value": s["sig_value"],
                    "sig_full": s["sig_full"],
                    "thinking_len": s["thinking_len"],
                    "type": s["type"],
                })

    print("Signature length distribution:")
    for length, count in sorted(sig_lens.items()):
        print(f"\n  sig_len={length}: {count} blocks")
        for sample in sig_samples[length]:
            print(f"    req={sample['request_id']} model={sample['model']} ch={sample['channel']} type={sample['type']} thinking_len={sample['thinking_len']}")
            if sample["sig_full"]:
                print(f"    FULL sig: [{sample['sig_full']}]")
            else:
                print(f"    sig prefix: [{sample['sig_value']}]")
