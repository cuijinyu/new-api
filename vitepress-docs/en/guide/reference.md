# API Reference

## Interface Overview

| Interface | Method | Description |
|------|------|------|
| /v1/chat/completions | POST | Create chat completion |
| /v1/models | GET | Get model list |
| /v1/usage | GET | Get usage statistics |

## Data Models

### Message Object

```json
{
  "role": "user|assistant|system|tool",
  "content": "Message content",
  "name": "Sender name",
  "tool_calls": [...],
  "tool_call_id": "tool_call_id"
}
```

### Choice Object

```json
{
  "index": 0,
  "message": {...},
  "finish_reason": "stop|length|tool_calls|content_filter"
}
```

### Usage Object

```json
{
  "prompt_tokens": 100,
  "completion_tokens": 50,
  "total_tokens": 150
}
```
