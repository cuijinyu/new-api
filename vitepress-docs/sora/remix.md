# Sora Remix 视频混剪

Remix 功能允许您基于已生成的视频进行修改，保留原视频的核心元素同时实现特定的调整。

## 接口详情

**接口地址:** `POST /v1/videos/remix`

**功能描述:** 基于已完成的视频任务创建混剪版本。系统会保留原视频的框架、场景转换和视觉布局，同时根据新的提示词进行修改。

**参考文档:** [Azure OpenAI Sora 2 API](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/video-generation)

**认证方式:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 请求参数

### Body 参数 (JSON)

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| video_id | string | 是 | 源视频任务 ID (必须是已完成的视频) | `video_68f10985d6c4819097007665bdcfba5f` |
| prompt | string | 是 | 描述要修改的内容，建议只做一个明确的调整 | `Shift the color palette to teal, sand, and rust` |

---

## 响应参数

### 成功响应 (200)

| 参数名 | 类型 | 说明 |
|--------|------|------|
| id | string | 新视频任务 ID |
| object | string | 对象类型，固定为 `video` |
| model | string | 使用的模型名称 |
| status | string | 任务状态: `queued`, `in_progress`, `completed`, `failed`, `cancelled` |
| progress | integer | 进度百分比 (0-100) |
| created_at | integer | 创建时间戳 (Unix timestamp) |
| completed_at | integer | 完成时间戳 (任务完成后可用) |
| expires_at | integer | 过期时间戳 (任务完成后可用) |
| seconds | string | 视频时长 (继承自源视频) |
| size | string | 视频尺寸 (继承自源视频) |
| remixed_from_video_id | string | 源视频 ID |
| error | object | 错误信息 (任务失败时可用) |

### 错误响应 (400)

| 参数名 | 类型 | 说明 |
|--------|------|------|
| error | object | 错误信息对象 |
| error.message | string | 错误描述 |
| error.code | string | 错误代码 |

---

## 代码示例

### cURL

```bash
curl -X POST "https://www.ezmodel.cloud/v1/videos/remix" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "video_id": "video_68f10985d6c4819097007665bdcfba5f",
    "prompt": "Shift the color palette to teal, sand, and rust, with a warm backlight"
  }'
```

### Python (使用 OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://www.ezmodel.cloud/v1/",
)

# 基于已有视频创建 Remix
video = client.videos.remix(
    video_id="video_68f10985d6c4819097007665bdcfba5f",
    prompt="Shift the color palette to teal, sand, and rust, with a warm backlight"
)

print("Video generation started:", video)
print(f"New Video ID: {video.id}")
print(f"Remixed from: {video.remixed_from_video_id}")
```

### Python (使用 requests)

```python
import requests
import json

url = "https://www.ezmodel.cloud/v1/videos/remix"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}

data = {
    "video_id": "video_68f10985d6c4819097007665bdcfba5f",
    "prompt": "Shift the color palette to teal, sand, and rust, with a warm backlight"
}

response = requests.post(url, headers=headers, json=data)
result = response.json()
print(json.dumps(result, indent=2))
```

### JavaScript

```javascript
const response = await fetch('https://www.ezmodel.cloud/v1/videos/remix', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer YOUR_API_KEY',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    video_id: 'video_68f10985d6c4819097007665bdcfba5f',
    prompt: 'Shift the color palette to teal, sand, and rust, with a warm backlight'
  })
});

