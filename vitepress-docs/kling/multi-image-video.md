# Kling 多图参考生视频

使用 Kling 模型结合多张图片生成视频。最多支持 4 张图片作为参考，通过 `image_list` 参数传入。

## 接口详情

**接口地址：** `POST /kling/v1/videos/multi-image2video`

**功能描述：** 提交一个多图参考生视频任务。视频生成是异步过程，提交成功后会返回 `task_id`，之后需要通过查询接口获取结果。

**认证方式：** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 请求参数

### Body 参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 | 示例 |
|--------|------|------|--------|------|------|
| model | string | 是 | - | 使用的模型 ID | `kling-v1-6` |
| image_list | array | 是 | - | 输入图片的列表，最多支持 4 张 | `[{"image": "url1"}, {"image": "url2"}]` |
| prompt | string | 是 | - | 视频描述文本（引导图片动态） | `让图片中的两个人物在未来的城市中一起跳舞` |
| negative_prompt | string | 否 | - | 负向提示词 | `模糊, 水印` |
| mode | string | 否 | `std` | 生成模式 | `std`, `pro` |
| aspect_ratio | string | 否 | `16:9` | 视频比例 | `16:9`, `9:16`, `1:1` |
| duration | string | 否 | `5` | 视频时长（秒） | `5`, `10` |
| callback_url | string | 否 | - | 任务结果回调通知地址 | `https://your-callback.com/api` |
| external_task_id | string | 否 | - | 自定义任务 ID | `my-unique-task-001` |

---

## 响应参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| code | integer | 状态码 (0 表示成功) |
| message | string | 提示信息 |
| data | object | 数据对象 |
| data.task_id | string | 任务 ID |
| data.task_status | string | 任务状态 (`submitted`, `processing`, `succeed`, `failed`) |

---

## 代码示例

### Curl 示例

```bash
curl https://your-domain.com/kling/v1/videos/multi-image2video \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "kling-v1-6",
    "image_list": [
      {"image": "https://example.com/image1.jpg"},
      {"image": "https://example.com/image2.jpg"}
    ],
    "prompt": "让人物动起来",
    "duration": "5"
  }'
```

---

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /kling/v1/videos/multi-image2video:
    post:
      summary: Kling 多图参考生视频
      description: 使用 Kling 模型结合多张图片生成视频。
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                model:
                  type: string
                image_list:
                  type: array
                  items:
                    type: object
                    properties:
                      image:
                        type: string
                prompt:
                  type: string
      responses:
        '200':
          description: 成功提交任务
```
