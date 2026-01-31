# BytePlus Responses API

## 概述

BytePlus Responses API 是字节跳动火山引擎提供的统一模型响应接口，支持多种输入格式、智能缓存和思考模式等高级特性。该接口遵循 BytePlus 的响应格式规范，支持流式和非流式输出。

## 接口详情

**接口地址：** `POST /api/v3/responses`

**功能描述：** 根据提供的输入内容和指令生成模型响应，支持自动缓存和思考模式。

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
| model | string | 是 | - | 推理接入点 ID (endpoint ID) 或 Model ID |
| input | object/array | 否 | - | 输入内容，可以是消息列表或其他格式 |
| instructions | string | 否 | - | 系统指令，类似于 system message |
| max_output_tokens | integer | 否 | - | 最大输出 token 数 |
| temperature | number | 否 | 1.0 | 采样温度，范围 [0, 2] |
| top_p | number | 否 | 1.0 | 核采样概率，范围 [0, 1] |
| stream | boolean | 否 | false | 是否流式响应 |
| previous_response_id | string | 否 | - | 上一次响应的 ID，用于启用自动缓存 |
| caching | object | 否 | - | 缓存配置 |
| thinking | object | 否 | - | 思考模式配置 |
| store | boolean | 否 | - | 是否存储响应以供后续使用 |
| tools | array | 否 | - | 工具配置（函数调用） |
| tool_choice | string/object | 否 | - | 工具选择策略 |
| metadata | object | 否 | - | 元数据 |

#### Caching 对象

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| type | string | 是 | 缓存类型: `enabled` 或 `disabled` |
| prefix | boolean | 否 | 是否启用前缀缓存 |

#### Thinking 对象

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| type | string | 是 | 思考模式: `enabled` 或 `disabled` |

## 响应格式

### Response Object

```json
{
  "id": "resp-abc123",
  "object": "response",
  "created_at": 1699012345,
  "model": "ep-20241231-abc123",
  "output": [
    {
      "type": "message",
      "id": "msg-xyz789",
      "status": "completed",
      "role": "assistant",
      "content": [
        {
          "type": "text",
          "text": "Hello! How can I help you today?"
        }
      ]
    }
  ],
  "usage": {
    "input_tokens": 10,
    "output_tokens": 12,
    "total_tokens": 22,
    "input_tokens_details": {
      "cached_tokens": 0
    }
  },
  "status": "completed",
  "caching": {
    "type": "enabled",
    "prefix": true
  },
  "store": true,
  "expire_at": 1699098745
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 响应的唯一标识符 (resp-xxx) |
| object | string | 对象类型，始终为 `response` |
| created_at | integer | 创建 Unix 时间戳 |
| model | string | 用于生成响应的模型或接入点 ID |
| output | array | 输出内容列表 |
| usage | object | Token 使用统计 |
| status | string | 响应状态: `completed`, `in_progress`, `failed` 等 |
| caching | object | 缓存配置结果 |
| store | boolean | 是否已存储响应 |
| expire_at | integer | 过期时间戳（如果启用了存储） |

### Usage 对象

| 字段 | 类型 | 说明 |
|------|------|------|
| input_tokens | integer | 输入 token 数 |
| output_tokens | integer | 输出 token 数 |
| total_tokens | integer | 总 token 数 |
| input_tokens_details | object | 输入 token 详情 |
| output_tokens_details | object | 输出 token 详情 |

#### Input Tokens Details

| 字段 | 类型 | 说明 |
|------|------|------|
| cached_tokens | integer | 缓存命中的 token 数 |

#### Output Tokens Details

| 字段 | 类型 | 说明 |
|------|------|------|
| reasoning_tokens | integer | 思考模式使用的 token 数 |

### Stream Response (流式响应)

当 `stream=true` 时，返回 SSE 格式的流式数据：

```
data: {"type":"response.output_item.added","item":{"type":"message","id":"msg-xyz789","status":"in_progress","role":"assistant"}}

data: {"type":"response.output_item.content_part.added","item_id":"msg-xyz789","output_index":0,"content_index":0,"part":{"type":"text"}}

data: {"type":"response.output_item.content_part.delta","item_id":"msg-xyz789","output_index":0,"content_index":0,"delta":"Hello"}

