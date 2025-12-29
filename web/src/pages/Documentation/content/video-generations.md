# 创建视频生成任务

提交视频生成任务，支持文生视频和图生视频。返回任务 ID，可通过 GET 接口查询任务状态。

## 接口详情

**接口地址：** `POST /v1/video/generations`

**功能描述：** 提交一个视频生成请求。该接口是一个异步接口，返回任务 ID 后，您需要调用对应的查询接口来获取视频生成进度和结果。

**认证方式：** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 请求参数

### Body 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| model | string | 是 | 使用的模型 ID | `kling-v1`, `gen-3-alpha` |
| prompt | string | 是 | 视频生成提示词 | `一只金毛寻回犬在草地上奔跑` |
| image | string | 否 | 待处理的图片 URL 或 Base64 (用于图生视频) | `https://example.com/image.jpg` |
| size | string | 否 | 视频尺寸 | `1024x1024`, `16:9` |
| quality | string | 否 | 视频质量 | `standard`, `hd` |
| duration | integer | 否 | 期望视频时长（秒） | `5`, `10` |

---

## 响应参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| id | string | 任务唯一标识符 (Task ID) |
| object | string | 对象类型，固定为 `video.generation` |
| created | integer | 创建时间的 Unix 时间戳 |
| status | string | 任务初始状态 (`pending`, `processing`) |

---

## 代码示例

### Python (使用 OpenAI 风格调用)

```python
import requests

url = "https://your-domain.com/v1/video/generations"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}
data = {
    "model": "kling-v1",
    "prompt": "一只金毛寻回犬在草地上奔跑",
    "size": "1024x1024"
}

response = requests.post(url, headers=headers, json=data)
print(response.json())
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
  /v1/video/generations:
    post:
      summary: 创建视频生成任务
      description: 提交视频生成任务，支持文生视频和图生视频。
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                model:
                  type: string
                prompt:
                  type: string
      responses:
        '200':
          description: 成功提交任务
```
