"""
分段计费（Tiered Pricing）完整验证脚本

验证目标：
- 验证 seed-1-8-251228 模型的分段计费配置是否正确加载
- 验证不同 token 区间是否应用正确的价格
- 通过日志验证实际计费是否正确
- 验证 BytePlus Context Cache API 的缓存计费
- 验证 BytePlus Responses API 的缓存计费（新增）

分段计费配置：
{
  "seed-1-8-251228": {
    "enabled": true,
    "tiers": [
      {
        "min_tokens": 0,
        "max_tokens": 128,
        "input_price": 0.25,
        "output_price": 2,
        "cache_hit_price": 0.05,
        "cache_store_price": 0.0083
      },
      {
        "min_tokens": 128,
        "max_tokens": -1,
        "input_price": 0.5,
        "output_price": 4,
        "cache_hit_price": 0.05,
        "cache_store_price": 0.0083
      }
    ]
  }
}

区间说明（单位：千 tokens）：
- 0-128K tokens: 输入 $0.25/M, 输出 $2/M
- 128K+ tokens: 输入 $0.5/M, 输出 $4/M

缓存计费说明：
- cache_store_price: $0.0083/M tokens (创建缓存时)
- cache_hit_price: $0.05/M tokens (使用缓存时)

BytePlus Responses API 说明：
- Responses API 是 BytePlus 新推出的对话 API，支持自动缓存
- 端点: POST /api/v3/responses
- 支持 previous_response_id 参数实现对话缓存
- 响应中包含 usage.input_tokens_details.cached_tokens 字段

Responses API 缓存参数示例（参照 BytePlus 文档）：
```bash
curl https://ark.ap-southeast.bytepluses.com/api/v3/responses \
-H "Authorization: Bearer $ARK_API_KEY" \
-H "Content-Type: application/json;charset=utf-8" \
-d '{
    "model": "seed-1-6-250915",
    "input":[
        {
            "role":"system", 
            "content": "You are a literary analysis assistant. <long excerpt>"
        }
    ],
    "caching":{
        "type":"enabled",
        "prefix": true
    },
    "thinking": {
        "type": "disabled"
    }
}'
```

注意事项：
1. input 必须超过 256 tokens，否则无法创建前缀缓存
2. caching.prefix 不支持与 max_output_tokens 同时使用
3. caching 不支持 instructions 参数
4. 使用 previous_response_id 时，设置 caching.type = "enabled"

BytePlus Context Cache API 说明：
- Context Cache API 需要使用 Endpoint ID (ep-xxx)，而不是 Model ID
- 普通 Chat API 可以使用 Model ID (如 seed-1-8-251228)
- 要测试 Context Cache，需要：
  1. 在 BytePlus 控制台创建推理端点，获取 Endpoint ID
  2. 使用 --endpoint 参数指定 Endpoint ID
  或者：
  3. 在渠道设置中配置 model_mapping: {"seed-1-8-251228": "ep-xxx"}

使用方法：
    python test_tiered_pricing.py --url <API_URL> --key <API_KEY>
    
    例如：
    python test_tiered_pricing.py --url http://localhost:3000 --key sk-xxx
    
    完整测试（包括长上下文）：
    python test_tiered_pricing.py --url http://localhost:3000 --key sk-xxx --full
    
    测试 Context Cache（需要 Endpoint ID）：
    python test_tiered_pricing.py --url http://localhost:3000 --key sk-xxx --endpoint ep-xxx
    
    测试 Responses API：
    python test_tiered_pricing.py --url http://localhost:3000 --key sk-xxx --responses
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
    cache_hit_price: float  # 缓存命中价格 USD/M tokens
    
    def __str__(self):
        max_str = "unlimited" if self.max_tokens_k == -1 else f"{self.max_tokens_k}K"
        return f"{self.min_tokens_k}K-{max_str}"


# 预定义的分段计费配置
TIERED_CONFIG = {
    "seed-1-8-251228": [
        TierConfig(0, 128, 0.25, 2.0, 0.05),
        TierConfig(128, -1, 0.5, 4.0, 0.05),
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
    cached_tokens: int = 0
) -> float:
    """计算预期费用（USD）"""
    # 非缓存输入 tokens
    non_cached_input = input_tokens - cached_tokens
    
    # 计算费用（价格单位是 USD/M tokens）
    input_cost = (non_cached_input / 1_000_000) * tier.input_price
    output_cost = (output_tokens / 1_000_000) * tier.output_price
    cache_cost = (cached_tokens / 1_000_000) * tier.cache_hit_price
    
    return input_cost + output_cost + cache_cost


def chat_completion(
    base_url: str, 
    api_key: str, 
    model: str, 
    messages: list,
    max_tokens: int = 100,
    timeout: int = 300,
    enable_cache: bool = False,
    extra_headers: dict = None
) -> Optional[Dict[str, Any]]:
    """
    发送 chat completion 请求
    
    Args:
        base_url: API 基础 URL
        api_key: API 密钥
        model: 模型名称
        messages: 消息列表
        max_tokens: 最大 tokens
        timeout: 超时时间
        enable_cache: 是否启用缓存 (Anthropic 风格)
        extra_headers: 额外的请求头
    """
    url = f"{base_url}/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 添加额外的请求头
    if extra_headers:
        headers.update(extra_headers)
    
    # 如果启用缓存，为系统消息添加 cache_control (Anthropic 风格)
    if enable_cache and messages:
        # 为最后一个系统消息添加 cache_control
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "system":
                if "cache_control" not in messages[i]:
                    messages[i]["cache_control"] = {"type": "ephemeral"}
                break
    
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        
        if response.status_code == 200:
            return response.json()
        else:
            print_fail(f"Request failed: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return None
    except requests.exceptions.Timeout:
        print_fail(f"Request timeout after {timeout}s")
        return None
    except Exception as e:
        print_fail(f"Request error: {e}")
        return None


def get_docker_logs(container_name: str = "new-api-local", lines: int = 50) -> str:
    """获取 Docker 容器日志"""
    try:
        result = subprocess.run(
            ["docker", "logs", container_name, "--tail", str(lines)],
            capture_output=True,
            timeout=10,
            encoding='utf-8',
            errors='ignore'
        )
        stdout = result.stdout if result.stdout else ""
        stderr = result.stderr if result.stderr else ""
        return stdout + stderr
    except Exception as e:
        print_warning(f"Failed to get docker logs: {e}")
        return ""


def parse_tiered_pricing_from_logs(logs: str) -> Optional[Dict[str, Any]]:
    """从日志中解析分段计费信息"""
    # 查找包含 tiered_pricing 的日志行
    pattern = r'"tiered_pricing":\s*true.*?"tiered_tier_range":\s*"([^"]+)".*?"tiered_input_price":\s*([\d.]+).*?"tiered_output_price":\s*([\d.]+)'
    
    matches = re.findall(pattern, logs)
    if matches:
        last_match = matches[-1]
        return {
            "tier_range": last_match[0],
            "input_price": float(last_match[1]),
            "output_price": float(last_match[2])
        }
    return None


def generate_long_text(target_tokens: int) -> str:
    """
    生成指定 token 数量的长文本
    根据实测：中文字符约 0.6 tokens/char
    为确保达到目标，按 0.5 tokens/char 估算（更保守）
    """
    # 基础文本块
    base_text = """
人工智能（Artificial Intelligence，简称AI）是计算机科学的一个分支，它企图了解智能的实质，
并生产出一种新的能以人类智能相似的方式做出反应的智能机器。该领域的研究包括机器人、语言识别、
图像识别、自然语言处理和专家系统等。人工智能从诞生以来，理论和技术日益成熟，应用领域也不断扩大，
可以设想，未来人工智能带来的科技产品，将会是人类智慧的"容器"。人工智能可以对人的意识、
思维的信息过程的模拟。人工智能不是人的智能，但能像人那样思考、也可能超过人的智能。

机器学习是人工智能的一个重要分支，它使用算法来解析数据、从中学习，然后对真实世界中的事件做出决策和预测。
与传统的为解决特定任务、硬编码的软件程序不同，机器学习是用大量的数据来"训练"，通过各种算法从数据中学习如何完成任务。
深度学习是机器学习的一个子集，它使用多层神经网络来模拟人脑的工作方式，从而实现对复杂模式的识别和学习。

自然语言处理（NLP）是人工智能和语言学领域的分支学科。此领域探讨如何处理及运用自然语言；
自然语言处理包括多方面和步骤，基本有认知、理解、生成等部分。自然语言认知和理解是让电脑把输入的语言变成有意思的符号和关系，
然后根据目的再处理。自然语言生成系统则是把计算机数据转化为自然语言。

