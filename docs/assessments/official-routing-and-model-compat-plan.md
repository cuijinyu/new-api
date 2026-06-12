# 官方路由调度与模型兼容改造调研计划

> 类型：调研与落地计划，不包含业务代码改动。
> 日期：2026-06-09
> 范围：对比官方 `official/main` 近阶段在路由调度、渠道选择、Claude/Gemini/OpenAI 兼容处理上的改造，评估对当前分支的借鉴价值，并补充实施前后验证项。

---

## 1. 结论先行

官方近期没有重写“优先级 + 权重随机”的核心选路算法，主要改造集中在两类：

1. **路由调度稳定性增强**
   - Channel Affinity 粘性路由边界修正。
   - `auto` 分组跨组重试。
   - 多 Key 自动禁用后的缓存驱逐。
   - 大请求体读取稳定性。
   - 任务查询接口模型回填。

2. **模型兼容层增强**
   - OpenAI o/GPT-5/Responses 语义适配。
   - Claude thinking/cache/tool/usage 边界修正。
   - Gemini thinking/tool/usage/native stream 兼容。

当前分支已有不少自研增强，例如 Claude thinking block 清洗、Gemini `contents` 单对象自动包数组、Channel Affinity poison rewrite。因此不建议直接合并官方主干，应按能力点手工移植，并保留现有定制行为。

建议优先级：

| 优先级 | 候选改动 | 原因 |
|---|---|---|
| P0 | OpenAI o 系判断收窄 | 当前 `strings.HasPrefix(model, "o")` 容易误伤非 OpenAI o 系模型 |
| P0 | 多 Key 自动禁用缓存驱逐 | 防止已禁用 key/channel 继续被调度 |
| P0 | Gemini usage/tool 字段映射 | 直接影响计费、对账和工具调用稳定性 |
| P1 | Channel Affinity `include_model_name` + 禁用后清理缓存 | 降低跨模型误粘和 stale cache |
| P1 | Claude 流式 usage/cache 修正 | 避免 cache creation 5m/1h 或 final usage 丢失 |
| P1 | BodyStorage 请求体读取 | 大 base64、多模态请求更稳 |
| P2 | `auto` 分组跨组重试 | 改善 fallback 覆盖面，但需要联动 retry 流程 |
| P2 | Chat Completions -> Responses 兼容层、Responses compact | 价值高，但改动面大，适合作为专项 |

---

## 2. 调研来源

本次基于本地远端引用 `official/main` 与当前分支对比，并抽取官方相关提交：

| 方向 | 代表提交 |
|---|---|
| Channel Affinity 首次引入 | `d9321b7da` feat: channel affinity |
| Affinity 按模型隔离 | `70560d537` feat: add IncludeModelName option |
| Affinity 禁用渠道缓存策略 | `4a188deea` feat: 支持配置渠道被禁用后是否清空渠道粘性 |
| request header 作为 affinity key | `68830e609` feat: support request_header key source |
| 多 Key 自动禁用缓存驱逐 | `ebbe31553` fix(channel): evict auto-disabled multi-key channels from cache |
| 任务查询模型回填 | `87cc22d7e` fix(distributor): resolve model for GET video task |
| BodyStorage / 磁盘 body cache | `d7c55b92b`, `29d48e262` |
| OpenAI o 系判断收窄 | `01c2128e2` fix: 收窄 OpenAI o 系模型适配范围 |
| Responses compact | `cf114ca7d` feat: openai response compact |
| Claude cache/speed passthrough | `f7adf02eb` feat(claude): add cache_control and speed passthrough controls |
| Claude 流式 usage 修正 | `82c2008d2`, `f7cdc727d` |
| Gemini stream/tool/usage 修正 | `23fde25b1`, `45cc95a25`, `c97f4524f`, `465c5edab` |

---

## 3. 路由调度改造计划

### 3.1 Channel Affinity 按模型隔离

官方改动：

