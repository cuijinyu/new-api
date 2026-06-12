# Service Inference Seedance 2.0 接入方案

## 1. 背景

本文设计 new-api 接入 `service-inference.ai` 提供的 Seedance 2.0 视频生成能力的方案。输入材料来自 `sd2_real.md` 中的服务商接口示例，并参考 new-api 官方 `main` 分支中 `doubao-video` 对 Seedance 2.0 的最新适配方式。

目标是让 service-inference 的 Seedance 视频生成在 new-api 中具备：

- 独立渠道接入能力。
- 与现有 `/v1/video/generations` 异步任务体系兼容。
- 支持 text / image / audio reference 输入。
- 基于上游 `usage.total_tokens` 做最终核销。
- 能在 AWS S3 usage log 中留下可对账的最终计费记录。
- 避免把 raw video URL、鉴权头、base64 等敏感信息写入长期日志。

## 2. 参考事实

### 2.1 官方 new-api Seedance 2.0 适配

官方 new-api 最新 `doubao-video` 适配器已经支持以下模型：

```text
doubao-seedance-1-5-pro-251215
doubao-seedance-2-0-260128
doubao-seedance-2-0-fast-260128
```

官方 Doubao 适配仍走火山方舟任务接口：

```text
POST /api/v3/contents/generations/tasks
GET  /api/v3/contents/generations/tasks/{task_id}
```

请求 payload 已扩展到 Seedance 2.0 所需字段，包括：

```text
content
callback_url
return_last_frame
service_tier
generate_audio
resolution
ratio
duration
frames
seed
camera_fixed
watermark
```

`content` item 支持：

```text
text
image_url
video_url
audio_url
```

官方代码还通过 metadata 透传高级字段，但会删除 metadata 里的 `model`，避免用户绕过 model mapping 和计费。

### 2.2 官方计费口径

官方 Seedance 2.0 逻辑有两段：

1. 提交时预扣。
2. 任务成功后，如果上游返回 `usage.total_tokens`，按实际 token 核销。

最终核销公式：

```text
actual_quota = usage.total_tokens * model_ratio * group_ratio
```

官方还内置了 Seedance 2.0 视频输入折扣：

```text
doubao-seedance-2-0-260128      video_input_ratio = 28 / 46
doubao-seedance-2-0-fast-260128 video_input_ratio = 22 / 37
```

注意：官方成功核销路径只使用 `total_tokens * model_ratio * group_ratio`，没有再次乘 `video_input_ratio`。因此必须确认上游 `usage.total_tokens` 是不是已经按服务商价格口径折算后的 billing tokens。如果不是，最终核销会抹掉预扣阶段的视频输入折扣。

### 2.3 Service Inference 接口事实

根据 `sd2_real.md`，service-inference 的 API base URL 是：

```text
https://model.service-inference.ai
```

认证方式：

```http
Authorization: Bearer <api_key>
Content-Type: application/json
```

视频生成接口：

```text
POST /v1/video/generate
GET  /v1/video/tasks/{task_id}
GET  /v1/video/tasks
```

资产接口：

```text
POST /v1/asset-groups
POST /v1/assets
POST /v1/assets/get
```

示例模型名：

```text
dreamina-seedance-2-0-260128
dreamina-seedance-2-0-ep
dreamina-seedance-2-0-fast-260128
```

视频生成响应：

```json
{
  "task": {
    "id": "mvt-179197ccca01401a",
    "status": "pending",
    "model": "dreamina-seedance-2-0-260128",
    "duration_seconds": 4,
    "outputs": [],
    "error": null,
    "created_at": "2026-05-26T05:26:52.505Z",
    "completed_at": null
  }
}
```

任务完成响应：

```json
{
  "task": {
    "id": "mvt-179197ccca01401a",
    "status": "completed",
    "model": "dreamina-seedance-2-0-260128",
    "duration_seconds": 4,
    "outputs": ["https://example.com/video.mp4"],
    "error": null,
    "created_at": "2026-05-26T05:26:52.505Z",
    "completed_at": "2026-05-26T05:35:22.566Z",
    "usage": {
      "completion_tokens": 40594,
      "total_tokens": 40594
    }
  }
}
```

结论：service-inference 不是火山方舟 Ark 原生兼容接口，但返回结构完整，适合接入 new-api 的异步 task 体系。

