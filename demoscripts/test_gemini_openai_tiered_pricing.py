"""
Gemini 分段计费测试脚本（OpenAI 兼容接口）

通过 /v1/chat/completions 接口测试 Gemini 模型的分段计费是否正确，
包括流式/非流式、缓存 token、不同价格区间。

使用方法：
    python test_gemini_openai_tiered_pricing.py --url <API_URL> --key <API_KEY>

    例如：
    python test_gemini_openai_tiered_pricing.py --url https://www.ezmodel.cloud --key sk-xxx
    python test_gemini_openai_tiered_pricing.py --url https://www.ezmodel.cloud --key sk-xxx --full
    python test_gemini_openai_tiered_pricing.py --url https://www.ezmodel.cloud --key sk-xxx --cache
    python test_gemini_openai_tiered_pricing.py --url https://www.ezmodel.cloud --key sk-xxx --stream-only
"""

import requests
import json
import argparse
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    CYAN = '\033[96m'


def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")


def print_success(text: str):
    print(f"{Colors.OKGREEN}[OK] {text}{Colors.ENDC}")


def print_fail(text: str):
    print(f"{Colors.FAIL}[FAIL] {text}{Colors.ENDC}")


def print_info(text: str):
    print(f"{Colors.OKBLUE}[INFO] {text}{Colors.ENDC}")


def print_warning(text: str):
    print(f"{Colors.WARNING}[WARN] {text}{Colors.ENDC}")


def print_section(text: str):
    print(f"\n{Colors.CYAN}{Colors.BOLD}--- {text} ---{Colors.ENDC}\n")


def print_table_header(columns: List[str], widths: List[int]):
    header = "|"
    separator = "|"
    for col, width in zip(columns, widths):
        header += f" {col:<{width}} |"
        separator += "-" * (width + 2) + "|"
    print(separator)
    print(header)
    print(separator)


def print_table_row(values: List[str], widths: List[int], highlight: bool = False):
    row = "|"
    for val, width in zip(values, widths):
        row += f" {val:<{width}} |"
    if highlight:
        print(f"{Colors.OKGREEN}{row}{Colors.ENDC}")
    else:
        print(row)


@dataclass
class TierConfig:
    min_tokens_k: int
    max_tokens_k: int
    input_price: float
    output_price: float
    cache_hit_price: float = 0.0

    def __str__(self):
        max_str = "unlimited" if self.max_tokens_k == -1 else f"{self.max_tokens_k}K"
        return f"{self.min_tokens_k}K-{max_str}"


TIERED_CONFIG = {
    "gemini-3.1-pro": [
        TierConfig(0, 200, 2.0, 12.0, cache_hit_price=0.5),
        TierConfig(200, -1, 4.0, 18.0, cache_hit_price=1.0),
    ]
}


def get_expected_tier(model: str, input_tokens_k: float) -> Optional[TierConfig]:
    if model not in TIERED_CONFIG:
        return None
    tiers = TIERED_CONFIG[model]
    for tier in tiers:
        if input_tokens_k >= tier.min_tokens_k:
            if tier.max_tokens_k == -1 or input_tokens_k < tier.max_tokens_k:
                return tier
    return tiers[-1] if tiers else None


def calculate_expected_cost(
    input_tokens: int,
    output_tokens: int,
    tier: TierConfig,
    cache_tokens: int = 0
) -> float:
    actual_input = max(input_tokens - cache_tokens, 0)
    input_cost = (actual_input / 1_000_000) * tier.input_price
    output_cost = (output_tokens / 1_000_000) * tier.output_price
    cache_cost = (cache_tokens / 1_000_000) * tier.cache_hit_price
    return input_cost + output_cost + cache_cost


