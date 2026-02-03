# Sora 获取视频任务状态

OpenAI 兼容的视频任务状态查询接口。

返回视频任务的详细状态信息，包括进度、完成状态和生成结果。

## 接口详情

**接口地址:** `GET /v1/videos/{video_id}`

**功能描述:** 查询指定视频任务的状态和详细信息。可用于轮询任务进度，获取生成状态。

**参考文档:** [Azure OpenAI Sora 2 API](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/video-generation)

**认证方式:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 请求参数

### Path 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| video_id | string | 是 | 视频任务 ID | `video_68f10985d6c4819097007665bdcfba5f` |

---

## 响应参数

### 成功响应 (200)

| 参数名 | 类型 | 说明 |
|--------|------|------|
| id | string | 视频任务 ID |
| object | string | 对象类型，固定为 `video` |
| model | string | 使用的模型名称 |
| status | string | 任务状态: `queued`, `in_progress`, `completed`, `failed`, `cancelled` |
| progress | integer | 进度百分比 (0-100) |
| created_at | integer | 创建时间戳 (Unix timestamp) |
| completed_at | integer | 完成时间戳 (任务完成后可用) |
| expires_at | integer | 过期时间戳 (任务完成后可用) |
| seconds | string | 视频时长 |
| size | string | 视频尺寸，格式: `{width}x{height}` |
| remixed_from_video_id | string | 如果是 Remix 生成的，显示源视频 ID |
| error | object | 错误信息 (任务失败时可用) |
| error.message | string | 错误描述 |
| error.code | string | 错误代码 |

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
| `queued` | 任务已提交，等待处理 |
| `in_progress` | 任务正在处理中 |
| `completed` | 任务已完成，视频生成成功 |
| `failed` | 任务失败 |
| `cancelled` | 任务已取消 |

---

## 代码示例

### cURL

```bash
# 查询任务状态
curl -X GET "https://www.ezmodel.cloud/v1/videos/video_68f10985d6c4819097007665bdcfba5f" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Python (轮询等待完成)

```python
import time
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://www.ezmodel.cloud/v1/",
)

video_id = "video_68f10985d6c4819097007665bdcfba5f"

# 轮询查询任务状态
while True:
    video = client.videos.retrieve(video_id)
    
    print(f"Status: {video.status}, Progress: {video.progress}%")
    
    if video.status == "completed":
        print("Video successfully completed!")
        print(f"Video ID: {video.id}")
        break
    elif video.status in ["failed", "cancelled"]:
        print(f"Video creation ended with status: {video.status}")
        if video.error:
            print(f"Error: {video.error.message}")
        break
    
    time.sleep(20)  # 建议每 20 秒查询一次
```

### Python (使用 create_and_poll 自动轮询)

```python
import asyncio
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://www.ezmodel.cloud/v1/",
)

async def main():
    # 创建视频并自动轮询等待完成
    video = await client.videos.create_and_poll(
        model="sora-2",
        prompt="A video of a cat on a motorcycle",
        size="1280x720",
        seconds="8",
    )

    if video.status == "completed":
        print("Video successfully completed:", video)
    else:
        print("Video creation failed. Status:", video.status)

asyncio.run(main())
```

### JavaScript

```javascript
const videoId = 'video_68f10985d6c4819097007665bdcfba5f';