## 3. 总体设计

推荐新增一个独立 task adaptor，而不是硬复用 `doubao-video`。

建议命名：

```text
relay/channel/task/serviceinference
```

或：

```text
relay/channel/task/inferencevideo
```

新增渠道类型建议：

```text
ChannelTypeServiceInferenceVideo
ChannelName = "service-inference-video"
```

默认 base URL：

```text
https://model.service-inference.ai
```

设计原因：

- service-inference submit/fetch 路径与方舟不同。
- 响应包裹层是 `task`，不是方舟的顶层 task object。
- 状态枚举是 `pending` / `processing` / `completed`，不是方舟的 `succeeded`。
- asset 上传是 service-inference 独有能力，后续可单独扩展。
- 单独渠道更容易在日志、价格、可用性、模型映射上对账。

## 4. 接口适配

### 4.1 Submit

new-api 对外仍保持现有视频生成入口：

```text
POST /v1/video/generations
```

adaptor 内部转发到：

```text
POST {base_url}/v1/video/generate
```

请求体建议直接构造 service-inference payload：

```json
{
  "model": "dreamina-seedance-2-0-260128",
  "content": [
    {
      "type": "text",
      "text": "prompt"
    },
    {
      "type": "image_url",
      "image_url": {
        "url": "asset://asset-id 或 https://..."
      },
      "role": "reference_image"
    },
    {
      "type": "audio_url",
      "audio_url": {
        "url": "https://example.com/audio.mp3"
      },
      "role": "reference_audio"
    }
  ],
  "duration": 4,
  "resolution": "480p",
  "ratio": "16:9",
  "generate_audio": true,
  "watermark": false
}
```

### 4.2 请求字段来源

基础字段来自 `relaycommon.TaskSubmitReq`：

```text
model
prompt
images
seconds / duration
metadata
```

建议规则：

- `req.Model` 映射后写入 `payload.model`。
- `req.Prompt` 追加为最后一个 `content` text item。
- `req.Images` 转成 `content[].type = image_url`。
- `metadata.content` 可透传，但需要过滤或覆盖其中的 text，避免 prompt 重复。
- `metadata.model` 必须删除，防止绕过 model mapping。
- `metadata.duration`、`metadata.resolution`、`metadata.ratio`、`metadata.generate_audio`、`metadata.watermark` 等写入 payload。
- 如果 `req.Seconds > 0`，优先写入 `duration`。

### 4.3 Response

submit 返回：

```json
{
  "task": {
    "id": "mvt-...",
    "status": "pending"
  }
}
```

`DoResponse` 应：

- 读取 `task.id` 作为上游 task id。
- 返回给客户端 new-api 统一格式。
- 将原始响应写入 `task.Data`。
- 在 task properties 中保留：
  - `OriginModelName`
  - `UpstreamModelName`
  - `TokenId`
  - `TokenName`
  - `RequestId`
  - `ClientIP`

### 4.4 Fetch

内部查询：

```text
GET {base_url}/v1/video/tasks/{task_id}
```

`ParseTaskResult` 映射规则：

| Service Inference status | new-api status |
|---|---|
| `pending` | `QUEUED` |
| `processing` | `IN_PROGRESS` |
| `completed` | `SUCCESS` |
| `failed` | `FAILURE` |
| `error != null` | `FAILURE` |

完成时：

- `Url = task.outputs[0]`
- `Duration = task.duration_seconds`
- `CompletionTokens = task.usage.completion_tokens`
- `TotalTokens = task.usage.total_tokens`
- `Reason = task.error.message` 或序列化后的 error。

## 5. 模型映射

建议对用户暴露稳定的本地模型名：

```text
seedance-2.0
doubao-seedance-2-0-260128
service-inference-seedance-2-0-260128
```

上游模型名使用：

```text
dreamina-seedance-2-0-260128
dreamina-seedance-2-0-ep
dreamina-seedance-2-0-fast-260128
```

推荐配置方式：

```text
用户请求模型: doubao-seedance-2-0-260128
渠道模型映射: doubao-seedance-2-0-260128 => dreamina-seedance-2-0-260128
用户请求模型: doubao-seedance-2-0-fast-260128
渠道模型映射: doubao-seedance-2-0-fast-260128 => dreamina-seedance-2-0-fast-260128
用户请求模型: service-inference-seedance-2-0-ep
渠道模型映射: service-inference-seedance-2-0-ep => dreamina-seedance-2-0-ep
计费模型名:   使用用户请求侧模型名，便于和其他 Seedance 渠道统一价格配置
上游模型名:   写入 logs.other.upstream_model_name
```

