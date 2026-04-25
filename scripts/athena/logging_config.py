"""
统一日志配置模块 — Athena 对账系统

支持环境变量:
  - LOG_LEVEL: DEBUG/INFO/WARNING/ERROR (默认: INFO)
  - LOG_FORMAT: text/json (默认: text)

JSON 格式便于 CloudWatch Logs Insights 分析。
"""

import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# 默认配置
# ---------------------------------------------------------------------------

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = "text"

# ---------------------------------------------------------------------------
# JSON Formatter for CloudWatch Logs Insights
# ---------------------------------------------------------------------------


class CloudWatchJSONFormatter(logging.Formatter):
    """结构化 JSON 日志格式，便于 CloudWatch Logs Insights 查询。

    输出格式示例:
    {
        "timestamp": "2026-04-25T10:30:45.123Z",
        "level": "INFO",
        "logger": "athena_engine",
        "message": "Query completed successfully",
        "query_id": "abc-123",
        "scanned_bytes": 1048576,
        "duration_ms": 1234,
        "row_count": 1000
    }
    """

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._extra_fields = set()

    def format(self, record: logging.LogRecord) -> str:
        # 创建基础日志字典
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 添加异常信息（如果有）
        if record.exc_info:
            log_entry["error_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
            log_entry["error_message"] = str(record.exc_info[1]) if record.exc_info[1] else ""
            log_entry["stack_trace"] = self.formatException(record.exc_info)
        elif hasattr(record, "error_type"):
            # 支持通过 extra 字段传入错误信息
            log_entry["error_type"] = getattr(record, "error_type", "")
            log_entry["error_message"] = getattr(record, "error_message", "")
            log_entry["stack_trace"] = getattr(record, "stack_trace", "")

        # 添加自定义字段 (从 record.__dict__ 中提取)
        # 跳过标准字段和已处理字段
        skip_fields = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "lineno", "funcName", "created", "msecs",
            "relativeCreated", "thread", "threadName", "processName",
            "process", "getMessage", "exc_info", "exc_text", "stack_info",
            "error_type", "error_message", "stack_trace",
        }

        for key, value in record.__dict__.items():
            if key not in skip_fields and not key.startswith("_"):
                log_entry[key] = value

        import json
        return json.dumps(log_entry, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """可读性强的文本日志格式。

    格式示例:
    [2026-04-25 10:30:45 UTC] [INFO] [athena_engine] Query completed - query_id=abc-123 rows=1000
    """

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

    def format(self, record: logging.LogRecord) -> str:
        # 基础格式: [timestamp] [level] [logger] message
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        ts_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        base = f"[{ts_str}] [{record.levelname}] [{record.name}] {record.getMessage()}"

        # 添加 extra 字段
        extra_parts = []
        skip_fields = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "lineno", "funcName", "created", "msecs",
            "relativeCreated", "thread", "threadName", "processName",
            "process", "getMessage", "exc_info", "exc_text", "stack_info",
        }

        for key, value in record.__dict__.items():
            if key not in skip_fields and not key.startswith("_"):
                extra_parts.append(f"{key}={value}")

        if extra_parts:
            return f"{base} - {' '.join(str(p) for p in extra_parts)}"

        return base


# ---------------------------------------------------------------------------
# Logger 获取函数
# ---------------------------------------------------------------------------

_loggers = {}
_configured = False