- `ChannelAffinityRule` 新增 `include_model_name`。
- cache key 从 `rule/group/value` 扩展为可选 `rule/model/group/value`。
- cache stats 解析同步识别 model 维度。

当前差距：

- 当前 `service/channel_affinity.go` 的 key 只包含 rule、group、affinity value。
- 跨模型复用同一个 prompt/session key 时，可能先命中旧模型绑定的渠道，再 fallback。

建议：

- 引入 `IncludeModelName bool`，默认 `false`，避免破坏已有缓存键。
- Codex/Claude/Gemini 缓存敏感规则可开启。
- 保留当前 poison rewrite，不用官方版本覆盖。

验证项：

- 单元测试：同一 affinity value、不同 model，在 `include_model_name=true` 时生成不同 cache key。
- 单元测试：`include_model_name=false` 时 cache key 与旧行为兼容。
- 集成测试：同一用户先请求 `claude-*`，再请求 `gpt-*`，不应因旧 cache 绑定到不支持模型的渠道。
- 回归测试：cache stats 的 `unknown` 数量不会因新 key 结构误增。

### 3.2 渠道禁用后的 Affinity 缓存处理

官方改动：

- 新增 `keep_on_channel_disabled`。
- 粘性命中的 preferred channel 不可用时，可清除当前 affinity cache。
- 修复 preferred channel 已禁用但仍保留 skip retry 状态的问题。

当前差距：

- 当前命中 disabled/stale preferred channel 后会 fallback，但 cache 未必清理，后续请求会重复命中坏缓存。

建议：

- 增加 `ClearCurrentChannelAffinityCache`。
- 默认当 preferred channel 不可用时清理当前 cache。
- 提供配置开关保留旧行为，适合需要手动恢复粘性的场景。

验证项：

- 单元测试：preferred channel 禁用后，默认删除当前 affinity cache。
- 单元测试：`keep_on_channel_disabled=true` 时不删除 cache。
- 集成测试：请求 A 命中 channel 1，禁用 channel 1 后请求 B fallback 到 channel 2，请求 C 不再重复读取 channel 1 的 stale cache。
- 日志验证：admin info 能标记 affinity miss/fallback 原因，方便排障。

### 3.3 request_header 作为 Affinity key source

官方改动：

- `ChannelAffinityKeySource.Type` 支持 `request_header`。
- 从 `c.Request.Header.Get(src.Key)` 提取 affinity value。

当前差距：

- 当前只支持 `context_int`、`context_string`、`gjson`。

建议：

- 手工补 `request_header`，用于客户端 session、tenant、custom user id 等场景。
- 默认不内置 header 规则，由管理员显式配置。

验证项：

- 单元测试：指定 header 存在时能生成 affinity key。
- 单元测试：header 缺失时跳过该 key source，继续尝试后续 source。
- 安全验证：敏感 header 只记录 fingerprint/hint，不记录完整值。

### 3.4 `auto` 分组跨组重试

官方改动：

- `CacheGetRandomSatisfiedChannel` 改为 `RetryParam`。
- `auto` 分组中，一个组内优先级耗尽后再切到下一个组。
- 通过 context 记录当前 auto group index 和 retry state。

当前差距：

- 当前函数签名为 `CacheGetRandomSatisfiedChannel(c, group, modelName, retry)`。
- 对所有 auto groups 使用同一个 retry 值，可能跳过某些组内可用低优先级渠道。

建议：

- 暂不直接合入，先补测试刻画当前行为。
- 若业务需要跨组兜底，再引入 `RetryParam`，并联动 `controller/relay.go` 的重试计数递增逻辑。

验证项：

- 单元测试：auto groups = A/B，A 有 priority 0/1，B 有 priority 0/1，重试顺序应为 A0 -> A1 -> B0 -> B1。
- 单元测试：未开启跨组重试时保持旧行为。
- 集成测试：某组模型无可用渠道时可切下一组。
- 回归测试：普通非 auto 分组调度结果不变。

### 3.5 多 Key 自动禁用缓存驱逐

官方改动：