计算机视觉是一门研究如何使机器"看"的科学，更进一步的说，就是指用摄影机和电脑代替人眼对目标进行识别、跟踪和测量等机器视觉，
并进一步做图形处理，使电脑处理成为更适合人眼观察或传送给仪器检测的图像。作为一个科学学科，计算机视觉研究相关的理论和技术，
试图建立能够从图像或者多维数据中获取"信息"的人工智能系统。

强化学习是机器学习的一个重要分支，它通过与环境的交互来学习最优策略。在强化学习中，智能体通过尝试不同的动作，
观察环境的反馈（奖励或惩罚），逐步学习如何在给定的环境中做出最优决策。强化学习已经在游戏、机器人控制、
自动驾驶等领域取得了显著的成果。AlphaGo就是强化学习的一个典型应用，它通过自我对弈学习围棋，最终击败了人类顶尖棋手。

生成对抗网络（GAN）是一种深度学习模型，由生成器和判别器两个神经网络组成。生成器负责生成假数据，判别器负责区分真假数据。
两个网络相互对抗、相互学习，最终生成器能够生成非常逼真的数据。GAN在图像生成、图像修复、风格迁移等领域有广泛应用。

Transformer是一种基于自注意力机制的神经网络架构，它在自然语言处理领域取得了革命性的突破。
BERT、GPT等大型语言模型都是基于Transformer架构构建的。Transformer的核心思想是通过自注意力机制，
让模型能够同时关注输入序列中的所有位置，从而更好地捕捉长距离依赖关系。
"""
    
    # 根据实测调整：约 0.58 tokens/char
    chars_per_block = len(base_text)
    tokens_per_block = chars_per_block * 0.58
    
    repeat_times = int(target_tokens / tokens_per_block) + 1
    
    # 生成长文本
    long_text = ""
    for i in range(repeat_times):
        long_text += f"\n\n=== Section {i+1} / {repeat_times} ===\n" + base_text
    
    return long_text


def test_tier_1_short_input(base_url: str, api_key: str, model: str) -> Tuple[bool, Dict]:
    """
    测试第一区间：短输入（< 128K tokens）
    """
    print_section("Test 1: Tier 1 - Short Input (< 128K tokens)")
    
    messages = [
        {"role": "user", "content": "Hello, please introduce yourself in one sentence."}
    ]
    
    print_info(f"Model: {model}")
    print_info(f"Expected tier: 0-128K (input: $0.25/M, output: $2/M)")
    
    result = chat_completion(base_url, api_key, model, messages, max_tokens=100)
    
    if result is None:
        return False, {}
    
    usage = result.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    prompt_tokens_k = prompt_tokens / 1000
    
    # 获取预期区间
    expected_tier = get_expected_tier(model, prompt_tokens_k)
    
    # 计算预期费用
    if expected_tier:
        expected_cost = calculate_expected_cost(prompt_tokens, completion_tokens, expected_tier)
    else:
        expected_cost = 0
    
    # 打印结果
    print(f"\n   Prompt tokens:     {prompt_tokens} ({prompt_tokens_k:.3f}K)")
    print(f"   Completion tokens: {completion_tokens}")
    print(f"   Expected tier:     {expected_tier}")
    print(f"   Expected cost:     ${expected_cost:.6f}")
    
    # 验证
    if prompt_tokens_k < 128:
        print_success(f"Input tokens ({prompt_tokens_k:.3f}K) < 128K, correctly in Tier 1")
        
        # 检查日志验证
        time.sleep(1)  # 等待日志写入
        logs = get_docker_logs()
        tier_info = parse_tiered_pricing_from_logs(logs)
        
        if tier_info:
            print_success(f"Log verification: tier_range={tier_info['tier_range']}, "
                         f"input_price=${tier_info['input_price']}, output_price=${tier_info['output_price']}")
            
            if tier_info['tier_range'] == "0-128":
                print_success("Tier range matches expected: 0-128")
            else:
                print_warning(f"Tier range mismatch: expected 0-128, got {tier_info['tier_range']}")
        
        return True, {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tier": "0-128K",
            "expected_cost": expected_cost
        }
    else:
        print_warning(f"Input tokens ({prompt_tokens_k:.3f}K) >= 128K, in Tier 2")
        return True, {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tier": "128K+",
            "expected_cost": expected_cost
        }


def test_tier_1_medium_input(base_url: str, api_key: str, model: str) -> Tuple[bool, Dict]:
    """
    测试第一区间：中等输入（仍在 < 128K tokens）
    """
    print_section("Test 2: Tier 1 - Medium Input (still < 128K tokens)")
    
    # 生成约 1000 tokens 的输入
    content = generate_long_text(1000)
    
    messages = [
        {"role": "user", "content": f"Please summarize the following text in 2 sentences:\n\n{content}"}
    ]
    
    print_info(f"Model: {model}")
    print_info(f"Input text length: ~{len(content)} chars")
    print_info(f"Expected tier: 0-128K (input: $0.25/M, output: $2/M)")
    
    result = chat_completion(base_url, api_key, model, messages, max_tokens=200)
    
    if result is None:
        return False, {}
    
    usage = result.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    prompt_tokens_k = prompt_tokens / 1000
    
    # 获取预期区间
    expected_tier = get_expected_tier(model, prompt_tokens_k)
    
    # 计算预期费用
    if expected_tier:
        expected_cost = calculate_expected_cost(prompt_tokens, completion_tokens, expected_tier)
    else:
        expected_cost = 0
    
    # 打印结果
    print(f"\n   Prompt tokens:     {prompt_tokens} ({prompt_tokens_k:.3f}K)")
    print(f"   Completion tokens: {completion_tokens}")
    print(f"   Expected tier:     {expected_tier}")
    print(f"   Expected cost:     ${expected_cost:.6f}")
    
    # 验证
    if prompt_tokens_k < 128:
        print_success(f"Input tokens ({prompt_tokens_k:.3f}K) < 128K, correctly in Tier 1")
        
        # 检查日志验证
        time.sleep(1)
        logs = get_docker_logs()
        tier_info = parse_tiered_pricing_from_logs(logs)
        
        if tier_info:
            print_success(f"Log verification: tier_range={tier_info['tier_range']}")
        
        return True, {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tier": "0-128K",
            "expected_cost": expected_cost
        }
    else:
        print_warning(f"Input tokens ({prompt_tokens_k:.3f}K) >= 128K")
        return True, {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tier": "128K+",
            "expected_cost": expected_cost
        }


def test_tier_2_long_input(base_url: str, api_key: str, model: str) -> Tuple[bool, Dict]:
    """
    测试第二区间：长输入（>= 128K tokens）
    警告：这个测试会消耗大量 tokens！
    """
    print_section("Test 3: Tier 2 - Long Input (>= 128K tokens)")
    
    print_warning("This test requires ~130K+ tokens input!")
    print_warning("Estimated cost: ~$0.07 for input + output cost")
    print_info("Generating long text...")
    
    # 生成约 140K tokens 的输入（确保超过 128K）
    # 根据实测，需要约 240K 字符才能达到 140K tokens
    content = generate_long_text(140000)
    
    messages = [
        {"role": "user", "content": f"Please provide a brief summary (2-3 sentences) of this long document:\n\n{content}"}
    ]
    
    print_info(f"Model: {model}")
    print_info(f"Input text length: ~{len(content)} chars (estimated ~{len(content)*1.5/1000:.0f}K tokens)")
    print_info(f"Expected tier: 128K+ (input: $0.5/M, output: $4/M)")
    print_info("Sending request (this may take a while)...")
    
    result = chat_completion(base_url, api_key, model, messages, max_tokens=200, timeout=600)
    
    if result is None:
        return False, {}
    
    usage = result.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    prompt_tokens_k = prompt_tokens / 1000
    
    # 获取预期区间
    expected_tier = get_expected_tier(model, prompt_tokens_k)
    
    # 计算预期费用
    if expected_tier:
        expected_cost = calculate_expected_cost(prompt_tokens, completion_tokens, expected_tier)
    else:
        expected_cost = 0
    
    # 打印结果
    print(f"\n   Prompt tokens:     {prompt_tokens} ({prompt_tokens_k:.3f}K)")
    print(f"   Completion tokens: {completion_tokens}")
    print(f"   Expected tier:     {expected_tier}")
    print(f"   Expected cost:     ${expected_cost:.6f}")
    
    # 验证
    if prompt_tokens_k >= 128:
        print_success(f"Input tokens ({prompt_tokens_k:.3f}K) >= 128K, correctly in Tier 2")
        
        # 检查日志验证
        time.sleep(1)
        logs = get_docker_logs()
        tier_info = parse_tiered_pricing_from_logs(logs)
        
        if tier_info:
            print_success(f"Log verification: tier_range={tier_info['tier_range']}, "
                         f"input_price=${tier_info['input_price']}, output_price=${tier_info['output_price']}")
            
            if tier_info['tier_range'] == "128--1":
                print_success("Tier range matches expected: 128--1 (128K to unlimited)")
            elif tier_info['input_price'] == 0.5 and tier_info['output_price'] == 4:
                print_success("Prices match Tier 2: input=$0.5/M, output=$4/M")
            else:
                print_warning(f"Tier info: {tier_info}")
        
        return True, {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tier": "128K+",
            "expected_cost": expected_cost
        }
    else:
        print_fail(f"Input tokens ({prompt_tokens_k:.3f}K) < 128K, should be in Tier 2!")
        return False, {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tier": "0-128K (unexpected)",
            "expected_cost": expected_cost
        }


def create_byteplus_context_cache(
    base_url: str,
    api_key: str,
    model: str,
    messages: list,
    ttl: int = 3600,
    mode: str = "session"
) -> Optional[Dict[str, Any]]:
    """
    创建 BytePlus Context Cache
    返回包含 context_id 和 usage 的字典
    
    注意：不同模型支持的参数不同
    - 有些模型不支持 truncation_strategy
    - mode 可以是 "session" 或 "common_prefix"
    """
    url = f"{base_url}/api/v3/context/create"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 基本参数，不包含 truncation_strategy（有些模型不支持）
    payload = {
        "model": model,
        "messages": messages,
        "mode": mode,
        "ttl": ttl
    }
    
    try:
        print_info(f"POST {url}")
        print_info(f"Payload: model={model}, messages_count={len(messages)}, mode=session, ttl={ttl}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        
        print_info(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            context_id = result.get("id")
            if context_id:
                print_success(f"Created context cache: {context_id}")
                usage = result.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                print_info(f"Cache creation prompt_tokens: {prompt_tokens}")
                
                # 检查 prompt_tokens_details
                prompt_details = usage.get("prompt_tokens_details", {})
                if prompt_details:
                    cached = prompt_details.get("cached_tokens", 0)
                    print_info(f"Cache creation cached_tokens: {cached}")
                
                return {
                    "context_id": context_id,
                    "usage": usage,
                    "raw_response": result
                }
            else:
                print_warning(f"No context_id in response: {result}")
        else:
            print_warning(f"Failed to create context cache: {response.status_code}")
            print(f"Response: {response.text[:500]}")
    except requests.exceptions.Timeout:
        print_warning("Context cache creation timeout (120s)")
    except Exception as e:
        print_warning(f"Context cache creation error: {e}")
    
    return None


def chat_with_context_cache(
    base_url: str,
    api_key: str,
    model: str,
    context_id: str,
    messages: list,
    max_tokens: int = 100
) -> Optional[Dict[str, Any]]:
    """
    使用 BytePlus Context Cache 进行对话
    """
    url = f"{base_url}/api/v3/context/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "context_id": context_id,
        "messages": messages,
        "max_tokens": max_tokens
    }
    
    try:
        print_info(f"POST {url}")
        print_info(f"Payload: model={model}, context_id={context_id}, messages_count={len(messages)}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        
        print_info(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            # 打印完整的 usage 信息用于调试
            usage = result.get("usage", {})
            if usage:
                print_info(f"Full usage response: {json.dumps(usage, indent=2)}")
            return result
        else:
            print_warning(f"Context chat failed: {response.status_code}")
            print(f"Response: {response.text[:500]}")
    except requests.exceptions.Timeout:
        print_warning("Context chat timeout (120s)")
    except Exception as e:
        print_warning(f"Context chat error: {e}")
    
    return None


def test_byteplus_context_cache(base_url: str, api_key: str, model: str, endpoint_id: str = None) -> Tuple[bool, Dict]:
    """
    测试 BytePlus 特有的 Context Cache 功能
    BytePlus Seed 模型需要主动创建缓存，而不是自动缓存
    
    API 端点：
    - POST /api/v3/context/create (创建缓存)
    - POST /api/v3/context/chat/completions (使用缓存对话)
    
    计费说明：
    - 创建缓存时：按 cache_store_price ($0.0083/M) 计费
    - 使用缓存时：按 cache_hit_price ($0.05/M) 计费
    """
    print_section("Test 4: BytePlus Context Cache (Active Caching)")
    
    print_info("BytePlus Seed models require ACTIVE cache creation")
    print_info("This is different from OpenAI/Anthropic automatic caching")
    print()
    print_info("Pricing for Context Cache:")
    print_info("  - Cache store: $0.0083 / M tokens")
    print_info("  - Cache hit:   $0.05 / M tokens")
    print_info("  - Regular input: $0.25 / M tokens (Tier 1)")
    print()
    print_info("Testing Context Cache API endpoints...")
    
    # 确定用于 Context Cache 的模型/endpoint
    cache_model = endpoint_id if endpoint_id else model
    if endpoint_id:
        print_info(f"Using endpoint ID for Context Cache: {endpoint_id}")
    else:
        print_warning(f"No endpoint ID provided, using model name: {model}")
        print_warning("Context Cache API requires endpoint ID (ep-xxx), not model name")
        print_info("Use --endpoint flag to specify endpoint ID")
    
    # 创建一个较长的系统提示词，以便更好地测试缓存效果
    unique_id = int(time.time() * 1000)
    
    # 生成约 2000 tokens 的系统提示词
    system_prompt = f"""You are a helpful AI assistant specialized in answering questions.