data: {"type":"response.output_item.content_part.delta","item_id":"msg-xyz789","output_index":0,"content_index":0,"delta":"!"}

data: {"type":"response.output_item.done","item":{"type":"message","id":"msg-xyz789","status":"completed","role":"assistant","content":[{"type":"text","text":"Hello!"}]}}

data: {"type":"response.done","response":{"id":"resp-abc123","object":"response","created_at":1699012345,"model":"ep-20241231-abc123","status":"completed","usage":{"input_tokens":10,"output_tokens":2,"total_tokens":12}}}

data: [DONE]
```

## 特性说明

### 自动缓存

通过传递 `previous_response_id` 参数，可以启用自动缓存功能，系统会自动缓存和复用之前对话的上下文：

```json
{
  "model": "ep-20241231-abc123",
  "input": [
    {"role": "user", "content": "继续上次的话题"}
  ],
  "previous_response_id": "resp-previous-123"
}
```

### 前缀缓存

启用前缀缓存可以缓存输入的公共前缀部分，适用于有大量相同前缀的场景：

```json
{
  "model": "ep-20241231-abc123",
  "input": [...],
  "caching": {
    "type": "enabled",
    "prefix": true
  }
}
```

### 思考模式

启用思考模式可以让模型在生成响应前进行更深入的思考：

```json
{
  "model": "ep-20241231-abc123",
  "input": [...],
  "thinking": {
    "type": "enabled"
  }
}
```

## 示例代码

### 基础请求示例

```bash
curl -X POST https://your-domain.com/api/v3/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "ep-20241231-abc123",
    "input": [
      {
        "role": "user",
        "content": "你好，请介绍一下自己"
      }
    ],
    "max_output_tokens": 1000
  }'
```

### 使用缓存的请求示例

```bash
curl -X POST https://your-domain.com/api/v3/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "ep-20241231-abc123",
    "input": [
      {
        "role": "user",
        "content": "继续刚才的话题"
      }
    ],
    "previous_response_id": "resp-abc123",
    "caching": {
      "type": "enabled",
      "prefix": true
    }
  }'
```

### 流式请求示例

```bash
curl -X POST https://your-domain.com/api/v3/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "ep-20241231-abc123",
    "input": [
      {
        "role": "user",
        "content": "写一个简短的故事"
      }
    ],
    "stream": true
  }'
```

### Python 示例

```python
import requests
import json

url = "https://your-domain.com/api/v3/responses"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_API_TOKEN"
}

# 非流式请求
data = {
    "model": "ep-20241231-abc123",
    "input": [
        {
            "role": "user",
            "content": "你好，请介绍一下自己"
        }
    ],
    "max_output_tokens": 1000,
    "temperature": 0.7
}

response = requests.post(url, headers=headers, json=data)
result = response.json()
print(result)

# 流式请求
data["stream"] = True
response = requests.post(url, headers=headers, json=data, stream=True)

for line in response.iter_lines():
    if line:
        line = line.decode('utf-8')
        if line.startswith('data: '):
            data_str = line[6:]
            if data_str == '[DONE]':
                break
            try:
                chunk = json.loads(data_str)
                print(chunk)
            except json.JSONDecodeError:
                pass
```

## 计费说明

- 输入 token 按照模型定价计费
- 输出 token 按照模型定价计费
- 缓存命中的 token（`cached_tokens`）按照缓存价格计费（通常为正常价格的 10%）
- 思考模式的 token（`reasoning_tokens`）按照输出 token 价格计费
- 支持分段计费，根据输入 token 数量自动应用不同价格梯度

## 错误处理

当请求失败时，响应会包含错误信息：

```json
{
  "error": {
    "message": "Invalid request: model is required",
    "type": "invalid_request_error",
    "code": "bad_request_body"
  }
}
```

常见错误码：

| 错误码 | 说明 |
|--------|------|
| bad_request_body | 请求体格式错误 |
| invalid_model | 无效的模型 ID |
| rate_limit_exceeded | 超过速率限制 |
| insufficient_quota | 配额不足 |
| upstream_error | 上游服务错误 |

## 参考文档

- [BytePlus ModelArk 官方文档](https://docs.byteplus.com/en/docs/ModelArk/Create_model_request)
- [字节跳动火山引擎 API 文档](https://www.volcengine.com/docs/82379)