const result = await response.json();
console.log('New Video ID:', result.id);
console.log('Remixed from:', result.remixed_from_video_id);
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
    url := "https://www.ezmodel.cloud/v1/videos/remix"
    
    payload := map[string]interface{}{
        "video_id": "video_68f10985d6c4819097007665bdcfba5f",
        "prompt":   "Shift the color palette to teal, sand, and rust, with a warm backlight",
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

public class SoraRemixExample {
    public static void main(String[] args) throws Exception {
        String url = "https://www.ezmodel.cloud/v1/videos/remix";
        String json = """
        {
            "video_id": "video_68f10985d6c4819097007665bdcfba5f",
            "prompt": "Shift the color palette to teal, sand, and rust, with a warm backlight"
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
        var url = "https://www.ezmodel.cloud/v1/videos/remix";
        
        client.DefaultRequestHeaders.Add("Authorization", "Bearer YOUR_API_KEY");
        
        var json = @"{
            ""video_id"": ""video_68f10985d6c4819097007665bdcfba5f"",
            ""prompt"": ""Shift the color palette to teal, sand, and rust, with a warm backlight""
        }";
        
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        var response = await client.PostAsync(url, content);
        var result = await response.Content.ReadAsStringAsync();
        
        Console.WriteLine(result);
    }
}
```

---

## 完整流程示例

### Python (创建视频 → Remix → 下载)

```python
import time
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://www.ezmodel.cloud/v1/",
)

# 1. 创建原始视频
print("Step 1: Creating original video...")
original_video = client.videos.create(
    model="sora-2",
    prompt="A cat sitting on a windowsill watching the rain",
    size="1280x720",
    seconds="8",
)

print(f"Original video ID: {original_video.id}")

# 等待原始视频完成
while original_video.status not in ["completed", "failed", "cancelled"]:
    print(f"Status: {original_video.status}, Progress: {original_video.progress}%")
    time.sleep(20)
    original_video = client.videos.retrieve(original_video.id)

if original_video.status != "completed":
    print(f"Original video failed: {original_video.status}")
    exit(1)

print("Original video completed!")

# 2. 创建 Remix 版本
print("\nStep 2: Creating remix version...")
remix_video = client.videos.remix(
    video_id=original_video.id,
    prompt="Change the weather to sunny with golden afternoon light"
)

print(f"Remix video ID: {remix_video.id}")
print(f"Remixed from: {remix_video.remixed_from_video_id}")

# 等待 Remix 视频完成
while remix_video.status not in ["completed", "failed", "cancelled"]:
    print(f"Status: {remix_video.status}, Progress: {remix_video.progress}%")
    time.sleep(20)
    remix_video = client.videos.retrieve(remix_video.id)

if remix_video.status != "completed":
    print(f"Remix video failed: {remix_video.status}")
    exit(1)

print("Remix video completed!")

# 3. 下载两个视频
print("\nStep 3: Downloading videos...")

original_content = client.videos.download_content(original_video.id, variant="video")
original_content.write_to_file("original_video.mp4")
print("Saved original_video.mp4")

remix_content = client.videos.download_content(remix_video.id, variant="video")
remix_content.write_to_file("remix_video.mp4")
print("Saved remix_video.mp4")

print("\nDone!")
```

---

## 响应示例

### 成功响应 (200)

```json
{
  "id": "video_68ff7cef76cc8190b7eab9395e936d9e",
  "object": "video",
  "model": "sora-2",
  "status": "queued",
  "progress": 0,
  "created_at": 1761574127,
  "completed_at": null,
  "expires_at": null,
  "seconds": "8",
  "size": "1280x720",
  "remixed_from_video_id": "video_68f10985d6c4819097007665bdcfba5f",
  "error": null
}
```

### 错误响应 (400)

```json
{
  "error": {
    "message": "Source video not found or not completed",
    "code": "invalid_video_id"
  }
}
```

---

## Remix 最佳实践

为获得最佳 Remix 效果，请遵循以下建议：

### 1. 单一修改原则

每次 Remix 只做一个明确的修改，这样可以更好地保留原视频的结构。

**推荐:**
```
"Change the lighting to golden hour sunset"
```

**不推荐:**
```
"Change the lighting to sunset, add more people, and make the camera move faster"
```

### 2. 适合 Remix 的修改类型

- **色彩/光线调整**: 改变色调、光线效果
- **天气变化**: 晴天改为雨天、增加雾效等
- **风格转换**: 写实改为动画风格
- **氛围调整**: 欢快改为忧郁等

### 3. 不适合 Remix 的修改

- 完全改变主体（如猫改为狗）
- 大幅改变场景（如室内改为室外）
- 改变动作序列

---

## 注意事项

1. **源视频要求**: 只能对状态为 `completed` 的视频进行 Remix
2. **继承属性**: Remix 视频会继承源视频的 `size` 和 `seconds` 属性
3. **修改范围**: 建议每次只做一个明确的修改，以保持最佳效果
4. **过期时间**: 源视频过期后无法进行 Remix
5. **并发限制**: Remix 任务与普通视频生成任务共享并发限制（最多 2 个）

---

## 常见错误码

| 错误码 | 说明 | 解决方案 |
|--------|------|---------|
| `invalid_video_id` | 源视频 ID 无效 | 检查 video_id 是否正确 |
| `video_not_completed` | 源视频尚未完成 | 等待源视频完成后再进行 Remix |
| `video_expired` | 源视频已过期 | 需要重新生成源视频 |
| `content_policy_violation` | 内容违规 | 修改提示词，避免违规内容 |

---

## 相关接口

- [创建视频生成任务](/sora/create)
- [查询视频任务状态](/sora/status)
- [获取视频内容](/sora/content)
