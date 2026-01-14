# 可灵 Kling 动作控制 (Motion Control)

通过上传参考图像和参考视频，让图像中的人物执行视频中的动作。

## 1. 创建任务

**接口地址：** `POST /v1/videos/motion-control`

**功能描述：** 提交一个动作控制视频生成任务。视频生成是异步过程，提交成功后会返回 `task_id`，之后需要通过查询接口获取结果。

**认证方式：** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

### 请求参数 (Body)

| 字段 | 类型 | 必填 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| prompt | string | 可选 | 空 | 文本提示词，可包含正向描述和负向描述。可通过提示词为画面增加元素、实现运镜效果等。不能超过2500个字符。 |
| image_url | string | 必须 | 无 | 参考图像，生成视频中的人物、背景等元素均以参考图为准。支持传入图片Base64编码或图片URL。图片格式支持 .jpg / .jpeg / .png。图片大小不超过10MB。<br/><br/>**注意：** 如果使用 Base64，请直接传递编码后的字符串，**不要**包含 `data:image/png;base64,` 等前缀。 |
| video_url | string | 必须 | 无 | 参考视频的获取链接。生成视频中的人物动作与参考视频一致。支持 .mp4/.mov，大小不超过100MB，时长不短于3秒。 |
| keep_original_sound | string | 可选 | yes | 是否保留视频原声。枚举值：`yes`, `no`。 |
| character_orientation | string | 必须 | 无 | 生成视频中人物的朝向。枚举值：`image` (与图片一致), `video` (与视频一致)。 |
| mode | string | 必须 | 无 | 生成视频的模式。枚举值：`std` (标准模式), `pro` (专家模式)。 |
| callback_url | string | 可选 | 无 | 任务结果回调通知地址。 |
| external_task_id | string | 可选 | 无 | 用户自定义任务ID，单用户下需保证唯一性。 |

### 响应参数

| 字段 | 类型 | 描述 |
| :--- | :--- | :--- |
| code | integer | 错误码 (0 表示成功) |
| message | string | 错误信息 |
| request_id | string | 请求ID |
| data | object | 数据对象 |
| data.task_id | string | 任务ID |
| data.task_status | string | 任务状态：`submitted` (已提交), `processing` (处理中), `succeed` (成功), `failed` (失败) |

---

## 2. 查询任务 (单个)

**接口地址：** `GET /v1/videos/motion-control/{task_id}`

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