这样同一个业务模型可以在 Doubao 官方渠道和 service-inference 渠道之间切换，同时日志里仍能看出实际供应商。

## 6. 计费设计

### 6.1 主计费模式

service-inference 返回：

```json
"usage": {
  "completion_tokens": 40594,
  "total_tokens": 40594
}
```

因此主计费模式应采用 token 核销：

```text
actual_quota = total_tokens * model_ratio * final_group_ratio
```

其中：

```text
model_ratio = provider_price_per_1m_tokens * QuotaPerUnit / 1_000_000
```

如果系统当前 `QuotaPerUnit = 500000`，则：

```text
model_ratio = provider_price_usd_per_1m_tokens * 500000 / 1_000_000
```

如果价格来源是人民币，需要先按系统的汇率策略换成 USD 口径，或者明确将模型倍率配置成系统内部 quota/token 口径。

### 6.2 预扣

提交阶段需要预扣，避免用户无额度提交长任务。

推荐预扣策略：

1. 如果 model price 配了固定单次价格，按固定单次价格预扣。
2. 如果使用 token ratio，且请求里有 `duration` / `resolution`，可用经验 tokens 估算。
3. 如果估算不可靠，按保守上限预扣，任务成功后用 `usage.total_tokens` 多退少补。

最稳妥的第一阶段：

```text
preconsume_quota = configured_model_price * group_ratio * QuotaPerUnit
```

也就是先按“每次任务估算价”预扣，成功后再按 `usage.total_tokens` 核销。

### 6.3 最终核销

任务成功且 `usage.total_tokens > 0` 时：

```text
actual_quota = total_tokens * model_ratio * final_group_ratio
quota_delta = actual_quota - preconsumed_quota
```

处理规则：

- `quota_delta > 0`：补扣。
- `quota_delta < 0`：退款。
- `quota_delta == 0`：记录最终结算日志，但不改余额。

### 6.4 视频输入折扣

当前 service-inference 文档示例只出现：

```text
text
image_url
audio_url
```

没有出现 `video_url`。因此不应把官方 Seedance 2.0 的视频输入折扣套在 image/audio 输入上。

如果后续 service-inference 支持 `video_url`，再加入：

```text
video_input_ratio = 含视频输入单价 / 不含视频输入单价
```

并记录：

```json
{
  "video_input": true,
  "video_input_ratio": 0.6087
}
```

但仍需验证 service-inference 返回的 `usage.total_tokens` 是否已经内含折扣。如果 `total_tokens` 已是价格折算 token，最终核销不再乘折扣；如果不是，最终核销必须乘折扣。

### 6.5 价格配置建议

不要直接把火山价格写死为 service-inference 价格。service-inference 可能有自己的加价或包月折扣。

推荐配置项：

```json
{
  "dreamina-seedance-2-0-260128": "<按 service-inference 实际价格换算后的 model_ratio>",
  "dreamina-seedance-2-0-ep": "<按 service-inference 实际价格换算后的 model_ratio>",
  "dreamina-seedance-2-0-fast-260128": "<按 service-inference 实际价格换算后的 model_ratio>"
}
```

如果希望用户侧统一模型名，则配置：

```json
{
  "doubao-seedance-2-0-260128": "<按 service-inference 实际价格换算后的 model_ratio>",
  "doubao-seedance-2-0-fast-260128": "<按 service-inference 实际价格换算后的 model_ratio>",
  "service-inference-seedance-2-0-ep": "<按 service-inference 实际价格换算后的 model_ratio>"
}
```

上游模型名只用于 mapping，不直接决定价格。

## 7. AWS 日志设计

### 7.1 当前本地日志能力

本地仓库已有三条 S3 日志链路：

```text
service/usage_log_s3.go
service/raw_log_s3.go
service/billing_retry_s3.go
```

启用条件主要是：

```text
RAW_LOG_S3_ENABLED=true
RAW_LOG_S3_BUCKET=...
RAW_LOG_S3_REGION=...
RAW_LOG_S3_ACCESS_KEY_ID=...
RAW_LOG_S3_SECRET_ACCESS_KEY=...
USAGE_LOG_S3_ENABLED=true
BILLING_RETRY_S3_ENABLED=true
```

