# Kling Omni Video

Kling Omni Video is Kling's unified multimodal video generation endpoint, supporting rich multimodal inputs including multiple images, video references, and subject control, enabling precise motion control and rich visual expression.

::: tip V3 New Features
The `kling-v3-omni` model introduces the following new capabilities on the Omni endpoint:
- **Extended Duration**: Supports 3-15 seconds (legacy O1 supports 3-10 seconds)
- **Multi-shot Narrative**: Generate multiple consecutive shots in a single request, up to 6 shots
- **Video Editing Mode**: Edit existing videos with text instructions via `refer_type: "base"`
- **Native Audio**: Supports generating synchronized audio (with multilingual lip sync)
- **VIDEO Element Reference**: `element_list` supports character elements extracted from video clips
:::

## API Details

**Endpoint:** `POST /kling/v1/videos/omni-video`

**Description:** Submit an Omni video generation task. Supports mixed inputs (text, images, videos, subject elements).

**Authentication:** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## Supported Models

| Model | Description | Duration Range | Multi-shot | Video Editing | Native Audio |
|-------|-------------|----------------|------------|---------------|--------------|
| `kling-v3-omni` | Video 3.0, latest version | 3-15s | ✅ | ✅ | ✅ |
| `kling-video-o1` | Omni V1 | 3-10s | ❌ | ❌ | ❌ |

---

## Request Parameters

### Body Parameters

| Name | Type | Required | Default | Description | Example |
|------|------|----------|---------|-------------|---------|
| model | string | Yes | - | Model ID | `kling-v3-omni` |
| prompt | string | Conditional | - | Video description text. Cannot be used together with `multi_prompt` | `A small fox running in the forest` |
| negative_prompt | string | No | - | Negative prompts | `blur, watermark` |
| mode | string | No | `std` | Generation mode: `std` (Standard 720p), `pro` (Professional 1080p) | `std`, `pro` |
| duration | string | No | `5` | Video duration (seconds). Cannot be used together with `multi_prompt`. See Duration Rules below | `5`, `10`, `15` |
| aspect_ratio | string | No | `16:9` | Video aspect ratio | `16:9`, `9:16`, `1:1` |
| image_list | array | No | - | Reference image list | See OmniImageItem below |
| video_list | array | No | - | Reference video list (using video reference increases cost multiplier) | See OmniVideoItem below |
| element_list | array | No | - | Subject element list | `[{"element_id": 123456}]` |
| multi_prompt | array | No | - | **V3 Only** Multi-shot scene list, up to 6 shots | See MultiShotItem below |
| sound | string | No | `off` | Whether to generate native audio. V3 supports `on`/`off`. **Note: Cannot be `on` when using `video_list`** | `on`, `off` |
| cfg_scale | float | No | 0.5 | Prompt adherence scale | 0.0 - 1.0 |
| external_task_id | string | No | - | Custom task ID | `my_task_001` |
| callback_url | string | No | - | Callback URL after task completion | `https://your-api.com/callback` |

### Duration Rules

| Model | Workflow | Supported Duration |
|-------|----------|-------------------|
| `kling-v3-omni` | T2V / I2V | `3` - `15` |
| `kling-v3-omni` | Video reference (refer_type=feature) | `3` - `10` |
| `kling-v3-omni` | Multi-shot | Sum of all shot durations must be within 3-15 range |
| `kling-v3-omni` | Video editing (refer_type=base) | Automatically follows original video duration |
| `kling-video-o1` | T2V / basic I2V | `5`, `10` |
| `kling-video-o1` | First/end frame / video reference | `3` - `10` |

### OmniImageItem

| Name | Type | Description |
|------|------|-------------|
| image_url | string | Image URL |
| type | string | Image role: `first_frame`, `end_frame`. Omit for general reference image |

### OmniVideoItem

| Name | Type | Description |
|------|------|-------------|
| video_url | string | Video URL |
| refer_type | string | Reference type: `feature` (feature reference) or `base` (video editing, `kling-v3-omni` only) |
| keep_original_sound | string | Keep original sound: `yes`, `no` |

### MultiShotItem (V3 Only)

Defines a single shot in multi-shot mode. When using `multi_prompt`, the top-level `prompt` and `duration` parameters cannot be used.

| Name | Type | Required | Description |
|------|------|----------|-------------|
| prompt | string | Yes | Description text for this shot, max 2500 characters. Supports `@image_1`, `@element_1` reference syntax |
| duration | string | Yes | Duration of this shot (seconds), minimum 3 seconds per shot |

::: warning Multi-shot Constraints
- Minimum 2 shots, maximum 6 shots
- Total duration of all shots must be within 3-15 seconds
- Each shot must be at least 3 seconds
:::

::: danger Audio and Video Input are Mutually Exclusive
When using `video_list` (video reference or video editing), `sound: "on"` is **not supported**. The upstream API will return: `sound on is not supported with video input`.
:::

---

## Pricing

| Model | Mode | Base Price | With Audio | With Video Input |
|-------|------|-----------|------------|-----------------|
| `kling-v3-omni` | Std | Per-second billing | ×1.5 | ×1.5 |
| `kling-v3-omni` | Pro | Per-second billing ×1.333 | ×1.5 | ×1.5 |
| `kling-video-o1` | Std | Per-second billing | - | ×1.5 |
| `kling-video-o1` | Pro | Per-second billing ×1.333 | - | ×1.5 |

---

## Response Parameters

Returns an OpenAI-compatible `video` object upon successful submission.

| Name | Type | Description |
|------|------|-------------|
| id | string | Task ID |
| task_id | string | Task ID (Compatibility field) |
| object | string | Object type, fixed as `video` |
| model | string | Model ID used |
| created_at | integer | Creation timestamp |

---

## Code Examples

### Basic Usage - Text to Video

```bash
curl https://your-domain.com/kling/v1/videos/omni-video \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "kling-v3-omni",
    "prompt": "A fox running through a sunlit forest with dappled light filtering through the leaves",
    "duration": "10",
    "aspect_ratio": "16:9",
    "sound": "on"
  }'
```

### Image to Video - First/End Frame Mode

```bash
curl https://your-domain.com/kling/v1/videos/omni-video \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "kling-v3-omni",
    "prompt": "The character slowly sits down from a standing position",
    "image_list": [
      {"image_url": "https://example.com/start.jpg", "type": "first_frame"},
      {"image_url": "https://example.com/end.jpg", "type": "end_frame"}
    ],
    "duration": "5"
  }'
```

### V3 Multi-shot Narrative

```bash
curl https://your-domain.com/kling/v1/videos/omni-video \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "kling-v3-omni",
    "multi_prompt": [
      {"prompt": "A girl pushes open the door of a coffee shop and walks in, camera follows", "duration": "4"},
      {"prompt": "The girl sits by the window, opens her laptop, close-up shot", "duration": "4"},
      {"prompt": "Rain starts falling outside, the girl smiles and looks out the window, medium shot", "duration": "5"}
    ],
    "aspect_ratio": "16:9",
    "mode": "pro",
    "sound": "on"
  }'
```

### V3 Video Editing (refer_type=base)

```bash
curl https://your-domain.com/kling/v1/videos/omni-video \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "kling-v3-omni",
    "prompt": "Replace the background with a snowy mountain landscape",
    "video_list": [
      {
        "video_url": "https://example.com/original.mp4",
        "refer_type": "base",
        "keep_original_sound": "yes"
      }
    ]
  }'
```

### Response Example

```json
{
  "id": "842250903629086785",
  "task_id": "842250903629086785",
  "object": "video",
  "model": "kling-v3-omni",
  "created_at": 1737367800
}
```
