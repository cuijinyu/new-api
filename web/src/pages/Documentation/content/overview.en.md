# API Overview

EZmodel API provides a complete RESTful API interface, supporting calls compatible with OpenAI API.

# Domain
```
https://www.ezmodel.cloud/
```

## Authentication

### Bearer Token Authentication

```http
Authorization: Bearer YOUR_API_TOKEN
```

## Core Interfaces

### 1. Chat Completion Interface

Fully compatible with OpenAI API:

```http
POST /v1/chat/completions
Content-Type: application/json
Authorization: Bearer YOUR_TOKEN

{
  "model": "gpt-5.1",
  "messages": [
    {
      "role": "user",
      "content": "Hello, how are you?"
    }
  ],
  "temperature": 0.7,
  "max_tokens": 1000
}
```

### 2. Model List Interface

Get list of available models:

```http
GET /v1/models
Authorization: Bearer YOUR_TOKEN
```

### 3. Usage Statistics Interface

Get API usage statistics:

```http
GET /v1/usage
Authorization: Bearer YOUR_TOKEN
```

## Error Handling

### Common Error Codes

- `401`: Authentication failed, invalid API key
- `429`: Rate limit exceeded
- `500`: Internal server error
- `503`: Service unavailable

## Limits

- Request Frequency: Limited based on account level
- Max Tokens per Request: Limited based on model
- Concurrent Connections: Limited based on account level
- Response Timeout: 30 seconds
