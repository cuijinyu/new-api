# BytePlus Context Cache API

## 概述

BytePlus Context Cache API 是字节跳动火山引擎提供的上下文缓存接口，允许用户预先创建和管理对话上下文缓存，显著降低重复上下文的 token 消耗和响应延迟。

该 API 支持两种缓存模式：
- **Session 模式**：适用于单个用户的连续对话场景
- **Common Prefix 模式**：适用于多个用户共享相同前缀内容的场景

## 接口详情

### 1. 创建上下文缓存

**接口地址：** `POST /api/v3/context/create`

**功能描述：** 创建一个新的上下文缓存，将初始消息列表缓存起来供后续对话使用。

**认证方式：** Bearer Token

```http
Authorization: Bearer YOUR_API_TOKEN
```

#### 请求参数

##### Header 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| Authorization | string | 是 | Bearer Token 认证 | `Bearer sk-xxx...` |
| Content-Type | string | 是 | 内容类型 | `application/json` |

##### Body 参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| model | string | 是 | - | 推理接入点 ID (endpoint ID) |
| messages | array | 是 | - | 初始消息列表，需要缓存的对话历史 |
| mode | string | 否 | session | 缓存模式: `session` 或 `common_prefix` |
| ttl | integer | 否 | 86400 | 过期时间（秒），范围 [3600, 604800]，默认 24 小时 |
| truncation_strategy | object | 否 | - | 截断策略配置 |

###### Truncation Strategy 对象

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| type | string | 是 | 截断策略类型，目前仅支持 `rolling_tokens` |
| rolling_tokens | boolean | 否 | 是否自动裁剪历史上下文以保持在 token 限制内 |

#### 响应格式

```json
{
  "id": "ctx-abc123xyz789",
  "model": "ep-20241231-abc123",
  "ttl": 86400,
  "mode": "session",
  "truncation_strategy": {
    "type": "rolling_tokens",
    "rolling_tokens": true
  },
  "usage": {
    "prompt_tokens": 150,
    "completion_tokens": 0,
    "total_tokens": 150,
    "prompt_tokens_details": {
      "cached_tokens": 0
    }
  }
}
```

##### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 上下文缓存 ID (ctx-xxx)，用于后续对话 |
| model | string | 推理接入点 ID |
| ttl | integer | 过期时间（秒） |
| mode | string | 缓存模式 |
| truncation_strategy | object | 截断策略 |
| usage | object | Token 使用情况 |

### 2. 使用上下文缓存进行对话

**接口地址：** `POST /api/v3/context/chat/completions`

**功能描述：** 使用已创建的上下文缓存进行对话，只需传入新的消息即可，系统会自动加载缓存的历史上下文。

**认证方式：** Bearer Token

```http
Authorization: Bearer YOUR_API_TOKEN
```

#### 请求参数

##### Header 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| Authorization | string | 是 | Bearer Token 认证 | `Bearer sk-xxx...` |
| Content-Type | string | 是 | 内容类型 | `application/json` |

##### Body 参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| model | string | 是 | - | 推理接入点 ID (endpoint ID) |
| context_id | string | 是 | - | 上下文缓存 ID (ctx-xxx) |
| messages | array | 是 | - | 新的消息列表（只需包含新消息） |
| stream | boolean | 否 | false | 是否流式响应 |
| stream_options | object | 否 | - | 流式响应选项 |
| max_tokens | integer | 否 | - | 最大生成 token 数 |
| temperature | number | 否 | 1.0 | 采样温度，范围 [0, 2] |
| top_p | number | 否 | 1.0 | 核采样概率，范围 [0, 1] |
| stop | string/array | 否 | - | 停止词 |

#### 响应格式

##### 非流式响应

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1699012345,
  "model": "ep-20241231-abc123",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "根据之前的对话内容，我理解您想要..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 200,
    "completion_tokens": 50,
    "total_tokens": 250,
    "prompt_tokens_details": {
      "cached_tokens": 150
    }
  }
}
```

##### 流式响应

当 `stream=true` 时，返回 SSE 格式的流式数据：

```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1699012345,"model":"ep-20241231-abc123","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1699012345,"model":"ep-20241231-abc123","choices":[{"index":0,"delta":{"content":"根据"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1699012345,"model":"ep-20241231-abc123","choices":[{"index":0,"delta":{"content":"之前"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1699012345,"model":"ep-20241231-abc123","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":200,"completion_tokens":50,"total_tokens":250,"prompt_tokens_details":{"cached_tokens":150}}}

