# Athena 对账系统改进计划

> 文档创建时间: 2026-04-25
> 系统路径: `scripts/athena/`
> 系统概述: 基于 AWS Athena 的 S3 日志分析平台，提供 CLI 工具、Web 仪表盘和定时任务三个入口

---

## 系统架构

```
S3 (ezmodel-log)
├── llm-usage-logs/   → usage_logs 表（账务核心）
├── llm-raw-logs/     → raw_logs 表（完整请求/响应）
├── llm-error-logs/   → error_logs 表（仅非 2xx）
├── athena-cache/     → 查询结果缓存（Parquet）
└── reports/          → 定时任务生成的报表
         ↓
    Athena (Partition Projection)
         ↓
┌─────────────────────────────────────────┐
│  athena_engine.py  (查询 + S3 缓存)     │
│  queries.py        (SQL 模板)           │
│  pricing_engine.py (价格计算)           │
│  report_builder.py (Excel 生成)         │
└─────────────┬───────────┬───────────┬───┘
              │           │           │
        bill_cli.py  bill_cron.py  bill_dashboard.py
         (CLI)       (定时任务)     (Web 仪表盘)
```

---

## 改进项清单

### 1. 价格配置管理

**现状**: 价格硬编码在 `pricing_engine.py` 的 `PRICING` 字典中

**问题**:
- 每次价格变动需要修改代码并重启服务
- 价格变更历史无法追溯
- 多环境部署困难

**改进方案**:
```python
# pricing.json
{
  "version": "2026-04-25",
  "models": {
    "claude-opus-4-6": [
      {"min_k": 0, "max_k": 200, "ip": 5, "op": 25, "chp": 0.5, "cwp": 6.25, "cwp_1h": 10},
      {"min_k": 200, "max_k": -1, "ip": 10, "op": 37.5, "chp": 1.0, "cwp": 12.5, "cwp_1h": 20}
    ]
  },
  "history": [
    {"date": "2026-04-25", "changes": [...], "author": "..."}
  ]
}
```

**优先级**: 高 | **预计工作量**: 0.5 天

---

### 2. 折扣配置数据结构

**现状**: `discounts.json` 使用文件 mtime 缓存

**问题**:
- 多进程环境下缓存不一致
- 无法追溯折扣变更历史
- 无并发控制

**改进方案**:
- 将折扣配置存储到 S3 或数据库
- 添加版本号和变更日志
- 实现乐观锁或分布式锁

**优先级**: 高 | **预计工作量**: 1 天

---

### 3. 错误处理与重试机制

**现状**: `athena_engine.py` 的 S3 客户端有重试，但 Athena 查询失败时没有

**问题**:
```python
# 当前实现
if state != "SUCCEEDED":
    raise RuntimeError(f"Athena query {state}: {reason}")
```

**改进方案**:
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=lambda e: isinstance(e, ThrottlingException) or "Throttling" in str(e)
)
def run_query_with_retry(sql: str, poll_interval: float = 1.5) -> dict:
    # ... 查询逻辑
```

**优先级**: 高 | **预计工作量**: 0.5 天

---

### 4. 分区查询校验不足

**现状**: `validate_raw_logs_partition()` 只检查 `raw_logs` 表

**问题**:
- `usage_logs` 也可以被滥用扫描全量数据
- 没有强制要求 year/month 过滤

**改进方案**:
```python
def validate_query_partitions(sql: str):
    """强制验证所有表查询都包含必要的分区过滤"""
    checks = [
        (r"\braw_logs\b", r"\bday\s*="),
        (r"\busage_logs\b", r"\b(year\s*=.*month\s*=|year_month\s*=)"),
    ]
    for table_pattern, required_filter in checks:
        if re.search(table_pattern, sql, re.IGNORECASE):
            if not re.search(required_filter, sql, re.IGNORECASE):
                raise ValueError(f"查询 {table_pattern} 必须指定分区过滤")
