# OpenRouter 实际扣费巡检方案

## 1. 背景

当前系统已经具备 OpenRouter 渠道、消费日志、价格配置、倍率计费、条件计费、缓存计费等能力。业务希望定期按照 OpenRouter 的价格检查系统已经产生的实际扣费是否正常。

本方案定义一个独立的扣费巡检能力，用 OpenRouter 价格和系统真实请求日志复算应扣额度，并与系统实际写入的 `logs.quota` 对比。

该能力不是账单对账，也不和现有 `recon` 模块结合。

## 2. 定义

### 2.1 巡检对象

巡检对象是系统内已经完成扣费并写入消费日志的 OpenRouter 请求。

核心对比关系：

```text
actual_quota   = 系统实际扣费，来自 logs.quota
expected_quota = 按 OpenRouter 价格和日志 token 用量复算出的应扣 quota
```

巡检结论回答的问题是：

```text
系统对这条 OpenRouter 请求的实际扣费，是否符合 OpenRouter 价格模型和系统计费规则？
```

### 2.2 非目标

本方案不做以下事情：

- 不使用 OpenRouter 余额变化判断扣费是否正确。
- 不拉取或导入 OpenRouter 账单。
- 不写入、不复用 `recon_*` 表。
- 不判断 OpenRouter 账户最终真实扣款是否和系统一致。
- 不修改用户余额、token 余额、渠道已用额度。
- 不自动修复价格配置或补退费，至少第一阶段只报告问题。

## 3. 现有代码基础

### 3.1 消费日志

消费日志结构在 `model/log.go`。

关键字段：

```text
logs.id
logs.created_at
logs.type
logs.channel_id
logs.model_name
logs.quota
logs.prompt_tokens
logs.completion_tokens
logs.group
logs.other
logs.request_id
logs.upstream_request_id
```

`logs.quota` 是巡检中的实际扣费来源。

### 3.2 OpenRouter 价格来源

当前已有 OpenRouter 价格拉取思路，位于 `controller/ratio_sync_sources.go`。

来源：

```text
GET https://openrouter.ai/api/v1/models
```

OpenRouter 价格字段：

```text
pricing.prompt
pricing.completion
pricing.input_cache_read
```

这些字段单位是 USD/token，通常是字符串。

### 3.3 quota 换算

系统换算基准在 `common/constants.go`：

```text
QuotaPerUnit = 500000
```

即：

```text
1 USD = 500000 quota
quota / 500000 = USD
```

### 3.4 现有扣费逻辑

主要扣费路径位于：

```text
relay/compatible_handler.go
service/quota.go
```

计费涉及：

- `model_ratio`
- `completion_ratio`
- `cache_ratio`
- `cache_creation_ratio`
- `group_ratio`
- 条件倍率 `cond_multiplier`
- Claude 200K 分段
- tiered pricing
- image/audio token
- web/file search 等工具费用
- 四舍五入规则

巡检应尽量复用或抽取同源计费逻辑，避免另写一套长期漂移的简化公式。

## 4. 总体架构

建议新增独立模块：

```text
openrouter_billing_inspection
```

模块职责：

```text
OpenRouter 价格快照采集
        ↓
OpenRouter 渠道日志扫描
        ↓
按请求发生时间匹配价格快照
        ↓
复算 expected_quota
        ↓
对比 logs.quota
        ↓
记录巡检结果并告警
```

## 5. 数据模型

### 5.1 OpenRouter 价格快照表

表名：

```text
openrouter_price_snapshots
```

字段建议：

```text
id                         bigint primary key
fetched_at                 bigint not null
model_id                   varchar(255) not null
canonical_slug             varchar(255)
local_model_name            varchar(255)
prompt_price_per_token      decimal(24, 18)
completion_price_per_token  decimal(24, 18)
cache_read_price_per_token  decimal(24, 18)
cache_write_price_per_token decimal(24, 18)
image_price                 decimal(24, 18)
request_price               decimal(24, 18)
is_free                     boolean default false
raw_json                    text
created_at                 bigint
```