data: [DONE]
```

## 使用场景

### 1. Session 模式（单用户连续对话）

适用于单个用户的长对话场景，例如客服对话、教学辅导等。

**优势：**
- 自动管理对话历史
- 显著降低 token 消耗
- 减少响应延迟

**示例：**

```bash
# 步骤 1: 创建上下文缓存
curl -X POST https://your-domain.com/api/v3/context/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "ep-20241231-abc123",
    "messages": [
      {
        "role": "system",
        "content": "你是一个专业的编程助手，擅长 Python 和 Go 语言。"
      },
      {
        "role": "user",
        "content": "我想学习 Go 语言的并发编程"
      },
      {
        "role": "assistant",
        "content": "很好！Go 语言的并发编程主要通过 goroutine 和 channel 实现..."
      }
    ],
    "mode": "session",
    "ttl": 86400
  }'

# 响应: {"id": "ctx-abc123", ...}

# 步骤 2: 使用缓存继续对话
curl -X POST https://your-domain.com/api/v3/context/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "ep-20241231-abc123",
    "context_id": "ctx-abc123",
    "messages": [
      {
        "role": "user",
        "content": "能给我一个 goroutine 的示例吗？"
      }
    ]
  }'
```

### 2. Common Prefix 模式（多用户共享前缀）

适用于多个用户共享相同系统提示词或文档的场景，例如 RAG 应用、文档问答等。

**优势：**
- 多个用户共享同一个缓存
- 大幅降低重复内容的 token 消耗
- 适合处理大型文档或知识库

**示例：**

```bash
# 步骤 1: 创建共享前缀缓存
curl -X POST https://your-domain.com/api/v3/context/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "ep-20241231-abc123",
    "messages": [
      {
        "role": "system",
        "content": "你是一个专业的文档问答助手。以下是产品文档内容：\n\n[大量文档内容...]"
      }
    ],
    "mode": "common_prefix",
    "ttl": 604800
  }'

# 响应: {"id": "ctx-shared123", ...}

# 步骤 2: 不同用户使用同一个缓存
# 用户 A
curl -X POST https://your-domain.com/api/v3/context/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "ep-20241231-abc123",
    "context_id": "ctx-shared123",
    "messages": [
      {
        "role": "user",
        "content": "这个产品支持哪些功能？"
      }
    ]
  }'

# 用户 B
curl -X POST https://your-domain.com/api/v3/context/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{
    "model": "ep-20241231-abc123",
    "context_id": "ctx-shared123",
    "messages": [
      {
        "role": "user",
        "content": "如何配置这个产品？"
      }
    ]
  }'
```

## 完整示例

### Python 示例

```python
import requests
import json

API_BASE = "https://your-domain.com"
API_KEY = "YOUR_API_TOKEN"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}

# 1. 创建上下文缓存
def create_context_cache(model, messages, mode="session", ttl=86400):
    url = f"{API_BASE}/api/v3/context/create"
    data = {
        "model": model,
        "messages": messages,
        "mode": mode,
        "ttl": ttl,
        "truncation_strategy": {
            "type": "rolling_tokens",
            "rolling_tokens": True
        }
    }
    
    response = requests.post(url, headers=HEADERS, json=data)
    result = response.json()
    
    if response.status_code == 200:
        print(f"✓ 上下文缓存创建成功: {result['id']}")
        print(f"  - 缓存了 {result['usage']['prompt_tokens']} 个 tokens")
        print(f"  - 有效期: {result['ttl']} 秒")
        return result['id']
    else:
        print(f"✗ 创建失败: {result}")
        return None

# 2. 使用上下文缓存进行对话
def chat_with_context(model, context_id, messages, stream=False):
    url = f"{API_BASE}/api/v3/context/chat/completions"
    data = {
        "model": model,
        "context_id": context_id,
        "messages": messages,
        "stream": stream
    }
    
    if stream:
        response = requests.post(url, headers=HEADERS, json=data, stream=True)
        print("✓ 流式响应:")
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data_str = line[6:]
                    if data_str == '[DONE]':
                        break
                    try:
                        chunk = json.loads(data_str)
                        if 'choices' in chunk and len(chunk['choices']) > 0:
                            delta = chunk['choices'][0].get('delta', {})
                            content = delta.get('content', '')
                            if content:
                                print(content, end='', flush=True)
                    except json.JSONDecodeError:
                        pass
        print()
    else:
        response = requests.post(url, headers=HEADERS, json=data)
        result = response.json()
        
        if response.status_code == 200:
            message = result['choices'][0]['message']['content']
            usage = result['usage']
            print(f"✓ 响应: {message}")
            print(f"  - 总 tokens: {usage['total_tokens']}")
            print(f"  - 缓存命中: {usage['prompt_tokens_details']['cached_tokens']} tokens")
            return result
        else:
            print(f"✗ 对话失败: {result}")
            return None