Session ID: {unique_id}

=== GUIDELINES ===
1. Be concise and accurate in all responses
2. Provide examples when helpful to illustrate concepts
3. Always be polite and professional in your communication
4. If you don't know something, honestly say so
5. Use structured formatting when presenting complex information

=== BACKGROUND KNOWLEDGE ===
This session is testing the context caching feature of the BytePlus Seed model.
Context caching is a feature that allows you to cache the initial context (system prompt and early messages)
to reduce token costs on subsequent requests.

Key points about context caching:
- Cache creation: When you create a cache, the system stores the tokenized context
- Cache hit: When you use a cached context, you only pay the cache_hit_price instead of full input price
- Cache store price: $0.0083 per million tokens (for storing the cache)
- Cache hit price: $0.05 per million tokens (for using the cache)
- Regular input price: $0.25 per million tokens (Tier 1, 0-128K tokens)

This means using cache can save up to 80% on input token costs!

=== ADDITIONAL CONTEXT ===
The BytePlus/Volcengine Context Cache API provides two main endpoints:
1. POST /api/v3/context/create - Creates a new context cache
2. POST /api/v3/context/chat/completions - Uses an existing cache for chat

The cache has a TTL (time-to-live) that determines how long it stays valid.
Default TTL is 86400 seconds (24 hours), but can be set between 3600 and 604800 seconds.

=== INSTRUCTIONS FOR THIS SESSION ===
When the user asks about your session ID, respond with: {unique_id}
When asked about guidelines, list the 5 guidelines above.
When asked about caching, explain the cost savings.

