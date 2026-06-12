# Service Inference Seedance 2.0 E2E Verification

Date: 2026-06-11

## Scope

Verified a real end-to-end call through local new-api:

- HTTP entry: `POST /v1/video/generations`
- Channel type: `57`
- Provider: `https://model.service-inference.ai`
- Model: `dreamina-seedance-2-0-260128`
- Tier: `480p_no_ref`
- Duration: `4`
- Audio: disabled
- Watermark: disabled

Secrets and signed media URLs are intentionally omitted.

## Real Task

Recorded task:

```text
task_id = mvt-512d4ffd9ce54256
status = SUCCESS
progress = 100%
outputs_count = 1
```

The provider returned:

```json
{
  "completion_tokens": 40594,
  "total_tokens": 40594
}
```

The stored task data is redacted:

```text
task.outputs removed
task.outputs_count = 1
```

## Output Retrieval

Direct provider media URL check:

```text
HTTP 206
content-type = video/mp4
range bytes downloaded = 2048
```

new-api proxy check:

```text
GET /v1/videos/mvt-512d4ffd9ce54256/content
HTTP 200
content-type = video/mp4
bytes downloaded = 357434
```

## Billing Verification

Configured provider price:

```text
480p_no_ref = $7.00 / 1M tokens
QuotaPerUnit = 500000
group_ratio = 1
```

Pre-consumption:

```text
estimated_tokens = 48000
preconsumed_quota = 48000 / 1_000_000 * 7.00 * 500000
                  = 168000
```

Final settlement:

```text
actual_quota = 40594 / 1_000_000 * 7.00 * 500000
             = 142078
quota_delta  = 142078 - 168000
             = -25922
```

Verified persisted state after settlement replay:

```text
task.quota = 142078
user.used_quota = 142078
token.used_quota = 142078
channel.used_quota = 142078
user.quota = 999857922
token.remain_quota = 999857922
```

## Logs

Pre-consume log:

```text
type = consume
quota = 168000
```

Settlement log:

```text
type = refund
quota = -25922
completion_tokens = 40594
other.billing_event = video_task_settlement
other.provider = service-inference
other.actual_quota = 142078
other.preconsumed_quota = 168000
other.quota_delta = -25922
other.total_tokens = 40594
other.outputs_count = 1
```

## Issues Found And Fixed

1. SQLite `channel_info` scan failed when the driver returned `string` instead of `[]byte`.
   Fixed `ChannelInfo.Scan` to support `string`, `[]byte`, nil, and empty values.

2. Service Inference submit returned `202 Accepted`, but task submit treated only `200 OK` as success.
   Fixed task submit handling to accept all 2xx responses.

3. Async video settlement corrected user and channel quotas but did not adjust token quota.
   Fixed supplement/refund settlement to update token quota by `token_id` without storing token key in task JSON.

## Remaining Operational Note

The existing local `one-api.db` has a separate SQLite re-migration issue (`invalid DDL, unbalanced brackets`) on application startup. E2E verification used a clean temporary SQLite database to isolate Seedance behavior from that pre-existing migration problem.
