"""
Gemini 3.1 Pro 分段计费（Tiered Pricing）测试脚本

验证目标：
- 验证 gemini-3.1-pro 模型的分段计费配置是否正确加载
- 验证不同 token 区间是否应用正确的价格
- 验证缓存 token（cachedContentTokenCount）是否正确返回并按 cache_hit_price 计价
- 通过日志验证实际计费是否正确

分段计费配置（参考官方定价）：
{
  "gemini-3.1-pro": {
    "enabled": true,
    "tiers": [
      {
        "min_tokens": 0,
        "max_tokens": 200,
        "input_price": 2.0,
        "output_price": 12.0
      },
      {
        "min_tokens": 200,
        "max_tokens": -1,
        "input_price": 4.0,
        "output_price": 18.0
      }
    ]
  }
}

区间说明（单位：千 tokens）：
- 0-200K tokens: 输入 $2/M, 输出 $12/M
- 200K+ tokens: 输入 $4/M, 输出 $18/M

使用方法：
    python test_gemini_31_pro_tiered_pricing.py --url <API_URL> --key <API_KEY>

    例如：
    python test_gemini_31_pro_tiered_pricing.py --url http://localhost:3000 --key sk-xxx

    完整测试（包括长上下文）：
    python test_gemini_31_pro_tiered_pricing.py --url http://localhost:3000 --key sk-xxx --full

    仅测试缓存 token 计费：
    python test_gemini_31_pro_tiered_pricing.py --url http://localhost:3000 --key sk-xxx --cache

注意事项：
1. 确保在系统设置中已配置 gemini-3.1-pro 的分段计费
2. 测试会发送真实请求，会产生费用
3. 使用 --full 参数会测试长上下文（200K+ tokens），耗时较长
"""

import requests
import json
import argparse
import time
import subprocess
import re
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass


# 配置颜色输出
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
    """打印表格头"""
    header = "|"
    separator = "|"
    for col, width in zip(columns, widths):
        header += f" {col:<{width}} |"
        separator += "-" * (width + 2) + "|"
    print(separator)
    print(header)
    print(separator)


def print_table_row(values: List[str], widths: List[int], highlight: bool = False):
    """打印表格行"""
    row = "|"
    for val, width in zip(values, widths):
        row += f" {val:<{width}} |"
    if highlight:
        print(f"{Colors.OKGREEN}{row}{Colors.ENDC}")
    else:
        print(row)


@dataclass
class TierConfig:
    """价格区间配置"""
    min_tokens_k: int  # 最小 token 数（千）
    max_tokens_k: int  # 最大 token 数（千），-1 表示无上限
    input_price: float  # 输入价格 USD/M tokens
    output_price: float  # 输出价格 USD/M tokens
    cache_hit_price: float = 0.0  # 缓存命中价格 USD/M tokens

    def __str__(self):
        max_str = "unlimited" if self.max_tokens_k == -1 else f"{self.max_tokens_k}K"
        return f"{self.min_tokens_k}K-{max_str}"


# Gemini 3.1 Pro 的分段计费配置（参考官方定价）
TIERED_CONFIG = {
    "gemini-3.1-pro": [
        TierConfig(0, 200, 2.0, 12.0, cache_hit_price=0.5),
        TierConfig(200, -1, 4.0, 18.0, cache_hit_price=1.0),
    ]
}


def get_expected_tier(model: str, input_tokens_k: float) -> Optional[TierConfig]:
    """根据输入 token 数获取预期的价格区间"""
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
    """计算预期费用（USD）

    input_tokens 应为实际输入 tokens（已减去 cache_tokens）。
    cache_tokens 按 cache_hit_price 单独计价。
    """
    actual_input = max(input_tokens - cache_tokens, 0)
    input_cost = (actual_input / 1_000_000) * tier.input_price
    output_cost = (output_tokens / 1_000_000) * tier.output_price
    cache_cost = (cache_tokens / 1_000_000) * tier.cache_hit_price

    return input_cost + output_cost + cache_cost


