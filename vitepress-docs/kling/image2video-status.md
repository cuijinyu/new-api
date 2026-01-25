# 获取 Kling 图生视频任务状态

查询 Kling 图生视频任务的状态和结果。

## 接口详情

**接口地址：** `GET /kling/v1/videos/image2video/:task_id`

**功能描述：** 通过提交任务时返回的 `task_id` 查询视频生成的进度和最终结果。

**认证方式：** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 请求参数

### Path 参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| task_id | string | 是 | 提交任务时返回的任务唯一标识符 |

---

## 响应参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| code | string | 状态码 (`success` 表示成功) |
| message | string | 提示信息 |
| data | object | 任务详情对象 |
| data.task_id | string | 任务 ID |
| data.status | string | 统一任务状态：`SUBMITTED`, `IN_PROGRESS`, `SUCCESS`, `FAILURE` |
| data.progress | string | 任务进度 (如 "100%") |
| data.data | object | Kling 原始响应数据 |
| data.data.data.task_status | string | Kling 任务状态：`submitted`, `processing`, `succeed`, `failed` |
| data.data.data.task_result.videos | array | 生成的视频列表 |
| data.data.data.task_result.videos[0].url | string | 视频下载/播放地址 |
| data.data.data.task_result.videos[0].duration | string | 视频时长 |

---

## 响应示例

```json
{
  "code": "success",
  "message": "",
  "data": {
    "task_id": "842250903629086785",
    "status": "SUCCESS",
    "progress": "100%",
    "data": {
      "code": 0,
      "data": {
        "task_id": "842250903629086785",
        "task_status": "succeed",
        "task_result": {
          "videos": [
            {
              "id": "842250903708762200",
              "url": "https://v16-kling-fdl.klingai.com/...",
              "duration": "5.1"
            }
          ]
        }
      }
    }
  }
}
```

---

## 代码示例

### Curl 示例

```bash
curl https://your-domain.com/kling/v1/videos/image2video/YOUR_TASK_ID \
  -H "Authorization: Bearer $YOUR_API_KEY"
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
  /kling/v1/videos/image2video/{task_id}:
    get:
      summary: 获取 Kling 图生视频任务状态
      description: 查询 Kling 图生视频任务的状态和结果。
      parameters:
        - name: task_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: 成功获取任务状态
```
