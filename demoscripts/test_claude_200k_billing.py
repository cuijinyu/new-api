"""
Claude 超长输入(>200K tokens)计费与缓存测试脚本

目标:
1. 使用超过 200K token 的输入进行请求
2. 开启 prompt caching 并观察缓存写入与缓存命中字段
3. 带上 context-1m-2025-08-07 flag 进行测试

示例:
python demoscripts/test_claude_200k_billing.py \
  --url https://www.ezmodel.cloud \
  --key sk-xxx \
  --model claude-sonnet-4-20250514
"""

import argparse
import time
from typing import Any, Dict

import anthropic
import httpx


CONTEXT_1M_FLAG = "context-1m-2025-08-07"


class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    CYAN = "\033[96m"


def print_header(text: str) -> None:
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 72}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 72}{Colors.ENDC}\n")


def print_info(text: str) -> None:
    print(f"{Colors.OKBLUE}ℹ️  {text}{Colors.ENDC}")


def print_success(text: str) -> None:
    print(f"{Colors.OKGREEN}✅ {text}{Colors.ENDC}")


def print_warning(text: str) -> None:
    print(f"{Colors.WARNING}⚠️  {text}{Colors.ENDC}")


def print_fail(text: str) -> None:
    print(f"{Colors.FAIL}❌ {text}{Colors.ENDC}")


def create_client(base_url: str, api_key: str, context_flag: str) -> anthropic.Anthropic:
    """创建带 context-1m flag 的 Anthropic 客户端。"""
    custom_http_client = httpx.Client(
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "anthropic-beta": context_flag,
        },
        timeout=600.0,
    )
    return anthropic.Anthropic(
        api_key=api_key,
        base_url=base_url,
        http_client=custom_http_client,
    )


