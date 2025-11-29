# 编辑图像

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /v1/images/edits:
    post:
      summary: 编辑图像
      deprecated: false
      description: 根据提示编辑现有图像
      operationId: createImageEdit
      tags:
        - 图片生成/编辑(Images)/OpenAI兼容格式
        - Images
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                image:
                  type: string
                  format: binary
                  example: ''
                mask:
                  type: string
                  format: binary
                  example: ''
                prompt:
                  type: string
                  example: ''
                model:
                  type: string
                  example: ''
                'n':
                  type: integer
                  example: 0
                size:
                  type: string
                  example: ''
                response_format:
                  type: string
                  example: ''
              required:
                - image
                - prompt
      responses:
        '200':
          description: 成功编辑图像
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
      x-run-in-apifox: https://app.apifox.com/web/project/7484041/apis/api-383826480-run
components:
  schemas:
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
