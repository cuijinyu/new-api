# Seedance 2.0 — BytePlus / Ark 原生入口

除了 OpenAI 兼容的 `/v1/video/generations`，Seedance 2.0 还提供一组 **BytePlus / Volcengine Ark 原生风格**的入口路径，方便已经基于 BytePlus SDK 或 Ark 文档写过对接的客户端零改动接入：

| 操作 | 方法 | 路径 |
|------|------|------|
| 创建视频任务 | POST | `/ark/api/v3/contents/generations/tasks` |
| 查询任务状态 | GET | `/ark/api/v3/contents/generations/tasks/{task_id}` |

> 该入口**只转换请求/响应格式**，上游链路、计费、分组、渠道与你用 `/v1/video/generations` 时完全一致（通常仍走 Service Inference 渠道）。换句话说：客户体感像在直连 BytePlus Ark，但实际经 EZModel 网关结算。

## 认证

```http
Authorization: Bearer YOUR_EZMODEL_API_KEY
Content-Type: application/json
```

API Key 仍使用 EZModel 的令牌，与 `/v1/video/generations` 共用。

## 请求体

完全遵循 Ark content-generations-tasks 规格：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | 是 | 模型名，如 `dreamina-seedance-2-0-fast-260128`；若渠道配置了模型重定向，也可传 BytePlus 模型 id |
| `content` | array | 是 | 内容项数组，见下 |
| `duration` | integer | 否 | 视频时长（秒） |
| `resolution` | string | 否 | `480p` / `720p` / `1080p`（Fast 仅支持 480p/720p） |
| `ratio` | string | 否 | 画幅，如 `16:9`、`9:16`、`1:1` |
| `generate_audio` | boolean | 否 | 是否生成音频 |
| `watermark` | boolean | 否 | 是否加水印 |

`content[]` 支持的项类型：

| type | 字段 | 说明 |
|------|------|------|
| `text` | `text` | 文本提示词（多项会被换行拼接） |
| `image_url` | `image_url.url` | 参考图（HTTPS/Base64 直链） |
| `video_url` | `video_url.url` + `role` | 参考视频素材（透传上游） |
| `audio_url` | `audio_url.url` + `role` | 参考音频素材（透传上游） |

## 文生视频示例

```bash
curl https://api.ezmodel.cloud/ark/api/v3/contents/generations/tasks \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dreamina-seedance-2-0-fast-260128",
    "content": [
      {"type": "text", "text": "A cinematic shot of a glass perfume bottle on a marble table, slow camera push in"}
    ],
    "duration": 4,
    "resolution": "720p",
    "ratio": "16:9"
  }'
```

响应（Ark 原生形状）：

```json
{
  "id": "mvt-512d4ffd9ce54256",
  "status": "queued"
}
```

## 图生视频 / 多参考素材示例

```bash
curl https://api.ezmodel.cloud/ark/api/v3/contents/generations/tasks \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dreamina-seedance-2-0-fast-260128",
    "content": [
      {"type": "text", "text": "Make the product rotate slowly"},
      {"type": "image_url", "image_url": {"url": "https://example.com/product.png"}},
      {"type": "audio_url", "audio_url": {"url": "https://example.com/bgm.mp3"}, "role": "reference_audio"}
    ],
    "duration": 4,
    "resolution": "720p"
  }'
```

## 查询任务状态

```bash
curl https://api.ezmodel.cloud/ark/api/v3/contents/generations/tasks/mvt-512d4ffd9ce54256 \
  -H "Authorization: Bearer $YOUR_API_KEY"
```

进行中响应：

```json
{
  "id": "mvt-512d4ffd9ce54256",
  "status": "processing"
}
```

完成响应（视频地址在 `content.video_url`）：

```json
{
  "id": "mvt-512d4ffd9ce54256",
  "model": "dreamina-seedance-2-0-fast-260128",
  "status": "succeeded",
  "content": {"video_url": "https://.../output.mp4"},
  "usage": {"completion_tokens": 87300, "total_tokens": 87300},
  "created_at": 1782971136
}
```

失败响应：

```json
{
  "id": "mvt-512d4ffd9ce54256",
  "status": "failed",
  "error": {"message": "task failed: ..."}
}
```

状态值映射：

| 内部状态 | Ark 返回 |
|------|------|
| SUBMITTED / QUEUED / NOT_START / PENDING / CREATED | `queued` |
| IN_PROGRESS / PROCESSING / RUNNING | `processing` |
| SUCCESS | `succeeded` |
| FAILURE | `failed` |

## 与 OpenAI 兼容入口的关系

两条入口共享同一个 token、同一个渠道、同一套计费：

- 请求体：本入口用 `content[]`，`/v1/video/generations` 用 `prompt` + `images` + `metadata`；二者最终被转成同一种上游请求。
- 响应体：本入口返回 `{id, status, content:{video_url}, usage}`，`/v1/video/generations` 返回 `{task_id, status}` 与 `{code, data:{...}}`。
- `task_id` 互通：任一入口创建的任务，都可用另一入口查询（注意路径与返回结构差异）。

## 注意事项

- 模型名建议直接用 `dreamina-seedance-2-0-*` 系列别名。若客户习惯传 BytePlus 官方模型 id，请在对应渠道的「模型重定向」里把该 id 映射到 `dreamina-*`，否则网关找不到渠道。
- Fast 模型仅支持 `480p` 和 `720p`。
- `content` 里的 `image_url` 直链会按 `no_ref` 档结算；只有 `asset://` 形式的上游资产引用（视频/音频/图片）才进入 `with_ref` 档。计费规则与 `/v1/video/generations` 完全一致，参见 Seedance 2.0 主文档。
