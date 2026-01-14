# Gemini Native Format

Gemini native interface supports both text and image generation. This interface allows you to directly call Gemini's native capabilities, including the latest image generation features.

## Interface Details

**Endpoint:** `POST /v1beta/models/{model}:generateContent`

**Description:** Generates content based on prompts and configurations. Supports multi-modal input (text, images) and multi-modal output (text, images).

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## Request Parameters

### Path Parameters

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| model | string | Yes | Model Name | `gemini-2.0-flash-exp` |

### Header Parameters

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| Authorization | string | Yes | Bearer Token Auth | Bearer sk-xxx... |
| Content-Type | string | Yes | Content Type | application/json |

### Body Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| contents | array[object] | Yes | List of dialogue contents |
| contents[].role | string | No | Role (user, model) |
| contents[].parts | array[object] | Yes | Content parts |
| contents[].parts[].text | string | No | Text prompt |
| generationConfig | object | No | Generation config options |
| generationConfig.responseModalities | array[string] | No | Response modalities (TEXT, IMAGE) |
| generationConfig.imageConfig | object | No | Image generation configuration |
| generationConfig.imageConfig.aspectRatio | string | No | Aspect ratio (1:1, 16:9, 9:16, etc.) |
| generationConfig.imageConfig.imageSize | string | No | Image quality/size (1K, 2K, 4K) |

---

## Response Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| candidates | array[object] | List of generation candidates |
| candidates[].content | object | Content object |
| candidates[].content.parts | array[object] | Content parts, containing text or generated image data |
| candidates[].finishReason | string | Reason for completion |
| usageMetadata | object | Usage statistics |
| usageMetadata.promptTokenCount | integer | Prompt token count |
| usageMetadata.candidatesTokenCount | integer | Generated token count |
| usageMetadata.totalTokenCount | integer | Total token count |

---

## Code Examples

### Curl Example (Image Generation)

```bash
curl -X POST "https://your-domain.com/v1beta/models/gemini-2.0-flash-exp:generateContent" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [
      {
        "parts": [
          {
            "text": "A cyberpunk style fox running in a forest"
          }
        ]
      }
    ],
    "generationConfig": {
      "responseModalities": ["IMAGE"],
      "imageConfig": {
        "aspectRatio": "16:9",
        "imageSize": "1K"
      }
    }
  }'
```

### Response Example

```json
{
  "candidates": [
    {
      "content": {
        "role": "model",
        "parts": [
          {
            "inlineData": {
              "mimeType": "image/png",
              "data": "iVBORw0KGgoAAA..."
            }
          }
        ]
      },
      "finishReason": "STOP"
    }
  ],
  "usageMetadata": {
    "promptTokenCount": 15,
    "candidatesTokenCount": 0,
    "totalTokenCount": 15
  }
}
```
