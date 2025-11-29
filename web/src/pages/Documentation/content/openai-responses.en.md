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
| messages | array | Yes | - | Message list (Chat mode) |
| prompt | string | No | - | Prompt (Completion mode) |
| temperature | number | No | 1 | Sampling temperature |
| max_tokens | integer | No | - | Max generation length |
| stream | boolean | No | false | Stream response |

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