def generate_long_text(target_tokens: int) -> str:
    base_text = (
        "Gemini 3.1 Pro 是 Google DeepMind 团队开发的最新一代人工智能助手。"
        "它具有强大的自然语言处理能力，在编程、写作、数据分析、内容创作等方面表现出色。"
        "分段计费（Tiered Pricing）是一种根据使用量动态调整价格的计费模式。"
        "当输入 token 数量小于 200K 时，输入价格为每百万 token $2，输出价格为 $12。"
        "当输入 token 数量超过 200K 时，输入价格调整为每百万 token $4，输出价格为 $18。"
        "这种计费策略有助于平衡资源使用和成本，为不同规模的应用提供灵活的定价选项。"
    )
    tokens_per_repeat = 150
    repeats = (target_tokens // tokens_per_repeat) + 1
    return (base_text * repeats)[:target_tokens * 2]


# ---------------------------------------------------------------------------
# OpenAI 兼容接口请求
# ---------------------------------------------------------------------------

def openai_chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: list,
    stream: bool = False,
    max_tokens: int = 500,
    temperature: float = 0.7,
    timeout: int = 120,
) -> Optional[Dict[str, Any]]:
    """
    通过 /v1/chat/completions 发送请求。
    流式模式下自动聚合所有 chunk，返回与非流式相同的结构。
    """
    url = f"{base_url}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }
    if stream:
        payload["stream_options"] = {"include_usage": True}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout, stream=stream)
        if resp.status_code != 200:
            print_fail(f"HTTP {resp.status_code}")
            print(f"Response: {resp.text[:500]}")
            return None

        if not stream:
            return resp.json()

        # --- 流式聚合 ---
        collected_text = ""
        usage = None
        chunk_count = 0

        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data_str = line[len("data: "):]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                chunk_count += 1
            except json.JSONDecodeError:
                continue

            for choice in chunk.get("choices", []):
                delta = choice.get("delta", {})
                if "content" in delta and delta["content"]:
                    collected_text += delta["content"]

            if chunk.get("usage"):
                usage = chunk["usage"]

        print_info(f"流式响应共收到 {chunk_count} 个 chunk")

        return {
            "choices": [{"message": {"content": collected_text}}],
            "usage": usage or {},
        }

    except requests.exceptions.Timeout:
        print_fail(f"Request timeout after {timeout}s")
        return None
    except Exception as e:
        print_fail(f"Request error: {e}")
        return None


# ---------------------------------------------------------------------------
# 解析 usage（OpenAI 格式）
# ---------------------------------------------------------------------------

def parse_usage(response: Dict[str, Any]) -> Dict[str, Any]:
    """从 OpenAI 格式响应中提取 usage 信息"""
    usage = response.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)

    # prompt_tokens_details 中的 cached_tokens
    details = usage.get("prompt_tokens_details") or {}
    cached_tokens = details.get("cached_tokens", 0)

    # completion_tokens_details 中的 reasoning_tokens（thinking tokens）
    comp_details = usage.get("completion_tokens_details") or {}
    reasoning_tokens = comp_details.get("reasoning_tokens", 0)

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
        "reasoning_tokens": reasoning_tokens,
    }


def print_usage(u: Dict[str, Any]):
    print_info(f"输入 tokens: {u['prompt_tokens']}")
    print_info(f"输出 tokens: {u['completion_tokens']}")
    print_info(f"缓存 tokens: {u['cached_tokens']}")
    if u['reasoning_tokens'] > 0:
        print_info(f"思考 tokens: {u['reasoning_tokens']}")
    print_info(f"总计 tokens: {u['total_tokens']}")


def print_cost(u: Dict[str, Any], model: str):
    input_tokens_k = u["prompt_tokens"] / 1000
    tier = get_expected_tier(model, input_tokens_k)
    if not tier:
        return
    print_success(f"预期价格区间: {tier}")
    print_info(f"输入价格: ${tier.input_price}/M  输出价格: ${tier.output_price}/M  缓存价格: ${tier.cache_hit_price}/M")
    cost = calculate_expected_cost(
        u["prompt_tokens"], u["completion_tokens"], tier,
        cache_tokens=u["cached_tokens"],
    )
    print_info(f"预期费用: ${cost:.6f} USD")


def get_response_text(response: Dict[str, Any]) -> str:
    choices = response.get("choices", [])
    if choices:
        return choices[0].get("message", {}).get("content", "")
    return ""


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