索引：

```text
idx_or_price_model_time(model_id, fetched_at)
idx_or_price_local_model_time(local_model_name, fetched_at)
idx_or_price_fetched_at(fetched_at)
```

说明：

- 必须保存完整 `model_id`，例如 `anthropic/claude-sonnet-4`。
- `local_model_name` 可以是系统模型名，例如截取 provider 后的 `claude-sonnet-4`，但不能只依赖该字段匹配价格。
- 免费模型需要显式标记 `is_free`，避免 `0` 被误认为缺失。

### 5.2 巡检运行表

表名：

```text
openrouter_billing_inspection_runs
```

字段建议：

```text
id                    bigint primary key
status                varchar(32) not null
trigger_type          varchar(32) not null
window_start          bigint not null
window_end            bigint not null
started_at            bigint not null
finished_at           bigint
total_logs            int default 0
checked_logs          int default 0
normal_count          int default 0
warning_count         int default 0
abnormal_count        int default 0
critical_count        int default 0
missing_count         int default 0
unsupported_count     int default 0
failed_count          int default 0
summary_json          text
created_at            bigint
```

`trigger_type` 可选：

```text
scheduled
manual
backfill
```

### 5.3 巡检明细表

表名：

```text
openrouter_billing_inspection_items
```

字段建议：

```text
id                    bigint primary key
run_id                bigint not null
log_id                bigint not null
created_at            bigint not null
channel_id            int not null
model_name            varchar(255) not null
openrouter_model_id   varchar(255)
price_snapshot_id     bigint
actual_quota          bigint not null
expected_quota        bigint
delta_quota           bigint
diff_rate             decimal(12, 8)
expected_usd          decimal(24, 12)
actual_usd            decimal(24, 12)
input_tokens          int default 0
output_tokens         int default 0
cache_read_tokens     int default 0
cache_write_tokens    int default 0
group_ratio           decimal(12, 6)
cond_multiplier       decimal(12, 6)
status                varchar(32) not null
reason_code           varchar(64)
reason_detail         text
raw_context_json      text
created_record_at     bigint
```

唯一索引：

```text
idx_or_inspection_log_run(run_id, log_id)
```

查询索引：

```text
idx_or_inspection_status(status)
idx_or_inspection_channel_time(channel_id, created_at)
idx_or_inspection_model_time(model_name, created_at)
```

## 6. 价格快照设计

### 6.1 采集频率

建议：

```text
每 6 小时采集一次
```

如果 OpenRouter 请求失败：

- 重试 3 次。
- 本轮快照标记失败。
- 巡检仍可使用最近一份有效快照。

### 6.2 历史价格匹配

不能用当前价格检查历史日志。

对每条日志，应选择：

```sql
fetched_at <= logs.created_at
ORDER BY fetched_at DESC
LIMIT 1
```

如果找不到历史快照：

- 可以使用最近一份快照兜底。
- 明细状态标记为 `price_snapshot_missing` 或 `price_snapshot_after_log`。
- 该结果默认不进入 critical 统计，避免误报。

### 6.3 模型映射

OpenRouter 模型 ID 示例：

```text
anthropic/claude-sonnet-4
openai/gpt-4o-mini
google/gemini-2.5-pro
meta-llama/llama-3.3-70b-instruct
```

系统日志中的模型名可能是：

```text
claude-sonnet-4
gpt-4o-mini
gemini-2.5-pro
```

建议维护独立映射：

```text
openrouter_model_mappings
```

字段：

```text
id
channel_id
local_model_name
openrouter_model_id
priority
enabled
note
created_at
updated_at
```

匹配优先级：

```text
显式 channel_id + local_model_name 映射
显式 local_model_name 映射
OpenRouter model_id 完整等于 logs.model_name
截取 provider 后等于 logs.model_name
无法匹配，标记 missing_model_mapping
```

第一阶段也可以不建映射表，但必须在结果中暴露模糊匹配风险。

