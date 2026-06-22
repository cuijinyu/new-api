# Agent 兼容设计参考

当前 `agent-workbench` 只需要兼容三条真实 Agent 路径：

- `claude_acp`：Claude Code + ACP，走智谱 Anthropic-compatible endpoint。
- `codingplan`：智谱 CodingPlan HTTP driver。
- `codex`：OpenAI Codex CLI。

`fake` 只保留为 E2E 和离线回归替身。OpenCode、Cursor、Aider、Gemini 等暂不纳入当前兼容范围。

## 1. 当前代码基线

现有 runner 已经把兼容范围收在四个 mode 内：

```text
fake
codex
codingplan
claude_acp
```

代码位置：

- `VALID_AGENT_MODES`：`agent-workbench/app/runner/config.py`
- 本地执行入口：`agent-workbench/app/runner/agent_runner.py`
- 智谱 HTTP driver：`agent-workbench/app/runner/codingplan_driver.py`
- Claude Code + ACP driver：`agent-workbench/app/runner/claude_acp_driver.py`

因此后续设计不需要泛化成“支持任意 Agent”。我们只需要把这三条路径做成稳定、可观测、可回退的 adapter。

## 2. 外部项目借鉴边界

| 项目 | 只借鉴什么 |
| --- | --- |
| Multica | runtime/profile/heartbeat/claim/recovery 的后端控制面 |
| Agent Orchestrator | Agent adapter contract：launch/env/activity/resume/preflight 分离 |
| Maestro | 本地进程发现、会话 attach、终端 UX 思路 |

Multica 的 `runtime_profile` 思路仍然有用，但我们不需要支持它的全部 provider。我们的 `protocol_family` 白名单只保留：

```text
claude_acp
codingplan
codex
fake
```

