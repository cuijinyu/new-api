# Sora 创建视频

OpenAI 兼容的视频生成接口，支持使用 Sora 2 模型生成高质量视频。

## 接口详情

**接口地址:** `POST /v1/videos`

**功能描述:** 使用 Sora 2 模型创建视频生成任务。支持文生视频、图生视频，可控制视频时长和尺寸。

**参考文档:** [Azure OpenAI Sora 2 API](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/video-generation)

**认证方式:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 请求参数

### Body 参数

**文生视频**: 使用 `application/json` 格式

**图生视频**: 使用 `multipart/form-data` 格式

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| model | string | 否 | 模型名称 | `sora-2` |
| prompt | string | 是 | 文本描述提示词，建议包含镜头类型、主体、动作、场景、光线和镜头运动 | `A video of a cool cat on a motorcycle in the night` |
| size | string | 否 | 视频尺寸 (宽x高)，支持 `720x1280` (竖屏) 或 `1280x720` (横屏)，默认 `720x1280` | `1280x720` |
| seconds | string | 否 | 视频时长 (秒)，支持 `4`、`8`、`12`，默认 `4` | `8` |
| input_reference | file | 否 | 参考图片，用于图生视频。支持 JPEG、PNG、WebP 格式，**分辨率必须与 size 参数完全匹配** | 图片文件 |

---

## 响应参数

### 成功响应 (200)

| 参数名 | 类型 | 说明 |
|--------|------|------|
| id | string | 视频任务 ID，格式为 `video_xxx` |
| object | string | 对象类型，固定为 `video` |
| model | string | 使用的模型名称 |
| status | string | 任务状态: `queued`, `in_progress`, `completed`, `failed`, `cancelled` |
| progress | integer | 进度百分比 (0-100) |
| created_at | integer | 创建时间戳 (Unix timestamp) |
| completed_at | integer | 完成时间戳 (任务完成后可用) |
| expires_at | integer | 过期时间戳 (任务完成后可用，24小时后过期) |
| seconds | string | 视频时长 |
| size | string | 视频尺寸，格式: `{width}x{height}` |
| remixed_from_video_id | string | 如果是 Remix 生成的，显示源视频 ID |
| error | object | 错误信息 (任务失败时可用) |
| error.message | string | 错误描述 |
| error.code | string | 错误代码 |

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
# 文生视频 (JSON 格式)
curl -X POST "https://www.ezmodel.cloud/v1/videos" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sora-2",
    "prompt": "A video of a cool cat on a motorcycle in the night",
    "size": "1280x720",
    "seconds": "8"
  }'

# 图生视频 (multipart/form-data 格式)
curl -X POST "https://www.ezmodel.cloud/v1/videos" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "model=sora-2" \
  -F "prompt=The cat starts walking slowly towards the camera" \
  -F "size=1280x720" \
  -F "seconds=8" \
  -F "input_reference=@reference_image.jpg"
```

### Python

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://www.ezmodel.cloud/v1/",
)

# 文生视频
video = client.videos.create(
    model="sora-2",
    prompt="A video of a cool cat on a motorcycle in the night",
    size="1280x720",
    seconds="8",
)

print("Video generation started:", video)
print(f"Video ID: {video.id}")
print(f"Status: {video.status}")
```

### Python (图生视频 - 使用 OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://www.ezmodel.cloud/v1/",
)

# 使用本地图片作为参考
video = client.videos.create(
    model="sora-2",
    prompt="The cat starts walking slowly towards the camera",
    size="1280x720",
    seconds="8",
    input_reference=open("reference_image.png", "rb"),
)

print("Video generation started:", video)
```

### Python (图生视频 - 使用 requests + 图片尺寸调整)

```python
import requests
from PIL import Image
import io

url = "https://www.ezmodel.cloud/v1/videos"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
}

