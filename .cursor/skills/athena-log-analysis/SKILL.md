---
name: athena-log-analysis
description: >-
  Athena 账单工具链：CLI/Web/定时任务，覆盖月度账单、逐条明细导出、利润分析、
  分段计费重算、供应商对账、折扣管理、异常检测。Use when the user mentions
  Athena, SQL 查询, 离线分析, 数据分析, 出账单, 费用查询, 用量统计, 错误分析,
  对账, 交叉对账, 用户账单, 模型用量, 重算, recalc, 降档, flat-tier, 利润,
  profit, 折扣, discount, 导入账单, import bill, crosscheck, 分段计费,
  tiered pricing, 明细导出, detail export, 逐条明细,
  or asks to query/analyze S3 log data or generate billing reports.
---

# Athena 账单与分析工具链

所有脚本位于 `scripts/athena/`，工作目录为 `scripts/athena`。

## 环境准备

```bash
cd scripts/athena
pip install -r requirements.txt
export $(grep -v '^#' ../../.env | grep -v '^$' | xargs)
```

**注意：** 每次新开终端都要重新 export 环境变量，否则报 `NoCredentialsError`。

## 一、CLI 工具 (`bill_cli.py`)

### 标准出账流程（推荐）

每月出账的标准操作：先导出聚合汇总，再导出逐条明细。

```bash
cd scripts/athena
export $(grep -v '^#' ../../.env | grep -v '^$' | xargs)

# Step 1: 聚合账单（~3-5 秒，缓存命中更快）
python bill_cli.py bill --month 2026-03 --user-id 89 --flat-tier -o output/
# 输出: output/bill_2026-03_user89_flattier.xlsx

# Step 2: 含逐条明细（大用户 ~5-8 分钟，小用户 ~20 秒）
python bill_cli.py bill --month 2026-03 --user-id 89 --flat-tier --detail -o output/
# 输出: output/bill_2026-03_user89_flattier.xlsx (汇总)
#       output/bill_2026-03_user89_flattier_detail.csv.gz (逐条明细)
```

明细导出采用按天并行查询 + S3 直接下载 + Athena 端 json_extract，208 万条约 7-8 分钟。

### 月度账单（含四层价格）

```bash
# 全平台月度账单 Excel（含刊例价/成本/客户应付/利润）
python bill_cli.py bill --month 2026-03 -o output/

# 指定用户
python bill_cli.py bill --month 2026-03 --user-id 89 -o output/

# 降档模式
python bill_cli.py bill --month 2026-03 --user-id 89 --flat-tier -o output/

# 含逐条明细（CSV.gz 压缩）
python bill_cli.py bill --month 2026-03 --user-id 89 --flat-tier --detail -o output/

# 人民币
python bill_cli.py bill --month 2026-03 --currency CNY -o output/
```

### 利润分析

```bash
# 利润概览
python bill_cli.py profit --month 2026-03

# 含用户明细
python bill_cli.py profit --month 2026-03 --detail

# 导出
python bill_cli.py profit --month 2026-03 -o profit.xlsx
```

### 分段计费重算（recalc）

从 Athena 拉逐条原始数据，用 PRICING 定价表重算刊例价（含 cache token 拆分），对比系统 quota 扣费。

```bash
# 基础重算
python bill_cli.py recalc --start 2026-03-01 --end 2026-03-15 -o output/

# 指定用户 + 降档模式（分段模型强制用低档价）
python bill_cli.py recalc --start 2026-03-01 --end 2026-03-28 \
    --user-id 18 --flat-tier -o output/

# 从某日起降档（之前按正常分段计费）
python bill_cli.py recalc --start 2026-03-01 --end 2026-03-28 \
    --flat-tier-since 2026-03-15 -o output/

# 指定渠道
python bill_cli.py recalc --start 2026-03-01 --end 2026-03-28 \
    --channel-id 25 -o output/
```

**降档说明：** `--flat-tier` 仅对 `claude-opus-4-6` 和 `claude-sonnet-4-6` 生效，强制使用 200K 以内低档价。`--flat-tier-since YYYY-MM-DD` 表示该日期之前仍按正常分段计费。

**输出 Excel 含：** 汇总表（用户×模型，重算 vs 系统扣费对比）+ 差异分析表（差额大的记录）。

### 供应商账单导入与对账

```bash
# 导入供应商账单（自动检测列名）
python bill_cli.py import-bill vendor_bill.csv --channel-id 25 --month 2026-03

# 手动指定列名
python bill_cli.py import-bill vendor_bill.csv --model-col "产品名称" --amount-col "消费金额"

# 交叉对账（我方 vs 供应商，按模型对比）
python bill_cli.py crosscheck --month 2026-03 --vendor vendor_bill.csv \
    --channel-id 25 -o output/
```

支持 CSV 和 Excel 格式，自动识别常见列名：模型/model/model_name、额度/amount/total/cost。

### 折扣管理

```bash
# 查看所有折扣配置
python bill_cli.py discount list

# 设置成本折扣（渠道级）
python bill_cli.py discount set-cost --id 25 --rate 0.41 --name "MateCloud"

# 设置客户折扣（用户级）
python bill_cli.py discount set-rev --id 18 --rate 0.65 --name "GMICloud"

# 按模型设置不同折扣
python bill_cli.py discount set-cost --id 25 --model "claude-opus-4-6" --rate 0.35
```

折扣配置存储在 `scripts/athena/discounts.json`，三级匹配：精确(key×model) > 通配(key×*) > 默认(*)。

### 其他命令

