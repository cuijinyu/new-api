# OpenAI Chat API

## 概述

Chat API 提供与 OpenAI Chat Completions API 完全兼容的接口，支持多轮对话、流式响应、工具调用等功能。

## 接口详情

**接口地址：** `POST /v1/chat/completions`

**功能描述：** 根据对话历史创建模型响应。支持流式和非流式响应。

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

| 参数名 | 类型 | 必填 | 默认值 | 说明 | 约束 |
|--------|------|------|--------|------|------|
| model | string | 是 | - | 模型 ID | `gpt-4`, `gpt-3.5-turbo` 等 |
| messages | array | 是 | - | 对话消息列表 | 最少 1 条消息 |
| temperature | number | 否 | 1 | 采样温度 | 0 ≤ x ≤ 2 |
| top_p | number | 否 | 1 | 核采样参数 | 0 ≤ x ≤ 1 |
| n | integer | 否 | 1 | 生成数量 | ≥ 1 |
| stream | boolean | 否 | false | 是否流式响应 | - |
| stream_options | object | 否 | - | 流式选项 | - |
| stop | string/array | 否 | - | 停止序列 | - |
| max_tokens | integer | 否 | - | 最大生成 Token 数 | ≥ 0 |
| max_completion_tokens | integer | 否 | - | 最大补全 Token 数 | ≥ 0 |
| presence_penalty | number | 否 | 0 | 存在惩罚 | -2 ≤ x ≤ 2 |
| frequency_penalty | number | 否 | 0 | 频率惩罚 | -2 ≤ x ≤ 2 |
| logit_bias | object | 否 | - | Token 偏置 | - |
| user | string | 否 | - | 用户标识 | - |
| tools | array | 否 | - | 工具列表 | - |
| tool_choice | string/object | 否 | auto | 工具选择策略 | `none`, `auto`, `required` |
| response_format | object | 否 | - | 响应格式 | - |
| seed | integer | 否 | - | 随机种子 | - |
| reasoning_effort | string | 否 | - | 推理强度 | `low`, `medium`, `high` |

### Messages 对象

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| role | string | 是 | 消息角色：`system`, `user`, `assistant`, `tool`, `developer` |
| content | string/array | 是 | 消息内容 |
| name | string | 否 | 发送者名称 |
| tool_calls | array | 否 | 工具调用列表 |
| tool_call_id | string | 否 | 工具调用 ID（tool 角色消息） |

### Tool 对象

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| type | string | 是 | 工具类型，通常为 `function` |
| function | object | 是 | 函数定义 |
| function.name | string | 是 | 函数名称 |
| function.description | string | 否 | 函数描述 |
| function.parameters | object | 否 | 函数参数 Schema |

### ResponseFormat 对象

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| type | string | 否 | 响应类型：`text`, `json_object`, `json_schema` |
| json_schema | object | 否 | JSON Schema 定义 |

## 响应格式

### 成功响应 (200)

**非流式响应：**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| id | string | 响应 ID |
| object | string | 对象类型，固定为 `chat.completion` |
| created | integer | 创建时间戳 |
| model | string | 使用的模型 |
| choices | array | 选择列表 |
| usage | object | 使用统计 |
| system_fingerprint | string | 系统指纹 |

### Usage 对象

| 参数名 | 类型 | 说明 |
|--------|------|------|
| prompt_tokens | integer | 提示词 Token 数 |
| completion_tokens | integer | 补全 Token 数 |
| total_tokens | integer | 总 Token 数 |

### 流式响应 (SSE)

流式响应以 `data:` 开头的数据块形式返回：

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk",...}
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk",...}
data: [DONE]
```

## 示例代码

### 基础对话

::: code-group

```bash [cURL]
curl -X POST https://ezmodel.cloud/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {
        "role": "system",
        "content": "You are a helpful assistant."
      },
      {
        "role": "user",
        "content": "Hello, how are you?"
      }
    ],
    "temperature": 0.7,
    "max_tokens": 150
  }'
```

```python [Python]
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_TOKEN",
    base_url="https://ezmodel.cloud/v1"
)

response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"}
    ],
    temperature=0.7,
    max_tokens=150
)

print(response.choices[0].message.content)
```

```javascript [Node.js]
import OpenAI from 'openai';

const openai = new OpenAI({
  apiKey: 'YOUR_API_TOKEN',
  baseURL: 'https://ezmodel.cloud/v1'
});

