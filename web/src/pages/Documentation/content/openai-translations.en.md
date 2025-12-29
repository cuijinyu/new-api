# Audio Translations

Translate and transcribe audio files into English text.

## API Details

**Endpoint:** `POST /v1/audio/translations`

**Description:** Translates an audio file from any supported language into English text. Supports various audio formats.

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## Request Parameters

### Header Parameters

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| Authorization | string | Yes | Bearer Token authentication | Bearer sk-xxx... |
| Content-Type | string | Yes | Content type | `multipart/form-data` |

### Body Parameters (Multipart Form Data)

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| file | file | Yes | The audio file to translate | `speech.mp3` |
| model | string | Yes | The ID of the model to use | `whisper-1` |
| prompt | string | No | An optional text to guide the model's style | - |
| response_format | string | No | The format of the translation (json, text, srt, vtt) | `json` |
| temperature | number | No | The sampling temperature (between 0 and 1) | `0` |

---

## Response Parameters

**Response Format:** Defaults to JSON formatted English translation.

```json
{
  "text": "Hello, this is a translated text from audio."
}
```

---

## Code Examples

### Python (using OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://your-domain.com/v1"
)

audio_file = open("german_speech.mp3", "rb")
translation = client.audio.translations.create(
  model="whisper-1", 
  file=audio_file
)

print(translation.text)
```

### Curl Example

```bash
curl https://your-domain.com/v1/audio/translations \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: multipart/form-data" \
  -F file="@german_speech.mp3" \
  -F model="whisper-1"
```

---

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /v1/audio/translations:
    post:
      summary: Audio Translation
      description: Translate audio files into English text.
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              required:
                - file
                - model
              properties:
                file:
                  type: string
                  format: binary
                model:
                  type: string
      responses:
        '200':
          description: Audio translated successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  text:
                    type: string
```
