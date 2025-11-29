# Claude 聊天

`POST /v1/messages`

Anthropic Claude Messages API 格式的请求。
需要在请求头中包含 `anthropic-version`。

## 请求参数

### Authorization

`Bearer Token`

在 Header 添加参数 Authorization，其值为在 Bearer 之后拼接 Token

示例：
`Authorization: Bearer ********************`

### Header 参数

| 参数名称 | 类型 | 必填 | 说明 | 示例值 |
| :--- | :--- | :--- | :--- | :--- |
| anthropic-version | string | 必需 | Anthropic API 版本 | `2023-06-01` |
| x-api-key | string | 可选 | Anthropic API Key (可选，也可使用 Bearer Token) | |

### Body 参数

`application/json`

| 参数名称 | 类型 | 必填 | 说明 | 示例值 |
| :--- | :--- | :--- | :--- | :--- |
| model | string | 必需 | 模型名称 | `claude-3-opus-20240229` |
| messages | array[object] | 必需 | 对话消息列表 | |
| messages.role | enum<string> | 必需 | 角色，可选值: `user`, `assistant` | |
| messages.content | string/array | 必需 | 消息内容 | |
| system | string/array | 可选 | 系统提示词 | |
| max_tokens | integer | 必需 | 最大生成 token 数 (>= 1) | `1` |
| temperature | number | 可选 | 温度 (0-1) | `0` |
| top_p | number | 可选 | Nucleus sampling | `0` |
| top_k | integer | 可选 | Top-k sampling | `0` |
| stream | boolean | 可选 | 是否流式输出 | `true` |
| stop_sequences | array[string] | 可选 | 停止序列 | |
| tools | array [object] | 可选 | 工具定义 | |
| tools.name | string | 可选 | 工具名称 | |
| tools.description | string | 可选 | 工具描述 | |
| tools.input_schema | object | 可选 | 工具输入参数 schema | |
| tool_choice | object | 可选 | 工具选择策略 | |
| tool_choice.type | enum<string> | 可选 | 类型: `auto`, `any`, `tool` | |
| tool_choice.name | string | 可选 | 工具名称 (当 type 为 tool 时) | |
| thinking | object | 可选 | 思考模式配置 | |
| thinking.type | enum<string> | 可选 | 类型: `enabled`, `disabled` | |
| thinking.budget_tokens | integer | 可选 | 思考预算 token 数 | |
| metadata | object | 可选 | 元数据 | |
| metadata.user_id | string | 可选 | 用户 ID | |

### 请求示例

```json
{
    "model": "claude-3-opus-20240229",
    "messages": [
        {
            "role": "user",
            "content": "Hello"
        }
    ],
    "system": "You are a helpful assistant.",
    "max_tokens": 1024,
    "temperature": 0.7,
    "stream": true
}
```

## 返回响应

🟢 `200` 成功

`application/json` 成功创建响应

### Body

| 参数名称 | 类型 | 说明 | 示例值 |
| :--- | :--- | :--- | :--- |
| id | string | 消息 ID | |
| type | string | 类型 | `message` |
| role | string | 角色 | `assistant` |
| content | array [object] | 内容列表 | |
| content.type | string | 内容类型 | `text` |
| content.text | string | 文本内容 | |
| model | string | 模型名称 | |
| stop_reason | enum<string> | 停止原因: `end_turn`, `max_tokens`, `stop_sequence`, `tool_use` | `end_turn` |
| usage | object | token 使用情况 | |
| usage.input_tokens | integer | 输入 tokens | |
| usage.output_tokens | integer | 输出 tokens | |
| usage.cache_creation_input_tokens | integer | 缓存创建 tokens | |
| usage.cache_read_input_tokens | integer | 缓存读取 tokens | |

### 响应示例

```json
{
    "id": "msg_01X...",
    "type": "message",
    "role": "assistant",
    "content": [
        {
            "type": "text",
            "text": "Hello!"
        }
    ],
    "model": "claude-3-opus-20240229",
    "stop_reason": "end_turn",
    "usage": {
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0
    }
}
```