`main.go` 中会把 `model.ConsumeLogHook` 接到 `service.EnqueueUsageLog`。因此：

- `RecordConsumeLog` 会进入 usage S3。
- `RecordConsumeLogNoContext` 也会进入 usage S3。
- `RecordRefundLog` 也应进入 usage S3 hook，并在 payload 中通过 `type = LogTypeRefund` 与普通消费日志区分。

### 7.2 Seedance 最终结算日志

异步视频任务的关键不是只记录提交时预扣，而是要记录最终 settlement。

建议新增统一的 video task settlement log helper：

```text
RecordVideoTaskSettlementLog(...)
```

成功完成时无论 `quota_delta` 是否为 0，都写一条结算日志：

```json
{
  "provider": "service-inference",
  "billing_event": "video_task_settlement",
  "task_id": "mvt-179197ccca01401a",
  "upstream_task_id": "mvt-179197ccca01401a",
  "model_name": "doubao-seedance-2-0-260128",
  "upstream_model_name": "dreamina-seedance-2-0-260128",
  "duration_seconds": 4,
  "resolution": "480p",
  "ratio": "16:9",
  "generate_audio": true,
  "watermark": false,
  "outputs_count": 1,
  "total_tokens": 40594,
  "completion_tokens": 40594,
  "model_ratio": 0.0,
  "group_ratio": 1.0,
  "preconsumed_quota": 0,
  "actual_quota": 0,
  "quota_delta": 0,
  "request_id": "...",
  "channel_id": 0
}
```

敏感字段处理：

- 不写完整 `outputs[0]` 视频 URL。
- 不写完整请求鉴权头。
- 不写完整 asset 原始 URL，除非确认没有敏感 query string。
- raw log 中如必须保存 response body，应对 `outputs` 做脱敏或只保留域名/hash。

### 7.3 补扣和退款

现有 video task 补扣/退款路径直接调用：

```text
model.DecreaseUserQuota
model.IncreaseUserQuota
model.UpdateUserUsedQuota
model.UpdateChannelUsedQuota
```

这绕过了 `PostConsumeQuota`，因此 billing retry S3 对异步最终核销没有兜底。

建议改造：

- 补扣使用统一扣费 helper，失败时写入 `billing_retry_s3`。
- 退款也需要对应 retry 机制，或者至少写一条 settlement failure log。
- `quota_delta == 0` 时不改余额，但仍写 settlement usage log，方便 AWS 对账知道这个任务已核销。

### 7.4 日志与 DB 的关系

DB 日志用于后台查询，S3 usage log 用于离线对账和 Athena 分析。两边字段应保持同一套核心字段：

```text
request_id
task_id
channel_id
model_name
upstream_model_name
quota
actual_quota
quota_delta
total_tokens
completion_tokens
group_ratio
model_ratio
provider
billing_event
```

`logs.quota` 对于结算日志建议记录本次 delta；`other.actual_quota` 记录任务最终应扣总额；`other.preconsumed_quota` 记录提交时预扣额。

## 8. 资产接口设计

service-inference 支持资产组和资产上传：

```text
POST /v1/asset-groups
POST /v1/assets
POST /v1/assets/get
```

第一阶段不建议把 asset 管理强行塞进视频生成主流程。建议分两阶段：

### 第一阶段

只支持：

```text
image_url.url = https://...
image_url.url = asset://...
audio_url.url = https://...
```

调用方自行创建 asset，或者直接传公网 URL。

### 第二阶段

新增 asset helper：

```text
CreateAssetGroup
CreateAsset
GetAsset
WaitAssetReady
```

可选能力：

- 当用户传入普通图片 URL 时，自动上传为 asset。
- 将 `asset_id` 写入 task metadata。
- asset 失败时在 task failure reason 中返回明确错误。

注意：文档说明“可以不等素材完成也能生成视频”，所以自动等待 asset ready 不是必需项，应做成配置开关。

## 9. 代码改造点

### 9.1 新增 adaptor

新增目录：

```text
relay/channel/task/serviceinference
```

建议文件：

```text
adaptor.go
constants.go
types.go
```

核心类型：