# 检查图片并调整尺寸
image_path = "test_local.jpg"
with Image.open(image_path) as img:
    original_width, original_height = img.size
    print(f"原始图片尺寸: {original_width}x{original_height}")

    # 根据图片比例选择目标尺寸 (只支持这两种)
    if original_height > original_width:
        # 竖屏，调整到720x1280
        target_size = (720, 1280)
        size_param = "720x1280"
    else:
        # 横屏或正方形，调整到1280x720
        target_size = (1280, 720)
        size_param = "1280x720"

    print(f"目标尺寸: {target_size[0]}x{target_size[1]}")

    # 调整图片尺寸
    img_resized = img.resize(target_size, Image.LANCZOS)

    # 保存到内存
    img_buffer = io.BytesIO()
    img_resized.save(img_buffer, format='JPEG', quality=95)
    img_buffer.seek(0)

# 准备表单数据
data = {
    "model": "sora-2",
    "prompt": "角马吃甜甜圈",
    "size": size_param,
    "seconds": "4"
}

# 发送请求 (multipart/form-data)
files = {"input_reference": ("image.jpg", img_buffer, "image/jpeg")}
response = requests.post(url, headers=headers, data=data, files=files)

result = response.json()
print(f"状态码: {response.status_code}")
print(f"响应: {result}")
```

### Python (URL 图片作为参考)

```python
from openai import OpenAI
import requests
from io import BytesIO

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://www.ezmodel.cloud/v1/",
)

# 从 URL 获取图片
image_url = "https://example.com/image.jpg"
response = requests.get(image_url)
image_data = BytesIO(response.content)
image_data.name = "image.jpg"

video = client.videos.create(
    model="sora-2",
    prompt="The scene comes to life with gentle movement",
    size="1280x720",
    seconds="8",
    input_reference=image_data,
)

print("Video generation started:", video)
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
    model: 'sora-2',
    prompt: 'A video of a cool cat on a motorcycle in the night',
    size: '1280x720',
    seconds: '8'
  })
});

const result = await response.json();
console.log('Video ID:', result.id);
console.log('Status:', result.status);
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
        "model":   "sora-2",
        "prompt":  "A video of a cool cat on a motorcycle in the night",
        "size":    "1280x720",
        "seconds": "8",
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
            "model": "sora-2",
            "prompt": "A video of a cool cat on a motorcycle in the night",
            "size": "1280x720",
            "seconds": "8"
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
            ""model"": ""sora-2"",
            ""prompt"": ""A video of a cool cat on a motorcycle in the night"",
            ""size"": ""1280x720"",
            ""seconds"": ""8""
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

### 错误响应 (400)

```json
{
  "error": {
    "message": "Invalid parameter: size must be 720x1280 or 1280x720",
    "code": "invalid_parameter"
  }
}
```

---

## 提示词最佳实践

为获得最佳视频生成效果，建议在提示词中包含以下元素：

1. **镜头类型**: 特写、中景、远景等
2. **主体描述**: 人物、动物、物体等
3. **动作描述**: 具体的动作和行为
4. **场景设置**: 环境、背景
5. **光线效果**: 日光、夜晚、逆光等
6. **镜头运动**: 推拉、摇移、跟随等

**示例提示词:**
```
A close-up shot of a golden retriever running on the beach at sunset, 
with waves crashing in the background, warm golden light, 
camera slowly tracking the dog's movement
```

---

## 内容限制

Sora 2 API 有以下内容限制：

- 仅生成适合 18 岁以下观众的内容
- 不支持生成版权角色和版权音乐
- 不支持生成真实人物（包括公众人物）
- 输入图片中不能包含人脸

请确保提示词和参考图片遵守这些规则，以避免生成失败。

---

## 注意事项

1. **异步处理**: 视频生成是异步过程，提交后需要通过查询接口获取生成结果
2. **分辨率限制**: 仅支持 `720x1280` (竖屏) 和 `1280x720` (横屏) 两种分辨率
3. **时长限制**: 仅支持 4、8、12 秒三种时长
4. **图片匹配**: 使用 `input_reference` 时，图片分辨率必须与 `size` 参数匹配
5. **并发限制**: 同时最多可有 2 个视频生成任务运行
6. **过期时间**: 生成的视频在 24 小时后过期，请及时下载保存
7. **音频支持**: Sora 2 支持在输出视频中生成音频

---

## 相关接口

- [查询视频任务状态](/sora/status)
- [获取视频内容](/sora/content)
- [Remix 视频混剪](/sora/remix)
