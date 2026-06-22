# Agent Workbench

这个目录用于承载 Agent 沙箱工作台的方案、接口契约和后续实现代码。

工作台目标：

- 复用当前项目已有的账单生成与对账能力。
- 用 OpenSandbox + Docker 提供 Codex/Agent 隔离执行环境。
- 提供面向运营的 Web 工作台：任务中心、资料库、生成账单、问 Agent、处理建议、历史经验。
- 将历史对话和对账经验沉淀为可复用资产，并版本化存储。
- 让 Agent 作为实时对话助手，默认带上本次账单、供应商资料和计费口径。

核心边界：

```text
scripts/athena
  = 确定性出账/对账引擎

agent-workbench
  = 对账运营工作台、实时对话 Agent、历史经验沉淀

OpenSandbox
  = 隔离运行 Codex/Agent/脚本

S3
  = 任务记录、账单结果、资料归档、经验资产
```

## 推荐第一阶段形态

```text
单台 EC2
  + Docker Compose
  + OpenSandbox Docker runtime
  + Workbench Web/API
  + Runner Orchestrator
  + 当前仓库 scripts/athena
  + S3 Skill Registry
```

后续迁移路线：

```text
单机 Docker
  -> ECS on EC2
  -> EKS + OpenSandbox Kubernetes runtime
```

## 文档

- [总体架构](docs/architecture.md)
- [Athena 系统集成契约](docs/athena-integration.md)
- [S3 与 Skills 设计](docs/s3-skills.md)
- [Job 类型与状态机](docs/job-model.md)
- [Pricing/Discounts DB 管理](docs/pricing-config-management.md)
- [本地 Docker 端到端验证](docs/local-docker-e2e.md)
- [AWS 部署文档](docs/aws-deployment.md)
- [Workbench UX 实施方案](docs/ux-implementation-plan.md)
> Billing Automation v2 final plan: [账单自动化最终综合方案](docs/billing-automation-final-plan.md)
