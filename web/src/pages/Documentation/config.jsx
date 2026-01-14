import React from 'react';
import { IconBookStroked, IconCode, IconCodeStroked, IconList, IconSend, IconComment } from '@douyinfe/semi-icons';

import overviewContentZh from './content/overview.md?raw';
import overviewContentEn from './content/overview.en.md?raw';
import openaiChatContentZh from './content/openai-chat.md?raw';
import openaiChatContentEn from './content/openai-chat.en.md?raw';
import openaiResponsesContentZh from './content/openai-responses.md?raw';
import openaiResponsesContentEn from './content/openai-responses.en.md?raw';
import claudeMessagesContentZh from './content/claude-messages.md?raw';
import claudeMessagesContentEn from './content/claude-messages.en.md?raw';
import examplesContentZh from './content/examples.md?raw';
import examplesContentEn from './content/examples.en.md?raw';
import referenceContentZh from './content/reference.md?raw';
import referenceContentEn from './content/reference.en.md?raw';
import openaiImagesContentZh from './content/openai-images.md?raw';
import openaiImagesContentEn from './content/openai-images.en.md?raw';
import videoGenerationsContentZh from './content/video-generations.md?raw';
import videoGenerationsContentEn from './content/video-generations.en.md?raw';
import videoGenerationsStatusContentZh from './content/video-generations-status.md?raw';
import videoGenerationsStatusContentEn from './content/video-generations-status.en.md?raw';
import klingMotionControlContentZh from './content/kling-motion-control.md?raw';
import klingMotionControlContentEn from './content/kling-motion-control.en.md?raw';
import openaiTtsContentZh from './content/openai-tts.md?raw';
import openaiTtsContentEn from './content/openai-tts.en.md?raw';
import openaiTranscriptionsContentZh from './content/openai-transcriptions.md?raw';
import openaiTranscriptionsContentEn from './content/openai-transcriptions.en.md?raw';
import openaiTranslationsContentZh from './content/openai-translations.md?raw';
import openaiTranslationsContentEn from './content/openai-translations.en.md?raw';
import geminiNativeContentZh from './content/gemini-native.md?raw';
import geminiNativeContentEn from './content/gemini-native.en.md?raw';

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
    key: 'claude-messages',
    title: 'doc.claudeMessages.title',
    description: 'doc.claudeMessages.desc',
    icon: <IconComment />,
    path: '/docs/claude-messages',
    content: {
      zh: claudeMessagesContentZh,
      en: claudeMessagesContentEn
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
  },
  {
    key: 'openai-images',
    title: 'doc.openaiImages.title',
    description: 'doc.openaiImages.desc',
    icon: <IconSend />,
    path: '/docs/openai-images',
    content: {
      zh: openaiImagesContentZh,
      en: openaiImagesContentEn
    }
  },
  {
    key: 'video-generations',
    title: 'doc.videoGenerations.title',
    description: 'doc.videoGenerations.desc',
    icon: <IconSend />,
    path: '/docs/video-generations',
    content: {
      zh: videoGenerationsContentZh,
      en: videoGenerationsContentEn
    }
  },
  {
    key: 'video-generations-status',
    title: 'doc.videoGenerationsStatus.title',
    description: 'doc.videoGenerationsStatus.desc',
    icon: <IconSend />,
    path: '/docs/video-generations-status',
    content: {
      zh: videoGenerationsStatusContentZh,
      en: videoGenerationsStatusContentEn
    }
  },
  {
    key: 'kling-motion-control',
    title: 'doc.klingMotionControl.title',
    description: 'doc.klingMotionControl.desc',
    icon: <IconSend />,
    path: '/docs/kling-motion-control',
    content: {
      zh: klingMotionControlContentZh,
      en: klingMotionControlContentEn
    }
  },
  {
    key: 'openai-tts',
    title: 'doc.openaiTts.title',
    description: 'doc.openaiTts.desc',
    icon: <IconSend />,
    path: '/docs/openai-tts',
    content: {
      zh: openaiTtsContentZh,
      en: openaiTtsContentEn
    }
  },
  {
    key: 'openai-transcriptions',
    title: 'doc.openaiTranscriptions.title',
    description: 'doc.openaiTranscriptions.desc',
    icon: <IconSend />,
    path: '/docs/openai-transcriptions',
    content: {
      zh: openaiTranscriptionsContentZh,
      en: openaiTranscriptionsContentEn
    }
  },
  {
    key: 'openai-translations',
    title: 'doc.openaiTranslations.title',
    description: 'doc.openaiTranslations.desc',
    icon: <IconSend />,
    path: '/docs/openai-translations',
    content: {
      zh: openaiTranslationsContentZh,
      en: openaiTranslationsContentEn
    }
  },
  {
    key: 'gemini-native',
    title: 'doc.geminiNative.title',
    description: 'doc.geminiNative.desc',
    icon: <IconSend />,
    path: '/docs/gemini-native',
    content: {
      zh: geminiNativeContentZh,
      en: geminiNativeContentEn
    }
  }
];
