# 音频翻译

将音频文件翻译并转录为英文文本。

## 接口详情

**接口地址：** `POST /v1/audio/translations`

**功能描述：** 将任何支持的语言音频文件翻译为英文文本。支持多种音频格式。

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
| Content-Type | string | 是 | 内容类型 | `multipart/form-data` |

### Body 参数 (Multipart Form Data)

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| file | file | 是 | 要翻译的音频文件 | `speech.mp3` |
| model | string | 是 | 使用的模型 ID | `whisper-1` |
| prompt | string | 否 | 用于指导模型风格或继续翻译的提示文本 | - |
| response_format | string | 否 | 响应格式 (json, text, srt, vtt) | `json` |
| temperature | number | 否 | 采样温度 (0-1 之间) | `0` |

---

## 响应参数

**响应格式：** 默认返回 JSON 格式的翻译后英文文本。

```json
{
  "text": "Hello, this is a translated text from audio."
}
```

---

## 代码示例

### Python (使用 OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://your-domain.com/v1"
)

audio_file = open("german_speech.mp3", "rb")
translation = client.audio.translations.create(
  model="whisper-1", 
  file=audio_file
)

print(translation.text)
```

### Curl 示例

```bash
curl https://your-domain.com/v1/audio/translations \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: multipart/form-data" \
  -F file="@german_speech.mp3" \
  -F model="whisper-1"
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
  /v1/audio/translations:
    post:
      summary: 音频翻译
      description: 将音频文件翻译为英文文本。
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              required:
                - file
                - model
              properties:
                file:
                  type: string
                  format: binary
                model:
                  type: string
      responses:
        '200':
          description: 成功翻译音频
          content:
            application/json:
              schema:
                type: object
                properties:
                  text:
                    type: string
```