```

**优先级**: 中 | **预计工作量**: 0.5 天

---

### 5. 数据质量检查

**现状**: 没有数据完整性校验

**问题**:
- `quota = 0` 但 `tokens > 0` 的异常记录
- 负值、空值未检测
- 异常比率（cache_write > input）未校验

**改进方案**:
```python
# data_quality.py
def validate_usage_logs(df: pd.DataFrame) -> dict:
    issues = {}

    # 1. 有 token 但 quota 为 0
    mask = (df["prompt_tokens"] + df["completion_tokens"] > 0) & (df["quota"] == 0)
    if mask.any():
        issues["zero_quota_with_tokens"] = mask.sum()

    # 2. 负值
    for col in ["quota", "prompt_tokens", "completion_tokens"]:
        if (df[col] < 0).any():
            issues[f"negative_{col}"] = (df[col] < 0).sum()

    # 3. 异常 cache 比率
    if "cache_creation_tokens" in df.columns:
        mask = df["cache_creation_tokens"] > df["prompt_tokens"]
        if mask.any():
            issues["cache_exceeds_input"] = mask.sum()

    return issues
```

**优先级**: 中 | **预计工作量**: 1 天

---

### 6. 仪表盘性能优化

**现状**: `bill_dashboard.py` 的 `@st.cache_data` 没有 TTL

**问题**:
- 数据变更后仪表盘显示陈旧结果
- 缓存无过期策略

**改进方案**:
```python
@st.cache_data(ttl=600)  # 10分钟过期
def load_monthly_kpi(month: str):
    # ...

@st.cache_data(ttl=60)   # 1分钟过期
def load_realtime_stats():
    # ...
```

**优先级**: 中 | **预计工作量**: 0.5 天

---

### 7. 日志记录不足

**现状**: 只有简单的 `print` 输出

**问题**:
- 生产环境问题排查困难
- 没有结构化日志
- 无法追踪查询性能

**改进方案**:
```python
# logging_config.py
import logging
import sys

def setup_logging(name: str, level: str = "INFO"):
    logger = logging.getLogger(name)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level))
    return logger

# 使用
logger = setup_logging("athena")
logger.info("query completed", extra={"scanned_bytes": 1024000, "duration_ms": 1234})
```

**优先级**: 中 | **预计工作量**: 0.5 天

---

### 8. 成本监控

**现状**: 没有追踪查询成本

**问题**:
- 难以监控和分析 Athena 成本
- 无法设置告警

**改进方案**:
```python
# Athena 定价 (us-east-1): $5.00 per TB scanned
COST_PER_TB = 5.0

def log_query_cost(scanned_bytes: int, query_name: str = ""):
    cost_usd = scanned_bytes / 1024 / 1024 / 1024 / 1024 * COST_PER_TB
    logger.info(f"Query cost: ${cost_usd:.4f} ({scanned_bytes / 1024 / 1024:.2f} MB)")
    if cost_usd > 1.0:  # 单次查询超过 $1 告警
        send_alert(f"High cost query: {query_name} = ${cost_usd:.2f}")
```

**优先级**: 低 | **预计工作量**: 0.5 天

---

### 9. 并发控制

**现状**: `run_queries_parallel_iter` 的 `max_concurrent=20` 是硬编码的

**问题**:
- 可能超过 Athena 工作组配额
- 无法根据负载动态调整

**改进方案**:
```python
# 从环境变量或配置读取
MAX_CONCURRENT_QUERIES = int(os.getenv("ATHENA_MAX_CONCURRENT", "20"))

def run_queries_parallel_iter(sqls: list[str], ...):
    # 根据 Athena 工作组限制动态调整
    workgroup = get_workgroup_limits()
    max_concurrent = min(MAX_CONCURRENT_QUERIES, workgroup.get("max_concurrent", 20))
    # ...
