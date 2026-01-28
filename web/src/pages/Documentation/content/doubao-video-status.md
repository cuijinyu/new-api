# 查询豆包视频任务状态

查询豆包视频生成任务的状态和结果。

## 接口详情

**接口地址:** `GET /v1/video/generations/:task_id`

**功能描述:** 通过提交任务时返回的 `task_id` 查询视频生成的进度和最终结果。任务完成后可获取生成的视频 URL。

**认证方式:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 请求参数

### Path 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| task_id | string | 是 | 提交任务时返回的任务唯一标识符 | `task_abc123xyz456` |

---

## 任务状态说明

| 状态 | 说明 | 进度 |
|------|------|------|
| `queued` | 任务正在排队中 | 10% |
| `in_progress` | 视频生成中 | 50% |
| `success` | 任务已完成 | 100% |
| `failure` | 任务失败 | 100% |

---

## 响应参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| code | string | 响应状态码，`success` 表示成功 |
| data | object | 任务详情对象 |
| data.task_id | string | 任务唯一标识符 |
| data.action | string | 任务类型，固定为 `generate` |
| data.status | string | 任务状态 |
| data.progress | string | 任务进度百分比 |
| data.fail_reason | string | 成功时为视频 URL，失败时为错误原因 |
| data.submit_time | integer | 提交时间戳 |
| data.start_time | integer | 开始处理时间戳 |
| data.finish_time | integer | 完成时间戳 |

---

## 代码示例

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

# 轮询查询任务状态
while True:
    response = requests.get(url, headers=headers)
    result = response.json()
    
    data = result.get("data", {})
    status = data.get("status")
    progress = data.get("progress", "0%")
    
    print(f"状态: {status}, 进度: {progress}")
    
    if status == "success":
        video_url = data.get("fail_reason")  # 成功时 fail_reason 字段存储视频 URL
        print(f"视频生成成功!")
        print(f"视频地址: {video_url}")
        break
    elif status == "failure":
        error_msg = data.get("fail_reason")
        print(f"任务失败: {error_msg}")
        break
    
    time.sleep(5)  # 等待5秒后再次查询
```

### JavaScript

```javascript
const taskId = 'task_abc123xyz456';
const url = `https://your-domain.com/v1/video/generations/${taskId}`;

// 轮询查询任务状态
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
    
    console.log(`状态: ${status}, 进度: ${progress}`);
    
    if (status === 'success') {
      const videoUrl = data.fail_reason;
      console.log('视频生成成功!');
      console.log('视频地址:', videoUrl);
      break;
    } else if (status === 'failure') {
      console.log('任务失败:', data.fail_reason);
      break;
    }
    
    await new Promise(resolve => setTimeout(resolve, 5000)); // 等待5秒
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
    
    // 轮询查询任务状态
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
        
        fmt.Printf("状态: %s, 进度: %s\n", result.Data.Status, result.Data.Progress)
        
        if result.Data.Status == "success" {
            fmt.Println("视频生成成功!")
            fmt.Printf("视频地址: %s\n", result.Data.FailReason)
            break
        } else if result.Data.Status == "failure" {
            fmt.Printf("任务失败: %s\n", result.Data.FailReason)
            break
        }
        
        time.Sleep(5 * time.Second)
    }
}
```

---

## 响应示例

### 任务排队中 (200)

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

### 任务处理中 (200)

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

### 任务完成 (200)

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

### 任务失败 (200)

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

## 注意事项

1. **轮询间隔**: 建议每 5-10 秒查询一次任务状态，避免过于频繁的请求
2. **视频 URL**: 任务成功完成后，视频 URL 存储在 `fail_reason` 字段中
3. **超时处理**: 视频生成可能需要较长时间（通常 1-5 分钟），建议设置合理的超时时间
4. **URL 有效期**: 生成的视频 URL 可能有过期时间，建议及时下载保存

---

## 相关接口

- [创建豆包视频生成任务](/docs/doubao-video)
