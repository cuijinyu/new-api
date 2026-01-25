---
layout: home

hero:
  name: "EZmodel API"
  text: "AI Model Aggregation Platform"
  tagline: OpenAI API Compatible, One-stop Access to Mainstream AI Models
  image:
    src: /logo.jpg
    alt: EZmodel
  actions:
    - theme: brand
      text: Get Started
      link: /en/guide/getting-started
    - theme: alt
      text: API Reference
      link: /en/guide/reference

features:
  - icon: 🚀
    title: OpenAI Compatible
    details: Fully compatible with OpenAI API format, switch without code changes
  - icon: 🤖
    title: Multi-Model Support
    details: Support GPT, Claude, Gemini and more LLMs, plus image, video, audio generation
  - icon: 🎬
    title: Video Generation
    details: Integrate Kling, Sora and other advanced video models, text-to-video, image-to-video
  - icon: 🔒
    title: Secure & Reliable
    details: Enterprise-grade security, API key management, usage statistics, rate limiting
  - icon: 💰
    title: Flexible Pricing
    details: Pay-as-you-go, prepaid and postpaid options, transparent pricing
  - icon: 📊
    title: Real-time Monitoring
    details: Complete Dashboard, real-time API calls and account balance
---

## Quick Start

### Install SDK

::: code-group

```bash [Python]
pip install openai
```

```bash [Node.js]
npm install openai
```

:::

### Send Your First Request

::: code-group

```python [Python]
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://ezmodel.cloud/v1"
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
  baseURL: 'https://ezmodel.cloud/v1'
});

const response = await openai.chat.completions.create({
  model: 'gpt-4',
  messages: [{ role: 'user', content: 'Hello!' }]
});

console.log(response.choices[0].message.content);
```

:::

## Supported Models

| Type | Models | Description |
|------|--------|-------------|
| Chat | GPT-4, GPT-3.5, Claude 3, Gemini | Multi-turn conversation, tool calls, streaming |
| Image | DALL-E 3, DALL-E 2 | Text-to-image, image editing |
| Video | Kling, Sora | Text-to-video, image-to-video, video extension |
| Audio | Whisper, TTS | Speech recognition, text-to-speech |

## Why EZmodel?

- **Unified API** - One API key to access all models
- **Complete Documentation** - Detailed API docs and code examples
- **Technical Support** - Professional technical team support
