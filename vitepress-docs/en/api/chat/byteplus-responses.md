# BytePlus Responses API

## Overview

BytePlus Responses API is a unified model response interface provided by ByteDance's Volcano Engine, supporting multiple input formats, intelligent caching, and advanced features like thinking mode. This interface follows BytePlus response format specifications, supporting both streaming and non-streaming outputs.

## Interface Details

**Endpoint:** `POST /api/v3/responses`

**Description:** Generate model responses based on provided input content and instructions, with support for automatic caching and thinking mode.

**Authentication:** Bearer Token

```http
Authorization: Bearer YOUR_API_TOKEN
```

## Request Parameters

### Header Parameters

| Parameter | Type | Required | Description | Example |
|--------|------|------|------|------|
| Authorization | string | Yes | Bearer Token Authentication | `Bearer sk-xxx...` |
| Content-Type | string | Yes | Content Type | `application/json` |

### Body Parameters

| Parameter | Type | Required | Default | Description |
|--------|------|------|--------|------|
| model | string | Yes | - | Inference endpoint ID or Model ID |
| input | object/array | No | - | Input content, can be message list or other formats |
| instructions | string | No | - | System instructions, similar to system message |
| max_output_tokens | integer | No | - | Maximum output tokens |
| temperature | number | No | 1.0 | Sampling temperature, range [0, 2] |
| top_p | number | No | 1.0 | Nucleus sampling probability, range [0, 1] |
| stream | boolean | No | false | Whether to stream response |
| previous_response_id | string | No | - | Previous response ID for automatic caching |
| caching | object | No | - | Caching configuration |
| thinking | object | No | - | Thinking mode configuration |
| store | boolean | No | - | Whether to store response for later use |
| tools | array | No | - | Tool configuration (function calling) |
| tool_choice | string/object | No | - | Tool choice strategy |
| metadata | object | No | - | Metadata |

#### Caching Object

| Parameter | Type | Required | Description |
|--------|------|------|------|
| type | string | Yes | Cache type: `enabled` or `disabled` |
| prefix | boolean | No | Whether to enable prefix caching |

#### Thinking Object

| Parameter | Type | Required | Description |
|--------|------|------|------|
| type | string | Yes | Thinking mode: `enabled` or `disabled` |

## Response Format

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

### Field Description

| Field | Type | Description |
|------|------|------|
| id | string | Unique identifier for the response (resp-xxx) |
| object | string | Object type, always `response` |
| created_at | integer | Creation Unix timestamp |
| model | string | Model or endpoint ID used for generation |
| output | array | Output content list |
| usage | object | Token usage statistics |
| status | string | Response status: `completed`, `in_progress`, `failed`, etc. |
| caching | object | Caching configuration result |
| store | boolean | Whether response is stored |
| expire_at | integer | Expiration timestamp (if storage enabled) |

### Usage Object

| Field | Type | Description |
|------|------|------|
| input_tokens | integer | Input token count |
| output_tokens | integer | Output token count |
| total_tokens | integer | Total token count |
| input_tokens_details | object | Input token details |
| output_tokens_details | object | Output token details |

#### Input Tokens Details

| Field | Type | Description |
|------|------|------|
| cached_tokens | integer | Number of cached tokens hit |

#### Output Tokens Details

| Field | Type | Description |
|------|------|------|
| reasoning_tokens | integer | Tokens used in thinking mode |

### Stream Response

When `stream=true`, returns SSE format streaming data:

```
data: {"type":"response.output_item.added","item":{"type":"message","id":"msg-xyz789","status":"in_progress","role":"assistant"}}

data: {"type":"response.output_item.content_part.added","item_id":"msg-xyz789","output_index":0,"content_index":0,"part":{"type":"text"}}

data: {"type":"response.output_item.content_part.delta","item_id":"msg-xyz789","output_index":0,"content_index":0,"delta":"Hello"}

data: {"type":"response.output_item.content_part.delta","item_id":"msg-xyz789","output_index":0,"content_index":0,"delta":"!"}

data: {"type":"response.output_item.done","item":{"type":"message","id":"msg-xyz789","status":"completed","role":"assistant","content":[{"type":"text","text":"Hello!"}]}}

data: {"type":"response.done","response":{"id":"resp-abc123","object":"response","created_at":1699012345,"model":"ep-20241231-abc123","status":"completed","usage":{"input_tokens":10,"output_tokens":2,"total_tokens":12}}}

data: [DONE]
```

## Features

### Automatic Caching

By passing the `previous_response_id` parameter, you can enable automatic caching, which automatically caches and reuses previous conversation context:

```json
{
  "model": "ep-20241231-abc123",
  "input": [
    {"role": "user", "content": "Continue from our previous discussion"}
  ],
  "previous_response_id": "resp-previous-123"
}
```

### Prefix Caching

Enable prefix caching to cache common prefix portions of input, suitable for scenarios with large amounts of shared prefix content:

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

### Thinking Mode

Enable thinking mode to allow the model to think more deeply before generating responses:

```json
{
  "model": "ep-20241231-abc123",
  "input": [...],
  "thinking": {
    "type": "enabled"
  }
}
```

## Examples

### Basic Request Example

```bash
curl -X POST https://your-domain.com/api/v3/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "ep-20241231-abc123",
    "input": [
      {
        "role": "user",
        "content": "Hello, please introduce yourself"
      }
    ],
    "max_output_tokens": 1000
  }'
```

### Request with Caching Example

```bash
curl -X POST https://your-domain.com/api/v3/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "ep-20241231-abc123",
    "input": [
      {
        "role": "user",
        "content": "Continue from our previous topic"
      }
    ],
    "previous_response_id": "resp-abc123",
    "caching": {
      "type": "enabled",
      "prefix": true
    }
  }'
```

### Streaming Request Example

```bash
curl -X POST https://your-domain.com/api/v3/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "ep-20241231-abc123",
    "input": [
      {
        "role": "user",
        "content": "Write a short story"
      }
    ],
    "stream": true
  }'
```

### Python Example

```python
import requests
import json

url = "https://your-domain.com/api/v3/responses"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_API_TOKEN"
}

# Non-streaming request
data = {
    "model": "ep-20241231-abc123",
    "input": [
        {
            "role": "user",
            "content": "Hello, please introduce yourself"
        }
    ],
    "max_output_tokens": 1000,
    "temperature": 0.7
}

response = requests.post(url, headers=headers, json=data)
result = response.json()
print(result)

# Streaming request
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

## Billing

- Input tokens are billed at model pricing
- Output tokens are billed at model pricing
- Cached tokens (`cached_tokens`) are billed at cache pricing (typically 10% of normal price)
- Thinking mode tokens (`reasoning_tokens`) are billed at output token pricing
- Supports tiered pricing, automatically applying different price tiers based on input token count

## Error Handling

When a request fails, the response contains error information:

```json
{
  "error": {
    "message": "Invalid request: model is required",
    "type": "invalid_request_error",
    "code": "bad_request_body"
  }
}
```

Common error codes:

| Error Code | Description |
|--------|------|
| bad_request_body | Invalid request body format |
| invalid_model | Invalid model ID |
| rate_limit_exceeded | Rate limit exceeded |
| insufficient_quota | Insufficient quota |
| upstream_error | Upstream service error |

## References

- [BytePlus ModelArk Official Documentation](https://docs.byteplus.com/en/docs/ModelArk/Create_model_request)
- [ByteDance Volcano Engine API Documentation](https://www.volcengine.com/docs/82379)
