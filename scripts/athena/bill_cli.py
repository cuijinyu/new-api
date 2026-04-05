#!/usr/bin/env python3
"""
EZModel 账单 CLI 工具

用法:
    python bill_cli.py bill --month 2026-03 -o bills/
    python bill_cli.py bill --month 2026-03 --user-id 89 -o bills/
    python bill_cli.py bill --month 2026-03 --channel-id 25 -o bills/
    python bill_cli.py daily --date 2026-03-29 -o reports/
    python bill_cli.py anomaly --month 2026-03 -o reports/
    python bill_cli.py ranking --month 2026-03
    python bill_cli.py users --month 2026-03
    python bill_cli.py channels --month 2026-03
    python bill_cli.py kpi --month 2026-03
    python bill_cli.py recalc --start 2026-03-01 --end 2026-03-15 --flat-tier -o output/
    python bill_cli.py import-bill vendor.csv --channel-id 25 --month 2026-03
    python bill_cli.py crosscheck --month 2026-03 --vendor vendor.csv --channel-id 25 -o output/
    python bill_cli.py query "SELECT ..." -o result.xlsx
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import pandas as pd
from tabulate import tabulate

from athena_engine import run_query_cached, run_safe_query, run_query_df
import queries
import report_builder
import pricing_engine
import cost_import


def _yesterday() -> str:
    return (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")


def _last_month() -> str:
    today = datetime.utcnow()
    first = today.replace(day=1)
    last_month = first - timedelta(days=1)
    return last_month.strftime("%Y-%m")


def _print_df(df, title=None):
    if title:
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")
    if df.empty:
        print("  (无数据)")
        return
    print(tabulate(df, headers="keys", tablefmt="simple", showindex=False,
                   floatfmt=".4f"))
    print()


def _export_df_excel(df, filepath):
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    df.to_excel(filepath, index=False, engine="openpyxl")
    print(f"  已导出: {filepath}")


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_bill(args):
    month = args.month or _last_month()
    output_dir = args.output or "."
    flat_tier = args.flat_tier or bool(args.flat_tier_since)
    end_day = getattr(args, "end_day", None)
    customer_view = getattr(args, "customer_view", False)
    result = report_builder.generate_monthly_bill(
        month, output_dir,
        user_id=args.user_id,
        channel_id=args.channel_id,
        currency=args.currency,
        exchange_rate=args.exchange_rate,
        flat_tier=flat_tier,
        flat_tier_since=args.flat_tier_since,
        end_day=end_day,
        detail=args.detail,
        customer_view=customer_view,
        upload_s3=args.upload,
        no_cache=args.no_cache,
    )
    if isinstance(result, dict):
        print(f"\n  月度账单已生成: {result['xlsx']}")
        print(f"  S3 下载链接（24h 有效）:")
        print(f"    汇总: {result['xlsx_url']}")
        if "detail_csv" in result:
            print(f"  逐条明细已生成: {result['detail_csv']}")
            print(f"    明细: {result['detail_csv_url']}")
    elif isinstance(result, list):
        print(f"\n  月度账单已生成: {result[0]}")
        print(f"  逐条明细已生成: {result[1]}")
    else:
        print(f"\n  月度账单已生成: {result}")


def cmd_daily(args):
    date = args.date or _yesterday()
    output_dir = args.output or "."
    path = report_builder.generate_daily_report(date, output_dir, no_cache=args.no_cache)
    print(f"\n  日报已生成: {path}")


def cmd_anomaly(args):
    month = args.month or _last_month()
    output_dir = args.output or "."
    path = report_builder.generate_anomaly_report(month, output_dir, no_cache=args.no_cache)
    print(f"\n  异常报告已生成: {path}")


def cmd_ranking(args):
    month = args.month or _last_month()
    df = run_query_cached(queries.model_ranking(month), no_cache=args.no_cache)
    _print_df(df, f"模型排行 — {month}")
    if args.output:
        _export_df_excel(df, args.output)


def cmd_users(args):
    month = args.month or _last_month()
    df = run_query_cached(queries.top_users(month, limit=args.limit),
                          no_cache=args.no_cache)
    _print_df(df, f"用户排行 — {month}")
    if args.output:
        _export_df_excel(df, args.output)


def cmd_channels(args):
    month = args.month or _last_month()
    df = run_query_cached(queries.channel_summary(month), no_cache=args.no_cache)
    _print_df(df, f"渠道汇总 — {month}")
    if args.output:
        _export_df_excel(df, args.output)


def cmd_kpi(args):
    month = args.month or _last_month()
    df = run_query_cached(queries.kpi_summary(month), no_cache=args.no_cache)
    if not df.empty:
        kpi = df.iloc[0]
        print(f"\n{'='*50}")
        print(f"  KPI 概览 — {month}")
        print(f"{'='*50}")
        print(f"  总调用量:     {int(kpi['total_calls']):>12,}")
        print(f"  活跃用户:     {int(kpi['unique_users']):>12,}")
        print(f"  活跃模型:     {int(kpi['unique_models']):>12,}")
        print(f"  总输入 Tokens:{int(kpi['total_input_tokens']):>12,}")
        print(f"  总输出 Tokens:{int(kpi['total_output_tokens']):>12,}")
        print(f"  总费用 (USD): ${float(kpi['total_usd']):>11,.2f}")
        print(f"{'='*50}\n")


def cmd_profit(args):
    month = args.month or _last_month()
    channel_id = getattr(args, "channel_id", None)
    df = run_query_cached(queries.monthly_bill_full(month, user_id=args.user_id,
                                                    channel_id=channel_id),
                          no_cache=args.no_cache)
    if df.empty:
        print("  (无数据)")
        return

    df = pricing_engine.apply_pricing_summary(df)

    total_list = df["list_price_usd"].sum()
    total_rev = df["revenue_usd"].sum()
    total_cost = df["cost_usd"].sum()
    total_profit = df["profit_usd"].sum()
    margin = round(total_profit / total_rev * 100, 1) if total_rev else 0

    print(f"\n{'='*60}")
    print(f"  利润分析 — {month}")
    print(f"{'='*60}")
    print(f"  刊例价 (USD):   ${total_list:>12,.2f}")
    print(f"  客户应付 (USD): ${total_rev:>12,.2f}")
    print(f"  我方成本 (USD): ${total_cost:>12,.2f}")
    print(f"  利润 (USD):     ${total_profit:>12,.2f}")
    print(f"  利润率:         {margin:>12.1f}%")
    print(f"{'='*60}")

    if args.detail:
        user_agg = df.groupby(["user_id", "username"]).agg({
            "list_price_usd": "sum", "revenue_usd": "sum",
            "cost_usd": "sum", "profit_usd": "sum",
        }).reset_index()
        user_agg["margin_pct"] = (user_agg["profit_usd"] / user_agg["revenue_usd"].replace(0, float("nan")) * 100).round(1)
        user_agg = user_agg.sort_values("profit_usd", ascending=False)
        _print_df(user_agg, "用户利润明细")

    if args.output:
        _export_df_excel(df, args.output)


def cmd_discount(args):
    action = args.action

    if action == "list":
        print("\n=== 成本折扣 (渠道×模型) ===")
        cost_rows = pricing_engine.get_all_cost_discounts()
        if cost_rows:
            _print_df(pd.DataFrame(cost_rows))
        else:
            print("  (无配置)")

        print("\n=== 客户折扣 (用户×模型) ===")
        rev_rows = pricing_engine.get_all_revenue_discounts()
        if rev_rows:
            _print_df(pd.DataFrame(rev_rows))
        else:
            print("  (无配置)")

    elif action == "set-cost":
        d = pricing_engine._load_discounts()
        ch = str(args.id)
        section = d["cost_discounts"].setdefault("by_channel", {})
        if ch not in section:
            section[ch] = {"_name": args.name or ""}
        model = args.model or "*"
        section[ch][model] = args.rate
        pricing_engine.save_discounts(d)
        print(f"  已设置: 渠道 {ch} / 模型 {model} = {args.rate}")

    elif action == "set-rev":
        d = pricing_engine._load_discounts()
        uid = str(args.id)
        section = d["revenue_discounts"].setdefault("by_user", {})
        if uid not in section:
            section[uid] = {"_name": args.name or ""}
        model = args.model or "*"
        section[uid][model] = args.rate
        pricing_engine.save_discounts(d)
        print(f"  已设置: 用户 {uid} / 模型 {model} = {args.rate}")


def cmd_recalc(args):
    output_dir = args.output or "."
    path = report_builder.generate_recalc_report(
        args.start, args.end, output_dir,
        user_id=args.user_id,
        channel_id=args.channel_id,
        flat_tier=args.flat_tier,
        flat_tier_since=args.flat_tier_since,
        no_cache=args.no_cache,
    )
    print(f"\n  重算报告已生成: {path}")


def cmd_import_bill(args):
    mapping = None
    if args.model_col or args.amount_col:
        mapping = {}
        if args.model_col:
            mapping["model"] = args.model_col
        if args.amount_col:
            mapping["amount"] = args.amount_col

    df = cost_import.import_and_summarize(
        args.file, column_mapping=mapping,
        channel_id=args.channel_id,
        vendor_name=args.name,
        month=args.month)

    _print_df(df, f"导入成功 — {os.path.basename(args.file)}")
    print(f"  总金额: ${df['vendor_amount'].sum():,.4f}")
    print(f"  模型数: {len(df)}")
    print(f"  记录已保存到 imports/ 目录")


def cmd_crosscheck(args):
    output_dir = args.output or "."

    vendor_files = args.vendor
    # Auto-detect row-level format
    if args.row_level or cost_import.is_row_level_bill(vendor_files[0]):
        print(f"  检测到逐条明细格式，使用 request_id 级别对账")
        path = report_builder.generate_row_level_crosscheck_report(
            vendor_files, output_dir,
            channel_id=args.channel_id,
            no_cache=args.no_cache)
    else:
        mapping = None
        if args.model_col or args.amount_col:
            mapping = {}
            if args.model_col:
                mapping["model"] = args.model_col
            if args.amount_col:
                mapping["amount"] = args.amount_col

        month = args.month or _last_month()
        path = report_builder.generate_crosscheck_report(
            month, vendor_files[0], output_dir,
            channel_id=args.channel_id,
            column_mapping=mapping,
            no_cache=args.no_cache)
    print(f"\n  对账报告已生成: {path}")


def cmd_query(args):
    sql = args.sql
    if args.safe:
        df = run_safe_query(sql, no_cache=args.no_cache)
    else:
        df = run_query_cached(sql, no_cache=args.no_cache)
    _print_df(df, "查询结果")
    if args.output:
        if args.output.endswith(".xlsx"):
            _export_df_excel(df, args.output)
        else:
            df.to_csv(args.output, index=False, encoding="utf-8-sig")
            print(f"  已导出: {args.output}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        description="EZModel 账单与分析 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--no-cache", action="store_true", help="跳过 S3 查询缓存")

    sub = parser.add_subparsers(dest="command", help="子命令")

    # bill
    p_bill = sub.add_parser("bill", parents=[common], help="生成月度账单 Excel")
    p_bill.add_argument("--month", help="YYYY-MM (默认上月)")
    p_bill.add_argument("--user-id", type=int, help="指定用户 ID")
    p_bill.add_argument("--channel-id", type=int, help="指定上游渠道 ID（只出该渠道的账单）")
    p_bill.add_argument("--currency", default="USD", choices=["USD", "CNY"])
    p_bill.add_argument("--exchange-rate", type=float, default=7.3, help="CNY 汇率")
    p_bill.add_argument("--flat-tier", action="store_true",
                        help="降档模式：分段模型强制使用低档价")
    p_bill.add_argument("--flat-tier-since", type=str,
                        help="降档起始日期 YYYY-MM-DD（隐含 --flat-tier）")
    p_bill.add_argument("--end-day", type=str,
                        help="账单截止日期 YYYY-MM-DD（含当天，必须在 --month 所在月内）")
    p_bill.add_argument("--detail", action="store_true",
                        help="同时导出逐条明细 CSV.zip（按天并行查询）")
    p_bill.add_argument("--customer-view", action="store_true",
                        help="客户版本：隐藏成本折扣、成本价、利润、渠道 ID 等内部数据")
    p_bill.add_argument("--upload", action="store_true",
                        help="上传产物到 S3 并生成 presigned 下载链接（24h 有效）")
    p_bill.add_argument("-o", "--output", default=".", help="输出目录")

    # daily
    p_daily = sub.add_parser("daily", parents=[common], help="生成日报 Excel")
    p_daily.add_argument("--date", help="YYYY-MM-DD (默认昨天)")
    p_daily.add_argument("-o", "--output", default=".", help="输出目录")

    # anomaly
    p_anom = sub.add_parser("anomaly", parents=[common], help="生成异常检测报告")
    p_anom.add_argument("--month", help="YYYY-MM (默认上月)")
    p_anom.add_argument("-o", "--output", default=".", help="输出目录")

    # ranking
    p_rank = sub.add_parser("ranking", parents=[common], help="模型排行")
    p_rank.add_argument("--month", help="YYYY-MM")
    p_rank.add_argument("-o", "--output", help="导出 xlsx/csv 路径")

    # users
    p_users = sub.add_parser("users", parents=[common], help="用户排行")
    p_users.add_argument("--month", help="YYYY-MM")
    p_users.add_argument("--limit", type=int, default=20)
    p_users.add_argument("-o", "--output", help="导出路径")

    # channels
    p_ch = sub.add_parser("channels", parents=[common], help="渠道汇总")
    p_ch.add_argument("--month", help="YYYY-MM")
    p_ch.add_argument("-o", "--output", help="导出路径")

    # kpi
    p_kpi = sub.add_parser("kpi", parents=[common], help="KPI 概览")
    p_kpi.add_argument("--month", help="YYYY-MM")

    # profit
    p_profit = sub.add_parser("profit", parents=[common], help="利润分析（四层价格）")
    p_profit.add_argument("--month", help="YYYY-MM")
    p_profit.add_argument("--user-id", type=int, help="指定用户 ID")
    p_profit.add_argument("--channel-id", type=int, help="指定上游渠道 ID")
    p_profit.add_argument("--detail", action="store_true", help="显示用户明细")
    p_profit.add_argument("-o", "--output", help="导出完整明细 xlsx")

    # discount
    p_disc = sub.add_parser("discount", parents=[common], help="折扣配置管理")
    disc_sub = p_disc.add_subparsers(dest="action")
    disc_sub.add_parser("list", help="列出所有折扣配置")
    p_set_cost = disc_sub.add_parser("set-cost", help="设置成本折扣 (渠道)")
    p_set_cost.add_argument("--id", required=True, help="渠道 ID")
    p_set_cost.add_argument("--model", default="*", help="模型名 (* = 所有)")
    p_set_cost.add_argument("--rate", type=float, required=True, help="折扣率")
    p_set_cost.add_argument("--name", help="渠道名称")
    p_set_rev = disc_sub.add_parser("set-rev", help="设置客户折扣 (用户)")
    p_set_rev.add_argument("--id", required=True, help="用户 ID")
    p_set_rev.add_argument("--model", default="*", help="模型名 (* = 所有)")
    p_set_rev.add_argument("--rate", type=float, required=True, help="折扣率")
    p_set_rev.add_argument("--name", help="用户名")

    # recalc
    p_recalc = sub.add_parser("recalc", parents=[common],
                              help="基于原始日志重算（分段计费 + 降档）")
    p_recalc.add_argument("--start", required=True, help="起始日期 YYYY-MM-DD")
    p_recalc.add_argument("--end", required=True, help="结束日期 YYYY-MM-DD")
    p_recalc.add_argument("--user-id", type=int, help="指定用户 ID")
    p_recalc.add_argument("--channel-id", type=int, help="指定渠道 ID")
    p_recalc.add_argument("--flat-tier", action="store_true",
                          help="降档模式：分段模型强制使用低档价")
    p_recalc.add_argument("--flat-tier-since", type=str,
                          help="降档起始日期 YYYY-MM-DD（隐含 --flat-tier）")
    p_recalc.add_argument("-o", "--output", default=".", help="输出目录")

    # import-bill
    p_import = sub.add_parser("import-bill", parents=[common],
                              help="导入供应商成本账单 (CSV/Excel)")
    p_import.add_argument("file", help="CSV 或 Excel 文件路径")
    p_import.add_argument("--channel-id", type=int, help="关联渠道 ID")
    p_import.add_argument("--name", help="供应商名称")
    p_import.add_argument("--month", help="账单月份 YYYY-MM")
    p_import.add_argument("--model-col", help="模型列名（自动检测失败时指定）")
    p_import.add_argument("--amount-col", help="金额列名（自动检测失败时指定）")

    # crosscheck
    p_cross = sub.add_parser("crosscheck", parents=[common],
                             help="与供应商账单交叉对账")
    p_cross.add_argument("--month", help="YYYY-MM (默认上月，汇总模式使用)")
    p_cross.add_argument("--vendor", required=True, nargs="+",
                         help="供应商账单文件路径（支持多个文件）")
    p_cross.add_argument("--channel-id", type=int, help="限定渠道 ID")
    p_cross.add_argument("--row-level", action="store_true",
                         help="强制使用逐条 request_id 对账模式（自动检测时可省略）")
    p_cross.add_argument("--model-col", help="模型列名（汇总模式）")
    p_cross.add_argument("--amount-col", help="金额列名（汇总模式）")
    p_cross.add_argument("-o", "--output", default=".", help="输出目录")

    # query
    p_query = sub.add_parser("query", parents=[common], help="自由 SQL 查询")
    p_query.add_argument("sql", help="SQL 语句")
    p_query.add_argument("-o", "--output", help="导出 xlsx/csv 路径")
    p_query.add_argument("--safe", action="store_true", default=True,
                         help="启用 raw_logs 分区安全检查 (默认)")
    p_query.add_argument("--unsafe", dest="safe", action="store_false",
                         help="跳过 raw_logs 分区检查")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    handlers = {
        "bill": cmd_bill,
        "daily": cmd_daily,
        "anomaly": cmd_anomaly,
        "ranking": cmd_ranking,
        "users": cmd_users,
        "channels": cmd_channels,
        "kpi": cmd_kpi,
        "profit": cmd_profit,
        "discount": cmd_discount,
        "recalc": cmd_recalc,
        "import-bill": cmd_import_bill,
        "crosscheck": cmd_crosscheck,
        "query": cmd_query,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
