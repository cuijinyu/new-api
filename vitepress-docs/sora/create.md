# Sora 创建视频

OpenAI 兼容的视频生成接口,支持使用 Sora 模型生成高质量视频。

## 接口详情

**接口地址:** `POST /v1/videos`

**功能描述:** 使用 Sora 模型创建视频生成任务。支持文生视频和图生视频,可控制视频时长、尺寸、帧率等参数。

**参考文档:** [OpenAI Videos API](https://platform.openai.com/docs/api-reference/videos/create)

**认证方式:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 请求参数

### Body 参数 (multipart/form-data)

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| model | string | 否 | 模型/风格 ID | `sora-1.0`, `sora-turbo` |
| prompt | string | 否 | 文本描述提示词 | `一只金毛犬在海边奔跑` |
| image | string | 否 | 图片输入 (URL 或 Base64),用于图生视频 | `https://example.com/image.jpg` |
| duration | number | 否 | 视频时长(秒) | `5.0`, `10.0` |
| width | integer | 否 | 视频宽度 | `1920`, `1280` |
| height | integer | 否 | 视频高度 | `1080`, `720` |
| fps | integer | 否 | 视频帧率 | `24`, `30`, `60` |
| seed | integer | 否 | 随机种子,用于生成可复现的结果 | `12345` |
| n | integer | 否 | 生成视频数量 | `1`, `2` |
| response_format | string | 否 | 响应格式 | `url`, `b64_json` |
| user | string | 否 | 用户标识 | `user-123` |
| metadata | object | 否 | 扩展参数 (如 negative_prompt, style, quality_level 等) | `{"style": "cinematic"}` |

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
| error | object | 错误信息 (可选) |
| error.message | string | 错误描述 |
| error.code | string | 错误代码 |
| metadata | object | 额外元数据 |

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
curl -X POST "https://www.ezmodel.cloud/v1/videos" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sora-1.0",
    "prompt": "一只可爱的橘猫在阳光下打瞌睡,微风吹动它的毛发",
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
    "prompt": "一只可爱的橘猫在阳光下打瞌睡,微风吹动它的毛发",
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
    prompt: '一只可爱的橘猫在阳光下打瞌睡,微风吹动它的毛发',
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
        "prompt":   "一只可爱的橘猫在阳光下打瞌睡,微风吹动它的毛发",
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
            "prompt": "一只可爱的橘猫在阳光下打瞌睡,微风吹动它的毛发",
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
            ""prompt"": ""一只可爱的橘猫在阳光下打瞌睡,微风吹动它的毛发"",
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

## 响应示例

### 成功响应 (200)

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

### 错误响应 (400)

```json
{
  "error": {
    "message": "Invalid parameter: duration must be between 1 and 60 seconds",
    "code": "invalid_parameter"
  }
}
```

---

## 注意事项

1. **异步处理**: 视频生成是异步过程,提交后需要通过查询接口获取生成结果
2. **参数限制**: 不同模型对视频时长、尺寸、帧率等参数有不同的限制
3. **计费说明**: 视频生成按时长和分辨率计费,具体费率请参考定价页面
4. **过期时间**: 生成的视频会在一定时间后过期,建议及时下载保存
5. **并发限制**: 每个账户可能有并发任务数量限制

---

## 相关接口

- [查询视频任务状态](https://www.ezmodel.cloud/docs/sora-videos-status)
- [获取视频内容](https://www.ezmodel.cloud/docs/sora-videos-content)
