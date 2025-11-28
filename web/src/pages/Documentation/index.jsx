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

## 📚 API 文档导航

### [📖 OpenAI Chat API 详细文档](./openai-chat-api.md)
- 完整的 Chat Completions API 规范
- 详细的参数说明和示例
- 错误处理和最佳实践
- 工具调用和函数调用指南

## 快速开始

### 认证方式

\`\`\`http
Authorization: Bearer YOUR_API_TOKEN
\`\`\`

### 基础调用示例

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

### 其他核心接口

- **模型列表：** \`GET /v1/models\` - 获取可用的模型列表
- **用量统计：** \`GET /v1/usage\` - 获取 API 使用统计

### 常见错误码

- \`401\`: 认证失败，无效的 API 密钥
- \`429\`: 请求频率限制
- \`500\`: 服务器内部错误
- \`503\`: 服务不可用

---

💡 **提示：** 查看 [OpenAI Chat API 详细文档](./openai-chat-api.md) 获取完整的接口规范、高级用法和最佳实践。`;

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