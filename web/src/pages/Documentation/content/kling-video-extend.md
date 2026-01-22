# 可灵 Kling 视频延长 (Video Extend)

对现有视频进行延长，生成更长时长的视频内容。

## 1. 创建任务

**接口地址：** `POST /kling/v1/videos/video-extend`

**功能描述：** 提交一个视频延长任务。视频延长是异步过程，提交成功后会返回 `task_id`，之后需要通过查询接口获取结果。

**认证方式：** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

### 请求参数 (Body)

| 字段 | 类型 | 必填 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| video_id | string | 必须 | 无 | 视频ID，需要延长的原始视频ID |
| prompt | string | 可选 | 空 | 正向文本提示词，用于引导视频延长的方向。不能超过2500个字符。 |
| negative_prompt | string | 可选 | 空 | 负向文本提示词，用于排除不需要的内容。不能超过2500个字符。 |
| cfg_scale | number | 可选 | 0.5 | 提示词参考强度，取值范围 [0, 1]。值越大，生成内容越贴近提示词。 |
| callback_url | string | 可选 | 无 | 任务结果回调通知地址。 |

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
  "video_id": "vid_original_123456",
  "prompt": "继续展现日落的美景，镜头缓缓拉远",
  "negative_prompt": "模糊, 抖动",
  "cfg_scale": 0.5
}
```

---

## 2. 查询任务 (单个)

**接口地址：** `GET /kling/v1/videos/video-extend/:task_id`

**功能描述：** 根据任务 ID 查询视频延长任务的状态和结果。

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
| request_id | string | 请求ID，用于跟踪请求、排查问题 |
| data | object | 数据对象 |
| data.task_id | string | 任务ID |
| data.task_status | string | 任务状态：`submitted` (已提交), `processing` (处理中), `succeed` (成功), `failed` (失败) |
| data.task_status_msg | string | 任务状态信息，当任务失败时展示失败原因 |
| data.task_result | object | 任务结果（仅成功时返回） |
| data.task_result.videos | array | 生成的视频列表 |
| data.task_result.videos[].id | string | 生成的视频ID，全局唯一 |
| data.task_result.videos[].url | string | 生成视频的URL（注意：视频会在30天后被清理，请及时转存） |
| data.task_result.videos[].duration | string | 视频总时长，单位秒 |
| data.created_at | integer | 任务创建时间，Unix时间戳（毫秒） |
| data.updated_at | integer | 任务更新时间，Unix时间戳（毫秒） |

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
