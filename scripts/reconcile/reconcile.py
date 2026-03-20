#!/usr/bin/env python3
"""
每日对账主入口：
- S3 日志加载
- usage 提取与费用计算
- 汇总与导出
- DB 异常检查（重试重复计费 / 失败计费）
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta

from cli import load_pricing, parse_args
from db_checks import run_db_checks, run_raw_detail_cross_check


def _build_dates(args):
    if args.date_range:
        start = datetime.strptime(args.date_range[0], "%Y-%m-%d")
        end = datetime.strptime(args.date_range[1], "%Y-%m-%d")
        dates = []
        cur = start
        while cur <= end:
            dates.append(cur.strftime("%Y-%m-%d"))
            cur += timedelta(days=1)
        return dates
    if args.date:
        return [args.date]
    return [(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")]


def _build_filter_desc(args, time_from, time_to):
    parts = []
    if args.user_id:
        parts.append(f"user_id={args.user_id}")
    if args.model:
        parts.append(f"model={args.model}")
    if args.channel_id:
        parts.append(f"channel_id={args.channel_id}")
    if time_from:
        parts.append(f"from={time_from}")
    if time_to:
        parts.append(f"to={time_to}")
    return ", ".join(parts) if parts else None


def _prefetch_with_node(dates, args, cache_dir):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mjs = os.path.join(script_dir, "s3_download.mjs")
    if not os.path.exists(mjs):
        return

    cmd = ["node", mjs, "--bucket", args.bucket, "--region", args.region,
           "--prefix", args.prefix, "--cache-dir", os.path.relpath(cache_dir, script_dir)]
    if args.endpoint:
        cmd += ["--endpoint", args.endpoint]
    if len(dates) == 1:
        cmd += ["--date", dates[0]]
    else:
        cmd += ["--date-range", dates[0], dates[-1]]

    print(f"  [Node.js] 启动高速 S3 下载器预热缓存 ...")
    try:
        subprocess.run(cmd, cwd=script_dir, check=True)
    except FileNotFoundError:
        print("  [Node.js] node 未找到，回退到 Python 下载", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(f"  [Node.js] 下载器退出码 {e.returncode}，回退到 Python 下载", file=sys.stderr)


def _run_reconcile(args):
    from collections import Counter, defaultdict

    from data_loader import get_s3_client
    from processor import merge_stats, new_stat_bucket, process_date
    from report_export import export_bill, export_csv, print_report

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

    dates = _build_dates(args)
    s3 = get_s3_client(args.region, args.endpoint)

    cache_dir = None
    if not args.no_cache:
        cache_dir = os.path.join(script_dir, args.cache_dir)
        os.makedirs(cache_dir, exist_ok=True)
        if args.verbose:
            print(f"  缓存目录: {cache_dir}")

    time_from = args.time_from
    time_to = args.time_to
    if time_from and len(time_from) <= 8:
        time_from = f"{dates[0]}T{time_from}"
    if time_to and len(time_to) <= 8:
        time_to = f"{dates[-1]}T{time_to}"

    filters_desc = _build_filter_desc(args, time_from, time_to)
    if filters_desc:
        print(f"  过滤条件: {filters_desc}")

    all_stats = defaultdict(new_stat_bucket)
    all_details = []
    grand_total_records = 0
    grand_parse_failures = 0
    grand_filtered_out = 0
    grand_error_categories = Counter()
    collect_details = bool(args.output or args.bill)

    if cache_dir and shutil.which("node"):
        _prefetch_with_node(dates, args, cache_dir)

    if args.workers > 1:
        print(f"  并发下载: {args.workers} 线程")
    if args.processes > 1:
        print(f"  并发处理: {args.processes} 进程")
    if not collect_details:
        print("  明细导出: 已关闭（仅控制台汇总，减少内存占用）")

    for date_str in dates:
        stats, details, total_records, parse_failures, filtered_out, err_cats = process_date(
            s3, args.bucket, args.prefix, date_str, pricing_cfg, args.group_by, args.verbose,
            filter_user_ids=args.user_id, filter_models=args.model,
            filter_channel_ids=args.channel_id,
            workers=args.workers, region=args.region, endpoint=args.endpoint,
            cache_dir=cache_dir, time_from=time_from, time_to=time_to,
            processes=args.processes, collect_details=collect_details,
            process_threads=args.process_threads,
        )
        grand_total_records += total_records
        grand_parse_failures += parse_failures
        grand_filtered_out += filtered_out
        grand_error_categories += err_cats
        if collect_details and details:
            all_details.extend(details)
        merge_stats(all_stats, stats)

    date_label = dates[0] if len(dates) == 1 else f"{dates[0]} ~ {dates[-1]}"
    print_report(date_label, all_stats, grand_total_records, grand_parse_failures, args.group_by,
                 filtered_out=grand_filtered_out, filters=filters_desc,
                 error_categories=grand_error_categories)

    if args.output:
        export_csv(args.output, all_details, all_stats, args.group_by)
    if args.bill:
        export_bill(args.bill, all_details, all_stats, date_label, args)


def main():
    args = parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_db_path = os.path.normpath(os.path.join(script_dir, "..", "logs_analysis.db"))

    if args.check_db:
        check_date = args.date or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        db_path = args.db_path if args.db_path else default_db_path
        cache_dir = None
        if not args.no_cache:
            cache_dir = os.path.join(script_dir, args.cache_dir)
            os.makedirs(cache_dir, exist_ok=True)
        run_db_checks(
            db_path=db_path,
            date_str=check_date,
            retry_window_sec=max(args.retry_window_sec, 1),
            check_output_prefix=args.check_output,
            failure_mode=args.failure_mode,
        )
        if args.cross_check_raw:
            run_raw_detail_cross_check(
                db_path=db_path,
                date_str=check_date,
                bucket=args.bucket,
                prefix=args.prefix,
                region=args.region,
                endpoint=args.endpoint,
                cache_dir=cache_dir,
                bucket_sec=max(args.cross_check_bucket_sec, 1),
                output_prefix=args.check_output,
            )
        return

    _run_reconcile(args)


if __name__ == "__main__":
    main()
