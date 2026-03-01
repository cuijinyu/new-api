# Kling 全能视频 (Omni Video)

Kling 全能视频是 Kling 的统一多模态视频生成端点，支持丰富的多模态输入，包括多张图片、视频参考、主体控制等，能够实现精确的动作控制和丰富的视觉表达。

::: tip V3 新特性
`kling-v3-0` 模型在 Omni 端点上新增了以下能力：
- **扩展时长**：支持 3-15 秒（旧版 O1 为 3-10 秒）
- **多镜头叙事 (Multi-shot)**：单次请求生成多个连续镜头，最多 6 个分镜
- **视频编辑模式**：通过 `refer_type: "base"` 对现有视频进行文本指令编辑
- **原生音频**：支持生成同步音频（含多语言口型同步）
- **VIDEO 元素引用**：`element_list` 支持从视频片段提取的角色元素
:::

## 接口详情

**接口地址：** `POST /kling/v1/videos/omni-video`

**功能描述：** 提交一个全能视频生成任务。支持混合输入（文本、图片、视频、主体元素）。

**认证方式：** Bearer Token
```http
Authorization: Bearer YOUR_API_TOKEN
```

---

## 支持的模型

| 模型 | 说明 | Duration 范围 | Multi-shot | 视频编辑 | 原生音频 |
|------|------|---------------|------------|----------|----------|
| `kling-v3-0` | Video 3.0，最新版本 | 3-15s | ✅ | ✅ | ✅ |
| `kling-video-o1` | Omni V1 | 3-10s | ❌ | ❌ | ❌ |

---

## 请求参数

### Body 参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 | 示例 |
|--------|------|------|--------|------|------|
| model | string | 是 | - | 使用的模型 ID | `kling-v3-0` |
| prompt | string | 条件必填 | - | 视频描述文本。使用 `multi_prompt` 时不可同时传入 | `一个在森林里奔跑的小狐狸` |
| negative_prompt | string | 否 | - | 负向提示词 | `模糊, 水印` |
| mode | string | 否 | `std` | 生成模式：`std` (标准 720p), `pro` (专业 1080p) | `std`, `pro` |
| duration | string | 否 | `5` | 视频时长（秒）。使用 `multi_prompt` 时不可同时传入。详见下方 Duration 规则 | `5`, `10`, `15` |
| aspect_ratio | string | 否 | `16:9` | 视频比例 | `16:9`, `9:16`, `1:1` |
| image_list | array | 否 | - | 参考图片列表 | 见下方 OmniImageItem |
| video_list | array | 否 | - | 参考视频列表（使用视频参考会增加费用倍率） | 见下方 OmniVideoItem |
| element_list | array | 否 | - | 主体元素列表 | `[{"element_id": 123456}]` |
| multi_prompt | array | 否 | - | **V3 专属** 多镜头分镜列表，最多 6 个 shot | 见下方 MultiShotItem |
| sound | string | 否 | `off` | 是否生成原生音频。V3 支持 `on`/`off`，V2.6 支持 `on`/`off` | `on`, `off` |
| cfg_scale | float | 否 | 0.5 | 提示词相关性 | 0.0 - 1.0 |
| external_task_id | string | 否 | - | 自定义任务 ID | `my_task_001` |
| callback_url | string | 否 | - | 任务完成后回调地址 | `https://your-api.com/callback` |

### Duration 规则

| 模型 | 工作流 | 支持的 Duration |
|------|--------|----------------|
| `kling-v3-0` | 所有工作流 | `3` - `15` |
| `kling-v3-0` | Multi-shot | 各 shot duration 之和须在 3-15 范围内 |
| `kling-v3-0` | 视频编辑 (refer_type=base) | 自动跟随原视频时长 |
| `kling-video-o1` | 文生/普通图生 | `5`, `10` |
| `kling-video-o1` | 首尾帧/视频参考 | `3` - `10` |

### OmniImageItem

