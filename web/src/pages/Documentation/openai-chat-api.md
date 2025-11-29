# OpenAI Chat API

## 概述

Chat API 提供与 OpenAI Chat Completions API 完全兼容的接口，支持多轮对话、流式响应、工具调用等功能。通过对话历史创建模型响应，支持流式和非流式响应。

---

## 接口详情

### 创建聊天对话

**接口地址：** `POST /v1/chat/completions`

**功能描述：** 根据对话历史创建模型响应。支持流式和非流式响应。

**认证方式：** Bearer Token
```
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

| 参数名 | 类型 | 必填 | 默认值 | 说明 | 约束 |
|--------|------|------|--------|------|------|
| model | string | 是 | - | 模型 ID | gpt-5.1, gpt-4 等 |
| messages | array[object] | 是 | - | 对话消息列表 | 最少 1 条消息 |
| temperature | number | 否 | 1 | 采样温度 | 0 ≤ x ≤ 2 |
| top_p | number | 否 | 1 | 核采样参数 | 0 ≤ x ≤ 1 |
| n | integer | 否 | 1 | 生成数量 | ≥ 1 |
| stream | boolean | 否 | false | 是否流式响应 | - |
| stream_options | object | 否 | - | 流式选项 | - |
| stream_options.include_usage | boolean | 否 | - | 包含使用统计 | - |
| stop | string/array | 否 | - | 停止序列 | - |
| max_tokens | integer | 否 | - | 最大生成 Token 数 | ≥ 0 |
| max_completion_tokens | integer | 否 | - | 最大补全 Token 数 | ≥ 0 |
| presence_penalty | number | 否 | 0 | 存在惩罚 | -2 ≤ x ≤ 2 |
| frequency_penalty | number | 否 | 0 | 频率惩罚 | -2 ≤ x ≤ 2 |
| logit_bias | object | 否 | - | Token 偏置 | - |
| user | string | 否 | - | 用户标识 | - |
| tools | array[object] | 否 | - | 工具列表 | - |
| tool_choice | string/object | 否 | auto | 工具选择策略 | none, auto, required |
| response_format | object | 否 | - | 响应格式 | - |
| seed | integer | 否 | - | 随机种子 | - |
| reasoning_effort | string | 否 | - | 推理强度 | low, medium, high |
| modalities | array[string] | 否 | - | 模态类型 | text, audio |
| audio | object | 否 | - | 音频配置 | - |

#### Messages 对象

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| role | enum | 是 | 消息角色：system, user, assistant, tool, developer |
| content | string | 是 | 消息内容 |
| name | string | 否 | 发送者名称 |
| tool_calls | array[object] | 否 | 工具调用列表 |
| tool_call_id | string | 否 | 工具调用 ID（tool 角色消息） |
| reasoning_content | string | 否 | 推理内容 |

#### Tool 对象

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| type | string | 是 | 工具类型，通常为 "function" |
| function | object | 是 | 函数定义 |
| function.name | string | 是 | 函数名称 |
| function.description | string | 否 | 函数描述 |
| function.parameters | object | 否 | 函数参数 Schema |

#### ResponseFormat 对象

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| type | enum | 否 | 响应类型：text, json_object, json_schema |
| json_schema | object | 否 | JSON Schema 定义 |

#### Audio 对象

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| voice | string | 否 | 语音类型 |
| format | string | 否 | 音频格式 |

---

### 响应格式

#### 成功响应 (200)

**非流式响应：**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| id | string | 响应 ID |
| object | string | 对象类型，固定为 "chat.completion" |
| created | integer | 创建时间戳 |
| model | string | 使用的模型 |
| choices | array[object] | 选择列表 |
| choices[].index | integer | 选择索引 |
| choices[].message | object | 消息内容 |
| choices[].finish_reason | enum | 完成原因：stop, length, tool_calls, content_filter |
| usage | object | 使用统计 |
| system_fingerprint | string | 系统指纹 |

#### Usage 对象

| 参数名 | 类型 | 说明 |
|--------|------|------|
| prompt_tokens | integer | 提示词 Token 数 |
| completion_tokens | integer | 补全 Token 数 |
| total_tokens | integer | 总 Token 数 |
| prompt_tokens_details | object | 提示词详情 |
| completion_tokens_details | object | 补全详情 |

#### 流式响应 (Server-Sent Events)

流式响应以 `data:` 开头的数据块形式返回：

```data
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk",...}
data: [DONE]
```

---

## 示例代码

### 1. 基础对话

#### 请求
```bash
curl -X POST https://ezmodel.cloud/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "gpt-5.1",
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

#### 响应
```json
{
  "id": "chatcmpl-8abcd1234efgh5678",
  "object": "chat.completion",
  "created": 1699012345,
  "model": "gpt-5.1",
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

### 2. 流式响应

#### 请求
```bash
curl -X POST https://ezmodel.cloud/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "gpt-5.1",
    "messages": [
      {
        "role": "user",
        "content": "写一首关于春天的诗"
      }
    ],
    "stream": true,
    "temperature": 0.8
  }'
