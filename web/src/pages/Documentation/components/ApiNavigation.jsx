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

import React, { useState } from 'react';
import { Card, Nav, Typography, Button } from '@douyinfe/semi-ui';
import { IconBookStroked, IconApiStroked, IconCodeStroked, IconListStroked } from '@douyinfe/semi-icons';

const { Title, Text } = Typography;

const ApiNavigation = ({ activeDoc, onDocChange }) => {
  const docs = [
    {
      key: 'overview',
      title: 'API 概览',
      description: '快速了解 New API 的核心功能和接口',
      icon: <IconApiStroked />,
      path: '/documentation'
    },
    {
      key: 'openai-chat',
      title: 'OpenAI Chat API',
      description: '完全兼容 OpenAI 的聊天补全接口，支持工具调用、流式响应等',
      icon: <IconBookStroked />,
      path: '/documentation/openai-chat-api'
    },
    {
      key: 'examples',
      title: '代码示例',
      description: '各种编程语言的 SDK 和示例代码',
      icon: <IconCodeStroked />,
      path: '/documentation/examples'
    },
    {
      key: 'reference',
      title: '参考文档',
      description: '完整的 API 参数和响应格式参考',
      icon: <IconListStroked />,
      path: '/documentation/reference'
    }
  ];

  return (
    <Card
      className="mb-8"
      bodyStyle={{ padding: '24px' }}
    >
      <div className="mb-6">
        <Title heading={4} className="mb-2">
          📚 API 文档导航
        </Title>
        <Text type="secondary" size="small">
          选择您想要查看的 API 文档部分
        </Text>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {docs.map((doc) => (
          <Card
            key={doc.key}
            className={`cursor-pointer transition-all duration-200 hover:shadow-md ${
              activeDoc === doc.key ? 'border-blue-500 bg-blue-50' : ''
            }`}
            bodyStyle={{ padding: '16px' }}
            onClick={() => onDocChange && onDocChange(doc.key)}
          >
            <div className="flex items-start space-x-3">
              <div className="mt-1 text-blue-500">
                {doc.icon}
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <Title heading={6} className="mb-1">
                    {doc.title}
                  </Title>
                  {activeDoc === doc.key && (
                    <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                  )}
                </div>
                <Text type="secondary" size="small">
                  {doc.description}
                </Text>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <div className="mt-6 pt-6 border-t border-gray-200">
        <div className="flex items-center justify-between">
          <Text type="secondary" size="small">
            需要其他帮助？
          </Text>
          <div className="space-x-3">
            <Button
              size="small"
              type="tertiary"
              onClick={() => window.open('https://github.com/QuantumNous/one-api', '_blank')}
            >
              GitHub
            </Button>
            <Button
              size="small"
              type="tertiary"
              onClick={() => window.open('https://discord.gg/quantumnous', '_blank')}
            >
              Discord
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
};

export default ApiNavigation;