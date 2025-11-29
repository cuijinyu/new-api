import React from 'react';
import { IconBookStroked, IconCode, IconCodeStroked, IconList, IconSend } from '@douyinfe/semi-icons';

import overviewContentZh from './content/overview.md?raw';
import overviewContentEn from './content/overview.en.md?raw';
import openaiChatContentZh from './content/openai-chat.md?raw';
import openaiChatContentEn from './content/openai-chat.en.md?raw';
import openaiResponsesContentZh from './content/openai-responses.md?raw';
import openaiResponsesContentEn from './content/openai-responses.en.md?raw';
import examplesContentZh from './content/examples.md?raw';
import examplesContentEn from './content/examples.en.md?raw';
import referenceContentZh from './content/reference.md?raw';
import referenceContentEn from './content/reference.en.md?raw';

export const documentationConfig = [
  {
    key: 'overview',
    title: 'doc.overview.title',
    description: 'doc.overview.desc',
    icon: <IconCode />,
    path: '/docs/overview',
    content: {
      zh: overviewContentZh,
      en: overviewContentEn
    }
  },
  {
    key: 'openai-chat',
    title: 'doc.openaiChat.title',
    description: 'doc.openaiChat.desc',
    icon: <IconBookStroked />,
    path: '/docs/openai-chat',
    content: {
      zh: openaiChatContentZh,
      en: openaiChatContentEn
    }
  },
  {
    key: 'openai-responses',
    title: 'doc.openaiResponses.title',
    description: 'doc.openaiResponses.desc',
    icon: <IconSend />,
    path: '/docs/openai-responses',
    content: {
      zh: openaiResponsesContentZh,
      en: openaiResponsesContentEn
    }
  },
  {
    key: 'examples',
    title: 'doc.examples.title',
    description: 'doc.examples.desc',
    icon: <IconCodeStroked />,
    path: '/docs/examples',
    content: {
      zh: examplesContentZh,
      en: examplesContentEn
    }
  },
  {
    key: 'reference',
    title: 'doc.reference.title',
    description: 'doc.reference.desc',
    icon: <IconList />,
    path: '/docs/reference',
    content: {
      zh: referenceContentZh,
      en: referenceContentEn
    }
  }
];
