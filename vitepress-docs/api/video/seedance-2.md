# Seedance 2.0 视频生成

通过 OpenAI 兼容的视频任务接口调用 Service Inference 提供的 Seedance 2.0。接口是异步的：先提交任务拿到 `task_id`，再轮询任务状态，完成后读取返回的视频地址或通过内容代理下载。

## 接口地址

| 操作 | 方法 | 路径 |
|------|------|------|
| 创建视频任务 | POST | `/v1/video/generations` |
| 查询任务状态 | GET | `/v1/video/generations/{task_id}` |
| 下载视频内容 | GET | `/v1/video/generations/{task_id}/content` |

认证方式：

```http
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

## 可用模型

| 模型 | 说明 | 分辨率 |
|------|------|--------|
| `dreamina-seedance-2-0-260128` | 标准 Seedance 2.0 | `480p`, `720p`, `1080p` |
| `dreamina-seedance-2-0-ep` | EP 版本 Seedance 2.0 | `480p`, `720p`, `1080p` |
| `dreamina-seedance-2-0-fast-260128` | Fast 版本 Seedance 2.0 | `480p`, `720p` |
| `doubao-seedance-2-0-260128` | 兼容别名 | `480p`, `720p`, `1080p` |
| `doubao-seedance-2-0-fast-260128` | Fast 兼容别名 | `480p`, `720p` |

如果后台配置了模型映射，也可以使用站点展示的自定义模型名；最终会被转发到对应的上游 Seedance 模型。

## 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | 是 | 模型名称 |
| `prompt` | string | 是 | 视频生成提示词 |
| `image` | string | 否 | 单张参考图 URL 或 Base64 |
| `images` | string[] | 否 | 多张参考图 URL 或 Base64 |
| `size` | string | 否 | 分辨率，支持 `480p`、`720p`、`1080p`；默认按 `720p` 计费 |
| `duration` | integer | 否 | 视频时长，单位秒 |
| `seconds` | string | 否 | 视频时长字符串；存在时会覆盖 `duration` |
| `metadata.resolution` | string | 否 | 透传给上游的分辨率；优先级高于 `size` |
| `metadata.ratio` | string | 否 | 画幅比例，例如 `16:9`、`9:16`、`1:1` |
| `metadata.generate_audio` | boolean | 否 | 是否生成音频 |
| `metadata.watermark` | boolean | 否 | 是否添加水印 |
| `metadata.content` | array | 否 | 透传上游 content 项，可用于音频、视频等参考素材 |

`prompt` 会被转换为上游 `content[].type = "text"`。`image` 或 `images` 会被转换为 `content[].type = "image_url"`，并标记为参考图片。

## 文生视频示例

```bash
curl https://www.ezmodel.cloud/v1/video/generations \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dreamina-seedance-2-0-260128",
    "prompt": "A cinematic shot of a glass perfume bottle on a marble table, soft morning light, slow camera push in",
    "size": "720p",
    "duration": 4,
    "metadata": {
      "ratio": "16:9",
      "generate_audio": false,
      "watermark": false
    }
  }'
```

响应示例：

```json
{
  "task_id": "mvt-512d4ffd9ce54256",
  "status": "pending"
}
```

## 图生视频示例

```bash
curl https://www.ezmodel.cloud/v1/video/generations \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dreamina-seedance-2-0-fast-260128",
    "prompt": "Make the product rotate slowly, keep the label sharp and readable",
    "image": "https://example.com/product.png",
    "size": "720p",
    "seconds": "4",
    "metadata": {
      "ratio": "1:1"
    }
  }'
```

## 多参考素材示例

如果需要传入音频或更多参考素材，可以使用 `metadata.content`。其中 `type`、`image_url`、`audio_url`、`video_url` 会原样转成上游 content 项。

```json
{
  "model": "dreamina-seedance-2-0-260128",
  "prompt": "Generate a relaxed lifestyle video matching the reference audio mood",
  "images": [
    "https://example.com/ref-1.jpg",
    "https://example.com/ref-2.jpg"
  ],
  "duration": 4,
  "metadata": {
    "resolution": "480p",
    "ratio": "9:16",
    "content": [
      {
        "type": "audio_url",
        "audio_url": {
          "url": "https://example.com/ref.mp3"
        },
        "role": "reference_audio"
      }
    ]
  }
}
```

## 查询任务状态

```bash
curl https://www.ezmodel.cloud/v1/video/generations/mvt-512d4ffd9ce54256 \
  -H "Authorization: Bearer $YOUR_API_KEY"
```

成功完成后，响应中的 `status` 会变为 `SUCCESS` 或 `completed`，并包含视频结果地址。不同部署的响应包装可能略有差异，建议以 `task_id` 轮询直到任务完成。

## 下载视频内容

任务完成后可以直接使用状态响应里的视频 URL，也可以通过内容代理接口下载：

```bash
curl -L https://www.ezmodel.cloud/v1/video/generations/mvt-512d4ffd9ce54256/content \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  --output seedance.mp4
```

响应通常为 `video/mp4`，并支持分片下载。

## 计费说明

Seedance 2.0 使用上游返回的 `usage.total_tokens` 做最终结算，单位价格为美元每 1M tokens。系统会先按请求时长和分辨率预扣，任务完成后按真实 token 用量补扣或退款。

| 模型 | 档位 | 价格 |
|------|------|------|
| `dreamina-seedance-2-0-260128` / `dreamina-seedance-2-0-ep` | `480p_no_ref`, `720p_no_ref` | `$7.00 / 1M tok` |
| `dreamina-seedance-2-0-260128` / `dreamina-seedance-2-0-ep` | `480p_with_ref`, `720p_with_ref` | `$4.30 / 1M tok` |
| `dreamina-seedance-2-0-260128` / `dreamina-seedance-2-0-ep` | `1080p_no_ref` | `$7.70 / 1M tok` |
| `dreamina-seedance-2-0-260128` / `dreamina-seedance-2-0-ep` | `1080p_with_ref` | `$4.70 / 1M tok` |
| `dreamina-seedance-2-0-fast-260128` | `480p_no_ref`, `720p_no_ref` | `$5.60 / 1M tok` |
| `dreamina-seedance-2-0-fast-260128` | `480p_with_ref`, `720p_with_ref` | `$3.30 / 1M tok` |

计费公式：

```text
最终美元费用 = usage.total_tokens / 1,000,000 * 对应档位价格
内部额度消耗 = 最终美元费用 * 500000 * 分组倍率
```

示例：一次 480p 文生视频任务实际返回 `total_tokens = 40594`，价格为 `$7.00 / 1M tok`：

```text
40594 / 1,000,000 * 7.00 = $0.284158
```

## 注意事项

- Fast 模型当前只配置 `480p` 和 `720p`，不要请求 `1080p`。
- 只要包含图片、音频或视频参考素材，就会进入 `with_ref` 价格档。
- `metadata.resolution` 优先级高于顶层 `size`。
- 视频任务是异步执行，请不要在创建接口等待最终视频。
- 最终扣费以任务完成后的上游 usage 为准，任务失败会退回预扣费用。