- 多 Key 渠道中某 key 自动禁用后，驱逐/更新 channel cache，避免继续选到已禁用 key。

当前风险：

- 当前存在多 Key、轮询、自动禁用、自建 cache 叠加，容易出现内存状态与 DB 状态短暂不一致。

建议：

- 对照官方 `ebbe31553` 检查当前 `Channel` key 禁用、`CacheUpdateChannel`、`GetNextEnabledKey`。
- 优先作为 P0 correctness fix。

验证项：

- 单元测试：multi-key channel 中 key A 自动禁用后，下一次 `GetNextEnabledKey` 不返回 key A。
- 并发测试：多个请求同时触发 key 禁用，不产生 data race 或 polling index 越界。
- 集成测试：禁用最后一个可用 key 时，渠道应不可选并返回明确错误。
- 回归测试：普通单 key 渠道不受影响。

### 3.6 BodyStorage / 磁盘请求体缓存

官方改动：

- 大请求体可落磁盘缓存。
- distributor、affinity、handler 统一从 BodyStorage 读取，避免重复读 body 与大 base64 常驻内存。

当前状态：

- 当前分支已有 `common/body_storage.go` 等自研文件，但部分链路仍直接使用 `common.GetRequestBody(c)` 或重复 unmarshal。

建议：

- 先做读取路径梳理，不直接替换所有 handler。
- 优先替换 distributor model 读取、affinity gjson key、param override audit 这类高频重复读路径。

验证项：

- 单元测试：BodyStorage 多次读取后 body 可 rewind，后续 handler 仍能正常转发。
- 大请求测试：10MB/50MB base64 请求不会导致明显内存飙升。
- 兼容测试：`application/json`、`multipart/form-data`、`application/x-www-form-urlencoded` 均能读取 model。
- 回归测试：请求 body 不被截断、不被重复消费。

### 3.7 任务查询接口模型回填

官方改动：

- `GET /v1/video/generations/:task_id` 和 `/v1/videos/:task_id` 从任务记录回填 `OriginModelName`，避免 token model limit 误判。

建议：

- 低风险吸收。

验证项：

- 集成测试：token 限制只允许任务原始模型，GET task 成功。
- 负例测试：token 不允许任务原始模型，GET task 被拒绝。
- 兼容测试：task_id 缺失或查不到任务时，不影响无需模型限制的请求。

---

## 4. Claude 兼容改造计划

### 4.1 cache_control / context_management / speed / service_tier / inference_geo 透传控制

官方改动：

- Claude 请求 DTO 增加新字段。
- `RemoveDisabledFields` 默认过滤敏感或高风险字段，通过 channel setting 显式允许。

当前状态：

- 当前已有 `context_management`、`output_config`、`service_tier` 等字段，但字段类型和过滤策略与官方不完全一致。

建议：

- 不全量覆盖 DTO，优先引入缺失字段和过滤开关。
- `service_tier`、`speed` 这类可能改变成本/SLA 的字段必须默认过滤或审计。

验证项：

- 单元测试：默认过滤 `speed/service_tier/inference_geo`。
- 单元测试：开启 allow flag 后字段保留。
- 集成测试：Claude 请求带 `cache_control.scope`、`context_management` 时按配置过滤或透传。
- 对账验证：开启 `service_tier/speed` 后日志 `other` 记录足够字段，能解释成本变化。

### 4.2 thinking 与 Opus 4.7/4.8 适配

官方改动：

- Opus 4.7/4.8 的 `-thinking` 不再简单使用 `thinking.type=enabled`，而是使用 `output_config.effort`。
- extended thinking 时将 `top_p` 置空。
- 新增/调整 Claude 4.x 模型别名。

当前状态：

- 当前已有 Claude thinking block 清洗逻辑，应保留。
- 当前 `TopP` 仍是 `float64`，官方已转为 pointer，以区分未传与显式 0。

建议：

- 先吸收 `top_p` 置空和 Opus 4.7/4.8 effort 逻辑。
- 模型别名更新要与计费表同步，不单独只加 model list。

