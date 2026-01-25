# Gemini 原生格式

Gemini 原生接口支持文本生成和图像生成。通过该接口，您可以直接调用 Gemini 的原生功能，包括最新的图像生成能力。

## 接口详情

**接口地址：** `POST /v1beta/models/{model}:generateContent`

**功能描述：** 根据提示词和配置生成内容。支持多模态输入（文本、图像）和多模态输出（文本、图像）。

**认证方式：** Bearer Token

```http
Authorization: Bearer YOUR_API_TOKEN
```

## 请求参数

### Path 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| model | string | 是 | 模型名称 | `gemini-2.0-flash-exp` |

### Header 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| Authorization | string | 是 | Bearer Token 认证 | `Bearer sk-xxx...` |
| Content-Type | string | 是 | 内容类型 | `application/json` |

### Body 参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| contents | array | 是 | 对话内容列表 |
| contents[].role | string | 否 | 角色 (`user`, `model`) |
| contents[].parts | array | 是 | 内容分段 |
| contents[].parts[].text | string | 否 | 文本提示词 |
| generationConfig | object | 否 | 生成配置选项 |
| generationConfig.responseModalities | array | 否 | 响应模态 (`TEXT`, `IMAGE`) |
| generationConfig.imageConfig | object | 否 | 图像生成配置 |
| generationConfig.imageConfig.aspectRatio | string | 否 | 图像比例 (`1:1`, `16:9`, `9:16` 等) |
| generationConfig.imageConfig.imageSize | string | 否 | 图像质量/尺寸 (`1K`, `2K`, `4K`) |

## 响应参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| candidates | array | 生成结果列表 |
| candidates[].content | object | 内容对象 |
| candidates[].content.parts | array | 内容分段，包含文本或生成的图像数据 |
| candidates[].finishReason | string | 完成原因 |
| usageMetadata | object | 使用统计信息 |
| usageMetadata.promptTokenCount | integer | 提示词 Token 数 |
| usageMetadata.candidatesTokenCount | integer | 生成内容 Token 数 |
| usageMetadata.totalTokenCount | integer | 总 Token 数 |

## 代码示例

### 文本生成

```bash
curl -X POST "https://ezmodel.cloud/v1beta/models/gemini-2.0-flash-exp:generateContent" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [
      {
        "parts": [
          {
            "text": "请介绍一下人工智能的发展历史"
          }
        ]
      }
    ]
  }'
```

### 图像生成

```bash
curl -X POST "https://ezmodel.cloud/v1beta/models/gemini-2.0-flash-exp:generateContent" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [
      {
        "parts": [
          {
            "text": "一只在森林里奔跑的赛博朋克风格的狐狸"
          }
        ]
      }
    ],
    "generationConfig": {
      "responseModalities": ["IMAGE"],
      "imageConfig": {
        "aspectRatio": "16:9",
        "imageSize": "1K"
      }
    }
  }'
```

### 响应示例

```json
{
  "candidates": [
    {
      "content": {
        "role": "model",
        "parts": [
          {
            "inlineData": {
              "mimeType": "image/png",
              "data": "iVBORw0KGgoAAA..."
            }
          }
        ]
      },
      "finishReason": "STOP"
    }
  ],
  "usageMetadata": {
    "promptTokenCount": 15,
    "candidatesTokenCount": 0,
    "totalTokenCount": 15
  }
}
```

## 支持的模型

| 模型 | 说明 |
|------|------|
| gemini-2.0-flash-exp | Gemini 2.0 Flash 实验版，支持图像生成 |
| gemini-1.5-pro | Gemini 1.5 Pro |
| gemini-1.5-flash | Gemini 1.5 Flash |

::: tip 提示
如果你习惯使用 OpenAI 格式，也可以使用 `/v1/chat/completions` 接口调用 Gemini 模型，系统会自动转换格式。
:::
