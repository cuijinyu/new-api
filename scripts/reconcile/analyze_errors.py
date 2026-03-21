#!/usr/bin/env python3
"""分析指定时段 S3 原始日志中的报错"""

import gzip
import json
import os
import sys
import io
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

CACHE_BASE = Path(__file__).parent / ".cache" / "llm-raw-logs"

def iter_logs(date_str, hours):
    """遍历指定日期、指定 UTC 小时目录下的所有 ndjson.gz 文件"""
    for h in hours:
        hour_dir = CACHE_BASE / date_str.replace("-", "/").replace("/", "/", 1).replace("-", "/") / f"{h:02d}"
        # 路径: .cache/llm-raw-logs/2026/03/21/00/
        parts = date_str.split("-")
        hour_dir = CACHE_BASE / parts[0] / parts[1] / parts[2] / f"{h:02d}"
        if not hour_dir.exists():
            print(f"  [跳过] {hour_dir} 不存在")
            continue
        files = sorted(hour_dir.glob("*.ndjson.gz"))
        print(f"  [扫描] {hour_dir}  共 {len(files)} 个文件")
        for fp in files:
            try:
                with gzip.open(fp, "rt", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                print(f"  [读取失败] {fp.name}: {e}", file=sys.stderr)


def analyze(date_str, utc_hours):
    print(f"\n{'='*70}")
    print(f"  分析日期: {date_str}  UTC 小时: {utc_hours}  (北京时间 +8)")
    print(f"{'='*70}\n")

    total = 0
    error_count = 0
    status_counter = Counter()
    error_status_counter = Counter()
    error_model_counter = Counter()
    error_channel_counter = Counter()
    error_type_counter = Counter()
    error_samples = defaultdict(list)

    for rec in iter_logs(date_str, utc_hours):
        total += 1
        sc = rec.get("status_code", 0)
        status_counter[sc] += 1

        if sc >= 400 or sc == 0:
            error_count += 1
            error_status_counter[sc] += 1
            model = rec.get("model", "unknown")
            channel = rec.get("channel_name", "unknown")
            ch_id = rec.get("channel_id", "?")
            error_model_counter[model] += 1
            error_channel_counter[f"[{ch_id}] {channel}"] += 1

            # 尝试从 response_body 中提取错误信息
            resp_body = rec.get("response_body", "")
            err_msg = ""
            if resp_body:
                try:
                    body = json.loads(resp_body) if isinstance(resp_body, str) else resp_body
                    if isinstance(body, dict):
                        err_obj = body.get("error", {})
                        if isinstance(err_obj, dict):
                            err_msg = err_obj.get("message", "") or err_obj.get("type", "")
                        elif isinstance(err_obj, str):
                            err_msg = err_obj
                        if not err_msg:
                            err_msg = body.get("message", "") or body.get("msg", "")
                except:
                    err_msg = resp_body[:200] if len(resp_body) > 200 else resp_body

            # 截断过长的错误信息用于分类
            err_key = err_msg[:150] if err_msg else f"(status={sc}, no message)"
            error_type_counter[err_key] += 1

            # 保存样本（每种错误最多保留2条）
            if len(error_samples[err_key]) < 2:
                error_samples[err_key].append({
                    "request_id": rec.get("request_id", ""),
                    "model": model,
                    "channel": f"[{ch_id}] {channel}",
                    "status_code": sc,
                    "error": err_msg[:300],
                    "path": rec.get("path", ""),
                })

    # ── 输出报告 ──
    print(f"\n📊 总请求数: {total}")
    print(f"❌ 错误请求数: {error_count}  ({error_count/max(total,1)*100:.2f}%)")

    print(f"\n── 状态码分布 ──")
    for sc, cnt in status_counter.most_common():
        marker = " ⚠️" if sc >= 400 or sc == 0 else ""
        print(f"  {sc}: {cnt}{marker}")

    print(f"\n── 错误状态码分布 ──")
    for sc, cnt in error_status_counter.most_common(20):
        print(f"  {sc}: {cnt}")

    print(f"\n── 错误按模型分布 (Top 20) ──")
    for model, cnt in error_model_counter.most_common(20):
        print(f"  {model}: {cnt}")

    print(f"\n── 错误按渠道分布 (Top 20) ──")
    for ch, cnt in error_channel_counter.most_common(20):
        print(f"  {ch}: {cnt}")

    print(f"\n── 错误类型分布 (Top 30) ──")
    for err, cnt in error_type_counter.most_common(30):
        print(f"\n  [{cnt} 次] {err}")
        samples = error_samples.get(err, [])
        for s in samples[:1]:
            print(f"    样本: request_id={s['request_id']}, model={s['model']}, channel={s['channel']}, path={s['path']}")

    print(f"\n{'='*70}")
    print(f"  分析完成")
    print(f"{'='*70}")


if __name__ == "__main__":
    date_str = sys.argv[1] if len(sys.argv) > 1 else "2026-03-21"
    # 北京时间 8-9 点 = UTC 0-1 点
    utc_hours = [0, 1]
    if len(sys.argv) > 2:
        utc_hours = [int(x) for x in sys.argv[2].split(",")]
    analyze(date_str, utc_hours)
