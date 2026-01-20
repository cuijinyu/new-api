import React from 'react';
import { 
  IconBookStroked, 
  IconCode, 
  IconCodeStroked, 
  IconList, 
  IconSend, 
  IconComment
} from '@douyinfe/semi-icons';

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
import klingVideoContentZh from './content/kling-video.md?raw';
import klingVideoContentEn from './content/kling-video.en.md?raw';
import klingVideoStatusContentZh from './content/kling-video-status.md?raw';
import klingVideoStatusContentEn from './content/kling-video-status.en.md?raw';
import klingImageVideoContentZh from './content/kling-image-video.md?raw';
import klingImageVideoContentEn from './content/kling-image-video.en.md?raw';
import klingImageVideoStatusContentZh from './content/kling-image-video-status.md?raw';
import klingImageVideoStatusContentEn from './content/kling-image-video-status.en.md?raw';
import klingMotionControlContentZh from './content/kling-motion-control.md?raw';
import klingMotionControlContentEn from './content/kling-motion-control.en.md?raw';
import klingMultiImageVideoContentZh from './content/kling-multi-image-video.md?raw';
import klingMultiImageVideoContentEn from './content/kling-multi-image-video.en.md?raw';
import klingMultiImageVideoStatusContentZh from './content/kling-multi-image-video-status.md?raw';
import klingMultiImageVideoStatusContentEn from './content/kling-multi-image-video-status.en.md?raw';
import klingOmniVideoContentZh from './content/kling-omni-video.md?raw';
import klingOmniVideoContentEn from './content/kling-omni-video.en.md?raw';
import klingOmniVideoStatusContentZh from './content/kling-omni-video-status.md?raw';
import klingOmniVideoStatusContentEn from './content/kling-omni-video-status.en.md?raw';
import openaiTtsContentZh from './content/openai-tts.md?raw';
import openaiTtsContentEn from './content/openai-tts.en.md?raw';
import openaiTranscriptionsContentZh from './content/openai-transcriptions.md?raw';
import openaiTranscriptionsContentEn from './content/openai-transcriptions.en.md?raw';
import openaiTranslationsContentZh from './content/openai-translations.md?raw';
import openaiTranslationsContentEn from './content/openai-translations.en.md?raw';
import geminiNativeContentZh from './content/gemini-native.md?raw';
import geminiNativeContentEn from './content/gemini-native.en.md?raw';
import soraVideosContentZh from './content/sora-videos.md?raw';
import soraVideosContentEn from './content/sora-videos.en.md?raw';
import soraVideosStatusContentZh from './content/sora-videos-status.md?raw';
import soraVideosStatusContentEn from './content/sora-videos-status.en.md?raw';
import soraVideosContentContentZh from './content/sora-videos-content.md?raw';
import soraVideosContentContentEn from './content/sora-videos-content.en.md?raw';

