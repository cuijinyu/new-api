# 生成图像

在给定提示的情况下创建图像。[了解更多](https://platform.openai.com/docs/guides/images)。

## 接口详情

**接口地址：** `POST /v1/images/generations`

**功能描述：** 根据文本提示生成图像。支持多种模型、尺寸和质量设置。

**认证方式：** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 请求参数

### Header 参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| Authorization | string | 是 | Bearer Token 认证 | Bearer sk-xxx... |
| Content-Type | string | 是 | 内容类型 | application/json |

### Body 参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 | 约束 |
|--------|------|------|--------|------|------|
| model | string | 否 | dall-e-2 | 使用的模型 ID | dall-e-2, dall-e-3 |
| prompt | string | 是 | - | 图像描述文本 | 最大 1000 字符 (dall-e-2) 或 4000 字符 (dall-e-3) |
| n | integer | 否 | 1 | 生成图像的数量 | 1-10 (dall-e-2), 1 (dall-e-3) |
| size | string | 否 | 1024x1024 | 图像尺寸 | 256x256, 512x512, 1024x1024, 1792x1024, 1024x1792 |
| quality | string | 否 | standard | 图像质量 (仅限 dall-e-3) | standard, hd |
| style | string | 否 | vivid | 图像风格 (仅限 dall-e-3) | vivid, natural |
| response_format | string | 否 | url | 响应格式 | url, b64_json |
| user | string | 否 | - | 用户标识符 | - |

---

## 响应参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| created | integer | 创建时间的 Unix 时间戳 |
| data | array[object] | 图像对象列表 |
| data.url | string | 图像 URL (如果 response_format 为 url) |
| data.b64_json | string | Base64 编码的图像数据 (如果 response_format 为 b64_json) |
| data.revised_prompt | string | 模型优化后的提示词 (仅限 dall-e-3) |

---

## 代码示例

### Python (使用 OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://your-domain.com/v1"
)

response = client.images.generate(
  model="dall-e-3",
  prompt="一只在太空中行走的可爱猫咪，写实风格",
  size="1024x1024",
  quality="standard",
  n=1,
)

image_url = response.data[0].url
print(image_url)
```

### Curl 示例

```bash
curl https://your-domain.com/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "dall-e-3",
    "prompt": "一只在太空中行走的可爱猫咪，写实风格",
    "n": 1,
    "size": "1024x1024"
  }'
```

---

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /v1/images/generations:
    post:
      summary: 生成图像
      deprecated: false
      description: 根据文本提示生成图像
      operationId: createImage
      tags:
        - 图片生成/编辑(Images)/OpenAI兼容格式
        - Images
      parameters: []
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ImageGenerationRequest'
      responses:
        '200':
          description: 成功生成图像
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ImageResponse'
          headers: {}
          x-apifox-name: 成功
      security:
        - BearerAuth: []
          x-apifox:
            schemeGroups:
              - id: jwrCZj4thx9ahcLD3WQGo
                schemeIds:
                  - BearerAuth
            required: true
            use:
              id: jwrCZj4thx9ahcLD3WQGo
            scopes:
              jwrCZj4thx9ahcLD3WQGo:
                BearerAuth: []
      x-apifox-folder: 图片生成/编辑(Images)/OpenAI兼容格式
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/7484041/apis/api-383826479-run
components:
  schemas:
    ImageGenerationRequest:
      type: object
      required:
        - prompt
      properties:
        model:
          type: string
          examples:
            - dall-e-3
        prompt:
          type: string
          description: 图像描述
        'n':
          type: integer
          minimum: 1
          maximum: 10
          default: 1
        size:
          type: string
          enum:
            - 256x256
            - 512x512
            - 1024x1024
            - 1792x1024
            - 1024x1792
          default: 1024x1024
        quality:
          type: string
          enum:
            - standard
            - hd
          default: standard
        style:
          type: string
          enum:
            - vivid
            - natural
          default: vivid
        response_format:
          type: string
          enum:
            - url
            - b64_json
          default: url
        user:
          type: string
      x-apifox-orders:
        - model
        - prompt
        - 'n'
        - size
        - quality
        - style
        - response_format
        - user
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ImageResponse:
      type: object
      properties:
        created:
          type: integer
        data:
          type: array
          items:
            type: object
            properties:
              url:
                type: string
              b64_json:
                type: string
              revised_prompt:
                type: string
            x-apifox-orders:
              - url
              - b64_json
              - revised_prompt
            x-apifox-ignore-properties: []
      x-apifox-orders:
        - created
        - data
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes:
    BearerAuth:
      type: bearer
      scheme: bearer
      description: |
        使用 Bearer Token 认证。
        格式: `Authorization: Bearer sk-xxxxxx`
servers: []
security:
  - BearerAuth: []
    x-apifox:
      schemeGroups:
        - id: jwrCZj4thx9ahcLD3WQGo
          schemeIds:
            - BearerAuth
      required: true
      use:
        id: jwrCZj4thx9ahcLD3WQGo
      scopes:
        jwrCZj4thx9ahcLD3WQGo:
          BearerAuth: []
```
