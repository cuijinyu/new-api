# 使用日志查询

通过 API Key 直接查询该 Token 的使用日志，无需登录，方便进行用量分析、成本核算和对账。

## 接口详情

```http
GET /api/log/token
```

## 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `key` | string | 是 | API Key，如 `sk-xxx` |
| `p` | int | 是 | 页码，从 `1` 开始 |
| `page_size` | int | 是 | 每页条数，最大 `100` |
| `start_timestamp` | int64 | 是 | 开始时间（Unix 秒） |
| `end_timestamp` | int64 | 是 | 结束时间（Unix 秒） |
| `type` | int | 否 | 日志类型：`0` 全部、`1` 充值、`2` 消费、`5` 错误、`6` 退款 |
| `model_name` | string | 否 | 模型名称（模糊匹配） |

## 请求示例

::: code-group

```bash [cURL]
# 查询最近 7 天的消费日志，第 1 页，每页 20 条
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
    "type": 2,  # 消费日志
    "start_timestamp": week_ago,
    "end_timestamp": now,
})
data = resp.json()
print(f"总计 {data['data']['total']} 条日志")
for log in data["data"]["items"]:
    print(f"  {log['model_name']}: {log['prompt_tokens']}+{log['completion_tokens']} tokens")
```

:::

## 响应格式

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

## 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | 日志 ID |
| `created_at` | int64 | 创建时间（Unix 秒） |
| `type` | int | 日志类型 |
| `token_name` | string | Token 名称 |
| `model_name` | string | 模型名称 |
| `quota` | int | 消耗额度 |
| `prompt_tokens` | int | 输入 Token 数 |
| `completion_tokens` | int | 输出 Token 数 |
| `use_time` | int | 请求耗时（秒） |
| `is_stream` | bool | 是否流式请求 |
| `group` | string | 用户分组 |
| `other` | string | 扩展信息（JSON 字符串，含倍率、缓存等计费详情） |

## 错误处理

| 错误信息 | 原因 | 解决方案 |
|----------|------|----------|
| `key is required` | 未提供 API Key | 在 `key` 参数中传入完整的 API Key |
| `record not found` | API Key 无效或不存在 | 检查 Key 是否正确 |
| `start_timestamp and end_timestamp are required` | 未指定时间范围 | 添加 `start_timestamp` 和 `end_timestamp` 参数 |
| `p and page_size are required` | 未指定分页参数 | 添加 `p` 和 `page_size` 参数 |

## 最佳实践

::: tip 性能建议
1. **合理设置时间范围**：缩小时间范围可显著提升查询速度
2. **合理设置分页大小**：建议 `page_size` 设为 20-50，最大不超过 100
3. **使用模型过滤**：如果只关心特定模型的用量，通过 `model_name` 缩小范围
4. **遍历全部数据**：逐页递增 `p` 直到返回的 `items` 为空或 `page * page_size >= total`
:::

## 下一步

- 查看 [快速开始](/guide/getting-started) 了解 API 基本用法
- 查看 [代码示例](/guide/examples) 了解各语言的集成方式
