# 文本转语音 (TTS)

将文本转换为自然语音。

## 接口详情

**接口地址：** `POST /v1/audio/speech`

**功能描述：** 根据输入的文本生成音频文件。支持多种模型、声音和输出格式。

**认证方式：** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 请求参数

### Header 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| Authorization | string | 是 | Bearer Token 认证 | Bearer sk-xxx... |
| Content-Type | string | 是 | 内容类型 | application/json |

### Body 参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 | 示例 |
|--------|------|------|--------|------|------|
| model | string | 是 | - | 使用的模型 ID | `tts-1`, `tts-1-hd` |
| input | string | 是 | - | 要转换为音频的文本 | `你好，欢迎使用 TTS 服务。` |
| voice | string | 是 | - | 生成音频时使用的声音 | `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer` |
| response_format | string | 否 | `mp3` | 输出音频的格式 | `mp3`, `opus`, `aac`, `flac`, `wav`, `pcm` |
| speed | number | 否 | 1.0 | 生成音频的速度 | 0.25 到 4.0 |

---

## 响应参数

**响应内容：** 成功时返回音频文件的二进制流。

**Content-Type：** 根据 `response_format` 确定，例如 `audio/mpeg`。

---

## 代码示例

### Python (使用 OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://your-domain.com/v1"
)

response = client.audio.speech.create(
    model="tts-1",
    voice="alloy",
    input="你好，欢迎使用 TTS 服务。",
)

response.stream_to_file("speech.mp3")
```

### Curl 示例

```bash
curl https://your-domain.com/v1/audio/speech \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tts-1",
    "input": "你好，欢迎使用 TTS 服务。",
    "voice": "alloy"
  }' \
  --output speech.mp3
```

---

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /v1/audio/speech:
    post:
      summary: 文本转语音
      description: 将文本转换为自然语音。
      requestBody:
        content:
          application/json:
            schema:
              type: object
              required:
                - model
                - input
                - voice
              properties:
                model:
                  type: string
                input:
                  type: string
                voice:
                  type: string
      responses:
        '200':
          description: 成功生成音频
          content:
            audio/mpeg:
              schema:
                type: string
                format: binary
```
