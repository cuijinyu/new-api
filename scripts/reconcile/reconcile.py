#!/usr/bin/env python3
"""
每日对账脚本：从 S3 原始日志中提取 usage 信息，按模型价格独立计算费用。

支持：
  - 分段计费 (tiered_pricing)
  - Claude 200K 自动倍率 (input x2, output x1.5)
  - 缓存写入 5m / 1h TTL 区分
  - Claude / OpenAI Web Search 工具调用计费

用法:
    python reconcile.py                          # 对账昨天
    python reconcile.py --date 2026-03-10        # 对账指定日期
    python reconcile.py --date 2026-03-10 --output report.csv

环境变量 (或通过命令行参数):
    S3_BUCKET, S3_REGION, S3_PREFIX, S3_ENDPOINT,
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
"""

import argparse
import csv
import gzip
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

import boto3
from tabulate import tabulate

# Claude 200K 阈值与倍率，对齐 ratio_setting/model_ratio.go
CLAUDE_200K_THRESHOLD = 200_000
CLAUDE_200K_INPUT_MULT = 2.0
CLAUDE_200K_OUTPUT_MULT = 1.5

CLAUDE_MODEL_RE = re.compile(r"claude", re.IGNORECASE)


def parse_args():
    p = argparse.ArgumentParser(description="S3 原始日志费用计算")
    p.add_argument("--date", type=str, default=None,
                   help="对账日期 (YYYY-MM-DD)，默认昨天")
    p.add_argument("--date-range", type=str, nargs=2, metavar=("START", "END"),
                   help="日期范围 (YYYY-MM-DD YYYY-MM-DD)")
    p.add_argument("--bucket", type=str,
                   default=os.getenv("RAW_LOG_S3_BUCKET", os.getenv("S3_BUCKET", "")))
    p.add_argument("--region", type=str,
                   default=os.getenv("RAW_LOG_S3_REGION", os.getenv("S3_REGION", "us-east-1")))
    p.add_argument("--prefix", type=str,
                   default=os.getenv("RAW_LOG_S3_PREFIX", os.getenv("S3_PREFIX", "llm-raw-logs")))
    p.add_argument("--endpoint", type=str,
                   default=os.getenv("RAW_LOG_S3_ENDPOINT", os.getenv("S3_ENDPOINT", "")))
    p.add_argument("--pricing", type=str, default="pricing.json",
                   help="模型价格配置文件路径")
    p.add_argument("--output", type=str, default=None,
                   help="输出 CSV 文件路径")
    p.add_argument("--group-by", type=str, default="model",
                   choices=["model", "channel", "user", "hour"],
                   help="汇总维度")
    p.add_argument("--user-id", type=int, nargs="+", default=None,
                   help="按用户 ID 过滤（可指定多个）")
    p.add_argument("--model", type=str, nargs="+", default=None,
                   help="按模型名过滤（可指定多个）")
    p.add_argument("--channel-id", type=int, nargs="+", default=None,
                   help="按渠道 ID 过滤（可指定多个）")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def load_pricing(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


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
        kw = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if token:
            kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
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


# ---------------------------------------------------------------------------
# Usage 提取
# ---------------------------------------------------------------------------

def extract_usage(record):
    """从 response_body 中提取上游返回的 token 用量和工具调用信息"""
    body = record.get("response_body", "")
    if not body:
        return None

    # 非流式：完整 JSON
    try:
        obj = json.loads(body)
        usage = obj.get("usage")
        if usage:
            return normalize_usage(usage)
    except json.JSONDecodeError:
        pass

    # 流式 SSE
    return extract_usage_from_sse(body)


def extract_usage_from_sse(text):
    last_usage = None
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            continue
        try:
            data = json.loads(payload)
            if "usage" in data and data["usage"]:
                last_usage = data["usage"]
            msg = data.get("message")
            if isinstance(msg, dict) and msg.get("usage"):
                last_usage = msg["usage"]
        except json.JSONDecodeError:
            continue
    if last_usage:
        return normalize_usage(last_usage)
    return None


def normalize_usage(usage):
    """提取标准化的 token 用量，包括 Claude 缓存 5m/1h 细分和工具调用"""
    cache_creation_total = int(usage.get("cache_creation_input_tokens") or 0)

    # Claude 缓存 5m/1h 细分：usage.cache_creation.ephemeral_5m/1h_input_tokens
    cache_creation_obj = usage.get("cache_creation")
    cache_5m = 0
    cache_1h = 0
    if isinstance(cache_creation_obj, dict):
        cache_5m = int(cache_creation_obj.get("ephemeral_5m_input_tokens") or 0)
        cache_1h = int(cache_creation_obj.get("ephemeral_1h_input_tokens") or 0)
        if cache_creation_total == 0 and (cache_5m or cache_1h):
            cache_creation_total = cache_5m + cache_1h

    # Web search 调用次数
    web_search_requests = 0
    server_tool_use = usage.get("server_tool_use")
    if isinstance(server_tool_use, dict):
        web_search_requests = int(server_tool_use.get("web_search_requests") or 0)

    return {
        "input_tokens": int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
        "cache_read_tokens": int(usage.get("cache_read_input_tokens") or 0),
        "cache_creation_tokens": cache_creation_total,
        "cache_creation_5m_tokens": cache_5m,
        "cache_creation_1h_tokens": cache_1h,
        "web_search_requests": web_search_requests,
    }


# ---------------------------------------------------------------------------
# 分段计费查找
# ---------------------------------------------------------------------------

def find_price_tier(model_pricing, input_tokens):
    """按 input_tokens 匹配分段价格区间，返回匹配的 tier dict 或 None"""
    tiers = model_pricing.get("tiered_pricing")
    if not tiers:
        return None

    input_tokens_k = input_tokens // 1000
    matched = None
    for tier in tiers:
        min_k = tier.get("min_tokens_k", 0)
        max_k = tier.get("max_tokens_k", -1)
        if input_tokens_k >= min_k:
            if max_k == -1 or input_tokens_k < max_k:
                matched = tier
                break

    # 未匹配则用最后一个区间（最高价格段）
    if matched is None and tiers:
        for t in reversed(tiers):
            if t.get("max_tokens_k", -1) == -1:
                return t
        return tiers[-1]

    return matched


def is_claude_model(model_name):
    return bool(CLAUDE_MODEL_RE.search(model_name))


# ---------------------------------------------------------------------------
# 费用计算
# ---------------------------------------------------------------------------

def calc_cost(usage, model_pricing, model_name, web_search_cfg):
    """
    根据 usage 和模型价格计算费用 (USD)。

    三条路径对齐 compatible_handler.go:
      1. 有 tiered_pricing -> 按分段价格
      2. Claude 模型无 tiered_pricing -> 自动 200K 倍率
      3. 普通模型 -> 基础价格
    """
    input_tokens = usage["input_tokens"]
    output_tokens = usage["output_tokens"]
    cache_read = usage["cache_read_tokens"]
    cache_creation_total = usage["cache_creation_tokens"]
    cache_5m = usage["cache_creation_5m_tokens"]
    cache_1h = usage["cache_creation_1h_tokens"]
    remaining_cache = max(cache_creation_total - cache_5m - cache_1h, 0)

    net_input = max(input_tokens - cache_read - cache_creation_total, 0)

    tier = find_price_tier(model_pricing, input_tokens)

    if tier is not None:
        # 路径 1：分段计费
        ip = tier.get("input_price", 0)
        op = tier.get("output_price", 0)
        chp = tier.get("cache_hit_price", 0)
        cwp = tier.get("cache_write_price", 0)
        cwp_1h = tier.get("cache_write_price_1h") or cwp

        cost = (
            net_input / 1_000_000 * ip
            + output_tokens / 1_000_000 * op
            + cache_read / 1_000_000 * chp
            + remaining_cache / 1_000_000 * cwp
            + cache_5m / 1_000_000 * cwp
            + cache_1h / 1_000_000 * cwp_1h
        )
    elif is_claude_model(model_name) and input_tokens >= CLAUDE_200K_THRESHOLD:
        # 路径 2：Claude 200K 自动倍率
        ip = model_pricing.get("input_price", 0) * CLAUDE_200K_INPUT_MULT
        op = model_pricing.get("output_price", 0) * CLAUDE_200K_OUTPUT_MULT
        chp = model_pricing.get("cache_hit_price", 0)
        cwp = model_pricing.get("cache_write_price", 0)
        cwp_1h = model_pricing.get("cache_write_price_1h") or cwp

        cost = (
            net_input / 1_000_000 * ip
            + output_tokens / 1_000_000 * op
            + cache_read / 1_000_000 * chp
            + remaining_cache / 1_000_000 * cwp
            + cache_5m / 1_000_000 * cwp
            + cache_1h / 1_000_000 * cwp_1h
        )
    else:
        # 路径 3：普通模型
        ip = model_pricing.get("input_price", 0)
        op = model_pricing.get("output_price", 0)
        chp = model_pricing.get("cache_hit_price", 0)
        cwp = model_pricing.get("cache_write_price", 0)
        cwp_1h = model_pricing.get("cache_write_price_1h") or cwp

        cost = (
            net_input / 1_000_000 * ip
            + output_tokens / 1_000_000 * op
            + cache_read / 1_000_000 * chp
            + remaining_cache / 1_000_000 * cwp
            + cache_5m / 1_000_000 * cwp
            + cache_1h / 1_000_000 * cwp_1h
        )

    # Web Search 附加费用
    ws_count = usage.get("web_search_requests", 0)
    if ws_count > 0 and web_search_cfg:
        ws_cost = calc_web_search_cost(model_name, ws_count, web_search_cfg)
        cost += ws_cost

    return cost


def calc_web_search_cost(model_name, call_count, web_search_cfg):
    """计算 Web Search 工具调用费用 (USD)"""
    if is_claude_model(model_name):
        price_per_k = web_search_cfg.get("claude", 10.0)
    elif (model_name.startswith("o3") or model_name.startswith("o4")
          or model_name.startswith("gpt-5")):
        price_per_k = web_search_cfg.get("openai_normal", 10.0)
    else:
        price_per_k = web_search_cfg.get("openai_high", 25.0)

    return call_count / 1000.0 * price_per_k


# ---------------------------------------------------------------------------
# 汇总维度
# ---------------------------------------------------------------------------

def get_group_key(record, usage, group_by):
    if group_by == "model":
        return record.get("model", "unknown")
    elif group_by == "channel":
        return f"{record.get('channel_id', 0)}-{record.get('channel_name', 'unknown')}"
    elif group_by == "user":
        return str(record.get("user_id", 0))
    elif group_by == "hour":
        try:
            dt = datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:00")
        except (ValueError, KeyError):
            return "unknown"
    return "unknown"


def new_stat_bucket():
    return {
        "count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "web_search_calls": 0,
        "cost": 0.0,
        "web_search_cost": 0.0,
        "errors": 0,
        "no_pricing": 0,
    }


# ---------------------------------------------------------------------------
# 处理单天数据
# ---------------------------------------------------------------------------

def process_date(s3, bucket, prefix, date_str, pricing_cfg, group_by, verbose,
                 filter_user_ids=None, filter_models=None, filter_channel_ids=None):
    """处理单天数据，返回汇总结果和明细"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    s3_prefix = f"{prefix}/{dt.strftime('%Y/%m/%d')}/"

    keys = list_s3_objects(s3, bucket, s3_prefix)
    if verbose:
        print(f"  [{date_str}] 找到 {len(keys)} 个文件")

    models_pricing = pricing_cfg.get("models", {})
    web_search_cfg = pricing_cfg.get("web_search", {})

    user_id_set = set(filter_user_ids) if filter_user_ids else None
    model_set = set(filter_models) if filter_models else None
    channel_id_set = set(filter_channel_ids) if filter_channel_ids else None

    stats = defaultdict(new_stat_bucket)
    details = []
    total_records = 0
    filtered_out = 0
    parse_failures = 0

    for key in keys:
        records = download_and_parse(s3, bucket, key)
        total_records += len(records)

        for rec in records:
            if user_id_set and rec.get("user_id", 0) not in user_id_set:
                filtered_out += 1
                continue
            if channel_id_set and rec.get("channel_id", 0) not in channel_id_set:
                filtered_out += 1
                continue

            model = rec.get("model", "unknown")
            if model_set and model not in model_set:
                filtered_out += 1
                continue

            usage = extract_usage(rec)

            if usage is None:
                parse_failures += 1
                continue

            model_pricing = models_pricing.get(model)
            group_key = get_group_key(rec, usage, group_by)
            s = stats[group_key]
            s["count"] += 1
            s["input_tokens"] += usage["input_tokens"]
            s["output_tokens"] += usage["output_tokens"]
            s["cache_read_tokens"] += usage["cache_read_tokens"]
            s["cache_creation_tokens"] += usage["cache_creation_tokens"]
            s["web_search_calls"] += usage.get("web_search_requests", 0)

            if rec.get("status_code", 200) >= 400:
                s["errors"] += 1

            if model_pricing:
                cost = calc_cost(usage, model_pricing, model, web_search_cfg)
                s["cost"] += cost

                ws_count = usage.get("web_search_requests", 0)
                ws_cost = 0.0
                if ws_count > 0 and web_search_cfg:
                    ws_cost = calc_web_search_cost(model, ws_count, web_search_cfg)
                s["web_search_cost"] += ws_cost

                details.append({
                    "date": date_str,
                    "request_id": rec.get("request_id", ""),
                    "model": model,
                    "channel_id": rec.get("channel_id", 0),
                    "channel_name": rec.get("channel_name", ""),
                    "user_id": rec.get("user_id", 0),
                    "status_code": rec.get("status_code", 0),
                    "input_tokens": usage["input_tokens"],
                    "output_tokens": usage["output_tokens"],
                    "cache_read_tokens": usage["cache_read_tokens"],
                    "cache_creation_tokens": usage["cache_creation_tokens"],
                    "cache_5m_tokens": usage["cache_creation_5m_tokens"],
                    "cache_1h_tokens": usage["cache_creation_1h_tokens"],
                    "web_search_calls": ws_count,
                    "cost_usd": round(cost, 8),
                    "group_key": group_key,
                })
            else:
                s["no_pricing"] += 1

    return stats, details, total_records, parse_failures, filtered_out


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------

def print_report(date_label, stats, total_records, parse_failures, group_by,
                 filtered_out=0, filters=None):
    print(f"\n{'='*80}")
    print(f"  费用报告 - {date_label}")
    print(f"{'='*80}")
    summary = f"  日志总数: {total_records}    解析失败: {parse_failures}"
    if filtered_out:
        summary += f"    过滤掉: {filtered_out}"
    print(summary)
    if filters:
        print(f"  过滤条件: {filters}")
    print()

    headers = [
        group_by.capitalize(), "请求数", "输入tokens", "输出tokens",
        "缓存读取", "缓存写入", "WebSearch", "错误", "无价格", "费用(USD)"
    ]
    rows = []
    total_cost = 0.0
    total_count = 0
    total_input = 0
    total_output = 0
    total_ws = 0

    for key in sorted(stats.keys()):
        s = stats[key]
        total_cost += s["cost"]
        total_count += s["count"]
        total_input += s["input_tokens"]
        total_output += s["output_tokens"]
        total_ws += s["web_search_calls"]
        rows.append([
            key,
            f"{s['count']:,}",
            f"{s['input_tokens']:,}",
            f"{s['output_tokens']:,}",
            f"{s['cache_read_tokens']:,}",
            f"{s['cache_creation_tokens']:,}",
            s["web_search_calls"] or "",
            s["errors"] or "",
            s["no_pricing"] or "",
            f"${s['cost']:.6f}",
        ])

    rows.append([
        "TOTAL",
        f"{total_count:,}",
        f"{total_input:,}",
        f"{total_output:,}",
        "", "",
        total_ws or "",
        "", "",
        f"${total_cost:.6f}",
    ])

    print(tabulate(rows, headers=headers, tablefmt="simple"))
    print(f"\n  总费用: ${total_cost:.6f} (约 ¥{total_cost * 7.3:.4f})")
    print(f"{'='*80}\n")


def export_csv(filepath, all_details, all_stats, group_by):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)

        w.writerow(["=== 汇总 ==="])
        w.writerow([group_by, "count", "input_tokens", "output_tokens",
                     "cache_read", "cache_write", "web_search_calls",
                     "errors", "no_pricing", "cost_usd", "web_search_cost_usd"])
        for key in sorted(all_stats.keys()):
            s = all_stats[key]
            w.writerow([key, s["count"], s["input_tokens"], s["output_tokens"],
                        s["cache_read_tokens"], s["cache_creation_tokens"],
                        s["web_search_calls"],
                        s["errors"], s["no_pricing"],
                        round(s["cost"], 8), round(s["web_search_cost"], 8)])

        w.writerow([])
        w.writerow(["=== 明细 ==="])
        if all_details:
            w.writerow(all_details[0].keys())
            for d in all_details:
                w.writerow(d.values())

    print(f"  CSV 已导出: {filepath}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    if not args.bucket:
        print("错误: 请设置 S3_BUCKET 或 --bucket", file=sys.stderr)
        sys.exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    pricing_path = args.pricing if os.path.isabs(args.pricing) else os.path.join(script_dir, args.pricing)
    pricing_cfg = load_pricing(pricing_path)
    models_pricing = pricing_cfg.get("models", {})
    print(f"  已加载 {len(models_pricing)} 个模型价格配置")

    ws_cfg = pricing_cfg.get("web_search")
    if ws_cfg:
        print(f"  Web Search 计费: Claude ${ws_cfg.get('claude', 0)}/千次, "
              f"OpenAI ${ws_cfg.get('openai_high', 0)}/${ws_cfg.get('openai_normal', 0)}/千次")

    # 确定日期范围
    if args.date_range:
        start = datetime.strptime(args.date_range[0], "%Y-%m-%d")
        end = datetime.strptime(args.date_range[1], "%Y-%m-%d")
        dates = []
        cur = start
        while cur <= end:
            dates.append(cur.strftime("%Y-%m-%d"))
            cur += timedelta(days=1)
    elif args.date:
        dates = [args.date]
    else:
        dates = [(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")]

    s3 = get_s3_client(args.region, args.endpoint)

    # 构建过滤条件描述
    filter_parts = []
    if args.user_id:
        filter_parts.append(f"user_id={args.user_id}")
    if args.model:
        filter_parts.append(f"model={args.model}")
    if args.channel_id:
        filter_parts.append(f"channel_id={args.channel_id}")
    filters_desc = ", ".join(filter_parts) if filter_parts else None
    if filters_desc:
        print(f"  过滤条件: {filters_desc}")

    all_stats = defaultdict(new_stat_bucket)
    all_details = []
    grand_total_records = 0
    grand_parse_failures = 0
    grand_filtered_out = 0

    for date_str in dates:
        stats, details, total_records, parse_failures, filtered_out = process_date(
            s3, args.bucket, args.prefix, date_str, pricing_cfg, args.group_by, args.verbose,
            filter_user_ids=args.user_id, filter_models=args.model,
            filter_channel_ids=args.channel_id,
        )
        grand_total_records += total_records
        grand_parse_failures += parse_failures
        grand_filtered_out += filtered_out
        all_details.extend(details)

        for key, s in stats.items():
            for field in s:
                all_stats[key][field] += s[field]

    date_label = dates[0] if len(dates) == 1 else f"{dates[0]} ~ {dates[-1]}"
    print_report(date_label, all_stats, grand_total_records, grand_parse_failures, args.group_by,
                 filtered_out=grand_filtered_out, filters=filters_desc)

    if args.output:
        export_csv(args.output, all_details, all_stats, args.group_by)


if __name__ == "__main__":
    main()
