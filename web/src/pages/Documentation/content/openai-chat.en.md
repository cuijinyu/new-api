# OpenAI Chat API

## Overview

Chat API provides an interface fully compatible with OpenAI Chat Completions API, supporting multi-turn conversations, streaming responses, tool calls, and more. Create model responses from conversation history, supporting both streaming and non-streaming responses.

---

## Interface Details

### Create Chat Completion

**Endpoint:** `POST /v1/chat/completions`

**Description:** Create model response based on conversation history. Supports streaming and non-streaming responses.

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

### Request Parameters

#### Header Parameters

| Parameter | Type | Required | Description | Example |
|--------|------|------|--------|------|
| Authorization | string | Yes | Bearer Token Authentication | Bearer sk-xxx... |
| Content-Type | string | Yes | Content Type | application/json |

#### Body Parameters

| Parameter | Type | Required | Default | Description | Constraints |
|--------|------|------|--------|------|------|
| model | string | Yes | - | Model ID | gpt-5.1, gpt-4, etc. |
| messages | array[object] | Yes | - | List of messages | Min 1 message |
| temperature | number | No | 1 | Sampling temperature | 0 ≤ x ≤ 2 |
| top_p | number | No | 1 | Nucleus sampling | 0 ≤ x ≤ 1 |
| n | integer | No | 1 | Number of generations | ≥ 1 |
| stream | boolean | No | false | Stream response | - |
| stream_options | object | No | - | Stream options | - |
| stream_options.include_usage | boolean | No | - | Include usage stats | - |
| stop | string/array | No | - | Stop sequences | - |
| max_tokens | integer | No | - | Max generation tokens | ≥ 0 |
| max_completion_tokens | integer | No | - | Max completion tokens | ≥ 0 |
| presence_penalty | number | No | 0 | Presence penalty | -2 ≤ x ≤ 2 |
| frequency_penalty | number | No | 0 | Frequency penalty | -2 ≤ x ≤ 2 |
| logit_bias | object | No | - | Token bias | - |
| user | string | No | - | User identifier | - |
| tools | array[object] | No | - | List of tools | - |
| tool_choice | string/object | No | auto | Tool choice strategy | none, auto, required |
| response_format | object | No | - | Response format | - |
| seed | integer | No | - | Random seed | - |
| reasoning_effort | string | No | - | Reasoning effort | low, medium, high |
| modalities | array[string] | No | - | Modality types | text, audio |
| audio | object | No | - | Audio config | - |

#### Messages Object

| Parameter | Type | Required | Description |
|--------|------|------|------|
| role | enum | Yes | Message role: system, user, assistant, tool, developer |
| content | string | Yes | Message content |
| name | string | No | Sender name |
| tool_calls | array[object] | No | List of tool calls |
| tool_call_id | string | No | Tool call ID (tool role message) |
| reasoning_content | string | No | Reasoning content |

#### Tool Object

| Parameter | Type | Required | Description |
|--------|------|------|------|
| type | string | Yes | Tool type, usually "function" |
| function | object | Yes | Function definition |
| function.name | string | Yes | Function name |
| function.description | string | No | Function description |
| function.parameters | object | No | Function parameter Schema |

#### ResponseFormat Object

| Parameter | Type | Required | Description |
|--------|------|------|------|
| type | enum | No | Response type: text, json_object, json_schema |
| json_schema | object | No | JSON Schema definition |

#### Audio Object

| Parameter | Type | Required | Description |
|--------|------|------|------|
| voice | string | No | Voice type |
| format | string | No | Audio format |

---

### Response Format

#### Success Response (200)

**Non-streaming Response:**

| Parameter | Type | Description |
|--------|------|------|
| id | string | Response ID |
| object | string | Object type, fixed as "chat.completion" |
| created | integer | Creation timestamp |
| model | string | Model used |
| choices | array[object] | List of choices |
| choices[].index | integer | Choice index |
| choices[].message | object | Message content |
| choices[].finish_reason | enum | Finish reason: stop, length, tool_calls, content_filter |
| usage | object | Usage statistics |
| system_fingerprint | string | System fingerprint |

#### Usage Object

| Parameter | Type | Description |
|--------|------|------|------|
| prompt_tokens | integer | Prompt tokens |
| completion_tokens | integer | Completion tokens |
| total_tokens | integer | Total tokens |
| prompt_tokens_details | object | Prompt details |
| completion_tokens_details | object | Completion details |

#### Streaming Response (Server-Sent Events)

Streaming responses are returned as data chunks starting with `data:`:

```data
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk",...}
data: [DONE]
```

---

## Code Examples

### 1. Basic Conversation

#### Request
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

#### Response
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
        "content": "Hello! I\'m doing well, thank you for asking. How can I assist you today?"
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

