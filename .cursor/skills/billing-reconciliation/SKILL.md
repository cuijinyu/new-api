---
name: billing-reconciliation
description: >-
  Generate billing reports and reconcile accounts for the LLM API platform.
  Covers: GMICloud monthly bills (gen_bill.py), daily S3 log reconciliation
  (reconcile.py), DB anomaly checks (duplicate/failed billing), raw log error
  scanning, and stream interrupt detection. Use when the user mentions 账单,
  对账, reconcile, billing, GMI, MateCloud, 月账单, 费用, 异常检查, 重复计费,
  失败计费, stream 中断, or asks to generate/check/export any billing data.
---

# 账单与对账工具体系

所有脚本位于 `scripts/reconcile/`，工作目录为 `scripts/`。

## 一、GMICloud 月度账单 (`gen_bill.py`)

**用途：** 从 `logs_analysis.db` 生成 GMICloud 的 Claude 模型月度账单 Excel。

**核心公式：**
- 刊例价 = `quota / 500,000` (USD)
- GMI 应付 = 刊例价 × 0.65
- 我方成本 = 刊例价 × 0.41

**输出：** `reconcile/GMICloud_bill_{YYYY-MM}.xlsx`（三个 Tab：按模型汇总、调用明细、三方对比）

### 新增月份流程

**Step 1 — 转换 MateCloud 账单 xlsx → CSV**

MateCloud 提供的 xlsx（如 `EZmodel-2026年X月账单.xlsx`）需转为 CSV。xlsx Claude sheet 列映射：

| 列索引 | 含义 | 目标 CSV 列 |
|--------|------|-------------|
| 0 | 时间 (datetime) | 时间 |
| 1 | 类型 | 类型 |
| 2 | 用户 | 用户 |
| 3 | 令牌 | 令牌 |
| 4 | 模型 | 模型 |
| 5 | 金额（折后） | 不用 |
| 6 | 原价（刊例价） | 额度 + 原价 |
| 7 | 折扣 | 折扣 |
| 8 | 提示 tokens | 提示 |
| 9 | 补全 tokens | 补全 |

注意：xlsx sheet 名因 Windows 编码问题可能乱码，用 `wb.sheetnames[1]` 按索引取。

```python
import openpyxl, csv
wb = openpyxl.load_workbook('reconcile/EZmodel-2026年X月账单.xlsx',
                            read_only=True, data_only=True)
ws = wb[wb.sheetnames[1]]
out = 'reconcile/EZmodel渠道账单/[24-25]MateCloud/EzmodelX月账单_明细.csv'
with open(out, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['时间','类型','用户','令牌','模型','额度','原价','折扣','提示','补全'])
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is None: continue
        ts = row[0]
        ts_str = (f'{ts.month}/{ts.day}/{str(ts.year)[-2:]} '
                  f'{ts.hour}:{ts.minute:02d}:{ts.second:02d}'
                  if hasattr(ts, 'strftime') else str(ts))
        w.writerow([ts_str, row[1], row[2], row[3], row[4],
                    row[6], row[6], row[7], row[8], row[9]])
wb.close()
```

**Step 2 — 更新 `gen_bill.py`**

1. `MATECLOUD_BILLS` 字典添加新月份 CSV 路径
2. `__main__` 的 `tasks` 列表添加 `("YYYY-MM", 月初timestamp, 下月初timestamp)`
3. 如有新 Claude 模型，在 `PRICING` 字典中添加定价（$/M tokens）

**Step 3 — 运行**

```bash
cd scripts && python gen_bill.py
```

---

## 二、S3 原始日志对账 (`reconcile.py`)

**用途：** 从 S3 原始日志独立计算费用，与系统 billed 对比。支持按模型/渠道/用户/小时汇总。

**定价配置：** `reconcile/pricing.json`，包含所有模型（Claude/GPT/Gemini/Grok/DeepSeek/视频模型等）。

### 常用命令

```bash
cd scripts/reconcile

# 对账昨天
python reconcile.py --bucket $S3_BUCKET

# 对账指定日期
python reconcile.py --bucket $S3_BUCKET --date 2026-03-10

# 日期范围
python reconcile.py --bucket $S3_BUCKET --date-range 2026-03-01 2026-03-10

# 按渠道/用户/小时汇总
python reconcile.py --bucket $S3_BUCKET --group-by channel

# 过滤特定用户/模型/渠道
python reconcile.py --bucket $S3_BUCKET --user-id 123 --model claude-sonnet-4-6

# 导出 CSV / Excel 账单
python reconcile.py --bucket $S3_BUCKET --output report.csv
python reconcile.py --bucket $S3_BUCKET --bill bill.xlsx --bill-currency CNY

# 高并发（大量文件）
python reconcile.py --bucket $S3_BUCKET --workers 20 --processes 8
```

### 环境变量