验证项：

- 单元测试：`claude-opus-4-7-thinking` 转换后使用 `output_config.effort=high`，不发送 `thinking.type=enabled`。
- 单元测试：thinking 请求不发送 `top_p`。
- 回归测试：现有 `SanitizeThinkingBlocks` 与跨渠道 retry 的 `StripAllThinkingBlocks` 行为不变。
- 真实上游 smoke：Claude thinking 请求不返回 invalid top_p / unsupported thinking type。

### 4.3 Claude 流式 usage/cache 修正

官方改动：

- `message_delta` usage-only final chunk 也能输出。
- 流式断流时不整份覆盖 usage，保留 cache 字段。
- 处理 cache creation 5m/1h split。

建议：

- 优先吸收 usage merge/patch 逻辑，不改现有计费主链路。

验证项：

- 单元测试：`message_start` 有 input/cache，`message_delta` 只有 output 时，最终 usage 合并完整。
- 单元测试：`cache_creation.ephemeral_5m_input_tokens` 和 `ephemeral_1h_input_tokens` 不丢失。
- 流式测试：usage-only final chunk 能被转发给客户端。
- 计费回归：Claude cache read/write 费用与 `service/quota.go` 结算一致。

### 4.4 tool_use 与并发工具调用

官方改动：

- 修复并发工具调用 index 碰撞。
- `input_json_delta` 空参数默认 `{}`。
- malformed tool arguments 时保留 `tool_use`，避免 tool_result 配对失败。

建议：

- 与当前自研 Claude/Gemini tool 逻辑逐个 case 对照，不直接覆盖。

验证项：

- 单元测试：两个并发 tool_call 不共享 id/index。
- 单元测试：空 `input_json_delta` 最终 arguments 为 `{}`。
- 集成测试：assistant tool_use 后 user tool_result 能正确配对。

---

## 5. Gemini 兼容改造计划

### 5.1 Native stream 识别

官方改动：

- Gemini native API 通过 URL `:streamGenerateContent` 判断流式，而不只看 `alt=sse`。

建议：

- 低风险吸收。

验证项：

- 单元测试：`/models/{model}:streamGenerateContent` 返回 `IsStream=true`。
- 单元测试：普通 `generateContent` 不误判。
- 集成测试：native stream 能走 SSE handler，并正确累计 usage。

### 5.2 ToolConfig 与 server-side tool invocation

官方改动：

- `ToolConfig` 增加 `includeServerSideToolInvocations`。

建议：

- 直接补 DTO 字段。

验证项：

- 单元测试：请求体包含该字段时不会被 unmarshal 丢弃。
- 转发测试：字段能透传到 Gemini native upstream。

### 5.3 usage 映射修正

官方改动：

- `promptTokens = promptTokenCount + toolUsePromptTokenCount`。
- `completionTokens = candidatesTokenCount + thoughtsTokenCount`。
- `reasoningTokens = thoughtsTokenCount`。
- `cachedTokens = cachedContentTokenCount`。

当前风险：

- 若不计入 toolUse/thought/cache token，会导致 Gemini 工具调用、thinking、cachedContent 场景低估成本。

建议：

- 作为 P0 计费正确性补丁吸收。

验证项：

- 单元测试：给定 Gemini `UsageMetadata`，映射后的 prompt/completion/total/reasoning/cached tokens 正确。
- 对账测试：含 tool use、thinking、cachedContent 的样本日志与供应商账单方向一致。
- 回归测试：无 usage metadata 时仍使用估算 fallback。

### 5.4 thinking config 与 snake_case/camelCase 兼容

官方改动：

- `generationConfig` 支持 `top_p/topP`、`max_output_tokens/maxOutputTokens`、`thinking_config/thinkingConfig` 等双命名。
- `ThinkingLevel` 改为 string。

当前状态：

- 当前已有 `contents` 单对象自动包数组，这是官方版本不完全覆盖的自研兼容。

建议：

