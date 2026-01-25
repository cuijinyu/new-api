# Kling 文生视频

使用 Kling 模型从文本描述生成视频。

## 接口详情

### 1. 提交文生视频任务

**接口地址：** `POST /kling/v1/videos/text2video`

**功能描述：** 提交一个视频生成任务。视频生成是异步过程，提交成功后会返回 `task_id`，之后需要通过查询接口获取结果。

**认证方式：** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 请求参数

### Body 参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 | 示例 |
|--------|------|------|--------|------|------|
| model | string | 是 | - | 使用的模型 ID | `kling-v1` |
| prompt | string | 是 | - | 视频描述文本 | `一只在森林里奔跑的小鹿` |
| image_tail | string | 否 | - | 尾帧图片 URL 或 Base64 编码，用于指定视频结束画面 | `https://example.com/end.jpg` |
| negative_prompt | string | 否 | - | 负向提示词 | `模糊, 水印` |
| cfg_scale | float | 否 | 5.0 | 提示词相关性 | 0.0 - 100.0 |
| mode | string | 否 | `std` | 生成模式 | `std` (标准), `pro` (专业) |
| aspect_ratio | string | 否 | `16:9` | 视频比例 | `16:9`, `9:16`, `1:1` |
| duration | string | 否 | `5` | 视频时长（秒） | `5`, `10` |

---

## 响应参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| code | integer | 状态码 (0 表示成功) |
| message | string | 提示信息 |
| data | object | 数据对象 |
| data.task_id | string | 任务 ID，用于后续查询结果 |
| data.task_status | string | 任务状态 (`submitted`, `processing`, `succeed`, `failed`) |

---

### 2. 查询任务结果

**接口地址：** `GET /kling/v1/videos/text2video/:task_id`

**响应示例：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "task_id": "xxx",
    "task_status": "succeed",
    "task_result": {
      "videos": [
        {
          "url": "https://example.com/video.mp4",
          "duration": "5"
        }
      ]
    }
  }
}
```

---

## 代码示例

### Curl 示例

```bash
# 1. 提交任务
curl https://your-domain.com/kling/v1/videos/text2video \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "kling-v1",
    "prompt": "一只在森林里奔跑的小鹿",
    "mode": "std",
    "aspect_ratio": "16:9",
    "duration": "5"
  }'

# 2. 查询结果 (替换 TASK_ID)
curl https://your-domain.com/kling/v1/videos/text2video/TASK_ID \
  -H "Authorization: Bearer $YOUR_API_KEY"
```
