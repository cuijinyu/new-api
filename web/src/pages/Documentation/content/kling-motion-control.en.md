# Kling Motion Control

Create videos where characters in an image perform actions from a reference video.

## 1. Create Task

**Endpoint:** `POST /v1/videos/motion-control`

**Description:** Submit a motion control video generation task. The process is asynchronous. Upon success, a `task_id` is returned, which can be used to query the results later.

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

### Request Parameters (Body)

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| prompt | string | No | Empty | Text prompt for positive/negative descriptions. Can be used to add elements or camera effects. Max 2500 characters. |
| image_url | string | Yes | - | Reference image for characters and background. Supports Base64 or URL. Formats: .jpg, .jpeg, .png. Max 10MB. |
| video_url | string | Yes | - | Reference video for character motion. Supports .mp4, .mov. Max 100MB, min 3s. |
| keep_original_sound | string | No | yes | Whether to keep original video sound. Enum: `yes`, `no`. |
| character_orientation | string | Yes | - | Character orientation in generated video. Enum: `image` (same as image), `video` (same as video). |
| mode | string | Yes | - | Video generation mode. Enum: `std` (standard), `pro` (professional). |
| callback_url | string | No | - | Callback URL for task completion notifications. |
| external_task_id | string | No | - | User-defined task ID. Must be unique per user. |

### Response Parameters

| Field | Type | Description |
| :--- | :--- | :--- |
| code | integer | Error code (0 for success) |
| message | string | Error message |
| request_id | string | Request ID |
| data | object | Data object |
| data.task_id | string | Task ID |
| data.task_status | string | Task status: `submitted`, `processing`, `succeed`, `failed` |

---

## 2. Query Task (Single)

**Endpoint:** `GET /v1/videos/motion-control/{task_id}`

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
    "task_info": {
      "external_task_id": "custom_id_123"
    },
    "task_result": {
      "videos": [
        {
          "id": "vid_123",
          "url": "https://example.com/video.mp4",
          "duration": "5"
        }
      ]
    },
    "created_at": 1722769557708,
    "updated_at": 1722769557708
  }
}
```
