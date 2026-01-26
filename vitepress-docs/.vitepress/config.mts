import { defineConfig } from 'vitepress'

// 中文侧边栏配置
const zhSidebar = [
  {
    text: '入门指南',
    collapsed: false,
    items: [
      { text: '快速开始', link: '/guide/getting-started' },
      { text: '代码示例', link: '/guide/examples' },
      { text: 'API 参考', link: '/guide/reference' },
    ]
  },
  {
    text: '聊天 API',
    collapsed: false,
    items: [
      { text: 'OpenAI Chat', link: '/api/chat/openai-chat' },
      { text: 'OpenAI Responses', link: '/api/chat/openai-responses' },
      { text: 'Claude Messages', link: '/api/chat/claude-messages' },
      { text: 'Gemini Native', link: '/api/chat/gemini-native' },
    ]
  },
  {
    text: '图像 API',
    collapsed: false,
    items: [
      { text: '图像生成', link: '/api/image/openai-images' },
      { text: '图像编辑', link: '/api/image/openai-image-edits' },
    ]
  },
  {
    text: '视频 API',
    collapsed: false,
    items: [
      { text: '创建视频', link: '/api/video/video-generations' },
      { text: '查询状态', link: '/api/video/video-generations-status' },
    ]
  },
  {
    text: '音频 API',
    collapsed: false,
    items: [
      { text: '文本转语音 (TTS)', link: '/api/audio/openai-tts' },
      { text: '语音转文本', link: '/api/audio/openai-transcriptions' },
      { text: '音频翻译', link: '/api/audio/openai-translations' },
    ]
  },
  {
    text: 'Kling 可灵视频',
    collapsed: false,
    items: [
      { text: '文生视频', link: '/kling/text2video' },
      { text: '文生视频状态查询', link: '/kling/text2video-status' },
      { text: '图生视频', link: '/kling/image2video' },
      { text: '图生视频状态查询', link: '/kling/image2video-status' },
      { text: '运动控制', link: '/kling/motion-control' },
      { text: '多图生视频', link: '/kling/multi-image-video' },
      { text: '多图生视频状态查询', link: '/kling/multi-image-video-status' },
      { text: 'Omni 全能视频', link: '/kling/omni-video' },
      { text: 'Omni 视频状态查询', link: '/kling/omni-video-status' },
      { text: '视频续写', link: '/kling/video-extend' },
      { text: '口型同步', link: '/kling/lip-sync' },
      { text: '多元素控制', link: '/kling/multi-elements' },
      { text: '语音合成 (TTS)', link: '/kling/tts' },
    ]
  },
  {
    text: 'Sora 视频',
    collapsed: false,
    items: [
      { text: '创建视频', link: '/sora/create' },
      { text: '查询状态', link: '/sora/status' },
      { text: '获取内容', link: '/sora/content' },
    ]
  },
]

// 英文侧边栏配置
const enSidebar = [
  {
    text: 'Getting Started',
    collapsed: false,
    items: [
      { text: 'Quick Start', link: '/en/guide/getting-started' },
      { text: 'Code Examples', link: '/en/guide/examples' },
      { text: 'API Reference', link: '/en/guide/reference' },
    ]
  },
  {
    text: 'Chat API',
    collapsed: false,
    items: [
      { text: 'OpenAI Chat', link: '/en/api/chat/openai-chat' },
      { text: 'OpenAI Responses', link: '/en/api/chat/openai-responses' },
      { text: 'Claude Messages', link: '/en/api/chat/claude-messages' },
      { text: 'Gemini Native', link: '/en/api/chat/gemini-native' },
    ]
  },
  {
    text: 'Image API',
    collapsed: false,
    items: [
      { text: 'Image Generation', link: '/en/api/image/openai-images' },
      { text: 'Image Editing', link: '/en/api/image/openai-image-edits' },
    ]
  },
  {
    text: 'Video API',
    collapsed: false,
    items: [
      { text: 'Create Video', link: '/en/api/video/video-generations' },
      { text: 'Query Status', link: '/en/api/video/video-generations-status' },
    ]
  },
  {
    text: 'Audio API',
    collapsed: false,
    items: [
      { text: 'Text to Speech (TTS)', link: '/en/api/audio/openai-tts' },
      { text: 'Speech to Text', link: '/en/api/audio/openai-transcriptions' },
      { text: 'Audio Translation', link: '/en/api/audio/openai-translations' },
    ]
  },
  {
    text: 'Kling Video',
    collapsed: false,
    items: [
      { text: 'Text to Video', link: '/en/kling/text2video' },
      { text: 'Text to Video Status', link: '/en/kling/text2video-status' },
      { text: 'Image to Video', link: '/en/kling/image2video' },
      { text: 'Image to Video Status', link: '/en/kling/image2video-status' },
      { text: 'Motion Control', link: '/en/kling/motion-control' },
      { text: 'Multi-Image Video', link: '/en/kling/multi-image-video' },
      { text: 'Multi-Image Video Status', link: '/en/kling/multi-image-video-status' },
      { text: 'Omni Video', link: '/en/kling/omni-video' },
      { text: 'Omni Video Status', link: '/en/kling/omni-video-status' },
      { text: 'Video Extension', link: '/en/kling/video-extend' },
      { text: 'Lip Sync', link: '/en/kling/lip-sync' },
      { text: 'Multi-Elements', link: '/en/kling/multi-elements' },
      { text: 'Text-to-Speech (TTS)', link: '/en/kling/tts' },
    ]
  },
  {
    text: 'Sora Video',
    collapsed: false,
    items: [
      { text: 'Create Video', link: '/en/sora/create' },
      { text: 'Query Status', link: '/en/sora/status' },
      { text: 'Get Content', link: '/en/sora/content' },
    ]
  },
]