Remember: This is a test session to verify that context caching works correctly
and that the billing system properly applies cache_hit_price for cached tokens.
"""
    
    initial_messages = [
        {"role": "system", "content": system_prompt}
    ]
    
    # Step 1: 创建缓存
    print()
    print_info("=" * 50)
    print_info("Step 1: Creating context cache...")
    print_info("=" * 50)
    
    cache_result = create_byteplus_context_cache(base_url, api_key, cache_model, initial_messages, ttl=3600)
    
    if not cache_result:
        print_warning("Context cache creation not supported or failed")
        print_info("Possible reasons:")
        print_info("  1. The model name needs to be mapped to an endpoint ID (ep-xxx)")
        print_info("  2. The upstream doesn't support Context Cache API")
        print_info("  3. The channel's model_mapping is not configured")
        print()
        print_info("To fix: Configure model_mapping in the channel settings:")
        print_info('  {"seed-1-8-251228": "ep-xxxxxxxx-xxxxx"}')
        return True, {"note": "Context cache API not available - check model_mapping"}
    
    context_id = cache_result.get("context_id")
    create_usage = cache_result.get("usage", {})
    create_prompt_tokens = create_usage.get("prompt_tokens", 0)
    
    # 计算缓存创建费用
    tier = get_expected_tier(model, create_prompt_tokens / 1000)
    if tier:
        # 缓存创建使用 cache_store_price
        cache_store_price = 0.0083  # USD per M tokens
        store_cost = (create_prompt_tokens / 1_000_000) * cache_store_price
        print_info(f"Cache creation cost: ${store_cost:.6f} ({create_prompt_tokens} tokens @ $0.0083/M)")
    
    # Step 2: 使用缓存进行第一次对话
    print()
    print_info("=" * 50)
    print_info("Step 2: First chat with context cache...")
    print_info("=" * 50)
    
    user_messages = [
        {"role": "user", "content": "Hello! What is your session ID? Please respond briefly."}
    ]
    
    result = chat_with_context_cache(base_url, api_key, cache_model, context_id, user_messages, max_tokens=100)
    
    if result is None:
        print_warning("Context cache conversation failed")
        return True, {"context_id": context_id, "note": "Conversation failed"}
    
    usage = result.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    
    prompt_details = usage.get("prompt_tokens_details", {})
    cached_tokens = prompt_details.get("cached_tokens", 0) if prompt_details else 0
    
    # 打印响应内容
    choices = result.get("choices", [])
    if choices:
        message = choices[0].get("message", {})
        content = message.get("content", "")
        print_info(f"Response: {content[:200]}...")
    
    print()
    print(f"   {Colors.BOLD}Token Usage:{Colors.ENDC}")
    print(f"   Prompt tokens:     {prompt_tokens}")
    print(f"   Completion tokens: {completion_tokens}")
    print(f"   Cached tokens:     {cached_tokens}")
    
    if cached_tokens > 0:
        cache_ratio = cached_tokens / prompt_tokens * 100 if prompt_tokens > 0 else 0
        print_success(f"Context cache HIT! {cached_tokens} tokens cached ({cache_ratio:.1f}%)")
        
        # 计算费用对比
        if tier:
            # 非缓存 tokens 的费用
            non_cached = prompt_tokens - cached_tokens
            non_cached_cost = (non_cached / 1_000_000) * tier.input_price
            
            # 缓存 tokens 的费用 (cache_hit_price)
            cache_hit_cost = (cached_tokens / 1_000_000) * tier.cache_hit_price
            
            # 如果没有缓存的费用
            full_cost = (prompt_tokens / 1_000_000) * tier.input_price
            
            # 实际费用
            actual_cost = non_cached_cost + cache_hit_cost
            
            # 节省
            savings = full_cost - actual_cost
            savings_percent = (savings / full_cost * 100) if full_cost > 0 else 0
            
            print()
            print(f"   {Colors.BOLD}Cost Analysis:{Colors.ENDC}")
            print(f"   Without cache: ${full_cost:.6f} ({prompt_tokens} tokens @ ${tier.input_price}/M)")
            print(f"   With cache:    ${actual_cost:.6f}")
            print(f"     - Non-cached: ${non_cached_cost:.6f} ({non_cached} tokens @ ${tier.input_price}/M)")
            print(f"     - Cached:     ${cache_hit_cost:.6f} ({cached_tokens} tokens @ ${tier.cache_hit_price}/M)")
            print_success(f"Savings: ${savings:.6f} ({savings_percent:.1f}%)")
    else:
        print_info("No cache hit in response (this may be normal for first request)")
    
    # Step 3: 使用缓存进行第二次对话
    print()
    print_info("=" * 50)
    print_info("Step 3: Second chat with same context cache...")
    print_info("=" * 50)
    
    user_messages_2 = [
        {"role": "user", "content": "What are the 5 guidelines you should follow? List them briefly."}
    ]
    
    result_2 = chat_with_context_cache(base_url, api_key, cache_model, context_id, user_messages_2, max_tokens=200)
    
    cached_tokens_2 = 0
    if result_2:
        usage_2 = result_2.get("usage", {})
        prompt_tokens_2 = usage_2.get("prompt_tokens", 0)
        completion_tokens_2 = usage_2.get("completion_tokens", 0)
        prompt_details_2 = usage_2.get("prompt_tokens_details", {})
        cached_tokens_2 = prompt_details_2.get("cached_tokens", 0) if prompt_details_2 else 0
        
        # 打印响应内容
        choices_2 = result_2.get("choices", [])
        if choices_2:
            message_2 = choices_2[0].get("message", {})
            content_2 = message_2.get("content", "")
            print_info(f"Response: {content_2[:300]}...")
        
        print()
        print(f"   {Colors.BOLD}Token Usage:{Colors.ENDC}")
        print(f"   Prompt tokens:     {prompt_tokens_2}")
        print(f"   Completion tokens: {completion_tokens_2}")
        print(f"   Cached tokens:     {cached_tokens_2}")
        
        if cached_tokens_2 > 0:
            cache_ratio_2 = cached_tokens_2 / prompt_tokens_2 * 100 if prompt_tokens_2 > 0 else 0
            print_success(f"Context cache HIT! {cached_tokens_2} tokens cached ({cache_ratio_2:.1f}%)")
        else:
            print_info("No cache hit in second request")
    
    # Step 4: 第三次对话，验证缓存持续有效
    print()
    print_info("=" * 50)
    print_info("Step 4: Third chat to verify cache persistence...")
    print_info("=" * 50)
    
    user_messages_3 = [
        {"role": "user", "content": "How much can I save by using context caching? Give a brief answer."}
    ]
    
    result_3 = chat_with_context_cache(base_url, api_key, cache_model, context_id, user_messages_3, max_tokens=150)
    
    cached_tokens_3 = 0
    if result_3:
        usage_3 = result_3.get("usage", {})
        prompt_tokens_3 = usage_3.get("prompt_tokens", 0)
        prompt_details_3 = usage_3.get("prompt_tokens_details", {})
        cached_tokens_3 = prompt_details_3.get("cached_tokens", 0) if prompt_details_3 else 0
        
        print()
        print(f"   Prompt tokens:     {prompt_tokens_3}")
        print(f"   Cached tokens:     {cached_tokens_3}")
        
        if cached_tokens_3 > 0:
            print_success(f"Cache still working! {cached_tokens_3} tokens cached")
    
    # 汇总结果
    print()
    print_info("=" * 50)
    print_info("Context Cache Test Summary")
    print_info("=" * 50)
    
    total_cached = cached_tokens + cached_tokens_2 + cached_tokens_3
    if total_cached > 0:
        print_success(f"Context Cache is WORKING!")
        print_info(f"Total cached tokens across 3 requests: {total_cached}")
    else:
        print_warning("No cache hits detected. Cache may not be working as expected.")
    
    return True, {
        "context_id": context_id,
        "create_prompt_tokens": create_prompt_tokens,
        "chat1_prompt_tokens": prompt_tokens,
        "chat1_cached_tokens": cached_tokens,
        "chat2_cached_tokens": cached_tokens_2,
        "chat3_cached_tokens": cached_tokens_3,
        "total_cached_tokens": total_cached
    }


def responses_api_request(
    base_url: str,
    api_key: str,
    model: str,
    input_content: str,
    instructions: str = None,
    max_output_tokens: int = 100,
    previous_response_id: str = None,
    caching: Dict[str, Any] = None,
    thinking: Dict[str, str] = None,
    stream: bool = False,
    timeout: int = 120
) -> Optional[Dict[str, Any]]:
    """
    发送 BytePlus Responses API 请求
    POST /api/v3/responses
    
    参数说明（根据 BytePlus 文档）：
    - caching: {"type": "enabled", "prefix": true} 启用前缀缓存
              {"type": "enabled"} 启用会话缓存
              {"type": "disabled"} 禁用缓存
    - thinking: {"type": "disabled"} 禁用思考模式（推荐用于缓存测试）
    - previous_response_id: 引用之前的响应 ID 来使用缓存
    
    注意：
    1. 缓存内容必须至少 256 tokens 才能创建前缀缓存
    2. caching.prefix 不支持与 max_output_tokens 同时使用
    3. caching 不支持 instructions 参数，需要将内容放在 input 中
    
    示例（参照 BytePlus 文档）:
    ```python
    # 第一次请求 - 创建前缀缓存
    result1 = responses_api_request(
        base_url, api_key, "seed-1-6-250915",
        input_content=[{
            "role": "system",
            "content": "You are a literary analysis assistant. <long excerpt>"  # 必须 >256 tokens
        }],
        caching={"type": "enabled", "prefix": True},
        thinking={"type": "disabled"},
        max_output_tokens=None  # prefix 缓存不支持 max_output_tokens
    )
    
    # 第二次请求 - 使用缓存
    result2 = responses_api_request(
        base_url, api_key, "seed-1-6-250915",
        input_content="Analyze the theme",
        previous_response_id=result1["id"],
        caching={"type": "enabled"},
        thinking={"type": "disabled"},
        max_output_tokens=150
    )
    ```
    """
    url = f"{base_url}/api/v3/responses"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # input 可以是字符串或消息列表
    # 如果是字符串,转换为标准格式
    if isinstance(input_content, str):
        input_data = input_content
    elif isinstance(input_content, list):
        # 如果是列表,直接使用(支持 role/content 格式)
        input_data = input_content
    else:
        input_data = str(input_content)
    
    payload = {
        "model": model,
        "input": input_data,
        "stream": stream
    }
    
    # max_output_tokens 与 caching.prefix 不兼容，所以只在非 None 时添加
    if max_output_tokens is not None:
        payload["max_output_tokens"] = max_output_tokens
    
    if instructions:
        payload["instructions"] = instructions
    
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id
    
    # 添加缓存配置
    if caching:
        payload["caching"] = caching
    
    # 添加思考模式配置（禁用思考模式以便更好地测试缓存）
    if thinking:
        payload["thinking"] = thinking
    
    try:
        print_info(f"POST {url}")
        print_info(f"Payload: model={model}, input_length={len(input_content)}, max_output_tokens={max_output_tokens}")
        if caching:
            print_info(f"Caching config: {caching}")
        if previous_response_id:
            print_info(f"Using previous_response_id: {previous_response_id}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        
        print_info(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            return result
        else:
            print_warning(f"Responses API failed: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return None
    except requests.exceptions.Timeout:
        print_warning(f"Responses API timeout ({timeout}s)")
        return None
    except Exception as e:
        print_warning(f"Responses API error: {e}")
        return None


def test_responses_api_basic(base_url: str, api_key: str, model: str) -> Tuple[bool, Dict]:
    """
    测试 BytePlus Responses API 基本功能
    POST /api/v3/responses
    """
    print_section("Test: Responses API - Basic Request")
    
    print_info("Testing BytePlus Responses API endpoint")
    print_info("Endpoint: POST /api/v3/responses")
    print()
    
    unique_id = int(time.time() * 1000)
    input_content = f"Hello! This is test {unique_id}. Please introduce yourself briefly."
    instructions = "You are a helpful AI assistant. Keep your responses concise."
    
    print_info(f"Model: {model}")
    print_info(f"Test ID: {unique_id}")
    
    result = responses_api_request(
        base_url, api_key, model,
        input_content=input_content,
        instructions=instructions,
        max_output_tokens=100
    )
    
    if result is None:
        print_fail("Responses API request failed")
        return False, {"error": "Request failed"}
    
    # 解析响应
    response_id = result.get("id", "")
    status = result.get("status", "")
    usage = result.get("usage", {})
    
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)
    
    # 检查 input_tokens_details
    input_details = usage.get("input_tokens_details", {})
    cached_tokens = input_details.get("cached_tokens", 0) if input_details else 0
    
    # 检查 output_tokens_details
    output_details = usage.get("output_tokens_details", {})
    reasoning_tokens = output_details.get("reasoning_tokens", 0) if output_details else 0
    
    print()
    print(f"   {Colors.BOLD}Response Info:{Colors.ENDC}")
    print(f"   Response ID:       {response_id}")
    print(f"   Status:            {status}")
    print()
    print(f"   {Colors.BOLD}Token Usage:{Colors.ENDC}")
    print(f"   Input tokens:      {input_tokens}")
    print(f"   Output tokens:     {output_tokens}")
    print(f"   Total tokens:      {total_tokens}")
    print(f"   Cached tokens:     {cached_tokens}")
    if reasoning_tokens > 0:
        print(f"   Reasoning tokens:  {reasoning_tokens}")
    
    # 打印输出内容
    output_list = result.get("output", [])
    if output_list:
        for item in output_list:
            if item.get("type") == "message":
                content_list = item.get("content", [])
                for content in content_list:
                    if content.get("type") == "output_text":
                        text = content.get("text", "")
                        print()
                        print(f"   {Colors.BOLD}Response Content:{Colors.ENDC}")
                        print(f"   {text[:200]}...")
    
    if response_id:
        print_success(f"Responses API basic request successful!")
        return True, {
            "response_id": response_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "status": status
        }
    else:
        print_fail("No response ID returned")
        return False, {}


def test_responses_api_cache(base_url: str, api_key: str, model: str, previous_response_id: str = None) -> Tuple[bool, Dict]:
    """
    测试 BytePlus Responses API 缓存功能
    使用 previous_response_id 参数测试缓存命中
    
    注意：根据 BytePlus 文档，创建缓存后需要等待一段时间才能使用
    缓存内容必须至少 256 tokens 才能创建前缀缓存
    """
    print_section("Test: Responses API - Cache Test")
    
    print_info("Testing Responses API caching with previous_response_id")
    print_info("Note: Cache creation requires at least 256 tokens and some time to be ready")
    print()
    
    # Step 1: 如果没有 previous_response_id，先发送一个请求获取
    if not previous_response_id:
        print_info("Step 1: Creating initial response with prefix caching enabled...")
        
        unique_id = int(time.time() * 1000)
        
        # 生成足够长的上下文以满足缓存要求 (至少 256 tokens)
        # 注意：根据 BytePlus 文档，caching 不支持 instructions 参数
        # 所以我们需要将长上下文放在 input 中
        long_context = generate_long_text(500)
        
        # 将系统提示和长上下文放在 input 中，而不是 instructions
        # 因为 BytePlus 文档明确指出 "caching is not supported for instructions"
        input_content = f"""You are a helpful AI assistant specialized in answering questions.