参考：Multica 的 runtime profile 把 `protocol_family`、`command_name`、`fixed_args` 分开建模，适合我们把“Agent 语义”和“实际启动命令”拆开。
[Multica runtime_profile](https://github.com/multica-ai/multica/blob/9d7060caf1b48162a5ecd263c79eb11fc0cea31f/server/migrations/120_runtime_profile.up.sql#L32-L83)

Agent Orchestrator 的 `Agent` interface 值得参考，因为它把启动命令、环境变量、活动状态、恢复命令、preflight 拆成独立能力。
[AO Agent interface](https://github.com/AgentWrapper/agent-orchestrator/blob/5897b4e8d8cefc33f681ab73bf0e3ebc0b17b517/packages/core/src/types.ts#L482-L581)

## 3. 三个 adapter 的定位

| Mode | 名称 | 依赖 | 主要用途 | 当前状态 |
| --- | --- | --- | --- | --- |
| `claude_acp` | Claude Code + 智谱 | `claude`、`acpx`/`npx acpx`、`ZHIPU_CODINGPLAN_API_KEY` | 需要文件工具、较复杂分析、多轮上下文时优先 | 已有 driver |
| `codingplan` | 智谱 CodingPlan HTTP | `ZHIPU_CODINGPLAN_API_KEY` | 账单差异分析、配置建议、无需本地 CLI 的场景 | 已有 driver |
| `codex` | Codex CLI | `codex`、OpenAI/Codex 凭证 | Codex 调查任务、代码/配置辅助分析 | 已有启动命令 |
| `fake` | 本地确定性替身 | 无 | E2E、离线验收、无 key 环境回退 | 必须保留 |

## 4. 建议的统一 adapter contract

当前不需要大型插件系统，只需要一个小接口：

```text
name
mode
preflight()
build_argv(context)
build_env(context)
parse_output(stdout, stderr, output_dir)
emit_events(stdout, stderr)
supports_sandbox
supports_local
```

推荐映射：

| Adapter | `preflight` | `build_argv` | `parse_output` |
| --- | --- | --- | --- |
| `claude_acp` | 检查 `ZHIPU_CODINGPLAN_API_KEY`，检查 `acpx` 或允许 `npx -y acpx`，检查 `claude` | `python claude_acp_driver.py` | 读取 `output/result.json`、`output/report.md`、`live_events.ndjson` |
| `codingplan` | 检查 `ZHIPU_CODINGPLAN_API_KEY` | `python codingplan_driver.py` | 读取 `output/result.json`、可选 `report.md` |
| `codex` | 检查 `codex` CLI，检查 OpenAI/Codex 凭证 | `codex exec --cd ... --output-dir ... --instructions ...` | 读取 output 目录与 stdout/stderr |
| `fake` | 始终通过 | `python fake_agent.py` | 固定 artifact contract |

## 5. 环境变量策略

只允许注入当前三类 adapter 需要的凭证：

| 变量 | 用途 |
| --- | --- |
| `ZHIPU_CODINGPLAN_API_KEY` | `codingplan` 和 `claude_acp` 必需 |
| `ZHIPU_CODINGPLAN_ENDPOINT` | `codingplan` 可选 endpoint |
| `ZHIPU_CODINGPLAN_ANTHROPIC_BASE_URL` | `claude_acp` 的 Anthropic-compatible base URL |
| `ZHIPU_CODINGPLAN_MODEL` | 智谱模型名 |
| `OPENAI_API_KEY` / `CODEX_API_KEY` | `codex` |
| `OPENAI_BASE_URL` | `codex` 可选代理/base URL |
| `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_API_KEY` | `claude_acp` 兼容兜底 |

安全要求：

- 这些变量只能在 agent 子进程启动瞬间注入。
- 不写入 DB、S3 artifact、stdout/stderr 明文。
- `result.json` 和 `report.md` 不允许包含环境变量、token、secret。
- Agent worker 默认不继承 billing worker 的真实 S3/Athena 写权限。

## 6. Runtime profile 最小设计

如果要落 DB，建议只做最小 schema：

```sql
agent_runtime_profiles (
  id uuid primary key,
  display_name text not null,
  mode text not null check (mode in ('claude_acp', 'codingplan', 'codex', 'fake')),
  command_name text,
  fixed_args jsonb not null default '[]',
  enabled boolean not null default true,
  created_at timestamptz not null,
  updated_at timestamptz not null
)
```

`command_name` 的建议值：

| Mode | command_name |
| --- | --- |
| `claude_acp` | `python app/runner/claude_acp_driver.py` |
| `codingplan` | `python app/runner/codingplan_driver.py` |
| `codex` | `codex` |
| `fake` | `python runner/fake_agent.py` |

当前阶段也可以先不落 profile 表，直接继续使用 `AGENT_MODE`。但如果要支持 UI 切换 Agent，profile 表会更清楚。

## 7. 与真实出账的关系

这三个 Agent 都不应该直接负责正式出账。

| 链路 | 是否用 Agent | 说明 |
| --- | --- | --- |
| 正式出账 `billing_run` | 否 | 继续由 deterministic billing worker 读取真实 S3/Athena |
| 明细账单生成 | 否 | 所有账单必须包含明细，由 billing worker 强制校验 |
| 差异解释/供应商对账 | 是 | 可用 `claude_acp`、`codingplan` 或 `codex` |
| 配置建议 | 是 | Agent 只生成建议，用户审批后再入库 |
| E2E | fake 为主 | 无 key 环境也要稳定跑通 |

## 8. 实现顺序

P0：收窄并固化现状

- 文档和 UI 只展示 `claude_acp`、`codingplan`、`codex`、`fake`。
- `AGENT_MODE` 之外的值全部拒绝或 fallback 到 `fake`，并记录明确事件。
- `preflight` 输出具体缺失项，而不是静默 fallback。

P1：增强可观测性

- `agent_events` 统一记录 `run.started`、`tool.call`、`assistant.delta`、`run.completed`、`run.error`。
- `claude_acp` 继续读取 `live_events.ndjson`。
- `codingplan` 把每轮 tool_call 和 HTTP 错误转成事件。
- `codex` 至少记录 stdout/stderr、退出码、output manifest。

P2：增强安全

- 子进程环境变量 allowlist。
- stdout/stderr 脱敏。
- Agent artifact manifest 标记来源 mode、模型、输入文件 checksum。
- Agent worker 与 billing worker IAM 分离。

P3：可选 UI 切换

- UI 允许选择：Claude Code + 智谱、智谱 CodingPlan、Codex、Fake。
- 显示每个 mode 的 preflight 状态。
- 无 key 或 CLI 缺失时禁用真实执行按钮。

## 9. 验收标准

- `AGENT_MODE=claude_acp`：能通过智谱 Anthropic-compatible endpoint 调起 Claude Code，生成 `result.json` 和 `report.md`。
- `AGENT_MODE=codingplan`：无本地 Agent CLI 时也能通过智谱 HTTP driver 完成分析。
- `AGENT_MODE=codex`：Codex CLI 存在且凭证可用时能执行调查任务。
- `AGENT_MODE=fake`：无任何 LLM key 时 E2E 仍稳定通过。
- 任一真实 Agent 失败时，任务状态、错误原因、stdout/stderr 摘要和 artifact manifest 可查。
- 任一 Agent 不得直接修改正式 billing fact、账单明细或已发布账单。

最终原则：当前只兼容 Claude Code + 智谱、智谱 CodingPlan、Codex。其它 Agent 不设计、不展示、不测试。
