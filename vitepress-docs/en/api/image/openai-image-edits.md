# Edit Image

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
      summary: Edit Image
      deprecated: false
      description: Edit an existing image based on a prompt.
      operationId: createImageEdit
      tags:
        - Images/OpenAI Compatible
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
          description: Image edited successfully
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
