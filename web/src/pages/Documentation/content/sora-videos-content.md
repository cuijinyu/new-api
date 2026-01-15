# Sora 获取视频内容

获取已完成视频任务的视频文件内容。

此接口会代理返回视频文件流,可直接下载或在浏览器中播放。

## 接口详情

**接口地址:** `GET /v1/videos/{task_id}/content`

**功能描述:** 获取指定视频任务生成的视频文件。返回视频文件的二进制流,适合下载保存或直接播放。

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
curl -X GET "https://www.ezmodel.cloud/v1/videos/vid_abc123xyz456/content" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -o video.mp4

# 或者直接在终端查看响应头
curl -I "https://www.ezmodel.cloud/v1/videos/vid_abc123xyz456/content" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Python

```python
import requests

task_id = "vid_abc123xyz456"
url = f"https://www.ezmodel.cloud/v1/videos/{task_id}/content"
headers = {
    "Authorization": "Bearer YOUR_API_KEY"
}

# 下载视频
response = requests.get(url, headers=headers, stream=True)

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

const taskId = 'vid_abc123xyz456';
const url = `https://www.ezmodel.cloud/v1/videos/${taskId}/content`;

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
const taskId = 'vid_abc123xyz456';
const url = `https://www.ezmodel.cloud/v1/videos/${taskId}/content`;

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

// 或者在浏览器中直接播放
function playVideo() {
  const videoElement = document.getElementById('video-player');
  videoElement.src = url;
  videoElement.play();
}
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
    taskID := "vid_abc123xyz456"
    url := fmt.Sprintf("https://www.ezmodel.cloud/v1/videos/%s/content", taskID)
    
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
        String taskId = "vid_abc123xyz456";
        String url = "https://www.ezmodel.cloud/v1/videos/" + taskId + "/content";
        
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
        var taskId = "vid_abc123xyz456";
        var url = $"https://www.ezmodel.cloud/v1/videos/{taskId}/content";
        
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

## 使用场景

### 1. 直接下载保存

```python
import requests

def download_video(task_id, output_path):
    url = f"https://www.ezmodel.cloud/v1/videos/{task_id}/content"
    headers = {"Authorization": "Bearer YOUR_API_KEY"}
    
    response = requests.get(url, headers=headers, stream=True)
    
    if response.status_code == 200:
        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    return False

# 使用
if download_video("vid_abc123xyz456", "my_video.mp4"):
    print("下载成功!")
```

### 2. 在网页中播放

```html
<!DOCTYPE html>
<html>
<head>
    <title>视频播放</title>
</head>
<body>
    <video id="videoPlayer" controls width="640" height="360">
        您的浏览器不支持视频播放。
    </video>
    
    <script>
        const taskId = 'vid_abc123xyz456';
        const apiKey = 'YOUR_API_KEY';
        const url = `https://www.ezmodel.cloud/v1/videos/${taskId}/content`;
        
        // 方法1: 直接设置视频源(需要服务器支持CORS)
        const video = document.getElementById('videoPlayer');
        video.src = url;
        
        // 方法2: 通过fetch获取blob并播放
        fetch(url, {
            headers: {
                'Authorization': `Bearer ${apiKey}`
            }
        })
        .then(response => response.blob())
        .then(blob => {
            const blobUrl = URL.createObjectURL(blob);
            video.src = blobUrl;
        })
        .catch(error => console.error('加载视频失败:', error));
    </script>
</body>
</html>
```

### 3. 完整的下载流程(包含状态轮询)

```python
import requests
import time

def wait_and_download(task_id, output_path):
    base_url = "https://www.ezmodel.cloud/v1/videos"
    headers = {"Authorization": "Bearer YOUR_API_KEY"}
    
    # 轮询任务状态
    while True:
        status_response = requests.get(f"{base_url}/{task_id}", headers=headers)
        result = status_response.json()
        
        if result['status'] == 'completed':
            print("视频生成完成,开始下载...")
            break
        elif result['status'] == 'failed':
            print(f"视频生成失败: {result.get('error', {}).get('message')}")
            return False
        
        print(f"进度: {result['progress']}%")
        time.sleep(5)
    
    # 下载视频
    content_response = requests.get(
        f"{base_url}/{task_id}/content",
        headers=headers,
        stream=True
    )
    
    if content_response.status_code == 200:
        with open(output_path, "wb") as f:
            for chunk in content_response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"视频已保存到: {output_path}")
        return True
    
    return False

# 使用
wait_and_download("vid_abc123xyz456", "final_video.mp4")
```

---

## 注意事项

1. **任务状态**: 只有状态为 `completed` 的任务才能获取视频内容
2. **文件大小**: 视频文件可能较大,建议使用流式下载(stream=True)
3. **超时设置**: 下载大文件时建议增加请求超时时间
4. **网络重试**: 建议实现下载失败重试机制
5. **存储空间**: 下载前确保有足够的磁盘空间
6. **Content-Type**: 响应的 Content-Type 通常为 `video/mp4`,也可能是其他视频格式
7. **CORS 设置**: 在浏览器中直接播放需要服务器支持跨域访问

---

## 常见错误码

| 错误码 | 说明 | 解决方案 |
|--------|------|---------|
| `video_not_found` | 视频任务不存在 | 检查 task_id 是否正确 |
| `video_not_ready` | 视频尚未生成完成 | 等待任务完成后再请求 |
| `video_expired` | 视频已过期 | 视频已被删除,需要重新生成 |
| `unauthorized` | 认证失败 | 检查 API Key 是否正确 |

---

## 相关接口

- [创建视频生成任务](https://www.ezmodel.cloud/docs/sora-videos)
- [查询视频任务状态](https://www.ezmodel.cloud/docs/sora-videos-status)