```go
type TaskAdaptor struct {
    taskcommon.BaseBilling
    ChannelType int
    apiKey      string
    baseURL     string
}
```

核心方法：

```text
Init
ValidateRequestAndSetAction
BuildRequestURL
BuildRequestHeader
BuildRequestBody
DoRequest
DoResponse
FetchTask
ParseTaskResult
GetModelList
GetChannelName
EstimateBilling
```

### 9.2 注册渠道

需要增加或修改：

```text
constant/channel.go
relay/channel/adapter.go
relay/task adaptor 注册表
前端渠道类型列表
```

默认 base URL：

```text
https://model.service-inference.ai
```

### 9.3 task final settlement

建议改造：

```text
controller/task_video.go
```

目标：

- 读取 `taskResult.TotalTokens`。
- 使用 `task.Properties.OriginModelName` 作为计费模型名。
- 使用 `task.Properties.UpstreamModelName` 作为日志字段。
- 补扣/退款支持失败重试。
- `quota_delta == 0` 也记录 final settlement。
- usage S3 中记录完整 billing context。

### 9.4 raw log 脱敏

建议在 raw log 记录 response body 前，对 service-inference 视频响应做脱敏：

```text
task.outputs => ["<redacted>", "..."]
```

或：

```text
outputs_count = len(outputs)
first_output_sha256 = sha256(outputs[0])
```

## 10. 验证计划

### 10.1 单元测试

新增测试覆盖：

- request payload 构造：
  - prompt 追加为 text。
  - images 转 image_url。
  - metadata content 透传。
  - metadata.model 被删除。
  - duration / resolution / ratio / generate_audio / watermark 正确透传。
- submit response 解析：
  - `task.id` 为空时报错。
  - `task.id` 正常返回。
- fetch response 解析：
  - `pending` -> queued。
  - `processing` -> in progress。
  - `completed` -> success。
  - `failed` / `error` -> failure。
  - usage tokens 正确进入 `TaskInfo`。

### 10.2 集成测试

使用真实 service-inference key 跑以下任务：

1. 文生视频，4s，480p。
2. 图片参考视频，`image_url` 为公网 URL。
3. 图片参考视频，`image_url` 为 `asset://...`。
4. 带 `audio_url` 且 `generate_audio=true`。

每单校验：

```text
task submit 成功
task fetch 最终 success
outputs_count > 0
usage.total_tokens > 0
DB task.Quota = actual_quota
usage S3 有 settlement log
raw S3 不包含完整 Authorization / outputs URL
```

### 10.3 价格验证

至少跑 3 单，对比 service-inference 控制台账单：

```text
expected_cost = usage.total_tokens / 1_000_000 * provider_price_per_1m_tokens
system_cost   = actual_quota / QuotaPerUnit
```

如果两者稳定一致，说明 `usage.total_tokens` 可作为 billing token 使用。

如果不一致，需要判断差异来自：

- service-inference 的单价不是火山原价。
- `usage.total_tokens` 不是 billing token。
- resolution / duration / audio 另有加价。
- group ratio 或系统汇率配置导致差异。

## 11. 风险点

### 11.1 价格风险

service-inference 文档只给了 usage，没有给价格。不能假设它和火山方舟价格完全一致。

处理方式：

- 以 service-inference 控制台价格为准配置 model ratio。
- 通过真实任务账单反推确认。
- 文档和日志里记录 provider price version。

### 11.2 usage 口径风险

如果 `usage.total_tokens` 已经是价格折算 tokens，直接乘 model ratio 即可。

如果它只是生成 token 数，且不同 resolution / audio / video input 有不同价格，则需要额外乘动态倍率。

处理方式：

- 第一阶段上线前必须用至少 3 单不同参数任务做账单校验。
- 结算日志记录 resolution / duration / generate_audio，方便后续反推。

### 11.3 异步补扣失败

异步任务完成时已经离开用户请求上下文，如果补扣失败，容易形成少扣。

处理方式：

- 补扣失败写入 billing retry S3。
- 后台 worker 定期重试。
- settlement log 中记录 `settlement_status`。

### 11.4 日志敏感信息

视频输出 URL 可能带签名 query，长期存 S3 有泄漏风险。

处理方式：

- usage log 只记录 outputs count/hash。
- raw log 对 outputs 脱敏。
- asset URL 如含 query，也按相同规则处理。

## 12. 推荐实施顺序

