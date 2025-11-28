# OpenAI Responses API

## 概述

Responses API 提供了一个标准化的接口来创建模型响应。该接口遵循 OpenAI 的响应格式规范，支持流式和非流式输出。

---

## 接口详情

### 创建响应

**接口地址：** `POST /v1/responses`

**功能描述：** 根据提供的参数（如 Prompt 或 Messages）生成模型响应。

**认证方式：** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

### 请求参数

#### Header 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| Authorization | string | 是 | Bearer Token 认证 | Bearer sk-xxx... |
| Content-Type | string | 是 | 内容类型 | application/json |

#### Body 参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| model | string | 是 | - | 模型 ID |
| messages | array | 是 | - | 消息列表（Chat 模式） |
| prompt | string | 否 | - | 提示词（Completion 模式） |
| temperature | number | 否 | 1 | 采样温度 |
| max_tokens | integer | 否 | - | 最大生成长度 |
| stream | boolean | 否 | false | 是否流式响应 |

---

### 响应格式 (OpenAI Format)

Responses API 返回标准的 OpenAI 响应格式对象。

#### Chat Completion Object

```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "gpt-3.5-turbo-0613",
  "system_fingerprint": "fp_44709d6fcb",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello there, how may I assist you today?"
      },
      "logprobs": null,
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 9,
    "completion_tokens": 12,
    "total_tokens": 21
  }
}
```

#### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 响应的唯一标识符 |
| object | string | 对象类型，始终为 "chat.completion" |
| created | integer | 创建 Unix 时间戳 |
| model | string | 用于生成响应的模型 |
| choices | array | 响应选项列表 |
| usage | object | Token 使用统计 |

#### Chunk Object (流式响应)

当 `stream=true` 时，返回流式数据块。

```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion.chunk",
  "created": 1694268190,
  "model": "gpt-3.5-turbo-0613",
  "system_fingerprint": "fp_44709d6fcb",
  "choices": [
    {
      "index": 0,
      "delta": {
        "role": "assistant",
        "content": ""
      },
      "logprobs": null,
      "finish_reason": null
    }
  ]
}
```

---

## 示例

### 请求示例

```bash
curl -X POST https://your-api-domain.com/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [
      {
        "role": "user",
        "content": "Hello!"
      }
    ]
  }'
```

### 响应示例

```json
{
  "id": "chatcmpl-888",
  "object": "chat.completion",
  "created": 1699012345,
  "model": "gpt-3.5-turbo",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hi! How can I help you?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 10,
    "total_tokens": 20
  }
}
```