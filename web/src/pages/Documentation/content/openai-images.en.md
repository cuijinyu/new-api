# Image Generation

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
