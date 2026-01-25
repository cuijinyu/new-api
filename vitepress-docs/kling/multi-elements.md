# 可灵 Kling 多模态视频编辑 (Multi-Elements)

通过自然语言对视频进行编辑，支持增加、替换、删除视频中的元素。

## 工作流程

多模态视频编辑需要以下步骤：
1. **初始化视频** - 上传待编辑的视频
2. **标记选区**（可选）- 标记需要编辑的视频元素
3. **预览选区**（可选）- 预览标记的选区效果
4. **创建任务** - 提交视频编辑任务

---

## 1. 初始化待编辑视频

**接口地址：** `POST /kling/v1/videos/multi-elements/init-selection`

**功能描述：** 初始化待编辑的视频，获取会话ID用于后续操作。

**认证方式：** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

### 请求参数 (Body)

| 字段 | 类型 | 必填 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| video_id | string | 可选 | 空 | 视频ID，从历史作品中选择，仅支持30天内生成的视频。与 `video_url` 二选一。 |
| video_url | string | 可选 | 无 | 视频URL。仅支持 MP4 和 MOV 格式。时长需 ≥2s且≤5s，或 ≥7s且≤10s。宽高尺寸需介于 720px 和 2160px 之间。仅支持 24、30 或 60fps。与 `video_id` 二选一。 |

### 响应参数

| 字段 | 类型 | 描述 |
| :--- | :--- | :--- |
| code | integer | 错误码 (0 表示成功) |
| message | string | 错误信息 |
| request_id | string | 请求ID |
| data.status | integer | 拒识码，非0为识别失败 |
| data.session_id | string | 会话ID，有效期24小时 |
| data.fps | number | 解析后视频的帧率 |
| data.original_duration | integer | 解析后视频的时长 |
| data.width | integer | 解析后视频的宽度 |
| data.height | integer | 解析后视频的高度 |
| data.total_frame | integer | 解析后视频的总帧数 |
| data.normalized_video | string | 初始化后的视频URL |

### 响应示例

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

## 2. 增加视频选区

**接口地址：** `POST /kling/v1/videos/multi-elements/add-selection`

**功能描述：** 在视频帧中标记需要编辑的区域。

### 请求参数 (Body)

| 字段 | 类型 | 必填 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| session_id | string | 必须 | 无 | 会话ID |
| frame_index | integer | 必须 | 无 | 帧号，最多支持10个标记帧 |
| points | array | 必须 | 无 | 点选坐标数组 |
| points[].x | number | 必须 | 无 | X坐标，取值范围 [0, 1] |
| points[].y | number | 必须 | 无 | Y坐标，取值范围 [0, 1]，[0,0] 代表画面左上角 |

### 响应参数

| 字段 | 类型 | 描述 |
| :--- | :--- | :--- |
| data.status | integer | 拒识码 |
| data.session_id | string | 会话ID |
| data.res.frame_index | integer | 帧号 |
| data.res.rle_mask_list | array | RLE蒙版列表，包含图像分割结果 |

---

## 3. 删减视频选区

**接口地址：** `POST /kling/v1/videos/multi-elements/delete-selection`

**功能描述：** 删除已标记的选区点。

### 请求参数 (Body)

| 字段 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| session_id | string | 必须 | 会话ID |
| frame_index | integer | 必须 | 帧号 |
| points | array | 必须 | 需删除的点选坐标，需与增加选区时完全一致 |

---

## 4. 清除视频选区

**接口地址：** `POST /kling/v1/videos/multi-elements/clear-selection`

**功能描述：** 清除所有已标记的选区。

### 请求参数 (Body)

| 字段 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| session_id | string | 必须 | 会话ID |

---

## 5. 预览已选区视频

**接口地址：** `POST /kling/v1/videos/multi-elements/preview-selection`

**功能描述：** 预览已标记选区的视频效果。

### 请求参数 (Body)

| 字段 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| session_id | string | 必须 | 会话ID |

### 响应参数

| 字段 | 类型 | 描述 |
| :--- | :--- | :--- |
| data.res.video | string | 含 mask 的视频URL |
| data.res.video_cover | string | 含 mask 的视频封面URL |
| data.res.tracking_output | string | 每一帧 mask 结果 |

---

## 6. 创建任务

**接口地址：** `POST /kling/v1/videos/multi-elements`

**功能描述：** 创建多模态视频编辑任务。

### 请求参数 (Body)

| 字段 | 类型 | 必填 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| model_name | string | 可选 | kling-v1-6 | 模型名称 |
| session_id | string | 必须 | 无 | 会话ID |
| edit_mode | string | 必须 | 无 | 操作类型：`addition`（增加元素）、`swap`（替换元素）、`removal`（删除元素） |
| image_list | array | 可选 | 空 | 参考图像列表。增加元素时必填（1-2张），替换元素时必填（1张），删除元素时无需填写。 |
| image_list[].image | string | 必须 | 无 | 图片 Base64 或 URL |
| prompt | string | 必须 | 无 | 正向文本提示词，不超过2500字符。使用 `<<<video_1>>>` 指代视频，`<<<image_1>>>` 指代图片。 |
| negative_prompt | string | 可选 | 空 | 负向文本提示词，不超过2500字符 |
| mode | string | 可选 | std | 生成模式：`std`（标准）、`pro`（高品质） |
| duration | string | 可选 | 5 | 生成视频时长：`5` 或 `10` 秒 |
| callback_url | string | 可选 | 空 | 回调通知地址 |
| external_task_id | string | 可选 | 空 | 自定义任务ID |

### 推荐的 Prompt 模板

**增加元素：**
```
基于<<<video_1>>>中的原始内容，以自然生动的方式，将<<<image_1>>>中的【主体描述】，融入<<<video_1>>>的【位置描述】
```

**替换元素：**
```
使用<<<image_1>>>中的【新元素】，替换<<<video_1>>>中的【原元素】
```

**删除元素：**
```
删除<<<video_1>>>中的【元素描述】
```

### 响应参数

| 字段 | 类型 | 描述 |
| :--- | :--- | :--- |
| data.task_id | string | 任务ID |
| data.task_status | string | 任务状态 |
| data.session_id | string | 会话ID |
| data.created_at | integer | 任务创建时间（毫秒） |
| data.updated_at | integer | 任务更新时间（毫秒） |

---

## 7. 查询任务

**接口地址：** `GET /kling/v1/videos/multi-elements/:task_id`

**功能描述：** 查询多模态视频编辑任务的状态和结果。

### 响应参数

| 字段 | 类型 | 描述 |
| :--- | :--- | :--- |
| data.task_id | string | 任务ID |
| data.task_status | string | 任务状态 |
| data.task_status_msg | string | 任务状态信息 |
| data.task_result.videos | array | 生成的视频列表 |
| data.task_result.videos[].id | string | 视频ID |
| data.task_result.videos[].session_id | string | 会话ID |
| data.task_result.videos[].url | string | 视频URL |
| data.task_result.videos[].duration | string | 视频时长（秒） |
