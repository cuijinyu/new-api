# 本地 Docker 端到端验证方案

## 1. 目标

在本地 Docker 环境完整验证 Agent Workbench 的核心闭环：

```text
配置入库
  -> 导出 pricing.json / discounts.json
  -> Athena Billing Worker dry-run
  -> 供应商账单对账
  -> OpenSandbox 创建 Codex/Agent sandbox
  -> 生成 report / config_change_request / skill_draft
  -> 应用建议
  -> 生成新 config_version
  -> 正式 billing rerun
  -> artifacts 和 Skills 归档
```

本地 E2E 不依赖真实生产 DB，不直接访问生产账务系统。

## 2. 本地 Docker Compose 拓扑

```text
docker compose -f agent-workbench/docker-compose.e2e.yml up
```

建议服务：

```text
postgres
  - Workbench DB
  - pricing/discount rules
  - job 状态

minio
  - 本地 S3 替身
  - jobs/billing/skills/artifacts

localstack optional
  - 可模拟部分 AWS API
  - 第一阶段可不启用

opensandbox-server
  - Docker runtime
  - 创建 per-job sandbox

workbench-api
  - Job API
  - 配置版本 API
  - 建议应用 API

workbench-web
  - 可视化页面

runner-orchestrator
  - 调 OpenSandbox
  - 调 billing worker
  - 上传 artifacts

mock-athena
  - 返回固定 usage/rawlogs fixture
  - 或使用本地 CSV 模拟 Athena query result
```

## 3. 为什么需要 mock Athena

本地 E2E 的目标是验证系统闭环，不是验证 AWS Athena 本身。

因此第一阶段建议支持两种模式：

### fixture mode

使用本地 CSV/JSON 作为查询结果：

```text
agent-workbench/e2e/fixtures/athena/
  usage_logs_2026_06.csv
  raw_logs_2026_06.csv
  supplier_1001ai_2026_06.xlsx
```

Billing Worker 通过环境变量切换：

```text
ATHENA_E2E_MODE=fixture
ATHENA_FIXTURE_DIR=/workspace/e2e/fixtures/athena
```

### real Athena mode

开发者明确提供 `.env` 和 AWS 凭证时，可以访问真实 Athena：

```text
ATHENA_E2E_MODE=real

### 本地 Docker + 正式 Athena（读仓库根 `.env`）

若已在仓库根 `.env` 配置 `RAW_LOG_S3_*`、`WORKBENCH_S3_BUCKET` 等正式 AWS 凭证，可叠加 prod overlay，避免 e2e compose 写死的 MinIO / fixture：

```bash
cd agent-workbench
make up-athena-prod
# 或
docker compose --env-file ../.env \
  -f docker-compose.e2e.yml -f docker-compose.athena-prod.yml \
  up -d workbench-api billing-worker workbench-scheduler workbench-web

make verify-athena-prod
```

确认 `ATHENA_E2E_MODE` 为空、`WORKBENCH_S3_ENDPOINT` 为空、`WORKBENCH_S3_BUCKET` 为正式桶后再重跑月账单/日成本任务。
RAW_LOG_S3_ACCESS_KEY_ID=...
RAW_LOG_S3_SECRET_ACCESS_KEY=...
```

CI 默认必须使用 fixture mode。

## 4. 本地 S3 设计

使用 MinIO：

```text
http://minio:9000
bucket: agent-workbench
access_key: minio
secret_key: minio123
```

初始化 bucket：

```text
agent-workbench/
  jobs/
  billing/
  skills/
  datasets/
```

E2E 断言应检查 MinIO 中是否产生：

```text
billing/2026-06/run-*/
jobs/*/output/report.md
jobs/*/output/result.json
jobs/*/output/config_change_request.json
skills/*/*/v*/
```

## 5. 本地 DB 初始化

Postgres 初始化数据：

```text
agent-workbench/e2e/db/
  001_schema.sql
  010_seed_pricing.sql
  020_seed_discounts.sql
  030_seed_skills.sql
```

必须包含：

- 从 `scripts/athena/pricing.json` 导入的 seed。
- 从 `scripts/athena/discounts.json` 导入的 seed。
- 初始 `billing_config_version = local-v0`。
- 一个测试用户。
- 一个测试供应商 `1001AI`。

## 6. E2E Case 设计

### Case 1：配置导出兼容性

目标：验证 DB 配置可以导出为现有 Athena Worker 兼容 JSON。

步骤：

```text
1. 读取 DB pricing/discount rules。
2. 导出 /workspace/config/pricing.json。
3. 导出 /workspace/config/discounts.json。
4. 与 scripts/athena 默认 seed 做结构校验。
5. 运行 pricing_engine 单元测试或 smoke test。
```

断言：

- JSON 可解析。
- 必要模型价格存在。
- 必要折扣规则存在。
- `billing_config_versions` 生成 checksum。

### Case 2：本地 billing_run

目标：验证正式出账 job 能跑通。

步骤：

```text
1. API 创建 billing_run month=2026-06 channel_id=65。
2. Runner materialize config_version。
3. Billing Worker 使用 fixture Athena 数据。
4. 输出 bill/detail/summary。
5. 上传 MinIO。
```

