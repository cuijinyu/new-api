# Seedance 2.0 Video Generation

Use the OpenAI-compatible video task API to call Seedance 2.0 through Service Inference. The API is asynchronous: submit a task, receive a `task_id`, then poll the task until the video is ready.

## Endpoints

| Operation | Method | Path |
|-----------|--------|------|
| Create video task | POST | `/v1/video/generations` |
| Query task status | GET | `/v1/video/generations/{task_id}` |
| Download video content | GET | `/v1/video/generations/{task_id}/content` |

Authentication:

```http
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

## Available Models

| Model | Description | Resolutions |
|-------|-------------|-------------|
| `dreamina-seedance-2-0-260128` | Standard Seedance 2.0 | `480p`, `720p`, `1080p` |
| `dreamina-seedance-2-0-ep` | Seedance 2.0 EP version | `480p`, `720p`, `1080p` |
| `dreamina-seedance-2-0-fast-260128` | Fast Seedance 2.0 | `480p`, `720p` |
| `doubao-seedance-2-0-260128` | Compatible alias | `480p`, `720p`, `1080p` |
| `doubao-seedance-2-0-fast-260128` | Fast compatible alias | `480p`, `720p` |

If your deployment uses model mapping, you may call the public model name shown by the site; it will be forwarded to the mapped upstream Seedance model.

## Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | Yes | Model name |
| `prompt` | string | Yes | Video generation prompt |
| `image` | string | No | Single reference image URL, Base64 string, or upstream asset reference |
| `images` | string[] | No | Multiple reference image URLs, Base64 strings, or upstream asset references |
| `size` | string | No | Resolution: `480p`, `720p`, or `1080p`; billing defaults to `720p` |
| `duration` | integer | No | Video duration in seconds |
| `seconds` | string | No | Duration as a string; overrides `duration` when present |
| `metadata.resolution` | string | No | Upstream resolution; takes priority over `size` |
| `metadata.ratio` | string | No | Aspect ratio, for example `16:9`, `9:16`, or `1:1` |
| `metadata.generate_audio` | boolean | No | Whether to generate audio |
| `metadata.watermark` | boolean | No | Whether to add a watermark |
| `metadata.content` | array | No | Upstream content items for audio, video, or other references |

The top-level `prompt` is converted to a text content item. `image` and `images` are converted to `image_url` reference content items.

## Text-to-Video Example

```bash
curl https://api.ezmodel.cloud/v1/video/generations \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dreamina-seedance-2-0-260128",
    "prompt": "A cinematic shot of a glass perfume bottle on a marble table, soft morning light, slow camera push in",
    "size": "720p",
    "duration": 4,
    "metadata": {
      "ratio": "16:9",
      "generate_audio": false,
      "watermark": false
    }
  }'
```

Response:

```json
{
  "task_id": "mvt-512d4ffd9ce54256",
  "status": "pending"
}
```

## Image-to-Video Example

```bash
curl https://api.ezmodel.cloud/v1/video/generations \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dreamina-seedance-2-0-fast-260128",
    "prompt": "Make the product rotate slowly, keep the label sharp and readable",
    "image": "https://example.com/product.png",
    "size": "720p",
    "seconds": "4",
    "metadata": {
      "ratio": "1:1"
    }
  }'
```

## Multiple Reference Assets

Use `metadata.content` when you need to pass audio or additional reference assets. The `type`, `image_url`, `audio_url`, and `video_url` content items are forwarded to the upstream request.

```json
{
  "model": "dreamina-seedance-2-0-260128",
  "prompt": "Generate a relaxed lifestyle video matching the reference audio mood",
  "images": [
    "https://example.com/ref-1.jpg",
    "https://example.com/ref-2.jpg"
  ],
  "duration": 4,
  "metadata": {
    "resolution": "480p",
    "ratio": "9:16",
    "content": [
      {
        "type": "audio_url",
        "audio_url": {
          "url": "https://example.com/ref.mp3"
        },
        "role": "reference_audio"
      }
    ]
  }
}
```

## Query Task Status

```bash
curl https://api.ezmodel.cloud/v1/video/generations/mvt-512d4ffd9ce54256 \
  -H "Authorization: Bearer $YOUR_API_KEY"
```

When the task is finished, the status becomes `SUCCESS` or `completed`, and the response contains the generated video URL. Response wrapping may vary by deployment, so poll by `task_id` until the task reaches a terminal state.

## Download Video Content

After the task is completed, use the returned video URL directly or download through the content proxy:

```bash
curl -L https://api.ezmodel.cloud/v1/video/generations/mvt-512d4ffd9ce54256/content \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  --output seedance.mp4
```

The response is usually `video/mp4` and supports range downloads.

## Price Tier Selection

Seedance selects the price tier from the request payload:

| Item | Rule |
|------|------|
| Resolution | `metadata.resolution` takes priority, then `size`; if neither is set, billing defaults to `720p` |
| `with_ref` | Only upstream asset references, for example `asset://asset-xxx`, select the `with_ref` tier |
| `no_ref` | Text-only prompts, ordinary HTTPS image URLs, and Base64 image references use `no_ref` |
| Fast model | Only `480p` and `720p` are supported; do not request `1080p` |

Ordinary HTTPS image URLs are forwarded to the upstream service, but production supplier billing has verified that these direct URLs are settled as `no_ref`. Reference asset URLs must be directly downloadable by the upstream service. Use public HTTPS URLs that do not require cookies or anti-hotlinking headers. If the upstream returns `resource download failed`, use another image URL or a reachable object-storage URL.

## Billing

Seedance 2.0 is settled by the upstream `usage.total_tokens`, priced in USD per 1M tokens. The system precharges when the task is submitted, then refunds or supplements the difference after the task is completed.

| Model | Tier | Price |
|-------|------|-------|
| `dreamina-seedance-2-0-260128` / `dreamina-seedance-2-0-ep` | `480p_no_ref`, `720p_no_ref` | `$7.00 / 1M tok` |
| `dreamina-seedance-2-0-260128` / `dreamina-seedance-2-0-ep` | `480p_with_ref`, `720p_with_ref` | `$4.30 / 1M tok` |
| `dreamina-seedance-2-0-260128` / `dreamina-seedance-2-0-ep` | `1080p_no_ref` | `$7.70 / 1M tok` |
| `dreamina-seedance-2-0-260128` / `dreamina-seedance-2-0-ep` | `1080p_with_ref` | `$4.70 / 1M tok` |
| `dreamina-seedance-2-0-fast-260128` | `480p_no_ref`, `720p_no_ref` | `$5.60 / 1M tok` |
| `dreamina-seedance-2-0-fast-260128` | `480p_with_ref`, `720p_with_ref` | `$3.30 / 1M tok` |

Formula:

```text
final USD = usage.total_tokens / 1,000,000 * tier price
internal quota = final USD * 500000 * group ratio
```

Billing logs contain two kinds of rows: the task precharge row and the completion adjustment row. Reconciliation should merge the precharge and the adjustment for the same task; the merged net amount is the final cost.

Example: a 480p text-to-video task returns `total_tokens = 40594` at `$7.00 / 1M tok`:

```text
40594 / 1,000,000 * 7.00 = $0.284158
```

## Notes

- The Fast model is configured for `480p` and `720p`; do not request `1080p`.
- Ordinary HTTPS/Base64 image references are forwarded upstream but are settled with the supplier-matched `no_ref` tier; upstream `asset://` references select `with_ref`.
- `metadata.resolution` takes priority over the top-level `size`.
- Video generation is asynchronous; do not wait for the final video in the create request.
- Final billing follows the completed task usage. Failed tasks refund the precharged quota.
