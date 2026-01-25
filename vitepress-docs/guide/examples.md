# 代码示例

本页面提供了各种编程语言调用 EZmodel API 的示例代码。

## Python 示例

### 安装 SDK

```bash
pip install openai
```

### 基础聊天

```python
from openai import OpenAI

# 初始化客户端
client = OpenAI(
    api_key="YOUR_API_TOKEN",
    base_url="https://ezmodel.cloud/v1"
)

# 基础聊天
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)
```

### 流式响应

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_TOKEN",
    base_url="https://ezmodel.cloud/v1"
)

stream = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "写一首诗"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="")
```

### 图像生成

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_TOKEN",
    base_url="https://ezmodel.cloud/v1"
)

response = client.images.generate(
    model="dall-e-3",
    prompt="一只在太空中漫步的可爱猫咪",
    size="1024x1024",
    quality="standard",
    n=1,
)

print(response.data[0].url)
```

### 工具调用

```python
from openai import OpenAI
import json

client = OpenAI(
    api_key="YOUR_API_TOKEN",
    base_url="https://ezmodel.cloud/v1"
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市的天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称"
                    }
                },
                "required": ["city"]
            }
        }
    }
]

response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "北京今天天气怎么样？"}],
    tools=tools,
    tool_choice="auto"
)

print(response.choices[0].message)
```

## JavaScript 示例

### 安装 SDK

```bash
npm install openai
```

### 基础聊天

```javascript
import OpenAI from 'openai';

const openai = new OpenAI({
  apiKey: 'YOUR_API_TOKEN',
  baseURL: 'https://ezmodel.cloud/v1',
});

async function chat() {
  const completion = await openai.chat.completions.create({
    messages: [{ role: 'user', content: 'Hello!' }],
    model: 'gpt-4',
  });

  console.log(completion.choices[0].message.content);
}

chat();
```

### 流式响应

```javascript
import OpenAI from 'openai';

const openai = new OpenAI({
  apiKey: 'YOUR_API_TOKEN',
  baseURL: 'https://ezmodel.cloud/v1',
});

async function streamingChat() {
  const stream = await openai.chat.completions.create({
    model: 'gpt-4',
    messages: [{ role: 'user', content: '写一首诗' }],
    stream: true,
  });

  for await (const chunk of stream) {
    process.stdout.write(chunk.choices[0]?.delta?.content || '');
  }
}

streamingChat();
```

### 在浏览器中使用

```javascript
import OpenAI from 'openai';

const openai = new OpenAI({
  apiKey: 'YOUR_API_TOKEN',
  baseURL: 'https://ezmodel.cloud/v1',
  dangerouslyAllowBrowser: true // 仅用于开发环境
});

const completion = await openai.chat.completions.create({
  messages: [{ role: 'user', content: 'Hello!' }],
  model: 'gpt-4',
});

console.log(completion.choices[0].message.content);
```

::: warning 安全提示
不要在生产环境的前端代码中暴露 API 密钥。建议通过后端代理调用 API。
:::

## cURL 示例

### 基础聊天

```bash
curl https://ezmodel.cloud/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

### 流式响应

```bash
curl https://ezmodel.cloud/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "写一首诗"}],
    "stream": true
  }'
```

### 图像生成

```bash
curl https://ezmodel.cloud/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "dall-e-3",
    "prompt": "一只在太空中漫步的可爱猫咪",
    "n": 1,
    "size": "1024x1024"
  }'
```

## 第三方库集成

### LangChain (Python)

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gpt-4",
    api_key="YOUR_API_TOKEN",
    base_url="https://ezmodel.cloud/v1"
)

response = llm.invoke("Hello!")
print(response.content)
```

### LangChain (JavaScript)

```javascript
import { ChatOpenAI } from "@langchain/openai";

const model = new ChatOpenAI({
  modelName: "gpt-4",
  openAIApiKey: "YOUR_API_TOKEN",
  configuration: {
    baseURL: "https://ezmodel.cloud/v1"
  }
});

const response = await model.invoke("Hello!");
console.log(response.content);
```
