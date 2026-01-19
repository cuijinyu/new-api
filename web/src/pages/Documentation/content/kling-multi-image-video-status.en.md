# Get Kling Multi-Image to Video Status

Query the status and results of a Kling multi-image reference video generation task.

## API Details

**Endpoint:** `GET /kling/v1/videos/multi-image2video/:task_id`

**Description:** Retrieves the progress and final result of video generation using the `task_id` returned during task submission.

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
| data.task_result | object | Task result (only present when status is `succeed`) |
| data.task_result.videos | array | List of generated videos |
| data.task_result.videos[0].url | string | URL for video download or playback |
| data.task_result.videos[0].duration | string | Total duration of the video |

---

## Code Examples

### Curl Example

```bash
curl https://your-domain.com/kling/v1/videos/multi-image2video/YOUR_TASK_ID \
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
  /kling/v1/videos/multi-image2video/{task_id}:
    get:
      summary: Get Kling Multi-Image to Video Status
      description: Query the status and results of a Kling multi-image reference video generation task.
      parameters:
        - name: task_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Status retrieved successfully
```
