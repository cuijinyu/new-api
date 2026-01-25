# API 参考文档

## 接口总览

| 接口 | 方法 | 描述 |
|------|------|------|
| `/v1/chat/completions` | POST | 创建聊天对话 |
| `/v1/responses` | POST | OpenAI Responses API |
| `/v1/messages` | POST | Claude Messages API |
| `/v1/models` | GET | 获取模型列表 |
| `/v1/images/generations` | POST | 生成图像 |
| `/v1/images/edits` | POST | 编辑图像 |
| `/v1/audio/speech` | POST | 文本转语音 |
| `/v1/audio/transcriptions` | POST | 语音转文本 |
| `/v1/audio/translations` | POST | 音频翻译 |
| `/kling/v1/videos/*` | POST/GET | Kling 视频生成 |
| `/sora/v1/videos/*` | POST/GET | Sora 视频生成 |

## 数据模型

### Message 对象

对话消息的基本结构：

```json
{
  "role": "user|assistant|system|tool",
  "content": "消息内容",
  "name": "发送者名称",
  "tool_calls": [...],
  "tool_call_id": "tool_call_id"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `role` | string | 是 | 消息角色：`system`, `user`, `assistant`, `tool` |
| `content` | string/array | 是 | 消息内容，可以是文本或多模态内容数组 |
| `name` | string | 否 | 发送者名称 |
| `tool_calls` | array | 否 | 工具调用列表（仅 assistant 角色） |
| `tool_call_id` | string | 否 | 工具调用 ID（仅 tool 角色） |

### Choice 对象

模型返回的选择项：

```json
{
  "index": 0,
  "message": {...},
  "finish_reason": "stop|length|tool_calls|content_filter"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `index` | integer | 选择项索引 |
| `message` | object | 消息内容 |
| `finish_reason` | string | 完成原因 |

### Usage 对象

Token 使用统计：

```json
{
  "prompt_tokens": 100,
  "completion_tokens": 50,
  "total_tokens": 150
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `prompt_tokens` | integer | 输入 Token 数 |
| `completion_tokens` | integer | 输出 Token 数 |
| `total_tokens` | integer | 总 Token 数 |

### Tool 对象

工具/函数定义：

```json
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "获取天气信息",
    "parameters": {
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
}
```

## 错误代码

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| `200` | 请求成功 |
| `400` | 请求参数错误 |
| `401` | 认证失败 |
| `403` | 权限不足 |
| `404` | 资源不存在 |
| `429` | 请求频率限制 |
| `500` | 服务器内部错误 |
| `503` | 服务不可用 |

### 错误类型

| 类型 | 说明 |
|------|------|
| `invalid_request_error` | 请求参数错误 |
| `invalid_api_key` | API 密钥无效 |
| `insufficient_quota` | 配额不足 |
| `rate_limit_exceeded` | 频率限制 |
| `api_error` | API 内部错误 |

## 请求限制

### 频率限制

根据账户等级，API 调用有不同的频率限制：

| 等级 | 每分钟请求数 | 并发连接数 |
|------|-------------|-----------|
| 免费版 | 60 | 1 |
| 基础版 | 300 | 5 |
| 专业版 | 3000 | 10 |
| 企业版 | 自定义 | 自定义 |

### Token 限制

不同模型有不同的上下文窗口限制：

| 模型 | 上下文窗口 |
|------|-----------|
| GPT-3.5 | 4K / 16K |
| GPT-4 | 8K / 32K / 128K |
| Claude 3 | 200K |
| Gemini | 32K / 128K |

## SDK 和工具

### 官方 SDK

| 语言 | 包名 | 安装命令 |
|------|------|---------|
| Python | openai | `pip install openai` |
| Node.js | openai | `npm install openai` |

### 第三方集成

- **LangChain** - 支持 Python 和 JavaScript
- **LlamaIndex** - 专注于 RAG 应用
- **Vercel AI SDK** - 前端流式响应
