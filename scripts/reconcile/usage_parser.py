import orjson


def classify_error_response(body, status_code):
    error_type = ""
    error_msg = ""

    lines = body.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if not next_line or next_line.startswith("event:") or next_line.startswith("data:"):
                    break
                payload += next_line
                j += 1
            i = j
            try:
                d = orjson.loads(payload)
                err = d.get("error", {})
                if isinstance(err, dict):
                    error_type = err.get("type", "")
                    error_msg = err.get("message", "")
                    if error_type:
                        break
            except (orjson.JSONDecodeError, AttributeError):
                continue
        else:
            i += 1

    if not error_type:
        try:
            obj = orjson.loads(body)
            err = obj.get("error", {})
            if isinstance(err, dict):
                error_type = err.get("type", err.get("code", ""))
                error_msg = err.get("message", "")
            elif isinstance(err, str):
                error_type = err
        except (orjson.JSONDecodeError, AttributeError):
            pass

    if error_type:
        short_msg = _shorten_error_msg(error_msg)
        label = f"{error_type}"
        if short_msg:
            label += f": {short_msg}"
        return label

    if status_code and status_code >= 400:
        return f"http_{status_code}"

    return "unknown_error"


def _shorten_error_msg(msg):
    if not msg:
        return ""
    if "tool_use" in msg and "tool_result" in msg:
        return "tool_use缺少tool_result"
    if "credit" in msg.lower() or "balance" in msg.lower() or "quota" in msg.lower():
        return "额度不足"
    if "rate_limit" in msg.lower() or "rate limit" in msg.lower():
        return "速率限制"
    if "context_length" in msg.lower() or "too many tokens" in msg.lower():
        return "上下文超长"
    if "overloaded" in msg.lower():
        return "服务过载"
    if "timeout" in msg.lower():
        return "超时"
    if len(msg) > 60:
        return msg[:57] + "..."
    return msg


def extract_usage(record):
    body = record.get("response_body", "")
    status_code = record.get("status_code", 0)

    if not body:
        if status_code and status_code >= 400:
            return None, f"http_{status_code}_empty_body"
        return None, "empty_response_body"

    try:
        obj = orjson.loads(body)
        usage = obj.get("usage")
        if usage:
            return normalize_usage(usage), None
        if obj.get("error"):
            return None, classify_error_response(body, status_code)
    except orjson.JSONDecodeError:
        pass

    result = extract_usage_from_sse(body)
    if result is not None:
        return result, None

    return None, classify_error_response(body, status_code)


def extract_usage_from_sse(text):
    merged = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            continue
        try:
            data = orjson.loads(payload)
        except orjson.JSONDecodeError:
            continue

        usage = None
        if "usage" in data and data["usage"]:
            usage = data["usage"]
        msg = data.get("message")
        if isinstance(msg, dict) and msg.get("usage"):
            usage = msg["usage"]

        if usage:
            _merge_usage(merged, usage)

        metrics = data.get("amazon-bedrock-invocationMetrics")
        if isinstance(metrics, dict):
            bedrock_usage = {}
            if "inputTokenCount" in metrics:
                bedrock_usage["input_tokens"] = metrics["inputTokenCount"]
            if "outputTokenCount" in metrics:
                bedrock_usage["output_tokens"] = metrics["outputTokenCount"]
            if "cacheReadInputTokenCount" in metrics:
                bedrock_usage["cache_read_input_tokens"] = metrics["cacheReadInputTokenCount"]
            if "cacheWriteInputTokenCount" in metrics:
                bedrock_usage["cache_creation_input_tokens"] = metrics["cacheWriteInputTokenCount"]
            if bedrock_usage:
                _merge_usage(merged, bedrock_usage)

    if merged:
        return normalize_usage(merged)
    return None


def _merge_usage(target, source):
    for k, v in source.items():
        if isinstance(v, dict):
            if k not in target or not isinstance(target[k], dict):
                target[k] = {}
            _merge_usage(target[k], v)
        elif isinstance(v, (int, float)):
            target[k] = max(target.get(k, 0), v)
        else:
            target[k] = v


def normalize_usage(usage):
    cache_creation_total = int(usage.get("cache_creation_input_tokens") or 0)

    cache_creation_obj = usage.get("cache_creation")
    cache_5m = 0
    cache_1h = 0
    if isinstance(cache_creation_obj, dict):
        cache_5m = int(cache_creation_obj.get("ephemeral_5m_input_tokens") or 0)
        cache_1h = int(cache_creation_obj.get("ephemeral_1h_input_tokens") or 0)
        if cache_creation_total == 0 and (cache_5m or cache_1h):
            cache_creation_total = cache_5m + cache_1h

    web_search_requests = 0
    server_tool_use = usage.get("server_tool_use")
    if isinstance(server_tool_use, dict):
        web_search_requests = int(server_tool_use.get("web_search_requests") or 0)

    return {
        "input_tokens": int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
        "cache_read_tokens": int(usage.get("cache_read_input_tokens") or 0),
        "cache_creation_tokens": cache_creation_total,
        "cache_creation_5m_tokens": cache_5m,
        "cache_creation_1h_tokens": cache_1h,
        "web_search_requests": web_search_requests,
    }
