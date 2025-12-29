# Image Generation

Creates an image given a prompt. [Learn more](https://platform.openai.com/docs/guides/images).

## API Details

**Endpoint:** `POST /v1/images/generations`

**Description:** Creates an image given a text prompt. Supports various models, sizes, and quality settings.

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## Request Parameters

### Header Parameters

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| Authorization | string | Yes | Bearer Token authentication | Bearer sk-xxx... |
| Content-Type | string | Yes | Content type | application/json |

### Body Parameters

| Parameter | Type | Required | Default | Description | Constraints |
|-----------|------|----------|---------|-------------|-------------|
| model | string | No | dall-e-2 | The ID of the model to use | dall-e-2, dall-e-3 |
| prompt | string | Yes | - | A text description of the desired image(s) | Max 1000 chars (dall-e-2) or 4000 chars (dall-e-3) |
| n | integer | No | 1 | The number of images to generate | 1-10 (dall-e-2), 1 (dall-e-3) |
| size | string | No | 1024x1024 | The size of the generated images | 256x256, 512x512, 1024x1024, 1792x1024, 1024x1792 |
| quality | string | No | standard | The quality of the image (dall-e-3 only) | standard, hd |
| style | string | No | vivid | The style of the image (dall-e-3 only) | vivid, natural |
| response_format | string | No | url | The format in which the generated images are returned | url, b64_json |
| user | string | No | - | A unique identifier representing your end-user | - |

---

## Response Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| created | integer | The Unix timestamp of when it was created |
| data | array[object] | A list of image objects |
| data.url | string | The URL of the image (if response_format is url) |
| data.b64_json | string | The base64-encoded JSON of the image (if response_format is b64_json) |
| data.revised_prompt | string | The prompt that the model used to generate the image (dall-e-3 only) |

---

## Code Examples

### Python (using OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://your-domain.com/v1"
)

response = client.images.generate(
  model="dall-e-3",
  prompt="A cute cat walking in space, realistic style",
  size="1024x1024",
  quality="standard",
  n=1,
)

image_url = response.data[0].url
print(image_url)
```

### Curl Example

```bash
curl https://your-domain.com/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "dall-e-3",
    "prompt": "A cute cat walking in space, realistic style",
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
      summary: Generate Image
      deprecated: false
      description: Creates an image given a prompt.
      operationId: createImage
      tags:
        - Images/OpenAI Compatible
        - Images
      parameters: []
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ImageGenerationRequest'
      responses:
        '200':
          description: Image generated successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ImageResponse'
          headers: {}
          x-apifox-name: Success
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
      x-apifox-folder: Images/OpenAI Compatible
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/project/7484041/apis/api-383826479-run
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
          description: A text description of the desired image(s).
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
        Use Bearer Token authentication.
        Format: `Authorization: Bearer sk-xxxxxx`
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
