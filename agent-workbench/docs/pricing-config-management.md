# Pricing/Discounts DB 管理方案

## 1. 背景

当前 Athena Billing Worker 依赖文件配置：

```text
scripts/athena/pricing.json
scripts/athena/discounts.json
```

这些文件适合脚本执行，但不适合作为长期管理源头：

- 不方便做建议处理和处理记录追溯。
- 不方便记录生效时间。
- 不方便查询历史版本。
- 不方便按供应商、渠道、模型、用户维度追溯。
- 不方便让 Codex 修改后做影响评估。

因此工作台需要把 pricing、discounts、model mapping、vendor mapping 等账务配置提升为 **DB 级管理对象**。

核心原则：

```text
DB = 配置事实源
JSON = 每次 billing_run 前导出的兼容快照
Git patch = 规则代码变更和可审计变更载体
S3 = 每次 run 的配置快照归档
```

## 2. 目标

- 在 DB 中管理 pricing、discounts、rate card、vendor mapping。
- 所有配置调整都先形成建议，再由用户选择应用、忽略或保存为经验。
- 每次正式出账绑定一个不可变配置版本。
- 继续兼容现有 `scripts/athena` 系统，不要求第一阶段重写 pricing engine。
- Agent 可以提出 DB 配置调整草稿，但不能直接生效。
- 用户选择应用建议后生成配置版本，并导出为 `pricing.json` / `discounts.json` 供账单后台使用。

## 3. 配置对象

建议 DB 管理以下对象：

```text
pricing_rules
discount_rules
vendor_rate_cards
model_mappings
channel_vendor_mappings
billing_config_versions
billing_config_suggestions
```

### pricing_rules

用于替代或生成 `pricing.json`。

字段建议：

```text
id
model_pattern
model_name
channel_id nullable
vendor nullable
input_price
output_price
cache_read_price
cache_write_price
unit
currency
priority
effective_from
effective_to
status
created_by
created_at
updated_at
```

### discount_rules

用于替代或生成 `discounts.json`。

字段建议：

```text
id
name
scope_type              # global / vendor / channel / model / user / group
vendor nullable
channel_id nullable
model_pattern nullable
user_id nullable
group_name nullable
discount_type           # multiplier / fixed_price / tiered / override
discount_value_json
priority
effective_from
effective_to
status
reason
created_by
created_at
updated_at
```

### vendor_rate_cards

供应商原始报价卡，保留供应商口径。

```text
id
vendor
rate_card_name
source_type             # xlsx / csv / api / manual
source_s3_uri
currency
effective_from
effective_to
raw_json
normalized_json
status
created_at
```

### model_mappings

处理供应商模型名、我方模型名、官方模型名之间的映射。

```text
id
vendor
channel_id nullable
source_model
canonical_model
official_model nullable
mapping_type            # exact / regex / alias
priority
effective_from
effective_to
status
notes
```

### channel_vendor_mappings

渠道与供应商族的归属关系。

```text
id
channel_id
channel_name
vendor
vendor_family
effective_from
effective_to
status
```

## 4. 版本模型

正式出账不能直接引用“当前 DB 状态”，必须引用一个不可变版本。

### billing_config_versions

```text
id
version
status                  # draft / active / archived
pricing_snapshot_s3_uri
discounts_snapshot_s3_uri
model_mapping_snapshot_s3_uri
source_change_request_id
created_by
created_at
activated_by
activated_at
checksum
```

每次正式出账记录：

```text
billing_run.config_version_id
```

这样可以保证同一个账单未来可复现。

## 5. 变更流程

```text
Agent/用户提出建议
  -> billing_config_suggestions
  -> 生成影响评估 dry-run
  -> 用户选择应用/忽略/保存经验
  -> 写入 DB active/draft rule
  -> 生成 billing_config_version
  -> 导出 JSON 快照到 S3
  -> 正式 billing_run 使用该 config_version
```

Agent 只能创建建议，不能直接激活规则。