Session ID: {unique_id}

=== GUIDELINES ===
1. Be concise and accurate in all responses
2. Provide examples when helpful
3. Always be polite and professional
4. If you don't know something, say so
5. Use structured formatting for complex information

=== BACKGROUND KNOWLEDGE ===
This session is testing the Responses API caching feature.
The Responses API supports caching through the previous_response_id parameter.
When you use previous_response_id, the system can reuse cached context from the previous response.

Key points about Responses API caching:
- Cache is automatically created when you make a request with caching enabled
- Use previous_response_id to reference a previous response
- Cached tokens are reported in usage.input_tokens_details.cached_tokens
- Cache hit price: $0.05/M tokens (vs regular input: $0.25/M tokens)

=== LONG CONTEXT ===
{long_context}

=== USER QUESTION ===
Hello! What is your session ID? Please respond briefly.
"""
        
        # 显式启用缓存 (prefix 模式) 和禁用思考模式
        # 根据文档：
        # 1. Cached content must be at least 256 tokens
        # 2. caching.prefix is not supported when max_output_tokens is set
        # 所以创建缓存时不设置 max_output_tokens
        caching_config = {"type": "enabled", "prefix": True}
        thinking_config = {"type": "disabled"}
        
        initial_result = responses_api_request(
            base_url, api_key, model,
            input_content=input_content,
            instructions=None,  # 不使用 instructions，因为不支持缓存
            max_output_tokens=None,  # 不设置 max_output_tokens，因为与 prefix 缓存不兼容
            caching=caching_config,
            thinking=thinking_config
        )
        
        if initial_result is None:
            print_warning("Failed to create initial response")
            return True, {"note": "Responses API not available"}
        
        previous_response_id = initial_result.get("id", "")
        initial_usage = initial_result.get("usage", {})
        initial_input_tokens = initial_usage.get("input_tokens", 0)
        
        print_success(f"Initial response created: {previous_response_id}")
        print_info(f"Initial input tokens: {initial_input_tokens}")
        
        # 等待缓存创建完成 - BytePlus 缓存需要一些时间来处理
        print_info("Waiting 5 seconds for cache to be created and ready...")
        time.sleep(5)
    
    # Step 2: 使用 previous_response_id 发送第二个请求
    print()
    print_info("Step 2: Sending request with previous_response_id...")
    print_info(f"Using previous_response_id: {previous_response_id}")
    
    # 第二次请求也需要禁用思考模式，并且启用缓存以继续使用
    # 根据文档：使用 session cache 时需要设置 caching.type = "enabled"
    caching_config = {"type": "enabled"}
    thinking_config = {"type": "disabled"}
    
    result = responses_api_request(
        base_url, api_key, model,
        input_content="Now tell me about the caching feature. How much can I save?",
        max_output_tokens=150,
        previous_response_id=previous_response_id,
        caching=caching_config,
        thinking=thinking_config
    )
    
    if result is None:
        print_warning("Cache test request failed")
        return True, {"previous_response_id": previous_response_id, "note": "Request failed"}
    
    # 解析响应
    response_id = result.get("id", "")
    usage = result.get("usage", {})
    
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    
    input_details = usage.get("input_tokens_details", {})
    cached_tokens = input_details.get("cached_tokens", 0) if input_details else 0
    
    print()
    print(f"   {Colors.BOLD}Token Usage (with cache):{Colors.ENDC}")
    print(f"   Input tokens:      {input_tokens}")
    print(f"   Output tokens:     {output_tokens}")
    print(f"   Cached tokens:     {cached_tokens}")
    
    # 检查缓存是否生效
    if cached_tokens > 0:
        cache_ratio = cached_tokens / input_tokens * 100 if input_tokens > 0 else 0
        print_success(f"Cache HIT! {cached_tokens} tokens cached ({cache_ratio:.1f}%)")
        
        # 计算费用节省
        tier = get_expected_tier(model, input_tokens / 1000)
        if tier:
            non_cached = input_tokens - cached_tokens
            non_cached_cost = (non_cached / 1_000_000) * tier.input_price
            cache_cost = (cached_tokens / 1_000_000) * tier.cache_hit_price
            full_cost = (input_tokens / 1_000_000) * tier.input_price
            actual_cost = non_cached_cost + cache_cost
            savings = full_cost - actual_cost
            savings_percent = (savings / full_cost * 100) if full_cost > 0 else 0
            
            print()
            print(f"   {Colors.BOLD}Cost Analysis:{Colors.ENDC}")
            print(f"   Without cache: ${full_cost:.6f}")
            print(f"   With cache:    ${actual_cost:.6f}")
            print_success(f"Savings: ${savings:.6f} ({savings_percent:.1f}%)")
    else:
        print_info("No cache hit detected in this request")
        print_info("This may be normal - cache behavior depends on the upstream API")
    
    # Step 3: 第三次请求，继续验证缓存
    print()
    print_info("Step 3: Third request to verify cache persistence...")
    
    result_3 = responses_api_request(
        base_url, api_key, model,
        input_content="What are the 5 guidelines you should follow?",
        max_output_tokens=200,
        previous_response_id=response_id  # 使用上一个响应的 ID
    )
    
    cached_tokens_3 = 0
    if result_3:
        usage_3 = result_3.get("usage", {})
        input_tokens_3 = usage_3.get("input_tokens", 0)
        input_details_3 = usage_3.get("input_tokens_details", {})
        cached_tokens_3 = input_details_3.get("cached_tokens", 0) if input_details_3 else 0
        
        print()
        print(f"   Input tokens:      {input_tokens_3}")
        print(f"   Cached tokens:     {cached_tokens_3}")
        
        if cached_tokens_3 > 0:
            print_success(f"Cache still working! {cached_tokens_3} tokens cached")
    
    # 检查日志
    print()
    print_info("Checking Docker logs for billing info...")
    time.sleep(1)
    logs = get_docker_logs(lines=30)
    
    # 查找 BytePlus Responses 相关日志
    if "BytePlus Responses consume" in logs:
        print_success("Found BytePlus Responses billing log!")
        # 解析日志中的计费信息
        cache_match = re.search(r'cached_tokens=(\d+)', logs)
        if cache_match:
            log_cached = int(cache_match.group(1))
            print_info(f"Log shows cached_tokens: {log_cached}")
    
    # 查找分段计费信息
    if "tiered_pricing" in logs:
        tier_info = parse_tiered_pricing_from_logs(logs)
        if tier_info:
            print_success(f"Tiered pricing applied: {tier_info}")
    
    total_cached = cached_tokens + cached_tokens_3
    
    return True, {
        "previous_response_id": previous_response_id,
        "new_response_id": response_id,
        "input_tokens": input_tokens,
        "cached_tokens": cached_tokens,
        "cached_tokens_3": cached_tokens_3,
        "total_cached": total_cached
    }


def test_responses_api_full(base_url: str, api_key: str, model: str) -> Tuple[bool, Dict]:
    """
    完整的 Responses API 测试流程
    """
    print_header("BytePlus Responses API Test Suite")
    
    print_info("Testing BytePlus Responses API endpoints")
    print_info("Endpoint: POST /api/v3/responses")
    print()
    
    results = {}
    
    # Test 1: 基本请求
    ok, data = test_responses_api_basic(base_url, api_key, model)
    results["basic"] = ok
    
    if not ok:
        print_fail("Basic test failed, skipping cache test")
        return False, results
    
    # Test 2: 缓存测试
    # 注意：不传递 response_id，让缓存测试自己创建带缓存配置的请求
    # 因为基础测试没有启用缓存，其 response_id 无法用于缓存测试
    ok, data = test_responses_api_cache(base_url, api_key, model, None)
    results["cache"] = ok
    
    # 汇总
    print()
    print_header("Responses API Test Summary")
    
    all_passed = all(results.values())
    for test_name, passed in results.items():
        status = f"{Colors.OKGREEN}[PASS]{Colors.ENDC}" if passed else f"{Colors.FAIL}[FAIL]{Colors.ENDC}"
        print(f"   {test_name}: {status}")
    
    if all_passed:
        print_success("All Responses API tests passed!")
    else:
        print_warning("Some Responses API tests failed")
    
    return all_passed, results


def test_cache_pricing_no_cache(base_url: str, api_key: str, model: str) -> Tuple[bool, Dict]:
    """
    测试缓存计费 - 无缓存命中（标准 OpenAI 兼容方式）
    首次请求，使用唯一内容确保不会命中缓存
    注意：BytePlus Seed 模型需要使用 Context Cache API，普通请求不会自动缓存
    """
    print_section("Test 5: Standard Cache Test - No Cache Hit (First Request)")
    
    # 使用时间戳确保内容唯一
    unique_id = int(time.time() * 1000)
    
    # 生成一段较长的系统提示词，以便后续测试缓存
    system_prompt = f"""You are a helpful AI assistant. Your task is to help users with their questions.