断言：

- job 状态为 COMPLETED。
- `billing_runs` 有记录。
- MinIO 有 billing artifacts。
- summary 金额符合 fixture 预期。

### Case 3：supplier_reconcile 触发差异

目标：验证供应商账单差异能进入异常队列。

步骤：

```text
1. 上传 supplier_1001ai_2026_06.xlsx fixture。
2. 创建 supplier_reconcile job。
3. 系统生成 diff.csv。
4. 差异超过阈值，自动创建 codex_investigation job。
```

断言：

- `diff.csv` 存在。
- `anomalies.csv` 存在。
- 新 job 类型为 `codex_investigation`。

### Case 4：Codex/Agent sandbox 生成变更请求

目标：验证 OpenSandbox + Agent job 可以跑通。

第一阶段不要求调用真实 Codex，可以使用 deterministic fake agent：

```text
AGENT_MODE=fake
```

fake agent 根据 fixture 固定输出：

```text
output/report.md
output/config_change_request.json
output/impact_summary.json
output/skill_draft/SKILL.md
```

第二阶段再启用真实 Codex：

```text
AGENT_MODE=codex
OPENAI_API_KEY=...
```

断言：

- OpenSandbox sandbox 被创建并销毁。
- job 输出完整。
- 建议状态为待处理。
- Codex sandbox 没有 Docker socket。

### Case 5：应用建议后生成新 config_version

目标：验证 DB 配置管理闭环。

步骤：

```text
1. 应用 config suggestion。
2. 写入新的 discount_rule。
3. 生成 billing_config_version local-v1。
4. 导出新 discounts.json。
5. 触发 billing_rerun_after_apply。
```

断言：

- 新 config_version 存在。
- 新旧 version checksum 不同。
- billing rerun 使用 local-v1。
- rerun summary 金额变化符合 impact_summary。

### Case 6：Skill 发布

目标：验证经验沉淀到本地 S3。

步骤：

```text
1. 保存 skill_draft 为历史经验。
2. 创建 skill_publish job。
3. 写入 MinIO skills/vendor-reconcile/1001ai/v1/。
4. 更新 latest.json。
```

断言：

- `SKILL.md` 存在。
- `manifest.json` 存在。
- `latest.json` 指向 v1。
- 后续 job 能加载该 Skill。

## 7. Fake Agent 设计

为了让 E2E 稳定，必须有 fake agent。

输入：

```text
/workspace/input/
/workspace/skills/
/workspace/instructions.md
```

输出：

```text
/workspace/output/report.md
/workspace/output/result.json
/workspace/output/config_change_request.json
/workspace/output/skill_draft/SKILL.md
```

fake agent 不调用 LLM，只根据 fixture 输出固定结果。

真实 Codex 只在手动 E2E 或 staging 中启用。

## 8. OpenSandbox 本地配置

建议本地配置：

```toml
[server]
host = "0.0.0.0"
port = 8090
api_key = "local-dev-key"
max_sandbox_timeout_seconds = 7200

[runtime]
type = "docker"
execd_image = "opensandbox/execd:v1.0.19"

[docker]
network_mode = "bridge"
host_ip = "host.docker.internal"
drop_capabilities = ["AUDIT_WRITE", "MKNOD", "NET_ADMIN", "NET_RAW", "SYS_ADMIN", "SYS_MODULE", "SYS_PTRACE", "SYS_TIME", "SYS_TTY_CONFIG"]
no_new_privileges = true
pids_limit = 4096

[storage]
allowed_host_paths = ["/srv/agent-workbench/jobs"]

[ingress]
mode = "direct"

[egress]
image = "opensandbox/egress:v1.1.1"
mode = "dns"
```

## 9. Compose 文件建议

后续实现可新增：

```text
agent-workbench/docker-compose.e2e.yml
agent-workbench/e2e/.env.example
agent-workbench/e2e/run-e2e.ps1
agent-workbench/e2e/run-e2e.sh
```

命令：

```bash
docker compose -f agent-workbench/docker-compose.e2e.yml up -d --build
python agent-workbench/e2e/run_e2e.py
docker compose -f agent-workbench/docker-compose.e2e.yml down -v
```

## 10. CI 策略

CI 默认跑：

- fixture mode。
- fake agent。
- MinIO。
- Postgres。
- OpenSandbox Docker runtime smoke test。

CI 不跑：

- real Athena。
- real OpenAI/Codex。
- production S3。

手动 staging 才跑：

- real Athena。
- real Codex。
- real S3 prefix。

## 11. 验收标准

本地 E2E 通过的最低标准：

- 能从 DB 导出 pricing/discount JSON。
- 能用 fixture 跑出 billing_run。
- 能生成供应商对账差异。
- 能创建 OpenSandbox sandbox。
- 能产出 Agent report 和 config_change_request。
- 能应用建议并生成新 config_version。
- 能重跑 billing。
- 能发布 Skill 到 MinIO。
- 全部 artifacts 可在 UI 或 API 查询。
