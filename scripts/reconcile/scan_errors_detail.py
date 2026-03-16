#!/usr/bin/env python3
"""Deep-dive into overloaded, rate-limit, timeout, and channel 38 errors on March 11."""

import gzip, json, os, sys, time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
from datetime import datetime, timezone, timedelta

CACHE_DIR = "E:/new-api/scripts/reconcile/.cache/llm-raw-logs/2026/03/11"
CST = timezone(timedelta(hours=8))


def scan_file(fpath):
    results = []
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
                status = rec.get("status_code") or rec.get("response_code") or 0
                if status < 400:
                    continue

                resp_body = rec.get("response_body", "") or ""
                model = rec.get("model", "?")
                channel = rec.get("channel_id") or rec.get("channel") or "?"
                ts = rec.get("created_at") or rec.get("timestamp") or 0
                req_id = rec.get("request_id", "")
                prompt_tokens = 0
                usage = rec.get("usage")
                if isinstance(usage, dict):
                    prompt_tokens = usage.get("prompt_tokens", 0) or 0

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
                                    except:
                                        pass
                        else:
                            error_msg = resp_body[:400]
                    except:
                        error_msg = resp_body[:400]

                results.append({
                    "status": status,
                    "model": model,
                    "channel": channel,
                    "ts": ts,
                    "prompt_tokens": prompt_tokens,
                    "msg": error_msg[:400],
                    "body_len": len(resp_body),
                    "body_empty": len(resp_body.strip()) == 0,
                    "body_head": resp_body[:200] if resp_body else "",
                })
    except:
        pass
    return results


def ts_to_hour(ts):
    if not ts or ts == 0:
        return "?"
    try:
        if isinstance(ts, str):
            ts = int(ts) if ts.isdigit() else 0
        if ts > 1e12:
            ts = ts / 1000
        dt = datetime.fromtimestamp(ts, tz=CST)
        return dt.strftime("%H")
    except:
        return "?"