def test_non_stream(base_url: str, api_key: str, model: str) -> bool:
    """非流式短上下文"""
    print_section("测试 1: 非流式请求（短上下文）")

    input_text = generate_long_text(5000)
    messages = [{"role": "user", "content": f"请用三句话总结以下内容：\n\n{input_text}"}]

    print_info(f"模型: {model}  stream=false  预计输入 ~5K tokens")
    resp = openai_chat_completion(base_url, api_key, model, messages, stream=False)
    if not resp:
        print_fail("请求失败")
        return False

    u = parse_usage(resp)
    print_success("请求成功")
    print_usage(u)

    if u["prompt_tokens"] == 0 and u["completion_tokens"] == 0:
        print_fail("usage 全为 0，计费异常！")
        return False

    print_cost(u, model)
    text = get_response_text(resp)
    if text:
        print(f"\n{Colors.CYAN}响应内容（前200字符）:{Colors.ENDC}")
        print(f"{text[:200]}...")
    return True


def test_stream(base_url: str, api_key: str, model: str) -> bool:
    """流式短上下文"""
    print_section("测试 2: 流式请求（短上下文）")

    input_text = generate_long_text(5000)
    messages = [{"role": "user", "content": f"请用三句话总结以下内容：\n\n{input_text}"}]

    print_info(f"模型: {model}  stream=true  预计输入 ~5K tokens")
    resp = openai_chat_completion(base_url, api_key, model, messages, stream=True)
    if not resp:
        print_fail("请求失败")
        return False

    u = parse_usage(resp)
    print_success("请求成功")
    print_usage(u)

    if u["prompt_tokens"] == 0 and u["completion_tokens"] == 0:
        print_fail("usage 全为 0，计费异常！")
        return False

    print_cost(u, model)
    text = get_response_text(resp)
    if text:
        print(f"\n{Colors.CYAN}响应内容（前200字符）:{Colors.ENDC}")
        print(f"{text[:200]}...")
    return True


def test_stream_vs_non_stream(base_url: str, api_key: str, model: str) -> bool:
    """对比流式与非流式的 usage 是否一致"""
    print_section("测试 3: 流式 vs 非流式 usage 对比")

    input_text = generate_long_text(3000)
    messages = [{"role": "user", "content": f"请用一句话总结：\n\n{input_text}"}]

    print_info("发送非流式请求...")
    resp_sync = openai_chat_completion(base_url, api_key, model, messages, stream=False, max_tokens=200)
    print_info("发送流式请求...")
    resp_stream = openai_chat_completion(base_url, api_key, model, messages, stream=True, max_tokens=200)

    if not resp_sync or not resp_stream:
        print_fail("请求失败")
        return False

    u_sync = parse_usage(resp_sync)
    u_stream = parse_usage(resp_stream)

    print_info(f"非流式 — prompt: {u_sync['prompt_tokens']}, completion: {u_sync['completion_tokens']}, cache: {u_sync['cached_tokens']}")
    print_info(f"流  式 — prompt: {u_stream['prompt_tokens']}, completion: {u_stream['completion_tokens']}, cache: {u_stream['cached_tokens']}")

    passed = True

    # prompt_tokens 应该相同（同样的输入）
    if u_sync["prompt_tokens"] != u_stream["prompt_tokens"]:
        diff = abs(u_sync["prompt_tokens"] - u_stream["prompt_tokens"])
        if diff > 5:
            print_warning(f"prompt_tokens 差异较大: {diff}")
        else:
            print_info(f"prompt_tokens 差异可接受: {diff}")

    # 关键检查：流式的 usage 不能全为 0
    if u_stream["prompt_tokens"] == 0 and u_stream["completion_tokens"] == 0:
        print_fail("流式 usage 全为 0！计费异常！")
        passed = False
    else:
        print_success("流式 usage 正常返回")

    if u_sync["prompt_tokens"] == 0 and u_sync["completion_tokens"] == 0:
        print_fail("非流式 usage 全为 0！计费异常！")
        passed = False
    else:
        print_success("非流式 usage 正常返回")

    return passed


