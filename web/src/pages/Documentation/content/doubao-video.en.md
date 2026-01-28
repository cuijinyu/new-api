# Doubao Video Generation

Create video generation tasks using Doubao Seedance models, supporting both text-to-video and image-to-video.

## API Details

**Endpoint:** `POST /v1/video/generations`

**Description:** Create video generation tasks using Doubao Seedance series models. Supports Text-to-Video (T2V) and Image-to-Video (I2V) to generate high-quality AI video content.

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## Supported Models

| Model Name | Description | Features |
|------------|-------------|----------|
| `doubao-seedance-1-0-pro-250528` | Seedance Pro Version | High-quality video generation for professional use |
| `doubao-seedance-1-0-lite-t2v` | Seedance Lite Text-to-Video | Lightweight version for text-to-video |
| `doubao-seedance-1-0-lite-i2v` | Seedance Lite Image-to-Video | Lightweight version for image-to-video |

---

## Request Parameters

### Body Parameters

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| model | string | Yes | Model ID | `doubao-seedance-1-0-pro-250528` |
| prompt | string | Yes | Video generation prompt | `A cute kitten playing in the garden` |
| images | array | No | Array of image URLs (for image-to-video) | `["https://example.com/image.jpg"]` |

---

## Response Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| task_id | string | Unique task identifier for querying task status |

---

## Code Examples

### cURL

```bash
curl -X POST "https://your-domain.com/v1/video/generations" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seedance-1-0-pro-250528",
    "prompt": "A cute kitten playing in a sunny garden, warm and cozy atmosphere"
  }'
```

### Python

```python
import requests
import json

url = "https://your-domain.com/v1/video/generations"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}

# Text-to-Video example
data = {
    "model": "doubao-seedance-1-0-pro-250528",
    "prompt": "A cute kitten playing in a sunny garden, warm and cozy atmosphere"
}

response = requests.post(url, headers=headers, json=data)
result = response.json()
print(json.dumps(result, indent=2))

# Get task_id for subsequent queries
task_id = result.get("task_id")
print(f"Task ID: {task_id}")
```

### Python (Image-to-Video)

```python
import requests
import json

url = "https://your-domain.com/v1/video/generations"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}

# Image-to-Video example
data = {
    "model": "doubao-seedance-1-0-lite-i2v",
    "prompt": "Make the person in the image smile and wave",
    "images": ["https://example.com/your-image.jpg"]
}

response = requests.post(url, headers=headers, json=data)
result = response.json()
print(json.dumps(result, indent=2))
```

### JavaScript

```javascript
const response = await fetch('https://your-domain.com/v1/video/generations', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer YOUR_API_KEY',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    model: 'doubao-seedance-1-0-pro-250528',
    prompt: 'A cute kitten playing in a sunny garden, warm and cozy atmosphere'
  })
});

const result = await response.json();
console.log('Task ID:', result.task_id);
```

### Go

```go
package main

import (
    "bytes"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
)

func main() {
    url := "https://your-domain.com/v1/video/generations"
    
    payload := map[string]interface{}{
        "model":  "doubao-seedance-1-0-pro-250528",
        "prompt": "A cute kitten playing in a sunny garden, warm and cozy atmosphere",
    }
    
    jsonData, _ := json.Marshal(payload)
    req, _ := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
    req.Header.Set("Authorization", "Bearer YOUR_API_KEY")
    req.Header.Set("Content-Type", "application/json")
    
    client := &http.Client{}
    resp, err := client.Do(req)
    if err != nil {
        panic(err)
    }
    defer resp.Body.Close()
    
    body, _ := io.ReadAll(resp.Body)
    fmt.Println(string(body))
}
```

---

## Response Example

### Success Response (200)

```json
{
  "task_id": "task_abc123xyz456"
}
```

---

## Notes

1. **Async Processing**: Video generation is asynchronous. After submitting a task, use the query API to get the results
2. **Model Selection**: 
   - Use `doubao-seedance-1-0-lite-t2v` for text-to-video
   - Use `doubao-seedance-1-0-lite-i2v` for image-to-video
   - Use `doubao-seedance-1-0-pro-250528` for higher quality output
3. **Prompt Tips**: Detailed and specific descriptions yield better generation results
4. **Image Requirements**: For image-to-video, ensure image URLs are publicly accessible

---

## Related APIs

- [Query Doubao Video Task Status](/docs/doubao-video-status)