## 7. 复算算法

### 7.1 基础公式

OpenRouter 侧预期成本：

```text
expected_usd =
  input_tokens       * prompt_price_per_token
+ output_tokens      * completion_price_per_token
+ cache_read_tokens  * cache_read_price_per_token
+ cache_write_tokens * cache_write_price_per_token
```

系统侧预期 quota：

```text
expected_quota =
  round(expected_usd * QuotaPerUnit * group_ratio * cond_multiplier)
```

其中：

```text
QuotaPerUnit = 500000
```

### 7.2 实际扣费

实际扣费直接来自：

```text
logs.quota
```

实际 USD：

```text
actual_usd = logs.quota / QuotaPerUnit
```

### 7.3 差异计算

```text
delta_quota = actual_quota - expected_quota
diff_rate = abs(delta_quota) / max(abs(actual_quota), abs(expected_quota), 1)
```

解释：

- `delta_quota > 0`：系统多扣。
- `delta_quota < 0`：系统少扣。
- `max(..., 1)` 避免免费模型或零成本请求除零。

### 7.4 token 提取

优先从结构化字段和 `logs.other` 提取。

建议优先级：

```text
input_tokens:
  other.input_text_tokens
  logs.prompt_tokens - cache_read_tokens - cache_write_tokens - input_image_tokens - input_audio_tokens
  logs.prompt_tokens

output_tokens:
  other.output_text_tokens
  other.output_non_image_tokens
  logs.completion_tokens - output_image_tokens - output_audio_tokens
  logs.completion_tokens

cache_read_tokens:
  other.cache_tokens

cache_write_tokens:
  other.cache_creation_tokens
  other.tiered_cache_creation_tokens_remaining
  other.tiered_cache_creation_tokens_5m + other.tiered_cache_creation_tokens_1h
```

如果无法可靠拆分，应标记为 `unsupported_token_breakdown`，不要硬判 abnormal。

### 7.5 group_ratio 和条件倍率

优先从 `logs.other` 读取请求发生时已经落入日志的倍率：

```text
other.group_ratio
other.billing_cond_multiplier
```

如果日志中没有：

- `group_ratio` 可根据 `logs.group` 查询当前配置兜底。
- 但使用当前配置复查历史日志存在误差风险，应标记 `runtime_ratio_missing`。

不建议用当前条件计费配置回放历史请求，除非日志中保存了当时的条件命中结果。

### 7.6 优先使用 OpenRouter usage.cost

如果日志或响应 `usage` 中保存了 OpenRouter 返回的 `cost`，应优先使用：

```text
expected_quota = round(usage.cost * QuotaPerUnit * group_ratio * cond_multiplier)
```

优先级：

```text
OpenRouter usage.cost
历史价格快照 + token 明细
当前价格快照 + token 明细，标记低可信
```

建议后续在消费日志 `other` 中补充：

```text
openrouter_cost
openrouter_model_id
openrouter_generation_id
```

这样巡检准确性会明显提升。

### 7.7 常见模型与场景覆盖矩阵

巡检不应按品牌硬编码计算逻辑，而应先按 OpenRouter 模型元数据和日志上下文识别计费形态，再套用对应复算策略。

识别依据：

```text
OpenRouter architecture.input_modalities
OpenRouter architecture.output_modalities
OpenRouter pricing 字段
logs.model_name
logs.other 中的结构化计费信息
系统 relay format / endpoint type
```

建议将请求归类为以下计费场景：

