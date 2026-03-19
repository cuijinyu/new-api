import argparse
import json
import os


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
    p.add_argument("--bill", type=str, default=None,
                   help="导出 Excel 账单文件路径 (.xlsx)")
    p.add_argument("--bill-title", type=str, default="API 使用账单",
                   help="账单标题")
    p.add_argument("--bill-currency", type=str, default="USD",
                   choices=["USD", "CNY"],
                   help="账单币种 (USD 或 CNY)")
    p.add_argument("--exchange-rate", type=float, default=7.3,
                   help="USD 转 CNY 汇率，默认 7.3")
    p.add_argument("--workers", type=int, default=10,
                   help="并发下载线程数，默认 10")
    p.add_argument("--processes", type=int, default=0,
                   help="并发进程数，默认 0（禁用；建议大量小文件时设置为 CPU 核数）")
    p.add_argument("--process-threads", type=int, default=4,
                   help="每个进程内部的下载线程数，默认 4")
    p.add_argument("--cache-dir", type=str, default=".cache",
                   help="本地缓存目录，缓存已下载的 S3 文件（默认 .cache）")
    p.add_argument("--no-cache", action="store_true",
                   help="禁用本地缓存，强制从 S3 下载")
    p.add_argument("--time-from", type=str, default=None,
                   help="起始时间过滤，格式 HH:MM:SS 或 YYYY-MM-DDTHH:MM:SS")
    p.add_argument("--time-to", type=str, default=None,
                   help="截止时间过滤，格式 HH:MM:SS 或 YYYY-MM-DDTHH:MM:SS")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--check-db", action="store_true",
                   help="从 SQLite logs_analysis.db 检查重试重复计费/失败计费")
    p.add_argument("--db-path", type=str, default=None,
                   help="SQLite 数据库路径（默认 scripts/logs_analysis.db）")
    p.add_argument("--retry-window-sec", type=int, default=120,
                   help="判定重试重复计费的时间窗口（秒），默认 120")
    p.add_argument("--failure-mode", type=str, default="strict",
                   choices=["strict", "loose"],
                   help="失败计费判定口径：strict(默认, 仅明确失败信号) / loose(宽松, 含零token与frt=-1000)")
    p.add_argument("--cross-check-raw", action="store_true",
                   help="用 S3 原始明细与 logs 账务数据做对照检查")
    p.add_argument("--cross-check-bucket-sec", type=int, default=60,
                   help="原始明细对照的时间分桶秒数，默认 60")
    p.add_argument("--check-output", type=str, default=None,
                   help="检查结果导出 CSV 文件前缀（例如 check_0311）")
    return p.parse_args()


def load_pricing(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)
