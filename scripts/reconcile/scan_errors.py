#!/usr/bin/env python3
"""Scan raw S3 logs for 200K+ context errors on March 11, with progress."""

import gzip, json, os, sys, time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count

CACHE_DIR = "E:/new-api/scripts/reconcile/.cache/llm-raw-logs/2026/03/11"

def scan_file(fpath):
    """Scan a single gz file, return (scanned, errors_list)."""
    scanned = 0
    errors = []
    try:
        with gzip.open(fpath, "rt", encoding="utf-8") as gz:
            for line in gz:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except:
                    continue
                scanned += 1
                status = rec.get("status_code") or rec.get("response_code") or 0
                if status < 400:
                    continue

                resp_body = rec.get("response_body", "") or ""
                model = rec.get("model", "?")
                channel = rec.get("channel_id") or rec.get("channel") or "?"
                prompt_tokens = rec.get("usage", {}).get("prompt_tokens", 0) if isinstance(rec.get("usage"), dict) else 0

                error_msg = ""
                if isinstance(resp_body, str) and resp_body:
                    try:
                        if resp_body.startswith("{"):
                            resp = json.loads(resp_body)
                            err = resp.get("error", {})
                            if isinstance(err, dict):
                                error_msg = err.get("message", "")
                            else:
                                error_msg = str(err)
                        elif "data:" in resp_body[:200]:
                            for evt in resp_body.split("\n"):
                                if evt.startswith("data: ") and "error" in evt:
                                    try:
                                        ev = json.loads(evt[6:])
                                        err = ev.get("error", {})
                                        if isinstance(err, dict):
                                            error_msg = err.get("message", "")
                                        else:
                                            error_msg = str(err)
                                    except:
                                        pass
                        else:
                            error_msg = resp_body[:300]
                    except:
                        error_msg = resp_body[:300]

                errors.append({
                    "status": status,
                    "model": model,
                    "channel": channel,
                    "prompt_tokens": prompt_tokens,
                    "msg": error_msg[:300],
                })
    except Exception as e:
        pass
    return scanned, errors


def classify(msg):
    m = msg.lower()
    if any(k in m for k in ("prompt is too long", "context_length", "too many input tokens",
                             "maximum context length", "token limit", "max tokens")):
        return "prompt_too_long"
    if "rate limit" in m or "rate_limit" in m:
        return "rate_limit"
    if "overload" in m:
        return "overloaded"
    if "invalid" in m:
        return "invalid_request"
    if "credit" in m or "billing" in m:
        return "billing"
    return "other"


def main():
    files = []
    for hour_dir in sorted(os.listdir(CACHE_DIR)):
        hpath = os.path.join(CACHE_DIR, hour_dir)
        if os.path.isdir(hpath):
            for f in os.listdir(hpath):
                if f.endswith(".gz"):
                    files.append(os.path.join(hpath, f))

    total_files = len(files)
    print(f"共 {total_files:,} 个文件待扫描")
    print(f"CPU 核心: {cpu_count()}, 使用 {min(cpu_count(), 16)} 个进程")
    print()

    workers = min(cpu_count(), 16)
    total_scanned = 0
    all_errors = []
    done = 0
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(scan_file, f): f for f in files}
        for fut in as_completed(futures):
            done += 1
            scanned, errs = fut.result()
            total_scanned += scanned
            all_errors.extend(errs)

            if done % 2000 == 0 or done == total_files:
                elapsed = time.time() - t0
                speed = done / elapsed if elapsed > 0 else 0
                pct = done / total_files * 100
                eta = (total_files - done) / speed if speed > 0 else 0
                print(f"  进度: {done:,}/{total_files:,} ({pct:.1f}%)  "
                      f"速度: {speed:.0f} files/s  ETA: {eta:.0f}s  "
                      f"已扫描记录: {total_scanned:,}  错误: {len(all_errors):,}")
                sys.stdout.flush()

    elapsed = time.time() - t0
    print(f"\n扫描完成! 耗时 {elapsed:.1f}s")
    print(f"总记录: {total_scanned:,}")
    print(f"HTTP 4xx/5xx 错误: {len(all_errors):,}")
    print(f"错误率: {len(all_errors)/max(total_scanned,1)*100:.3f}%")

    # Classify
    by_cat = Counter()
    by_status = Counter()
    by_cat_channel = Counter()
    by_cat_model = Counter()
    samples = {}

    for e in all_errors:
        cat = classify(e["msg"])
        e["cat"] = cat
        by_cat[cat] += 1
        by_status[e["status"]] += 1
        by_cat_channel[(cat, e["channel"])] += 1
        by_cat_model[(cat, e["model"])] += 1
        key = f'{cat}_{e["status"]}'
        if key not in samples:
            samples[key] = e

    print(f"\n{'='*60}")
    print(f"错误分类汇总:")
    print(f"{'='*60}")
    for cat, cnt in by_cat.most_common():
        print(f"  {cat}: {cnt:,}")

    print(f"\nHTTP 状态码分布:")
    for s, cnt in by_status.most_common():
        print(f"  {s}: {cnt:,}")

    # Detail for prompt_too_long
    print(f"\n{'='*60}")
    print(f"prompt_too_long (>200K 上下文过长) 详情:")
    print(f"{'='*60}")
    ptl = [e for e in all_errors if e["cat"] == "prompt_too_long"]
    if ptl:
        ch_cnt = Counter(e["channel"] for e in ptl)
        model_cnt = Counter(e["model"] for e in ptl)
        print(f"  总数: {len(ptl):,}")
        print(f"\n  按渠道:")
        for ch, cnt in ch_cnt.most_common():
            print(f"    渠道 {ch}: {cnt:,}")
        print(f"\n  按模型:")
        for m, cnt in model_cnt.most_common():
            print(f"    {m}: {cnt:,}")
        print(f"\n  样例:")
        shown_keys = set()
        for e in ptl:
            key = (e["channel"], e["model"])
            if key in shown_keys:
                continue
            shown_keys.add(key)
            print(f"    ch={e['channel']} model={e['model']} status={e['status']}")
            print(f"    msg: {e['msg'][:200]}")
            print()
    else:
        print("  未发现 prompt_too_long 错误")

    # Detail for all other categories by channel
    for cat in ["rate_limit", "overloaded", "invalid_request", "billing", "other"]:
        subset = [e for e in all_errors if e["cat"] == cat]
        if not subset:
            continue
        print(f"\n{'='*60}")
        print(f"{cat} 详情 (共 {len(subset):,}):")
        print(f"{'='*60}")
        ch_cnt = Counter(e["channel"] for e in subset)
        for ch, cnt in ch_cnt.most_common():
            print(f"  渠道 {ch}: {cnt:,}")
        shown_keys = set()
        for e in subset[:3]:
            key = (e["channel"], e["model"])
            if key in shown_keys:
                continue
            shown_keys.add(key)
            print(f"  样例: ch={e['channel']} model={e['model']} status={e['status']}")
            print(f"    msg: {e['msg'][:200]}")


if __name__ == "__main__":
    main()
