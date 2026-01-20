# Get Kling Omni Video Task Status

Query the status and results of a Kling Omni video task.

## API Details

**Endpoint:** `GET /kling/v1/videos/omni-video/:task_id`

**Description:** Query the progress and results of Omni video generation using the `task_id` returned when the task was submitted.

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## Response Parameters

Returns a unified task status object upon successful query.

| Name | Type | Description |
|------|------|-------------|
| code | string | Status code (`success` for success) |
| message | string | Message |
| data | object | Task detail object |
| data.task_id | string | Task ID |
| data.status | string | Task status: `SUBMITTED`, `IN_PROGRESS`, `SUCCESS`, `FAILURE` |
| data.progress | string | Task progress (e.g., "100%") |
| data.data | object | Raw Kling response data (includes `task_result`, etc.) |

---

## Response Example

```json
{
  "code": "success",
  "data": {
    "task_id": "842250903629086785",
    "status": "SUCCESS",
    "progress": "100%",
    "data": {
      "code": 0,
      "message": "HTTP_OK",
      "request_id": "...",
      "data": {
        "task_id": "842250903629086785",
        "task_status": "succeed",
        "task_result": {
          "videos": [
            {
              "id": "...",
              "url": "https://...",
              "duration": "5.0"
            }
          ]
        }
      }
    }
  }
}
```
