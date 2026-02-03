# Sora 下载视频内容

获取已完成视频任务的视频文件。

此接口用于下载生成完成的视频文件。

## 接口详情

**接口地址:** `GET /v1/videos/{video_id}/content`

**功能描述:** 获取指定视频任务生成的视频文件。返回视频文件的二进制流，适合下载保存或直接播放。

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

### Query 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| variant | string | 否 | 下载变体类型，默认 `video` | `video` |

---

## 响应参数

### 成功响应 (200)

**Content-Type:** `video/mp4`

返回视频文件的二进制流。

### 错误响应 (404)

**Content-Type:** `application/json`

| 参数名 | 类型 | 说明 |
|--------|------|------|
| error | object | 错误信息对象 |
| error.message | string | 错误描述 |
| error.code | string | 错误代码 |

---

## 代码示例

### cURL

```bash
# 下载视频到本地文件
curl -X GET "https://www.ezmodel.cloud/v1/videos/video_68f10985d6c4819097007665bdcfba5f/content?variant=video" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -o video.mp4

# 或者直接在终端查看响应头
curl -I "https://www.ezmodel.cloud/v1/videos/video_68f10985d6c4819097007665bdcfba5f/content" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Python (使用 OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://www.ezmodel.cloud/v1/",
)

video_id = "video_68f10985d6c4819097007665bdcfba5f"

# 下载视频内容
content = client.videos.download_content(video_id, variant="video")
content.write_to_file("video.mp4")

print("Saved video.mp4")
```

### Python (使用 requests)

```python
import requests

video_id = "video_68f10985d6c4819097007665bdcfba5f"
url = f"https://www.ezmodel.cloud/v1/videos/{video_id}/content"
headers = {
    "Authorization": "Bearer YOUR_API_KEY"
}
params = {
    "variant": "video"
}

# 下载视频
response = requests.get(url, headers=headers, params=params, stream=True)

if response.status_code == 200:
    # 保存到本地文件
    with open("output_video.mp4", "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    print("视频下载成功!")
elif response.status_code == 404:
    error = response.json()
    print(f"错误: {error.get('error', {}).get('message')}")
else:
    print(f"请求失败: {response.status_code}")
```

### JavaScript (Node.js)

```javascript
const fs = require('fs');
const https = require('https');

const videoId = 'video_68f10985d6c4819097007665bdcfba5f';
const url = `https://www.ezmodel.cloud/v1/videos/${videoId}/content?variant=video`;

const options = {
  headers: {
    'Authorization': 'Bearer YOUR_API_KEY'
  }
};

// 下载视频
https.get(url, options, (response) => {
  if (response.statusCode === 200) {
    const fileStream = fs.createWriteStream('output_video.mp4');
    response.pipe(fileStream);
    
    fileStream.on('finish', () => {
      fileStream.close();
      console.log('视频下载成功!');
    });
  } else {
    console.error(`请求失败: ${response.statusCode}`);
  }
}).on('error', (err) => {
  console.error('下载错误:', err.message);
});
```

### JavaScript (Browser)

```javascript
const videoId = 'video_68f10985d6c4819097007665bdcfba5f';
const url = `https://www.ezmodel.cloud/v1/videos/${videoId}/content?variant=video`;

// 下载视频文件
async function downloadVideo() {
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Authorization': 'Bearer YOUR_API_KEY'
      }
    });
    
    if (response.ok) {
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = 'video.mp4';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(downloadUrl);
      console.log('视频下载成功!');
    } else {
      const error = await response.json();
      console.error('错误:', error.error?.message);
    }
  } catch (err) {
    console.error('下载错误:', err);
  }
}

downloadVideo();
```

### Go

```go
package main

import (
    "fmt"
    "io"
    "net/http"
    "os"
)

func main() {
    videoID := "video_68f10985d6c4819097007665bdcfba5f"
    url := fmt.Sprintf("https://www.ezmodel.cloud/v1/videos/%s/content?variant=video", videoID)
    
    // 创建请求
    req, err := http.NewRequest("GET", url, nil)
    if err != nil {
        panic(err)
    }
    req.Header.Set("Authorization", "Bearer YOUR_API_KEY")
    
    // 发送请求
    client := &http.Client{}
    resp, err := client.Do(req)
    if err != nil {
        panic(err)
    }
    defer resp.Body.Close()
    
    if resp.StatusCode == 200 {
        // 创建输出文件
        out, err := os.Create("output_video.mp4")
        if err != nil {
            panic(err)
        }
        defer out.Close()
        
        // 写入文件
        _, err = io.Copy(out, resp.Body)
        if err != nil {
            panic(err)
        }
        
        fmt.Println("视频下载成功!")
    } else {
        fmt.Printf("请求失败: %d\n", resp.StatusCode)
    }
}
```

### Java

```java
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.URI;

