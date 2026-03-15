# Usage Log Query

Query usage logs for a specific Token using the API Key directly — no login required. Useful for usage analysis, cost accounting, and reconciliation.

## Endpoint

```http
GET /api/log/token
```

## Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `key` | string | Yes | API Key, e.g. `sk-xxx` |
| `p` | int | Yes | Page number, starting from `1` |
| `page_size` | int | Yes | Items per page, max `100` |
| `start_timestamp` | int64 | Yes | Start time (Unix seconds) |
| `end_timestamp` | int64 | Yes | End time (Unix seconds) |
| `type` | int | No | Log type: `0` all, `1` topup, `2` consume, `5` error, `6` refund |
| `model_name` | string | No | Model name (fuzzy match) |

## Example

::: code-group

```bash [cURL]
# Query consumption logs from the last 7 days, page 1, 20 items per page
curl "https://www.ezmodel.cloud/api/log/token?\
key=sk-your-api-key&\
p=1&\
page_size=20&\
type=2&\
start_timestamp=1710000000&\
end_timestamp=1710604800"
```

```python [Python]
import requests
import time

base_url = "https://www.ezmodel.cloud"
now = int(time.time())
week_ago = now - 7 * 86400

resp = requests.get(f"{base_url}/api/log/token", params={
    "key": "sk-your-api-key",
    "p": 1,
    "page_size": 20,
    "type": 2,  # consumption logs
    "start_timestamp": week_ago,
    "end_timestamp": now,
})
data = resp.json()
print(f"Total: {data['data']['total']} logs")
for log in data["data"]["items"]:
    print(f"  {log['model_name']}: {log['prompt_tokens']}+{log['completion_tokens']} tokens")
```

:::

## Response Format

```json
{
  "success": true,
  "message": "",
  "data": {
    "page": 1,
    "page_size": 20,
    "total": 156,
    "items": [
      {
        "id": 42,
        "created_at": 1710500000,
        "type": 2,
        "username": "your_username",
        "token_name": "my-token",
        "model_name": "gpt-4o",
        "quota": 5000,
        "prompt_tokens": 1200,
        "completion_tokens": 800,
        "use_time": 3,
        "is_stream": true,
        "group": "default",
        "other": "{\"model_ratio\":1.5,\"request_path\":\"/v1/chat/completions\"}"
      }
    ]
  }
}
```

## Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Log ID |
| `created_at` | int64 | Creation time (Unix seconds) |
| `type` | int | Log type |
| `token_name` | string | Token name |
| `model_name` | string | Model name |
| `quota` | int | Quota consumed |
| `prompt_tokens` | int | Input token count |
| `completion_tokens` | int | Output token count |
| `use_time` | int | Request duration (seconds) |
| `is_stream` | bool | Whether streaming was used |
| `group` | string | User group |
| `other` | string | Extended info (JSON string with pricing ratios, cache details, etc.) |

## Error Handling

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `key is required` | API Key not provided | Pass the full API Key in the `key` parameter |
| `record not found` | Invalid or non-existent API Key | Verify the Key is correct |
| `start_timestamp and end_timestamp are required` | Missing time range | Add both timestamp parameters |
| `p and page_size are required` | Missing pagination parameters | Add `p` and `page_size` parameters |

## Best Practices

::: tip Performance Tips
1. **Use a reasonable time range** — narrower ranges yield faster queries
2. **Use reasonable page sizes** — 20-50 recommended, max 100
3. **Filter by model** if you only need usage for specific models
4. **Paginate through all data** — increment `p` until `items` is empty or `page * page_size >= total`
:::

## Next Steps

- See [Getting Started](/en/guide/getting-started) for basic API usage
- See [Code Examples](/en/guide/examples) for integration in various languages
