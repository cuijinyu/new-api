"""
Athena 查询成本监控模块

追踪 Athena 查询扫描的数据量并计算成本。
Athena 定价约 $5.00 per TB scanned (us-east-1)，其他区域可能不同。
"""

import logging
import os
from datetime import datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# 成本配置：每 TB 扫描数据的成本（美元）
# 可通过环境变量 ATHENA_COST_PER_TB 覆盖
# AWS Athena 定价参考：https://aws.amazon.com/athena/pricing/
# us-east-1: $5.00 per TB
# 其他区域可能略有差异
COST_PER_TB = float(os.getenv("ATHENA_COST_PER_TB", "5.00"))

# 成本告警阈值（美元）
# 单次查询成本超过此值时记录 WARNING 级别日志
# 可通过环境变量 ATHENA_COST_ALERT_THRESHOLD 覆盖
COST_ALERT_THRESHOLD = float(os.getenv("ATHENA_COST_ALERT_THRESHOLD", "1.0"))

# 每月的字节数（用于 TB 转换）
BYTES_PER_TB = 1_099_511_627_776  # 1024^4

# ---------------------------------------------------------------------------
# Global cost tracking
# ---------------------------------------------------------------------------

# 本次运行的总成本追踪器
_total_cost: float = 0.0
_total_scanned_bytes: int = 0
_query_count: int = 0
_cache_hits: int = 0

# 查询成本明细（按查询名称分组）
_query_costs: dict[str, dict] = {}


def reset_tracking():
    """重置成本追踪器（用于测试或新会话）"""
    global _total_cost, _total_scanned_bytes, _query_count, _cache_hits, _query_costs
    _total_cost = 0.0
    _total_scanned_bytes = 0
    _query_count = 0
    _cache_hits = 0
    _query_costs = {}


def get_total_cost() -> float:
    """获取本次运行的总成本（美元）"""
    return _total_cost


def get_total_scanned_bytes() -> int:
    """获取本次运行的总扫描字节数"""
    return _total_scanned_bytes


def get_query_count() -> int:
    """获取本次运行的查询总数"""
    return _query_count


def get_cache_hit_count() -> int:
    """获取本次运行的缓存命中次数"""
    return _cache_hits


def get_query_costs() -> dict[str, dict]:
    """获取按查询名称分组的成本明细"""
    return _query_costs.copy()


def get_cost_summary() -> dict:
    """获取成本摘要"""
    return {
        "total_cost_usd": round(_total_cost, 4),
        "total_scanned_tb": round(_total_scanned_bytes / BYTES_PER_TB, 4),
        "total_scanned_bytes": _total_scanned_bytes,
        "query_count": _query_count,
        "cache_hits": _cache_hits,
        "cache_misses": _query_count - _cache_hits,
        "cache_hit_rate": round(_cache_hits / _query_count * 100, 1) if _query_count > 0 else 0,
    }


# ---------------------------------------------------------------------------
# Cost calculation functions
# ---------------------------------------------------------------------------

def calculate_query_cost(scanned_bytes: int) -> float:
    """计算查询成本

    Args:
        scanned_bytes: 扫描的字节数

    Returns:
        成本（美元）
    """
    tb_scanned = scanned_bytes / BYTES_PER_TB
    return tb_scanned * COST_PER_TB


def bytes_to_tb(bytes_value: int) -> float:
    """将字节数转换为 TB"""
    return bytes_value / BYTES_PER_TB


def bytes_to_gb(bytes_value: int) -> float:
    """将字节数转换为 GB"""
    return bytes_value / (1024**3)


def bytes_to_mb(bytes_value: int) -> float:
    """将字节数转换为 MB"""
    return bytes_value / (1024**2)


# ---------------------------------------------------------------------------
# Logging functions
# ---------------------------------------------------------------------------

def _get_logger() -> logging.Logger:
    """获取成本监控专用 logger"""
    return logging.getLogger("athena.cost")