// https://vitepress.dev/reference/site-config
export default defineConfig({
  title: "EZmodel API",
  description: "EZmodel API 文档 - 兼容 OpenAI 的 AI 模型聚合平台",
  
  head: [
    ['link', { rel: 'icon', href: '/favicon.ico' }],
    ['meta', { name: 'theme-color', content: '#3eaf7c' }],
    ['meta', { name: 'og:type', content: 'website' }],
    ['meta', { name: 'og:title', content: 'EZmodel API 文档' }],
    ['meta', { name: 'og:description', content: '兼容 OpenAI 的 AI 模型聚合平台' }],
  ],
  
  locales: {
    root: {
      label: '简体中文',
      lang: 'zh-CN',
    },
    en: {
      label: 'English',
      lang: 'en',
      link: '/en/',
      themeConfig: {
        nav: [
          { text: 'Home', link: '/en/' },
          { text: 'Get Started', link: '/en/guide/getting-started' },
          { 
            text: 'API Reference',
            items: [
              { text: 'Chat API', link: '/en/api/chat/openai-chat' },
              { text: 'Image API', link: '/en/api/image/openai-images' },
              { text: 'Video API', link: '/en/api/video/video-generations' },
              { text: 'Audio API', link: '/en/api/audio/openai-tts' },
            ]
          },
          { text: 'Kling Video', link: '/en/kling/text2video' },
          { text: 'Sora Video', link: '/en/sora/create' },
        ],
        sidebar: enSidebar,
        outline: { label: 'On this page' },
        docFooter: { prev: 'Previous', next: 'Next' },
        lastUpdated: { text: 'Last updated' },
        returnToTopLabel: 'Back to top',
        sidebarMenuLabel: 'Menu',
        darkModeSwitchLabel: 'Theme',
      }
    }
  },
  
  themeConfig: {
    logo: '/logo.jpg',
    siteTitle: 'EZmodel API',
    
    nav: [
      { text: '首页', link: '/' },
      { text: '快速开始', link: '/guide/getting-started' },
      { 
        text: 'API 参考',
        items: [
          { text: '聊天 API', link: '/api/chat/openai-chat' },
          { text: '图像 API', link: '/api/image/openai-images' },
          { text: '视频 API', link: '/api/video/video-generations' },
          { text: '音频 API', link: '/api/audio/openai-tts' },
        ]
      },
      { text: 'Kling 视频', link: '/kling/text2video' },
      { text: 'Sora 视频', link: '/sora/create' },
    ],

    sidebar: zhSidebar,
    
    footer: {
      message: '企业合作联系：jasonhu@ezmodel.cloud',
      copyright: 'Copyright © 2025-present EZmodel'
    },
    
    search: {
      provider: 'local',
      options: {
        locales: {
          root: {
            translations: {
              button: { buttonText: '搜索文档', buttonAriaLabel: '搜索文档' },
              modal: {
                noResultsText: '无法找到相关结果',
                resetButtonTitle: '清除查询条件',
                footer: { selectText: '选择', navigateText: '切换', closeText: '关闭' }
              }
            }
          },
          en: {
            translations: {
              button: { buttonText: 'Search', buttonAriaLabel: 'Search' },
              modal: {
                noResultsText: 'No results found',
                resetButtonTitle: 'Clear query',
                footer: { selectText: 'Select', navigateText: 'Navigate', closeText: 'Close' }
              }
            }
          }
        }
      }
    },
    
    outline: {
      label: '页面导航',
      level: [2, 3]
    },
    
    docFooter: {
      prev: '上一页',
      next: '下一页'
    },
    
    lastUpdated: {
      text: '最后更新于',
      formatOptions: {
        dateStyle: 'short',
        timeStyle: 'short'
      }
    },
    
    returnToTopLabel: '回到顶部',
    sidebarMenuLabel: '菜单',
    darkModeSwitchLabel: '主题',
    lightModeSwitchTitle: '切换到浅色模式',
    darkModeSwitchTitle: '切换到深色模式',
  },
  
  markdown: {
    lineNumbers: true,
    theme: {
      light: 'github-light',
      dark: 'github-dark'
    }
  },
})
