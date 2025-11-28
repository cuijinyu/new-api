# API 参考文档

## 接口总览

| 接口 | 方法 | 描述 |
|------|------|------|
| /v1/chat/completions | POST | 创建聊天对话 |
| /v1/models | GET | 获取模型列表 |
| /v1/usage | GET | 获取用量统计 |

## 数据模型

### Message 对象

```json
{
  "role": "user|assistant|system|tool",
  "content": "消息内容",
  "name": "发送者名称",
  "tool_calls": [...],
  "tool_call_id": "tool_call_id"
}
```

### Choice 对象

```json
{
  "index": 0,
  "message": {...},
  "finish_reason": "stop|length|tool_calls|content_filter"
}
```

### Usage 对象

```json
{
  "prompt_tokens": 100,
  "completion_tokens": 50,
  "total_tokens": 150
}
```