def log_query_cost(scanned_bytes: int, query_name: str,
                   context: Optional[dict] = None,
                   is_cache_hit: bool = False) -> float:
    """记录查询成本

    Args:
        scanned_bytes: 扫描的字节数
        query_name: 查询名称/描述
        context: 额外的上下文信息（如查询类型、表名等）
        is_cache_hit: 是否为缓存命中

    Returns:
        本次查询的成本（美元）
    """
    global _total_cost, _total_scanned_bytes, _query_count, _cache_hits, _query_costs

    _query_count += 1

    if is_cache_hit:
        _cache_hits += 1
        cost = 0.0
    else:
        _total_scanned_bytes += scanned_bytes
        cost = calculate_query_cost(scanned_bytes)
        _total_cost += cost

    # 记录到按名称分组的成本追踪
    if query_name not in _query_costs:
        _query_costs[query_name] = {
            "count": 0,
            "total_bytes": 0,
            "total_cost": 0.0,
            "cache_hits": 0,
        }

    _query_costs[query_name]["count"] += 1
    if not is_cache_hit:
        _query_costs[query_name]["total_bytes"] += scanned_bytes
        _query_costs[query_name]["total_cost"] += cost
    else:
        _query_costs[query_name]["cache_hits"] += 1

    logger = _get_logger()

    # 构建日志消息
    if is_cache_hit:
        msg = f"[CACHE HIT] {query_name}"
        if scanned_bytes > 0:
            msg += f" (original scan: {bytes_to_mb(scanned_bytes):.2f} MB)"
        logger.info(msg)
    else:
        tb_scanned = bytes_to_tb(scanned_bytes)
        msg = f"[QUERY] {query_name} | Scanned: {format_bytes(scanned_bytes)} | Cost: ${cost:.4f}"

        # 成本告警
        if cost >= COST_ALERT_THRESHOLD:
            logger.warning(f"[HIGH COST] {query_name} | Cost: ${cost:.4f} >= ${COST_ALERT_THRESHOLD}")
            logger.warning(f"  Consider adding partition filters or reducing data scope")
        elif cost >= COST_ALERT_THRESHOLD * 0.5:
            # 成本超过阈值一半时记录 INFO 级别提示
            logger.info(f"[COST WARNING] {query_name} | Cost: ${cost:.4f} (approaching threshold ${COST_ALERT_THRESHOLD})")

        logger.info(msg)

    # 记录上下文信息（DEBUG 级别）
    if context and logger.isEnabledFor(logging.DEBUG):
        ctx_str = " | ".join(f"{k}={v}" for k, v in context.items())
        logger.debug(f"  Context: {ctx_str}")

    return cost


def log_cache_hit(query_name: str, original_bytes: int = 0):
    """记录缓存命中（便捷函数）

    Args:
        query_name: 查询名称/描述
        original_bytes: 原始查询扫描的字节数（可选）
    """
    log_query_cost(original_bytes, query_name, is_cache_hit=True)


def format_bytes(bytes_value: int) -> str:
    """格式化字节数为易读字符串

    Args:
        bytes_value: 字节数

    Returns:
        格式化后的字符串（如 "1.23 TB", "456.78 MB"）
    """
    if bytes_value >= BYTES_PER_TB:
        return f"{bytes_to_tb(bytes_value):.2f} TB"
    elif bytes_value >= 1024**3:
        return f"{bytes_to_gb(bytes_value):.2f} GB"
    elif bytes_value >= 1024**2:
        return f"{bytes_to_mb(bytes_value):.2f} MB"
    elif bytes_value >= 1024:
        return f"{bytes_value / 1024:.2f} KB"
    else:
        return f"{bytes_value} bytes"


def print_cost_summary():
    """打印成本摘要到控制台（用于 CLI 输出）"""
    summary = get_cost_summary()

    print(f"\n{'='*60}")
    print(f"  Athena 查询成本摘要")
    print(f"{'='*60}")
    print(f"  总查询次数:     {summary['query_count']:>12,}")
    print(f"  缓存命中:       {summary['cache_hits']:>12,}")
    print(f"  缓存命中率:     {summary['cache_hit_rate']:>12.1f}%")
    print(f"  总扫描数据量:   {format_bytes(summary['total_scanned_bytes']):>12}")
    print(f"  预估总成本:     ${summary['total_cost_usd']:>11,.4f}")
    print(f"  单价:           ${COST_PER_TB:>11,.2f} / TB")
    print(f"{'='*60}\n")


def print_query_breakdown(limit: int = 10):
    """打印按查询分组的成本明细

    Args:
        limit: 显示的前 N 个查询（默认 10）
    """
    costs = get_query_costs()
    if not costs:
        return

    # 按总成本降序排序
    sorted_costs = sorted(
        costs.items(),
        key=lambda x: x[1]["total_cost"],
        reverse=True
    )[:limit]

    print(f"\n{'='*80}")
    print(f"  查询成本明细（按成本排序，Top {len(sorted_costs)}）")
    print(f"{'='*80}")
    print(f"  {'查询名称':<40} {'次数':>6} {'扫描量':>12} {'成本':>12}")
    print(f"  {'-'*40} {'-'*6} {'-'*12} {'-'*12}")

    for name, data in sorted_costs:
        cost = data["total_cost"]
        bytes_val = data["total_bytes"]
        count = data["count"] - data["cache_hits"]
        cache_hits = data["cache_hits"]
        cache_str = f" ({cache_hits} cached)" if cache_hits > 0 else ""
        print(f"  {name:<40} {count:>6} {format_bytes(bytes_val):>12} ${cost:>10.4f}{cache_str}")

    print(f"{'='*80}\n")
