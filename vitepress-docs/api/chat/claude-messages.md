# Claude Messages API

## 概述

Anthropic Claude Messages API 格式的请求接口，支持 Claude 系列模型的原生调用方式。

## 接口详情

**接口地址：** `POST /v1/messages`

**功能描述：** 使用 Anthropic Claude Messages 格式创建对话响应。

**认证方式：** Bearer Token 或 x-api-key

```http
Authorization: Bearer YOUR_API_TOKEN
```

或

```http
x-api-key: YOUR_API_TOKEN
```

## 请求参数

### Header 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| anthropic-version | string | 是 | Anthropic API 版本 | `2023-06-01` |
| x-api-key | string | 否 | Anthropic API Key | - |
| Authorization | string | 否 | Bearer Token | `Bearer sk-xxx` |

### Body 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| model | string | 是 | 模型名称 | `claude-3-opus-20240229` |
| messages | array | 是 | 对话消息列表 | - |
| system | string/array | 否 | 系统提示词 | - |
| max_tokens | integer | 是 | 最大生成 token 数 | `1024` |
| temperature | number | 否 | 温度 (0-1) | `0.7` |
| top_p | number | 否 | Nucleus sampling | `0.9` |
| top_k | integer | 否 | Top-k sampling | `40` |
| stream | boolean | 否 | 是否流式输出 | `true` |
| stop_sequences | array | 否 | 停止序列 | - |
| tools | array | 否 | 工具定义 | - |
| tool_choice | object | 否 | 工具选择策略 | - |
| thinking | object | 否 | 思考模式配置 | - |
| metadata | object | 否 | 元数据 | - |

### Messages 对象

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| role | string | 是 | 角色，可选值：`user`, `assistant` |
| content | string/array | 是 | 消息内容 |

### Tool 对象

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| name | string | 是 | 工具名称 |
| description | string | 否 | 工具描述 |
| input_schema | object | 是 | 工具输入参数 schema |

### Thinking 对象

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| type | string | 是 | 类型：`enabled`, `disabled` |
| budget_tokens | integer | 否 | 思考预算 token 数 |

## 响应格式

### 成功响应 (200)

| 参数名 | 类型 | 说明 |
|--------|------|------|
| id | string | 消息 ID |
| type | string | 类型，固定为 `message` |
| role | string | 角色，固定为 `assistant` |
| content | array | 内容列表 |
| model | string | 模型名称 |
| stop_reason | string | 停止原因 |
| usage | object | Token 使用情况 |

### Content 对象

| 参数名 | 类型 | 说明 |
|--------|------|------|
| type | string | 内容类型：`text`, `tool_use` |
| text | string | 文本内容（type 为 text 时） |
| id | string | 工具调用 ID（type 为 tool_use 时） |
| name | string | 工具名称（type 为 tool_use 时） |
| input | object | 工具输入（type 为 tool_use 时） |

### Usage 对象

| 参数名 | 类型 | 说明 |
|--------|------|------|
| input_tokens | integer | 输入 tokens |
| output_tokens | integer | 输出 tokens |
| cache_creation_input_tokens | integer | 缓存创建 tokens |
| cache_read_input_tokens | integer | 缓存读取 tokens |

## 示例代码

### 基础对话

::: code-group

```bash [cURL]
curl -X POST https://ezmodel.cloud/v1/messages \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -H "x-api-key: YOUR_API_TOKEN" \
  -d '{
    "model": "claude-3-opus-20240229",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "Hello, Claude!"}
    ]
  }'
```

```python [Python]
import anthropic

client = anthropic.Anthropic(
    api_key="YOUR_API_TOKEN",
    base_url="https://ezmodel.cloud"
)

message = client.messages.create(
    model="claude-3-opus-20240229",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Hello, Claude!"}
    ]
)

print(message.content[0].text)
```

