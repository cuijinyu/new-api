# 可灵 Kling 语音合成 (TTS)

将文本转换为自然流畅的语音，支持多种音色选择。

## 接口说明

**接口地址：** `POST /kling/v1/tts`

**功能描述：** 将输入的文本内容合成为语音音频，支持调整语速和音量。

**认证方式：** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 请求参数 (Body)

| 字段 | 类型 | 必填 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| text | string | 必须 | 无 | 待合成的文本内容，最大长度 10000 字符 |
| voice_id | string | 必须 | 无 | 音色ID，可从可灵平台获取可用音色列表 |
| speed | number | 可选 | 1.0 | 语速，取值范围 [0.5, 2.0]，1.0 为正常语速 |
| volume | number | 可选 | 1.0 | 音量，取值范围 [0, 2.0]，1.0 为正常音量 |
| callback_url | string | 可选 | 无 | 任务结果回调通知地址 |

---

## 响应参数

| 字段 | 类型 | 描述 |
| :--- | :--- | :--- |
| code | integer | 错误码 (0 表示成功) |
| message | string | 错误信息 |
| request_id | string | 请求ID |
| data | object | 数据对象 |
| data.audio_id | string | 生成的音频ID |
| data.audio_url | string | 生成的音频URL |
| data.duration | integer | 音频时长（毫秒） |
| data.created_at | integer | 创建时间（毫秒时间戳） |

---

## 请求示例

### 基础请求

```json
{
  "text": "你好，欢迎使用可灵AI语音合成服务。",
  "voice_id": "voice_001"
}
```

### 完整参数请求

```json
{
  "text": "这是一段测试文本，用于演示语音合成功能。通过调整语速和音量参数，可以获得不同效果的语音输出。",
  "voice_id": "voice_001",
  "speed": 1.2,
  "volume": 0.8
}
```

---

## 响应示例

### 成功响应

```json
{
  "code": 0,
  "message": "success",
  "request_id": "req_tts_123456",
  "data": {
    "audio_id": "audio_abc123",
    "audio_url": "https://example.com/tts/audio_abc123.mp3",
    "duration": 5200,
    "created_at": 1722769557708
  }
}
```

### 错误响应

```json
{
  "code": 400,
  "message": "text is required for tts",
  "request_id": "req_tts_123457"
}
```

---

## 代码示例

### cURL

```bash
curl -X POST "https://api.example.com/kling/v1/tts" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "你好，这是一段测试语音。",
    "voice_id": "voice_001",
    "speed": 1.0,
    "volume": 1.0
  }'
```

### Python

```python
import requests

url = "https://api.example.com/kling/v1/tts"
headers = {
    "Authorization": "Bearer YOUR_API_TOKEN",
    "Content-Type": "application/json"
}
payload = {
    "text": "你好，这是一段测试语音。",
    "voice_id": "voice_001",
    "speed": 1.0,
    "volume": 1.0
}

response = requests.post(url, json=payload, headers=headers)
result = response.json()

if result["code"] == 0:
    audio_url = result["data"]["audio_url"]
    print(f"音频生成成功: {audio_url}")
else:
    print(f"生成失败: {result['message']}")
```

### JavaScript

```javascript
const response = await fetch('https://api.example.com/kling/v1/tts', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer YOUR_API_TOKEN',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    text: '你好，这是一段测试语音。',
    voice_id: 'voice_001',
    speed: 1.0,
    volume: 1.0
  })
});

const result = await response.json();

if (result.code === 0) {
  console.log('音频URL:', result.data.audio_url);
} else {
  console.error('生成失败:', result.message);
}
```

---

## 注意事项

1. **文本长度限制**：单次请求最大支持 1000 字符
2. **同步接口**：该接口为同步接口，直接返回生成的音频信息，无需轮询任务状态
3. **音频格式**：返回的音频为 MP3 格式
4. **音色选择**：请确保使用有效的 `voice_id`，可从可灵平台获取可用音色列表

---

## 错误码说明

| 错误码 | 描述 |
| :--- | :--- |
| 0 | 成功 |
| 400 | 请求参数错误（如缺少必填字段、参数超出范围等） |
| 401 | 认证失败 |
| 429 | 请求过于频繁 |
| 500 | 服务器内部错误 |
