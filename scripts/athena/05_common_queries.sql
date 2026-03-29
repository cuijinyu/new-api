-- ============================================================
-- 常用查询模板集
-- 额度换算：quota ÷ 500000 = USD
-- ============================================================


-- ============================================================
-- A. 账单类查询
-- ============================================================

-- A1. 某用户某月账单（按模型汇总）
SELECT
    model_name,
    COUNT(*)                                    AS call_count,
    SUM(prompt_tokens)                          AS total_input_tokens,
    SUM(completion_tokens)                      AS total_output_tokens,
    SUM(prompt_tokens + completion_tokens)       AS total_tokens,
    SUM(quota)                                  AS total_quota,
    ROUND(SUM(quota) / 500000.0, 4)             AS total_usd
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '03'
  AND user_id = 123
GROUP BY model_name
ORDER BY total_usd DESC;


-- A2. 全平台月度账单（按用户汇总，出账单用）
SELECT
    user_id,
    username,
    COUNT(*)                                    AS call_count,
    SUM(prompt_tokens)                          AS total_input_tokens,
    SUM(completion_tokens)                      AS total_output_tokens,
    SUM(quota)                                  AS total_quota,
    ROUND(SUM(quota) / 500000.0, 4)             AS total_usd
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '03'
GROUP BY user_id, username
ORDER BY total_usd DESC;


-- A3. 全平台月度账单（按用户 × 模型明细）
SELECT
    user_id,
    username,
    model_name,
    COUNT(*)                                    AS call_count,
    SUM(prompt_tokens)                          AS total_input_tokens,
    SUM(completion_tokens)                      AS total_output_tokens,
    SUM(quota)                                  AS total_quota,
    ROUND(SUM(quota) / 500000.0, 4)             AS total_usd
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '03'
GROUP BY user_id, username, model_name
ORDER BY user_id, total_usd DESC;


-- A4. GMICloud 专用账单（特定渠道的 Claude 模型）
-- 替换 channel_id 为 GMI 对应的渠道 ID
SELECT
    model_name,
    COUNT(*)                                    AS call_count,
    SUM(prompt_tokens)                          AS total_input_tokens,
    SUM(completion_tokens)                      AS total_output_tokens,
    SUM(quota)                                  AS total_quota,
    ROUND(SUM(quota) / 500000.0, 4)             AS list_price_usd,
    ROUND(SUM(quota) / 500000.0 * 0.65, 4)      AS gmi_payable_usd,
    ROUND(SUM(quota) / 500000.0 * 0.41, 4)      AS our_cost_usd
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '03'
  AND model_name LIKE 'claude%'
  -- AND channel_id IN (xx, yy)
GROUP BY model_name
ORDER BY list_price_usd DESC;


-- A5. 按天费用趋势（某用户或全平台）
SELECT
    day,
    COUNT(*)                                    AS call_count,
    SUM(quota)                                  AS total_quota,
    ROUND(SUM(quota) / 500000.0, 4)             AS total_usd
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '03'
  -- AND user_id = 123  -- 可选：过滤特定用户
GROUP BY day
ORDER BY day;


-- ============================================================
-- B. 对账与异常检测
-- ============================================================

-- B1. 找 quota > 0 但 tokens 为 0 的可疑记录（可能是失败但扣费）
SELECT
    request_id,
    from_unixtime(created_at) AS created_time,
    user_id, username, model_name, channel_id,
    prompt_tokens, completion_tokens, quota,
    other
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '03' AND day = '29'
  AND quota > 0
  AND prompt_tokens = 0
  AND completion_tokens = 0
ORDER BY created_at;


-- B2. 找疑似重复计费（同用户、同模型、同 tokens、同 quota，10 秒内多次出现）
WITH numbered AS (
    SELECT
        request_id, created_at, user_id, model_name,
        prompt_tokens, completion_tokens, quota, token_name,
        LAG(created_at) OVER (
            PARTITION BY user_id, model_name, prompt_tokens, completion_tokens, quota
            ORDER BY created_at
        ) AS prev_created_at
    FROM ezmodel_logs.usage_logs
    WHERE year = '2026' AND month = '03'
      AND quota > 0
)
SELECT *
FROM numbered
WHERE created_at - prev_created_at <= 10
ORDER BY user_id, model_name, created_at;


