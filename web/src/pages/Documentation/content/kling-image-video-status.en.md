# Get Kling Image-to-Video Task Status

Query the status and results of a Kling image-to-video task.

## API Details

**Endpoint:** `GET /kling/v1/videos/image2video/:task_id`

**Description:** Query the progress and final result of video generation using the `task_id` returned when the task was submitted.

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## Request Parameters

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| task_id | string | Yes | The unique identifier of the task returned during submission |

---

## Response Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| code | integer | Status code (0 for success) |
| message | string | Status message |
| data | object | Data object |
| data.task_id | string | Task ID |
| data.task_status | string | Task status: `submitted`, `processing`, `succeed`, `failed` |
| data.task_result | object | Task result (present only when status is `succeed`) |
| data.task_result.videos | array | List of generated videos |
| data.task_result.videos[0].url | string | Video download/playback URL |
| data.task_result.videos[0].duration | string | Video duration |

---

## Code Examples

### Curl Example

```bash
curl https://your-domain.com/kling/v1/videos/image2video/YOUR_TASK_ID \
  -H "Authorization: Bearer $YOUR_API_KEY"
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
  /kling/v1/videos/image2video/{task_id}:
    get:
      summary: Get Kling Image-to-Video Task Status
      description: Query the status and results of a Kling image-to-video task.
      parameters:
        - name: task_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Successfully retrieved task status
```
