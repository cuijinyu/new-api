# S3 原始日志费用计算脚本

从 S3 原始日志中提取 token 用量，按模型价格配置独立计算费用。

## 支持的计费逻辑

- **分段计费 (Tiered Pricing)**：按 input tokens 总量匹配不同价格区间
- **Claude 200K 自动倍率**：无分段配置的 Claude 模型，input >= 200K 时自动 input x2、output x1.5
- **缓存 5m/1h TTL 区分**：Claude 缓存写入支持 5m 和 1h 两种 TTL 独立定价
- **Web Search 工具计费**：Claude ($10/千次)、OpenAI ($10-25/千次)

## 安装

```bash
pip install -r requirements.txt
```

## 价格配置

编辑 `pricing.json`，按模型名称配置价格（单位: USD / 1M tokens）：

```json
{
  "models": {
    "claude-sonnet-4-6": {
      "input_price": 3.0,
      "output_price": 15.0,
      "cache_hit_price": 0.3,
      "cache_write_price": 3.75,
      "cache_write_price_1h": 6.0,
      "tiered_pricing": [
        {"min_tokens_k": 0, "max_tokens_k": 200, "input_price": 3.0, "output_price": 15.0, "cache_hit_price": 0.3, "cache_write_price": 3.75, "cache_write_price_1h": 6.0},
        {"min_tokens_k": 200, "max_tokens_k": -1, "input_price": 6.0, "output_price": 22.5, "cache_hit_price": 0.6, "cache_write_price": 3.75, "cache_write_price_1h": 6.0}
      ]
    },
    "gpt-4o": {
      "input_price": 2.5,
      "output_price": 10.0
    }
  },
  "web_search": {
    "claude": 10.0,
    "openai_high": 25.0,
    "openai_normal": 10.0
  }
}
```

**配置说明：**

| 字段 | 说明 |
|------|------|
| `input_price` | 输入价格 (USD/M tokens) |
| `output_price` | 输出价格 (USD/M tokens) |
| `cache_hit_price` | 缓存命中价格 (USD/M tokens) |
| `cache_write_price` | 缓存写入价格 - 默认/5m TTL (USD/M tokens) |
| `cache_write_price_1h` | 缓存写入价格 - 1h TTL (USD/M tokens)，未配置时回退到 `cache_write_price` |
| `tiered_pricing` | 分段价格数组，按 `min_tokens_k` 升序，`max_tokens_k = -1` 表示无上限 |
| `web_search.claude` | Claude Web Search 每千次调用价格 |
| `web_search.openai_high` | OpenAI Web Search 每千次调用价格 (gpt-4o, gpt-4.1 等) |
| `web_search.openai_normal` | OpenAI Web Search 每千次调用价格 (o3, o4, gpt-5 系列) |

## 用法

```bash
# 对账昨天（默认）
python reconcile.py --bucket my-bucket

# 对账指定日期
python reconcile.py --bucket my-bucket --date 2026-03-10

# 日期范围
python reconcile.py --bucket my-bucket --date-range 2026-03-01 2026-03-10

# 按渠道/用户/小时汇总
python reconcile.py --bucket my-bucket --group-by channel
python reconcile.py --bucket my-bucket --group-by user
python reconcile.py --bucket my-bucket --group-by hour

# 导出 CSV
python reconcile.py --bucket my-bucket --date 2026-03-10 --output report.csv

# 使用自定义 S3 端点（如 LocalStack）
python reconcile.py --bucket test-raw-logs --endpoint http://localhost:4566

# 详细输出
python reconcile.py --bucket my-bucket --verbose
```

## 环境变量

优先读取 `RAW_LOG_S3_*` 前缀的变量（与系统 Go 代码一致），回退到通用名称。

| 变量 | 回退变量 | 说明 | 默认值 |
|------|---------|------|--------|
| `RAW_LOG_S3_BUCKET` | `S3_BUCKET` | S3 桶名 | (必填) |
| `RAW_LOG_S3_REGION` | `S3_REGION` | AWS 区域 | `us-east-1` |
| `RAW_LOG_S3_PREFIX` | `S3_PREFIX` | 日志前缀 | `llm-raw-logs` |
| `RAW_LOG_S3_ENDPOINT` | `S3_ENDPOINT` | 自定义端点 | (空) |
| `RAW_LOG_S3_ACCESS_KEY_ID` | `AWS_ACCESS_KEY_ID` | AWS AK | (环境默认) |
| `RAW_LOG_S3_SECRET_ACCESS_KEY` | `AWS_SECRET_ACCESS_KEY` | AWS SK | (环境默认) |

## 计费逻辑说明

脚本对齐系统 `compatible_handler.go` 的三条计费路径：

1. **有 tiered_pricing 配置**：按 input_tokens 总量（千 tokens）匹配价格区间，各区间独立定价
2. **Claude 模型无 tiered_pricing**：input_tokens >= 200K 时自动应用 input x2、output x1.5 倍率
3. **普通模型**：直接使用基础价格

缓存写入费用按 TTL 区分：5m 使用 `cache_write_price`，1h 使用 `cache_write_price_1h`（未配置时回退）。