| 场景 | 典型模型 | 输入 | 输出 | 第一阶段策略 | 最终策略 |
|---|---|---|---|---|---|
| 文生文 | OpenAI GPT、Claude、Gemini 文本模型 | text | text | 支持 | 支持 |
| 视觉理解 | Gemini、GPT vision、Claude vision | text + image | text | 若日志能拆出 image token 则支持，否则 unsupported | 支持 image input token |
| 文生图 | OpenAI image、Gemini image generation 等 | text | image | unsupported，避免误报 | 按 image output token 或按次价格复算 |
| 图文生图 | Gemini image、OpenAI image edit 类 | text + image | image | unsupported | 支持 image input + image output |
| 缓存读取 | Claude cache read、Gemini/OpenRouter cache hit | text/cache | text | 支持 `cache_tokens` | 支持历史价格快照中的 cache read |
| 缓存写入 | Claude cache creation | text/cache_write | text | unsupported 或仅在日志完整时支持 | 支持 5m/1h/默认 cache write |
| 长上下文分段 | Claude >200K、其他 tiered 模型 | text/cache | text | unsupported 或仅同源计算器支持 | 支持 tiered pricing |
| 工具调用 | OpenAI Responses web/file search 等 | text/tool | text/tool | unsupported | 支持工具固定费用 |
| 免费模型 | `:free` 或价格全 0 模型 | text/image | text/image | 支持，但用绝对误差阈值 | 支持 |
| 一口价模型 | 系统 `model_price` 模式 | 任意 | 任意 | unsupported | 按系统一口价规则独立复算 |

### 7.8 Gemini 覆盖策略

Gemini 在 OpenRouter 上常见形态包括：

```text
text -> text
text + image -> text
text -> image
text + image -> image
```

Gemini 巡检要点：

- 文生文请求按普通 input/output token 复算。
- 视觉理解请求必须区分 `input_text_tokens` 与 `input_image_tokens`。
- 文生图或图文生图不能简单把 `completion_tokens` 当文本输出 token。
- 如果日志中存在 `output_image_tokens`、`image_completion_tokens`、`gemini_image_output_token_source`，可进入 image output 复算。
- 如果日志中只有总 `prompt_tokens/completion_tokens`，且模型输出模态包含 image，应标记 `unsupported_image_tokens`。

建议 Gemini 日志补充字段：

```text
input_text_tokens
input_image_tokens
output_text_tokens
output_image_tokens
gemini_image_output_count
gemini_image_output_tokens_per_image
gemini_image_output_token_source
openrouter_cost
openrouter_model_id
```

Gemini 文生图复算优先级：

```text
OpenRouter usage.cost
image output token * OpenRouter image/output price
系统 Gemini image token 规则
unsupported
```

### 7.9 Claude 覆盖策略

Claude 在 OpenRouter 上常见形态包括：

```text
text -> text
text + image -> text
cache read
cache creation
long context / >200K pricing
```

Claude 巡检要点：

- 普通文生文按 input/output token 复算。
- Claude vision 请求必须识别 image input token，不能全部当 text input。
- cache read 读取 `other.cache_tokens`，使用 OpenRouter cache read 价格。
- cache creation 读取 `other.cache_creation_tokens`，如果有 5m/1h 明细，按对应价格拆分。
- Claude >200K 分段不能靠当前模型名粗暴判断，必须使用请求当时总输入 token 和同源分段规则。
- 如果 OpenRouter 响应保存了 `usage.cost`，优先使用 cost，因为它天然包含 provider 实际计费细节。

建议 Claude 日志补充字段：

```text
input_text_tokens
input_image_tokens
cache_tokens
cache_creation_tokens
cache_creation_tokens_5m
cache_creation_tokens_1h
claude_200k_total_input_tokens
claude_200k_input_multiplier
claude_200k_output_multiplier
openrouter_cost
openrouter_model_id
```

Claude 复算优先级：

```text
OpenRouter usage.cost
历史价格快照 + text/cache/image input/output 明细 + Claude 分段规则
同源 DryRunBillingCalculator
unsupported
```

### 7.10 OpenAI 覆盖策略

OpenAI 在 OpenRouter 上常见形态包括：

```text
Chat Completions 文生文
Responses 文生文
vision input
image generation
image edit
web search / file search 工具调用
```

OpenAI 巡检要点：

