# 可灵 Kling 对口型 (Lip Sync)

让视频中的人物根据音频进行口型同步，实现音画匹配的效果。

## 工作流程

对口型功能需要两个步骤：
1. **人脸识别** - 识别视频中的人脸，获取 `session_id`
2. **创建对口型任务** - 使用 `session_id` 和音频创建对口型任务

---

## 1. 人脸识别

**接口地址：** `POST /kling/v1/videos/identify-face`

**功能描述：** 识别视频中的人脸，返回可用于对口型的人脸信息和会话ID。

**认证方式：** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

### 请求参数 (Body)

| 字段 | 类型 | 必填 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| video_id | string | 可选 | 无 | 可灵AI生成的视频ID。与 `video_url` 二选一，不能同时为空，也不能同时有值。 |
| video_url | string | 可选 | 无 | 视频的获取URL。与 `video_id` 二选一，不能同时为空，也不能同时有值。 |

### 响应参数

| 字段 | 类型 | 描述 |
| :--- | :--- | :--- |
| code | integer | 错误码 (0 表示成功) |
| message | string | 错误信息 |
| request_id | string | 请求ID |
| data | object | 数据对象 |
| data.session_id | string | 会话ID，有效期24小时，用于后续创建对口型任务 |
| data.face_data | array | 人脸数据列表 |
| data.face_data[].face_id | string | 人脸ID |
| data.face_data[].face_image | string | 人脸示意图URL |
| data.face_data[].start_time | integer | 可对口型区间起点时间（毫秒） |
| data.face_data[].end_time | integer | 可对口型区间终点时间（毫秒） |

### 请求示例

```json
{
  "video_url": "https://example.com/video.mp4"
}
```

### 响应示例

```json
{
  "code": 0,
  "message": "success",
  "request_id": "req_123456",
  "data": {
    "session_id": "session_abc123",
    "face_data": [
      {
        "face_id": "face_001",
        "face_image": "https://example.com/face_preview.jpg",
        "start_time": 0,
        "end_time": 5000
      }
    ]
  }
}
```

---

## 2. 创建对口型任务

**接口地址：** `POST /kling/v1/videos/advanced-lip-sync`

**功能描述：** 创建对口型视频生成任务。

**认证方式：** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

### 请求参数 (Body)

| 字段 | 类型 | 必填 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| session_id | string | 必须 | 无 | 会话ID，由人脸识别接口返回 |
| face_choose | array | 必须 | 无 | 指定人脸对口型配置，暂时仅支持单人 |
| face_choose[].face_id | string | 必须 | 无 | 人脸ID，由人脸识别接口返回 |
| face_choose[].audio_id | string | 可选 | 无 | 试听接口生成的音频ID。与 `sound_file` 二选一。 |
| face_choose[].sound_file | string | 可选 | 无 | 音频文件（Base64编码或URL）。与 `audio_id` 二选一。 |
| face_choose[].sound_start_time | integer | 必须 | 无 | 音频裁剪起点时间（毫秒） |
| face_choose[].sound_end_time | integer | 必须 | 无 | 音频裁剪终点时间（毫秒） |
| face_choose[].sound_insert_time | integer | 必须 | 无 | 裁剪后音频插入时间（毫秒） |
| face_choose[].sound_volume | number | 可选 | 1 | 音频音量大小，取值范围 [0, 2] |
| face_choose[].original_audio_volume | number | 可选 | 1 | 原始视频音量大小，取值范围 [0, 2] |
| external_task_id | string | 可选 | 无 | 用户自定义任务ID，单用户下需保证唯一性 |
| callback_url | string | 可选 | 无 | 任务结果回调通知地址 |

### 响应参数

| 字段 | 类型 | 描述 |
| :--- | :--- | :--- |
| code | integer | 错误码 (0 表示成功) |
| message | string | 错误信息 |
| request_id | string | 请求ID |
| data | object | 数据对象 |
| data.task_id | string | 任务ID |
| data.task_status | string | 任务状态：`submitted` (已提交), `processing` (处理中), `succeed` (成功), `failed` (失败) |

### 请求示例

```json
{
  "session_id": "session_abc123",
  "face_choose": [
    {
      "face_id": "face_001",
      "sound_file": "https://example.com/audio.mp3",
      "sound_start_time": 0,
      "sound_end_time": 5000,
      "sound_insert_time": 0,
      "sound_volume": 1.0,
      "original_audio_volume": 0.5
    }
  ]
}
```

---

## 3. 查询任务

**接口地址：** `GET /kling/v1/videos/advanced-lip-sync/:task_id`

**功能描述：** 根据任务 ID 查询对口型任务的状态和结果。

**认证方式：** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

### 请求路径参数

| 字段 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| task_id | string | 必须 | 任务 ID，由创建任务接口返回 |

### 响应参数

| 字段 | 类型 | 描述 |
| :--- | :--- | :--- |
| code | integer | 错误码 (0 表示成功) |
| message | string | 错误信息 |
| request_id | string | 请求ID |
| data | object | 数据对象 |
| data.task_id | string | 任务ID |
| data.task_status | string | 任务状态 |
| data.task_status_msg | string | 任务状态信息 |
| data.task_result | object | 任务结果（仅成功时返回） |
| data.task_result.videos | array | 生成的视频列表 |
| data.task_result.videos[].id | string | 生成的视频ID |
| data.task_result.videos[].url | string | 生成视频的URL |
| data.task_result.videos[].duration | string | 视频总时长（秒） |
| data.created_at | integer | 任务创建时间（毫秒） |
| data.updated_at | integer | 任务更新时间（毫秒） |

### 响应示例

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
          "id": "vid_lipsync_123",
          "url": "https://example.com/lipsync_video.mp4",
          "duration": "5"
        }
      ]
    },
    "created_at": 1722769557708,
    "updated_at": 1722769557708
  }
}
```
