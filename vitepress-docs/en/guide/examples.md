# Code Examples

## Python Example

```python
import openai

# Initialize client
client = openai.OpenAI(
    api_key="YOUR_API_TOKEN",
    base_url="https://ezmodel.cloud/v1"
)

# Basic chat
response = client.chat.completions.create(
    model="gpt-5.1",
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)

# Streaming response
stream = client.chat.completions.create(
    model="gpt-5.1",
    messages=[{"role": "user", "content": "Write a poem"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="")
```

## JavaScript Example

```javascript
import OpenAI from 'openai';

const openai = new OpenAI({
  apiKey: 'YOUR_API_TOKEN',
  baseURL: 'https://ezmodel.cloud/v1',
  dangerouslyAllowBrowser: true
});

// Basic chat
async function chat() {
  const completion = await openai.chat.completions.create({
    messages: [{ role: 'user', content: 'Hello!' }],
    model: 'gpt-5.1',
  });

  console.log(completion.choices[0].message.content);
}

// Streaming response
async function streamingChat() {
  const stream = await openai.chat.completions.create({
    model: 'gpt-5.1',
    messages: [{ role: 'user', content: 'Write a poem' }],
    stream: true,
  });

  for await (const chunk of stream) {
    process.stdout.write(chunk.choices[0]?.delta?.content || '');
  }
}
```
