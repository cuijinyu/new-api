# 任务类型与状态机

## 1. 任务类型

### billing_run

生成账单任务。内部调用当前项目 `scripts/athena/bill_cli.py`，用户侧不暴露脚本细节。

### supplier_reconcile

供应商账单标准化与自动对账。

### agent_conversation

实时对话 Agent 任务。创建时自动带上本次账单、供应商资料、计费口径和可引用的历史经验。

### skill_publish

经验沉淀任务。

### billing_rerun_after_suggestion

应用建议后，基于新计费口径或新规则重新生成账单。

## 2. 状态机

```text
CREATED
  -> QUEUED
  -> PREPARING_WORKSPACE
  -> FETCHING_INPUTS
  -> LOADING_SKILLS
  -> CREATING_SANDBOX
  -> RUNNING
  -> COLLECTING_RESULTS
  -> SUGGESTION_READY
  -> APPLIED / DISCARDED / SAVED_AS_EXPERIENCE
  -> RERUNNING_BILLING
  -> COMPLETED
```

异常状态：

```text
FAILED
TIMED_OUT
CANCELLED
SANDBOX_LOST
SUGGESTION_EXPIRED
```

## 3. 任务记录字段

```json
{
  "id": "job-abc123",
  "type": "agent_conversation",
  "status": "RUNNING",
  "created_by": "user",
  "created_at": "2026-06-19T00:00:00Z",
  "started_at": "2026-06-19T00:01:00Z",
  "finished_at": null,
  "month": "2026-06",
  "channel_id": 65,
  "vendor": "1001AI",
  "s3_prefix": "s3://agent-workbench/jobs/2026-06-19/job-abc123/",
  "sandbox_id": "sbx_xxx",
  "billing_run_id": "run-xxx",
  "error_message": null
}
```

## 4. 后台执行步骤

```text
1. 创建任务工作目录。
2. 下载本次资料和账单结果。
3. 下载匹配的历史经验。
4. 准备 instructions.md。
5. 调 OpenSandbox 创建 sandbox。
6. 上传 workspace 到 sandbox。
7. 执行 Codex/Agent 命令。
8. 流式采集对话和检查步骤。
9. 下载结果文件。
10. 归档结果。
11. 销毁 sandbox。
12. 更新任务状态。
```

## 5. Agent 输出契约

必须输出：

```text
output/report.md
output/result.json
```

可选输出：

```text
output/patch.diff
output/skill_draft/
output/dry_run_before/
output/dry_run_after/
```

`result.json`：

```json
{
  "status": "completed",
  "summary": "发现供应商账单折扣变更，需要调整 discounts.json",
  "suggestion_ready": true,
  "patch_path": "output/patch.diff",
  "impact": {
    "month": "2026-06",
    "channel_id": 65,
    "amount_usd_delta": -123.45
  },
  "recommended_next_job": "billing_rerun_after_suggestion"
}
```
