# Kling Omni Video

Kling Omni Video is an advanced version of Kling V1.0, supporting richer multimodal inputs including multiple images, video references, and subject control, enabling more precise motion control and richer visual expression.

## API Details

**Endpoint:** `POST /kling/v1/videos/omni-video`

**Description:** Submit an Omni video generation task. Supports mixed inputs (text, images, videos, subject elements).

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## Request Parameters

### Body Parameters

| Name | Type | Required | Default | Description | Example |
|------|------|----------|---------|-------------|---------|
| model | string | Yes | - | Model ID | `kling-v1` |
| prompt | string | No | - | Video description text | `A small fox running in the forest` |
| negative_prompt | string | No | - | Negative prompts | `blur, watermark` |
| mode | string | No | `std` | Generation mode: `std` (Standard), `pro` (Professional) | `std`, `pro` |
| duration | string | No | `5` | Video duration (seconds). T2V and basic I2V only support `5`, `10`; first/end frame mode and video reference support `3-10` | `5`, `10` |
| aspect_ratio | string | No | `16:9` | Video aspect ratio | `16:9`, `9:16`, `1:1` |
| image_list | array | No | - | Reference image list | `[{"image_url": "...", "type": "first_frame"}]` |
| video_list | array | No | - | Reference video list (using video reference increases cost multiplier) | `[{"video_url": "...", "refer_type": "feature"}]` |
| element_list | array | No | - | Subject element list | `[{"element_id": 123456}]` |
| cfg_scale | float | No | 0.5 | Prompt adherence scale | 0.0 - 1.0 |
| external_task_id | string | No | - | Custom task ID | `my_task_001` |
| callback_url | string | No | - | Callback URL after task completion | `https://your-api.com/callback` |

### OmniImageItem
| Name | Type | Description |
|------|------|-------------|
| image_url | string | Image URL |
| type | string | Image role: `first_frame`, `end_frame` |

### OmniVideoItem
| Name | Type | Description |
|------|------|-------------|
| video_url | string | Video URL |
| refer_type | string | Reference type: only `feature` is supported, `base` is not supported |
| keep_original_sound | string | Keep original sound: `yes`, `no` |

---

## Response Parameters

Returns an OpenAI-compatible `video` object upon successful submission.

| Name | Type | Description |
|------|------|-------------|
| id | string | Task ID |
| task_id | string | Task ID (Compatibility field) |
| object | string | Object type, fixed as `video` |
| model | string | Model ID used |
| created_at | integer | Creation timestamp |

---

## Code Examples

### Curl Example (Mixed Input)

```bash
curl https://your-domain.com/kling/v1/videos/omni-video \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "kling-v1",
    "prompt": "Make the character move",
    "image_list": [
      {
        "image_url": "https://example.com/start.jpg",
        "type": "first_frame"
      }
    ],
    "duration": "5"
  }'
```

### Response Example

```json
{
  "id": "842250903629086785",
  "task_id": "842250903629086785",
  "object": "video",
  "model": "kling-v1",
  "created_at": 1737367800
}
```
