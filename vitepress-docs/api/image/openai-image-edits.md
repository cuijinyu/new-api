# 图像编辑

编辑或扩展现有图像。

## 接口详情

**接口地址：** `POST /v1/images/edits`

**功能描述：** 根据文本提示对现有图像进行编辑。支持图像修复和扩展。

**认证方式：** Bearer Token

```http
Authorization: Bearer YOUR_API_TOKEN
```

## 请求参数

### Header 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| Authorization | string | 是 | Bearer Token 认证 | `Bearer sk-xxx...` |
| Content-Type | string | 是 | 内容类型 | `multipart/form-data` |

### Body 参数 (Multipart Form Data)

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| image | file | 是 | 要编辑的原始图像 (PNG, 小于 4MB, 正方形) |
| prompt | string | 是 | 描述期望编辑效果的文本 |
| mask | file | 否 | 遮罩图像，定义要编辑的区域 (PNG, 透明区域表示编辑区域) |
| model | string | 否 | 使用的模型 ID |
| n | integer | 否 | 生成图像数量 (1-10) |
| size | string | 否 | 图像尺寸 (`256x256`, `512x512`, `1024x1024`) |
| response_format | string | 否 | 响应格式 (`url`, `b64_json`) |

## 响应参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| created | integer | 创建时间戳 |
| data | array | 图像对象列表 |
| data[].url | string | 图像 URL |
| data[].b64_json | string | Base64 编码的图像数据 |

## 代码示例

### Python

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://ezmodel.cloud/v1"
)

response = client.images.edit(
    model="dall-e-2",
    image=open("original.png", "rb"),
    mask=open("mask.png", "rb"),
    prompt="在图片中添加一只蝴蝶",
    n=1,
    size="1024x1024"
)

print(response.data[0].url)
```

### cURL

```bash
curl https://ezmodel.cloud/v1/images/edits \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -F image="@original.png" \
  -F mask="@mask.png" \
  -F prompt="在图片中添加一只蝴蝶" \
  -F n=1 \
  -F size="1024x1024"
```

## 注意事项

::: tip 图像要求
- 原始图像必须是 PNG 格式
- 图像必须是正方形
- 文件大小不能超过 4MB
:::

::: tip 遮罩说明
- 遮罩图像中的透明区域表示需要编辑的部分
- 遮罩必须与原始图像尺寸相同
:::