| 参数名 | 类型 | 说明 |
|--------|------|------|
| image_url | string | 图片 URL |
| type | string | 图片作用：`first_frame` (首帧), `end_frame` (尾帧)，不传则为普通参考图 |

### OmniVideoItem

| 参数名 | 类型 | 说明 |
|--------|------|------|
| video_url | string | 视频 URL |
| refer_type | string | 参考类型：`feature` (特征参考) 或 `base` (视频编辑，仅 `kling-v3-0` 支持) |
| keep_original_sound | string | 是否保留原声：`yes`, `no` |

### MultiShotItem (V3 专属)

多镜头模式下的单个分镜定义。使用 `multi_prompt` 时，`prompt` 和 `duration` 参数不可同时传入。

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| prompt | string | 是 | 该分镜的描述文本，最长 2500 字符。支持 `@image_1`、`@element_1` 等引用语法 |
| duration | string | 是 | 该分镜时长（秒），每个 shot 至少 3 秒 |

::: warning 多镜头限制
- 最少 2 个 shot，最多 6 个 shot
- 各 shot 的 duration 总和须在 3-15 秒范围内
- 每个 shot 的 duration 至少为 3 秒
:::

---

## 计费说明

| 模型 | 模式 | 基础价格 | 含音频 | 含视频输入 |
|------|------|---------|--------|-----------|
| `kling-v3-0` | Std | 按秒计费 | ×1.5 | ×1.5 |
| `kling-v3-0` | Pro | 按秒计费 ×1.333 | ×1.5 | ×1.5 |
| `kling-video-o1` | Std | 按秒计费 | - | ×1.5 |
| `kling-video-o1` | Pro | 按秒计费 ×1.333 | - | ×1.5 |

---

## 响应参数

提交成功后返回 OpenAI 兼容的 `video` 对象。

| 参数名 | 类型 | 说明 |
|--------|------|------|
| id | string | 任务 ID |
| task_id | string | 任务 ID (兼容性字段) |
| object | string | 对象类型，固定为 `video` |
| model | string | 使用的模型 ID |
| created_at | integer | 创建时间戳 |

---

## 代码示例

### 基础用法 - 文生视频

```bash
curl https://your-domain.com/kling/v1/videos/omni-video \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "kling-v3-0",
    "prompt": "一只在森林里奔跑的小狐狸，阳光透过树叶洒下斑驳的光影",
    "duration": "10",
    "aspect_ratio": "16:9",
    "sound": "on"
  }'
```

### 图生视频 - 首尾帧模式

```bash
curl https://your-domain.com/kling/v1/videos/omni-video \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "kling-v3-0",
    "prompt": "让人物从站立缓缓坐下",
    "image_list": [
      {"image_url": "https://example.com/start.jpg", "type": "first_frame"},
      {"image_url": "https://example.com/end.jpg", "type": "end_frame"}
    ],
    "duration": "5"
  }'
```

### V3 多镜头叙事 (Multi-shot)

```bash
curl https://your-domain.com/kling/v1/videos/omni-video \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "kling-v3-0",
    "multi_prompt": [
      {"prompt": "一个女孩推开咖啡店的门走进去，镜头跟随", "duration": "4"},
      {"prompt": "女孩坐在窗边，打开笔记本电脑，特写", "duration": "4"},
      {"prompt": "窗外下起了雨，女孩微笑着看向窗外，中景", "duration": "5"}
    ],
    "aspect_ratio": "16:9",
    "mode": "pro",
    "sound": "on"
  }'
```

### V3 视频编辑 (refer_type=base)

```bash
curl https://your-domain.com/kling/v1/videos/omni-video \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "kling-v3-0",
    "prompt": "将背景替换为雪山风景",
    "video_list": [
      {
        "video_url": "https://example.com/original.mp4",
        "refer_type": "base",
        "keep_original_sound": "yes"
      }
    ]
  }'
```

### 响应示例

```json
{
  "id": "842250903629086785",
  "task_id": "842250903629086785",
  "object": "video",
  "model": "kling-v3-0",
  "created_at": 1737367800
}
```
