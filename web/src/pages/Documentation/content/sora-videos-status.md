# Sora 获取视频任务状态

OpenAI 兼容的视频任务状态查询接口。

返回视频任务的详细状态信息,包括进度、完成状态和生成结果。

## 接口详情

**接口地址:** `GET /v1/videos/{task_id}`

**功能描述:** 查询指定视频任务的状态和详细信息。可用于轮询任务进度,获取生成的视频 URL。

**认证方式:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 请求参数

### Path 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| task_id | string | 是 | 视频任务 ID | `vid_abc123xyz456` |

---

## 响应参数

### 成功响应 (200)

| 参数名 | 类型 | 说明 |
|--------|------|------|
| id | string | 视频任务 ID |
| object | string | 对象类型,固定为 `video` |
| model | string | 使用的模型名称 |
| status | string | 任务状态: `pending`, `processing`, `completed`, `failed` |
| progress | integer | 进度百分比 (0-100) |
| created_at | integer | 创建时间戳 (Unix timestamp) |
| seconds | string | 视频时长 |
| completed_at | integer | 完成时间戳 (可选) |
| expires_at | integer | 过期时间戳 (可选) |
| size | string | 视频尺寸,格式: `{width}x{height}` |
| url | string | 视频下载地址 (任务完成后可用) |
| error | object | 错误信息 (任务失败时可用) |
| error.message | string | 错误描述 |
| error.code | string | 错误代码 |
| metadata | object | 额外元数据 |

### 错误响应 (404)

| 参数名 | 类型 | 说明 |
|--------|------|------|
| error | object | 错误信息对象 |
| error.message | string | 错误描述 |
| error.code | string | 错误代码 |

---

## 任务状态说明

| 状态 | 说明 |
|------|------|
| `pending` | 任务已提交,等待处理 |
| `processing` | 任务正在处理中 |
| `completed` | 任务已完成,视频生成成功 |
| `failed` | 任务失败 |

---

## 代码示例

### cURL

```bash
# 查询任务状态
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

# 轮询查询任务状态
while True:
    response = requests.get(url, headers=headers)
    result = response.json()
    
    print(f"状态: {result['status']}, 进度: {result['progress']}%")
    
    if result['status'] == 'completed':
        print(f"视频生成成功!")
        print(f"下载地址: {result.get('url')}")
        break
    elif result['status'] == 'failed':
        print(f"任务失败: {result.get('error', {}).get('message')}")
        break
    
    time.sleep(5)  # 等待5秒后再次查询
```

### JavaScript

```javascript
const taskId = 'vid_abc123xyz456';
const url = `https://www.ezmodel.cloud/v1/videos/${taskId}`;

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
    console.log(`状态: ${result.status}, 进度: ${result.progress}%`);
    
    if (result.status === 'completed') {
      console.log('视频生成成功!');
      console.log('下载地址:', result.url);
      break;
    } else if (result.status === 'failed') {
      console.log('任务失败:', result.error?.message);
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
        
        var result VideoTaskResponse
        json.Unmarshal(body, &result)
        
        fmt.Printf("状态: %s, 进度: %d%%\n", result.Status, result.Progress)
        
        if result.Status == "completed" {
            fmt.Println("视频生成成功!")
            fmt.Printf("下载地址: %s\n", result.URL)
            break
        } else if result.Status == "failed" {
            if result.Error != nil {
                fmt.Printf("任务失败: %s\n", result.Error.Message)
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
        
        // 轮询查询任务状态
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
            
            System.out.println("状态: " + status + ", 进度: " + progress + "%");
            
            if ("completed".equals(status)) {
                System.out.println("视频生成成功!");
                System.out.println("下载地址: " + result.get("url").getAsString());
                break;
            } else if ("failed".equals(status)) {
                JsonObject error = result.getAsJsonObject("error");
                if (error != null) {
                    System.out.println("任务失败: " + error.get("message").getAsString());
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
        
        // 轮询查询任务状态
        while (true)
        {
            var response = await client.GetAsync(url);
            var content = await response.Content.ReadAsStringAsync();
            var result = JsonSerializer.Deserialize<JsonElement>(content);
            
            var status = result.GetProperty("status").GetString();
            var progress = result.GetProperty("progress").GetInt32();
            
            Console.WriteLine($"状态: {status}, 进度: {progress}%");
            
            if (status == "completed")
            {
                Console.WriteLine("视频生成成功!");
                Console.WriteLine($"下载地址: {result.GetProperty("url").GetString()}");
                break;
            }
            else if (status == "failed")
            {
                if (result.TryGetProperty("error", out var error))
                {
                    Console.WriteLine($"任务失败: {error.GetProperty("message").GetString()}");
                }
                break;
            }
            
            await Task.Delay(5000);
        }
    }
}
```

---

## 响应示例

### 任务处理中 (200)

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

### 任务完成 (200)

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

### 任务失败 (200)

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

### 任务不存在 (404)

```json
{
  "error": {
    "message": "Video task not found",
    "code": "task_not_found"
  }
}
```

---

## 注意事项

1. **轮询间隔**: 建议每 3-5 秒查询一次任务状态,避免过于频繁的请求
2. **超时处理**: 视频生成可能需要较长时间,建议设置合理的超时时间
3. **URL 有效期**: 视频下载链接有过期时间,请在 `expires_at` 之前下载
4. **错误重试**: 网络错误时应实现重试机制
5. **状态缓存**: 任务完成后状态信息会保留一段时间供查询

---

## 相关接口

- [创建视频生成任务](https://www.ezmodel.cloud/docs/sora-videos)
- [获取视频内容](https://www.ezmodel.cloud/docs/sora-videos-content)