```javascript [Node.js]
import Anthropic from '@anthropic-ai/sdk';

const anthropic = new Anthropic({
  apiKey: 'YOUR_API_TOKEN',
  baseURL: 'https://ezmodel.cloud'
});

const message = await anthropic.messages.create({
  model: 'claude-3-opus-20240229',
  max_tokens: 1024,
  messages: [
    { role: 'user', content: 'Hello, Claude!' }
  ]
});

console.log(message.content[0].text);
```

:::

**响应示例：**

```json
{
  "id": "msg_01X...",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "Hello! How can I help you today?"
    }
  ],
  "model": "claude-3-opus-20240229",
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 10,
    "output_tokens": 12,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0
  }
}
```

### 带系统提示词

```bash
curl -X POST https://ezmodel.cloud/v1/messages \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -H "x-api-key: YOUR_API_TOKEN" \
  -d '{
    "model": "claude-3-opus-20240229",
    "max_tokens": 1024,
    "system": "You are a professional translator. Translate all user input to Chinese.",
    "messages": [
      {"role": "user", "content": "Hello, how are you today?"}
    ]
  }'
```

### 流式响应

```python
import anthropic

client = anthropic.Anthropic(
    api_key="YOUR_API_TOKEN",
    base_url="https://ezmodel.cloud"
)

with client.messages.stream(
    model="claude-3-opus-20240229",
    max_tokens=1024,
    messages=[{"role": "user", "content": "讲一个故事"}]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

### 工具调用

```bash
curl -X POST https://ezmodel.cloud/v1/messages \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -H "x-api-key: YOUR_API_TOKEN" \
  -d '{
    "model": "claude-3-opus-20240229",
    "max_tokens": 1024,
    "tools": [
      {
        "name": "get_weather",
        "description": "获取指定城市的天气信息",
        "input_schema": {
          "type": "object",
          "properties": {
            "city": {
              "type": "string",
              "description": "城市名称"
            }
          },
          "required": ["city"]
        }
      }
    ],
    "messages": [
      {"role": "user", "content": "北京今天天气怎么样？"}
    ]
  }'
```

### 多模态输入（图像）

```python
import anthropic
import base64

client = anthropic.Anthropic(
    api_key="YOUR_API_TOKEN",
    base_url="https://ezmodel.cloud"
)

# 使用 URL
message = client.messages.create(
    model="claude-3-opus-20240229",
    max_tokens=1024,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "url",
                        "url": "https://example.com/image.jpg"
                    }
                },
                {
                    "type": "text",
                    "text": "描述这张图片"
                }
            ]
        }
    ]
)

# 或使用 Base64
with open("image.jpg", "rb") as f:
    image_data = base64.standard_b64encode(f.read()).decode("utf-8")

message = client.messages.create(
    model="claude-3-opus-20240229",
    max_tokens=1024,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_data
                    }
                },
                {
                    "type": "text",
                    "text": "描述这张图片"
                }
            ]
        }
    ]
)
```

## 支持的模型

| 模型 | 上下文窗口 | 说明 |
|------|-----------|------|
| claude-3-opus-20240229 | 200K | 最强能力，适合复杂任务 |
| claude-3-sonnet-20240229 | 200K | 平衡性能与成本 |
| claude-3-haiku-20240307 | 200K | 快速响应，成本最低 |
| claude-3-5-sonnet-20241022 | 200K | Claude 3.5 Sonnet |

## 与 OpenAI 格式对比

| 特性 | Claude Messages | OpenAI Chat |
|------|-----------------|-------------|
| 系统消息 | 独立 `system` 字段 | messages 数组中 |
| 响应格式 | `content` 数组 | `message.content` 字符串 |
| 必填参数 | `max_tokens` 必填 | `max_tokens` 可选 |
| 停止原因 | `stop_reason` | `finish_reason` |

::: tip 提示
如果你习惯使用 OpenAI 格式，也可以使用 `/v1/chat/completions` 接口调用 Claude 模型，系统会自动转换格式。
:::
