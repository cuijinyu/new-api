# 代码示例

## Python 示例

```python
import openai

# 初始化客户端
client = openai.OpenAI(
    api_key="YOUR_API_TOKEN",
    base_url="https://ezmodel.cloud/v1"
)

# 基础聊天
response = client.chat.completions.create(
    model="gpt-5.1",
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)

# 流式响应
stream = client.chat.completions.create(
    model="gpt-5.1",
    messages=[{"role": "user", "content": "写一首诗"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="")
```

## JavaScript 示例

```javascript
import OpenAI from 'openai';

const openai = new OpenAI({
  apiKey: 'YOUR_API_TOKEN',
  baseURL: 'https://ezmodel.cloud/v1',
  dangerouslyAllowBrowser: true
});

// 基础聊天
async function chat() {
  const completion = await openai.chat.completions.create({
    messages: [{ role: 'user', content: 'Hello!' }],
    model: 'gpt-5.1',
  });

  console.log(completion.choices[0].message.content);
}

// 流式响应
async function streamingChat() {
  const stream = await openai.chat.completions.create({
    model: 'gpt-5.1',
    messages: [{ role: 'user', content: '写一首诗' }],
    stream: true,
  });

  for await (const chunk of stream) {
    process.stdout.write(chunk.choices[0]?.delta?.content || '');
  }
}
```
