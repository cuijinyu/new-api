# Get Video Generation Task Status

Query the status and results of a video generation task.

## API Details

**Endpoint:** `GET /v1/video/generations/:task_id`

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

## Task Statuses

| Status | Description |
|--------|-------------|
| `queued` | Task is in queue |
| `in_progress` | Video is being generated |
| `completed` | Task completed successfully |
| `failed` | Task failed |

---

## Response Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| id | string | Unique task identifier |
| object | string | Object type |
| created | integer | Unix timestamp of creation |
| status | string | Task status |
| data | array | List of generated results (present only when status is `completed`) |
| data.url | string | Video download or playback URL |
| error | object | Error information (present only when status is `failed`) |

---

## Code Examples

### Curl Example

```bash
curl https://your-domain.com/v1/video/generations/YOUR_TASK_ID \
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
  /v1/video/generations/{task_id}:
    get:
      summary: Get Video Generation Task Status
      description: Query the status and results of a video generation task.
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
