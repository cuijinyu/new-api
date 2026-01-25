# 获取视频生成任务状态

查询视频生成任务的状态和结果。

## 接口详情

**接口地址：** `GET /v1/video/generations/:task_id`

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

## 任务状态说明

| 状态码 | 说明 |
|--------|------|
| `queued` | 任务正在排队中 |
| `in_progress` | 视频生成中 |
| `completed` | 任务已完成 |
| `failed` | 任务失败 |

---

## 响应参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| id | string | 任务唯一标识符 |
| object | string | 对象类型 |
| created | integer | 创建时间的 Unix 时间戳 |
| status | string | 任务状态 |
| data | array | 生成的结果列表 (仅在 `completed` 时存在) |
| data.url | string | 视频下载或在线播放地址 |
| error | object | 错误信息 (仅在 `failed` 时存在) |

---

## 代码示例

### Curl 示例

```bash
curl https://your-domain.com/v1/video/generations/YOUR_TASK_ID \
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
  /v1/video/generations/{task_id}:
    get:
      summary: 获取视频生成任务状态
      description: 查询视频生成任务的状态和结果。
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
