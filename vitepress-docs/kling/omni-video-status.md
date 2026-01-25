# 获取 Kling 全能视频任务状态

查询 Kling 全能视频任务的状态和结果。

## 接口详情

**接口地址：** `GET /kling/v1/videos/omni-video/:task_id`

**功能描述：** 通过提交任务时返回的 `task_id` 查询全能视频生成的进度和结果。

**认证方式：** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 响应参数

查询成功后返回统一任务状态对象。

| 参数名 | 类型 | 说明 |
|--------|------|------|
| code | string | 状态码 (`success` 表示成功) |
| message | string | 提示信息 |
| data | object | 任务详情对象 |
| data.task_id | string | 任务 ID |
| data.status | string | 任务状态：`SUBMITTED`, `IN_PROGRESS`, `SUCCESS`, `FAILURE` |
| data.progress | string | 任务进度 (如 "100%") |
| data.data | object | Kling 原始响应数据 (包含 `task_result` 等) |

---

## 响应示例

```json
{
  "code": "success",
  "data": {
    "task_id": "842250903629086785",
    "status": "SUCCESS",
    "progress": "100%",
    "data": {
      "code": 0,
      "message": "HTTP_OK",
      "request_id": "...",
      "data": {
        "task_id": "842250903629086785",
        "task_status": "succeed",
        "task_result": {
          "videos": [
            {
              "id": "...",
              "url": "https://...",
              "duration": "5.0"
            }
          ]
        }
      }
    }
  }
}
```
