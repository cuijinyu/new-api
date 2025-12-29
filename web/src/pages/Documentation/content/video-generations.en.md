# Create Video Generation Task

Submit a video generation task, supporting both text-to-video and image-to-video. Returns a Task ID, which can be used to query the status via the GET interface.

## API Details

**Endpoint:** `POST /v1/video/generations`

**Description:** Submits a video generation request. This is an asynchronous interface. After receiving the Task ID, you need to call the corresponding query interface to get the progress and result.

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## Request Parameters

### Body Parameters

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| model | string | Yes | The model ID to use | `kling-v1`, `gen-3-alpha` |
| prompt | string | Yes | The prompt for video generation | `A golden retriever running on the grass` |
| image | string | No | Image URL or Base64 (for image-to-video) | `https://example.com/image.jpg` |
| size | string | No | Video dimensions | `1024x1024`, `16:9` |
| quality | string | No | Video quality | `standard`, `hd` |
| duration | integer | No | Desired video duration in seconds | `5`, `10` |

---

## Response Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| id | string | Unique task identifier (Task ID) |
| object | string | Object type, always `video.generation` |
| created | integer | Unix timestamp of creation |
| status | string | Initial task status (`pending`, `processing`) |

---

## Code Examples

### Python (OpenAI-style call)

```python
import requests

url = "https://your-domain.com/v1/video/generations"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}
data = {
    "model": "kling-v1",
    "prompt": "A golden retriever running on the grass",
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
      summary: Create Video Generation Task
      description: Submit a video generation task, supporting both text-to-video and image-to-video.
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
          description: Task submitted successfully
```
