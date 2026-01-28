# 豆包视频生成

使用豆包 Seedance 模型创建视频生成任务，支持文生视频和图生视频。

## 接口详情

**接口地址:** `POST /v1/video/generations`

**功能描述:** 使用豆包 Seedance 系列模型创建视频生成任务。支持文生视频 (Text-to-Video) 和图生视频 (Image-to-Video)，可生成高质量的 AI 视频内容。

**认证方式:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 支持的模型

| 模型名称 | 说明 | 特点 |
|----------|------|------|
| `doubao-seedance-1-0-pro-250528` | Seedance Pro 版本 | 高质量视频生成，适合专业场景 |
| `doubao-seedance-1-0-lite-t2v` | Seedance Lite 文生视频 | 轻量版，文本生成视频 |
| `doubao-seedance-1-0-lite-i2v` | Seedance Lite 图生视频 | 轻量版，图片生成视频 |

---

## 请求参数

### Body 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| model | string | 是 | 模型 ID | `doubao-seedance-1-0-pro-250528` |
| prompt | string | 是 | 视频生成提示词 | `一只可爱的小猫在花园里玩耍` |
| images | array | 否 | 图片 URL 数组 (用于图生视频) | `["https://example.com/image.jpg"]` |

---

## 响应参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| task_id | string | 任务唯一标识符，用于查询任务状态 |

---

## 代码示例

### cURL

```bash
curl -X POST "https://your-domain.com/v1/video/generations" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seedance-1-0-pro-250528",
    "prompt": "一只可爱的小猫在花园里玩耍，阳光明媚，画面温馨"
  }'
```

### Python

```python
import requests
import json

url = "https://your-domain.com/v1/video/generations"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}

# 文生视频示例
data = {
    "model": "doubao-seedance-1-0-pro-250528",
    "prompt": "一只可爱的小猫在花园里玩耍，阳光明媚，画面温馨"
}

response = requests.post(url, headers=headers, json=data)
result = response.json()
print(json.dumps(result, indent=2, ensure_ascii=False))

# 获取 task_id 用于后续查询
task_id = result.get("task_id")
print(f"任务ID: {task_id}")
```

### Python (图生视频)

```python
import requests
import json

url = "https://your-domain.com/v1/video/generations"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}

# 图生视频示例
data = {
    "model": "doubao-seedance-1-0-lite-i2v",
    "prompt": "让图片中的人物微笑并挥手",
    "images": ["https://example.com/your-image.jpg"]
}

response = requests.post(url, headers=headers, json=data)
result = response.json()
print(json.dumps(result, indent=2, ensure_ascii=False))
```

### JavaScript

```javascript
const response = await fetch('https://your-domain.com/v1/video/generations', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer YOUR_API_KEY',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    model: 'doubao-seedance-1-0-pro-250528',
    prompt: '一只可爱的小猫在花园里玩耍，阳光明媚，画面温馨'
  })
});

const result = await response.json();
console.log('任务ID:', result.task_id);
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
    url := "https://your-domain.com/v1/video/generations"
    
    payload := map[string]interface{}{
        "model":  "doubao-seedance-1-0-pro-250528",
        "prompt": "一只可爱的小猫在花园里玩耍，阳光明媚，画面温馨",
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

---

## 响应示例

### 成功响应 (200)

```json
{
  "task_id": "task_abc123xyz456"
}
```

---

## 注意事项

1. **异步处理**: 视频生成是异步过程，提交任务后需要通过查询接口获取生成结果
2. **模型选择**: 
   - 使用 `doubao-seedance-1-0-lite-t2v` 进行文生视频
   - 使用 `doubao-seedance-1-0-lite-i2v` 进行图生视频
   - 使用 `doubao-seedance-1-0-pro-250528` 获得更高质量的输出
3. **提示词建议**: 提供详细、具体的描述可以获得更好的生成效果
4. **图片要求**: 图生视频时，请确保图片 URL 可公开访问

---

## 相关接口

- [查询豆包视频任务状态](/docs/doubao-video-status)
