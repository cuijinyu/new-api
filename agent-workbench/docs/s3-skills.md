# 资料归档与经验库

## 1. S3 Bucket 结构

建议使用独立 bucket 或独立 prefix：

```text
s3://agent-workbench/
  jobs/
  billing/
  skills/
  datasets/
  temp/
```

## 2. 任务结果文件

```text
jobs/
  2026-06-19/
    job-abc123/
      job.json
      input/
      workspace/
      logs/
      output/
      suggestions/
```

必须保留：

- job 输入。
- 执行命令。
- stdout/stderr。
- Codex report。
- patch。
- dry-run 结果。
- Skill 草稿。
- 建议处理记录。

## 3. 账单结果文件

```text
billing/
  2026-06/
    run-xxx/
      command.json
      bill.xlsx
      detail.csv
      summary.json
      stdout.log
      stderr.log
      athena/
```

正式账单只从 `billing/` 下的正式 `billing_run` 读取。

## 4. Skills Registry

```text
skills/
  vendor-reconcile/
    1001ai/
      v1/
        SKILL.md
        manifest.json
        sql/
        examples/
        tests/
        templates/
      latest.json

  claude-anomaly/
    cache-creation-fraud/
      v1/
        SKILL.md
        manifest.json
        sql/
        examples/
        tests/
```

## 5. Skill Manifest

```json
{
  "name": "claude-cache-creation-fraud",
  "version": "v1",
  "category": "claude-anomaly",
  "vendor": "*",
  "tags": ["claude", "cache_creation", "rawlogs", "athena"],
  "entrypoint": "SKILL.md",
  "created_from_job": "job-abc123",
  "created_at": "2026-06-19T00:00:00Z",
  "status": "active"
}
```

## 6. Skill 发布流程

```text
codex_investigation
  -> output/skill_draft/
  -> operator reviews, edits, and saves
  -> skill_publish job
  -> write skills/<category>/<name>/vN/
  -> update latest.json
```

## 7. 本次 Claude 异常应沉淀的 Skills

建议沉淀：

```text
skills/claude-anomaly/cache-creation-fraud/v1/
skills/claude-anomaly/model-mismatch-strict-parse/v1/
skills/vendor-reconcile/1001ai/v1/
```

其中 `model-mismatch-strict-parse` 必须记录：

- 不要用 response body 第一个 `"model"` 字段判断真实模型。
- JSON 响应只认顶层 `$.model`。
- SSE 响应只认 `message_start.message.model`。
- `tool_use.input.model` 不能作为响应模型。
- ch65 `claude-opus-4-6 -> haiku` 是误判案例，应放入 negative example。