def gemini_chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    contents: list,
    generation_config: dict = None,
    timeout: int = 120
) -> Optional[Dict[str, Any]]:
    """
    发送 Gemini chat completion 流式请求，聚合结果后返回与非流式相同的结构。

    返回格式与非流式一致：
    {
        "candidates": [{"content": {"parts": [{"text": "..."}]}}],
        "usageMetadata": { ... }
    }
    """
    url = f"{base_url}/v1beta/models/{model}:streamGenerateContent?alt=sse"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "contents": contents
    }

    if generation_config:
        payload["generationConfig"] = generation_config

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout, stream=True)

        if response.status_code != 200:
            print_fail(f"Request failed: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return None

        collected_text = ""
        usage_metadata = {}
        chunk_count = 0

        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            if not line.startswith("data: "):
                continue
            data_str = line[len("data: "):]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                chunk_count += 1
            except json.JSONDecodeError:
                continue

            # 拼接文本
            for candidate in chunk.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "text" in part:
                        collected_text += part["text"]

            # usageMetadata 通常在最后一个 chunk 中包含完整信息
            if "usageMetadata" in chunk:
                usage_metadata = chunk["usageMetadata"]

        print_info(f"流式响应共收到 {chunk_count} 个 chunk")

        return {
            "candidates": [{"content": {"parts": [{"text": collected_text}]}}],
            "usageMetadata": usage_metadata,
        }

    except requests.exceptions.Timeout:
        print_fail(f"Request timeout after {timeout}s")
        return None
    except Exception as e:
        print_fail(f"Request error: {e}")
        return None


def generate_long_text(target_tokens: int) -> str:
    """生成指定长度的文本"""
    # 估算：每个中文字符约 1.5 tokens，每个英文单词约 1 token
    # 使用重复的文本来达到目标 token 数
    base_text = """
    Gemini 3.1 Pro 是 Google DeepMind 团队开发的最新一代人工智能助手。
    它具有强大的自然语言处理能力，在编程、写作、数据分析、内容创作等方面表现出色。
    分段计费（Tiered Pricing）是一种根据使用量动态调整价格的计费模式。
    当输入 token 数量小于 200K 时，输入价格为每百万 token $2，输出价格为 $12。
    当输入 token 数量超过 200K 时，输入价格调整为每百万 token $4，输出价格为 $18。
    这种计费策略有助于平衡资源使用和成本，为不同规模的应用提供灵活的定价选项。
    """
    # 估算 base_text 的 token 数约 150
    tokens_per_repeat = 150
    repeats = (target_tokens // tokens_per_repeat) + 1
    return (base_text * repeats)[:target_tokens * 2]  # 过长一点没关系


def get_docker_logs(container_name: str = "new-api-local", lines: int = 50) -> str:
    """获取 Docker 容器日志"""
    try:
        result = subprocess.run(
            ["docker", "logs", container_name, "--tail", str(lines)],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout
    except Exception as e:
        print_warning(f"Failed to get docker logs: {e}")
        return ""


def parse_log_for_usage(logs: str) -> List[Dict[str, Any]]:
    """从日志中解析使用量信息"""
    usage_records = []

    # 匹配模式：tiered pricing, input_tokens, output_tokens, price info
    patterns = [
        r'tiered.*?input:\s*(\d+).*?output:\s*(\d+).*?input_price:\s*([\d.]+).*?output_price:\s*([\d.]+)',
        r'TieredPricingData.*?PromptTokenCount[:\s]+(\d+).*?CandidatesTokenCount[:\s]+(\d+)',
        r'useTieredPricing.*?promptTokenCount["\s:]+(\d+).*?candidatesTokenCount["\s:]+(\d+)',
    ]

    for line in logs.split('\n'):
        for pattern in patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                try:
                    input_tokens = int(match.group(1))
                    output_tokens = int(match.group(2))
                    record = {
                        'input_tokens': input_tokens,
                        'output_tokens': output_tokens,
                        'total_tokens': input_tokens + output_tokens,
                    }
                    if len(match.groups()) >= 4:
                        record['input_price'] = float(match.group(3))
                        record['output_price'] = float(match.group(4))
                    usage_records.append(record)
                    break
                except (ValueError, IndexError):
                    continue

    return usage_records


def test_short_context(base_url: str, api_key: str, model: str) -> bool:
    """测试短上下文（< 200K tokens，第一区间）"""
    print_section("测试短上下文（第一区间 < 200K tokens）")

    # 生成约 10K tokens 的输入
    input_text = generate_long_text(10000)
    contents = [
        {
            "role": "user",
            "parts": [{"text": f"请总结以下内容：\n\n{input_text}"}]
        }
    ]

    generation_config = {
        "maxOutputTokens": 500,
        "temperature": 0.7
    }

    print_info(f"发送请求到 {model}...")
    print_info(f"预计输入 tokens: ~10K")

    response = gemini_chat_completion(
        base_url, api_key, model, contents, generation_config
    )

    if not response:
        print_fail("请求失败")
        return False

    # 解析响应
    try:
        usage_metadata = response.get('usageMetadata', {})
        prompt_tokens = usage_metadata.get('promptTokenCount', 0)
        candidates_tokens = usage_metadata.get('candidatesTokenCount', 0)
        total_tokens = usage_metadata.get('totalTokenCount', 0)
        cached_tokens = usage_metadata.get('cachedContentTokenCount', 0)

        print_success(f"请求成功！")
        print_info(f"输入 tokens: {prompt_tokens}")
        print_info(f"输出 tokens: {candidates_tokens}")
        print_info(f"缓存 tokens: {cached_tokens}")
        print_info(f"总计 tokens: {total_tokens}")

        # 验证使用的价格区间
        input_tokens_k = prompt_tokens / 1000
        expected_tier = get_expected_tier(model, input_tokens_k)

        if expected_tier:
            print_success(f"预期价格区间: {expected_tier}")
            print_info(f"输入价格: ${expected_tier.input_price}/M tokens")
            print_info(f"输出价格: ${expected_tier.output_price}/M tokens")
            print_info(f"缓存命中价格: ${expected_tier.cache_hit_price}/M tokens")

            expected_cost = calculate_expected_cost(
                prompt_tokens, candidates_tokens, expected_tier,
                cache_tokens=cached_tokens
            )
            print_info(f"预期费用: ${expected_cost:.6f} USD")

        # 打印响应内容片段
        if 'candidates' in response and len(response['candidates']) > 0:
            content = response['candidates'][0].get('content', {})
            if 'parts' in content and len(content['parts']) > 0:
                text = content['parts'][0].get('text', '')
                print(f"\n{Colors.CYAN}响应内容（前200字符）:{Colors.ENDC}")
                print(f"{text[:200]}...")

        return True

    except Exception as e:
        print_fail(f"解析响应失败: {e}")
        return False


def test_long_context(base_url: str, api_key: str, model: str) -> bool:
    """测试长上下文（> 200K tokens，第二区间）"""
    print_section("测试长上下文（第二区间 > 200K tokens）")
    print_warning("此测试将发送大量数据，可能需要较长时间...")

    # 生成约 250K tokens 的输入
    input_text = generate_long_text(250000)
    contents = [
        {
            "role": "user",
            "parts": [{"text": f"请分析以下内容并提取关键信息：\n\n{input_text}"}]
        }
    ]

    generation_config = {
        "maxOutputTokens": 1000,
        "temperature": 0.7
    }

    print_info(f"发送请求到 {model}...")
    print_info(f"预计输入 tokens: ~250K")

    response = gemini_chat_completion(
        base_url, api_key, model, contents, generation_config, timeout=300
    )

    if not response:
        print_fail("请求失败")
        return False

    # 解析响应
    try:
        usage_metadata = response.get('usageMetadata', {})
        prompt_tokens = usage_metadata.get('promptTokenCount', 0)
        candidates_tokens = usage_metadata.get('candidatesTokenCount', 0)
        total_tokens = usage_metadata.get('totalTokenCount', 0)
        cached_tokens = usage_metadata.get('cachedContentTokenCount', 0)

        print_success(f"请求成功！")
        print_info(f"输入 tokens: {prompt_tokens}")
        print_info(f"输出 tokens: {candidates_tokens}")
        print_info(f"缓存 tokens: {cached_tokens}")
        print_info(f"总计 tokens: {total_tokens}")

        # 验证使用的价格区间
        input_tokens_k = prompt_tokens / 1000
        expected_tier = get_expected_tier(model, input_tokens_k)

        if expected_tier:
            print_success(f"预期价格区间: {expected_tier}")
            print_info(f"输入价格: ${expected_tier.input_price}/M tokens")
            print_info(f"输出价格: ${expected_tier.output_price}/M tokens")
            print_info(f"缓存命中价格: ${expected_tier.cache_hit_price}/M tokens")

            expected_cost = calculate_expected_cost(
                prompt_tokens, candidates_tokens, expected_tier,
                cache_tokens=cached_tokens
            )
            print_info(f"预期费用: ${expected_cost:.6f} USD")

        # 打印响应内容片段
        if 'candidates' in response and len(response['candidates']) > 0:
            content = response['candidates'][0].get('content', {})
            if 'parts' in content and len(content['parts']) > 0:
                text = content['parts'][0].get('text', '')
                print(f"\n{Colors.CYAN}响应内容（前200字符）:{Colors.ENDC}")
                print(f"{text[:200]}...")

        return True

    except Exception as e:
        print_fail(f"解析响应失败: {e}")
        return False


def test_boundary_case(base_url: str, api_key: str, model: str) -> bool:
    """测试边界情况（接近 200K tokens）"""
    print_section("测试边界情况（~200K tokens）")

    # 生成约 190K-210K tokens 的输入，测试边界
    input_text = generate_long_text(200000)
    contents = [
        {
            "role": "user",
            "parts": [{"text": f"请分析以下内容：\n\n{input_text}"}]
        }
    ]

    generation_config = {
        "maxOutputTokens": 500,
        "temperature": 0.7
    }

    print_info(f"发送请求到 {model}...")
    print_info(f"预计输入 tokens: ~200K（边界测试）")

    response = gemini_chat_completion(
        base_url, api_key, model, contents, generation_config, timeout=300
    )

    if not response:
        print_fail("请求失败")
        return False

    # 解析响应
    try:
        usage_metadata = response.get('usageMetadata', {})
        prompt_tokens = usage_metadata.get('promptTokenCount', 0)
        candidates_tokens = usage_metadata.get('candidatesTokenCount', 0)
        total_tokens = usage_metadata.get('totalTokenCount', 0)
        cached_tokens = usage_metadata.get('cachedContentTokenCount', 0)

        print_success(f"请求成功！")
        print_info(f"输入 tokens: {prompt_tokens} ({prompt_tokens/1000:.1f}K)")
        print_info(f"输出 tokens: {candidates_tokens}")
        print_info(f"缓存 tokens: {cached_tokens}")
        print_info(f"总计 tokens: {total_tokens}")

        # 验证使用的价格区间
        input_tokens_k = prompt_tokens / 1000
        expected_tier = get_expected_tier(model, input_tokens_k)

        if expected_tier:
            tier_range = "0-200K" if input_tokens_k < 200 else "200K+"
            print_success(f"预期价格区间: {expected_tier} ({tier_range})")
            print_info(f"输入价格: ${expected_tier.input_price}/M tokens")
            print_info(f"输出价格: ${expected_tier.output_price}/M tokens")
            print_info(f"缓存命中价格: ${expected_tier.cache_hit_price}/M tokens")

            expected_cost = calculate_expected_cost(
                prompt_tokens, candidates_tokens, expected_tier,
                cache_tokens=cached_tokens
            )
            print_info(f"预期费用: ${expected_cost:.6f} USD")

            # 边界警告
            if 190 <= input_tokens_k <= 210:
                print_warning(f"边界区间！当前输入 {input_tokens_k:.1f}K tokens")

        return True

    except Exception as e:
        print_fail(f"解析响应失败: {e}")
        return False


def test_cache_tokens(base_url: str, api_key: str, model: str) -> bool:
    """测试缓存 token 计费

    通过发送两轮相同的上下文来触发 Gemini 的隐式缓存（implicit caching），
    验证第二次请求的 cachedContentTokenCount 是否正确返回，
    以及缓存 token 是否按 cache_hit_price 单独计价。
    """
    print_section("测试缓存 token 计费（Cache Tokens）")

    # 使用足够长的文本触发隐式缓存（Gemini 隐式缓存要求 ≥ 32K tokens）
    input_text = generate_long_text(40000)
    base_contents = [
        {
            "role": "user",
            "parts": [{"text": f"请仔细阅读以下内容：\n\n{input_text}"}]
        },
        {
            "role": "model",
            "parts": [{"text": "好的，我已经仔细阅读了以上全部内容。请问您有什么问题？"}]
        },
    ]

    generation_config = {
        "maxOutputTokens": 200,
        "temperature": 0.7
    }

    # --- 第一轮请求：建立缓存 ---
    print_info("第一轮请求：建立缓存...")
    contents_round1 = base_contents + [
        {"role": "user", "parts": [{"text": "请用一句话总结上面的内容。"}]}
    ]

    resp1 = gemini_chat_completion(
        base_url, api_key, model, contents_round1, generation_config
    )
    if not resp1:
        print_fail("第一轮请求失败")
        return False

    usage1 = resp1.get('usageMetadata', {})
    prompt1 = usage1.get('promptTokenCount', 0)
    cached1 = usage1.get('cachedContentTokenCount', 0)
    candidates1 = usage1.get('candidatesTokenCount', 0)
    print_success("第一轮请求成功")
    print_info(f"  输入 tokens: {prompt1}, 缓存 tokens: {cached1}, 输出 tokens: {candidates1}")

    # --- 等待缓存生效 ---
    print_info("等待 3 秒让缓存生效...")
    time.sleep(3)

    # --- 第二轮请求：应命中缓存 ---
    print_info("第二轮请求：验证缓存命中...")
    contents_round2 = base_contents + [
        {"role": "user", "parts": [{"text": "请列出上面内容中提到的关键数字。"}]}
    ]

    resp2 = gemini_chat_completion(
        base_url, api_key, model, contents_round2, generation_config
    )
    if not resp2:
        print_fail("第二轮请求失败")
        return False

    usage2 = resp2.get('usageMetadata', {})
    prompt2 = usage2.get('promptTokenCount', 0)
    cached2 = usage2.get('cachedContentTokenCount', 0)
    candidates2 = usage2.get('candidatesTokenCount', 0)
    total2 = usage2.get('totalTokenCount', 0)
    print_success("第二轮请求成功")
    print_info(f"  输入 tokens: {prompt2}, 缓存 tokens: {cached2}, 输出 tokens: {candidates2}, 总计: {total2}")

    # --- 验证缓存命中 ---
    passed = True
    if cached2 > 0:
        print_success(f"缓存命中！cachedContentTokenCount = {cached2}")
        actual_input = prompt2 - cached2
        print_info(f"  实际计费输入 tokens: {actual_input} (prompt {prompt2} - cache {cached2})")

        input_tokens_k = prompt2 / 1000
        expected_tier = get_expected_tier(model, input_tokens_k)
        if expected_tier:
            expected_cost = calculate_expected_cost(
                prompt2, candidates2, expected_tier, cache_tokens=cached2
            )
            cost_no_cache = calculate_expected_cost(
                prompt2, candidates2, expected_tier, cache_tokens=0
            )
            savings = cost_no_cache - expected_cost
            print_info(f"  预期费用（含缓存优惠）: ${expected_cost:.6f} USD")
            print_info(f"  无缓存费用: ${cost_no_cache:.6f} USD")
            print_info(f"  缓存节省: ${savings:.6f} USD ({savings/cost_no_cache*100:.1f}%)" if cost_no_cache > 0 else "")
    else:
        print_warning("第二轮请求未命中缓存（cachedContentTokenCount = 0）")
        print_warning("这可能是因为：隐式缓存需要更大的上下文、或模型/服务端未启用缓存")
        passed = False

    # 打印响应内容片段
    if 'candidates' in resp2 and len(resp2['candidates']) > 0:
        content = resp2['candidates'][0].get('content', {})
        if 'parts' in content and len(content['parts']) > 0:
            text = content['parts'][0].get('text', '')
            print(f"\n{Colors.CYAN}第二轮响应内容（前200字符）:{Colors.ENDC}")
            print(f"{text[:200]}...")

    return passed


def print_pricing_summary(model: str):
    """打印定价概要"""
    print_header(f"{model} 分段计费概要")

    if model not in TIERED_CONFIG:
        print_fail(f"未找到模型 {model} 的定价配置")
        return

    tiers = TIERED_CONFIG[model]

    # 打印定价表格
    columns = ["区间 (K tokens)", "输入价格 ($/M)", "输出价格 ($/M)", "缓存价格 ($/M)"]
    widths = [20, 18, 18, 18]
    print_table_header(columns, widths)

    for tier in tiers:
        max_str = "∞" if tier.max_tokens_k == -1 else f"{tier.max_tokens_k}K"
        range_str = f"{tier.min_tokens_k}K - {max_str}"
        print_table_row(
            [range_str, f"${tier.input_price}", f"${tier.output_price}", f"${tier.cache_hit_price}"],
            widths
        )
    print("|" + "-" * (sum(widths) + len(widths) * 3 + 2) + "|")

    # 打印说明
    print(f"\n{Colors.CYAN}定价说明:{Colors.ENDC}")
    print(f"  • 第一区间 (0-200K): 适合短到中等长度的对话")
    print(f"  • 第二区间 (200K+): 适合长文档处理、大量上下文分析")
    print(f"  • 价格以美元 (USD) 计算")
    print(f"  • Token 计数基于千 tokens (K)")


def main():
    parser = argparse.ArgumentParser(
        description='Gemini 3.1 Pro 分段计费测试脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --url http://localhost:3000 --key sk-xxx
  %(prog)s --url http://localhost:3000 --key sk-xxx --full
  %(prog)s --url http://localhost:3000 --key sk-xxx --model gemini-3.1-pro-001
        """
    )
    parser.add_argument('--url', required=True, help='API 基础 URL (例如: http://localhost:3000)')
    parser.add_argument('--key', required=True, help='API 密钥')
    parser.add_argument('--model', default='gemini-3.1-pro-preview', help='模型名称 (默认: gemini-3.1-pro)')
    parser.add_argument('--full', action='store_true', help='运行完整测试（包括长上下文测试）')
    parser.add_argument('--boundary', action='store_true', help='仅测试边界情况')
    parser.add_argument('--cache', action='store_true', help='仅测试缓存 token 计费')

    args = parser.parse_args()

    print_header("Gemini 3.1 Pro 分段计费测试")
    print_info(f"API URL: {args.url}")
    print_info(f"模型: {args.model}")
    print_info(f"完整测试: {'是' if args.full else '否'}")

    # 打印定价概要
    print_pricing_summary(args.model)

    # 运行测试
    results = []

    if args.cache:
        # 仅测试缓存
        results.append(("缓存 token 测试", test_cache_tokens(args.url, args.key, args.model)))
    elif args.boundary:
        # 仅测试边界
        results.append(("边界测试", test_boundary_case(args.url, args.key, args.model)))
    else:
        # 短上下文测试
        results.append(("短上下文测试", test_short_context(args.url, args.key, args.model)))

        # 缓存 token 测试
        results.append(("缓存 token 测试", test_cache_tokens(args.url, args.key, args.model)))

        # 边界测试
        results.append(("边界测试", test_boundary_case(args.url, args.key, args.model)))

        # 完整测试包括长上下文
        if args.full:
            results.append(("长上下文测试", test_long_context(args.url, args.key, args.model)))

    # 打印测试结果摘要
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
        print_success("\n所有测试通过！✓")
    else:
        print_fail("\n部分测试失败，请检查日志。")

    # 获取并显示日志
    if not all_passed:
        print_section("最近的日志")
        logs = get_docker_logs()
        if logs:
            print(logs[-1000:] if len(logs) > 1000 else logs)
        else:
            print_info("无法获取日志")

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
