---
# https://vitepress.dev/reference/default-theme-home-page
layout: home

hero:
  name: "EZmodel API"
  text: "AI 模型聚合平台"
  tagline: 兼容 OpenAI API 格式，一站式接入主流 AI 模型
  image:
    src: /logo.png
    alt: EZmodel
  actions:
    - theme: brand
      text: 快速开始
      link: /guide/getting-started
    - theme: alt
      text: API 参考
      link: /guide/reference

features:
  - icon: 🚀
    title: OpenAI 兼容
    details: 完全兼容 OpenAI API 格式，无需修改代码即可切换使用
  - icon: 🤖
    title: 多模型支持
    details: 支持 GPT、Claude、Gemini 等主流大语言模型，以及图像、视频、音频生成
  - icon: 🎬
    title: 视频生成
    details: 集成 Kling、Sora 等先进视频生成模型，支持文生视频、图生视频
  - icon: 🔒
    title: 安全可靠
    details: 企业级安全保障，支持 API 密钥管理、用量统计、频率限制
  - icon: 💰
    title: 灵活计费
    details: 按量付费，支持预付费和后付费模式，透明的价格体系
  - icon: 📊
    title: 实时监控
    details: 完善的 Dashboard，实时查看 API 调用情况和账户余额
---

<style>
:root {
  --vp-home-hero-name-color: transparent;
  --vp-home-hero-name-background: -webkit-linear-gradient(120deg, #bd34fe 30%, #41d1ff);
  --vp-home-hero-image-background-image: linear-gradient(-45deg, #bd34fe50 50%, #47caff50 50%);
  --vp-home-hero-image-filter: blur(44px);
}

@media (min-width: 640px) {
  :root {
    --vp-home-hero-image-filter: blur(56px);
  }
}

@media (min-width: 960px) {
  :root {
    --vp-home-hero-image-filter: blur(68px);
  }
}
</style>

## 快速上手

### 安装 SDK

::: code-group

```bash [Python]
pip install openai
```

```bash [Node.js]
npm install openai
```

```bash [cURL]
# 无需安装，直接使用 curl 命令
```

:::

### 发送第一个请求

::: code-group

```python [Python]
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://www.ezmodel.cloud/v1"
)

response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)
```

```javascript [Node.js]
import OpenAI from 'openai';

const openai = new OpenAI({
  apiKey: 'YOUR_API_KEY',
  baseURL: 'https://www.ezmodel.cloud/v1'
});

const response = await openai.chat.completions.create({
  model: 'gpt-4',
  messages: [{ role: 'user', content: 'Hello!' }]
});

console.log(response.choices[0].message.content);
```

```bash [cURL]
curl https://www.ezmodel.cloud/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

:::

## 支持的模型

| 类型 | 模型 | 描述 |
|------|------|------|
| 聊天 | GPT-4, GPT-3.5, Claude 3, Gemini | 支持多轮对话、工具调用、流式输出 |
| 图像 | DALL-E 3, DALL-E 2 | 文本生成图像、图像编辑 |
| 视频 | Kling, Sora | 文生视频、图生视频、视频续写 |
| 音频 | Whisper, TTS | 语音识别、文本转语音 |

## 为什么选择 EZmodel？

- **统一接口** - 一个 API 密钥访问所有模型
- **完善文档** - 详细的 API 文档和示例代码
- **技术支持** - 专业的技术团队提供支持