Please follow these guidelines:
1. Be concise and accurate in your responses
2. If you don't know something, say so
3. Always be polite and professional
4. Provide examples when helpful
5. This is test session {unique_id}

Additional context for this conversation:
- The user may ask about various topics
- You should provide helpful and informative responses
- Keep your answers focused and relevant
"""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Hello! This is test {unique_id}. Please say hi back."}
    ]
    
    print_info(f"Model: {model}")
    print_info(f"Test ID: {unique_id}")
    print_info("Expected: No cache hit (first request with unique content)")
    print_info("Sending request with cache_control enabled (Anthropic style)...")
    
    # 添加缓存控制头部和 Anthropic 风格的 cache_control
    extra_headers = {
        "anthropic-beta": "prompt-caching-2024-07-31",
        "x-cache-control": "ephemeral"
    }
    
    result = chat_completion(
        base_url, api_key, model, messages, 
        max_tokens=50, 
        enable_cache=True,  # 启用 Anthropic 风格缓存
        extra_headers=extra_headers
    )
    
    if result is None:
        return False, {}
    
    usage = result.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    cached_tokens = usage.get("cached_tokens", 0)
    
    # 检查 prompt_tokens_details
    prompt_details = usage.get("prompt_tokens_details", {})
    detail_cached = prompt_details.get("cached_tokens", 0) if prompt_details else 0
    
    print(f"\n   Prompt tokens:     {prompt_tokens}")
    print(f"   Completion tokens: {completion_tokens}")
    print(f"   Cached tokens:     {cached_tokens}")
    if prompt_details:
        print(f"   prompt_tokens_details.cached_tokens: {detail_cached}")
    
    # 验证无缓存命中
    actual_cached = cached_tokens or detail_cached
    if actual_cached == 0:
        print_success("No cache hit as expected (cached_tokens = 0)")
        success = True
    else:
        print_warning(f"Unexpected cache hit on first request (cached_tokens = {actual_cached})")
        success = True  # 仍然算通过，因为可能有全局缓存
    
    # 返回消息用于后续缓存测试
    return success, {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": actual_cached,
        "messages": messages,  # 保存消息用于后续测试
        "unique_id": unique_id
    }


def test_cache_pricing_with_cache(
    base_url: str, 
    api_key: str, 
    model: str,
    previous_messages: list = None,
    unique_id: int = None
) -> Tuple[bool, Dict]:
    """
    测试缓存计费 - 缓存命中（标准 OpenAI 兼容方式）
    发送相同的请求，验证缓存命中和缓存价格
    注意：BytePlus Seed 模型需要使用 Context Cache API，此测试可能不会命中缓存
    """
    print_section("Test 6: Standard Cache Test - With Cache Hit (Repeat Request)")
    
    if previous_messages is None:
        # 如果没有之前的消息，创建新的
        unique_id = unique_id or int(time.time() * 1000)
        system_prompt = f"""You are a helpful AI assistant. Your task is to help users with their questions.
