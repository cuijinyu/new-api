# OpenAI Responses API

## 概述

Responses API 提供了一个标准化的接口来创建模型响应。该接口遵循 OpenAI 的响应格式规范，支持流式和非流式输出。

## 接口详情

**接口地址：** `POST /v1/responses`

**功能描述：** 根据提供的参数（如 Prompt 或 Messages）生成模型响应。

**认证方式：** Bearer Token

```http
Authorization: Bearer YOUR_API_TOKEN
```

## 请求参数

### Header 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| Authorization | string | 是 | Bearer Token 认证 | `Bearer sk-xxx...` |
| Content-Type | string | 是 | 内容类型 | `application/json` |

### Body 参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| model | string | 是 | - | 模型 ID |
| input | array | 是 | - | 输入内容，消息列表 |
| instructions | string | 否 | - | 系统指令 |
| temperature | number | 否 | 1 | 采样温度 |
| max_output_tokens | integer | 否 | - | 最大输出 token 数 |
| stream | boolean | 否 | false | 是否流式响应 |
| previous_response_id | string | 否 | - | 上一次响应的 ID（用于缓存） |
| extra_body | object | 否 | - | 厂商扩展参数 |

### extra_body 参数（厂商扩展）

`extra_body` 参数用于传递特定厂商的扩展参数。当使用 OpenAI SDK 调用不同厂商的模型时，可以通过此参数传递厂商特有的配置。

#### BytePlus/字节跳动模型扩展参数

当调用 BytePlus/字节跳动的模型（如 Seed 系列）时，支持以下扩展参数：

| 参数名 | 类型 | 说明 |
|--------|------|------|
| caching | object | 缓存配置 |
| caching.type | string | 缓存类型：`enabled` 或 `disabled` |
| caching.prefix | boolean | 是否启用前缀缓存 |
| thinking | object | 思考模式配置 |
| thinking.type | string | 思考模式：`enabled` 或 `disabled` |

## 响应格式

### Chat Completion Object

```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "gpt-4",
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

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 响应的唯一标识符 |
| object | string | 对象类型，始终为 `chat.completion` |
| created | integer | 创建 Unix 时间戳 |
| model | string | 用于生成响应的模型 |
| choices | array | 响应选项列表 |
| usage | object | Token 使用统计 |

### Chunk Object (流式响应)

当 `stream=true` 时，返回流式数据块：

```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion.chunk",
  "created": 1694268190,
  "model": "gpt-4",
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

## 示例代码

### 请求示例

```bash
curl -X POST https://ezmodel.cloud/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "gpt-4",
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
  "model": "gpt-4",
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

## 厂商特定功能

### BytePlus/字节跳动缓存功能

BytePlus Seed 系列模型支持通过 `extra_body` 参数启用缓存功能，可以显著降低重复上下文的 token 消耗和响应延迟。

#### 前缀缓存 (Prefix Caching)

前缀缓存适用于有大量相同前缀内容的场景，如固定的系统提示词。输入内容至少需要 256 tokens 才能创建缓存。

```python
from openai import OpenAI

client = OpenAI(
    base_url='http://your-api-server/v1',
    api_key='your-api-key',
)

# 第一次请求：启用前缀缓存
response = client.responses.create(
    model="seed-1-6-250915",
    input=[
        {
            "role": "system",
            "content": "你是一个文学分析助手。请简洁清晰地回答问题。这是《麦琪的礼物》的节选...(长文本)"
        }
    ],
    extra_body={
        "caching": {"type": "enabled", "prefix": True},
        "thinking": {"type": "disabled"}
    }
)

print(f"Response ID: {response.id}")
print(f"Usage: {response.usage.model_dump_json()}")
```

#### 会话缓存 (Session Caching)

通过 `previous_response_id` 参数可以复用之前对话的上下文缓存：

```python
# 第二次请求：使用 previous_response_id 利用缓存
second_response = client.responses.create(
    model="seed-1-6-250915",
    previous_response_id=response.id,
    input=[
        {"role": "user", "content": "请用5个要点简要概括这个故事。"}
    ],
    extra_body={
        "caching": {"type": "enabled"},
        "thinking": {"type": "disabled"}
    }
)

# 检查缓存命中
if second_response.usage.input_tokens_details:
    cached_tokens = second_response.usage.input_tokens_details.cached_tokens
    print(f"缓存命中 tokens: {cached_tokens}")
```

#### 思考模式 (Thinking Mode)

思考模式可以让模型在生成响应前进行更深入的思考，适用于复杂推理任务：

```python
# 启用思考模式
response = client.responses.create(
    model="seed-1-6-250915",
    input=[
        {"role": "user", "content": "请分析这道数学题的解法..."}
    ],
    extra_body={
        "thinking": {"type": "enabled"}
    }
)
```

#### cURL 示例

```bash
# 启用前缀缓存
curl -X POST http://your-api-server/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "seed-1-6-250915",
    "input": [
      {
        "role": "system",
        "content": "你是一个文学分析助手..."
      },
      {
        "role": "user",
        "content": "请分析这段文字的主题"
      }
    ],
    "extra_body": {
      "caching": {"type": "enabled", "prefix": true},
      "thinking": {"type": "disabled"}
    }
  }'
```

```bash
# 使用会话缓存
curl -X POST http://your-api-server/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "seed-1-6-250915",
    "previous_response_id": "resp-abc123",
    "input": [
      {
        "role": "user",
        "content": "继续上面的分析"
      }
    ],
    "extra_body": {
      "caching": {"type": "enabled"},
      "thinking": {"type": "disabled"}
    }
  }'
```

### 缓存计费说明

- 输入 token 按照模型定价计费
- 输出 token 按照模型定价计费
- 缓存命中的 token（`cached_tokens`）按照缓存价格计费（通常为正常价格的 10%）
- 思考模式的 token（`reasoning_tokens`）按照输出 token 价格计费

### 注意事项

1. 前缀缓存要求输入内容至少 256 tokens
2. `caching.prefix` 不支持与 `max_output_tokens` 同时使用
3. 使用 `previous_response_id` 时，建议设置 `caching.type = "enabled"`
4. 缓存创建后需要等待一小段时间才能生效
