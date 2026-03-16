import re


CLAUDE_200K_THRESHOLD = 200_000
CLAUDE_200K_INPUT_MULT = 2.0
CLAUDE_200K_OUTPUT_MULT = 1.5
CLAUDE_MODEL_RE = re.compile(r"claude", re.IGNORECASE)


def find_price_tier(model_pricing, input_tokens):
    tiers = model_pricing.get("tiered_pricing")
    if not tiers:
        return None

    input_tokens_k = input_tokens // 1000
    matched = None
    for tier in tiers:
        min_k = tier.get("min_tokens_k", 0)
        max_k = tier.get("max_tokens_k", -1)
        if input_tokens_k >= min_k:
            if max_k == -1 or input_tokens_k < max_k:
                matched = tier
                break

    if matched is None and tiers:
        for tier in reversed(tiers):
            if tier.get("max_tokens_k", -1) == -1:
                return tier
        return tiers[-1]

    return matched


def is_claude_model(model_name):
    return bool(CLAUDE_MODEL_RE.search(model_name))


def calc_web_search_cost(model_name, call_count, web_search_cfg):
    if is_claude_model(model_name):
        price_per_k = web_search_cfg.get("claude", 10.0)
    elif (model_name.startswith("o3") or model_name.startswith("o4")
          or model_name.startswith("gpt-5")):
        price_per_k = web_search_cfg.get("openai_normal", 10.0)
    else:
        price_per_k = web_search_cfg.get("openai_high", 25.0)

    return call_count / 1000.0 * price_per_k


def calc_cost(usage, model_pricing, model_name, web_search_cfg):
    per_call = model_pricing.get("per_call_price")
    if per_call is not None:
        return per_call

    input_tokens = usage["input_tokens"]
    output_tokens = usage["output_tokens"]
    cache_read = usage["cache_read_tokens"]
    cache_creation_total = usage["cache_creation_tokens"]
    cache_5m = usage["cache_creation_5m_tokens"]
    cache_1h = usage["cache_creation_1h_tokens"]
    remaining_cache = max(cache_creation_total - cache_5m - cache_1h, 0)
    net_input = max(input_tokens - cache_read - cache_creation_total, 0)

    tier = find_price_tier(model_pricing, input_tokens)
    if tier is not None:
        ip = tier.get("input_price", 0)
        op = tier.get("output_price", 0)
        chp = tier.get("cache_hit_price", 0)
        cwp = tier.get("cache_write_price", 0)
        cwp_1h = tier.get("cache_write_price_1h") or cwp
    elif is_claude_model(model_name) and input_tokens >= CLAUDE_200K_THRESHOLD:
        ip = model_pricing.get("input_price", 0) * CLAUDE_200K_INPUT_MULT
        op = model_pricing.get("output_price", 0) * CLAUDE_200K_OUTPUT_MULT
        chp = model_pricing.get("cache_hit_price", 0)
        cwp = model_pricing.get("cache_write_price", 0)
        cwp_1h = model_pricing.get("cache_write_price_1h") or cwp
    else:
        ip = model_pricing.get("input_price", 0)
        op = model_pricing.get("output_price", 0)
        chp = model_pricing.get("cache_hit_price", 0)
        cwp = model_pricing.get("cache_write_price", 0)
        cwp_1h = model_pricing.get("cache_write_price_1h") or cwp

    cost = (
        net_input / 1_000_000 * ip
        + output_tokens / 1_000_000 * op
        + cache_read / 1_000_000 * chp
        + remaining_cache / 1_000_000 * cwp
        + cache_5m / 1_000_000 * cwp
        + cache_1h / 1_000_000 * cwp_1h
    )

    ws_count = usage.get("web_search_requests", 0)
    if ws_count > 0 and web_search_cfg:
        cost += calc_web_search_cost(model_name, ws_count, web_search_cfg)

    return cost