def test_cache_tokens(base_url: str, api_key: str, model: str) -> bool:
    """缓存 token 测试：两轮对话触发隐式缓存"""
    print_section("测试 4: 缓存 token 计费（Cache Tokens）")

    input_text = generate_long_text(40000)
    base_messages = [
        {"role": "user", "content": f"请仔细阅读以下内容：\n\n{input_text}"},
        {"role": "assistant", "content": "好的，我已经仔细阅读了以上全部内容。请问您有什么问题？"},
    ]

    # --- 第一轮 ---
    print_info("第一轮请求：建立缓存...")
    msgs1 = base_messages + [{"role": "user", "content": "请用一句话总结上面的内容。"}]
    resp1 = openai_chat_completion(base_url, api_key, model, msgs1, stream=True, max_tokens=200)
    if not resp1:
        print_fail("第一轮请求失败")
        return False
    u1 = parse_usage(resp1)
    print_success("第一轮请求成功")
    print_info(f"  prompt: {u1['prompt_tokens']}, cache: {u1['cached_tokens']}, completion: {u1['completion_tokens']}")

    # --- 等待 ---
    print_info("等待 3 秒让缓存生效...")
    time.sleep(3)

    # --- 第二轮 ---
    print_info("第二轮请求：验证缓存命中...")
    msgs2 = base_messages + [{"role": "user", "content": "请列出上面内容中提到的关键数字。"}]
    resp2 = openai_chat_completion(base_url, api_key, model, msgs2, stream=True, max_tokens=200)
    if not resp2:
        print_fail("第二轮请求失败")
        return False
    u2 = parse_usage(resp2)
    print_success("第二轮请求成功")
    print_info(f"  prompt: {u2['prompt_tokens']}, cache: {u2['cached_tokens']}, completion: {u2['completion_tokens']}")

    passed = True
    if u2["cached_tokens"] > 0:
        print_success(f"缓存命中！cached_tokens = {u2['cached_tokens']}")
        actual_input = u2["prompt_tokens"] - u2["cached_tokens"]
        print_info(f"  实际计费输入: {actual_input} (prompt {u2['prompt_tokens']} - cache {u2['cached_tokens']})")

        tier = get_expected_tier(model, u2["prompt_tokens"] / 1000)
        if tier:
            cost_with_cache = calculate_expected_cost(
                u2["prompt_tokens"], u2["completion_tokens"], tier,
                cache_tokens=u2["cached_tokens"],
            )
            cost_no_cache = calculate_expected_cost(
                u2["prompt_tokens"], u2["completion_tokens"], tier,
                cache_tokens=0,
            )
            savings = cost_no_cache - cost_with_cache
            print_info(f"  含缓存费用: ${cost_with_cache:.6f} USD")
            print_info(f"  无缓存费用: ${cost_no_cache:.6f} USD")
            if cost_no_cache > 0:
                print_info(f"  缓存节省: ${savings:.6f} USD ({savings/cost_no_cache*100:.1f}%)")
    else:
        print_warning("第二轮请求未命中缓存（cached_tokens = 0）")
        print_warning("可能原因：隐式缓存需要更大上下文、或模型/服务端未启用缓存")
        passed = False

    text = get_response_text(resp2)
    if text:
        print(f"\n{Colors.CYAN}第二轮响应（前200字符）:{Colors.ENDC}")
        print(f"{text[:200]}...")

    return passed