### billing_config_suggestions

```text
id
type                    # pricing / discount / mapping / vendor_rate_card
status                  # draft / suggested / applied / discarded / saved_as_experience
proposed_by             # user / agent
job_id nullable
reason
change_payload_json
impact_summary_json
dry_run_before_s3_uri
dry_run_after_s3_uri
patch_diff_s3_uri nullable
handled_by
handle_comment
created_at
handled_at
applied_at
```

## 6. JSON 导出兼容层

为了不破坏现有 `scripts/athena`，第一阶段新增一个导出步骤：

```text
DB config version
  -> export_pricing_json
  -> export_discounts_json
  -> materialized files in workspace
  -> scripts/athena/bill_cli.py
```

每次 `billing_run` workspace：

```text
/workspace/config/
  pricing.json
  discounts.json
  model_mappings.json
  config_version.json
```

然后 Runner 以兼容方式覆盖或指定配置文件。

如果当前 `bill_cli.py` 暂不支持 `--pricing-file` / `--discounts-file` 参数，第一阶段可以在 job workspace 内复制仓库后替换：

```text
workspace/repo/scripts/athena/pricing.json
workspace/repo/scripts/athena/discounts.json
```

后续建议给 `bill_cli.py` 增加显式参数：

```bash
python scripts/athena/bill_cli.py bill \
  --month 2026-06 \
  --pricing-file /workspace/config/pricing.json \
  --discounts-file /workspace/config/discounts.json \
  -o /workspace/output
```

## 7. Agent 工作方式

Agent 不再直接修改生产 `discounts.json` 作为事实源，而是输出：

```text
output/config_suggestion.json
output/report.md
output/impact_summary.json
output/skill_draft/
```

`config_suggestion.json` 示例：

```json
{
  "type": "discount",
  "reason": "1001AI 2026-06 supplier bill shows updated Claude discount",
  "changes": [
    {
      "action": "create_discount_rule",
      "scope_type": "channel",
      "channel_id": 65,
      "model_pattern": "claude-*",
      "discount_type": "multiplier",
      "discount_value_json": {"multiplier": 0.82},
      "effective_from": "2026-06-01",
      "effective_to": null
    }
  ],
  "evidence": [
    "s3://agent-workbench/jobs/2026-06-19/job-abc/output/diff.csv"
  ]
}
```

用户选择应用建议后，由系统写入 DB 并生成新 config version。

## 8. 与 Git 的关系

DB 管配置，Git 管代码和默认 seed。

保留 Git 中的：

```text
scripts/athena/pricing.json
scripts/athena/discounts.json
```

作为：

- 本地开发默认值。
- DB 初始化 seed。
- 灾备 fallback。

生产正式出账使用 DB 导出的版本化快照，不直接依赖 Git 工作树中的默认 JSON。

## 9. 审计要求

每次配置变更必须记录：

- 谁提出。
- 谁处理。
- 为什么改。
- 影响哪个月份、渠道、模型、用户。
- dry-run 前后金额。
- 对账差异是否收敛。
- 生成了哪个 config version。
- 哪些 billing_run 使用了该版本。

## 10. 迁移步骤

### Phase 1：DB 只读导入

- 建表。
- 从 `pricing.json` / `discounts.json` 导入 DB。
- 生成 version `v0`。
- 导出 JSON 后与原文件做 diff，确保一致。

### Phase 2：正式出账使用 DB 快照

- `billing_run` 绑定 config_version。
- Worker 启动前导出 JSON。
- 出账产物归档 config snapshot。

### Phase 3：Workbench 管理建议

- UI 支持新增/编辑 discount rule。
- UI 支持应用、忽略、保存经验。
- Agent 输出 config suggestion。
- 应用建议后生成新版本。

### Phase 4：逐步改造 pricing_engine

- `pricing_engine.py` 仍可读 JSON。
- 后续可以增加 DB adapter。
- 最终可选择直接从 DB snapshot 计算，但不作为第一阶段目标。