- Chat Completions 文生文按普通 input/output token 复算。
- Responses 文生文也可以按 input/output token 复算，但要额外检查工具调用费用。
- vision 请求必须拆出 image input token。
- image generation / image edit 请求不能套用文本 completion price。
- 如果系统当前按 `image_generation_call_price` 或 `model_price` 计费，第一阶段应标记 unsupported，避免错误判断。
- web search、file search 等工具调用如果日志中有 call count 和 price，可额外复算，否则标记 `unsupported_tool_charge`。

建议 OpenAI 日志补充字段：

```text
input_text_tokens
input_image_tokens
output_text_tokens
output_image_tokens
image_generation_call
image_generation_call_price
web_search_call_count
web_search_price
file_search_call_count
file_search_price
openrouter_cost
openrouter_model_id
```

OpenAI 文生图复算优先级：

```text
OpenRouter usage.cost
OpenRouter image/output pricing 字段
系统 image_generation_call_price
unsupported
```

### 7.11 支持等级

为了避免一次性覆盖所有复杂场景导致误报，建议每条巡检结果带上 `support_level`：

```text
exact       使用 OpenRouter usage.cost 或完整同源上下文，可信度最高
standard    普通 text/cache token 复算，可信度高
estimated   使用当前配置或不完整拆分，可信度中等
unsupported 暂不可靠复算，不进入异常统计
```

第一阶段建议只把以下场景纳入异常统计：

```text
support_level in (exact, standard)
```

以下场景只记录覆盖率和原因，不判定异常：

```text
vision token 缺明细
image output 缺明细
tool call 缺 call count 或 price
tiered pricing 缺当时分段上下文
model_price 一口价
```

## 8. 状态和阈值

### 8.1 状态

```text
normal       正常
warning      轻微偏差
abnormal     明显偏差
critical     严重偏差
missing      缺少必要数据
unsupported  暂不支持可靠复算
failed       巡检执行失败
```

### 8.2 阈值

建议默认：

```text
abs(delta_quota) <= 2 quota       normal
diff_rate <= 0.5%                 normal
0.5% < diff_rate <= 2%            warning
2% < diff_rate <= 5%              abnormal
diff_rate > 5%                    critical
```

对低金额请求增加绝对阈值，避免一两个 quota 的四舍五入误差造成高百分比误报：

```text
expected_quota < 100 时，以 abs(delta_quota) <= 5 作为 normal
expected_quota < 1000 时，以 abs(delta_quota) <= 10 作为 normal
```

### 8.3 reason_code

建议枚举：

```text
ok
rounding_tolerance
overcharged
undercharged
missing_price_snapshot
missing_model_mapping
missing_openrouter_price
free_model_mismatch
unsupported_image_tokens
unsupported_audio_tokens
unsupported_tool_charge
unsupported_model_price
unsupported_tiered_pricing
unsupported_token_breakdown
runtime_ratio_missing
price_snapshot_after_log
calculator_error
```

## 9. 调度设计

### 9.1 价格快照任务

```text
任务名: openrouter_price_snapshot_job
频率: 每 6 小时
职责: 拉取 OpenRouter 模型价格并保存快照
```

### 9.2 扣费巡检任务

```text
任务名: openrouter_billing_inspection_job
频率: 每 15 分钟
窗口: 最近 30 分钟
延迟: 跳过最近 3 到 5 分钟日志
```

跳过最近几分钟的原因：

- 避免流式请求刚结束但日志尚未完整落库。
- 避免异步补扣或重试造成短暂不一致。

### 9.3 回填任务

```text
任务名: openrouter_billing_inspection_backfill
触发: 手动
用途: 对指定时间范围重新巡检
```

要求：

- 幂等。
- 可按 `channel_id`、`model_name`、`status` 过滤。
- 支持分页或批量大小限制。

## 10. API 设计

### 10.1 手动触发巡检

```text
POST /api/openrouter_billing_inspection/run
```

请求：

```json
{
  "window_start": 1710000000,
  "window_end": 1710003600,
  "channel_id": 12,
  "model_name": "claude-sonnet-4",
  "dry_run": false
}
```

