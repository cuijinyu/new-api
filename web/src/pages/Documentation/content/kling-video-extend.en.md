# Kling Video Extend

Extend existing videos to generate longer duration video content.

## 1. Create Task

**Endpoint:** `POST /kling/v1/videos/video-extend`

**Description:** Submit a video extend task. Video extension is an asynchronous process. After successful submission, a `task_id` will be returned. You need to query the result through the query endpoint.

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

### Request Parameters (Body)

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| video_id | string | Required | - | Video ID, the original video ID to be extended |
| prompt | string | Optional | empty | Positive text prompt to guide the video extension direction. Max 2500 characters. |
| negative_prompt | string | Optional | empty | Negative text prompt to exclude unwanted content. Max 2500 characters. |
| cfg_scale | number | Optional | 0.5 | Prompt reference strength, range [0, 1]. Higher values make generated content closer to the prompt. |
| callback_url | string | Optional | - | Callback URL for task result notification. |

### Response Parameters

| Field | Type | Description |
| :--- | :--- | :--- |
| code | integer | Error code (0 indicates success) |
| message | string | Error message |
| request_id | string | Request ID |
| data | object | Data object |
| data.task_id | string | Task ID |
| data.task_status | string | Task status: `submitted`, `processing`, `succeed`, `failed` |

### Request Example

```json
{
  "video_id": "vid_original_123456",
  "prompt": "Continue showing the beautiful sunset, slowly zooming out",
  "negative_prompt": "blurry, shaky",
  "cfg_scale": 0.5
}
```

---

## 2. Query Task

**Endpoint:** `GET /kling/v1/videos/video-extend/:task_id`

**Description:** Query the status and result of a video extend task by task ID.

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

### Path Parameters

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| task_id | string | Required | Task ID returned by the create task endpoint |

### Response Parameters

| Field | Type | Description |
| :--- | :--- | :--- |
| code | integer | Error code (0 indicates success) |
| message | string | Error message |
| request_id | string | Request ID for tracking and debugging |
| data | object | Data object |
| data.task_id | string | Task ID |
| data.task_status | string | Task status: `submitted`, `processing`, `succeed`, `failed` |
| data.task_status_msg | string | Task status message, shows failure reason when task fails |
| data.task_result | object | Task result (only returned on success) |
| data.task_result.videos | array | Generated video list |
| data.task_result.videos[].id | string | Generated video ID, globally unique |
| data.task_result.videos[].url | string | Generated video URL (Note: videos will be cleaned up after 30 days, please save them in time) |
| data.task_result.videos[].duration | string | Video duration in seconds |
| data.created_at | integer | Task creation time, Unix timestamp (ms) |
| data.updated_at | integer | Task update time, Unix timestamp (ms) |

### Response Example

```json
{
  "code": 0,
  "message": "success",
  "request_id": "req_123456",
  "data": {
    "task_id": "task_123456",
    "task_status": "succeed",
    "task_status_msg": "success",
    "task_result": {
      "videos": [
        {
          "id": "vid_extended_123",
          "url": "https://example.com/extended_video.mp4",
          "duration": "10"
        }
      ]
    },
    "created_at": 1722769557708,
    "updated_at": 1722769557708
  }
}
```