# 使用示例
if __name__ == "__main__":
    MODEL = "ep-20241231-abc123"
    
    # 创建上下文缓存
    initial_messages = [
        {
            "role": "system",
            "content": "你是一个专业的 AI 助手，擅长回答技术问题。"
        },
        {
            "role": "user",
            "content": "请介绍一下 RESTful API 的设计原则"
        },
        {
            "role": "assistant",
            "content": "RESTful API 的设计原则包括：1. 使用 HTTP 方法（GET、POST、PUT、DELETE）；2. 资源导向的 URL 设计；3. 无状态通信；4. 统一的接口..."
        }
    ]
    
    context_id = create_context_cache(MODEL, initial_messages)
    
    if context_id:
        print("\n" + "="*50 + "\n")
        
        # 第一次对话
        chat_with_context(
            MODEL,
            context_id,
            [{"role": "user", "content": "能详细说说无状态通信吗？"}]
        )
        
        print("\n" + "="*50 + "\n")
        
        # 第二次对话（流式）
        chat_with_context(
            MODEL,
            context_id,
            [{"role": "user", "content": "给我一个 RESTful API 的示例"}],
            stream=True
        )
```

### JavaScript/Node.js 示例

```javascript
const axios = require('axios');

const API_BASE = 'https://your-domain.com';
const API_KEY = 'YOUR_API_TOKEN';
const HEADERS = {
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${API_KEY}`
};

// 1. 创建上下文缓存
async function createContextCache(model, messages, mode = 'session', ttl = 86400) {
  try {
    const response = await axios.post(
      `${API_BASE}/api/v3/context/create`,
      {
        model,
        messages,
        mode,
        ttl,
        truncation_strategy: {
          type: 'rolling_tokens',
          rolling_tokens: true
        }
      },
      { headers: HEADERS }
    );
    
    console.log(`✓ 上下文缓存创建成功: ${response.data.id}`);
    console.log(`  - 缓存了 ${response.data.usage.prompt_tokens} 个 tokens`);
    console.log(`  - 有效期: ${response.data.ttl} 秒`);
    
    return response.data.id;
  } catch (error) {
    console.error('✗ 创建失败:', error.response?.data || error.message);
    return null;
  }
}

// 2. 使用上下文缓存进行对话
async function chatWithContext(model, contextId, messages, stream = false) {
  try {
    const response = await axios.post(
      `${API_BASE}/api/v3/context/chat/completions`,
      {
        model,
        context_id: contextId,
        messages,
        stream
      },
      { 
        headers: HEADERS,
        responseType: stream ? 'stream' : 'json'
      }
    );
    
    if (stream) {
      console.log('✓ 流式响应:');
      response.data.on('data', (chunk) => {
        const lines = chunk.toString().split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6);
            if (dataStr === '[DONE]') break;
            try {
              const data = JSON.parse(dataStr);
              const content = data.choices?.[0]?.delta?.content;
              if (content) process.stdout.write(content);
            } catch (e) {}
          }
        }
      });
      
      return new Promise((resolve) => {
        response.data.on('end', () => {
          console.log();
          resolve();
        });
      });
    } else {
      const result = response.data;
      const message = result.choices[0].message.content;
      const usage = result.usage;
      
      console.log(`✓ 响应: ${message}`);
      console.log(`  - 总 tokens: ${usage.total_tokens}`);
      console.log(`  - 缓存命中: ${usage.prompt_tokens_details.cached_tokens} tokens`);
      
      return result;
    }
  } catch (error) {
    console.error('✗ 对话失败:', error.response?.data || error.message);
    return null;
  }
}

// 使用示例
(async () => {
  const MODEL = 'ep-20241231-abc123';
  
  // 创建上下文缓存
  const initialMessages = [
    {
      role: 'system',
      content: '你是一个专业的 AI 助手，擅长回答技术问题。'
    },
    {
      role: 'user',
      content: '请介绍一下 RESTful API 的设计原则'
    },
    {
      role: 'assistant',
      content: 'RESTful API 的设计原则包括：1. 使用 HTTP 方法（GET、POST、PUT、DELETE）；2. 资源导向的 URL 设计；3. 无状态通信；4. 统一的接口...'
    }
  ];
  
  const contextId = await createContextCache(MODEL, initialMessages);
  
  if (contextId) {
    console.log('\n' + '='.repeat(50) + '\n');
    
    // 第一次对话
    await chatWithContext(
      MODEL,
      contextId,
      [{ role: 'user', content: '能详细说说无状态通信吗？' }]
    );
    
    console.log('\n' + '='.repeat(50) + '\n');
    
    // 第二次对话（流式）
    await chatWithContext(
      MODEL,
      contextId,
      [{ role: 'user', content: '给我一个 RESTful API 的示例' }],
      true
    );
  }
})();
```

## 计费说明

### 创建上下文缓存

- 首次创建缓存时，按照正常的输入 token 价格计费
- `usage.prompt_tokens` 表示缓存的 token 数量

### 使用上下文缓存对话

- **缓存命中的 tokens**（`usage.prompt_tokens_details.cached_tokens`）：按照缓存价格计费，通常为正常价格的 **10%**
- **新输入的 tokens**（`usage.prompt_tokens - cached_tokens`）：按照正常输入价格计费
- **输出 tokens**（`usage.completion_tokens`）：按照正常输出价格计费

### 示例计算

假设模型定价为：
- 输入: $0.01 / 1K tokens
- 输出: $0.03 / 1K tokens
- 缓存: $0.001 / 1K tokens (10%)

**场景：**
- 缓存了 5000 tokens 的对话历史
- 新输入 100 tokens
- 输出 200 tokens

**费用计算：**
- 缓存 tokens: 5000 × $0.001 / 1000 = $0.005
- 新输入 tokens: 100 × $0.01 / 1000 = $0.001
- 输出 tokens: 200 × $0.03 / 1000 = $0.006
- **总计: $0.012**

如果不使用缓存，费用为：
- 输入 tokens: 5100 × $0.01 / 1000 = $0.051
- 输出 tokens: 200 × $0.03 / 1000 = $0.006
- **总计: $0.057**

**节省: 79%**

## 最佳实践

### 1. 选择合适的缓存模式

- **Session 模式**：用于单用户的连续对话，每个用户创建独立的缓存
- **Common Prefix 模式**：用于多用户共享的场景，如文档问答、知识库查询

### 2. 设置合理的 TTL

- 短期对话：3600 秒（1 小时）
- 日常对话：86400 秒（24 小时，默认）
- 长期缓存：604800 秒（7 天，最大值）

### 3. 使用截断策略

启用 `rolling_tokens` 可以自动管理上下文长度，避免超出模型的 token 限制：

```json
{
  "truncation_strategy": {
    "type": "rolling_tokens",
    "rolling_tokens": true
  }
}
```

### 4. 监控缓存命中率

通过 `usage.prompt_tokens_details.cached_tokens` 监控缓存命中情况，优化缓存策略。

### 5. 合理组织消息

将稳定的、重复使用的内容（如系统提示词、文档内容）放在缓存中，将变化的内容作为新消息传入。

## 错误处理

当请求失败时，响应会包含错误信息：

```json
{
  "error": {
    "message": "Invalid context_id: context not found or expired",
    "type": "invalid_request_error",
    "code": "invalid_context_id"
  }
}
```

常见错误码：

| 错误码 | 说明 | 解决方案 |
|--------|------|----------|
| bad_request_body | 请求体格式错误 | 检查 JSON 格式和必填参数 |
| invalid_model | 无效的模型 ID | 确认模型 ID 正确 |
| invalid_context_id | 无效或过期的上下文 ID | 重新创建上下文缓存 |
| context_expired | 上下文已过期 | 重新创建上下文缓存 |
| rate_limit_exceeded | 超过速率限制 | 降低请求频率或升级配额 |
| insufficient_quota | 配额不足 | 充值或检查配额使用情况 |

## 参考文档

- [BytePlus ModelArk Context Cache 文档](https://docs.byteplus.com/en/docs/ModelArk/1346559)
- [字节跳动火山引擎 API 文档](https://www.volcengine.com/docs/82379)
