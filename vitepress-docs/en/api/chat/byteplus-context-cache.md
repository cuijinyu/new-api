# BytePlus Context Cache API

## Overview

BytePlus Context Cache API is a context caching interface provided by ByteDance's Volcano Engine, allowing users to pre-create and manage conversation context caches, significantly reducing token consumption and response latency for repeated contexts.

The API supports two caching modes:
- **Session Mode**: Suitable for continuous conversation scenarios with a single user
- **Common Prefix Mode**: Suitable for scenarios where multiple users share the same prefix content

## Interface Details

### 1. Create Context Cache

**Endpoint:** `POST /api/v3/context/create`

**Description:** Create a new context cache to cache initial message list for subsequent conversations.

**Authentication:** Bearer Token

```http
Authorization: Bearer YOUR_API_TOKEN
```

#### Request Parameters

##### Header Parameters

| Parameter | Type | Required | Description | Example |
|--------|------|------|------|------|
| Authorization | string | Yes | Bearer Token Authentication | `Bearer sk-xxx...` |
| Content-Type | string | Yes | Content Type | `application/json` |

##### Body Parameters

| Parameter | Type | Required | Default | Description |
|--------|------|------|--------|------|
| model | string | Yes | - | Inference endpoint ID |
| messages | array | Yes | - | Initial message list, conversation history to cache |
| mode | string | No | session | Cache mode: `session` or `common_prefix` |
| ttl | integer | No | 86400 | Expiration time (seconds), range [3600, 604800], default 24 hours |
| truncation_strategy | object | No | - | Truncation strategy configuration |

###### Truncation Strategy Object

| Parameter | Type | Required | Description |
|--------|------|------|------|
| type | string | Yes | Truncation strategy type, currently only supports `rolling_tokens` |
| rolling_tokens | boolean | No | Whether to automatically trim historical context to stay within token limit |

#### Response Format

```json
{
  "id": "ctx-abc123xyz789",
  "model": "ep-20241231-abc123",
  "ttl": 86400,
  "mode": "session",
  "truncation_strategy": {
    "type": "rolling_tokens",
    "rolling_tokens": true
  },
  "usage": {
    "prompt_tokens": 150,
    "completion_tokens": 0,
    "total_tokens": 150,
    "prompt_tokens_details": {
      "cached_tokens": 0
    }
  }
}
```

##### Field Description

| Field | Type | Description |
|------|------|------|
| id | string | Context cache ID (ctx-xxx), used for subsequent conversations |
| model | string | Inference endpoint ID |
| ttl | integer | Expiration time (seconds) |
| mode | string | Cache mode |
| truncation_strategy | object | Truncation strategy |
| usage | object | Token usage |

### 2. Chat with Context Cache

**Endpoint:** `POST /api/v3/context/chat/completions`

**Description:** Chat using a created context cache, only need to pass new messages, system will automatically load cached historical context.

**Authentication:** Bearer Token

```http
Authorization: Bearer YOUR_API_TOKEN
```

#### Request Parameters

##### Header Parameters

| Parameter | Type | Required | Description | Example |
|--------|------|------|------|------|
| Authorization | string | Yes | Bearer Token Authentication | `Bearer sk-xxx...` |
| Content-Type | string | Yes | Content Type | `application/json` |

##### Body Parameters

| Parameter | Type | Required | Default | Description |
|--------|------|------|--------|------|
| model | string | Yes | - | Inference endpoint ID |
| context_id | string | Yes | - | Context cache ID (ctx-xxx) |
| messages | array | Yes | - | New message list (only need to include new messages) |
| stream | boolean | No | false | Whether to stream response |
| stream_options | object | No | - | Stream response options |
| max_tokens | integer | No | - | Maximum generation tokens |
| temperature | number | No | 1.0 | Sampling temperature, range [0, 2] |
| top_p | number | No | 1.0 | Nucleus sampling probability, range [0, 1] |
| stop | string/array | No | - | Stop words |

#### Response Format

##### Non-streaming Response

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1699012345,
  "model": "ep-20241231-abc123",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Based on our previous conversation, I understand you want to..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 200,
    "completion_tokens": 50,
    "total_tokens": 250,
    "prompt_tokens_details": {
      "cached_tokens": 150
    }
  }
}
```

##### Streaming Response

When `stream=true`, returns SSE format streaming data:

```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1699012345,"model":"ep-20241231-abc123","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1699012345,"model":"ep-20241231-abc123","choices":[{"index":0,"delta":{"content":"Based"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1699012345,"model":"ep-20241231-abc123","choices":[{"index":0,"delta":{"content":" on"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1699012345,"model":"ep-20241231-abc123","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":200,"completion_tokens":50,"total_tokens":250,"prompt_tokens_details":{"cached_tokens":150}}}