- 合并时保留当前 `contents` 单对象兼容，同时补官方 snake_case/camelCase 双命名。

验证项：

- 单元测试：camelCase 与 snake_case 生成相同内部结构。
- 单元测试：`contents` 传单对象仍自动包为数组。
- 单元测试：`thinking_budget`、`thinking_level` 类型错误时返回明确错误。

### 5.5 Gemini -> Claude tool_use 修正

官方改动：

- 修复 Gemini 转 Claude 时 `tool_use` 结构错误。
- 对 thoughtSignature 做兼容注入。

建议：

- 作为 tool calling 专项验证，避免影响普通文本/多模态转换。

验证项：

- 单元测试：Gemini functionCall 转 Claude tool_use 字段完整。
- 单元测试：Gemini functionResponse 转 Claude tool_result 能配对。
- 集成测试：包含图片 + tool call 的多轮请求能完成。

---

## 6. OpenAI / Responses 兼容改造计划

### 6.1 o 系与 GPT-5 developer role 判断

官方改动：

- 新增 `IsOpenAIReasoningOModel`，只匹配 `o1/o3/o4`。
- `gpt-5` 仍使用 developer role。

当前差距：

- 当前 `GetSystemRoleName` 对所有 `o*` 模型返回 developer，可能误伤 `openrouter/*` 或其他供应商模型名。

建议：

- P0 吸收，风险低。

验证项：

- 单元测试：`o1/o3/o4` 返回 `developer`。
- 单元测试：`gpt-5*` 返回 `developer`。
- 单元测试：`omni-*`、`openrouter-*`、`ollama-*` 返回 `system`。
- 回归测试：`o1-mini`、`o1-preview` 保持官方例外逻辑。

### 6.2 pointer / RawMessage 字段语义

官方改动：

- 将 `stream/max_tokens/top_p/top_k/n/logprobs/dimensions/seed` 等从值类型改为 pointer。
- 将 provider-specific 或动态字段改为 `json.RawMessage`。

价值：

- 保留显式 `0`、`false`、`null`。
- 避免因 Go 零值导致字段被错误省略或错误发送。

建议：

- 不建议一次性全量改 DTO，影响面大。
- 优先改高风险字段：`stream`、`top_p`、`max_tokens`、`max_completion_tokens`、`n`。

验证项：

- 单元测试：显式 `stream:false` round-trip 后仍存在或按策略正确省略。
- 单元测试：未传 `top_p` 与传 `top_p:0` 能区分。
- 转发测试：provider 不支持的字段仍能被 `RemoveDisabledFields` 清理。

### 6.3 Chat Completions -> Responses 兼容层

官方改动：

- 新增 `service/openaicompat`。
- 支持 system/developer -> instructions。
- 支持 tool/function output、assistant function_call、image_url、response_format json_schema。
- 可按 channel/model policy 决定是否启用。

价值：

- 对 GPT-5、Codex、Responses-only 上游有明显价值。

风险：

- 改动面大，涉及请求转换、响应转换、工具调用、计费、日志。

建议：

- 作为专项引入，默认关闭，仅白名单 channel/model 开启。

验证项：

- 单元测试：纯文本 chat 请求转换为 responses input。
- 单元测试：system/developer 合并为 instructions。
- 单元测试：tool_call/tool output 能完整转换。
- 单元测试：`response_format.json_schema` 转为 Responses text format。
- E2E：同一 prompt 在 Chat Completions 与 Responses 兼容模式下输出结构一致。
- 计费验证：usage 映射到内部 prompt/completion/reasoning/cache 字段正确。

### 6.4 Responses compact

官方改动：

- 新增 `/v1/responses/compact` 路由、DTO 和 handler。
- compact response usage 映射回内部 Usage。

建议：

- 如果 Codex 客户端或内部压缩上下文需求明确，则引入。
- 需要同步模型列表、计费模型后缀、endpoint defaults。

验证项：