def setup_logging(log_level: str = None, log_format: str = None) -> None:
    """配置全局日志处理器。

    Args:
        log_level: 日志级别 DEBUG/INFO/WARNING/ERROR，默认从 LOG_LEVEL 环境变量读取
        log_format: 日志格式 text/json，默认从 LOG_FORMAT 环境变量读取
    """
    global _configured

    if _configured:
        return

    level = (log_level or os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL)).upper()
    fmt = (log_format or os.getenv("LOG_FORMAT", DEFAULT_LOG_FORMAT)).lower()

    # 验证级别
    numeric_level = getattr(logging, level, logging.INFO)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    # 验证格式
    if fmt not in ("text", "json"):
        fmt = "text"

    # 获取根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # 清除现有处理器
    root_logger.handlers.clear()

    # 创建格式化器
    if fmt == "json":
        formatter = CloudWatchJSONFormatter()
    else:
        formatter = TextFormatter()

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(numeric_level)
    root_logger.addHandler(console_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger。

    首次调用时自动配置日志系统。

    Args:
        name: logger 名称，建议使用模块名 (如 "athena_engine", "bill_cron")

    Returns:
        logging.Logger 实例
    """
    if not _configured:
        setup_logging()

    if name not in _loggers:
        _loggers[name] = logging.getLogger(name)

    return _loggers[name]


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------

def log_query_start(logger: logging.Logger, query_id: str, sql_preview: str = None):
    """记录查询开始日志。

    Args:
        logger: logger 实例
        query_id: Athena 查询 ID
        sql_preview: SQL 预览（可选）
    """
    extra = {"query_id": query_id, "event": "query_start"}
    if sql_preview:
        extra["sql_preview"] = sql_preview[:200]
    logger.info("Athena query started", extra=extra)


def log_query_complete(logger: logging.Logger, query_id: str,
                      scanned_bytes: int, duration_ms: int, row_count: int):
    """记录查询完成日志。

    Args:
        logger: logger 实例
        query_id: Athena 查询 ID
        scanned_bytes: 扫描字节数
        duration_ms: 执行耗时（毫秒）
        row_count: 返回行数
    """
    logger.info(
        "Athena query completed",
        extra={
            "query_id": query_id,
            "event": "query_complete",
            "scanned_bytes": scanned_bytes,
            "duration_ms": duration_ms,
            "row_count": row_count,
        }
    )


def log_cache_hit(logger: logging.Logger, cache_key: str, ttl: int | None = None):
    """记录缓存命中日志。

    Args:
        logger: logger 实例
        cache_key: 缓存键
        ttl: TTL 秒数（None 表示永久）
    """
    logger.debug(
        "Cache hit",
        extra={
            "cache_key": cache_key,
            "event": "cache_hit",
            "hit": True,
            "ttl": ttl,
        }
    )


def log_cache_miss(logger: logging.Logger, cache_key: str, ttl: int | None = None):
    """记录缓存未命中日志。

    Args:
        logger: logger 实例
        cache_key: 缓存键
        ttl: TTL 秒数（None 表示永久）
    """
    logger.debug(
        "Cache miss",
        extra={
            "cache_key": cache_key,
            "event": "cache_miss",
            "hit": False,
            "ttl": ttl,
        }
    )


def log_cache_write(logger: logging.Logger, cache_key: str, row_count: int):
    """记录缓存写入日志。

    Args:
        logger: logger 实例
        cache_key: 缓存键
        row_count: 缓存行数
    """
    logger.debug(
        "Cache write",
        extra={
            "cache_key": cache_key,
            "event": "cache_write",
            "row_count": row_count,
        }
    )


def log_report_start(logger: logging.Logger, report_type: str, date_range: str):
    """记录报表生成开始日志。

    Args:
        logger: logger 实例
        report_type: 报表类型 (daily/monthly/anomaly/recalc/crosscheck)
        date_range: 日期范围 (YYYY-MM 或 YYYY-MM-DD)
    """
    logger.info(
        f"Report generation started: {report_type}",
        extra={
            "event": "report_start",
            "report_type": report_type,
            "date_range": date_range,
        }
    )


def log_report_complete(logger: logging.Logger, report_type: str,
                       date_range: str, output_path: str, record_count: int,
                       duration_ms: int):
    """记录报表生成完成日志。

    Args:
        logger: logger 实例
        report_type: 报表类型
        date_range: 日期范围
        output_path: 输出文件路径
        record_count: 记录数
        duration_ms: 总耗时（毫秒）
    """
    logger.info(
        f"Report generation completed: {report_type}",
        extra={
            "event": "report_complete",
            "report_type": report_type,
            "date_range": date_range,
            "output_path": output_path,
            "record_count": record_count,
            "duration_ms": duration_ms,
        }
    )


def log_error(logger: logging.Logger, error_type: str, error_message: str,
             stack_trace: str = None, **kwargs):
    """记录结构化错误日志。

    Args:
        logger: logger 实例
        error_type: 错误类型
        error_message: 错误消息
        stack_trace: 堆栈跟踪（可选）
        **kwargs: 额外上下文字段
    """
    extra = {
        "event": "error",
        "error_type": error_type,
        "error_message": error_message,
    }
    if stack_trace:
        extra["stack_trace"] = stack_trace
    extra.update(kwargs)

    logger.error(error_message, extra=extra)


# ---------------------------------------------------------------------------
# 性能计时上下文管理器
# ---------------------------------------------------------------------------

from contextlib import contextmanager
import time


@contextmanager
def log_duration(logger: logging.Logger, event: str, **extra_fields):
    """上下文管理器：记录操作耗时。

    用法:
        with log_duration(logger, "query_execution", query_id="abc-123"):
            result = run_query(...)

    输出日志包含 duration_ms 字段。
    """
    start_time = time.time()
    try:
        yield
    finally:
        duration_ms = int((time.time() - start_time) * 1000)
        extra_fields_with_duration = {**extra_fields, "duration_ms": duration_ms}
        logger.info(f"{event} completed", extra=extra_fields_with_duration)