data: [DONE]
```

## Use Cases

### 1. Session Mode (Single User Continuous Conversation)

Suitable for long conversation scenarios with a single user, such as customer service dialogues, tutoring, etc.

**Advantages:**
- Automatically manage conversation history
- Significantly reduce token consumption
- Reduce response latency

**Example:**

```bash
# Step 1: Create context cache
curl -X POST https://your-domain.com/api/v3/context/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "ep-20241231-abc123",
    "messages": [
      {
        "role": "system",
        "content": "You are a professional programming assistant, skilled in Python and Go."
      },
      {
        "role": "user",
        "content": "I want to learn Go concurrency programming"
      },
      {
        "role": "assistant",
        "content": "Great! Go concurrency programming is mainly implemented through goroutines and channels..."
      }
    ],
    "mode": "session",
    "ttl": 86400
  }'

# Response: {"id": "ctx-abc123", ...}

# Step 2: Continue conversation using cache
curl -X POST https://your-domain.com/api/v3/context/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "ep-20241231-abc123",
    "context_id": "ctx-abc123",
    "messages": [
      {
        "role": "user",
        "content": "Can you give me an example of goroutine?"
      }
    ]
  }'
```

### 2. Common Prefix Mode (Multi-user Shared Prefix)

Suitable for scenarios where multiple users share the same system prompts or documents, such as RAG applications, document Q&A, etc.

**Advantages:**
- Multiple users share the same cache
- Significantly reduce token consumption for repeated content
- Suitable for handling large documents or knowledge bases

**Example:**

```bash
# Step 1: Create shared prefix cache
curl -X POST https://your-domain.com/api/v3/context/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "ep-20241231-abc123",
    "messages": [
      {
        "role": "system",
        "content": "You are a professional document Q&A assistant. Here is the product documentation:\n\n[Large document content...]"
      }
    ],
    "mode": "common_prefix",
    "ttl": 604800
  }'

# Response: {"id": "ctx-shared123", ...}

# Step 2: Different users use the same cache
# User A
curl -X POST https://your-domain.com/api/v3/context/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "ep-20241231-abc123",
    "context_id": "ctx-shared123",
    "messages": [
      {
        "role": "user",
        "content": "What features does this product support?"
      }
    ]
  }'

# User B
curl -X POST https://your-domain.com/api/v3/context/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "ep-20241231-abc123",
    "context_id": "ctx-shared123",
    "messages": [
      {
        "role": "user",
        "content": "How to configure this product?"
      }
    ]
  }'
```

## Complete Examples

### Python Example

```python
import requests
import json

API_BASE = "https://your-domain.com"
API_KEY = "YOUR_API_TOKEN"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}

# 1. Create context cache
def create_context_cache(model, messages, mode="session", ttl=86400):
    url = f"{API_BASE}/api/v3/context/create"
    data = {
        "model": model,
        "messages": messages,
        "mode": mode,
        "ttl": ttl,
        "truncation_strategy": {
            "type": "rolling_tokens",
            "rolling_tokens": True
        }
    }
    
    response = requests.post(url, headers=HEADERS, json=data)
    result = response.json()
    
    if response.status_code == 200:
        print(f"✓ Context cache created: {result['id']}")
        print(f"  - Cached {result['usage']['prompt_tokens']} tokens")
        print(f"  - TTL: {result['ttl']} seconds")
        return result['id']
    else:
        print(f"✗ Creation failed: {result}")
        return None

# 2. Chat with context cache
def chat_with_context(model, context_id, messages, stream=False):
    url = f"{API_BASE}/api/v3/context/chat/completions"
    data = {
        "model": model,
        "context_id": context_id,
        "messages": messages,
        "stream": stream
    }
    
    if stream:
        response = requests.post(url, headers=HEADERS, json=data, stream=True)
        print("✓ Streaming response:")
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data_str = line[6:]
                    if data_str == '[DONE]':
                        break
                    try:
                        chunk = json.loads(data_str)
                        if 'choices' in chunk and len(chunk['choices']) > 0:
                            delta = chunk['choices'][0].get('delta', {})
                            content = delta.get('content', '')
                            if content:
                                print(content, end='', flush=True)
                    except json.JSONDecodeError:
                        pass
        print()
    else:
        response = requests.post(url, headers=HEADERS, json=data)
        result = response.json()
        
        if response.status_code == 200:
            message = result['choices'][0]['message']['content']
            usage = result['usage']
            print(f"✓ Response: {message}")
            print(f"  - Total tokens: {usage['total_tokens']}")
            print(f"  - Cache hit: {usage['prompt_tokens_details']['cached_tokens']} tokens")
            return result
        else:
            print(f"✗ Chat failed: {result}")
            return None

