# Get Kling Text-to-Video Task Status

Query the status and results of a Kling text-to-video task.

## API Details

**Endpoint:** `GET /kling/v1/videos/text2video/:task_id`

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
| code | string | Status code (`success` for success) |
| message | string | Status message |
| data | object | Task detail object |
| data.task_id | string | Task ID |
| data.status | string | Unified task status: `SUBMITTED`, `IN_PROGRESS`, `SUCCESS`, `FAILURE` |
| data.progress | string | Task progress (e.g., "100%") |
| data.data | object | Original Kling response data |
| data.data.data.task_status | string | Kling task status: `submitted`, `processing`, `succeed`, `failed` |
| data.data.data.task_result.videos | array | List of generated videos |
| data.data.data.task_result.videos[0].url | string | URL for video download or playback |
| data.data.data.task_result.videos[0].duration | string | Total duration of the video |

---

## Response Example

```json
{
  "code": "success",
  "message": "",
  "data": {
    "task_id": "842250903629086785",
    "status": "SUCCESS",
    "progress": "100%",
    "data": {
      "code": 0,
      "data": {
        "task_id": "842250903629086785",
        "task_status": "succeed",
        "task_result": {
          "videos": [
            {
              "id": "842250903708762200",
              "url": "https://v16-kling-fdl.klingai.com/...",
              "duration": "5.1"
            }
          ]
        }
      }
    }
  }
}
```

---

## Code Examples

### Curl Example

```bash
curl https://your-domain.com/kling/v1/videos/text2video/YOUR_TASK_ID \
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
  /kling/v1/videos/text2video/{task_id}:
    get:
      summary: Get Kling Text-to-Video Task Status
      description: Query the status and results of a Kling text-to-video task.
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
