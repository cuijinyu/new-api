#!/usr/bin/env python3
"""
折扣配置管理 CLI 工具

用于管理 discounts.json 配置文件，支持版本控制和变更历史追踪。
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.athena.pricing_engine import (
    get_all_cost_discounts,
    get_all_revenue_discounts,
    get_discounts_version,
    save_discounts,
    validate_discounts_structure,
    _load_discounts,
)

_DISCOUNTS_PATH = Path(__file__).resolve().parent / "discounts.json"


def cmd_show(args):
    """显示当前折扣配置"""
    d = _load_discounts()

    print(f"\n{'='*60}")
    print(f"折扣配置概览")
    print(f"{'='*60}")
    print(f"版本: {d.get('_version', 'N/A')}")
    print(f"更新时间: {d.get('_updated_at', 'N/A')}")
    print(f"更新者: {d.get('_updated_by', 'N/A')}")

    # Cost discounts
    cost_rows = get_all_cost_discounts()
    print(f"\n[成本折扣] 共 {len(cost_rows)} 条记录")
    if cost_rows:
        print(f"{'渠道ID':<10} {'渠道名称':<20} {'模型':<25} {'折扣率':<10}")
        print("-" * 65)
        for row in cost_rows:
            print(f"{row['channel_id']:<10} {row['channel_name']:<20} {row['model']:<25} {row['discount']:<10.2f}")

    # Revenue discounts
    rev_rows = get_all_revenue_discounts()
    print(f"\n[客户折扣] 共 {len(rev_rows)} 条记录")
    if rev_rows:
        print(f"{'用户ID':<10} {'用户名称':<20} {'模型':<25} {'折扣率':<10}")
        print("-" * 65)
        for row in rev_rows:
            print(f"{row['user_id']:<10} {row['user_name']:<20} {row['model']:<25} {row['discount']:<10.2f}")

    print(f"\n{'='*60}\n")


def cmd_version(args):
    """显示版本信息"""
    d = _load_discounts()

    print(f"\n折扣配置版本信息")
    print(f"-" * 40)
    print(f"当前版本: {d.get('_version', 'N/A')}")
    print(f"更新时间: {d.get('_updated_at', 'N/A')}")
    print(f"更新者: {d.get('_updated_by', 'N/A')}")
    print()


def cmd_validate(args):
    """验证配置完整性"""
    result = validate_discounts_structure()

    print(f"\n配置验证结果")
    print(f"-" * 40)

    if result["valid"]:
        print("状态: PASSED")
    else:
        print("状态: FAILED")

    print(f"版本: {result['version']}")
    print(f"更新时间: {result['updated_at']}")

    if result["warnings"]:
        print(f"\n警告 ({len(result['warnings'])}):")
        for w in result["warnings"]:
            print(f"  - {w}")

    if result["errors"]:
        print(f"\n错误 ({len(result['errors'])}):")
        for e in result["errors"]:
            print(f"  - {e}")

    print()

    # Return exit code based on validation result
    sys.exit(0 if result["valid"] else 1)


def cmd_history(args):
    """显示变更历史"""
    d = _load_discounts()
    changelog = d.get("_changelog", [])

    print(f"\n变更历史")
    print(f"-" * 40)

    if not changelog:
        print("暂无变更记录")
        print()
        return

    for i, entry in enumerate(reversed(changelog)):
        print(f"\n[{len(changelog) - i}] {entry.get('timestamp', 'N/A')}")
        print(f"    版本: {entry.get('version', 'N/A')}")
        print(f"    作者: {entry.get('author', 'N/A')}")
        changes = entry.get('changes', [])
        if changes:
            print(f"    变更:")
            for change in changes:
                print(f"      - {change}")

    print()


def cmd_add_cost(args):
    """添加成本折扣"""
    d = _load_discounts()

    channel_id = args.channel_id
    model = args.model if args.model else "*"
    discount = float(args.discount)
    name = args.name or f"Channel-{channel_id}"

    # Initialize by_channel if needed
    if "by_channel" not in d["cost_discounts"]:
        d["cost_discounts"]["by_channel"] = {}

    # Initialize channel entry if needed
    if str(channel_id) not in d["cost_discounts"]["by_channel"]:
        d["cost_discounts"]["by_channel"][str(channel_id)] = {}

    # Set discount
    d["cost_discounts"]["by_channel"][str(channel_id)][model] = discount
    d["cost_discounts"]["by_channel"][str(channel_id)]["_name"] = name

    # Update metadata
    d["_updated_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    d["_updated_by"] = args.author or os.getenv("USER", os.getenv("USERNAME", "unknown"))

    # Add changelog entry
    changelog = d.get("_changelog", [])
    changelog.append({
        "timestamp": d["_updated_at"],
        "version": d.get("_version", "1.0.0"),
        "changes": [f"Added cost discount: channel {channel_id}, model {model}, rate {discount}"],
        "author": d["_updated_by"],
    })
    d["_changelog"] = changelog

    # Save
    save_discounts(d)
    print(f"\n已添加成本折扣: 渠道 {channel_id}, 模型 {model}, 折扣 {discount}")


def cmd_add_revenue(args):
    """添加客户折扣"""
    d = _load_discounts()

    user_id = args.user_id
    model = args.model if args.model else "*"
    discount = float(args.discount)
    name = args.name or f"User-{user_id}"

    # Initialize by_user if needed
    if "by_user" not in d["revenue_discounts"]:
        d["revenue_discounts"]["by_user"] = {}

    # Initialize user entry if needed
    if str(user_id) not in d["revenue_discounts"]["by_user"]:
        d["revenue_discounts"]["by_user"][str(user_id)] = {}

    # Set discount
    d["revenue_discounts"]["by_user"][str(user_id)][model] = discount
    d["revenue_discounts"]["by_user"][str(user_id)]["_name"] = name

    # Update metadata
    d["_updated_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    d["_updated_by"] = args.author or os.getenv("USER", os.getenv("USERNAME", "unknown"))

    # Add changelog entry
    changelog = d.get("_changelog", [])
    changelog.append({
        "timestamp": d["_updated_at"],
        "version": d.get("_version", "1.0.0"),
        "changes": [f"Added revenue discount: user {user_id}, model {model}, rate {discount}"],
        "author": d["_updated_by"],
    })
    d["_changelog"] = changelog

    # Save
    save_discounts(d)
    print(f"\n已添加客户折扣: 用户 {user_id}, 模型 {model}, 折扣 {discount}")


def cmd_bump_version(args):
    """升级版本号"""
    d = _load_discounts()

    current = d.get("_version", "1.0.0")
    parts = current.split(".")

    if args.level == "major":
        parts[0] = str(int(parts[0]) + 1)
        parts[1] = "0"
        parts[2] = "0"
    elif args.level == "minor":
        parts[1] = str(int(parts[1]) + 1)
        parts[2] = "0"
    else:  # patch
        parts[2] = str(int(parts[2]) + 1)

    new_version = ".".join(parts)
    d["_version"] = new_version
    d["_updated_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    d["_updated_by"] = args.author or os.getenv("USER", os.getenv("USERNAME", "unknown"))

    # Add changelog entry
    changelog = d.get("_changelog", [])
    changelog.append({
        "timestamp": d["_updated_at"],
        "version": new_version,
        "changes": args.message or ["Version bump"],
        "author": d["_updated_by"],
    })
    d["_changelog"] = changelog

    save_discounts(d)
    print(f"\n版本已更新: {current} -> {new_version}")


def main():
    parser = argparse.ArgumentParser(
        description="折扣配置管理 CLI 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python discount_cli.py show              # 显示当前配置
  python discount_cli.py version           # 显示版本信息
  python discount_cli.py validate          # 验证配置
  python discount_cli.py history           # 显示变更历史
  python discount_cli.py add-cost 25 "*" 0.35 --name "MateCloud"    # 添加成本折扣
  python discount_cli.py add-rev 18 "*" 0.65 --name "GMICloud"      # 添加客户折扣
  python discount_cli.py bump-version patch -m "Fixed discount rates"  # 升级版本
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # show command
    subparsers.add_parser("show", help="显示当前折扣配置")

    # version command
    subparsers.add_parser("version", help="显示版本信息")

    # validate command
    subparsers.add_parser("validate", help="验证配置完整性")

    # history command
    subparsers.add_parser("history", help="显示变更历史")

    # add-cost command
    parser_cost = subparsers.add_parser("add-cost", help="添加成本折扣")
    parser_cost.add_argument("channel_id", help="渠道ID")
    parser_cost.add_argument("model", help="模型名称 (使用 '*' 表示通配)")
    parser_cost.add_argument("discount", help="折扣率 (0.0-1.0)")
    parser_cost.add_argument("--name", help="渠道名称")
    parser_cost.add_argument("--author", help="更新者")

    # add-revenue command
    parser_rev = subparsers.add_parser("add-rev", help="添加客户折扣")
    parser_rev.add_argument("user_id", help="用户ID")
    parser_rev.add_argument("model", help="模型名称 (使用 '*' 表示通配)")
    parser_rev.add_argument("discount", help="折扣率 (0.0-1.0)")
    parser_rev.add_argument("--name", help="用户名称")
    parser_rev.add_argument("--author", help="更新者")

    # bump-version command
    parser_bump = subparsers.add_parser("bump-version", help="升级版本号")
    parser_bump.add_argument("level", choices=["major", "minor", "patch"], help="版本级别")
    parser_bump.add_argument("-m", "--message", action="append", help="变更说明")
    parser_bump.add_argument("--author", help="更新者")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Map commands to functions
    commands = {
        "show": cmd_show,
        "version": cmd_version,
        "validate": cmd_validate,
        "history": cmd_history,
        "add-cost": cmd_add_cost,
        "add-rev": cmd_add_revenue,
        "bump-version": cmd_bump_version,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