```

#### 响应
```
data: {"id":"chatcmpl-8abcd1234efgh5678","object":"chat.completion.chunk","created":1699012345,"model":"gpt-5.1","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-8abcd1234efgh5678","object":"chat.completion.chunk","created":1699012345,"model":"gpt-5.1","choices":[{"index":0,"delta":{"content":"春"},"finish_reason":null}]}

data: {"id":"chatcmpl-8abcd1234efgh5678","object":"chat.completion.chunk","created":1699012345,"model":"gpt-5.1","choices":[{"index":0,"delta":{"content":"风"},"finish_reason":null}]}

...

data: [DONE]
```

### 3. 工具调用

#### 请求
```bash
curl -X POST https://ezmodel.cloud/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "gpt-5.1",
    "messages": [
      {
        "role": "user",
        "content": "现在北京几点了？"
      }
    ],
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

#### 响应
```json
{
  "id": "chatcmpl-8abcd1234efgh5678",
  "object": "chat.completion",
  "created": 1699012345,
  "model": "gpt-5.1",
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

### 4. JSON 格式响应

#### 请求
```bash
curl -X POST https://ezmodel.cloud/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "gpt-5.1",
    "messages": [
      {
        "role": "system",
        "content": "You are a helpful assistant designed to output JSON."
      },
      {
        "role": "user",
        "content": "列出三种水果，包含名称和颜色"
      }
    ],
    "response_format": {
      "type": "json_object"
    }
  }'
```

#### 响应
```json
{
  "id": "chatcmpl-8abcd1234efgh5678",
  "object": "chat.completion",
  "created": 1699012345,
  "model": "gpt-5.1",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"fruits\":[{\"name\":\"苹果\",\"color\":\"红色\"},{\"name\":\"香蕉\",\"color\":\"黄色\"},{\"name\":\"葡萄\",\"color\":\"紫色\"}]}"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 45,
    "completion_tokens": 42,
    "total_tokens": 87
  }
}
```

---

## 错误处理

### 错误响应格式

```json
{
  "error": {
    "message": "错误描述信息",
    "type": "错误类型",
    "param": "相关参数",
    "code": "错误代码"
  }
}
```

### 常见错误码

| HTTP状态码 | 错误类型 | 说明 |
|------------|----------|------|
| 400 | invalid_request_error | 请求参数错误 |
| 401 | invalid_api_key | API 密钥无效或未提供 |
| 401 | insufficient_quota | API 配额不足 |
| 403 | access_denied | 访问被拒绝 |
| 404 | not_found | 资源不存在 |
| 429 | rate_limit_exceeded | 请求频率超限 |
| 500 | api_error | 服务器内部错误 |
| 503 | service_unavailable | 服务暂不可用 |

### 常见错误示例

#### 无效的 API 密钥
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

#### 请求频率限制
```json
{
  "error": {
    "message": "Rate limit exceeded. Please try again later.",
    "type": "rate_limit_exceeded",
    "param": null,
    "code": "rate_limit_exceeded"
  }
}
```

#### Token 超限
```json
{
  "error": {
    "message": "This model's maximum context length is 4097 tokens. However, your messages resulted in 5120 tokens.",
    "type": "invalid_request_error",
    "param": "messages",
    "code": "context_length_exceeded"
  }
}
```

---

## 限制说明

### 请求限制
- **Token 限制：** 根据模型类型，通常为 4K-128K tokens
- **请求频率：** 根据账户等级限制，通常为每分钟 60-3000 次请求
- **并发连接：** 根据账户等级限制，通常为 1-10 个并发连接
- **响应超时：** 非流式请求默认超时时间 30 秒

### 模型支持
- **支持的模型：** GPT-3.5 系列、GPT-4 系列、Claude 系列等
- **工具调用：** GPT-4、GPT-4 Turbo、GPT-4o 等模型支持
- **视觉功能：** GPT-4 Vision、GPT-4o 等模型支持
- **音频功能：** GPT-4o 等模型支持

### 最佳实践
1. **合理设置 temperature：** 创造性任务使用较高值（0.8-1.0），准确性任务使用较低值（0.1-0.3）
2. **控制 Token 使用：** 设置合适的 max_tokens 避免不必要的消耗
3. **善用系统消息：** 通过 system role 设置明确的角色和行为指导
4. **错误处理：** 始终包含适当的错误处理和重试机制
5. **流式响应：** 长文本生成时建议使用 stream=true 获得更好体验

---

## SDK 和工具

### 官方 SDK
- **OpenAI Python SDK：** `pip install openai`
- **OpenAI Node.js SDK：** `npm install openai`
- **OpenAI Java SDK：** 支持多种 Java HTTP 客户端

### 第三方库
- **LangChain：** 支持链式调用和复杂工作流
- **LlamaIndex：** 专注于 RAG（检索增强生成）应用

---

## 版本更新

### v1.0 (当前版本)
- 完全兼容 OpenAI Chat Completions API
- 支持流式和非流式响应
- 支持工具调用和函数调用
- 支持多模态输入（文本、图像、音频）

### 即将推出
- 更多模型选择
- 增强的错误处理
- 更精细的成本控制
- 批量处理功能