def test_long_context_stream(base_url: str, api_key: str, model: str) -> bool:
    """流式长上下文（第二价格区间 > 200K）"""
    print_section("测试 5: 流式长上下文（> 200K tokens）")
    print_warning("此测试将发送大量数据，可能需要较长时间...")

    input_text = generate_long_text(250000)
    messages = [{"role": "user", "content": f"请分析以下内容并提取关键信息：\n\n{input_text}"}]

    print_info(f"模型: {model}  stream=true  预计输入 ~250K tokens")
    resp = openai_chat_completion(base_url, api_key, model, messages, stream=True, max_tokens=1000, timeout=300)
    if not resp:
        print_fail("请求失败")
        return False

    u = parse_usage(resp)
    print_success("请求成功")
    print_usage(u)

    if u["prompt_tokens"] == 0 and u["completion_tokens"] == 0:
        print_fail("usage 全为 0，计费异常！")
        return False

    print_cost(u, model)
    text = get_response_text(resp)
    if text:
        print(f"\n{Colors.CYAN}响应内容（前200字符）:{Colors.ENDC}")
        print(f"{text[:200]}...")
    return True


# ---------------------------------------------------------------------------
# 定价概要
# ---------------------------------------------------------------------------

def print_pricing_summary(model: str):
    print_header(f"{model} 分段计费概要")
    if model not in TIERED_CONFIG:
        print_warning(f"未找到模型 {model} 的本地定价配置（不影响测试）")
        return
    tiers = TIERED_CONFIG[model]
    columns = ["区间 (K tokens)", "输入 ($/M)", "输出 ($/M)", "缓存 ($/M)"]
    widths = [20, 14, 14, 14]
    print_table_header(columns, widths)
    for tier in tiers:
        max_str = "∞" if tier.max_tokens_k == -1 else f"{tier.max_tokens_k}K"
        range_str = f"{tier.min_tokens_k}K - {max_str}"
        print_table_row(
            [range_str, f"${tier.input_price}", f"${tier.output_price}", f"${tier.cache_hit_price}"],
            widths,
        )
    print("|" + "-" * (sum(widths) + len(widths) * 3 + 2) + "|")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Gemini 分段计费测试（OpenAI 兼容接口）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --url https://www.ezmodel.cloud --key sk-xxx
  %(prog)s --url https://www.ezmodel.cloud --key sk-xxx --full
  %(prog)s --url https://www.ezmodel.cloud --key sk-xxx --cache
  %(prog)s --url https://www.ezmodel.cloud --key sk-xxx --stream-only
        """,
    )
    parser.add_argument('--url', required=True, help='API 基础 URL')
    parser.add_argument('--key', required=True, help='API 密钥')
    parser.add_argument('--model', default='gemini-3.1-pro-preview', help='模型名称')
    parser.add_argument('--full', action='store_true', help='运行完整测试（含长上下文）')
    parser.add_argument('--cache', action='store_true', help='仅测试缓存 token')
    parser.add_argument('--stream-only', action='store_true', help='仅测试流式请求')

    args = parser.parse_args()

    print_header("Gemini 分段计费测试（OpenAI 兼容接口）")
    print_info(f"API URL: {args.url}")
    print_info(f"模型: {args.model}")
    print_info(f"接口: /v1/chat/completions")

    print_pricing_summary(args.model)

    results = []

    if args.cache:
        results.append(("缓存 token 测试", test_cache_tokens(args.url, args.key, args.model)))
    elif args.stream_only:
        results.append(("流式请求", test_stream(args.url, args.key, args.model)))
    else:
        results.append(("非流式请求", test_non_stream(args.url, args.key, args.model)))
        results.append(("流式请求", test_stream(args.url, args.key, args.model)))
        results.append(("流式 vs 非流式对比", test_stream_vs_non_stream(args.url, args.key, args.model)))
        results.append(("缓存 token 测试", test_cache_tokens(args.url, args.key, args.model)))
        if args.full:
            results.append(("流式长上下文", test_long_context_stream(args.url, args.key, args.model)))

    # --- 结果摘要 ---
    print_header("测试结果摘要")
    columns = ["测试项", "状态"]
    widths = [25, 10]
    print_table_header(columns, widths)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print_table_row([name, status], widths, highlight=passed)
        if not passed:
            all_passed = False
    print("|" + "-" * (sum(widths) + len(widths) * 3 + 2) + "|")

    if all_passed:
        print_success("\n所有测试通过！")
    else:
        print_fail("\n部分测试失败，请检查日志。")

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