-- B3. Usage 日志 vs Raw 日志交叉对账（某天的记录数对比）
SELECT 'usage' AS source, COUNT(*) AS record_count
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '03' AND day = '29'
UNION ALL
SELECT 'raw' AS source, COUNT(*) AS record_count
FROM ezmodel_logs.raw_logs
WHERE year = '2026' AND month = '03' AND day = '29';


-- B4. 找 Usage 中有但 Raw 中没有的请求（或反之）
SELECT u.request_id, u.user_id, u.model_name, u.quota,
       from_unixtime(u.created_at) AS created_time
FROM ezmodel_logs.usage_logs u
LEFT JOIN ezmodel_logs.raw_logs r
  ON u.request_id = r.request_id
  AND r.year = '2026' AND r.month = '03' AND r.day = '29'
WHERE u.year = '2026' AND u.month = '03' AND u.day = '29'
  AND r.request_id IS NULL
  AND u.quota > 0
ORDER BY u.created_at;


-- ============================================================
-- C. 运营分析
-- ============================================================

-- C1. 按模型的调用量和费用排行（某月）
SELECT
    model_name,
    COUNT(*)                                    AS call_count,
    SUM(prompt_tokens + completion_tokens)       AS total_tokens,
    ROUND(SUM(quota) / 500000.0, 2)             AS total_usd,
    ROUND(AVG(use_time_seconds), 1)             AS avg_latency_sec,
    ROUND(SUM(CASE WHEN is_stream THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS stream_pct
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '03'
GROUP BY model_name
ORDER BY total_usd DESC;


-- C2. 按渠道的调用量和费用（某月）
SELECT
    channel_id,
    COUNT(*)                                    AS call_count,
    COUNT(DISTINCT model_name)                  AS model_count,
    COUNT(DISTINCT user_id)                     AS user_count,
    ROUND(SUM(quota) / 500000.0, 2)             AS total_usd
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '03'
GROUP BY channel_id
ORDER BY total_usd DESC;


-- C3. 按小时的流量分布（某天）
SELECT
    hour,
    COUNT(*)                                    AS call_count,
    SUM(prompt_tokens + completion_tokens)       AS total_tokens,
    ROUND(SUM(quota) / 500000.0, 2)             AS total_usd
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '03' AND day = '29'
GROUP BY hour
ORDER BY hour;


-- C4. 用户 Token 使用分布（找大客户）
SELECT
    user_id,
    username,
    token_name,
    COUNT(*)                                    AS call_count,
    ROUND(SUM(quota) / 500000.0, 2)             AS total_usd,
    MIN(from_unixtime(created_at))              AS first_call,
    MAX(from_unixtime(created_at))              AS last_call
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '03'
GROUP BY user_id, username, token_name
ORDER BY total_usd DESC
LIMIT 50;


-- C5. 平均延迟最高的模型（性能监控）
SELECT
    model_name,
    COUNT(*)                                    AS call_count,
    ROUND(AVG(use_time_seconds), 2)             AS avg_latency,
    ROUND(APPROX_PERCENTILE(use_time_seconds, 0.5), 2)  AS p50_latency,
    ROUND(APPROX_PERCENTILE(use_time_seconds, 0.95), 2) AS p95_latency,
    ROUND(APPROX_PERCENTILE(use_time_seconds, 0.99), 2) AS p99_latency
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '03'
GROUP BY model_name
HAVING COUNT(*) >= 100
ORDER BY p95_latency DESC;


-- ============================================================
-- D. 错误分析（基于 error_logs 表）
-- ============================================================

-- D1. 按状态码和模型的错误分布
SELECT
    status_code,
    model,
    COUNT(*)                                    AS error_count
FROM ezmodel_logs.error_logs
WHERE year = '2026' AND month = '03' AND day = '29'
GROUP BY status_code, model
ORDER BY error_count DESC;


-- D2. 按渠道的错误率（需联合 raw_logs 算总量）
SELECT
    e.channel_id,
    e.channel_name,
    COUNT(*)                                    AS error_count,
    r.total_count,
    ROUND(COUNT(*) * 100.0 / r.total_count, 2)  AS error_rate_pct
FROM ezmodel_logs.error_logs e
JOIN (
    SELECT channel_id, COUNT(*) AS total_count
    FROM ezmodel_logs.raw_logs
    WHERE year = '2026' AND month = '03' AND day = '29'
    GROUP BY channel_id
) r ON e.channel_id = r.channel_id
WHERE e.year = '2026' AND e.month = '03' AND e.day = '29'
GROUP BY e.channel_id, e.channel_name, r.total_count
ORDER BY error_rate_pct DESC;


-- D3. 429 限流错误的时间分布（按小时）
SELECT
    hour,
    model,
    channel_name,
    COUNT(*) AS rate_limit_count
FROM ezmodel_logs.error_logs
WHERE year = '2026' AND month = '03' AND day = '29'
  AND status_code = 429
GROUP BY hour, model, channel_name
ORDER BY hour, rate_limit_count DESC;


-- D4. 查看特定错误请求的详情
SELECT
    request_id,
    created_at,
    model,
    channel_name,
    status_code,
    SUBSTR(response_body, 1, 500) AS response_preview,
    response_error
FROM ezmodel_logs.error_logs
WHERE year = '2026' AND month = '03' AND day = '29'
  AND status_code = 500
ORDER BY created_at DESC
LIMIT 20;


-- ============================================================
-- E. 高级：从 other JSON 提取扩展字段
-- ============================================================

-- E1. 分析 cache_tokens 使用情况
SELECT
    model_name,
    COUNT(*) AS total_calls,
    SUM(CASE WHEN json_extract_scalar(other, '$.cache_tokens') IS NOT NULL
             AND CAST(json_extract_scalar(other, '$.cache_tokens') AS BIGINT) > 0
        THEN 1 ELSE 0 END) AS cache_hit_calls,
    ROUND(SUM(CASE WHEN json_extract_scalar(other, '$.cache_tokens') IS NOT NULL
             AND CAST(json_extract_scalar(other, '$.cache_tokens') AS BIGINT) > 0
        THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS cache_hit_rate_pct,
    SUM(CAST(COALESCE(json_extract_scalar(other, '$.cache_tokens'), '0') AS BIGINT)) AS total_cache_tokens
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '03'
GROUP BY model_name
ORDER BY total_calls DESC;


-- E2. 首 Token 响应时间 (FRT) 分析
SELECT
    model_name,
    COUNT(*) AS call_count,
    ROUND(AVG(CAST(json_extract_scalar(other, '$.frt') AS DOUBLE)), 0) AS avg_frt_ms,
    ROUND(APPROX_PERCENTILE(CAST(json_extract_scalar(other, '$.frt') AS DOUBLE), 0.5), 0) AS p50_frt_ms,
    ROUND(APPROX_PERCENTILE(CAST(json_extract_scalar(other, '$.frt') AS DOUBLE), 0.95), 0) AS p95_frt_ms
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '03'
  AND json_extract_scalar(other, '$.frt') IS NOT NULL
GROUP BY model_name
ORDER BY avg_frt_ms DESC;


-- E3. Web Search 调用统计
SELECT
    model_name,
    COUNT(*) AS web_search_calls,
    ROUND(SUM(quota) / 500000.0, 2) AS total_usd
FROM ezmodel_logs.usage_logs
WHERE year = '2026' AND month = '03'
  AND json_extract_scalar(other, '$.web_search') = 'true'
GROUP BY model_name
ORDER BY web_search_calls DESC;
