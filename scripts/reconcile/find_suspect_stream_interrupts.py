#!/usr/bin/env python3
"""
从 S3 原始日志中找出“疑似 stream 自动中断”的请求，并按用户/来源归纳。

判定思路偏保守：
1. 先识别 stream 请求（优先读取 request_body.stream，回退到 response_body 是否像 SSE）
2. 只关注 HTTP 2xx、且没有显式 error 的请求
3. 若流式响应缺少正常结束信号（如 [DONE] / finish_reason / message_stop），
   且响应中已有内容块，则视为高可疑
4. 若还缺少 usage、存在 response_error、SSE 片段 JSON 解析异常，则进一步加分

用法示例：
    python find_suspect_stream_interrupts.py --bucket my-bucket --date 2026-03-10
    python find_suspect_stream_interrupts.py --bucket my-bucket --date-range 2026-03-01 2026-03-10
    python find_suspect_stream_interrupts.py --bucket my-bucket --date 2026-03-10 --detail-output suspects.csv
"""

import argparse
import csv
import gzip
import json
import os
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import boto3


NORMAL_END_EVENTS = {
    "done",
    "message_stop",
    "response.completed",
}

CONTENT_KEYS = {
    "content",
    "text",
    "thinking",
    "reasoning",
    "tool_calls",
    "function_call",
    "refusal",
}


