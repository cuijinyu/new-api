# Kling Text-to-Speech (TTS)

Convert text into natural and fluent speech with multiple voice options.

## API Description

**Endpoint:** `POST /kling/v1/tts`

**Description:** Synthesize input text into speech audio, with adjustable speed and volume.

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

**Pricing:** Charged per call, **0.05 CNY** per request, regardless of text length.

---

## Request Parameters (Body)

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| text | string | Required | - | Text content to synthesize, maximum 10000 characters |
| voice_id | string | Required | - | Voice ID, available voices can be obtained from Kling platform |
| speed | number | Optional | 1.0 | Speech speed, range [0.5, 2.0], 1.0 is normal speed |
| volume | number | Optional | 1.0 | Volume level, range [0, 2.0], 1.0 is normal volume |
| callback_url | string | Optional | - | Callback URL for task result notification |

---

## Response Parameters

| Field | Type | Description |
| :--- | :--- | :--- |
| code | integer | Error code (0 indicates success) |
| message | string | Error message |
| request_id | string | Request ID |
| data | object | Data object |
| data.audio_id | string | Generated audio ID |
| data.audio_url | string | Generated audio URL |
| data.duration | integer | Audio duration (milliseconds) |
| data.created_at | integer | Creation timestamp (milliseconds) |

---

## Request Examples

### Basic Request

```json
{
  "text": "Hello, welcome to Kling AI text-to-speech service.",
  "voice_id": "voice_001"
}
```

### Full Parameters Request

```json
{
  "text": "This is a test text to demonstrate the text-to-speech feature. By adjusting speed and volume parameters, you can get different speech output effects.",
  "voice_id": "voice_001",
  "speed": 1.2,
  "volume": 0.8
}
```

---

## Response Examples

### Success Response

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

### Error Response

```json
{
  "code": 400,
  "message": "text is required for tts",
  "request_id": "req_tts_123457"
}
```

---

## Code Examples

### cURL

```bash
curl -X POST "https://api.example.com/kling/v1/tts" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello, this is a test speech.",
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
    "text": "Hello, this is a test speech.",
    "voice_id": "voice_001",
    "speed": 1.0,
    "volume": 1.0
}

response = requests.post(url, json=payload, headers=headers)
result = response.json()

if result["code"] == 0:
    audio_url = result["data"]["audio_url"]
    print(f"Audio generated successfully: {audio_url}")
else:
    print(f"Generation failed: {result['message']}")
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
    text: 'Hello, this is a test speech.',
    voice_id: 'voice_001',
    speed: 1.0,
    volume: 1.0
  })
});

const result = await response.json();

if (result.code === 0) {
  console.log('Audio URL:', result.data.audio_url);
} else {
  console.error('Generation failed:', result.message);
}
```

---

## Notes

1. **Text Length Limit**: Maximum 10000 characters per request
2. **Pricing**: Charged per call, 0.05 CNY per request, regardless of text length
3. **Synchronous API**: This is a synchronous endpoint that returns audio information directly, no polling required
4. **Audio Format**: The returned audio is in MP3 format
5. **Voice Selection**: Ensure you use a valid `voice_id`, available voices can be obtained from Kling platform

---

## Error Codes

| Code | Description |
| :--- | :--- |
| 0 | Success |
| 400 | Invalid request parameters (missing required fields, parameters out of range, etc.) |
| 401 | Authentication failed |
| 429 | Too many requests |
| 500 | Internal server error |