```bash
python bill_cli.py kpi --month 2026-03           # KPI 概览
python bill_cli.py ranking --month 2026-03        # 模型排行
python bill_cli.py users --month 2026-03          # 用户排行
python bill_cli.py channels --month 2026-03       # 渠道汇总
python bill_cli.py daily --date 2026-03-29 -o .   # 日报
python bill_cli.py anomaly --month 2026-03 -o .   # 异常检测报告
python bill_cli.py query "SELECT ..." -o r.xlsx   # 自由 SQL
```

## 二、Web 仪表盘 (`bill_dashboard.py`)

```bash
streamlit run bill_dashboard.py
# 浏览器打开 http://localhost:8501
```

Tab 页：
- **费用趋势** — 每日费用/调用量/Token 消耗折线图
- **利润分析** — KPI 卡片 + 用户利润分解 + 模型利润明细 + 完整定价明细表
- **重算分析** — 选择时间段/用户/渠道/降档模式，一键重算并下载 Excel
- **对账** — 上传供应商 CSV/Excel，一键交叉对比，下载对账报告
- **模型分析** — 费用分布饼图 + 排行表
- **用户分析** — 用户×模型明细
- **渠道分析** — 渠道费用分布
- **异常检测** — 异常扣费 + 重复计费
- **错误分析** — 按天查询 error_logs
- **折扣管理** — 可视化编辑成本/客户折扣，支持批量操作
- **导出** — 一键生成月度账单/异常报告 Excel，支持含逐条明细 CSV.gz

## 三、定时任务 (`bill_cron.py`)

```bash
python bill_cron.py              # 前台运行
nohup python bill_cron.py &      # 后台运行
python bill_cron.py --run-daily  # 立即执行日报
python bill_cron.py --run-monthly # 立即执行月报
```

## 四层价格体系

| 层级 | 计算方式 | 配置位置 |
|------|---------|---------|
| 刊例价 | quota ÷ 500000 (USD) | 系统自动 |
| 成本价 | 刊例价 × cost_discount(channel, model) | discounts.json |
| 客户价 | 刊例价 × revenue_discount(user, model) | discounts.json |
| 利润 | 客户价 - 成本价 | 自动计算 |

## 分段计费定价表

定义在 `pricing_engine.py` 的 `PRICING` 字典中，与 `gen_bill.py` 保持一致。支持：
- **固定价模型**：如 `claude-haiku-4-5-20251001`，单一价格
- **分段价模型**：如 `claude-opus-4-6`，按 prompt_tokens 是否超过 200K 分两档
- **降档模式**：`flat_tier=True` 强制分段模型使用低档价

新增模型时需同步更新 `PRICING` 字典。

## 成本控制

| 措施 | 效果 |
|------|------|
| S3 查询缓存 | 相同查询不重复扫描；历史月份永久缓存，当月 1h TTL，当天 10min |
| raw_logs 分区校验 | 必须指定 day，防止全月扫描 |
| usage_logs 优先 | 账单分析全走 usage_logs（~450 MB/月），单次扫描 ~$0.002 |
| 明细导出按天分片 | 31 天并行查询，分区裁剪，总扫描量 ~500 MB，~$0.0025 |
| S3 直接下载 | 跳过 get_query_results 分页 API，200 万行下载从 20min → 30s |
| Athena 端 json_extract | 不传输 other 原始 JSON，省 ~1GB 传输量 |

### 明细导出性能参考

| 场景 | 耗时 | Athena 费用 |
|------|------|-------------|
| 用户 89 整月 208 万条 | ~7-8 分钟 | ~$0.0025 |
| 单日 6.5 万条 | ~10 秒 | ~$0.00007 |
| 小用户整月 ~5 万条 | ~20 秒 | ~$0.0003 |

## 文件索引

| 文件 | 说明 |
|------|------|
| `athena_engine.py` | Athena 查询引擎 + S3 缓存 + S3 直接下载 + 并行查询 |
| `queries.py` | 预置 SQL 模板（含 raw_usage_detail_daily 按天明细查询） |
| `pricing_engine.py` | 四层价格引擎 + 分段计费重算 + 对账函数 |
| `cost_import.py` | 通用成本账单导入器（CSV/Excel） |
| `report_builder.py` | Excel 报表生成（月报/日报/异常/重算/对账） |
| `discounts.json` | 折扣配置（渠道×模型成本折扣 + 用户×模型客户折扣） |
| `bill_cli.py` | CLI 入口 |
| `bill_cron.py` | 定时任务调度 |
| `bill_dashboard.py` | Streamlit Web 仪表盘 |
| `query_athena.py` | 轻量查询工具 |
| `setup_athena.py` | Athena 建表脚本 |
| `01-04_*.sql` | 建表 DDL |
| `05_common_queries.sql` | SQL 查询参考 |

## Athena 表结构

S3 桶 `ezmodel-log`，三类 ndjson.gz 日志，Partition Projection 自动分区：

| 表 | S3 前缀 | 用途 |
|----|---------|------|
| `ezmodel_logs.usage_logs` | `llm-usage-logs/` | 账务核心 |
| `ezmodel_logs.raw_logs` | `llm-raw-logs/` | 完整请求/响应（大） |
| `ezmodel_logs.error_logs` | `llm-error-logs/` | 仅非 2xx |

### usage_logs 关键字段

`request_id`, `created_at`(unix秒), `user_id`, `username`, `channel_id`, `model_name`, `prompt_tokens`, `completion_tokens`, `quota`(÷500000=USD), `other`(JSON), `is_stream`, `use_time_seconds`

### other JSON 子字段

用 `json_extract_scalar(other, '$.key')` 提取：`frt`(首token时间ms), `cache_tokens`, `cache_creation_tokens`, `tiered_cache_creation_tokens_5m`, `tiered_cache_creation_tokens_1h`, `web_search`
