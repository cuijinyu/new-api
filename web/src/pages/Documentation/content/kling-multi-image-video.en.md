# Kling Multi-Image to Video

Generate videos using multiple reference images with Kling models. Supports up to 4 images via the `image_list` parameter.

## API Details

**Endpoint:** `POST /kling/v1/videos/multi-image2video`

**Description:** Submits a multi-image reference video generation task. Video generation is an asynchronous process. After a successful submission, a `task_id` is returned, which is then used to retrieve results through the query endpoint.

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## Request Parameters

### Body Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| model | string | Yes | - | The ID of the model to use | `kling-v1-6` |
| image_list | array | Yes | - | List of input images, up to 4 | `[{"image": "url1"}, {"image": "url2"}]` |
| prompt | string | Yes | - | Text description to guide image dynamics | `Make the two characters in the images dance together` |
| negative_prompt | string | No | - | Negative prompts | `blur, watermark` |
| mode | string | No | `std` | Generation mode | `std`, `pro` |
| aspect_ratio | string | No | `16:9` | Video aspect ratio | `16:9`, `9:16`, `1:1` |
| duration | string | No | `5` | Video duration in seconds | `5`, `10` |
| callback_url | string | No | - | Callback URL for task result notifications | `https://your-callback.com/api` |
| external_task_id | string | No | - | Custom task ID | `my-unique-task-001` |

---

## Response Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| code | integer | Status code (0 for success) |
| message | string | Status message |
| data | object | Data object |
| data.task_id | string | Task ID |
| data.task_status | string | Task status (`submitted`, `processing`, `succeed`, `failed`) |

---

## Code Examples

### Curl Example

```bash
curl https://your-domain.com/kling/v1/videos/multi-image2video \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "kling-v1-6",
    "image_list": [
      {"image": "https://example.com/image1.jpg"},
      {"image": "https://example.com/image2.jpg"}
    ],
    "prompt": "Animate the characters",
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
  /kling/v1/videos/multi-image2video:
    post:
      summary: Kling Multi-Image to Video
      description: Generate videos using multiple reference images with Kling models.
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                model:
                  type: string
                image_list:
                  type: array
                  items:
                    type: object
                    properties:
                      image:
                        type: string
                prompt:
                  type: string
      responses:
        '200':
          description: Task submitted successfully
```
