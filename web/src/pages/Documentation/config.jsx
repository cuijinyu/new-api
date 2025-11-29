import React from 'react';
import { IconBookStroked, IconCode, IconCodeStroked, IconList, IconSend } from '@douyinfe/semi-icons';

import overviewContent from './content/overview.md?raw';
import openaiChatContent from './content/openai-chat.md?raw';
import openaiResponsesContent from './content/openai-responses.md?raw';
import examplesContent from './content/examples.md?raw';
import referenceContent from './content/reference.md?raw';

export const documentationConfig = [
  {
    key: 'overview',
    title: 'API 概览',
    description: '快速了解 New API 的核心功能和接口',
    icon: <IconCode />,
    path: '/docs/overview',
    content: overviewContent
  },
  {
    key: 'openai-chat',
    title: 'OpenAI Chat API',
    description: '完全兼容 OpenAI 的聊天补全接口，支持工具调用、流式响应等',
    icon: <IconBookStroked />,
    path: '/docs/openai-chat',
    content: openaiChatContent
  },
  {
    key: 'openai-responses',
    title: 'OpenAI Responses API',
    description: '创建模型响应的标准接口',
    icon: <IconSend />,
    path: '/docs/openai-responses',
    content: openaiResponsesContent
  },
  {
    key: 'examples',
    title: '代码示例',
    description: '各种编程语言的 SDK 和示例代码',
    icon: <IconCodeStroked />,
    path: '/docs/examples',
    content: examplesContent
  },
  {
    key: 'reference',
    title: '参考文档',
    description: '完整的 API 参数和响应格式参考',
    icon: <IconList />,
    path: '/docs/reference',
    content: referenceContent
  }
];