export const documentationConfig = [
  {
    key: 'overview',
    title: 'doc.overview.title',
    description: 'doc.overview.desc',
    icon: <IconCode />,
    path: '/docs/overview',
    category: 'getting-started',
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
    category: 'chat',
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
    category: 'chat',
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
    category: 'chat',
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
    category: 'getting-started',
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
    category: 'getting-started',
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
    category: 'image',
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
    category: 'video',
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
    category: 'video',
    content: {
      zh: videoGenerationsStatusContentZh,
      en: videoGenerationsStatusContentEn
    }
  },
  {
    key: 'kling-video',
    title: 'doc.klingVideo.title',
    description: 'doc.klingVideo.desc',
    icon: <IconSend />,
    path: '/docs/kling-video',
    category: 'video',
    content: {
      zh: klingVideoContentZh,
      en: klingVideoContentEn
    }
  },
  {
    key: 'kling-video-status',
    title: 'doc.klingVideoStatus.title',
    description: 'doc.klingVideoStatus.desc',
    icon: <IconSend />,
    path: '/docs/kling-video-status',
    category: 'video',
    content: {
      zh: klingVideoStatusContentZh,
      en: klingVideoStatusContentEn
    }
  },
  {
    key: 'kling-image-video',
    title: 'doc.klingImageVideo.title',
    description: 'doc.klingImageVideo.desc',
    icon: <IconSend />,
    path: '/docs/kling-image-video',
    category: 'video',
    content: {
      zh: klingImageVideoContentZh,
      en: klingImageVideoContentEn
    }
  },
  {
    key: 'kling-image-video-status',
    title: 'doc.klingImageVideoStatus.title',
    description: 'doc.klingImageVideoStatus.desc',
    icon: <IconSend />,
    path: '/docs/kling-image-video-status',
    category: 'video',
    content: {
      zh: klingImageVideoStatusContentZh,
      en: klingImageVideoStatusContentEn
    }
  },
  {
    key: 'kling-motion-control',
    title: 'doc.klingMotionControl.title',
    description: 'doc.klingMotionControl.desc',
    icon: <IconSend />,
    path: '/docs/kling-motion-control',
    category: 'video',
    content: {
      zh: klingMotionControlContentZh,
      en: klingMotionControlContentEn
    }
  },
  {
    key: 'kling-multi-image-video',
    title: 'doc.klingMultiImageVideo.title',
    description: 'doc.klingMultiImageVideo.desc',
    icon: <IconSend />,
    path: '/docs/kling-multi-image-video',
    category: 'video',
    content: {
      zh: klingMultiImageVideoContentZh,
      en: klingMultiImageVideoContentEn
    }
  },
  {
    key: 'kling-multi-image-video-status',
    title: 'doc.klingMultiImageVideoStatus.title',
    description: 'doc.klingMultiImageVideoStatus.desc',
    icon: <IconSend />,
    path: '/docs/kling-multi-image-video-status',
    category: 'video',
    content: {
      zh: klingMultiImageVideoStatusContentZh,
      en: klingMultiImageVideoStatusContentEn
    }
  },
  {
    key: 'kling-omni-video',
    title: 'doc.klingOmniVideo.title',
    description: 'doc.klingOmniVideo.desc',
    icon: <IconSend />,
    path: '/docs/kling-omni-video',
    category: 'video',
    content: {
      zh: klingOmniVideoContentZh,
      en: klingOmniVideoContentEn
    }
  },
  {
    key: 'kling-omni-video-status',
    title: 'doc.klingOmniVideoStatus.title',
    description: 'doc.klingOmniVideoStatus.desc',
    icon: <IconSend />,
    path: '/docs/kling-omni-video-status',
    category: 'video',
    content: {
      zh: klingOmniVideoStatusContentZh,
      en: klingOmniVideoStatusContentEn
    }
  },
  {
    key: 'openai-tts',
    title: 'doc.openaiTts.title',
    description: 'doc.openaiTts.desc',
    icon: <IconSend />,
    path: '/docs/openai-tts',
    category: 'audio',
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
    category: 'audio',
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
    category: 'audio',
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
    category: 'chat',
    content: {
      zh: geminiNativeContentZh,
      en: geminiNativeContentEn
    }
  },
  {
    key: 'sora-videos',
    title: 'doc.soraVideos.title',
    description: 'doc.soraVideos.desc',
    icon: <IconSend />,
    path: '/docs/sora-videos',
    category: 'video',
    content: {
      zh: soraVideosContentZh,
      en: soraVideosContentEn
    }
  },
  {
    key: 'sora-videos-status',
    title: 'doc.soraVideosStatus.title',
    description: 'doc.soraVideosStatus.desc',
    icon: <IconSend />,
    path: '/docs/sora-videos-status',
    category: 'video',
    content: {
      zh: soraVideosStatusContentZh,
      en: soraVideosStatusContentEn
    }
  },
  {
    key: 'sora-videos-content',
    title: 'doc.soraVideosContent.title',
    description: 'doc.soraVideosContent.desc',
    icon: <IconSend />,
    path: '/docs/sora-videos-content',
    category: 'video',
    content: {
      zh: soraVideosContentContentZh,
      en: soraVideosContentContentEn
    }
  }
];
