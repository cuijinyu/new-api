# Claude Chat

`POST /v1/messages`

Requests in Anthropic Claude Messages API format.
Requires `anthropic-version` in the request header.

## Request Parameters

### Authorization

`Bearer Token`

Add the `Authorization` parameter to the Header, with the value being the Token appended after `Bearer `.

Example:
`Authorization: Bearer ********************`

### Header Parameters

| Parameter Name | Type | Required | Description | Example Value |
| :--- | :--- | :--- | :--- | :--- |
| anthropic-version | string | Required | Anthropic API Version | `2023-06-01` |
| x-api-key | string | Optional | Anthropic API Key (Optional, can also use Bearer Token) | |

### Body Parameters

`application/json`

| Parameter Name | Type | Required | Description | Example Value |
| :--- | :--- | :--- | :--- | :--- |
| model | string | Required | Model Name | `claude-3-opus-20240229` |
| messages | array[object] | Required | List of conversation messages | |
| messages.role | `enum<string>` | Required | Role, options: `user`, `assistant` | |
| messages.content | string/array | Required | Message content | |
| system | string/array | Optional | System prompt | |
| max_tokens | integer | Required | Max generation tokens (>= 1) | `1` |
| temperature | number | Optional | Temperature (0-1) | `0` |
| top_p | number | Optional | Nucleus sampling | `0` |
| top_k | integer | Optional | Top-k sampling | `0` |
| stream | boolean | Optional | Whether to stream output | `true` |
| stop_sequences | array[string] | Optional | Stop sequences | |
| tools | array [object] | Optional | Tool definitions | |
| tools.name | string | Optional | Tool name | |
| tools.description | string | Optional | Tool description | |
| tools.input_schema | object | Optional | Tool input parameter schema | |
| tool_choice | object | Optional | Tool choice strategy | |
| tool_choice.type | `enum<string>` | Optional | Type: `auto`, `any`, `tool` | |
| tool_choice.name | string | Optional | Tool name (when type is `tool`) | |
| thinking | object | Optional | Thinking mode configuration | |
| thinking.type | `enum<string>` | Optional | Type: `enabled`, `disabled` | |
| thinking.budget_tokens | integer | Optional | Thinking budget tokens | |
| metadata | object | Optional | Metadata | |
| metadata.user_id | string | Optional | User ID | |

### Request Example

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

## Response

`200` Success

`application/json` Response created successfully

### Body

| Parameter Name | Type | Description | Example Value |
| :--- | :--- | :--- | :--- |
| id | string | Message ID | |
| type | string | Type | `message` |
| role | string | Role | `assistant` |
| content | array [object] | Content list | |
| content.type | string | Content type | `text` |
| content.text | string | Text content | |
| model | string | Model Name | |
| stop_reason | `enum<string>` | Stop reason: `end_turn`, `max_tokens`, `stop_sequence`, `tool_use` | `end_turn` |
| usage | object | Token usage | |
| usage.input_tokens | integer | Input tokens | |
| usage.output_tokens | integer | Output tokens | |
| usage.cache_creation_input_tokens | integer | Cache creation input tokens | |
| usage.cache_read_input_tokens | integer | Cache read input tokens | |

### Response Example

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