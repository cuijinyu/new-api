# Text-to-Speech (TTS)

Convert text into natural sounding speech.

## API Details

**Endpoint:** `POST /v1/audio/speech`

**Description:** Generates audio from input text. Supports various models, voices, and output formats.

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
| Content-Type | string | Yes | Content type | application/json |

### Body Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| model | string | Yes | - | The ID of the model to use | `tts-1`, `tts-1-hd` |
| input | string | Yes | - | The text to generate audio for | `Hello, welcome to TTS service.` |
| voice | string | Yes | - | The voice to use when generating the audio | `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer` |
| response_format | string | No | `mp3` | The format to audio in | `mp3`, `opus`, `aac`, `flac`, `wav`, `pcm` |
| speed | number | No | 1.0 | The speed of the generated audio | 0.25 to 4.0 |

---

## Response Parameters

**Response Content:** Returns the binary audio file on success.

**Content-Type:** Determined by `response_format`, e.g., `audio/mpeg`.

---

## Code Examples

### Python (using OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://your-domain.com/v1"
)

response = client.audio.speech.create(
    model="tts-1",
    voice="alloy",
    input="Hello, welcome to TTS service.",
)

response.stream_to_file("speech.mp3")
```

### Curl Example

```bash
curl https://your-domain.com/v1/audio/speech \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tts-1",
    "input": "Hello, welcome to TTS service.",
    "voice": "alloy"
  }' \
  --output speech.mp3
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
  /v1/audio/speech:
    post:
      summary: Text-to-Speech
      description: Convert text into natural sounding speech.
      requestBody:
        content:
          application/json:
            schema:
              type: object
              required:
                - model
                - input
                - voice
              properties:
                model:
                  type: string
                input:
                  type: string
                voice:
                  type: string
      responses:
        '200':
          description: Audio generated successfully
          content:
            audio/mpeg:
              schema:
                type: string
                format: binary
```