def configure_stdio():
    """尽量强制标准输出/错误输出使用 UTF-8，避免 Windows 终端乱码。"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def parse_args():
    parser = argparse.ArgumentParser(description="查找疑似 stream 自动中断请求")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="对账日期 (YYYY-MM-DD)，默认昨天",
    )
    parser.add_argument(
        "--date-range",
        type=str,
        nargs=2,
        metavar=("START", "END"),
        help="日期范围 (YYYY-MM-DD YYYY-MM-DD)",
    )
    parser.add_argument(
        "--bucket",
        type=str,
        default=os.getenv("RAW_LOG_S3_BUCKET", os.getenv("S3_BUCKET", "")),
    )
    parser.add_argument(
        "--region",
        type=str,
        default=os.getenv("RAW_LOG_S3_REGION", os.getenv("S3_REGION", "us-east-1")),
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default=os.getenv("RAW_LOG_S3_PREFIX", os.getenv("S3_PREFIX", "llm-raw-logs")),
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=os.getenv("RAW_LOG_S3_ENDPOINT", os.getenv("S3_ENDPOINT", "")),
    )
    parser.add_argument("--workers", type=int, default=10, help="并发下载线程数，默认 10")
    parser.add_argument("--user-id", type=int, nargs="+", default=None, help="按用户 ID 过滤")
    parser.add_argument("--channel-id", type=int, nargs="+", default=None, help="按渠道 ID 过滤")
    parser.add_argument("--model", type=str, nargs="+", default=None, help="按模型名过滤")
    parser.add_argument(
        "--min-score",
        type=int,
        default=3,
        help="最低可疑分数，默认 3",
    )
    parser.add_argument(
        "--truncation-threshold",
        type=int,
        default=900000,
        help="响应体达到该长度时标记为可能被截断，默认 900000",
    )
    parser.add_argument(
        "--detail-output",
        type=str,
        default=None,
        help="导出疑似请求明细 CSV",
    )
    parser.add_argument(
        "--summary-output",
        type=str,
        default=None,
        help="导出用户/来源归纳 CSV",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def get_s3_client(region, endpoint):
    kwargs = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    ak = os.getenv("RAW_LOG_S3_ACCESS_KEY_ID", os.getenv("AWS_ACCESS_KEY_ID"))
    sk = os.getenv("RAW_LOG_S3_SECRET_ACCESS_KEY", os.getenv("AWS_SECRET_ACCESS_KEY"))
    if ak and sk:
        kwargs["aws_access_key_id"] = ak
        kwargs["aws_secret_access_key"] = sk
    return boto3.client("s3", **kwargs)


def list_s3_objects(s3, bucket, prefix):
    objects = []
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            objects.append(obj["Key"])
        if not resp.get("IsTruncated"):
            break
        token = resp["NextContinuationToken"]
    return objects


def download_and_parse(s3, bucket, key):
    resp = s3.get_object(Bucket=bucket, Key=key)
    data = gzip.decompress(resp["Body"].read())
    records = []
    for line in data.decode("utf-8", errors="replace").strip().split("\n"):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def parse_dates(args):
    if args.date_range:
        start = datetime.strptime(args.date_range[0], "%Y-%m-%d")
        end = datetime.strptime(args.date_range[1], "%Y-%m-%d")
        if end < start:
            raise ValueError("结束日期不能早于开始日期")
        dates = []
        cursor = start
        while cursor <= end:
            dates.append(cursor.strftime("%Y-%m-%d"))
            cursor += timedelta(days=1)
        return dates
    if args.date:
        return [args.date]
    return [(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")]


def parse_json_object(text):
    if not text:
        return None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def request_stream_flag(record):
    request_body = parse_json_object(record.get("request_body", ""))
    if request_body is not None and "stream" in request_body:
        return bool(request_body.get("stream"))
    body = record.get("response_body", "") or ""
    return "data:" in body or "[DONE]" in body or "event:" in body


def looks_like_sse(body):
    if not body:
        return False
    return "data:" in body or "[DONE]" in body or "event:" in body


def _mark_content(meta, value):
    if value in (None, "", [], {}):
        return
    meta["content_chunks"] += 1


def _mark_finish_reason(meta, value):
    if value in (None, "", "null"):
        return
    finish_reason = str(value)
    meta["finish_reasons"].add(finish_reason)
    meta["normal_end"] = True


def inspect_json_chunk(data, meta):
    if not isinstance(data, dict):
        return

    if data.get("error"):
        meta["has_error"] = True

    data_type = str(data.get("type") or "").strip().lower()
    if data_type in NORMAL_END_EVENTS:
        meta["normal_end"] = True
        if data_type != "done":
            meta["finish_reasons"].add(data_type)

    if data.get("usage"):
        meta["has_usage"] = True
    if data.get("finish_reason"):
        _mark_finish_reason(meta, data.get("finish_reason"))
    if data.get("stop_reason"):
        _mark_finish_reason(meta, data.get("stop_reason"))

    for key in CONTENT_KEYS:
        _mark_content(meta, data.get(key))

    delta = data.get("delta")
    if isinstance(delta, dict):
        if delta.get("usage"):
            meta["has_usage"] = True
        if delta.get("finish_reason"):
            _mark_finish_reason(meta, delta.get("finish_reason"))
        if delta.get("stop_reason"):
            _mark_finish_reason(meta, delta.get("stop_reason"))
        for key in CONTENT_KEYS:
            _mark_content(meta, delta.get(key))

    message = data.get("message")
    if isinstance(message, dict):
        if message.get("usage"):
            meta["has_usage"] = True
        if message.get("stop_reason"):
            _mark_finish_reason(meta, message.get("stop_reason"))
        for key in CONTENT_KEYS:
            _mark_content(meta, message.get(key))

    choices = data.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            if choice.get("finish_reason"):
                _mark_finish_reason(meta, choice.get("finish_reason"))
            delta_obj = choice.get("delta")
            if isinstance(delta_obj, dict):
                for key in CONTENT_KEYS:
                    _mark_content(meta, delta_obj.get(key))
            message_obj = choice.get("message")
            if isinstance(message_obj, dict):
                for key in CONTENT_KEYS:
                    _mark_content(meta, message_obj.get(key))

    response = data.get("response")
    if isinstance(response, dict):
        status = str(response.get("status") or "").strip().lower()
        if status == "completed":
            meta["normal_end"] = True
            meta["finish_reasons"].add("response.completed")


def inspect_stream_response(body):
    meta = {
        "has_sse_data": False,
        "has_done_marker": False,
        "has_usage": False,
        "has_error": False,
        "normal_end": False,
        "content_chunks": 0,
        "data_events": 0,
        "json_parse_errors": 0,
        "finish_reasons": set(),
        "events": Counter(),
    }
    current_event = ""

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            current_event = ""
            continue
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
            if current_event:
                meta["events"][current_event] += 1
                if current_event.lower() in NORMAL_END_EVENTS:
                    meta["normal_end"] = True
                    if current_event.lower() != "done":
                        meta["finish_reasons"].add(current_event)
            continue
        if not line.startswith("data:"):
            continue

        meta["has_sse_data"] = True
        meta["data_events"] += 1
        payload = line[len("data:"):].strip()

        if payload == "[DONE]":
            meta["has_done_marker"] = True
            meta["normal_end"] = True
            continue

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            meta["json_parse_errors"] += 1
            continue

        inspect_json_chunk(data, meta)

        if current_event and current_event.lower() in NORMAL_END_EVENTS:
            meta["normal_end"] = True

    return meta


def shorten_text(text, max_len=120):
    if not text:
        return ""
    text = " ".join(str(text).split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def build_source_label(record):
    channel_id = record.get("channel_id", 0)
    channel_name = record.get("channel_name", "") or "unknown"
    return f"{channel_id}-{channel_name}"


def match_filters(record, user_ids=None, channel_ids=None, models=None):
    if user_ids and record.get("user_id", 0) not in user_ids:
        return False
    if channel_ids and record.get("channel_id", 0) not in channel_ids:
        return False
    if models and record.get("model", "") not in models:
        return False
    return True


def detect_suspect(record, args):
    if not request_stream_flag(record):
        return None

    status_code = int(record.get("status_code") or 0)
    if status_code and status_code >= 400:
        return None

    body = record.get("response_body", "") or ""
    response_error = record.get("response_error", "") or ""

    score = 0
    reasons = []
    if response_error:
        score += 3
        reasons.append("response_error 非空")

    if not body:
        score += 3
        reasons.append("stream 请求响应体为空")
        meta = {
            "has_sse_data": False,
            "has_done_marker": False,
            "has_usage": False,
            "has_error": False,
            "normal_end": False,
            "content_chunks": 0,
            "data_events": 0,
            "json_parse_errors": 0,
            "finish_reasons": set(),
        }
    else:
        if not looks_like_sse(body):
            score += 2
            reasons.append("stream 请求但响应体不像 SSE")
            meta = {
                "has_sse_data": False,
                "has_done_marker": False,
                "has_usage": False,
                "has_error": False,
                "normal_end": False,
                "content_chunks": 0,
                "data_events": 0,
                "json_parse_errors": 0,
                "finish_reasons": set(),
            }
        else:
            meta = inspect_stream_response(body)
            if meta["has_error"]:
                return None

            if not meta["normal_end"]:
                score += 2
                reasons.append("缺少正常结束信号")

            if meta["content_chunks"] > 0 and not meta["normal_end"]:
                score += 2
                reasons.append("已有内容块但未正常结束")

            if not meta["has_done_marker"]:
                score += 1
                reasons.append("缺少 [DONE]")

            if not meta["has_usage"]:
                score += 1
                reasons.append("缺少最终 usage")

            if meta["json_parse_errors"] > 0:
                score += 1
                reasons.append("SSE 片段存在 JSON 解析失败")

    body_len = len(body)
    possible_truncation = body_len >= args.truncation_threshold
    if possible_truncation:
        score -= 1
        reasons.append("响应体较长，可能因日志截断误判")

    if score < args.min_score:
        return None

    return {
        "request_id": record.get("request_id", ""),
        "created_at": record.get("created_at", ""),
        "user_id": record.get("user_id", 0),
        "source": build_source_label(record),
        "channel_id": record.get("channel_id", 0),
        "channel_name": record.get("channel_name", ""),
        "path": record.get("path", ""),
        "model": record.get("model", ""),
        "status_code": status_code,
        "score": score,
        "reasons": " | ".join(dict.fromkeys(reasons)),
        "response_error": shorten_text(response_error, 160),
        "has_done_marker": meta["has_done_marker"],
        "has_usage": meta["has_usage"],
        "normal_end": meta["normal_end"],
        "content_chunks": meta["content_chunks"],
        "data_events": meta["data_events"],
        "json_parse_errors": meta["json_parse_errors"],
        "finish_reasons": ",".join(sorted(meta["finish_reasons"])),
        "possible_truncation": possible_truncation,
        "body_preview": shorten_text(body, 200),
    }


def collect_suspects_for_date(s3, args, date_str):
    prefix = f"{args.prefix}/{datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y/%m/%d')}/"
    keys = list_s3_objects(s3, args.bucket, prefix)
    if args.verbose:
        print(f"[{date_str}] 匹配到 {len(keys)} 个对象")

    user_ids = set(args.user_id) if args.user_id else None
    channel_ids = set(args.channel_id) if args.channel_id else None
    models = set(args.model) if args.model else None

    suspects = []
    total_records = 0
    stream_records = 0
    filtered_out = 0
    download_errors = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_map = {
            pool.submit(download_and_parse, s3, args.bucket, key): key
            for key in keys
        }
        for future in as_completed(future_map):
            key = future_map[future]
            try:
                records = future.result()
            except Exception as exc:
                download_errors += 1
                if args.verbose:
                    print(f"[{date_str}] 下载失败 {key}: {exc}")
                continue

            for record in records:
                total_records += 1
                if not match_filters(record, user_ids, channel_ids, models):
                    filtered_out += 1
                    continue
                if request_stream_flag(record):
                    stream_records += 1
                suspect = detect_suspect(record, args)
                if suspect:
                    suspects.append(suspect)

    return {
        "date": date_str,
        "keys": len(keys),
        "total_records": total_records,
        "stream_records": stream_records,
        "filtered_out": filtered_out,
        "download_errors": download_errors,
        "suspects": suspects,
    }


def build_summary_rows(suspects):
    grouped = defaultdict(
        lambda: {
            "count": 0,
            "score_total": 0,
            "models": Counter(),
            "reasons": Counter(),
            "paths": Counter(),
            "first_seen": "",
            "last_seen": "",
        }
    )

    for item in suspects:
        key = (item["user_id"], item["source"])
        group = grouped[key]
        group["count"] += 1
        group["score_total"] += item["score"]
        if item["model"]:
            group["models"][item["model"]] += 1
        for reason in item["reasons"].split(" | "):
            if reason:
                group["reasons"][reason] += 1
        if item["path"]:
            group["paths"][item["path"]] += 1

        created_at = item["created_at"]
        if created_at:
            if not group["first_seen"] or created_at < group["first_seen"]:
                group["first_seen"] = created_at
            if not group["last_seen"] or created_at > group["last_seen"]:
                group["last_seen"] = created_at

    rows = []
    for (user_id, source), group in grouped.items():
        rows.append(
            {
                "user_id": user_id,
                "source": source,
                "suspect_count": group["count"],
                "avg_score": round(group["score_total"] / group["count"], 2),
                "top_models": ",".join(model for model, _ in group["models"].most_common(3)),
                "top_reasons": " | ".join(reason for reason, _ in group["reasons"].most_common(3)),
                "top_paths": ",".join(path for path, _ in group["paths"].most_common(3)),
                "first_seen": group["first_seen"],
                "last_seen": group["last_seen"],
            }
        )

    rows.sort(key=lambda row: (-row["suspect_count"], -row["avg_score"], row["user_id"], row["source"]))
    return rows


def print_table(rows, headers):
    if not rows:
        print("(无数据)")
        return

    widths = []
    for key, title in headers:
        max_width = len(title)
        for row in rows:
            max_width = max(max_width, len(str(row.get(key, ""))))
        widths.append(min(max_width, 40))

    def fmt_cell(value, width):
        text = str(value)
        if len(text) > width:
            text = text[: width - 3] + "..."
        return text.ljust(width)

    header_line = " | ".join(
        fmt_cell(title, width) for (_, title), width in zip(headers, widths)
    )
    sep_line = "-+-".join("-" * width for width in widths)
    print(header_line)
    print(sep_line)
    for row in rows:
        print(
            " | ".join(
                fmt_cell(row.get(key, ""), width)
                for (key, _), width in zip(headers, widths)
            )
        )


def export_csv(filepath, rows):
    if not rows:
        return
    with open(filepath, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    configure_stdio()
    args = parse_args()
    if not args.bucket:
        raise SystemExit("缺少 --bucket，或请设置 RAW_LOG_S3_BUCKET / S3_BUCKET")

    dates = parse_dates(args)
    s3 = get_s3_client(args.region, args.endpoint)

    all_suspects = []
    grand_total_records = 0
    grand_stream_records = 0
    grand_filtered_out = 0
    grand_download_errors = 0

    for date_str in dates:
        result = collect_suspects_for_date(s3, args, date_str)
        all_suspects.extend(result["suspects"])
        grand_total_records += result["total_records"]
        grand_stream_records += result["stream_records"]
        grand_filtered_out += result["filtered_out"]
        grand_download_errors += result["download_errors"]
        print(
            f"[{date_str}] 总记录 {result['total_records']}, "
            f"stream 请求 {result['stream_records']}, "
            f"疑似中断 {len(result['suspects'])}, "
            f"过滤 {result['filtered_out']}, "
            f"下载失败 {result['download_errors']}"
        )

    all_suspects.sort(
        key=lambda item: (-item["score"], item["created_at"], item["request_id"])
    )
    summary_rows = build_summary_rows(all_suspects)

    print()
    print("=== 总览 ===")
    print(f"日期范围: {dates[0]} -> {dates[-1]}")
    print(f"原始记录总数: {grand_total_records}")
    print(f"stream 请求数: {grand_stream_records}")
    print(f"疑似 stream 自动中断: {len(all_suspects)}")
    print(f"过滤掉: {grand_filtered_out}")
    print(f"下载失败对象数: {grand_download_errors}")

    print()
    print("=== 按用户ID + 来源(渠道)归纳 ===")
    print_table(
        summary_rows[:50],
        [
            ("user_id", "用户ID"),
            ("source", "来源(渠道)"),
            ("suspect_count", "疑似数"),
            ("avg_score", "平均分"),
            ("top_models", "主要模型"),
            ("top_reasons", "主要原因"),
            ("top_paths", "主要路径"),
        ],
    )

    print()
    print("=== 可疑请求样本 ===")
    print_table(
        all_suspects[:50],
        [
            ("created_at", "时间"),
            ("request_id", "Request ID"),
            ("user_id", "用户ID"),
            ("source", "来源(渠道)"),
            ("path", "路径"),
            ("model", "模型"),
            ("score", "分数"),
            ("reasons", "原因"),
        ],
    )

    if args.detail_output:
        export_csv(args.detail_output, all_suspects)
        print(f"\n已导出疑似请求明细: {args.detail_output}")
    if args.summary_output:
        export_csv(args.summary_output, summary_rows)
        print(f"已导出用户/来源归纳: {args.summary_output}")


if __name__ == "__main__":
    main()
