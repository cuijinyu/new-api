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

import React, { useState, useEffect } from 'react';
import { Card, Typography, Button, Spin, Empty } from '@douyinfe/semi-ui';
import { IconArrowLeft, IconCopy, IconDownload } from '@douyinfe/semi-icons';
import MarkdownRenderer from '../../../components/common/markdown/MarkdownRenderer';

const { Title, Text } = Typography;

const DocumentViewer = ({ docKey, onBack }) => {
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const docConfigs = {
    overview: {
      title: 'API 概览',
      content: `# API 文档

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

### 2. 模型列表接口

获取可用的模型列表：

\`\`\`http
GET /v1/models
Authorization: Bearer YOUR_TOKEN
\`\`\`

### 3. 用量统计接口

获取 API 使用统计：

\`\`\`http
GET /v1/usage
Authorization: Bearer YOUR_TOKEN
\`\`\`

## 错误处理

### 常见错误码

- \`401\`: 认证失败，无效的 API 密钥
- \`429\`: 请求频率限制
- \`500\`: 服务器内部错误
- \`503\`: 服务不可用

## 限制说明

- 请求频率：根据账户等级限制
- 单次请求最大 Token 数：根据模型限制
- 并发连接数：根据账户等级限制
- 响应超时时间：30秒`
    },
    openaiChat: {
      title: 'OpenAI Chat API',
      content: `# OpenAI Chat API

## 概述

Chat API 提供与 OpenAI Chat Completions API 完全兼容的接口，支持多轮对话、流式响应、工具调用等功能。通过对话历史创建模型响应，支持流式和非流式响应。

---

## 接口详情

### 创建聊天对话

**接口地址：** \`POST /v1/chat/completions\`

**功能描述：** 根据对话历史创建模型响应。支持流式和非流式响应。

**认证方式：** Bearer Token
\`\`\`http
Authorization: Bearer YOUR_API_TOKEN
\`\`\`

---

### 请求参数

#### Header 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| Authorization | string | 是 | Bearer Token 认证 | Bearer sk-xxx... |
| Content-Type | string | 是 | 内容类型 | application/json |

#### Body 参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 | 约束 |
|--------|------|------|--------|------|------|
| model | string | 是 | - | 模型 ID | gpt-3.5-turbo, gpt-4 等 |
| messages | array[object] | 是 | - | 对话消息列表 | 最少 1 条消息 |
| temperature | number | 否 | 1 | 采样温度 | 0 ≤ x ≤ 2 |
| top_p | number | 否 | 1 | 核采样参数 | 0 ≤ x ≤ 1 |
| n | integer | 否 | 1 | 生成数量 | ≥ 1 |
| stream | boolean | 否 | false | 是否流式响应 | - |
| max_tokens | integer | 否 | - | 最大生成 Token 数 | ≥ 0 |
| presence_penalty | number | 否 | 0 | 存在惩罚 | -2 ≤ x ≤ 2 |
| frequency_penalty | number | 否 | 0 | 频率惩罚 | -2 ≤ x ≤ 2 |

---

## 示例代码

### 1. 基础对话

#### 请求
\`\`\`bash
curl -X POST https://your-api-domain.com/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer YOUR_API_TOKEN" \\
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [
      {
        "role": "system",
        "content": "You are a helpful assistant."
      },
      {
        "role": "user",
        "content": "Hello, how are you?"
      }
    ],
    "temperature": 0.7,
    "max_tokens": 150
  }'
\`\`\`

#### 响应
\`\`\`json
{
  "id": "chatcmpl-8abcd1234efgh5678",
  "object": "chat.completion",
  "created": 1699012345,
  "model": "gpt-3.5-turbo",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! I'm doing well, thank you for asking. How can I assist you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 22,
    "completion_tokens": 18,
    "total_tokens": 40
  }
}
\`\`\`

### 2. 流式响应

#### 请求
\`\`\`bash
curl -X POST https://your-api-domain.com/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer YOUR_API_TOKEN" \\
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [
      {
        "role": "user",
        "content": "写一首关于春天的诗"
      }
    ],
    "stream": true,
    "temperature": 0.8
  }'
\`\`\`

---

## 错误处理

### 错误响应格式

\`\`\`json
{
  "error": {
    "message": "错误描述信息",
    "type": "错误类型",
    "param": "相关参数",
    "code": "错误代码"
  }
}
\`\`\`

### 常见错误码

| HTTP状态码 | 错误类型 | 说明 |
|------------|----------|------|
| 400 | invalid_request_error | 请求参数错误 |
| 401 | invalid_api_key | API 密钥无效或未提供 |
| 401 | insufficient_quota | API 配额不足 |
| 403 | access_denied | 访问被拒绝 |
| 404 | not_found | 资源不存在 |
| 429 | rate_limit_exceeded | 请求频率超限 |
| 500 | api_error | 服务器内部错误 |
| 503 | service_unavailable | 服务暂不可用 |

---

## 限制说明

### 请求限制
- **Token 限制：** 根据模型类型，通常为 4K-128K tokens
- **请求频率：** 根据账户等级限制，通常为每分钟 60-3000 次请求
- **并发连接：** 根据账户等级限制，通常为 1-10 个并发连接
- **响应超时：** 非流式请求默认超时时间 30 秒

### 最佳实践
1. **合理设置 temperature：** 创造性任务使用较高值（0.8-1.0），准确性任务使用较低值（0.1-0.3）
2. **控制 Token 使用：** 设置合适的 max_tokens 避免不必要的消耗
3. **善用系统消息：** 通过 system role 设置明确的角色和行为指导
4. **错误处理：** 始终包含适当的错误处理和重试机制
5. **流式响应：** 长文本生成时建议使用 stream=true 获得更好体验`
    },
    examples: {
      title: '代码示例',
      content: `# 代码示例

## Python 示例

\`\`\`python
import openai

# 初始化客户端
client = openai.OpenAI(
    api_key="YOUR_API_TOKEN",
    base_url="https://your-api-domain.com/v1"
)

# 基础聊天
response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)

# 流式响应
stream = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "写一首诗"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="")
\`\`\`

## JavaScript 示例

\`\`\`javascript
import OpenAI from 'openai';

const openai = new OpenAI({
  apiKey: 'YOUR_API_TOKEN',
  baseURL: 'https://your-api-domain.com/v1',
  dangerouslyAllowBrowser: true
});

// 基础聊天
async function chat() {
  const completion = await openai.chat.completions.create({
    messages: [{ role: 'user', content: 'Hello!' }],
    model: 'gpt-3.5-turbo',
  });

  console.log(completion.choices[0].message.content);
}

// 流式响应
async function streamingChat() {
  const stream = await openai.chat.completions.create({
    model: 'gpt-3.5-turbo',
    messages: [{ role: 'user', content: '写一首诗' }],
    stream: true,
  });

  for await (const chunk of stream) {
    process.stdout.write(chunk.choices[0]?.delta?.content || '');
  }
}
\`\`\``
    },
    reference: {
      title: '参考文档',
      content: `# API 参考文档

## 接口总览

| 接口 | 方法 | 描述 |
|------|------|------|
| /v1/chat/completions | POST | 创建聊天对话 |
| /v1/models | GET | 获取模型列表 |
| /v1/usage | GET | 获取用量统计 |

## 数据模型

### Message 对象

\`\`\`json
{
  "role": "user|assistant|system|tool",
  "content": "消息内容",
  "name": "发送者名称",
  "tool_calls": [...],
  "tool_call_id": "tool_call_id"
}
\`\`\`

### Choice 对象

\`\`\`json
{
  "index": 0,
  "message": {...},
  "finish_reason": "stop|length|tool_calls|content_filter"
}
\`\`\`

### Usage 对象

\`\`\`json
{
  "prompt_tokens": 100,
  "completion_tokens": 50,
  "total_tokens": 150
}
\`\`\``
    }
  };

  useEffect(() => {
    const loadContent = async () => {
      if (!docKey) return;

      const config = docConfigs[docKey];
      if (!config) {
        setError('文档不存在');
        return;
      }

      if (config.content) {
        setContent(config.content);
        return;
      }

      // 所有文档内容都已嵌入，无需额外加载
    };

    loadContent();
  }, [docKey]);

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    // 这里可以添加复制成功提示
  };

  const handleDownload = () => {
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${docKey}-documentation.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (!docKey) {
    return (
      <Card className="min-h-[400px]">
        <Empty
          image={<Empty.Image style={{ height: 150 }} />}
          title="请选择要查看的文档"
          description="从左侧导航选择您想要查看的 API 文档部分"
        />
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="min-h-[400px]">
        <div className="text-center py-8">
          <Title heading={5} className="mb-4 text-red-500">
            加载失败
          </Title>
          <Text type="secondary">{error}</Text>
          <div className="mt-6">
            <Button onClick={onBack} icon={<IconArrowLeft />}>
              返回
            </Button>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card
      className="min-h-[400px]"
      title={
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Button
              icon={<IconArrowLeft />}
              type="tertiary"
              onClick={onBack}
            />
            <Title heading={5} className="mb-0">
              {docConfigs[docKey]?.title || '文档'}
            </Title>
          </div>
          <div className="flex space-x-2">
            <Button
              icon={<IconCopy />}
              type="tertiary"
              onClick={handleCopy}
              size="small"
            >
              复制
            </Button>
            <Button
              icon={<IconDownload />}
              type="tertiary"
              onClick={handleDownload}
              size="small"
            >
              下载
            </Button>
          </div>
        </div>
      }
      bodyStyle={{ padding: 0 }}
    >
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Spin size="large" />
        </div>
      ) : (
        <div className="prose prose-lg max-w-none p-6">
          <MarkdownRenderer content={content} />
        </div>
      )}
    </Card>
  );
};

export default DocumentViewer;