```

**优先级**: 中 | **预计工作量**: 0.5 天

---

### 10. 模型名称映射

**现状**: 模型名称需精确匹配

**问题**:
- 新模型无法自动计费
- 别名无法识别
- 模型名称变更导致历史数据无法计费

**改进方案**:
```python
# model_aliases.json
{
  "mappings": {
    "claude-opus-4": ["claude-opus-4-6", "claude-opus-4-5-20251101"],
    "claude-sonnet-4": ["claude-sonnet-4-6", "claude-sonnet-4-5-20250929"],
    "gpt-4o": ["gpt-4o-2024-05-13", "gpt-4o-2024-08-06"]
  }
}
```

**优先级**: 中 | **预计工作量**: 1 天

---

### 11. 时区处理

**现状**: 代码中混用 UTC 和本地时间

**问题**:
- `bill_cron.py` 的调度时区不明确
- 日报/月报时间边界可能出错

**改进方案**:
```python
# 统一使用 UTC，在 UI 层转换
from datetime import datetime, timezone

def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)

def to_user_timezone(dt: datetime, tz: str = "Asia/Shanghai") -> datetime:
    import pytz
    return dt.astimezone(pytz.timezone(tz))
```

**优先级**: 低 | **预计工作量**: 0.5 天

---

### 12. 单元测试

**现状**: 核心计算逻辑没有测试覆盖

**问题**:
- 修改代码时容易引入 bug
- 无法验证边界条件

**改进方案**:
```python
# tests/test_pricing_engine.py
import pytest
from pricing_engine import recalc_from_raw, PRICING

def test_flat_tier_pricing():
    df = pd.DataFrame([{
        "model_name": "claude-opus-4-6",
        "prompt_tokens": 150_000,  # 第一档
        "completion_tokens": 50_000,
        "quota": 100_000_000,
        "other": "{}",
        "created_at": 1700000000,
        "channel_id": 1,
        "user_id": 1
    }])
    result = recalc_from_raw(df, flat_tier=True)
    assert result["expected_usd"][0] > 0

def test_tier_boundary():
    # 测试 200K 边界
    pass

def test_cache_token_pricing():
    # 测试缓存 token 计价
    pass
```

**优先级**: 低 | **预计工作量**: 2 天

---

## 优先级排序

| 优先级 | 改进项 | 预计工作量 | 累计工作量 |
|--------|--------|-----------|-----------|
| **高** | 价格配置外部化 | 0.5 天 | 0.5 天 |
| **高** | 折扣配置改进 | 1 天 | 1.5 天 |
| **高** | 错误处理重试 | 0.5 天 | 2 天 |
| **中** | 分区查询校验 | 0.5 天 | 2.5 天 |
| **中** | 数据质量检查 | 1 天 | 3.5 天 |
| **中** | 仪表盘缓存 TTL | 0.5 天 | 4 天 |
| **中** | 日志记录 | 0.5 天 | 4.5 天 |
| **中** | 并发控制 | 0.5 天 | 5 天 |
| **中** | 模型名称映射 | 1 天 | 6 天 |
| **低** | 成本监控 | 0.5 天 | 6.5 天 |
| **低** | 时区处理 | 0.5 天 | 7 天 |
| **低** | 单元测试 | 2 天 | 9 天 |

---

## 相关文件

- `scripts/athena/athena_engine.py` - Athena 查询引擎
- `scripts/athena/queries.py` - SQL 查询模板
- `scripts/athena/pricing_engine.py` - 价格计算引擎
- `scripts/athena/report_builder.py` - Excel 报表生成
- `scripts/athena/bill_cron.py` - 定时任务
- `scripts/athena/bill_dashboard.py` - Streamlit 仪表盘
- `scripts/athena/discounts.json` - 折扣配置

---

## 变更历史

| 日期 | 版本 | 说明 | 作者 |
|------|------|------|------|
| 2026-04-25 | 1.0 | 初始文档 | Claude |
