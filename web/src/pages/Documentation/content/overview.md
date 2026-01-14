# API 文档

EZmodel API 提供了完整的 RESTful API 接口，支持与 OpenAI API 兼容的调用方式。

# 域名
```
https://www.ezmodel.cloud/
```

## 认证方式

### Bearer Token 认证

```http
Authorization: Bearer YOUR_API_TOKEN
```

## 核心接口

### 1. 聊天完成接口

与 OpenAI API 完全兼容：

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

### 2. 模型列表接口

获取可用的模型列表：

```http
GET /v1/models
Authorization: Bearer YOUR_TOKEN
```

### 3. 用量统计接口

获取 API 使用统计：

```http
GET /v1/usage
Authorization: Bearer YOUR_TOKEN
```

## 错误处理

### 常见错误码

- `401`: 认证失败，无效的 API 密钥
- `429`: 请求频率限制
- `500`: 服务器内部错误
- `503`: 服务不可用

## 限制说明

- 请求频率：根据账户等级限制
- 单次请求最大 Token 数：根据模型限制
- 并发连接数：根据账户等级限制
- 响应超时时间：30秒