### 10.2 查询运行记录

```text
GET /api/openrouter_billing_inspection/runs
```

参数：

```text
page
page_size
status
start_time
end_time
```

### 10.3 查询明细

```text
GET /api/openrouter_billing_inspection/items
```

参数：

```text
run_id
channel_id
model_name
status
reason_code
min_diff_rate
page
page_size
```

### 10.4 查询摘要

```text
GET /api/openrouter_billing_inspection/summary
```

返回：

```json
{
  "total": 1200,
  "normal": 1178,
  "warning": 12,
  "abnormal": 6,
  "critical": 1,
  "missing": 2,
  "unsupported": 1,
  "top_models": [],
  "top_channels": [],
  "top_reason_codes": []
}
```

## 11. 告警设计

### 11.1 告警触发

建议触发条件：

```text
critical_count > 0
abnormal_count >= 10
同一模型 abnormal 连续 3 轮出现
同一渠道 diff_rate 平均值 > 2%
missing_model_mapping 数量突然增加
```

### 11.2 告警内容

告警必须包含可行动信息：

```text
巡检窗口: 2026-06-08 10:00:00 ~ 10:30:00
渠道: OpenRouter channel 12
模型: claude-sonnet-4
状态: critical
实际扣费: 12500 quota
预期扣费: 9800 quota
差异: +2700 quota / 27.55%
原因: overcharged
价格快照: 2026-06-08 06:00:00
样例日志: log_id=123456
建议: 检查 model_ratio/completion_ratio/cache_ratio 或 group_ratio 是否偏高
```

### 11.3 告警渠道

可复用系统已有通知能力：

- 管理后台通知。
- Webhook。
- 邮件。
- Telegram。

第一阶段建议只做后台列表和系统日志，避免误报直接打扰。

## 12. 前端页面建议

新增页面：

```text
设置 / 巡检 / OpenRouter 扣费巡检
```

页面模块：

```text
运行概览
状态分布
模型差异排行
渠道差异排行
异常明细表
价格快照状态
手动运行入口
```

明细表字段：

```text
时间
渠道
模型
实际 quota
预期 quota
差异
差异率
状态
原因
价格快照时间
request_id
log_id
```

## 13. 实施阶段

### 阶段一：最小可靠闭环

目标：

```text
能对普通文本 OpenRouter 请求做真实扣费复算。
```

范围：

- 新增价格快照表。
- 新增巡检运行表和明细表。
- 拉取 OpenRouter 价格快照。
- 扫描 OpenRouter 渠道消费日志。
- 覆盖普通文生文 input/output token。
- 覆盖 Gemini、Claude、OpenAI 的普通 text -> text 请求。
- 支持 `group_ratio`。
- 支持日志中已经完整记录的 `cache_tokens`。
- 输出 `actual_quota / expected_quota / delta / diff_rate`。
- 暂不支持场景标记 `unsupported`。

暂不做：

- 自动修复。
- 余额对账。
- 视觉输入 token 缺明细的请求。
- 文生图、图文生图。
- 工具调用。
- 复杂 tiered pricing。
- model_price 一口价模型。

验收标准：

```text
选取 100 条普通文本 OpenRouter 日志，巡检可给出稳定结果。
无价格快照、无模型映射、含复杂计费项的日志不会误判为 abnormal。
```

### 阶段二：提升准确性

目标：

```text
覆盖 OpenRouter 上常见复杂计费。
```

范围：

- 保存 `openrouter_cost` 到日志 `other`。
- 保存 `openrouter_model_id` 到日志 `other`。
- 保存 Gemini、Claude、OpenAI 的结构化 token 明细。
- 支持 cache read。
- 支持 cache creation。
- 支持 Claude 200K 分段。
- 支持 Gemini / OpenAI 文生图和图文生图的 image token 或按次费用。
- 支持 Claude / Gemini / OpenAI vision input token。
- 支持 OpenAI Responses web search / file search 等工具费用。
- 支持条件倍率从日志读取。
- 支持显式模型映射表。