// 轮询查询任务状态
async function pollTaskStatus() {
  while (true) {
    const response = await fetch(
      `https://www.ezmodel.cloud/v1/videos/${videoId}`,
      {
        method: 'GET',
        headers: {
          'Authorization': 'Bearer YOUR_API_KEY'
        }
      }
    );
    
    const result = await response.json();
    console.log(`Status: ${result.status}, Progress: ${result.progress}%`);
    
    if (result.status === 'completed') {
      console.log('Video successfully completed!');
      console.log('Video ID:', result.id);
      break;
    } else if (result.status === 'failed' || result.status === 'cancelled') {
      console.log('Video creation ended:', result.status);
      if (result.error) {
        console.log('Error:', result.error.message);
      }
      break;
    }
    
    await new Promise(resolve => setTimeout(resolve, 20000)); // 等待 20 秒
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

type VideoResponse struct {
    ID                  string `json:"id"`
    Object              string `json:"object"`
    Model               string `json:"model"`
    Status              string `json:"status"`
    Progress            int    `json:"progress"`
    CreatedAt           int64  `json:"created_at"`
    CompletedAt         *int64 `json:"completed_at,omitempty"`
    ExpiresAt           *int64 `json:"expires_at,omitempty"`
    Seconds             string `json:"seconds"`
    Size                string `json:"size"`
    RemixedFromVideoID  *string `json:"remixed_from_video_id,omitempty"`
    Error               *struct {
        Message string `json:"message"`
        Code    string `json:"code"`
    } `json:"error,omitempty"`
}

func main() {
    videoID := "video_68f10985d6c4819097007665bdcfba5f"
    url := fmt.Sprintf("https://www.ezmodel.cloud/v1/videos/%s", videoID)
    
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
        
        var result VideoResponse
        json.Unmarshal(body, &result)
        
        fmt.Printf("Status: %s, Progress: %d%%\n", result.Status, result.Progress)
        
        if result.Status == "completed" {
            fmt.Println("Video successfully completed!")
            fmt.Printf("Video ID: %s\n", result.ID)
            break
        } else if result.Status == "failed" || result.Status == "cancelled" {
            fmt.Printf("Video creation ended with status: %s\n", result.Status)
            if result.Error != nil {
                fmt.Printf("Error: %s\n", result.Error.Message)
            }
            break
        }
        
        time.Sleep(20 * time.Second)
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
        String videoId = "video_68f10985d6c4819097007665bdcfba5f";
        String url = "https://www.ezmodel.cloud/v1/videos/" + videoId;
        
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
            
            System.out.println("Status: " + status + ", Progress: " + progress + "%");
            
            if ("completed".equals(status)) {
                System.out.println("Video successfully completed!");
                System.out.println("Video ID: " + result.get("id").getAsString());
                break;
            } else if ("failed".equals(status) || "cancelled".equals(status)) {
                System.out.println("Video creation ended with status: " + status);
                if (result.has("error") && !result.get("error").isJsonNull()) {
                    JsonObject error = result.getAsJsonObject("error");
                    System.out.println("Error: " + error.get("message").getAsString());
                }
                break;
            }
            
            Thread.sleep(20000);
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
        var videoId = "video_68f10985d6c4819097007665bdcfba5f";
        var url = $"https://www.ezmodel.cloud/v1/videos/{videoId}";
        
        client.DefaultRequestHeaders.Add("Authorization", "Bearer YOUR_API_KEY");
        
        // 轮询查询任务状态
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
                Console.WriteLine("Video successfully completed!");
                Console.WriteLine($"Video ID: {result.GetProperty("id").GetString()}");
                break;
            }
            else if (status == "failed" || status == "cancelled")
            {
                Console.WriteLine($"Video creation ended with status: {status}");
                if (result.TryGetProperty("error", out var error) && 
                    error.ValueKind != JsonValueKind.Null)
                {
                    Console.WriteLine($"Error: {error.GetProperty("message").GetString()}");
                }
                break;
            }
            
            await Task.Delay(20000);
        }
    }
}
```

---

## 响应示例

### 任务排队中 (200)

```json
{
  "id": "video_68f10985d6c4819097007665bdcfba5f",
  "object": "video",
  "model": "sora-2",
  "status": "queued",
  "progress": 0,
  "created_at": 1760627077,
  "completed_at": null,
  "expires_at": null,
  "seconds": "8",
  "size": "1280x720",
  "remixed_from_video_id": null,
  "error": null
}
```

### 任务处理中 (200)

```json
{
  "id": "video_68f10985d6c4819097007665bdcfba5f",
  "object": "video",
  "model": "sora-2",
  "status": "in_progress",
  "progress": 45,
  "created_at": 1760627077,
  "completed_at": null,
  "expires_at": null,
  "seconds": "8",
  "size": "1280x720",
  "remixed_from_video_id": null,
  "error": null
}
```

### 任务完成 (200)

```json
{
  "id": "video_68f10985d6c4819097007665bdcfba5f",
  "object": "video",
  "model": "sora-2",
  "status": "completed",
  "progress": 100,
  "created_at": 1760627077,
  "completed_at": 1760627863,
  "expires_at": 1760714196,
  "seconds": "8",
  "size": "1280x720",
  "remixed_from_video_id": null,
  "error": null
}
```

### 任务失败 (200)

```json
{
  "id": "video_68f10985d6c4819097007665bdcfba5f",
  "object": "video",
  "model": "sora-2",
  "status": "failed",
  "progress": 0,
  "created_at": 1760627077,
  "completed_at": null,
  "expires_at": null,
  "seconds": "8",
  "size": "1280x720",
  "remixed_from_video_id": null,
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
    "message": "Video not found",
    "code": "video_not_found"
  }
}
```

---

## 注意事项

1. **轮询间隔**: 建议每 20 秒查询一次任务状态，避免过于频繁的请求
2. **超时处理**: 视频生成通常需要 1-3 分钟，建议设置合理的超时时间
3. **过期时间**: 任务完成后 24 小时内有效，请在 `expires_at` 之前下载视频
4. **错误重试**: 网络错误时应实现重试机制
5. **进度更新**: `progress` 字段每 5 秒更新一次

---

## 相关接口

- [创建视频生成任务](/sora/create)
- [获取视频内容](/sora/content)
- [Remix 视频混剪](/sora/remix)
