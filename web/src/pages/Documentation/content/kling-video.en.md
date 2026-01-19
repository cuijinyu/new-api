# Kling Text-to-Video

Generate videos from text descriptions using Kling models.

## API Details

### 1. Submit Text-to-Video Task

**Endpoint:** `POST /kling/v1/videos/text2video`

**Description:** Submits a video generation task. Video generation is an asynchronous process. After a successful submission, a `task_id` is returned, which is then used to retrieve results through the query endpoint.

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## Request Parameters

### Body Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| model | string | Yes | - | The ID of the model to use | `kling-v1` |
| prompt | string | Yes | - | Text description of the video | `A deer running in the forest` |
| image_tail | string | No | - | Tail frame image URL or Base64 encoded data, used to specify the ending frame of the video | `https://example.com/end.jpg` |
| negative_prompt | string | No | - | Negative prompts | `blur, watermark` |
| cfg_scale | float | No | 5.0 | Prompt correlation scale | 0.0 - 100.0 |
| mode | string | No | `std` | Generation mode | `std` (Standard), `pro` (Professional) |
| aspect_ratio | string | No | `16:9` | Video aspect ratio | `16:9`, `9:16`, `1:1` |
| duration | string | No | `5` | Video duration in seconds | `5`, `10` |

---

## Response Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| code | integer | Status code (0 for success) |
| message | string | Status message |
| data | object | Data object |
| data.task_id | string | Task ID, used for querying results |
| data.task_status | string | Task status (`submitted`, `processing`, `succeed`, `failed`) |

---

### 2. Query Task Result

**Endpoint:** `GET /kling/v1/videos/text2video/:task_id`

**Response Example:**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "task_id": "xxx",
    "task_status": "succeed",
    "task_result": {
      "videos": [
        {
          "url": "https://example.com/video.mp4",
          "duration": "5"
        }
      ]
    }
  }
}
```

---

## Code Examples

### Curl Example

```bash
# 1. Submit task
curl https://your-domain.com/kling/v1/videos/text2video \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "kling-v1",
    "prompt": "A deer running in the forest",
    "mode": "std",
    "aspect_ratio": "16:9",
    "duration": "5"
  }'

# 2. Query result (replace TASK_ID)
curl https://your-domain.com/kling/v1/videos/text2video/TASK_ID \
  -H "Authorization: Bearer $YOUR_API_KEY"
```