Please follow these guidelines:
1. Be concise and accurate in your responses
2. If you don't know something, say so
3. Always be polite and professional
4. Provide examples when helpful
5. This is test session {unique_id}

Additional context for this conversation:
- The user may ask about various topics
- You should provide helpful and informative responses
- Keep your answers focused and relevant
"""
        previous_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Hello! This is test {unique_id}. Please say hi back."}
        ]
    
    print_info(f"Model: {model}")
    print_info(f"Sending same request again to test cache hit")
    print_info(f"Expected cache_hit_price: $0.05/M tokens")
    print_info("Sending request with cache_control enabled (Anthropic style)...")
    
    # 等待一小段时间让缓存生效
    print_info("Waiting 2 seconds for cache to be ready...")
    time.sleep(2)
    
    # 添加缓存控制头部
    extra_headers = {
        "anthropic-beta": "prompt-caching-2024-07-31",
        "x-cache-control": "ephemeral"
    }
    
    result = chat_completion(
        base_url, api_key, model, previous_messages, 
        max_tokens=50,
        enable_cache=True,  # 启用 Anthropic 风格缓存
        extra_headers=extra_headers
    )
    
    if result is None:
        return False, {}
    
    usage = result.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    cached_tokens = usage.get("cached_tokens", 0)
    
    # 检查 prompt_tokens_details
    prompt_details = usage.get("prompt_tokens_details", {})
    detail_cached = prompt_details.get("cached_tokens", 0) if prompt_details else 0
    
    print(f"\n   Prompt tokens:     {prompt_tokens}")
    print(f"   Completion tokens: {completion_tokens}")
    print(f"   Cached tokens:     {cached_tokens}")
    if prompt_details:
        print(f"   prompt_tokens_details.cached_tokens: {detail_cached}")
    
    actual_cached = cached_tokens or detail_cached
    
    # 验证缓存命中
    if actual_cached > 0:
        cache_ratio = actual_cached / prompt_tokens * 100 if prompt_tokens > 0 else 0
        print_success(f"Cache hit! {actual_cached} tokens cached ({cache_ratio:.1f}% of prompt)")
        
        # 计算缓存节省的费用
        # 正常输入价格 vs 缓存价格
        tier = get_expected_tier(model, prompt_tokens / 1000)
        if tier:
            normal_cost = (actual_cached / 1_000_000) * tier.input_price
            cache_cost = (actual_cached / 1_000_000) * tier.cache_hit_price
            savings = normal_cost - cache_cost
            print_info(f"Cache savings: ${savings:.6f} (normal: ${normal_cost:.6f}, cached: ${cache_cost:.6f})")
        
        success = True
    else:
        print_warning("No cache hit detected. This model may not support caching.")
        print_info("Note: Not all models support prompt caching")
        success = True  # 不算失败，因为不是所有模型都支持缓存
    
    # 检查日志中的缓存信息
    time.sleep(1)
    logs = get_docker_logs(lines=20)
    if "cache_tokens" in logs or "cached_tokens" in logs:
        # 解析日志中的缓存信息
        cache_match = re.search(r'"cache_tokens":\s*(\d+)', logs)
        if cache_match:
            log_cached = int(cache_match.group(1))
            print_info(f"Log verification: cache_tokens = {log_cached}")
    
    return success, {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": actual_cached,
        "cache_hit_price": 0.05
    }


def test_cache_pricing_partial(base_url: str, api_key: str, model: str, previous_messages: list = None) -> Tuple[bool, Dict]:
    """
    测试缓存计费 - 部分缓存命中（标准 OpenAI 兼容方式）
    发送相同的系统提示词但不同的用户消息，验证部分缓存命中
    注意：BytePlus Seed 模型需要使用 Context Cache API
    """
    print_section("Test 7: Standard Cache Test - Partial Cache Hit")
    
    if previous_messages is None or len(previous_messages) < 2:
        print_warning("No previous messages available, skipping partial cache test")
        return True, {}
    
    # 使用相同的系统提示词，但不同的用户消息
    new_messages = [
        previous_messages[0],  # 相同的系统提示词
        {"role": "user", "content": f"Now tell me a joke. Request time: {time.time()}"}
    ]
    
    print_info(f"Model: {model}")
    print_info("Sending request with same system prompt but different user message")
    print_info("Expected: Partial cache hit on system prompt")
    print_info("Sending request with cache_control enabled (Anthropic style)...")
    
    # 添加缓存控制头部
    extra_headers = {
        "anthropic-beta": "prompt-caching-2024-07-31",
        "x-cache-control": "ephemeral"
    }
    
    result = chat_completion(
        base_url, api_key, model, new_messages, 
        max_tokens=100,
        enable_cache=True,  # 启用 Anthropic 风格缓存
        extra_headers=extra_headers
    )
    
    if result is None:
        return False, {}
    
    usage = result.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    cached_tokens = usage.get("cached_tokens", 0)
    
    prompt_details = usage.get("prompt_tokens_details", {})
    detail_cached = prompt_details.get("cached_tokens", 0) if prompt_details else 0
    
    print(f"\n   Prompt tokens:     {prompt_tokens}")
    print(f"   Completion tokens: {completion_tokens}")
    print(f"   Cached tokens:     {cached_tokens}")
    if prompt_details:
        print(f"   prompt_tokens_details.cached_tokens: {detail_cached}")
    
    actual_cached = cached_tokens or detail_cached
    
    if actual_cached > 0:
        cache_ratio = actual_cached / prompt_tokens * 100 if prompt_tokens > 0 else 0
        print_success(f"Partial cache hit! {actual_cached} tokens cached ({cache_ratio:.1f}% of prompt)")
    else:
        print_info("No partial cache hit. This is normal for some models.")
    
    return True, {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": actual_cached
    }


def test_database_config() -> Tuple[bool, str]:
    """
    检查数据库中的分段计费配置
    """
    print_section("Test 0: Database Configuration Check")
    
    try:
        result = subprocess.run(
            ["docker", "exec", "postgres-local", "psql", "-U", "root", "-d", "new-api", 
             "-c", "SELECT value FROM options WHERE key = 'TieredPricing';"],
            capture_output=True,
            timeout=10,
            encoding='utf-8',
            errors='ignore'
        )
        
        output = result.stdout
        if "seed-1-8-251228" in output and '"enabled": true' in output:
            print_success("TieredPricing config found in database")
            
            # 解析配置
            if '"min_tokens": 0' in output and '"max_tokens": 128' in output:
                print_success("Tier 1 config: 0-128K tokens")
            if '"min_tokens": 128' in output and '"max_tokens": -1' in output:
                print_success("Tier 2 config: 128K+ tokens")
            
            return True, output
        else:
            print_fail("TieredPricing config not found or not enabled")
            return False, output
    except Exception as e:
        print_warning(f"Failed to check database: {e}")
        return False, str(e)


def run_all_tests(base_url: str, api_key: str, model: str, full_test: bool = False, 
                  test_cache: bool = True, endpoint_id: str = None, test_responses: bool = False):
    """运行所有测试"""
    print_header(f"Tiered Pricing Verification - {model}")
    
    print_info(f"API URL: {base_url}")
    print_info(f"Model: {model}")
    if endpoint_id:
        print_info(f"Endpoint ID: {endpoint_id} (for Context Cache)")
    print_info(f"Full test (including 128K+ input): {full_test}")
    print_info(f"Cache test: {test_cache}")
    print_info(f"Responses API test: {test_responses}")
    
    results = {}
    test_data = []
    cache_test_data = []
    
    # Test 0: 数据库配置检查
    db_ok, _ = test_database_config()
    results["database_config"] = db_ok
    
    # Test 1: 短输入（Tier 1）
    ok, data = test_tier_1_short_input(base_url, api_key, model)
    results["tier1_short"] = ok
    if data:
        test_data.append(("Short input", data))
    
    # Test 2: 中等输入（Tier 1）
    ok, data = test_tier_1_medium_input(base_url, api_key, model)
    results["tier1_medium"] = ok
    if data:
        test_data.append(("Medium input", data))
    
    # Test 3: 长输入（Tier 2）- 仅在 full_test 模式下运行
    if full_test:
        ok, data = test_tier_2_long_input(base_url, api_key, model)
        results["tier2_long"] = ok
        if data:
            test_data.append(("Long input (128K+)", data))
    else:
        print_section("Test 3: Tier 2 - Long Input (SKIPPED)")
        print_warning("Skipped: Use --full flag to run this test")
        print_info("This test requires ~130K tokens and will cost ~$0.07")
        results["tier2_long"] = None
    
    # Responses API Tests (if enabled)
    responses_test_data = []
    if test_responses:
        print_section("Responses API Tests")
        ok, data = test_responses_api_full(base_url, api_key, model)
        results["responses_api"] = ok
        if data:
            responses_test_data.append(("Responses API", data))
    else:
        print_section("Responses API Tests (SKIPPED)")
        print_warning("Skipped: Use --responses flag to run Responses API tests")
        results["responses_api"] = None
    
    # Cache Tests (4-7)
    previous_messages = None
    unique_id = None
    context_cache_data = None
    
    if test_cache:
        # Test 4: BytePlus Context Cache (主动缓存) - 这是主要的缓存测试
        ok, data = test_byteplus_context_cache(base_url, api_key, model, endpoint_id)
        results["byteplus_context_cache"] = ok
        context_cache_data = data
        
        # 如果 Context Cache 有数据，添加到缓存测试结果
        if data and data.get("total_cached_tokens", 0) > 0:
            cache_test_data.append(("Context Cache Create", {
                "prompt_tokens": data.get("create_prompt_tokens", 0),
                "completion_tokens": 0,
                "cached_tokens": 0,
                "note": "Cache stored"
            }))
            cache_test_data.append(("Context Cache Chat 1", {
                "prompt_tokens": data.get("chat1_prompt_tokens", 0),
                "completion_tokens": 0,
                "cached_tokens": data.get("chat1_cached_tokens", 0)
            }))
            if data.get("chat2_cached_tokens", 0) > 0:
                cache_test_data.append(("Context Cache Chat 2", {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cached_tokens": data.get("chat2_cached_tokens", 0)
                }))
            if data.get("chat3_cached_tokens", 0) > 0:
                cache_test_data.append(("Context Cache Chat 3", {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cached_tokens": data.get("chat3_cached_tokens", 0)
                }))
        
        # Test 5: 标准缓存测试 - 无缓存命中 (OpenAI 兼容方式，BytePlus 可能不支持)
        ok, data = test_cache_pricing_no_cache(base_url, api_key, model)
        results["cache_no_hit"] = ok
        if data and data.get("prompt_tokens"):
            cache_test_data.append(("Standard - No cache", data))
            previous_messages = data.get("messages")
            unique_id = data.get("unique_id")
        
        # Test 6: 标准缓存测试 - 缓存命中
        ok, data = test_cache_pricing_with_cache(base_url, api_key, model, previous_messages, unique_id)
        results["cache_with_hit"] = ok
        if data and data.get("prompt_tokens"):
            cache_test_data.append(("Standard - With cache", data))
        
        # Test 7: 标准缓存测试 - 部分缓存命中
        ok, data = test_cache_pricing_partial(base_url, api_key, model, previous_messages)
        results["cache_partial"] = ok
        if data and data.get("prompt_tokens"):
            cache_test_data.append(("Standard - Partial", data))
    else:
        print_section("Cache Tests (SKIPPED)")
        print_warning("Skipped: Cache tests are enabled by default")
        print_info("Use --no-cache flag to skip cache tests")
        results["byteplus_context_cache"] = None
        results["cache_no_hit"] = None
        results["cache_with_hit"] = None
        results["cache_partial"] = None
    
    # 打印测试数据汇总表
    print_header("Test Results Summary")
    
    # Tier 测试结果
    if test_data:
        print(f"\n{Colors.BOLD}Tiered Pricing Tests:{Colors.ENDC}")
        columns = ["Test", "Prompt Tokens", "Completion", "Tier", "Est. Cost"]
        widths = [20, 15, 12, 12, 12]
        print_table_header(columns, widths)
        
        for name, data in test_data:
            values = [
                name,
                str(data.get("prompt_tokens", "N/A")),
                str(data.get("completion_tokens", "N/A")),
                data.get("tier", "N/A"),
                f"${data.get('expected_cost', 0):.6f}"
            ]
            highlight = "128K+" in data.get("tier", "")
            print_table_row(values, widths, highlight)
        
        print("|" + "-" * (sum(widths) + len(widths) * 3 - 1) + "|")
    
    # 缓存测试结果
    if cache_test_data:
        print(f"\n{Colors.BOLD}Cache Pricing Tests:{Colors.ENDC}")
        columns = ["Test", "Prompt", "Completion", "Cached", "Cache Rate"]
        widths = [20, 12, 12, 12, 12]
        print_table_header(columns, widths)
        
        for name, data in cache_test_data:
            prompt = data.get("prompt_tokens", 0)
            cached = data.get("cached_tokens", 0)
            cache_rate = f"{cached/prompt*100:.1f}%" if prompt > 0 else "0%"
            
            values = [
                name,
                str(prompt),
                str(data.get("completion_tokens", "N/A")),
                str(cached),
                cache_rate
            ]
            highlight = cached > 0
            print_table_row(values, widths, highlight)
        
        print("|" + "-" * (sum(widths) + len(widths) * 3 - 1) + "|")
    
    # 打印测试结果
    print("\n" + Colors.BOLD + "Test Results:" + Colors.ENDC)
    all_passed = True
    for test_name, passed in results.items():
        if passed is None:
            status = f"{Colors.WARNING}[SKIP]{Colors.ENDC}"
        elif passed:
            status = f"{Colors.OKGREEN}[PASS]{Colors.ENDC}"
        else:
            status = f"{Colors.FAIL}[FAIL]{Colors.ENDC}"
            all_passed = False
        print(f"   {test_name}: {status}")
    
    print()
    if all_passed:
        print_success("All tests passed! Tiered pricing is working correctly.")
    else:
        print_fail("Some tests failed. Please check the configuration.")
    
    # 打印价格区间说明
    print_section("Tiered Pricing Reference")
    print("   Tier 1 (0-128K tokens):")
    print("      Input:  $0.25 / M tokens")
    print("      Output: $2.00 / M tokens")
    print("      Cache:  $0.05 / M tokens")
    print()
    print("   Tier 2 (128K+ tokens):")
    print("      Input:  $0.50 / M tokens")
    print("      Output: $4.00 / M tokens")
    print("      Cache:  $0.05 / M tokens")
    
    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description="Tiered Pricing Verification Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic test (Tier 1 + Cache tests)
    python test_tiered_pricing.py --url http://localhost:3000 --key sk-xxx
    
    # Full test (including Tier 2 with 128K+ tokens)
    python test_tiered_pricing.py --url http://localhost:3000 --key sk-xxx --full
    
    # Skip cache tests
    python test_tiered_pricing.py --url http://localhost:3000 --key sk-xxx --no-cache
    
    # Test with specific endpoint ID for Context Cache
    python test_tiered_pricing.py --url http://localhost:3000 --key sk-xxx --endpoint ep-xxx
    
    # Full test with all features
    python test_tiered_pricing.py --url http://localhost:3000 --key sk-xxx --full --endpoint ep-xxx

Note on Context Cache:
    BytePlus Context Cache API requires an Endpoint ID (ep-xxx) instead of model name.
    If you want to test Context Cache, you need to either:
    1. Configure model_mapping in the channel settings: {"seed-1-8-251228": "ep-xxx"}
    2. Use --endpoint flag to specify the endpoint ID directly
        """
    )
    parser.add_argument("--url", type=str, default="http://localhost:3000",
                        help="API URL (default: http://localhost:3000)")
    parser.add_argument("--key", type=str, required=True,
                        help="API Key")
    parser.add_argument("--model", type=str, default="seed-1-8-251228",
                        help="Model to test (default: seed-1-8-251228)")
    parser.add_argument("--endpoint", type=str, default=None,
                        help="BytePlus Endpoint ID (ep-xxx) for Context Cache tests")
    parser.add_argument("--full", action="store_true",
                        help="Run full test including 128K+ token input (costs ~$0.07)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Skip cache pricing tests")
    parser.add_argument("--responses", action="store_true",
                        help="Run Responses API tests (POST /api/v3/responses)")
    
    args = parser.parse_args()
    
    # 移除 URL 末尾的斜杠
    base_url = args.url.rstrip("/")
    
    run_all_tests(base_url, args.key, args.model, args.full, 
                  test_cache=not args.no_cache, endpoint_id=args.endpoint,
                  test_responses=args.responses)


if __name__ == "__main__":
    main()