1. 新增 service-inference task adaptor。
2. 注册渠道类型和默认 base URL。
3. 支持 model mapping 到 `dreamina-seedance-2-0-260128`。
4. 完成 submit/fetch/status/usage 解析。
5. 接入 token final settlement。
6. 增加 settlement usage log。
7. 增加 billing retry 对异步补扣的兜底。
8. 增加 raw log outputs 脱敏。
9. 用真实 key 跑 3 到 4 单价格校验。
10. 根据账单结果决定是否需要 resolution/audio/video_input 动态倍率。

## 13. 第一阶段验收标准

第一阶段完成后，应满足：

- 可以通过 new-api `/v1/video/generations` 提交 service-inference Seedance 2.0 任务。
- 可以通过现有 video task fetch 接口查询结果。
- 完成任务能返回视频 URL。
- `usage.total_tokens` 被写入 task result。
- 成功任务按 `total_tokens * model_ratio * group_ratio` 核销。
- 补扣、退款、零差额都能在 AWS usage log 中形成最终 settlement 记录。
- raw log 不包含完整鉴权信息和完整视频输出 URL。
- 至少 3 单真实任务与 service-inference 控制台账单误差在可解释范围内。

## 14. Implementation Update: Service Inference Real Pricing

This section supersedes earlier placeholders about unknown Service Inference pricing.

### 14.1 Confirmed Provider Prices

Prices are configured as USD per 1M provider billing tokens.

| Model | Tier | Price |
| --- | --- | --- |
| `dreamina-seedance-2-0-260128` | `480p_no_ref` | `$7.00 / 1M tok` |
| `dreamina-seedance-2-0-260128` | `480p_with_ref` | `$4.30 / 1M tok` |
| `dreamina-seedance-2-0-260128` | `720p_no_ref` | `$7.00 / 1M tok` |
| `dreamina-seedance-2-0-260128` | `720p_with_ref` | `$4.30 / 1M tok` |
| `dreamina-seedance-2-0-260128` | `1080p_no_ref` | `$7.70 / 1M tok` |
| `dreamina-seedance-2-0-260128` | `1080p_with_ref` | `$4.70 / 1M tok` |
| `dreamina-seedance-2-0-ep` | same as normal | `$7.00 / $4.30 / $7.70 / $4.70` |
| `dreamina-seedance-2-0-fast-260128` | `480p_no_ref` | `$5.60 / 1M tok` |
| `dreamina-seedance-2-0-fast-260128` | `480p_with_ref` | `$3.30 / 1M tok` |
| `dreamina-seedance-2-0-fast-260128` | `720p_no_ref` | `$5.60 / 1M tok` |
| `dreamina-seedance-2-0-fast-260128` | `720p_with_ref` | `$3.30 / 1M tok` |

`fast` 1080p is not configured because no provider price was supplied. Requests for that combination should be blocked or priced only after the provider price is confirmed.

### 14.2 Billing Formula Implemented

The channel uses `ModelPrice` as the base USD-per-1M-token price:

```text
normal / ep base ModelPrice = 7.00
fast base ModelPrice        = 5.60
```

The adaptor applies a dynamic scale:

```text
unit_scale = selected_tier_price / base_model_price / 1_000_000
actual_quota = ModelPrice * usage.total_tokens * unit_scale * group_ratio * QuotaPerUnit
```

This is equivalent to:

```text
actual_usd = usage.total_tokens / 1_000_000 * selected_tier_price
actual_quota = actual_usd * group_ratio * QuotaPerUnit
```

For pre-consumption, the adaptor estimates billing tokens from requested duration and resolution, then uses the same selected-tier price scale. Final settlement still uses provider-returned `usage.total_tokens`.

### 14.3 Persisted Channel

The local DB channel is configured as:

```text
type: 57
name: Service Inference Seedance 2.0
base_url: https://model.service-inference.ai
group: default
models:
  dreamina-seedance-2-0-260128
  dreamina-seedance-2-0-ep
  dreamina-seedance-2-0-fast-260128
  doubao-seedance-2-0-260128
  doubao-seedance-2-0-fast-260128
  service-inference-seedance-2-0-260128
  service-inference-seedance-2-0-ep
  service-inference-seedance-2-0-fast-260128
```

The API key is stored only in the channel `key` field and must not be copied into docs, logs, or source files.