public class SoraVideoContentExample {
    public static void main(String[] args) throws Exception {
        String videoId = "video_68f10985d6c4819097007665bdcfba5f";
        String url = "https://www.ezmodel.cloud/v1/videos/" + videoId + "/content?variant=video";
        
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(url))
            .header("Authorization", "Bearer YOUR_API_KEY")
            .GET()
            .build();
        
        HttpResponse<InputStream> response = client.send(request,
            HttpResponse.BodyHandlers.ofInputStream());
        
        if (response.statusCode() == 200) {
            // 保存到文件
            try (FileOutputStream fos = new FileOutputStream("output_video.mp4");
                 InputStream is = response.body()) {
                byte[] buffer = new byte[8192];
                int bytesRead;
                while ((bytesRead = is.read(buffer)) != -1) {
                    fos.write(buffer, 0, bytesRead);
                }
            }
            System.out.println("视频下载成功!");
        } else {
            System.out.println("请求失败: " + response.statusCode());
        }
    }
}
```

### C#

```csharp
using System;
using System.IO;
using System.Net.Http;
using System.Threading.Tasks;

class Program
{
    static async Task Main(string[] args)
    {
        var client = new HttpClient();
        var videoId = "video_68f10985d6c4819097007665bdcfba5f";
        var url = $"https://www.ezmodel.cloud/v1/videos/{videoId}/content?variant=video";
        
        client.DefaultRequestHeaders.Add("Authorization", "Bearer YOUR_API_KEY");
        
        try
        {
            var response = await client.GetAsync(url);
            
            if (response.IsSuccessStatusCode)
            {
                // 下载并保存视频
                using var fileStream = new FileStream("output_video.mp4", FileMode.Create);
                await response.Content.CopyToAsync(fileStream);
                Console.WriteLine("视频下载成功!");
            }
            else if (response.StatusCode == System.Net.HttpStatusCode.NotFound)
            {
                var error = await response.Content.ReadAsStringAsync();
                Console.WriteLine($"错误: {error}");
            }
            else
            {
                Console.WriteLine($"请求失败: {response.StatusCode}");
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"下载错误: {ex.Message}");
        }
    }
}
```

---

## 完整流程示例

### Python (创建、轮询、下载)

```python
import time
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://www.ezmodel.cloud/v1/",
)

# 1. 创建视频
video = client.videos.create(
    model="sora-2",
    prompt="A video of a cat on a motorcycle",
    size="1280x720",
    seconds="8",
)

print(f"Video creation started. ID: {video.id}")
print(f"Initial status: {video.status}")

# 2. 轮询等待完成
while video.status not in ["completed", "failed", "cancelled"]:
    print(f"Status: {video.status}, Progress: {video.progress}%. Waiting 20 seconds...")
    time.sleep(20)
    video = client.videos.retrieve(video.id)

# 3. 下载视频
if video.status == "completed":
    print("Video successfully completed! Downloading...")
    content = client.videos.download_content(video.id, variant="video")
    content.write_to_file("video.mp4")
    print("Saved video.mp4")
else:
    print(f"Video creation ended with status: {video.status}")
    if video.error:
        print(f"Error: {video.error.message}")
```

---

## 响应示例

### 成功响应 (200)

**Headers:**
```
HTTP/1.1 200 OK
Content-Type: video/mp4
Content-Length: 15728640
Content-Disposition: attachment; filename="video.mp4"
```

**Body:** 视频文件的二进制流

### 错误响应 (404)

```json
{
  "error": {
    "message": "Video not found or not ready",
    "code": "video_not_found"
  }
}
```

---

## 注意事项

1. **任务状态**: 只有状态为 `completed` 的任务才能获取视频内容
2. **文件大小**: 视频文件可能较大，建议使用流式下载 (stream=True)
3. **超时设置**: 下载大文件时建议增加请求超时时间
4. **网络重试**: 建议实现下载失败重试机制
5. **存储空间**: 下载前确保有足够的磁盘空间
6. **过期时间**: 视频在任务完成后 24 小时内有效，请及时下载
7. **音频支持**: Sora 2 生成的视频包含音频

---

## 常见错误码

| 错误码 | 说明 | 解决方案 |
|--------|------|---------|
| `video_not_found` | 视频任务不存在 | 检查 video_id 是否正确 |
| `video_not_ready` | 视频尚未生成完成 | 等待任务完成后再请求 |
| `video_expired` | 视频已过期 | 视频已被删除，需要重新生成 |
| `unauthorized` | 认证失败 | 检查 API Key 是否正确 |

---

## 相关接口

- [创建视频生成任务](/sora/create)
- [查询视频任务状态](/sora/status)
- [Remix 视频混剪](/sora/remix)
