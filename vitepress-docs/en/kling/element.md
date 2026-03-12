# Kling Elements

Elements are used to reuse consistent character/object identities. You can create custom elements from images or videos and reference them in subsequent Kling video tasks.

## API Overview

This project transparently proxies Kling official element APIs to the following paths:

1. Create Element: POST /kling/v1/general/advanced-custom-elements
2. Get Custom Element (Single): GET /kling/v1/general/advanced-custom-elements/:id
3. List Custom Elements: GET /kling/v1/general/advanced-custom-elements
4. List Preset Elements: GET /kling/v1/general/advanced-presets-elements
5. Delete Element: POST /kling/v1/general/delete-elements

::: tip Notes
1. Responses are the upstream raw JSON and are not wrapped in OpenAI-style format.
2. In the current implementation, Element APIs are treated as management endpoints: no billing and no task-table persistence.
:::

## Authentication

Authentication method: Bearer Token

```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 1. Create Element

**Endpoint:** POST /kling/v1/general/advanced-custom-elements

**Description:** Create a custom element (image reference or video reference). The request usually returns a task_id. You can query the final status and element_id via the single-item query endpoint.

### Request Parameters (Body)

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| element_name | string | Required | Element name |
| element_description | string | Required | Element description |
| reference_type | string | Required | image_refer / video_refer |
| element_image_list | object | Conditionally required | Required when reference_type=image_refer |
| element_video_list | object | Conditionally required | Required when reference_type=video_refer |
| element_voice_id | string | Optional | Voice ID |
| tag_list | array | Optional | Tag list |
| callback_url | string | Optional | Callback URL |
| external_task_id | string | Optional | Business-side custom task ID |

### element_image_list

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| frontal_image | string | Required | Front image (URL or Base64) |
| refer_images | array | Required | Reference image list |
| refer_images[].image_url | string | Required | Reference image (URL or Base64) |

### element_video_list

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| refer_videos | array | Required | Reference video list |
| refer_videos[].video_url | string | Required | Video URL |

### tag_list (common tags)

| tag_id | tag_name |
| :--- | :--- |
| o_101 | Meme |
| o_102 | Character |
| o_103 | Animal |
| o_104 | Prop |
| o_105 | Clothing |
| o_106 | Scene |
| o_107 | VFX |
| o_108 | Other |

### cURL Examples

```bash
curl -X POST "https://www.ezmodel.cloud/kling/v1/general/advanced-custom-elements" \
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

```bash
curl -X POST "https://www.ezmodel.cloud/kling/v1/general/advanced-custom-elements" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "element_name": "your_element_name",
    "element_description": "dadongbei",
    "reference_type": "video_refer",
    "element_video_list": {
      "refer_videos": [
        {"video_url": "https://example.com/video.mp4"}
      ]
    }
  }'
```

---

## 2. Get Custom Element (Single)

**Endpoint:** GET /kling/v1/general/advanced-custom-elements/:id

**Description:** Query task status and result by task_id (or external_task_id).

### Path Parameters

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| id | string | Required | task_id or external_task_id |

### cURL Example

```bash
curl -sS -H "Authorization: Bearer YOUR_API_TOKEN" \
  "https://www.ezmodel.cloud/kling/v1/general/advanced-custom-elements/860434405402222626"
```

---

## 3. List Custom Elements

**Endpoint:** GET /kling/v1/general/advanced-custom-elements

### Query Parameters

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| pageNum | int | No | 1 | Page number |
| pageSize | int | No | 30 | Items per page |

### cURL Example

```bash
curl -sS -H "Authorization: Bearer YOUR_API_TOKEN" \
  "https://www.ezmodel.cloud/kling/v1/general/advanced-custom-elements?pageNum=1&pageSize=2"
```

---

## 4. List Preset Elements

**Endpoint:** GET /kling/v1/general/advanced-presets-elements

### Query Parameters

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| pageNum | int | No | 1 | Page number |
| pageSize | int | No | 30 | Items per page |

### cURL Example

```bash
curl -sS -H "Authorization: Bearer YOUR_API_TOKEN" \
  "https://www.ezmodel.cloud/kling/v1/general/advanced-presets-elements?pageNum=1&pageSize=2"
```

### Expected Differences in Responses

Under the same pageNum/pageSize values, these two listing endpoints should return different content:

1. Preset list is usually platform preset data (owned_by is commonly kling).
2. Custom list contains data created under the current account (owned_by is your account ID).

---

## 5. Delete Element

**Endpoint:** POST /kling/v1/general/delete-elements

### Request Parameters (Body)

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| element_id | string | Required | Element ID to delete |

### cURL Example

```bash
curl -X POST "https://ezmodel.cloud/kling/v1/general/delete-elements" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"element_id":"123456"}'
```
