# Query Doubao Video Task Status

Query the status and results of a Doubao video generation task.

## API Details

**Endpoint:** `GET /v1/video/generations/:task_id`

**Description:** Query the progress and final result of video generation using the `task_id` returned when the task was submitted. Once completed, you can get the generated video URL.

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## Request Parameters

### Path Parameters

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| task_id | string | Yes | The unique task identifier returned during submission | `task_abc123xyz456` |

---

## Task Status Description

| Status | Description | Progress |
|--------|-------------|----------|
| `queued` | Task is in queue | 10% |
| `in_progress` | Video is being generated | 50% |
| `success` | Task completed successfully | 100% |
| `failure` | Task failed | 100% |

---

## Response Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| code | string | Response status code, `success` indicates success |
| data | object | Task details object |
| data.task_id | string | Unique task identifier |
| data.action | string | Task type, always `generate` |
| data.status | string | Task status |
| data.progress | string | Task progress percentage |
| data.fail_reason | string | Video URL on success, error message on failure |
| data.submit_time | integer | Submission timestamp |
| data.start_time | integer | Processing start timestamp |
| data.finish_time | integer | Completion timestamp |

---

## Code Examples

### cURL

```bash
curl -X GET "https://your-domain.com/v1/video/generations/task_abc123xyz456" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Python

```python
import requests
import time
import json

task_id = "task_abc123xyz456"
url = f"https://your-domain.com/v1/video/generations/{task_id}"
headers = {
    "Authorization": "Bearer YOUR_API_KEY"
}

# Poll task status
while True:
    response = requests.get(url, headers=headers)
    result = response.json()
    
    data = result.get("data", {})
    status = data.get("status")
    progress = data.get("progress", "0%")
    
    print(f"Status: {status}, Progress: {progress}")
    
    if status == "success":
        video_url = data.get("fail_reason")  # On success, fail_reason contains video URL
        print(f"Video generation successful!")
        print(f"Video URL: {video_url}")
        break
    elif status == "failure":
        error_msg = data.get("fail_reason")
        print(f"Task failed: {error_msg}")
        break
    
    time.sleep(5)  # Wait 5 seconds before next query
```

### JavaScript

```javascript
const taskId = 'task_abc123xyz456';
const url = `https://your-domain.com/v1/video/generations/${taskId}`;

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
    const data = result.data || {};
    const status = data.status;
    const progress = data.progress || '0%';
    
    console.log(`Status: ${status}, Progress: ${progress}`);
    
    if (status === 'success') {
      const videoUrl = data.fail_reason;
      console.log('Video generation successful!');
      console.log('Video URL:', videoUrl);
      break;
    } else if (status === 'failure') {
      console.log('Task failed:', data.fail_reason);
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

type TaskResponse struct {
    Code string `json:"code"`
    Data struct {
        TaskID     string `json:"task_id"`
        Action     string `json:"action"`
        Status     string `json:"status"`
        Progress   string `json:"progress"`
        FailReason string `json:"fail_reason"`
        SubmitTime int64  `json:"submit_time"`
        StartTime  int64  `json:"start_time"`
        FinishTime int64  `json:"finish_time"`
    } `json:"data"`
}

func main() {
    taskID := "task_abc123xyz456"
    url := fmt.Sprintf("https://your-domain.com/v1/video/generations/%s", taskID)
    
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
        
        var result TaskResponse
        json.Unmarshal(body, &result)
        
        fmt.Printf("Status: %s, Progress: %s\n", result.Data.Status, result.Data.Progress)
        
        if result.Data.Status == "success" {
            fmt.Println("Video generation successful!")
            fmt.Printf("Video URL: %s\n", result.Data.FailReason)
            break
        } else if result.Data.Status == "failure" {
            fmt.Printf("Task failed: %s\n", result.Data.FailReason)
            break
        }
        
        time.Sleep(5 * time.Second)
    }
}
```

---

## Response Examples

### Task Queued (200)

```json
{
  "code": "success",
  "data": {
    "task_id": "task_abc123xyz456",
    "action": "generate",
    "status": "queued",
    "progress": "10%",
    "fail_reason": "",
    "submit_time": 1705334400,
    "start_time": 0,
    "finish_time": 0
  }
}
```

### Task Processing (200)

```json
{
  "code": "success",
  "data": {
    "task_id": "task_abc123xyz456",
    "action": "generate",
    "status": "in_progress",
    "progress": "50%",
    "fail_reason": "",
    "submit_time": 1705334400,
    "start_time": 1705334410,
    "finish_time": 0
  }
}
```

### Task Completed (200)

```json
{
  "code": "success",
  "data": {
    "task_id": "task_abc123xyz456",
    "action": "generate",
    "status": "success",
    "progress": "100%",
    "fail_reason": "https://storage.example.com/videos/task_abc123xyz456.mp4",
    "submit_time": 1705334400,
    "start_time": 1705334410,
    "finish_time": 1705334520
  }
}
```

### Task Failed (200)

```json
{
  "code": "success",
  "data": {
    "task_id": "task_abc123xyz456",
    "action": "generate",
    "status": "failure",
    "progress": "100%",
    "fail_reason": "task failed",
    "submit_time": 1705334400,
    "start_time": 1705334410,
    "finish_time": 1705334450
  }
}
```

---

## Notes

1. **Polling Interval**: Recommend querying every 5-10 seconds to avoid excessive requests
2. **Video URL**: On successful completion, the video URL is stored in the `fail_reason` field
3. **Timeout Handling**: Video generation may take a while (typically 1-5 minutes), set appropriate timeout
4. **URL Expiration**: Generated video URLs may expire, download and save promptly

---

## Related APIs

- [Create Doubao Video Generation Task](/docs/doubao-video)
