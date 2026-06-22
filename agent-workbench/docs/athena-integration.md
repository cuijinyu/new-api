# 账单生成与对账系统集成契约

## 1. 现有系统定位

当前项目的 `scripts/athena` 是正式账单生成和对账的确定性系统。`Athena` 是内部执行能力，用户界面统一称为“生成账单”。

关键文件：

```text
scripts/athena/
  bill_cli.py              # 出账 CLI 入口
  athena_engine.py         # Athena 查询、缓存、S3 结果下载
  queries.py               # SQL 生成
  pricing_engine.py        # 价格/折扣计算
  report_builder.py        # 报告/账单构建
  pricing.json             # 定价配置
  discounts.json           # 折扣配置
  *_reconciliation*.py     # 历史供应商对账脚本
```

工作台必须复用这些文件，不重新实现账务逻辑。

## 2. 账单后台调用方式

Workbench 创建生成账单任务后，由后台执行器在受控环境中执行当前项目命令。

示例：

```bash
python scripts/athena/bill_cli.py bill \
  --month 2026-06 \
  -o /workspace/output
```

按渠道出账：

```bash
python scripts/athena/bill_cli.py bill \
  --month 2026-06 \
  --channel-id 65 \
  -o /workspace/output
```

如果需要沿用历史 flat tier 参数：

```bash
python scripts/athena/bill_cli.py bill \
  --month 2026-06 \
  --channel-id 65 \
  --flat-tier \
  -o /workspace/output
```

具体参数以 `bill_cli.py` 当前实现为准，Workbench 只保存 command contract 和执行记录。

## 3. 输入

`billing_run` 输入：

```json
{
  "job_type": "billing_run",
  "month": "2026-06",
  "channel_id": 65,
  "flat_tier": false,
  "git_sha": "<current repo sha>",
  "config_version_id": "cfg-20260619-001",
  "pricing_file": "/workspace/config/pricing.json",
  "discounts_file": "/workspace/config/discounts.json",
  "output_prefix": "s3://agent-workbench/billing/2026-06/run-xxx/"
}
```

`supplier_reconcile` 输入：

```json
{
  "job_type": "supplier_reconcile",
  "vendor": "1001AI",
  "month": "2026-06",
  "our_billing_run_id": "run-xxx",
  "supplier_bill_s3_uri": "s3://agent-workbench/jobs/2026-06-19/job-abc/input/supplier.xlsx"
}
```

`agent_conversation` 输入：

```json
{
  "job_type": "agent_conversation",
  "reason": "supplier_diff_over_threshold",
  "month": "2026-06",
  "vendor": "1001AI",
  "our_billing_run_id": "run-xxx",
  "supplier_reconcile_job_id": "job-abc",
  "historical_session_ids": ["as-history-001"],
  "allowed_actions": ["read", "dry_run", "write_patch", "write_report", "draft_skill"]
}
```

## 4. 输出

`billing_run` 输出到 S3：

```text
billing/2026-06/run-xxx/
  command.json
  stdout.log
  stderr.log
  bill.xlsx
  detail.csv
  summary.json
  athena/
    queries.jsonl
    results/
```

`supplier_reconcile` 输出：

```text
jobs/2026-06-19/job-abc/output/
  supplier_normalized.csv
  diff.csv
  summary.json
  anomalies.csv
  report.md
```

`agent_conversation` 输出：

```text
jobs/2026-06-19/job-codex/output/
  report.md
  patch.diff
  dry_run_before/
  dry_run_after/
  skill_draft/
  result.json
```

## 5. Dry-run 规则

Codex 可以在 sandbox 内执行 dry-run：

```bash
python scripts/athena/bill_cli.py bill \
  --month 2026-06 \
  --channel-id 65 \
  -o /workspace/output/dry_run_after
```

但 dry-run 只能用于影响评估，不作为正式账单。

用户选择应用建议后，Workbench 必须启动新的生成账单任务，由正式账单后台重跑。

## 6. 折扣和定价变更

Codex 对以下文件只能生成 patch：

```text
scripts/athena/discounts.json
scripts/athena/pricing.json
scripts/athena/pricing_engine.py
scripts/athena/queries.py
```

长期设计中，`pricing.json` 和 `discounts.json` 不是生产事实源。生产事实源是 Workbench DB 中的 pricing/discount rules。每次 `billing_run` 会绑定一个不可变 `config_version_id`，Runner 在执行前把该版本导出为兼容现有 Athena 脚本的 JSON 文件：

```text
DB billing_config_version
  -> /workspace/config/pricing.json
  -> /workspace/config/discounts.json
  -> scripts/athena/bill_cli.py
```

因此 Agent 对折扣/定价的建议应优先输出 `config_suggestion.json`，由用户选择应用后写入 DB 并生成新版本；只有 pricing engine 代码逻辑变化时，才生成 Git patch。

建议处理记录必须包含：

- 修改前后 diff。
- 影响月份。
- 影响渠道。
- 影响模型。
- 影响金额。
- 建议原因。
- dry-run 对账结果。

## 7. Athena 权限

正式 Billing Worker：

- 可访问必要 Athena workgroup。
- 可读 raw_logs / usage_logs / error_logs。
- 可写指定 S3 result prefix。

Codex sandbox：

- 默认只读。
- Athena workgroup 应设置扫描量限制。
- 查询必须保存 SQL。
- raw_logs 查询必须带 day 分区过滤。
- 高扫描量查询需要被后台策略拦截，或进入人工确认后的受控重跑。

## 8. 幂等性

`billing_run` 幂等 key：

```text
month + channel_id + git_sha + pricing_version + discounts_version + command_hash
```

同一个 key 重复执行时：

- 默认复用已有结果。
- 如果用户选择 force rerun，生成新的 run_id。

## 9. Agent 对话后的正式闭环

```text
Agent conclusion + suggestion
  -> apply suggestion or save experience
  -> optional patch / merge PR
  -> new git_sha
  -> formal billing_run
  -> supplier_reconcile
  -> archive conversation as historical experience
```