# Usage example
if __name__ == "__main__":
    MODEL = "ep-20241231-abc123"
    
    # Create context cache
    initial_messages = [
        {
            "role": "system",
            "content": "You are a professional AI assistant, skilled in answering technical questions."
        },
        {
            "role": "user",
            "content": "Please introduce RESTful API design principles"
        },
        {
            "role": "assistant",
            "content": "RESTful API design principles include: 1. Use HTTP methods (GET, POST, PUT, DELETE); 2. Resource-oriented URL design; 3. Stateless communication; 4. Uniform interface..."
        }
    ]
    
    context_id = create_context_cache(MODEL, initial_messages)
    
    if context_id:
        print("\n" + "="*50 + "\n")
        
        # First conversation
        chat_with_context(
            MODEL,
            context_id,
            [{"role": "user", "content": "Can you explain stateless communication in detail?"}]
        )
        
        print("\n" + "="*50 + "\n")
        
        # Second conversation (streaming)
        chat_with_context(
            MODEL,
            context_id,
            [{"role": "user", "content": "Give me an example of RESTful API"}],
            stream=True
        )
```

## Billing

### Creating Context Cache

- When creating cache for the first time, billed at normal input token pricing
- `usage.prompt_tokens` indicates the number of cached tokens

### Chatting with Context Cache

- **Cached tokens hit** (`usage.prompt_tokens_details.cached_tokens`): Billed at cache pricing, typically **10%** of normal price
- **New input tokens** (`usage.prompt_tokens - cached_tokens`): Billed at normal input pricing
- **Output tokens** (`usage.completion_tokens`): Billed at normal output pricing

### Example Calculation

Assuming model pricing:
- Input: $0.01 / 1K tokens
- Output: $0.03 / 1K tokens
- Cache: $0.001 / 1K tokens (10%)

**Scenario:**
- Cached 5000 tokens of conversation history
- New input 100 tokens
- Output 200 tokens

**Cost Calculation:**
- Cache tokens: 5000 × $0.001 / 1000 = $0.005
- New input tokens: 100 × $0.01 / 1000 = $0.001
- Output tokens: 200 × $0.03 / 1000 = $0.006
- **Total: $0.012**

Without cache, cost would be:
- Input tokens: 5100 × $0.01 / 1000 = $0.051
- Output tokens: 200 × $0.03 / 1000 = $0.006
- **Total: $0.057**

**Savings: 79%**

## Best Practices

### 1. Choose Appropriate Cache Mode

- **Session Mode**: For single-user continuous conversations, create independent cache for each user
- **Common Prefix Mode**: For multi-user shared scenarios, such as document Q&A, knowledge base queries

### 2. Set Reasonable TTL

- Short-term conversations: 3600 seconds (1 hour)
- Daily conversations: 86400 seconds (24 hours, default)
- Long-term cache: 604800 seconds (7 days, maximum)

### 3. Use Truncation Strategy

Enable `rolling_tokens` to automatically manage context length, avoiding exceeding model token limits:

```json
{
  "truncation_strategy": {
    "type": "rolling_tokens",
    "rolling_tokens": true
  }
}
```

### 4. Monitor Cache Hit Rate

Monitor cache hit status through `usage.prompt_tokens_details.cached_tokens` to optimize caching strategy.

### 5. Organize Messages Properly

Place stable, reusable content (such as system prompts, document content) in cache, pass changing content as new messages.

## Error Handling

When a request fails, the response contains error information:

```json
{
  "error": {
    "message": "Invalid context_id: context not found or expired",
    "type": "invalid_request_error",
    "code": "invalid_context_id"
  }
}
```

Common error codes:

| Error Code | Description | Solution |
|--------|------|----------|
| bad_request_body | Invalid request body format | Check JSON format and required parameters |
| invalid_model | Invalid model ID | Confirm model ID is correct |
| invalid_context_id | Invalid or expired context ID | Recreate context cache |
| context_expired | Context has expired | Recreate context cache |
| rate_limit_exceeded | Rate limit exceeded | Reduce request frequency or upgrade quota |
| insufficient_quota | Insufficient quota | Recharge or check quota usage |

## References

- [BytePlus ModelArk Context Cache Documentation](https://docs.byteplus.com/en/docs/ModelArk/1346559)
- [ByteDance Volcano Engine API Documentation](https://www.volcengine.com/docs/82379)