| 变量 | 回退 | 说明 |
|------|------|------|
| `RAW_LOG_S3_BUCKET` | `S3_BUCKET` | S3 桶名（必填） |
| `RAW_LOG_S3_REGION` | `S3_REGION` | AWS 区域 |
| `RAW_LOG_S3_PREFIX` | `S3_PREFIX` | 日志前缀 `llm-raw-logs` |
| `RAW_LOG_S3_ENDPOINT` | `S3_ENDPOINT` | 自定义端点 |
| `RAW_LOG_S3_ACCESS_KEY_ID` | `AWS_ACCESS_KEY_ID` | AK |
| `RAW_LOG_S3_SECRET_ACCESS_KEY` | `AWS_SECRET_ACCESS_KEY` | SK |

---

## 三、DB 异常检查 (`reconcile.py --check-db`)

**用途：** 从 `logs_analysis.db` 检测重试重复计费和失败计费。

```bash
cd scripts/reconcile

# 基本检查
python reconcile.py --check-db --date 2026-03-10

# 导出 CSV（重复簇 + 失败记录）
python reconcile.py --check-db --date 2026-03-10 \
  --check-output reconcile/check_0310

# 宽松模式（含 zero tokens / frt=-1000 等弱信号）
python reconcile.py --check-db --date 2026-03-10 --failure-mode loose

# 原始明细交叉对照（S3 vs DB）
python reconcile.py --check-db --cross-check-raw --date 2026-03-10 \
  --bucket $S3_BUCKET --check-output reconcile/maas_cross_0310
```

**检查项：**
1. **重试重复计费** — 同用户/token/模型/tokens/quota 在时间窗口内多次出现
2. **失败计费** — quota>0 但有 error 字段或失败关键词
3. **原始明细对照** — S3 记录数 vs DB 记录数，找多入账

---

## 四、错误扫描 (`scan_errors.py` / `scan_errors_detail.py`)

**用途：** 扫描 S3 缓存中的 HTTP 4xx/5xx 错误，分类统计。

`scan_errors.py` — 快速汇总（按类别/状态码/渠道）
`scan_errors_detail.py` — 深入分析（overload/rate_limit/timeout/特定渠道，按小时分布）

注意：这两个脚本的 `CACHE_DIR` 路径硬编码，使用前需修改。

---

## 五、Stream 中断检测 (`find_suspect_stream_interrupts.py`)

**用途：** 从 S3 日志找出疑似 stream 自动中断的请求。

```bash
cd scripts/reconcile
python find_suspect_stream_interrupts.py --bucket $S3_BUCKET --date 2026-03-10
python find_suspect_stream_interrupts.py --bucket $S3_BUCKET \
  --date-range 2026-03-01 2026-03-10 \
  --detail-output suspects.csv --summary-output summary.csv
```

**判定逻辑：** 评分制，stream 请求 + HTTP 2xx + 无显式 error，但缺少正常结束信号（[DONE]/finish_reason/message_stop）、缺少 usage、有 response_error 等。

---

## 关键文件索引

| 文件 | 用途 |
|------|------|
| `scripts/gen_bill.py` | GMICloud 月度账单生成（独立脚本） |
| `scripts/logs_analysis.db` | SQLite 数据库（logs 表） |
| `scripts/reconcile/reconcile.py` | S3 日志对账主入口 |
| `scripts/reconcile/pricing.json` | 全模型定价配置 |
| `scripts/reconcile/costing.py` | 费用计算核心（分段/200K 倍率/Web Search） |
| `scripts/reconcile/usage_parser.py` | 响应体 usage 提取（JSON/SSE/Bedrock） |
| `scripts/reconcile/processor.py` | 多线程/多进程批量处理 |
| `scripts/reconcile/data_loader.py` | S3 下载 + 本地缓存 |
| `scripts/reconcile/db_checks.py` | DB 异常检查（重复/失败/交叉对照） |
| `scripts/reconcile/report_export.py` | CSV/Excel 报表导出 |
| `scripts/reconcile/cli.py` | 命令行参数定义 |
| `scripts/reconcile/scan_errors.py` | 错误快速扫描 |
| `scripts/reconcile/scan_errors_detail.py` | 错误深入分析 |
| `scripts/reconcile/find_suspect_stream_interrupts.py` | Stream 中断检测 |
| `scripts/reconcile/EZmodel渠道账单/[24-25]MateCloud/` | MateCloud 账单 CSV |
| `scripts/reconcile/GMICloud_bill_*.xlsx` | 生成的 GMI 账单 |

## pricing.json 维护

新模型上线时在 `pricing.json` 中添加条目。三种计费模式：

1. **Token 计费**：`input_price` + `output_price`（+ 可选 `cache_*_price`）
2. **分段计费**：`tiered_pricing` 数组，按 `min_tokens_k`/`max_tokens_k` 分档
3. **按次计费**：`per_call_price`（视频/图片模型）

价格单位：token 类为 USD/M tokens，per_call 为 USD/次，web_search 为 USD/千次。