- 路由测试：`/v1/responses/compact` 能正确进入 compact relay mode。
- handler 测试：compact response usage 映射正确。
- Azure 测试：Azure Responses compact URL 拼接正确。
- 计费测试：compact 模型后缀计费与普通 responses 分离或按预期复用。

---

## 7. 横向验证矩阵

| 场景 | 必测内容 |
|---|---|
| 渠道选择 | priority/weight 选择未被改动；auto 分组重试符合预期 |
| 粘性路由 | cache key、命中、清理、禁用 fallback、日志 admin info |
| 多 Key | polling index、自动禁用、无可用 key 错误、并发安全 |
| 大请求体 | body 可重复读取；multipart/json/form 均正常；内存占用可接受 |
| Claude | thinking、cache_control、message_delta usage、tool_use、web_search 计费 |
| Gemini | native stream、thinking config、tool use、cachedContent、usage metadata |
| OpenAI | o/GPT-5 developer role、Responses conversion、compact、json_schema |
| 计费 | prompt/completion/cache/reasoning/tool tokens 不少算、不重复算 |
| 日志/对账 | `other` 中能解释 service_tier、speed、reasoning、cache split 等成本来源 |

---

## 8. 推荐实施顺序

### 阶段一：低风险 correctness fix

1. OpenAI o 系判断收窄。
2. Gemini usage metadata 映射修正。
3. 多 Key 自动禁用缓存驱逐。
4. Gemini `streamGenerateContent` 识别。
5. Channel Affinity disabled channel cache 清理。

阶段验收：

- 相关单元测试全部通过。
- 现有 chat/completions、Claude、Gemini smoke 不回退。
- 计费字段与原有日志格式兼容。

### 阶段二：兼容表达力增强

1. Channel Affinity `include_model_name`。
2. request_header affinity source。
3. Claude 流式 usage/cache patch。
4. Claude/Gemini 缺失字段补齐与过滤开关。
5. BodyStorage 高频读取链路收敛。

阶段验收：

- 粘性路由缓存命中率与 stale cache 发生率可观测。
- Claude cache creation 5m/1h 日志字段稳定。
- 大请求体压测无明显内存异常。

### 阶段三：专项能力

1. `auto` 分组跨组重试。
2. Chat Completions -> Responses 兼容层。
3. `/v1/responses/compact`。

阶段验收：

- 默认关闭或白名单开启。
- 每项均有 E2E 与计费回归。
- 有回滚开关。

---

## 9. 风险与注意事项

1. **不能直接覆盖官方文件**
   当前分支有自研增强且与官方主干历史不线性，直接 merge 风险高。

2. **DTO 值类型改 pointer 会产生广泛影响**
   需要检查所有读写字段的位置，特别是 `GetMaxTokens`、`IsStream`、计费估算、转换器。

3. **兼容字段可能改变实际成本**
   `service_tier`、`speed`、`thinking`、`reasoning`、`web_search`、`tool_use` 都可能影响上游费用，必须有日志快照。

4. **Responses 兼容层不是简单转发**
   涉及请求结构、工具调用、响应格式、usage、计费、日志，不应混在小补丁里做。

5. **保留当前自研能力**
   - Claude thinking block 清洗。
   - Channel Affinity poison rewrite。
   - Gemini `contents` 单对象兼容。
   - 已有计费与对账字段语义。

---

## 10. 待办清单

| 状态 | 事项 | 负责人建议 |
|---|---|---|
| 待办 | 为 OpenAI o 系判断补单元测试并改实现 | 后端 |
| 待办 | 梳理 Gemini usage metadata 样本并补测试 | 后端 + 对账 |
| 待办 | 对照官方 multi-key cache eviction 设计当前修复 | 后端 |
| 待办 | 设计 Affinity `include_model_name` 配置迁移与默认值 | 后端 |
| 待办 | 梳理 Claude stream usage 样本，确认 cache split 语义 | 后端 + 对账 |
| 待办 | 统计当前 BodyStorage 覆盖点与直接读 body 点 | 后端 |
| 待办 | 决定是否需要 Responses compatibility 专项 | 产品/后端 |
