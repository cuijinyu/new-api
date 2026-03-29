#!/usr/bin/env python3
"""
定时任务调度器 — 自动生成日报/月报并上传 S3

用法:
    python bill_cron.py                  # 前台运行
    python bill_cron.py --run-daily      # 立即执行一次日报
    python bill_cron.py --run-monthly    # 立即执行一次月报
    nohup python bill_cron.py &          # 后台运行
"""

import argparse
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import boto3
import schedule

from athena_engine import REGION, AK, SK, RESULT_BUCKET
import report_builder

REPORT_BUCKET = os.getenv("REPORT_S3_BUCKET", RESULT_BUCKET)
REPORT_PREFIX = os.getenv("REPORT_S3_PREFIX", "reports")

DAILY_SCHEDULE = os.getenv("CRON_DAILY_TIME", "02:00")   # UTC
MONTHLY_DAY = int(os.getenv("CRON_MONTHLY_DAY", "2"))
MONTHLY_SCHEDULE = os.getenv("CRON_MONTHLY_TIME", "03:00")  # UTC

FLAT_TIER = os.getenv("CRON_FLAT_TIER", "").lower() in ("1", "true", "yes")
FLAT_TIER_SINCE = os.getenv("CRON_FLAT_TIER_SINCE", "").strip() or None


def _get_s3():
    kw = {"region_name": REGION}
    if AK and SK:
        kw["aws_access_key_id"] = AK
        kw["aws_secret_access_key"] = SK
    endpoint = os.getenv("RAW_LOG_S3_ENDPOINT", "")
    if endpoint:
        kw["endpoint_url"] = endpoint
    return boto3.client("s3", **kw)


def _upload_to_s3(local_path: str, s3_key: str):
    s3 = _get_s3()
    s3.upload_file(local_path, REPORT_BUCKET, s3_key)
    print(f"  [S3] 已上传: s3://{REPORT_BUCKET}/{s3_key}")


def _log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}")


# ---------------------------------------------------------------------------
# Daily report job
# ---------------------------------------------------------------------------

def run_daily_report(date: str = None):
    if date is None:
        date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    _log(f"开始生成日报: {date}")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = report_builder.generate_daily_report(date, tmpdir)
            filename = Path(path).name
            s3_key = f"{REPORT_PREFIX}/daily/{date}/{filename}"
            _upload_to_s3(path, s3_key)
        _log(f"日报完成: {date}")
    except Exception as e:
        _log(f"日报失败: {date} — {e}")
        import traceback
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Monthly report job
# ---------------------------------------------------------------------------

def run_monthly_report(year_month: str = None,
                       flat_tier: bool = None, flat_tier_since: str = None):
    if year_month is None:
        today = datetime.now(timezone.utc)
        last_month = (today.replace(day=1) - timedelta(days=1))
        year_month = last_month.strftime("%Y-%m")

    ft = flat_tier if flat_tier is not None else FLAT_TIER
    fts = flat_tier_since if flat_tier_since is not None else FLAT_TIER_SINCE
    if fts:
        ft = True

    tier_msg = ""
    if ft:
        tier_msg = f" [降档{'自 ' + fts if fts else '全量'}]"

    _log(f"开始生成月报: {year_month}{tier_msg}")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = report_builder.generate_monthly_bill(
                year_month, tmpdir,
                flat_tier=ft, flat_tier_since=fts)
            filename = Path(path).name
            s3_key = f"{REPORT_PREFIX}/monthly/{year_month}/{filename}"
            _upload_to_s3(path, s3_key)

            anom_path = report_builder.generate_anomaly_report(year_month, tmpdir)
            anom_filename = Path(anom_path).name
            anom_key = f"{REPORT_PREFIX}/monthly/{year_month}/{anom_filename}"
            _upload_to_s3(anom_path, anom_key)

        _log(f"月报完成: {year_month}{tier_msg}")
    except Exception as e:
        _log(f"月报失败: {year_month} — {e}")
        import traceback
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

def _daily_job():
    run_daily_report()


def _monthly_check():
    """Run monthly report if today is the configured day."""
    today = datetime.now(timezone.utc)
    if today.day == MONTHLY_DAY:
        run_monthly_report()


def run_scheduler():
    tier_info = ""
    if FLAT_TIER:
        tier_info = f", 降档{'自 ' + FLAT_TIER_SINCE if FLAT_TIER_SINCE else '全量'}"
    _log(f"调度器启动 — 日报: 每天 {DAILY_SCHEDULE} UTC, "
         f"月报: 每月 {MONTHLY_DAY} 号 {MONTHLY_SCHEDULE} UTC{tier_info}")
    _log(f"报表上传: s3://{REPORT_BUCKET}/{REPORT_PREFIX}/")

    schedule.every().day.at(DAILY_SCHEDULE).do(_daily_job)
    schedule.every().day.at(MONTHLY_SCHEDULE).do(_monthly_check)

    while True:
        schedule.run_pending()
        time.sleep(30)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="EZModel 报表定时任务")
    parser.add_argument("--run-daily", action="store_true",
                        help="立即执行一次日报（昨天）")
    parser.add_argument("--run-monthly", action="store_true",
                        help="立即执行一次月报（上月）")
    parser.add_argument("--date", help="指定日报日期 YYYY-MM-DD")
    parser.add_argument("--month", help="指定月报月份 YYYY-MM")
    parser.add_argument("--flat-tier", action="store_true",
                        help="降档模式：分段模型强制使用低档价")
    parser.add_argument("--flat-tier-since", type=str,
                        help="降档起始日期 YYYY-MM-DD（隐含 --flat-tier）")
    args = parser.parse_args()

    ft = args.flat_tier or bool(args.flat_tier_since)
    fts = args.flat_tier_since

    if args.run_daily:
        run_daily_report(args.date)
    elif args.run_monthly:
        run_monthly_report(args.month, flat_tier=ft or None, flat_tier_since=fts)
    else:
        run_scheduler()


if __name__ == "__main__":
    main()
