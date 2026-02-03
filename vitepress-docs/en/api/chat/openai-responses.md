# OpenAI Responses API

## Overview

Responses API provides a standardized interface to create model responses. This interface follows OpenAI's response format specification, supporting streaming and non-streaming outputs.

---

## Interface Details

### Create Response

**Endpoint:** `POST /v1/responses`

**Description:** Generate model response based on provided parameters (like Prompt or Messages).

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

### Request Parameters

#### Header Parameters

| Parameter | Type | Required | Description | Example |
|--------|------|------|------|------|
| Authorization | string | Yes | Bearer Token Authentication | Bearer sk-xxx... |
| Content-Type | string | Yes | Content Type | application/json |

#### Body Parameters

| Parameter | Type | Required | Default | Description |
|--------|------|------|--------|------|
| model | string | Yes | - | Model ID |
| input | array | Yes | - | Input content, message list |
| instructions | string | No | - | System instructions |
| temperature | number | No | 1 | Sampling temperature |
| max_output_tokens | integer | No | - | Max output tokens |
| stream | boolean | No | false | Stream response |
| previous_response_id | string | No | - | Previous response ID (for caching) |
| extra_body | object | No | - | Vendor-specific parameters |

#### extra_body Parameter (Vendor Extensions)

The `extra_body` parameter is used to pass vendor-specific extension parameters. When using the OpenAI SDK to call models from different vendors, you can use this parameter to pass vendor-specific configurations.

##### BytePlus/ByteDance Model Extensions

When calling BytePlus/ByteDance models (such as Seed series), the following extension parameters are supported:

| Parameter | Type | Description |
|--------|------|------|
| caching | object | Caching configuration |
| caching.type | string | Cache type: `enabled` or `disabled` |
| caching.prefix | boolean | Whether to enable prefix caching |
| thinking | object | Thinking mode configuration |
| thinking.type | string | Thinking mode: `enabled` or `disabled` |

---

### Response Format (OpenAI Format)

Responses API returns standard OpenAI response format object.

#### Chat Completion Object

```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "gpt-5.1",
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

#### Field Description

| Field | Type | Description |
|------|------|------|
| id | string | Unique identifier for the response |
| object | string | Object type, always "chat.completion" |
| created | integer | Creation Unix timestamp |
| model | string | Model used for generation |
| choices | array | List of response choices |
| usage | object | Token usage statistics |

#### Chunk Object (Streaming)

When `stream=true`, returns streaming data chunks.

```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion.chunk",
  "created": 1694268190,
  "model": "gpt-5.1",
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

---

## Examples

### Request Example

```bash
curl -X POST https://ezmodel.cloud/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "gpt-5.1",
    "messages": [
      {
        "role": "user",
        "content": "Hello!"
      }
    ]
  }'
```

### Response Example

```json
{
  "id": "chatcmpl-888",
  "object": "chat.completion",
  "created": 1699012345,
  "model": "gpt-5.1",
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

---

## Vendor-Specific Features

### BytePlus/ByteDance Caching

BytePlus Seed series models support caching through the `extra_body` parameter, which can significantly reduce token consumption and response latency for repeated contexts.

#### Prefix Caching

Prefix caching is suitable for scenarios with large amounts of identical prefix content, such as fixed system prompts. Input content must be at least 256 tokens to create a cache.

```python
from openai import OpenAI

client = OpenAI(
    base_url='http://your-api-server/v1',
    api_key='your-api-key',
)

# First request: Enable prefix caching
response = client.responses.create(
    model="seed-1-6-250915",
    input=[
        {
            "role": "system",
            "content": "You are a literary analysis assistant. Answer concisely and clearly. Here is an excerpt from The Gift of the Magi...(long text)"
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

#### Session Caching

Use the `previous_response_id` parameter to reuse context cache from previous conversations:

```python
# Second request: Use previous_response_id to leverage cache
second_response = client.responses.create(
    model="seed-1-6-250915",
    previous_response_id=response.id,
    input=[
        {"role": "user", "content": "Briefly summarize the story in 5 bullet points."}
    ],
    extra_body={
        "caching": {"type": "enabled"},
        "thinking": {"type": "disabled"}
    }
)

# Check cache hit
if second_response.usage.input_tokens_details:
    cached_tokens = second_response.usage.input_tokens_details.cached_tokens
    print(f"Cached tokens: {cached_tokens}")
```

#### Thinking Mode

Thinking mode allows the model to think more deeply before generating responses, suitable for complex reasoning tasks:

```python
# Enable thinking mode
response = client.responses.create(
    model="seed-1-6-250915",
    input=[
        {"role": "user", "content": "Please analyze the solution to this math problem..."}
    ],
    extra_body={
        "thinking": {"type": "enabled"}
    }
)
```

#### cURL Examples

```bash
# Enable prefix caching
curl -X POST http://your-api-server/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "seed-1-6-250915",
    "input": [
      {
        "role": "system",
        "content": "You are a literary analysis assistant..."
      },
      {
        "role": "user",
        "content": "Please analyze the theme of this text"
      }
    ],
    "extra_body": {
      "caching": {"type": "enabled", "prefix": true},
      "thinking": {"type": "disabled"}
    }
  }'
```

```bash
# Use session caching
curl -X POST http://your-api-server/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "seed-1-6-250915",
    "previous_response_id": "resp-abc123",
    "input": [
      {
        "role": "user",
        "content": "Continue the analysis above"
      }
    ],
    "extra_body": {
      "caching": {"type": "enabled"},
      "thinking": {"type": "disabled"}
    }
  }'
```

### Caching Billing

- Input tokens are billed at model pricing
- Output tokens are billed at model pricing
- Cached tokens (`cached_tokens`) are billed at cache pricing (typically 10% of normal price)
- Thinking mode tokens (`reasoning_tokens`) are billed at output token pricing

### Important Notes

1. Prefix caching requires at least 256 input tokens
2. `caching.prefix` is not supported when `max_output_tokens` is set
3. When using `previous_response_id`, it's recommended to set `caching.type = "enabled"`
4. Cache needs a short time to take effect after creation