def classify(e):
    m = (e["msg"] or "").lower()
    s = e["status"]
    if any(k in m for k in ("prompt is too long", "context_length", "too many input tokens",
                             "maximum context length", "token limit")):
        return "prompt_too_long"
    if "overload" in m:
        return "overloaded"
    if "rate limit" in m or "rate_limit" in m or s == 429:
        return "rate_limit"
    if s == 503 and "overload" not in m:
        return "503_other"
    if s == 504:
        return "gateway_timeout"
    if "credit" in m or "billing" in m:
        return "billing"
    if "invalid" in m:
        return "invalid_request"
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
    print(f"共 {total_files:,} 个文件, 使用 {min(cpu_count(), 16)} 进程并行扫描\n")

    workers = min(cpu_count(), 16)
    all_errors = []
    done = 0
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(scan_file, f): f for f in files}
        for fut in as_completed(futures):
            done += 1
            all_errors.extend(fut.result())
            if done % 5000 == 0 or done == total_files:
                elapsed = time.time() - t0
                speed = done / elapsed
                print(f"  {done:,}/{total_files:,} ({done/total_files*100:.0f}%) "
                      f"{speed:.0f} f/s  错误累计: {len(all_errors):,}")
                sys.stdout.flush()

    elapsed = time.time() - t0
    print(f"\n扫描完成 {elapsed:.1f}s, 总错误 {len(all_errors):,}\n")

    for e in all_errors:
        e["cat"] = classify(e)
        e["hour"] = ts_to_hour(e["ts"])

    # ============================================================
    # 1. OVERLOADED (503) deep dive
    # ============================================================
    overloaded = [e for e in all_errors if e["cat"] == "overloaded"]
    print("=" * 70)
    print(f"一、OVERLOADED 503 过载错误 (共 {len(overloaded):,})")
    print("=" * 70)

    ch_cnt = Counter(e["channel"] for e in overloaded)
    print("\n按渠道:")
    for ch, cnt in ch_cnt.most_common():
        print(f"  渠道 {ch}: {cnt:,}")

    model_cnt = Counter(e["model"] for e in overloaded)
    print("\n按模型:")
    for m, cnt in model_cnt.most_common():
        print(f"  {m}: {cnt:,}")

    hour_cnt = Counter(e["hour"] for e in overloaded)
    print("\n按小时 (CST):")
    for h in sorted(hour_cnt.keys()):
        bar = "#" * (hour_cnt[h] // 50)
        print(f"  {h}:00  {hour_cnt[h]:>5,}  {bar}")

    ch_model = Counter((e["channel"], e["model"]) for e in overloaded)
    print("\n渠道×模型 TOP10:")
    for (ch, m), cnt in ch_model.most_common(10):
        print(f"  渠道{ch} / {m}: {cnt:,}")

    # ============================================================
    # 2. RATE LIMIT (429) deep dive
    # ============================================================
    ratelimit = [e for e in all_errors if e["cat"] == "rate_limit"]
    print("\n" + "=" * 70)
    print(f"二、RATE LIMIT 429 限速错误 (共 {len(ratelimit):,})")
    print("=" * 70)

    ch_cnt = Counter(e["channel"] for e in ratelimit)
    print("\n按渠道:")
    for ch, cnt in ch_cnt.most_common():
        print(f"  渠道 {ch}: {cnt:,}")

    model_cnt = Counter(e["model"] for e in ratelimit)
    print("\n按模型:")
    for m, cnt in model_cnt.most_common():
        print(f"  {m}: {cnt:,}")

    hour_cnt = Counter(e["hour"] for e in ratelimit)
    print("\n按小时 (CST):")
    for h in sorted(hour_cnt.keys()):
        bar = "#" * (hour_cnt[h] // 50)
        print(f"  {h}:00  {hour_cnt[h]:>5,}  {bar}")

    ch_model = Counter((e["channel"], e["model"]) for e in ratelimit)
    print("\n渠道×模型 TOP10:")
    for (ch, m), cnt in ch_model.most_common(10):
        print(f"  渠道{ch} / {m}: {cnt:,}")

    # sample messages
    rl_msgs = Counter(e["msg"][:120] for e in ratelimit if e["msg"])
    print("\n限速错误消息 TOP5:")
    for msg, cnt in rl_msgs.most_common(5):
        print(f"  [{cnt:,}] {msg}")

    # ============================================================
    # 3. GATEWAY TIMEOUT (504) deep dive
    # ============================================================
    timeout = [e for e in all_errors if e["cat"] == "gateway_timeout"]
    print("\n" + "=" * 70)
    print(f"三、GATEWAY TIMEOUT 504 网关超时 (共 {len(timeout):,})")
    print("=" * 70)

    ch_cnt = Counter(e["channel"] for e in timeout)
    print("\n按渠道:")
    for ch, cnt in ch_cnt.most_common():
        print(f"  渠道 {ch}: {cnt:,}")

    model_cnt = Counter(e["model"] for e in timeout)
    print("\n按模型:")
    for m, cnt in model_cnt.most_common():
        print(f"  {m}: {cnt:,}")

    hour_cnt = Counter(e["hour"] for e in timeout)
    print("\n按小时 (CST):")
    for h in sorted(hour_cnt.keys()):
        bar = "#" * (hour_cnt[h] // 50)
        print(f"  {h}:00  {hour_cnt[h]:>5,}  {bar}")

    # sample body
    print("\n超时响应体样例:")
    shown = set()
    for e in timeout:
        bh = e["body_head"][:150]
        if bh not in shown:
            shown.add(bh)
            print(f"  ch={e['channel']} model={e['model']}")
            print(f"  body({e['body_len']}b): {bh}")
            print()
        if len(shown) >= 5:
            break

    # ============================================================
    # 4. CHANNEL 38 (Aiderby) "other" errors
    # ============================================================
    ch38_other = [e for e in all_errors if e["channel"] in (38, "38") and e["cat"] == "other"]
    ch38_all = [e for e in all_errors if e["channel"] in (38, "38")]
    print("\n" + "=" * 70)
    print(f"四、渠道 38 (Aiderby) 错误详情 (总错误 {len(ch38_all):,}, 其中 other={len(ch38_other):,})")
    print("=" * 70)

    ch38_cats = Counter(e["cat"] for e in ch38_all)
    print("\n渠道38 错误分类:")
    for cat, cnt in ch38_cats.most_common():
        print(f"  {cat}: {cnt:,}")

    ch38_status = Counter(e["status"] for e in ch38_all)
    print("\n渠道38 状态码:")
    for s, cnt in ch38_status.most_common():
        print(f"  {s}: {cnt:,}")

    print(f"\n渠道38 other 错误中 body 为空: {sum(1 for e in ch38_other if e['body_empty']):,} / {len(ch38_other):,}")

    body_patterns = Counter()
    for e in ch38_other:
        if e["body_empty"]:
            body_patterns["(empty body)"] += 1
        elif e["body_len"] < 10:
            body_patterns[f"short: '{e['body_head'][:50]}'"] += 1
        else:
            body_patterns[e["body_head"][:100]] += 1

    print("\n渠道38 other 错误 body 模式 TOP10:")
    for pat, cnt in body_patterns.most_common(10):
        print(f"  [{cnt:,}] {pat}")

    ch38_model = Counter(e["model"] for e in ch38_other)
    print("\n渠道38 other 按模型:")
    for m, cnt in ch38_model.most_common():
        print(f"  {m}: {cnt:,}")

    ch38_hour = Counter(e["hour"] for e in ch38_other)
    print("\n渠道38 other 按小时:")
    for h in sorted(ch38_hour.keys()):
        bar = "#" * (ch38_hour[h] // 50)
        print(f"  {h}:00  {ch38_hour[h]:>5,}  {bar}")

    # non-empty body samples
    print("\n渠道38 有 body 的 other 错误样例:")
    shown = set()
    for e in ch38_other:
        if not e["body_empty"] and e["body_head"] not in shown:
            shown.add(e["body_head"])
            print(f"  status={e['status']} model={e['model']}")
            print(f"  body({e['body_len']}b): {e['body_head'][:300]}")
            print()
        if len(shown) >= 5:
            break

    # ============================================================
    # 5. CHANNEL 40 billing errors
    # ============================================================
    ch40 = [e for e in all_errors if e["channel"] in (40, "40")]
    print("\n" + "=" * 70)
    print(f"五、渠道 40 错误详情 (共 {len(ch40):,})")
    print("=" * 70)
    ch40_cats = Counter(e["cat"] for e in ch40)
    for cat, cnt in ch40_cats.most_common():
        print(f"  {cat}: {cnt:,}")

    ch40_models = Counter(e["model"] for e in ch40)
    print("\n按模型:")
    for m, cnt in ch40_models.most_common():
        print(f"  {m}: {cnt:,}")

    ch40_hours = Counter(e["hour"] for e in ch40)
    print("\n按小时:")
    for h in sorted(ch40_hours.keys()):
        print(f"  {h}:00  {ch40_hours[h]:,}")

    print("\n样例:")
    for e in ch40[:3]:
        print(f"  status={e['status']} model={e['model']} hour={e['hour']}")
        print(f"  msg: {e['msg'][:200]}")
        print()

    # ============================================================
    # 6. 503_other (non-overload 503)
    # ============================================================
    s503_other = [e for e in all_errors if e["cat"] == "503_other"]
    if s503_other:
        print("\n" + "=" * 70)
        print(f"六、503 非 overload 错误 (共 {len(s503_other):,})")
        print("=" * 70)
        ch_cnt = Counter(e["channel"] for e in s503_other)
        for ch, cnt in ch_cnt.most_common():
            print(f"  渠道 {ch}: {cnt:,}")
        print("\n样例:")
        shown = set()
        for e in s503_other:
            key = (e["channel"], e["model"])
            if key not in shown:
                shown.add(key)
                print(f"  ch={e['channel']} model={e['model']} body({e['body_len']}b): {e['body_head'][:200]}")
            if len(shown) >= 5:
                break

    # ============================================================
    # 7. Overall error summary by channel
    # ============================================================
    print("\n" + "=" * 70)
    print("七、全渠道错误汇总")
    print("=" * 70)
    ch_cat = defaultdict(Counter)
    for e in all_errors:
        ch_cat[e["channel"]][e["cat"]] += 1

    all_cats = sorted(set(e["cat"] for e in all_errors))
    header = f"{'渠道':>6} | {'总计':>7} | " + " | ".join(f"{c[:12]:>12}" for c in all_cats)
    print(header)
    print("-" * len(header))
    for ch in sorted(ch_cat.keys(), key=lambda x: sum(ch_cat[x].values()), reverse=True):
        total = sum(ch_cat[ch].values())
        vals = " | ".join(f"{ch_cat[ch].get(c, 0):>12,}" for c in all_cats)
        print(f"{ch:>6} | {total:>7,} | {vals}")


if __name__ == "__main__":
    main()
