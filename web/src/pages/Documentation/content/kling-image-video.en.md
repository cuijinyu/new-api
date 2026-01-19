# Kling Image-to-Video

Generate videos from images using Kling models. Supports passing image URL or Base64 encoded image data via the `image` parameter.

## API Details

**Endpoint:** `POST /kling/v1/videos/image2video`

**Description:** Submits an image-to-video task. Video generation is an asynchronous process. After a successful submission, a `task_id` is returned, which is then used to retrieve results through the query endpoint.

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
| image | string | Yes | - | URL or Base64 encoded data of the input image | `https://example.com/start.jpg` |
| image_tail | string | No | - | Tail frame image URL or Base64 encoded data, used to specify the ending frame of the video | `https://example.com/end.jpg` |
| prompt | string | No | - | Text description to guide image dynamics | `Make the person in the image smile` |
| negative_prompt | string | No | - | Negative prompts | `blur, watermark` |
| cfg_scale | float | No | 5.0 | Prompt correlation scale | 0.0 - 100.0 |
| mode | string | No | `std` | Generation mode | `std`, `pro` |
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

## Code Examples

### Curl Example

```bash
curl https://your-domain.com/kling/v1/videos/image2video \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "kling-v1",
    "image": "https://example.com/start.jpg",
    "prompt": "Animate the person",
    "duration": "5"
  }'
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
  /kling/v1/videos/image2video:
    post:
      summary: Kling Image-to-Video
      description: Generate videos from images using Kling models.
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                model:
                  type: string
                image:
                  type: string
                image_tail:
                  type: string
      responses:
        '200':
          description: Task submitted successfully
```
