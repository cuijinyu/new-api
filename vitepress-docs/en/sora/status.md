# Sora Get Video Task Status

OpenAI-compatible video task status query interface.

Returns detailed status information for a video task, including progress, completion status, and generation results.

## API Details

**Endpoint:** `GET /v1/videos/{task_id}`

**Description:** Query the status and detailed information of a specified video task. Used for polling task progress and retrieving the generated video URL.

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## Request Parameters

### Path Parameters

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| task_id | string | Yes | Video task ID | `vid_abc123xyz456` |

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
| url | string | Video download URL (available after task completion) |
| error | object | Error information (available when task fails) |
| error.message | string | Error description |
| error.code | string | Error code |
| metadata | object | Additional metadata |

### Error Response (404)

| Parameter | Type | Description |
|-----------|------|-------------|
| error | object | Error information object |
| error.message | string | Error description |
| error.code | string | Error code |

---

## Task Status Description

| Status | Description |
|--------|-------------|
| `pending` | Task submitted, waiting for processing |
| `processing` | Task is being processed |
| `completed` | Task completed, video generated successfully |
| `failed` | Task failed |

---

## Code Examples

### cURL

```bash
# Query task status
curl -X GET "https://www.ezmodel.cloud/v1/videos/vid_abc123xyz456" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Python

```python
import requests
import time
import json

task_id = "vid_abc123xyz456"
url = f"https://www.ezmodel.cloud/v1/videos/{task_id}"
headers = {
    "Authorization": "Bearer YOUR_API_KEY"
}

# Poll task status
while True:
    response = requests.get(url, headers=headers)
    result = response.json()
    
    print(f"Status: {result['status']}, Progress: {result['progress']}%")
    
    if result['status'] == 'completed':
        print(f"Video generated successfully!")
        print(f"Download URL: {result.get('url')}")
        break
    elif result['status'] == 'failed':
        print(f"Task failed: {result.get('error', {}).get('message')}")
        break
    
    time.sleep(5)  # Wait 5 seconds before next query
```

### JavaScript

```javascript
const taskId = 'vid_abc123xyz456';
const url = `https://www.ezmodel.cloud/v1/videos/${taskId}`;

// Poll task status
async function pollTaskStatus() {
  while (true) {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Authorization': 'Bearer YOUR_API_KEY'
      }
    });
    
    const result = await response.json();
    console.log(`Status: ${result.status}, Progress: ${result.progress}%`);
    
    if (result.status === 'completed') {
      console.log('Video generated successfully!');
      console.log('Download URL:', result.url);
      break;
    } else if (result.status === 'failed') {
      console.log('Task failed:', result.error?.message);
      break;
    }
    
    await new Promise(resolve => setTimeout(resolve, 5000)); // Wait 5 seconds
  }
}

pollTaskStatus();
```

### Go

```go
package main

import (
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "time"
)

type VideoTaskResponse struct {
    ID         string `json:"id"`
    Object     string `json:"object"`
    Model      string `json:"model"`
    Status     string `json:"status"`
    Progress   int    `json:"progress"`
    CreatedAt  int64  `json:"created_at"`
    Seconds    string `json:"seconds"`
    URL        string `json:"url,omitempty"`
    Error      *struct {
        Message string `json:"message"`
        Code    string `json:"code"`
    } `json:"error,omitempty"`
}

func main() {
    taskID := "vid_abc123xyz456"
    url := fmt.Sprintf("https://www.ezmodel.cloud/v1/videos/%s", taskID)
    
    client := &http.Client{}
    
    // Poll task status
    for {
        req, _ := http.NewRequest("GET", url, nil)
        req.Header.Set("Authorization", "Bearer YOUR_API_KEY")
        
        resp, err := client.Do(req)
        if err != nil {
            panic(err)
        }
        
        body, _ := io.ReadAll(resp.Body)
        resp.Body.Close()
        
        var result VideoTaskResponse
        json.Unmarshal(body, &result)
        
        fmt.Printf("Status: %s, Progress: %d%%\n", result.Status, result.Progress)
        
        if result.Status == "completed" {
            fmt.Println("Video generated successfully!")
            fmt.Printf("Download URL: %s\n", result.URL)
            break
        } else if result.Status == "failed" {
            if result.Error != nil {
                fmt.Printf("Task failed: %s\n", result.Error.Message)
            }
            break
        }
        
        time.Sleep(5 * time.Second)
    }
}
```

### Java

```java
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.URI;
import com.google.gson.Gson;
import com.google.gson.JsonObject;