### 2. Streaming Response

#### Request
```bash
curl -X POST https://ezmodel.cloud/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "gpt-5.1",
    "messages": [
      {
        "role": "user",
        "content": "Write a poem about spring"
      }
    ],
    "stream": true,
    "temperature": 0.8
  }'
```

#### Response
```
data: {"id":"chatcmpl-8abcd1234efgh5678","object":"chat.completion.chunk","created":1699012345,"model":"gpt-5.1","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-8abcd1234efgh5678","object":"chat.completion.chunk","created":1699012345,"model":"gpt-5.1","choices":[{"index":0,"delta":{"content":"Spring"},"finish_reason":null}]}

data: {"id":"chatcmpl-8abcd1234efgh5678","object":"chat.completion.chunk","created":1699012345,"model":"gpt-5.1","choices":[{"index":0,"delta":{"content":" breeze"},"finish_reason":null}]}

... 

data: [DONE]
```

### 3. Tool Call

#### Request
```bash
curl -X POST https://ezmodel.cloud/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "gpt-5.1",
    "messages": [
      {
        "role": "user",
        "content": "What time is it in Beijing now?"
      }
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_current_time",
          "description": "Get current time in specified timezone",
          "parameters": {
            "type": "object",
            "properties": {
              "timezone": {
                "type": "string",
                "description": "Timezone, e.g. Asia/Shanghai"
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

#### Response
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

### 4. JSON Response

#### Request
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
        "content": "List three fruits, including name and color"
      }
    ],
    "response_format": {
      "type": "json_object"
    }
  }'
```

#### Response
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
        "content": "{\"fruits\":[{\"name\":\"Apple\",\"color\":\"Red\"},{\"name\":\"Banana\",\"color\":\"Yellow\"},{\"name\":\"Grape\",\"color\":\"Purple\"}]}"
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

## Error Handling

### Error Response Format

```json
{
  "error": {
    "message": "Error description message",
    "type": "Error type",
    "param": "Related parameter",
    "code": "Error code"
  }
}
```

### Common Error Codes

| HTTP Status Code | Error Type | Description |
|------------|----------|------|
| 400 | invalid_request_error | Request parameter error |
| 401 | invalid_api_key | API key invalid or not provided |
| 401 | insufficient_quota | API quota insufficient |
| 403 | access_denied | Access denied |
| 404 | not_found | Resource not found |
| 429 | rate_limit_exceeded | Request rate limit exceeded |
| 500 | api_error | Internal server error |
| 503 | service_unavailable | Service unavailable |

### Common Error Examples

#### Invalid API Key
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

#### Rate Limit Exceeded
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

#### Token Limit Exceeded
```json
{
  "error": {
    "message": "This model\'s maximum context length is 4097 tokens. However, your messages resulted in 5120 tokens.",
    "type": "invalid_request_error",
    "param": "messages",
    "code": "context_length_exceeded"
  }
}
```

---

## Limits

### Request Limits
- **Token Limit:** Depends on model type, typically 4K-128K tokens
- **Request Rate:** Depends on account level, typically 60-3000 requests per minute
- **Concurrent Connections:** Depends on account level, typically 1-10 concurrent connections
- **Response Timeout:** Non-streaming requests default timeout 30 seconds

### Model Support
- **Supported Models:** GPT-3.5 Series, GPT-4 Series, Claude Series, etc.
- **Tool Calls:** GPT-4, GPT-4 Turbo, GPT-4o, etc.
- **Vision Features:** GPT-4 Vision, GPT-4o, etc.
- **Audio Features:** GPT-4o, etc.

### Best Practices
1. **Set Temperature Appropriately:** High values (0.8-1.0) for creative tasks, low values (0.1-0.3) for accuracy tasks
2. **Control Token Usage:** Set appropriate max_tokens to avoid unnecessary consumption
3. **Use System Messages:** Set clear roles and behavior guidance via system role
4. **Error Handling:** Always include proper error handling and retry mechanisms
5. **Streaming Responses:** Recommend using stream=true for long text generation for better experience

---

## SDKs and Tools

### Official SDKs
- **OpenAI Python SDK:** `pip install openai`
- **OpenAI Node.js SDK:** `npm install openai`
- **OpenAI Java SDK:** Supports various Java HTTP clients

### Third-party Libraries
- **LangChain:** Supports chain calls and complex workflows
- **LlamaIndex:** Focuses on RAG (Retrieval Augmented Generation) applications

---

## Version Updates

### v1.0 (Current Version)
- Fully compatible with OpenAI Chat Completions API
- Supports streaming and non-streaming responses
- Supports tool calls and function calls
- Supports multi-modal input (text, image, audio)

### Coming Soon
- More model choices
- Enhanced error handling
- Finer cost control
- Batch processing features
