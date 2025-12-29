# Audio Transcriptions

Convert audio files into text.

## API Details

**Endpoint:** `POST /v1/audio/transcriptions`

**Description:** Transcribes an audio file into text in the specified format. Supports various audio formats and models.

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
| file | file | Yes | The audio file to transcribe | `speech.mp3` |
| model | string | Yes | The ID of the model to use | `whisper-1` |
| language | string | No | The language of the input audio (ISO-639-1 format) | `zh`, `en` |
| prompt | string | No | An optional text to guide the model's style | - |
| response_format | string | No | The format of the transcript (json, text, srt, vtt) | `json` |
| temperature | number | No | The sampling temperature (between 0 and 1) | `0` |

---

## Response Parameters

**Response Format:** Defaults to JSON formatted transcription.

```json
{
  "text": "Hello, this is a test audio."
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

audio_file = open("speech.mp3", "rb")
transcript = client.audio.transcriptions.create(
  model="whisper-1", 
  file=audio_file
)

print(transcript.text)
```

### Curl Example

```bash
curl https://your-domain.com/v1/audio/transcriptions \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: multipart/form-data" \
  -F file="@speech.mp3" \
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
  /v1/audio/transcriptions:
    post:
      summary: Audio Transcription
      description: Convert audio files into text.
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
          description: Audio transcribed successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  text:
                    type: string
```
