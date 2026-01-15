# Sora Video Creation

OpenAI-compatible video generation interface, supporting high-quality video generation using Sora models.

## API Details

**Endpoint:** `POST /v1/videos`

**Description:** Create a video generation task using Sora models. Supports text-to-video and image-to-video with controllable parameters like duration, dimensions, and frame rate.

**Reference:** [OpenAI Videos API](https://platform.openai.com/docs/api-reference/videos/create)

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## Request Parameters

### Body Parameters (multipart/form-data)

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| model | string | No | Model/style ID | `sora-1.0`, `sora-turbo` |
| prompt | string | No | Text description prompt | `A golden retriever running on the beach` |
| image | string | No | Image input (URL or Base64) for image-to-video | `https://example.com/image.jpg` |
| duration | number | No | Video duration in seconds | `5.0`, `10.0` |
| width | integer | No | Video width | `1920`, `1280` |
| height | integer | No | Video height | `1080`, `720` |
| fps | integer | No | Video frame rate | `24`, `30`, `60` |
| seed | integer | No | Random seed for reproducible results | `12345` |
| n | integer | No | Number of videos to generate | `1`, `2` |
| response_format | string | No | Response format | `url`, `b64_json` |
| user | string | No | User identifier | `user-123` |
| metadata | object | No | Extended parameters (e.g., negative_prompt, style, quality_level) | `{"style": "cinematic"}` |

---

## Response Parameters

### Success Response (200)

| Parameter | Type | Description |
|-----------|------|-------------|
| id | string | Video task ID |
| object | string | Object type, always `video` |
| model | string | Model name used |
| status | string | Task status: `pending`, `processing`, `completed`, `failed` |
| progress | integer | Progress percentage (0-100) |
| created_at | integer | Creation timestamp (Unix timestamp) |
| seconds | string | Video duration |
| completed_at | integer | Completion timestamp (optional) |
| expires_at | integer | Expiration timestamp (optional) |
| size | string | Video dimensions in format `{width}x{height}` |
| error | object | Error information (optional) |
| error.message | string | Error description |
| error.code | string | Error code |
| metadata | object | Additional metadata |

### Error Response (400)

| Parameter | Type | Description |
|-----------|------|-------------|
| error | object | Error information object |
| error.message | string | Error description |
| error.code | string | Error code |

---

## Code Examples

### cURL

```bash
curl -X POST "https://www.ezmodel.cloud/v1/videos" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sora-1.0",
    "prompt": "A cute orange cat napping in the sunlight with wind gently blowing its fur",
    "duration": 10,
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "n": 1
  }'
```

### Python

```python
import requests
import json

url = "https://www.ezmodel.cloud/v1/videos"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}

data = {
    "model": "sora-1.0",
    "prompt": "A cute orange cat napping in the sunlight with wind gently blowing its fur",
    "duration": 10,
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "n": 1
}

response = requests.post(url, headers=headers, json=data)
result = response.json()
print(json.dumps(result, indent=2))
```

### JavaScript

```javascript
const response = await fetch('https://www.ezmodel.cloud/v1/videos', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer YOUR_API_KEY',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    model: 'sora-1.0',
    prompt: 'A cute orange cat napping in the sunlight with wind gently blowing its fur',
    duration: 10,
    width: 1920,
    height: 1080,
    fps: 30,
    n: 1
  })
});

const result = await response.json();
console.log(result);
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
    url := "https://www.ezmodel.cloud/v1/videos"
    
    payload := map[string]interface{}{
        "model":    "sora-1.0",
        "prompt":   "A cute orange cat napping in the sunlight with wind gently blowing its fur",
        "duration": 10,
        "width":    1920,
        "height":   1080,
        "fps":      30,
        "n":        1,
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

### Java

```java
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.URI;

public class SoraVideoExample {
    public static void main(String[] args) throws Exception {
        String url = "https://www.ezmodel.cloud/v1/videos";
        String json = """
        {
            "model": "sora-1.0",
            "prompt": "A cute orange cat napping in the sunlight with wind gently blowing its fur",
            "duration": 10,
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "n": 1
        }
        """;
        
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(url))
            .header("Authorization", "Bearer YOUR_API_KEY")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(json))
            .build();
        
        HttpResponse<String> response = client.send(request, 
            HttpResponse.BodyHandlers.ofString());
        System.out.println(response.body());
    }
}
```

### C#

```csharp
using System;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;

class Program
{
    static async Task Main(string[] args)
    {
        var client = new HttpClient();
        var url = "https://www.ezmodel.cloud/v1/videos";
        
        client.DefaultRequestHeaders.Add("Authorization", "Bearer YOUR_API_KEY");
        
        var json = @"{
            ""model"": ""sora-1.0"",
            ""prompt"": ""A cute orange cat napping in the sunlight with wind gently blowing its fur"",
            ""duration"": 10,
            ""width"": 1920,
            ""height"": 1080,
            ""fps"": 30,
            ""n"": 1
        }";
        
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        var response = await client.PostAsync(url, content);
        var result = await response.Content.ReadAsStringAsync();
        
        Console.WriteLine(result);
    }
}
```

---

## Response Examples

### Success Response (200)

```json
{
  "id": "vid_abc123xyz456",
  "object": "video",
  "model": "sora-1.0",
  "status": "processing",
  "progress": 0,
  "created_at": 1705334400,
  "seconds": "10.0",
  "completed_at": null,
  "expires_at": 1705420800,
  "size": "1920x1080",
  "error": null,
  "metadata": {
    "fps": 30,
    "seed": 12345
  }
}
```

### Error Response (400)

```json
{
  "error": {
    "message": "Invalid parameter: duration must be between 1 and 60 seconds",
    "code": "invalid_parameter"
  }
}
```

---

## Important Notes

1. **Asynchronous Processing**: Video generation is an asynchronous process. After submission, use the query interface to retrieve results
2. **Parameter Limits**: Different models have different limitations on video duration, dimensions, and frame rate
3. **Billing**: Video generation is billed based on duration and resolution. See pricing page for details
4. **Expiration**: Generated videos expire after a certain period. Download and save them promptly
5. **Concurrency Limits**: Each account may have limits on the number of concurrent tasks

---

## Related APIs

- [Query Video Task Status](https://www.ezmodel.cloud/docs/sora-videos-status)
- [Get Video Content](https://www.ezmodel.cloud/docs/sora-videos-content)
