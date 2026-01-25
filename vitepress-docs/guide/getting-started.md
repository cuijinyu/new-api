# 快速开始

EZmodel API 提供了完整的 RESTful API 接口，支持与 OpenAI API 兼容的调用方式。

## API 域名

```
https://ezmodel.cloud/
```

## 认证方式

### Bearer Token 认证

所有 API 请求都需要在 Header 中携带认证信息：

```http
Authorization: Bearer YOUR_API_TOKEN
```

::: tip 获取 API Token
登录 [EZmodel 控制台](https://ezmodel.cloud) 后，在「令牌管理」页面创建新的 API Token。
:::

## 核心接口

### 1. 聊天完成接口

与 OpenAI API 完全兼容：

```http
POST /v1/chat/completions
Content-Type: application/json
Authorization: Bearer YOUR_TOKEN

{
  "model": "gpt-4",
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

| 错误码 | 说明 |
|--------|------|
| `401` | 认证失败，无效的 API 密钥 |
| `429` | 请求频率限制 |
| `500` | 服务器内部错误 |
| `503` | 服务不可用 |

### 错误响应格式

```json
{
  "error": {
    "message": "错误描述信息",
    "type": "错误类型",
    "param": "相关参数",
    "code": "错误代码"
  }
}
```

## 限制说明

| 限制项 | 说明 |
|--------|------|
| 请求频率 | 根据账户等级限制 |
| 单次请求最大 Token 数 | 根据模型限制 |
| 并发连接数 | 根据账户等级限制 |
| 响应超时时间 | 30秒 |

## 下一步

- 查看 [代码示例](/guide/examples) 了解各语言的使用方式
- 阅读 [API 参考](/guide/reference) 了解完整的接口文档
- 探索 [聊天 API](/api/chat/openai-chat) 了解聊天接口的详细参数
