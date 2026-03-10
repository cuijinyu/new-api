# Kling 主体 (Element)

主体（Element）用于复用固定角色/物体形象。你可以通过图片或视频创建自定义主体，并在后续可灵视频任务中引用。

## 接口说明

本项目将可灵官方主体接口透传到以下路径：

1. 创建主体：POST /kling/v1/general/advanced-custom-elements
2. 查询自定义主体（单个）：GET /kling/v1/general/advanced-custom-elements/:id
3. 查询自定义主体（列表）：GET /kling/v1/general/advanced-custom-elements
4. 查询官方主体（列表）：GET /kling/v1/general/advanced-presets-elements
5. 删除主体：POST /kling/v1/general/delete-elements

::: tip 说明
1. 响应为上游原始 JSON，不做 OpenAI 风格封装。
2. 当前实现中，Element 作为管理接口处理：不扣费，不写任务表。
:::

## 鉴权

认证方式：Bearer Token

```http
Authorization: Bearer YOUR_API_TOKEN
```


---

## 1. 创建主体

**接口地址：** POST /kling/v1/general/advanced-custom-elements

**功能描述：** 创建一个自定义主体（图片参考或视频参考）。提交后通常返回 task_id，可通过单条查询接口查看最终状态和 element_id。

### 请求参数 (Body)

| 字段 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| element_name | string | 必填 | 主体名称 |
| element_description | string | 必填 | 主体描述 |
| reference_type | string | 必填 | image_refer / video_refer |
| element_image_list | object | 条件必填 | reference_type=image_refer 时必填 |
| element_video_list | object | 条件必填 | reference_type=video_refer 时必填 |
| element_voice_id | string | 可选 | 音色 ID |
| tag_list | array | 可选 | 标签列表 |
| callback_url | string | 可选 | 回调地址 |
| external_task_id | string | 可选 | 业务侧任务 ID |

### element_image_list

| 字段 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| frontal_image | string | 必填 | 正面图（URL 或 Base64） |
| refer_images | array | 必填 | 参考图列表 |
| refer_images[].image_url | string | 必填 | 参考图（URL 或 Base64） |

### element_video_list

| 字段 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| refer_videos | array | 必填 | 参考视频列表 |
| refer_videos[].video_url | string | 必填 | 视频 URL |

### tag_list（常用标签）

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

### cURL 示例

```bash
curl -X POST "https://ezmodel.cloud/kling/v1/general/advanced-custom-elements" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "element_name": "local_test_element",
    "element_description": "local test",
    "reference_type": "image_refer",
    "element_image_list": {
      "frontal_image": "https://example.com/a.png",
      "refer_images": [{"image_url": "https://example.com/b.png"}]
    },
    "tag_list": [{"tag_id": "o_102"}]
  }'
```

---

## 2. 查询自定义主体（单个）

**接口地址：** GET /kling/v1/general/advanced-custom-elements/:id

**功能描述：** 查询指定 task_id（或 external_task_id）的任务状态与结果。

### 路径参数

| 字段 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| id | string | 必填 | task_id 或 external_task_id |

### cURL 示例

```bash
curl -sS -H "Authorization: Bearer YOUR_API_TOKEN" \
  "https://ezmodel.cloud/kling/v1/general/advanced-custom-elements/860434405402222626"
```

---

## 3. 查询自定义主体（列表）

**接口地址：** GET /kling/v1/general/advanced-custom-elements

### 查询参数

| 字段 | 类型 | 必填 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| pageNum | int | 否 | 1 | 页码 |
| pageSize | int | 否 | 30 | 每页数量 |

### cURL 示例

```bash
curl -sS -H "Authorization: Bearer YOUR_API_TOKEN" \
  "https://ezmodel.cloud/kling/v1/general/advanced-custom-elements?pageNum=1&pageSize=2"
```

---

## 4. 查询官方主体（列表）

**接口地址：** GET /kling/v1/general/advanced-presets-elements

### 查询参数

| 字段 | 类型 | 必填 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| pageNum | int | 否 | 1 | 页码 |
| pageSize | int | 否 | 30 | 每页数量 |

### cURL 示例

```bash
curl -sS -H "Authorization: Bearer YOUR_API_TOKEN" \
  "https://ezmodel.cloud/kling/v1/general/advanced-presets-elements?pageNum=1&pageSize=2"
```

### 实际返回差异说明

同样 pageNum/pageSize 下，这两个列表接口返回内容应不同：

1. 官方列表一般为平台预置数据（常见 owned_by 为 kling）。
2. 自定义列表为当前账号创建数据（owned_by 为你的账号 ID）。

---

## 5. 删除主体

**接口地址：** POST /kling/v1/general/delete-elements

### 请求参数 (Body)

| 字段 | 类型 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| element_id | string | 必填 | 要删除的主体 ID |

### cURL 示例

```bash
curl -X POST "https://ezmodel.cloud/kling/v1/general/delete-elements" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"element_id":"123456"}'
```
