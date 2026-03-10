# Kling 主体 (Element)

主体（Element）用于在视频生成时稳定复用同一个角色/物体外观。你可以通过「图片参考」或「视频参考」创建自定义主体，并在后续视频生成（如 Omni Video 的 `element_list`）中引用。

::: tip 本项目说明
- 本项目已新增一套 Element 转发接口，调用路径带前缀：`/kling/v1/...`（下方“本项目接口”）。
- 本项目不会对返回体做 OpenAI 风格封装：响应为可灵上游的原始 JSON。
- 当前实现把 Element 接口按“免费管理接口”处理：不扣费、不写入任务表（仅转发）。
:::

---

## 鉴权

本项目接口使用平台自身的 Token 鉴权：

```http
Authorization: Bearer <NEW_API_TOKEN>
```

> 注意：这里的 Token 是本项目的访问 Token，不是可灵官方 API Key。

---

## 1. 创建主体

**本项目接口：** `POST /kling/v1/general/advanced-custom-elements`

**上游接口：** `POST /v1/general/advanced-custom-elements`

**功能描述：** 创建一个自定义主体（图片定制 / 视频定制）。是否异步以可灵上游为准；通常会返回 `task_id`，后续可用查询接口获取最终 `element_id`。

### 请求头

| Header | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| Content-Type | string | 必填 | application/json | 数据交换格式 |
| Authorization | string | 必填 | - | 本项目 Token 鉴权 |

### 请求参数 (Body)

请求体保持与可灵官方一致（本项目直接透传）。

| 字段 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| element_name | string | 必填 | 主体名称（不超过 20 个字符） |
| element_description | string | 必填 | 主体描述（不超过 100 个字符） |
| reference_type | string | 必填 | `video_refer` / `image_refer` |
| element_image_list | object | 条件必填 | `reference_type=image_refer` 时必填 |
| element_video_list | object | 条件必填 | `reference_type=video_refer` 时必填 |
| element_voice_id | string | 可选 | 主体音色 ID（仅视频定制主体支持绑定） |
| tag_list | array | 可选 | 主体标签列表 |
| callback_url | string | 可选 | 任务回调地址（由可灵上游回调） |
| external_task_id | string | 可选 | 业务侧自定义任务 ID（单用户下需唯一） |

#### element_image_list（图片参考主体）

| 字段 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| frontal_image | string | 必填 | 正面参考图（URL 或 Base64） |
| refer_images | array | 必填 | 其他参考图列表（1～3 张） |
| refer_images[].image_url | string | 必填 | 参考图（URL 或 Base64） |

#### element_video_list（视频参考主体）

| 字段 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| refer_videos | array | 必填 | 参考视频列表（至多 1 段） |
| refer_videos[].video_url | string | 必填 | 视频 URL |

#### tag_list（主体标签）

| tag_id | tag_name |
| :--- | :--- |
| o_101 | 热梗 |
| o_102 | 人物 |
| o_103 | 动物 |
| o_104 | 道具 |
| o_105 | 服饰 |
| o_106 | 场景 |
| o_107 | 特效 |
| o_108 | 其他 |

### 响应

响应为可灵上游原始 JSON（通常包含 `code/message/request_id/data`，`data` 内可能有 `task_id`/`task_status` 等字段）。

### 调用示例

创建图片定制主体：

```bash
curl --location 'https://<YOUR_HOST>/kling/v1/general/advanced-custom-elements' \
	--header 'Authorization: Bearer <NEW_API_TOKEN>' \
	--header 'Content-Type: application/json' \
	--data '{
		"element_name": "my_element",
		"element_description": "desc",
		"reference_type": "image_refer",
		"element_image_list": {
			"frontal_image": "image_url_0",
			"refer_images": [
				{"image_url": "image_url_1"},
				{"image_url": "image_url_2"}
			]
		},
		"tag_list": [{"tag_id": "o_102"}]
	}'
```

---

## 2. 查询自定义主体（单个）

**本项目接口：** `GET /kling/v1/general/advanced-custom-elements/{id}`

**上游接口：** `GET /v1/general/advanced-custom-elements/{id}`

**功能描述：** 查询创建主体任务的状态与结果。`id` 通常为创建接口返回的 `task_id`，也可能支持 `external_task_id`（以可灵上游为准）。

### 路径参数

| 字段 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| id | string | 必填 | `task_id` 或 `external_task_id` |

### 调用示例

```bash
curl --location 'https://<YOUR_HOST>/kling/v1/general/advanced-custom-elements/842250903629086785' \
	--header 'Authorization: Bearer <NEW_API_TOKEN>'
```

---

## 3. 查询自定义主体（列表）

**本项目接口：** `GET /kling/v1/general/advanced-custom-elements`

**上游接口：** `GET /v1/general/advanced-custom-elements`

### 查询参数

| 字段 | 类型 | 必填 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| pageNum | int | 可选 | 1 | 页码（通常范围 [1, 1000]） |
| pageSize | int | 可选 | 30 | 每页数量（通常范围 [1, 500]） |

### 调用示例

```bash
curl --location 'https://<YOUR_HOST>/kling/v1/general/advanced-custom-elements?pageNum=1&pageSize=30' \
	--header 'Authorization: Bearer <NEW_API_TOKEN>'
```

---

## 4. 查询官方主体（列表）

**本项目接口：** `GET /kling/v1/general/advanced-presets-elements`

**上游接口：** `GET /v1/general/advanced-presets-elements`

### 查询参数

| 字段 | 类型 | 必填 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| pageNum | int | 可选 | 1 | 页码（通常范围 [1, 1000]） |
| pageSize | int | 可选 | 30 | 每页数量（通常范围 [1, 500]） |

### 调用示例

```bash
curl --location 'https://<YOUR_HOST>/kling/v1/general/advanced-presets-elements?pageNum=1&pageSize=30' \
	--header 'Authorization: Bearer <NEW_API_TOKEN>'
```

---

## 5. 删除自定义主体

**本项目接口：** `POST /kling/v1/general/delete-elements`

**上游接口：** `POST /v1/general/delete-elements`

### 请求头

| Header | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| Content-Type | string | 必填 | application/json | 数据交换格式 |
| Authorization | string | 必填 | - | 本项目 Token 鉴权 |

### 请求参数 (Body)

| 字段 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| element_id | string | 必填 | 要删除的主体 ID |

### 调用示例

```bash
curl --location 'https://<YOUR_HOST>/kling/v1/general/delete-elements' \
	--header 'Authorization: Bearer <NEW_API_TOKEN>' \
	--header 'Content-Type: application/json' \
	--data '{
		"element_id": "123456"
	}'
```
