/*
Copyright (C) 2025 QuantumNous

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

For commercial licensing, please contact support@quantumnous.com
*/

import React from 'react';
import { Card, Typography } from '@douyinfe/semi-ui';
import { useTranslation } from 'react-i18next';
import MarkdownRenderer from '../../components/common/markdown/MarkdownRenderer';

const { Title, Text } = Typography;

const Documentation = () => {
  const { t } = useTranslation();

  const apiDocumentationContent = `# API 文档

New API 提供了完整的 RESTful API 接口，支持与 OpenAI API 兼容的调用方式。

## 认证方式

### Bearer Token 认证

\`\`\`http
Authorization: Bearer YOUR_API_TOKEN
\`\`\`

## 核心接口

### 1. 聊天完成接口

与 OpenAI API 完全兼容：

\`\`\`http
POST /v1/chat/completions
Content-Type: application/json
Authorization: Bearer YOUR_TOKEN

{
  "model": "gpt-3.5-turbo",
  "messages": [
    {
      "role": "user",
      "content": "Hello, how are you?"
    }
  ],
  "temperature": 0.7,
  "max_tokens": 1000
}
\`\`\`

**响应示例：**
\`\`\`json
{
  "id": "chatcmpl-xxxxxxxx",
  "object": "chat.completion",
  "created": 1699012345,
  "model": "gpt-3.5-turbo",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! I'm doing well, thank you for asking."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 12,
    "total_tokens": 22
  }
}
\`\`\`

### 2. 流式聊天接口

支持服务器发送事件 (SSE) 的流式响应：

\`\`\`http
POST /v1/chat/completions
Content-Type: application/json
Authorization: Bearer YOUR_TOKEN

{
  "model": "gpt-3.5-turbo",
  "messages": [
    {
      "role": "user",
      "content": "写一首诗"
    }
  ],
  "stream": true,
  "temperature": 0.7
}
\`\`\`

### 3. 模型列表接口

获取可用的模型列表：

\`\`\`http
GET /v1/models
Authorization: Bearer YOUR_TOKEN
\`\`\`

**响应示例：**
\`\`\`json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-3.5-turbo",
      "object": "model",
      "created": 1677610602,
      "owned_by": "openai"
    },
    {
      "id": "gpt-4",
      "object": "model",
      "created": 1687882411,
      "owned_by": "openai"
    }
  ]
}
\`\`\`

### 4. 用量统计接口

获取 API 使用统计：

\`\`\`http
GET /v1/usage
Authorization: Bearer YOUR_TOKEN
\`\`\`

**响应示例：**
\`\`\`json
{
  "object": "usage",
  "prompt_tokens": 1250,
  "completion_tokens": 750,
  "total_tokens": 2000,
  "cost": 0.024
}
\`\`\`

## 错误处理

### 标准错误响应格式

\`\`\`json
{
  "error": {
    "message": "Invalid API key provided",
    "type": "invalid_request_error",
    "param": "authorization",
    "code": "invalid_api_key"
  }
}
\`\`\`

### 常见错误码

- \`401\`: 认证失败，无效的 API 密钥
- \`429\`: 请求频率限制
- \`500\`: 服务器内部错误
- \`503\`: 服务不可用

## 限制说明

- 请求频率：根据账户等级限制
- 单次请求最大 Token 数：根据模型限制
- 并发连接数：根据账户等级限制
- 响应超时时间：30秒`;

  return (
    <div className="min-h-screen bg-gray-50 pt-16">
      <div className="max-w-6xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-8">
          <Title heading={1} className="mb-4">
            {t('API 文档')}
          </Title>
          <Text type="secondary" className="text-lg">
            {t('New API 接口文档和使用说明')}
          </Text>
        </div>

        <Card className="mb-8">
          <div className="prose prose-lg max-w-none">
            <MarkdownRenderer content={apiDocumentationContent} />
          </div>
        </Card>
      </div>
    </div>
  );
};

export default Documentation;