public class SoraVideoStatusExample {
    public static void main(String[] args) throws Exception {
        String taskId = "vid_abc123xyz456";
        String url = "https://www.ezmodel.cloud/v1/videos/" + taskId;
        
        HttpClient client = HttpClient.newHttpClient();
        Gson gson = new Gson();
        
        // Poll task status
        while (true) {
            HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .header("Authorization", "Bearer YOUR_API_KEY")
                .GET()
                .build();
            
            HttpResponse<String> response = client.send(request, 
                HttpResponse.BodyHandlers.ofString());
            
            JsonObject result = gson.fromJson(response.body(), JsonObject.class);
            String status = result.get("status").getAsString();
            int progress = result.get("progress").getAsInt();
            
            System.out.println("Status: " + status + ", Progress: " + progress + "%");
            
            if ("completed".equals(status)) {
                System.out.println("Video generated successfully!");
                System.out.println("Download URL: " + result.get("url").getAsString());
                break;
            } else if ("failed".equals(status)) {
                JsonObject error = result.getAsJsonObject("error");
                if (error != null) {
                    System.out.println("Task failed: " + error.get("message").getAsString());
                }
                break;
            }
            
            Thread.sleep(5000);
        }
    }
}
```

### C#

```csharp
using System;
using System.Net.Http;
using System.Threading.Tasks;
using System.Text.Json;

class Program
{
    static async Task Main(string[] args)
    {
        var client = new HttpClient();
        var taskId = "vid_abc123xyz456";
        var url = $"https://www.ezmodel.cloud/v1/videos/{taskId}";
        
        client.DefaultRequestHeaders.Add("Authorization", "Bearer YOUR_API_KEY");
        
        // Poll task status
        while (true)
        {
            var response = await client.GetAsync(url);
            var content = await response.Content.ReadAsStringAsync();
            var result = JsonSerializer.Deserialize<JsonElement>(content);
            
            var status = result.GetProperty("status").GetString();
            var progress = result.GetProperty("progress").GetInt32();
            
            Console.WriteLine($"Status: {status}, Progress: {progress}%");
            
            if (status == "completed")
            {
                Console.WriteLine("Video generated successfully!");
                Console.WriteLine($"Download URL: {result.GetProperty("url").GetString()}");
                break;
            }
            else if (status == "failed")
            {
                if (result.TryGetProperty("error", out var error))
                {
                    Console.WriteLine($"Task failed: {error.GetProperty("message").GetString()}");
                }
                break;
            }
            
            await Task.Delay(5000);
        }
    }
}
```

---

## Response Examples

### Task Processing (200)

```json
{
  "id": "vid_abc123xyz456",
  "object": "video",
  "model": "sora-1.0",
  "status": "processing",
  "progress": 45,
  "created_at": 1705334400,
  "seconds": "10.0",
  "size": "1920x1080",
  "metadata": {
    "fps": 30,
    "seed": 12345
  }
}
```

### Task Completed (200)

```json
{
  "id": "vid_abc123xyz456",
  "object": "video",
  "model": "sora-1.0",
  "status": "completed",
  "progress": 100,
  "created_at": 1705334400,
  "completed_at": 1705334520,
  "expires_at": 1705420800,
  "seconds": "10.0",
  "size": "1920x1080",
  "url": "https://storage.example.com/videos/vid_abc123xyz456.mp4",
  "metadata": {
    "fps": 30,
    "seed": 12345
  }
}
```

### Task Failed (200)

```json
{
  "id": "vid_abc123xyz456",
  "object": "video",
  "model": "sora-1.0",
  "status": "failed",
  "progress": 0,
  "created_at": 1705334400,
  "seconds": "10.0",
  "error": {
    "message": "Content policy violation: inappropriate content detected",
    "code": "content_policy_violation"
  }
}
```

### Task Not Found (404)

```json
{
  "error": {
    "message": "Video task not found",
    "code": "task_not_found"
  }
}
```

---

## Important Notes

1. **Polling Interval**: Recommend querying status every 3-5 seconds to avoid excessive requests
2. **Timeout Handling**: Video generation may take considerable time, set reasonable timeout values
3. **URL Validity**: Video download links have expiration times, download before `expires_at`
4. **Error Retry**: Implement retry mechanism for network errors
5. **Status Caching**: Task status information is retained for a period after completion for querying

---

## Related APIs

- [Create Video Generation Task](https://www.ezmodel.cloud/docs/sora-videos)
- [Get Video Content](https://www.ezmodel.cloud/docs/sora-videos-content)