验收标准：

```text
OpenRouter Claude、OpenAI、Google 文本模型的正常请求误报率低于 0.5%。
```

### 阶段三：运营化

目标：

```text
把巡检结果变成日常运营工具。
```

范围：

- 管理后台页面。
- 告警规则。
- 异常聚合。
- 手动回填。
- 导出 CSV。
- 按模型、渠道、用户维度聚合。

验收标准：

```text
管理员可以在 5 分钟内定位一次异常扣费的主要模型、渠道和原因。
```

### 阶段四：自动化建议

目标：

```text
提供修复建议，但不自动执行资金变更。
```

范围：

- 根据偏差生成建议配置。
- 提示应该调整 `model_ratio`、`completion_ratio`、`cache_ratio` 还是 `group_ratio`。
- 标记疑似 OpenRouter 改价导致的异常。

验收标准：

```text
异常项能生成明确的人类可审核建议。
```

## 14. 关键风险

### 14.1 当前价格检查历史日志

风险：

```text
OpenRouter 改价后，大量历史日志会被误判。
```

控制：

```text
必须保存价格快照，并按日志创建时间匹配历史快照。
```

### 14.2 模型映射错误

风险：

```text
不同 provider 或变体下的同名模型被串价。
```

控制：

```text
保存完整 OpenRouter model_id。
高价值模型配置显式映射。
模糊匹配结果标记低可信。
```

### 14.3 巡检公式和实际扣费公式漂移

风险：

```text
巡检器自己算错，导致误报。
```

控制：

```text
抽取同源 DryRunBillingCalculator。
将计费上下文结构化。
对计算器加单元测试。
```

### 14.4 复杂计费项误报

风险：

```text
image/audio/tool/tiered 请求被普通文本公式误判。
```

控制：

```text
第一阶段遇到复杂计费项直接 unsupported。
逐项补齐后再纳入异常判断。
```

### 14.5 日志缺少当时倍率

风险：

```text
使用当前 group_ratio 或条件倍率检查历史请求会误判。
```

控制：

```text
优先使用 logs.other 中保存的运行时倍率。
后续补齐日志字段。
```

## 15. 推荐代码组织

建议新增目录：

```text
service/openrouter_inspection/
```

内部文件：

```text
price_fetcher.go
price_snapshot.go
log_scanner.go
calculator.go
classifier.go
runner.go
alert.go
```

模型文件：

```text
model/openrouter_inspection.go
```

控制器：

```text
controller/openrouter_inspection.go
```

路由：

```text
router/openrouter_inspection.go
```

测试：

```text
service/openrouter_inspection/calculator_test.go
service/openrouter_inspection/classifier_test.go
```

## 16. 单元测试建议

必须覆盖：

```text
普通 input only
普通 input + output
cache read
cache creation
免费模型
缺价格
缺模型映射
四舍五入边界
低金额绝对误差阈值
group_ratio
cond_multiplier
```

典型用例：

```text
input_price = 2 USD/M
output_price = 10 USD/M
input_tokens = 1000
output_tokens = 100
group_ratio = 1

expected_usd = 1000 * 0.000002 + 100 * 0.00001 = 0.003
expected_quota = 0.003 * 500000 = 1500
```

## 17. 最终判断

该技术路线合理，并且适合当前系统。

但它成立的前提是：

```text
保存历史价格快照
按真实 logs.quota 对比
尽量使用同源扣费计算器
复杂计费项先标记 unsupported
不和 recon/余额/上游账单混用
```

如果只用当前 OpenRouter 价格简单乘日志 token，再和 `logs.quota` 比较，短期能发现明显错误，但长期会因为改价、模型映射、缓存、多模态、条件倍率等因素产生大量误报。

推荐按阶段实施，先建立普通文本模型的可靠闭环，再逐步覆盖缓存、Claude 分段、多模态和工具调用。
