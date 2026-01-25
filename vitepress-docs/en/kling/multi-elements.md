# Kling Multi-Elements Video Editing

Edit videos using natural language, supporting adding, replacing, and removing elements in videos.

## Workflow

Multi-elements video editing requires the following steps:
1. **Initialize Video** - Upload the video to be edited
2. **Mark Selection** (Optional) - Mark the video elements to be edited
3. **Preview Selection** (Optional) - Preview the marked selection effect
4. **Create Task** - Submit the video editing task

---

## 1. Initialize Video

**Endpoint:** `POST /kling/v1/videos/multi-elements/init-selection`

**Description:** Initialize the video to be edited and get a session ID for subsequent operations.

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

### Request Parameters (Body)

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| video_id | string | Optional | empty | Video ID from history, only supports videos generated within 30 days. Choose either this or `video_url`. |
| video_url | string | Optional | - | Video URL. Only supports MP4 and MOV formats. Duration must be ≥2s and ≤5s, or ≥7s and ≤10s. Width/height must be between 720px and 2160px. Only supports 24, 30, or 60fps. Choose either this or `video_id`. |

### Response Parameters

| Field | Type | Description |
| :--- | :--- | :--- |
| code | integer | Error code (0 indicates success) |
| message | string | Error message |
| request_id | string | Request ID |
| data.status | integer | Rejection code, non-zero means recognition failed |
| data.session_id | string | Session ID, valid for 24 hours |
| data.fps | number | Parsed video frame rate |
| data.original_duration | integer | Parsed video duration |
| data.width | integer | Parsed video width |
| data.height | integer | Parsed video height |
| data.total_frame | integer | Parsed video total frames |
| data.normalized_video | string | Normalized video URL |

### Response Example

```json
{
  "code": 0,
  "message": "success",
  "request_id": "req_123456",
  "data": {
    "status": 0,
    "session_id": "session_abc123",
    "fps": 30.0,
    "original_duration": 5000,
    "width": 1280,
    "height": 720,
    "total_frame": 150,
    "normalized_video": "https://example.com/normalized_video.mp4"
  }
}
```

---

## 2. Add Selection

**Endpoint:** `POST /kling/v1/videos/multi-elements/add-selection`

**Description:** Mark the area to be edited in video frames.

### Request Parameters (Body)

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| session_id | string | Required | - | Session ID |
| frame_index | integer | Required | - | Frame number, max 10 marked frames supported |
| points | array | Required | - | Point coordinate array |
| points[].x | number | Required | - | X coordinate, range [0, 1] |
| points[].y | number | Required | - | Y coordinate, range [0, 1], [0,0] represents top-left corner |

### Response Parameters

| Field | Type | Description |
| :--- | :--- | :--- |
| data.status | integer | Rejection code |
| data.session_id | string | Session ID |
| data.res.frame_index | integer | Frame number |
| data.res.rle_mask_list | array | RLE mask list containing image segmentation results |

---

## 3. Delete Selection

**Endpoint:** `POST /kling/v1/videos/multi-elements/delete-selection`

**Description:** Delete marked selection points.

### Request Parameters (Body)

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| session_id | string | Required | Session ID |
| frame_index | integer | Required | Frame number |
| points | array | Required | Point coordinates to delete, must match exactly with add selection |

---

## 4. Clear Selection

**Endpoint:** `POST /kling/v1/videos/multi-elements/clear-selection`

**Description:** Clear all marked selections.

### Request Parameters (Body)

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| session_id | string | Required | Session ID |

---

## 5. Preview Selection

**Endpoint:** `POST /kling/v1/videos/multi-elements/preview-selection`

**Description:** Preview the video effect with marked selections.

### Request Parameters (Body)

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| session_id | string | Required | Session ID |

### Response Parameters

| Field | Type | Description |
| :--- | :--- | :--- |
| data.res.video | string | Video URL with mask |
| data.res.video_cover | string | Video cover URL with mask |
| data.res.tracking_output | string | Mask result for each frame |

---

## 6. Create Task

**Endpoint:** `POST /kling/v1/videos/multi-elements`

**Description:** Create a multi-elements video editing task.

### Request Parameters (Body)

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| model_name | string | Optional | kling-v1-6 | Model name |
| session_id | string | Required | - | Session ID |
| edit_mode | string | Required | - | Edit mode: `addition`, `swap`, `removal` |
| image_list | array | Optional | empty | Reference image list. Required for addition (1-2 images), required for swap (1 image), not needed for removal. |
| image_list[].image | string | Required | - | Image Base64 or URL |
| prompt | string | Required | - | Positive text prompt, max 2500 characters. Use `<<<video_1>>>` for video, `<<<image_1>>>` for image. |
| negative_prompt | string | Optional | empty | Negative text prompt, max 2500 characters |
| mode | string | Optional | std | Generation mode: `std`, `pro` |
| duration | string | Optional | 5 | Video duration: `5` or `10` seconds |
| callback_url | string | Optional | empty | Callback URL |
| external_task_id | string | Optional | empty | Custom task ID |

### Recommended Prompt Templates

**Addition:**
```
Using the context of <<<video_1>>>, seamlessly add [subject] from <<<image_1>>> to [location]
```

**Swap:**
```
Swap [new element] from <<<image_1>>> for [original element] from <<<video_1>>>
```

**Removal:**
```
Delete [element description] from <<<video_1>>>
```

### Response Parameters

| Field | Type | Description |
| :--- | :--- | :--- |
| data.task_id | string | Task ID |
| data.task_status | string | Task status |
| data.session_id | string | Session ID |
| data.created_at | integer | Task creation time (ms) |
| data.updated_at | integer | Task update time (ms) |

---

## 7. Query Task

**Endpoint:** `GET /kling/v1/videos/multi-elements/:task_id`

**Description:** Query the status and result of a multi-elements video editing task.

### Response Parameters

| Field | Type | Description |
| :--- | :--- | :--- |
| data.task_id | string | Task ID |
| data.task_status | string | Task status |
| data.task_status_msg | string | Task status message |
| data.task_result.videos | array | Generated video list |
| data.task_result.videos[].id | string | Video ID |
| data.task_result.videos[].session_id | string | Session ID |
| data.task_result.videos[].url | string | Video URL |
| data.task_result.videos[].duration | string | Video duration (seconds) |