const response = await openai.chat.completions.create({
  model: 'gpt-4',
  messages: [
    { role: 'system', content: 'You are a helpful assistant.' },
    { role: 'user', content: 'Hello, how are you?' }
  ],
  temperature: 0.7,
  max_tokens: 150
});

console.log(response.choices[0].message.content);
```

:::

**响应示例：**

```json
{
  "id": "chatcmpl-8abcd1234efgh5678",
  "object": "chat.completion",
  "created": 1699012345,
  "model": "gpt-4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! I'm doing well, thank you for asking. How can I assist you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 22,
    "completion_tokens": 18,
    "total_tokens": 40
  }
}
```

### 流式响应

::: code-group

```bash [cURL]
curl -X POST https://ezmodel.cloud/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "写一首关于春天的诗"}],
    "stream": true,
    "temperature": 0.8
  }'
```

```python [Python]
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_TOKEN",
    base_url="https://ezmodel.cloud/v1"
)

stream = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "写一首关于春天的诗"}],
    stream=True,
    temperature=0.8
)

for chunk in stream:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="")
```

```javascript [Node.js]
import OpenAI from 'openai';

const openai = new OpenAI({
  apiKey: 'YOUR_API_TOKEN',
  baseURL: 'https://ezmodel.cloud/v1'
});

const stream = await openai.chat.completions.create({
  model: 'gpt-4',
  messages: [{ role: 'user', content: '写一首关于春天的诗' }],
  stream: true,
  temperature: 0.8
});

for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0]?.delta?.content || '');
}
```

:::

### 工具调用

::: code-group

```bash [cURL]
curl -X POST https://ezmodel.cloud/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "现在北京几点了？"}],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_current_time",
          "description": "获取指定时区的当前时间",
          "parameters": {
            "type": "object",
            "properties": {
              "timezone": {
                "type": "string",
                "description": "时区，如 Asia/Shanghai"
              }
            },
            "required": ["timezone"]
          }
        }
      }
    ],
    "tool_choice": "auto"
  }'
```

```python [Python]
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_TOKEN",
    base_url="https://ezmodel.cloud/v1"
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取指定时区的当前时间",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "时区，如 Asia/Shanghai"
                    }
                },
                "required": ["timezone"]
            }
        }
    }
]

response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "现在北京几点了？"}],
    tools=tools,
    tool_choice="auto"
)

print(response.choices[0].message)
```

:::

**响应示例：**

```json
{
  "id": "chatcmpl-8abcd1234efgh5678",
  "object": "chat.completion",
  "created": 1699012345,
  "model": "gpt-4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_abc123",
            "type": "function",
            "function": {
              "name": "get_current_time",
              "arguments": "{\"timezone\": \"Asia/Shanghai\"}"
            }
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ],
  "usage": {
    "prompt_tokens": 58,
    "completion_tokens": 21,
    "total_tokens": 79
  }
}
```

### JSON 格式响应

```bash
curl -X POST https://ezmodel.cloud/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
      {"role": "user", "content": "列出三种水果，包含名称和颜色"}
    ],
    "response_format": {"type": "json_object"}
  }'
```

## 错误处理

### 常见错误码

| HTTP状态码 | 错误类型 | 说明 |
|------------|----------|------|
| 400 | `invalid_request_error` | 请求参数错误 |
| 401 | `invalid_api_key` | API 密钥无效或未提供 |
| 401 | `insufficient_quota` | API 配额不足 |
| 403 | `access_denied` | 访问被拒绝 |
| 404 | `not_found` | 资源不存在 |
| 429 | `rate_limit_exceeded` | 请求频率超限 |
| 500 | `api_error` | 服务器内部错误 |
| 503 | `service_unavailable` | 服务暂不可用 |

### 错误响应示例

```json
{
  "error": {
    "message": "Invalid API key provided",
    "type": "invalid_request_error",
    "param": "authorization",
    "code": "invalid_api_key"
  }
}
```

## 最佳实践

::: tip 温度设置
- 创造性任务（写作、头脑风暴）：使用较高值 0.8-1.0
- 准确性任务（翻译、代码）：使用较低值 0.1-0.3
:::

::: tip Token 控制
设置合适的 `max_tokens` 避免不必要的消耗，同时确保有足够空间生成完整回复。
:::

::: tip 系统消息
通过 `system` role 设置明确的角色和行为指导，可以显著提升响应质量。
:::

::: tip 错误处理
始终包含适当的错误处理和重试机制，处理网络异常和 API 限制。
:::
