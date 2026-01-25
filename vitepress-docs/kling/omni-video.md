# Kling 全能视频 (Omni Video)

Kling 全能视频是 Kling V1.0 的进阶版本，支持更丰富的多模态输入，包括多张图片、视频参考、主体控制等，能够实现更精确的动作控制和更丰富的视觉表达。

## 接口详情

**接口地址：** `POST /kling/v1/videos/omni-video`

**功能描述：** 提交一个全能视频生成任务。支持混合输入（文本、图片、视频、主体元素）。

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
| prompt | string | 否 | - | 视频描述文本 | `一个在森林里奔跑的小狐狸` |
| negative_prompt | string | 否 | - | 负向提示词 | `模糊, 水印` |
| mode | string | 否 | `std` | 生成模式：`std` (标准), `pro` (专业) | `std`, `pro` |
| duration | string | 否 | `5` | 视频时长（秒）。文生、普通图生仅支持 `5`, `10`；首尾帧模式及视频参考支持 `3-10` | `5`, `10` |
| aspect_ratio | string | 否 | `16:9` | 视频比例 | `16:9`, `9:16`, `1:1` |
| image_list | array | 否 | - | 参考图片列表 | `[{"image_url": "...", "type": "first_frame"}]` |
| video_list | array | 否 | - | 参考视频列表（使用视频参考会增加费用倍率） | `[{"video_url": "...", "refer_type": "feature"}]` |
| element_list | array | 否 | - | 主体元素列表 | `[{"element_id": 123456}]` |
| cfg_scale | float | 否 | 0.5 | 提示词相关性 | 0.0 - 1.0 |
| external_task_id | string | 否 | - | 自定义任务 ID | `my_task_001` |
| callback_url | string | 否 | - | 任务完成后回调地址 | `https://your-api.com/callback` |

### OmniImageItem
| 参数名 | 类型 | 说明 |
|--------|------|------|
| image_url | string | 图片 URL |
| type | string | 图片作用：`first_frame` (首帧), `end_frame` (尾帧) |

### OmniVideoItem
| 参数名 | 类型 | 说明 |
|--------|------|------|
| video_url | string | 视频 URL |
| refer_type | string | 参考类型：仅支持 `feature` (特征参考)，不支持 `base` |
| keep_original_sound | string | 是否保留原声：`yes`, `no` |

---

## 响应参数

提交成功后返回 OpenAI 兼容的 `video` 对象。

| 参数名 | 类型 | 说明 |
|--------|------|------|
| id | string | 任务 ID |
| task_id | string | 任务 ID (兼容性字段) |
| object | string | 对象类型，固定为 `video` |
| model | string | 使用的模型 ID |
| created_at | integer | 创建时间戳 |

---

## 代码示例

### Curl 示例 (混合输入)

```bash
curl https://your-domain.com/kling/v1/videos/omni-video \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "kling-v1",
    "prompt": "让人物动起来",
    "image_list": [
      {
        "image_url": "https://example.com/start.jpg",
        "type": "first_frame"
      }
    ],
    "duration": "5"
  }'
```

### 响应示例

```json
{
  "id": "842250903629086785",
  "task_id": "842250903629086785",
  "object": "video",
  "model": "kling-v1",
  "created_at": 1737367800
}
```
