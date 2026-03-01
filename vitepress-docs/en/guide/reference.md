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

## Kling Video Models

### Supported Models

| Model ID | Description | Recommended Endpoint |
|----------|-------------|---------------------|
| `kling-v1` | Kling V1.0 Base | text2video / image2video |
| `kling-v1-5` | Kling V1.5 | text2video / image2video |
| `kling-v1-6` | Kling V1.6 | text2video / image2video |
| `kling-v2-1` | Kling V2.1 | text2video / image2video |
| `kling-v2-5-turbo` | Kling V2.5 Turbo | text2video / image2video |
| `kling-v2-6` | Kling V2.6 | text2video / image2video |
| `kling-video-o1` | Kling Omni V1 | omni-video |
| `kling-v3` | Kling V3.0 (Latest) | omni-video |
| `kling-v2-1-master` | Kling V2.1 Master | text2video / image2video |
| `kling-v2-master` | Kling V2 Master | text2video / image2video |

### Kling V3 New Features

`kling-v3` provides the following new capabilities via the [Omni Video](/en/kling/omni-video) endpoint:

- **Extended Duration**: 3-15 seconds (O1 supports 3-10 seconds)
- **Multi-shot Narrative**: Generate multiple consecutive shots in a single request
- **Video Editing**: Edit existing videos with text instructions via `refer_type: "base"`
- **Native Audio**: Generate synchronized audio (with multilingual lip sync)