def generate_long_text(target_tokens: int) -> str:
    """
    生成长文本。
    经验上英文词约 1 token，这里用重复词确保可控地超过目标。
    """
    anchor = (
        "This is a deterministic context block for large-input billing and caching test. "
        "It is intentionally repetitive so that token size can be scaled predictably. "
        "Please treat this as immutable background context. "
    )
    # 先构造基础块，再按 token 目标进行放大
    base = (anchor + "\n") * 200
    words = base.split()
    if len(words) >= target_tokens:
        return " ".join(words[:target_tokens])

    repeat_times = (target_tokens // len(words)) + 1
    large_words = words * repeat_times
    return " ".join(large_words[:target_tokens])


def to_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def extract_usage(message: Any) -> Dict[str, int]:
    usage_obj = getattr(message, "usage", None)
    if usage_obj is None:
        return {}
    # SDK 的 usage 通常是对象，使用 getattr 提取
    return {
        "input_tokens": to_int(getattr(usage_obj, "input_tokens", 0)),
        "output_tokens": to_int(getattr(usage_obj, "output_tokens", 0)),
        "cache_creation_input_tokens": to_int(
            getattr(usage_obj, "cache_creation_input_tokens", 0)
        ),
        "cache_read_input_tokens": to_int(
            getattr(usage_obj, "cache_read_input_tokens", 0)
        ),
    }


def calc_cost(
    usage: Dict[str, int],
    input_per_m: float,
    output_per_m: float,
    cache_write_per_m: float,
    cache_read_per_m: float,
) -> float:
    return (
        usage.get("input_tokens", 0) / 1_000_000 * input_per_m
        + usage.get("output_tokens", 0) / 1_000_000 * output_per_m
        + usage.get("cache_creation_input_tokens", 0) / 1_000_000 * cache_write_per_m
        + usage.get("cache_read_input_tokens", 0) / 1_000_000 * cache_read_per_m
    )


def print_usage_and_cost(
    title: str,
    usage: Dict[str, int],
    input_per_m: float,
    output_per_m: float,
    cache_write_per_m: float,
    cache_read_per_m: float,
) -> float:
    print(f"{Colors.CYAN}{Colors.BOLD}{title}{Colors.ENDC}")
    print(f"  input_tokens:                {usage.get('input_tokens', 0)}")
    print(f"  output_tokens:               {usage.get('output_tokens', 0)}")
    print(
        f"  cache_creation_input_tokens: {usage.get('cache_creation_input_tokens', 0)}"
    )
    print(f"  cache_read_input_tokens:     {usage.get('cache_read_input_tokens', 0)}")
    cost = calc_cost(
        usage, input_per_m, output_per_m, cache_write_per_m, cache_read_per_m
    )
    print(f"  estimated_cost_usd:          ${cost:.6f}\n")
    return cost


def request_with_cache(
    client: anthropic.Anthropic,
    model: str,
    long_text: str,
    question: str,
    max_tokens: int,
) -> Any:
    return client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[
            {
                "type": "text",
                "text": long_text,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": question}],
    )


def run_test(
    base_url: str,
    api_key: str,
    model: str,
    context_flag: str,
    target_input_tokens: int,
    max_tokens: int,
    input_per_m: float,
    output_per_m: float,
    cache_write_per_m: float,
    cache_read_per_m: float,
) -> bool:
    print_header("Claude >200K 输入计费与缓存测试")
    print_info(f"URL: {base_url}")
    print_info(f"Model: {model}")
    print_info(f"Context Flag: {context_flag}")
    print_info(f"目标输入 token: > {target_input_tokens}")

    long_text = generate_long_text(target_input_tokens)
    print_info(f"生成长文本字符数: {len(long_text):,}")

    client = create_client(base_url, api_key, context_flag)
    ok = True

    try:
        print_header("请求 1: 建立缓存（首次请求）")
        t1 = time.time()
        r1 = request_with_cache(
            client=client,
            model=model,
            long_text=long_text,
            question="请用一句话确认你已经读取到全部上下文。",
            max_tokens=max_tokens,
        )
        d1 = time.time() - t1
        u1 = extract_usage(r1)
        c1 = print_usage_and_cost(
            "Usage #1",
            u1,
            input_per_m,
            output_per_m,
            cache_write_per_m,
            cache_read_per_m,
        )
        print_info(f"请求 1 延迟: {d1:.2f}s")

        print_info("等待 3 秒让缓存稳定...")
        time.sleep(3)

        print_header("请求 2: 完全相同请求（验证缓存命中）")
        t2 = time.time()
        r2 = request_with_cache(
            client=client,
            model=model,
            long_text=long_text,
            question="请用一句话确认你已经读取到全部上下文。",
            max_tokens=max_tokens,
        )
        d2 = time.time() - t2
        u2 = extract_usage(r2)
        c2 = print_usage_and_cost(
            "Usage #2",
            u2,
            input_per_m,
            output_per_m,
            cache_write_per_m,
            cache_read_per_m,
        )
        print_info(f"请求 2 延迟: {d2:.2f}s")

        print_info("等待 3 秒...")
        time.sleep(3)

        print_header("请求 3: 相同前缀 + 新问题（验证部分命中）")
        t3 = time.time()
        r3 = request_with_cache(
            client=client,
            model=model,
            long_text=long_text,
            question="在不复述全文的前提下，总结上下文的主要结构。",
            max_tokens=max_tokens,
        )
        d3 = time.time() - t3
        u3 = extract_usage(r3)
        c3 = print_usage_and_cost(
            "Usage #3",
            u3,
            input_per_m,
            output_per_m,
            cache_write_per_m,
            cache_read_per_m,
        )
        print_info(f"请求 3 延迟: {d3:.2f}s")

        print_header("结果分析")
        if u1.get("input_tokens", 0) <= 200_000:
            print_warning(
                "请求 1 的 input_tokens 未超过 200K，可提高 --target-input-tokens 再测。"
            )
            ok = False
        else:
            print_success(f"请求 1 input_tokens = {u1.get('input_tokens', 0)} (> 200K)")

        if u2.get("cache_read_input_tokens", 0) > 0:
            print_success(
                f"请求 2 检测到缓存命中: cache_read_input_tokens={u2.get('cache_read_input_tokens', 0)}"
            )
        else:
            print_warning("请求 2 未检测到 cache_read_input_tokens > 0")
            ok = False

        print_info(f"估算费用对比: #1=${c1:.6f}, #2=${c2:.6f}, #3=${c3:.6f}")
        if c2 < c1:
            print_success("请求 2 估算费用低于请求 1，符合缓存命中降本预期。")
        else:
            print_warning("请求 2 估算费用未低于请求 1，请核对费率参数或网关计费策略。")

        return ok
    except anthropic.APIStatusError as e:
        print_fail(f"APIStatusError: status={e.status_code}, message={e.message}")
        if hasattr(e, "body"):
            print_fail(f"body: {e.body}")
        return False
    except Exception as e:
        print_fail(f"请求失败: {type(e).__name__}: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Claude >200K 输入计费与缓存测试")
    parser.add_argument(
        "--url",
        type=str,
        default="https://www.ezmodel.cloud",
        help="API Base URL",
    )
    parser.add_argument(
        "--key",
        type=str,
        required=True,
        help="API Key",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-20250514",
        help="模型名称",
    )
    parser.add_argument(
        "--context-flag",
        type=str,
        default=CONTEXT_1M_FLAG,
        help="Anthropic beta flag（默认: context-1m-2025-08-07）",
    )
    parser.add_argument(
        "--target-input-tokens",
        type=int,
        default=210000,
        help="目标输入 token 数（默认 210000，用于确保超过 200K）",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=64,
        help="输出 token 上限",
    )
    parser.add_argument(
        "--input-per-m",
        type=float,
        default=3.0,
        help="普通输入每百万 token 价格（USD）",
    )
    parser.add_argument(
        "--output-per-m",
        type=float,
        default=15.0,
        help="输出每百万 token 价格（USD）",
    )
    parser.add_argument(
        "--cache-write-per-m",
        type=float,
        default=3.75,
        help="缓存写入每百万 token 价格（USD）",
    )
    parser.add_argument(
        "--cache-read-per-m",
        type=float,
        default=0.3,
        help="缓存读取每百万 token 价格（USD）",
    )
    args = parser.parse_args()

    passed = run_test(
        base_url=args.url,
        api_key=args.key,
        model=args.model,
        context_flag=args.context_flag,
        target_input_tokens=args.target_input_tokens,
        max_tokens=args.max_tokens,
        input_per_m=args.input_per_m,
        output_per_m=args.output_per_m,
        cache_write_per_m=args.cache_write_per_m,
        cache_read_per_m=args.cache_read_per_m,
    )
    if passed:
        print_success("测试通过。")
    else:
        print_warning("测试未完全通过，请根据日志调整参数重试。")


if __name__ == "__main__":
    main()
