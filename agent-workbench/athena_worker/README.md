# Athena 账单与分析工具链

基于 AWS Athena 的 S3 日志分析平台，提供 CLI 工具、Web 仪表盘和定时任务三个入口。

## 快速开始

```bash
cd scripts/athena

# 安装依赖
pip install -r requirements.txt

# 加载环境变量
export $(grep -v '^#' ../../.env | grep -v '^$' | xargs)
```

## 三个入口

### 1. CLI 工具

```bash
# 月度账单 Excel
python bill_cli.py bill --month 2026-03 -o bills/

# 指定用户账单
python bill_cli.py bill --month 2026-03 --user-id 89 -o bills/

# 日报
python bill_cli.py daily --date 2026-03-29 -o reports/

# 异常检测报告
python bill_cli.py anomaly --month 2026-03 -o reports/

# KPI 概览
python bill_cli.py kpi --month 2026-03

# 模型排行
python bill_cli.py ranking --month 2026-03

# 用户排行
python bill_cli.py users --month 2026-03

# 渠道汇总
python bill_cli.py channels --month 2026-03

# 自由 SQL 查询
python bill_cli.py query "SELECT model_name, COUNT(*) FROM ezmodel_logs.usage_logs WHERE year='2026' AND month='03' GROUP BY model_name"

# 导出查询结果
python bill_cli.py query "SELECT ..." -o result.xlsx
python bill_cli.py query "SELECT ..." -o result.csv
```

### 2. Web 仪表盘

```bash
streamlit run bill_dashboard.py
```

浏览器打开 http://localhost:8501，功能包括：
- KPI 卡片（总费用、调用量、用户数、模型数）
- 每日费用趋势图
- 模型费用饼图/柱状图
- 用户排行 + 用户×模型明细
- 渠道分析
- 异常检测面板
- 错误分析面板（按天查询）
- 一键导出 Excel 账单

### 3. 定时任务

```bash
# 前台运行调度器
python bill_cron.py

# 后台运行
nohup python bill_cron.py &

# 立即执行一次日报
python bill_cron.py --run-daily

# 立即执行一次月报
python bill_cron.py --run-monthly
```

定时任务：
- 日报：每天 UTC 02:00，生成昨天的日报 Excel，上传到 `s3://ezmodel-log/reports/daily/`
- 月报：每月 2 号 UTC 03:00，生成上月账单 + 异常报告，上传到 `s3://ezmodel-log/reports/monthly/`

## 架构

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
│  report_builder.py (Excel 生成)         │
└─────────────┬───────────┬───────────┬───┘
              │           │           │
        bill_cli.py  bill_cron.py  bill_dashboard.py
         (CLI)       (定时任务)     (Web 仪表盘)
```

## 成本控制

| 措施 | 效果 |
|------|------|
| S3 查询缓存 | 相同查询不重复扫描；历史月份永久缓存，当月 1h TTL，当天 10min |
| raw_logs 分区校验 | 必须指定 day，防止全月扫描（~100 GB） |
| usage_logs 优先 | 账单分析全走 usage_logs（~450 MB/月），不碰 raw_logs |
| Streamlit 缓存 | 页面内切换不重复查询 |

预估月度成本：约 $3（正常使用频率）。

## 额度换算

系统内部额度 `quota` 与美元的换算：`quota ÷ 500,000 = USD`

## 文件索引

| 文件 | 说明 |
|------|------|
| `athena_engine.py` | 核心：Athena 查询引擎 + S3 缓存 + 分页 |
| `queries.py` | 核心：预置 SQL 模板（参数化） |
| `report_builder.py` | 核心：Excel 报表生成（openpyxl） |
| `bill_cli.py` | 入口：CLI 工具 |
| `bill_cron.py` | 入口：定时任务调度 |
| `bill_dashboard.py` | 入口：Streamlit Web 仪表盘 |
| `query_athena.py` | 简单查询工具（轻量版） |
| `setup_athena.py` | Athena 建表脚本 |
| `01-04_*.sql` | 建表 DDL |
| `05_common_queries.sql` | SQL 查询参考 |
| `requirements.txt` | Python 依赖 |

## 环境变量

从 `.env` 加载，主要使用：

| 变量 | 说明 |
|------|------|
| `RAW_LOG_S3_REGION` | AWS 区域 |
| `RAW_LOG_S3_ACCESS_KEY_ID` | AWS AK |
| `RAW_LOG_S3_SECRET_ACCESS_KEY` | AWS SK |
| `ATHENA_WORKGROUP` | Athena 工作组（默认 primary） |
| `ATHENA_RESULT_BUCKET` | 查询结果桶（默认 ezmodel-log） |
| `ATHENA_CACHE_BUCKET` | 缓存桶（默认同上） |
| `REPORT_S3_BUCKET` | 报表上传桶（默认同上） |
| `CRON_DAILY_TIME` | 日报时间（默认 02:00 UTC） |
| `CRON_MONTHLY_DAY` | 月报日期（默认 2 号） |
