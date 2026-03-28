#!/usr/bin/env python3
"""深入分析报错 - 聚合 Bedrock 错误详情"""

import gzip
import json
import os
import sys
import io
import re
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

CACHE_BASE = Path(__file__).parent / ".cache" / "llm-raw-logs"


def iter_logs(date_str, hours):
    parts = date_str.split("-")
    for h in hours:
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


def normalize_bedrock_error(msg):
    """将 Bedrock 错误归类，去掉 RequestID 等变化部分"""
    msg = re.sub(r"RequestID: [a-f0-9-]+", "RequestID: <ID>", msg)
    msg = re.sub(r"request too large for model.*", "request too large for model ...", msg, flags=re.IGNORECASE)
    # 提取 ValidationException 后面的具体错误
    m = re.search(r"(ValidationException|ThrottlingException|ModelTimeoutException|ModelErrorException|AccessDeniedException|ServiceUnavailableException)[:\s]+(.*)", msg)
    if m:
        exc_type = m.group(1)
        detail = m.group(2).strip()
        detail = re.sub(r"RequestID: <ID>,?\s*", "", detail)
        detail = detail[:200]
        return f"{exc_type}: {detail}"
    # 提取 StatusCode
    m2 = re.search(r"StatusCode: (\d+)", msg)
    if m2:
        sc = m2.group(1)
        return f"Bedrock StatusCode={sc} (detail truncated)"
    return msg[:200]


def extract_error(rec):
    """从记录中提取错误信息"""
    resp_body = rec.get("response_body", "")
    if not resp_body:
        return f"(empty response, status={rec.get('status_code', '?')})"
    try:
        body = json.loads(resp_body) if isinstance(resp_body, str) else resp_body
        if isinstance(body, dict):
            err_obj = body.get("error", {})
            if isinstance(err_obj, dict):
                msg = err_obj.get("message", "") or err_obj.get("type", "")
            elif isinstance(err_obj, str):
                msg = err_obj
            else:
                msg = ""
            if not msg:
                msg = body.get("message", "") or body.get("msg", "")
            return msg if msg else str(body)[:300]
    except:
        return resp_body[:300]
    return "(parse error)"


def analyze(date_str, utc_hours):
    print(f"\n{'='*80}")
    print(f"  分析日期: {date_str}  UTC 小时: {utc_hours}  (北京时间 +8)")
    print(f"{'='*80}\n")

    total = 0
    error_count = 0
    status_counter = Counter()
    error_category = Counter()
    error_by_channel_model = Counter()
    error_samples = defaultdict(list)
    deepseek_errors = []
    non_bedrock_errors = []

    for rec in iter_logs(date_str, utc_hours):
        total += 1
        sc = rec.get("status_code", 0)
        status_counter[sc] += 1

        if sc < 400 and sc != 0:
            continue

        error_count += 1
        model = rec.get("model", "unknown")
        channel = rec.get("channel_name", "unknown")
        ch_id = rec.get("channel_id", "?")
        raw_err = extract_error(rec)

        # 归类错误
        if "Bedrock" in raw_err or "InvokeModel" in raw_err:
            cat = normalize_bedrock_error(raw_err)
        else:
            cat = raw_err[:200]

        error_category[cat] += 1
        key = f"{model} @ [{ch_id}] {channel}"
        error_by_channel_model[key] += 1

        sample = {
            "request_id": rec.get("request_id", ""),
            "model": model,
            "channel": f"[{ch_id}] {channel}",
            "status_code": sc,
            "path": rec.get("path", ""),
            "error_full": raw_err[:500],
        }

        if len(error_samples[cat]) < 3:
            error_samples[cat].append(sample)

        if "deepseek" in model.lower() or "DeepSeek" in channel:
            deepseek_errors.append(sample)
        if "Bedrock" not in raw_err and "InvokeModel" not in raw_err:
            non_bedrock_errors.append(sample)

    # ── 报告 ──
    print(f"📊 总请求数: {total}")
    print(f"✅ 成功请求: {total - error_count}")
    print(f"❌ 错误请求: {error_count}  ({error_count/max(total,1)*100:.2f}%)\n")

    print(f"── 状态码分布 ──")
    for sc, cnt in sorted(status_counter.items()):
        pct = cnt / total * 100
        marker = " ⚠️" if sc >= 400 or sc == 0 else ""
        print(f"  {sc:>4d}: {cnt:>5d}  ({pct:.1f}%){marker}")

    print(f"\n── 错误按 模型@渠道 分布 (Top 15) ──")
    for key, cnt in error_by_channel_model.most_common(15):
        print(f"  {cnt:>4d}  {key}")

    print(f"\n── 错误分类聚合 (Top 20) ──")
    for cat, cnt in error_category.most_common(20):
        print(f"\n  🔴 [{cnt:>4d} 次] {cat}")
        for s in error_samples[cat][:1]:
            print(f"     样本: model={s['model']}, channel={s['channel']}, status={s['status_code']}")
            if s["error_full"] != cat:
                print(f"     完整错误: {s['error_full'][:300]}")

    if non_bedrock_errors:
        print(f"\n── 非 Bedrock 错误详情 ({len(non_bedrock_errors)} 条) ──")
        seen = set()
        for s in non_bedrock_errors:
            key = (s["model"], s["channel"], s["error_full"][:100])
            if key in seen:
                continue
            seen.add(key)
            print(f"\n  model={s['model']}, channel={s['channel']}, status={s['status_code']}")
            print(f"  path={s['path']}")
            print(f"  error: {s['error_full'][:400]}")

    if deepseek_errors:
        print(f"\n── DeepSeek 错误详情 ({len(deepseek_errors)} 条) ──")
        for s in deepseek_errors[:10]:
            print(f"\n  request_id={s['request_id']}")
            print(f"  model={s['model']}, channel={s['channel']}, status={s['status_code']}")
            print(f"  error: {s['error_full'][:400]}")

    print(f"\n{'='*80}")
    print(f"  分析完成")
    print(f"{'='*80}")


if __name__ == "__main__":
    date_str = sys.argv[1] if len(sys.argv) > 1 else "2026-03-21"
    utc_hours = [0, 1]
    if len(sys.argv) > 2:
        utc_hours = [int(x) for x in sys.argv[2].split(",")]
    analyze(date_str, utc_hours)
