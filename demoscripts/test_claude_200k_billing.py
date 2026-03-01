"""
Claude 200K 分段计费验证脚本

验证目标：
- 验证 Claude 模型在 input tokens ≤ 200K 时使用正常费率
- 验证 Claude 模型在 input tokens > 200K 时自动应用特殊倍率
  - 输入价格 x2（如 $5 → $10 / MTok）
  - 输出价格 x1.5（如 $25 → $37.50 / MTok）
- 通过对比两次请求的实际扣费来验证倍率是否生效

策略：
- 使用 1M 特殊填充标记（重复文本）构造超长 prompt，使 input tokens > 200K
- 对比一次短请求（< 200K）和一次长请求（> 200K）的 token 费用比例
- 通过 /api/log/self 接口获取实际扣费日志进行验证

使用方法：
    python test_claude_200k_billing.py --url http://localhost:3000 --key sk-xxx
    python test_claude_200k_billing.py --url http://localhost:3000 --key sk-xxx --model claude-sonnet-4-20250514
    python test_claude_200k_billing.py --url http://localhost:3000 --key sk-xxx --test short  # 只跑短请求
    python test_claude_200k_billing.py --url http://localhost:3000 --key sk-xxx --test long   # 只跑长请求
"""

import os
import json
import time
import argparse
import requests
from typing import Optional, Tuple

# ==================== 颜色输出 ====================

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'


def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}  {text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def print_success(text: str):
    print(f"{Colors.OKGREEN}✅ {text}{Colors.ENDC}")


def print_fail(text: str):
    print(f"{Colors.FAIL}❌ {text}{Colors.ENDC}")


def print_info(text: str):
    print(f"{Colors.OKBLUE}ℹ️  {text}{Colors.ENDC}")


def print_warn(text: str):
    print(f"{Colors.WARNING}⚠️  {text}{Colors.ENDC}")


def print_dim(text: str):
    print(f"{Colors.DIM}{text}{Colors.ENDC}")


# ==================== 填充文本生成 ====================

# 使用多样化的英文文本块作为填充，每个块约 200-300 tokens
FILLER_BLOCKS = [
    """The development of artificial intelligence has transformed numerous industries worldwide.
Machine learning algorithms now power recommendation systems, autonomous vehicles, and medical diagnostics.
Natural language processing enables chatbots and translation services that were once thought impossible.
Computer vision systems can identify objects, faces, and even emotions with remarkable accuracy.
Reinforcement learning has achieved superhuman performance in complex games like Go and StarCraft.
The ethical implications of these advances continue to be debated by researchers, policymakers, and the public.""",

    """Cloud computing has revolutionized how businesses deploy and scale their applications.
Infrastructure as a service provides virtual machines, storage, and networking on demand.
Platform as a service offers development tools and runtime environments without managing servers.
Software as a service delivers complete applications through web browsers.
Serverless computing allows developers to focus on code without worrying about infrastructure.
Container orchestration with Kubernetes has become the standard for managing microservices.""",

    """The history of programming languages spans over seven decades of innovation and evolution.
Assembly language provided the first abstraction over machine code in the 1950s.
FORTRAN and COBOL brought high-level programming to scientific and business computing.
C language introduced portable systems programming and influenced countless successors.
Object-oriented programming with Smalltalk and C++ changed how developers model problems.
Modern languages like Rust, Go, and Swift continue to push the boundaries of safety and performance.""",

    """Distributed systems form the backbone of modern internet services and cloud platforms.
Consistency, availability, and partition tolerance cannot all be guaranteed simultaneously.
Consensus algorithms like Raft and Paxos enable replicated state machines across multiple nodes.
Eventually consistent systems trade strong consistency for improved availability and latency.
Message queues decouple producers and consumers enabling asynchronous processing patterns.
Service mesh architectures provide observability, security, and traffic management for microservices.""",

    """Database technology has evolved from simple file systems to sophisticated distributed engines.
Relational databases with SQL remain the foundation for transactional workloads worldwide.
NoSQL databases offer flexible schemas and horizontal scaling for specific use cases.
Time-series databases optimize storage and queries for temporal data patterns.
Graph databases excel at modeling and querying highly connected data relationships.
NewSQL databases combine the scalability of NoSQL with the ACID guarantees of traditional systems.""",

    """Cybersecurity threats continue to evolve as technology becomes more pervasive in daily life.
Ransomware attacks target hospitals, schools, and critical infrastructure with devastating effects.
Phishing remains the most common initial attack vector for corporate data breaches.
Zero-day exploits in widely used software can affect millions of users simultaneously.
Supply chain attacks compromise trusted software distribution channels to reach downstream targets.
Defense in depth strategies layer multiple security controls to protect against diverse threats.""",

    """The Internet of Things connects billions of devices creating unprecedented data streams.
Smart home devices adjust lighting, temperature, and security based on occupant behavior patterns.
Industrial IoT sensors monitor equipment health enabling predictive maintenance strategies.
Wearable health devices track vital signs providing continuous monitoring outside clinical settings.
Connected vehicles communicate with infrastructure and each other to improve traffic flow.
Edge computing processes IoT data locally reducing latency and bandwidth requirements significantly.""",

    """Quantum computing promises to solve problems intractable for classical computers.
Quantum bits or qubits can exist in superposition representing multiple states simultaneously.
Entanglement enables correlations between qubits that have no classical analog whatsoever.
Quantum error correction remains a significant challenge for building practical quantum computers.
Shor's algorithm threatens current encryption but requires millions of stable qubits to implement.
Near-term quantum advantage may emerge in optimization, simulation, and machine learning tasks.""",
]


def generate_filler_text(target_tokens: int) -> str:
    """
    生成指定 token 数量的填充文本。
    
    粗略估算：1 token ≈ 4 个英文字符 ≈ 0.75 个英文单词
    每个 FILLER_BLOCK 约 250 tokens，循环拼接直到达到目标。
    """
    # 每个块大约 250 tokens，计算需要多少个块
    tokens_per_block = 250
    blocks_needed = (target_tokens // tokens_per_block) + 1
    
    parts = []
    for i in range(blocks_needed):
        block = FILLER_BLOCKS[i % len(FILLER_BLOCKS)]
        # 添加编号以增加多样性，避免重复被压缩
        parts.append(f"\n--- Section {i+1} ---\n{block}")
    
    result = "\n".join(parts)
    
    # 粗略截断到目标 token 数（1 token ≈ 4 字符）
    target_chars = target_tokens * 4
    if len(result) > target_chars:
        result = result[:target_chars]
    
    return result


# ==================== API 调用 ====================

def chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: list,
    max_tokens: int = 100,
    stream: bool = False,
    timeout: int = 300,
) -> Optional[dict]:
    """发送 OpenAI 兼容格式的聊天请求"""
    url = f"{base_url}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": stream,
    }

    try:
        if stream:
            resp = requests.post(url, headers=headers, json=payload, stream=True, timeout=timeout)
            if resp.status_code != 200:
                print_fail(f"HTTP {resp.status_code}: {resp.text[:500]}")
                return None

            content = ""
            usage = None
            for line in resp.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8")
                if not line_str.startswith("data: "):
                    continue
                data_str = line_str[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    if "content" in delta and delta["content"]:
                        content += delta["content"]
                    if "usage" in chunk and chunk["usage"]:
                        usage = chunk["usage"]
                except json.JSONDecodeError:
                    pass

            return {
                "content": content,
                "usage": usage or {},
            }
        else:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code != 200:
                print_fail(f"HTTP {resp.status_code}: {resp.text[:500]}")
                return None
            result = resp.json()
            return {
                "content": result["choices"][0]["message"]["content"],
                "usage": result.get("usage", {}),
            }
    except requests.exceptions.Timeout:
        print_fail(f"请求超时 (timeout={timeout}s)")
        return None
    except Exception as e:
        print_fail(f"请求异常: {type(e).__name__}: {e}")
        return None


def get_latest_log(base_url: str, api_key: str) -> Optional[dict]:
    """获取最近一条使用日志"""
    url = f"{base_url}/api/log/self"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"p": 0, "size": 1, "type": 2}  # type=2 消耗日志

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            print_warn(f"获取日志失败: HTTP {resp.status_code}")
            return None
        data = resp.json()
        logs = data.get("data", {}).get("data", [])
        if not logs:
            return None
        return logs[0]
    except Exception as e:
        print_warn(f"获取日志异常: {e}")
        return None


def get_user_quota(base_url: str, api_key: str) -> Optional[int]:
    """获取当前用户额度"""
    url = f"{base_url}/api/user/self"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("data", {}).get("quota", None)
    except:
        return None


# ==================== 测试用例 ====================

def test_short_request(base_url: str, api_key: str, model: str) -> Optional[dict]:
    """
    测试 1: 短请求（< 200K tokens）— 正常费率
    """
    print_header("测试 1: 短请求 (< 200K tokens) — 正常费率")

    messages = [
        {"role": "user", "content": "Hello, please say 'OK' and nothing else."}
    ]

    print_info(f"模型: {model}")
    print_info("预估 input tokens: ~20 (远小于 200K)")
    print_info("预期: 使用正常费率 (input x1.0, output x1.0)")
    print()

    quota_before = get_user_quota(base_url, api_key)

    start_time = time.time()
    result = chat_completion(base_url, api_key, model, messages, max_tokens=50)
    latency = time.time() - start_time

    if not result:
        print_fail("短请求失败")
        return None

    # 等一下让后台计费完成
    time.sleep(2)

    quota_after = get_user_quota(base_url, api_key)
    log = get_latest_log(base_url, api_key)

    usage = result["usage"]
    print_info(f"响应内容: {result['content'][:200]}")
    print_info(f"延迟: {latency:.2f}s")
    print_info(f"Input tokens: {usage.get('prompt_tokens', 'N/A')}")
    print_info(f"Output tokens: {usage.get('completion_tokens', 'N/A')}")
    print_info(f"Total tokens: {usage.get('total_tokens', 'N/A')}")

    if quota_before is not None and quota_after is not None:
        quota_consumed = quota_before - quota_after
        print_info(f"额度消耗: {quota_consumed} (before={quota_before}, after={quota_after})")

    if log:
        other = log.get("other", "")
        if isinstance(other, str):
            try:
                other = json.loads(other)
            except:
                other = {}
        print_info(f"日志 quota: {log.get('quota', 'N/A')}")
        print_info(f"日志 model_ratio: {other.get('model_ratio', 'N/A')}")
        print_info(f"日志 completion_ratio: {other.get('completion_ratio', 'N/A')}")

        if other.get("claude_200k"):
            print_fail("短请求不应触发 Claude 200K 倍率！")
        else:
            print_success("短请求未触发 Claude 200K 倍率 — 正确")

    print_success("短请求测试完成")
    return {
        "usage": usage,
        "log": log,
        "quota_consumed": (quota_before - quota_after) if quota_before and quota_after else None,
    }


def test_long_request(base_url: str, api_key: str, model: str) -> Optional[dict]:
    """
    测试 2: 长请求（> 200K tokens）— 特殊倍率
    使用 ~1M 特殊标记填充 prompt，确保超过 200K tokens
    """
    print_header("测试 2: 长请求 (> 200K tokens) — 特殊倍率 (1M 填充)")

    print_info(f"模型: {model}")
    print_info("正在生成 ~250K tokens 的填充文本...")

    # 生成约 250K tokens 的填充文本（确保超过 200K 阈值）
    filler = generate_filler_text(target_tokens=250000)
    print_info(f"填充文本长度: {len(filler):,} 字符 (预估 ~{len(filler)//4:,} tokens)")

    prompt = (
        f"Below is a very long document. Please read it carefully and then respond with "
        f"ONLY the word 'ACKNOWLEDGED'. Do not summarize or comment.\n\n"
        f"{filler}"
    )

    messages = [{"role": "user", "content": prompt}]

    print_info("预期: 触发 Claude >200K 倍率 (input x2.0, output x1.5)")
    print_info("发送请求中... (可能需要较长时间)")
    print()

    quota_before = get_user_quota(base_url, api_key)

    start_time = time.time()
    result = chat_completion(
        base_url, api_key, model, messages,
        max_tokens=50,
        timeout=600,  # 长上下文需要更长超时
    )
    latency = time.time() - start_time

    if not result:
        print_fail("长请求失败")
        return None

    # 等一下让后台计费完成
    time.sleep(3)

    quota_after = get_user_quota(base_url, api_key)
    log = get_latest_log(base_url, api_key)

    usage = result["usage"]
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    print_info(f"响应内容: {result['content'][:200]}")
    print_info(f"延迟: {latency:.2f}s")
    print_info(f"Input tokens: {prompt_tokens:,}")
    print_info(f"Output tokens: {completion_tokens:,}")
    print_info(f"Total tokens: {usage.get('total_tokens', 0):,}")

    if prompt_tokens > 0:
        if prompt_tokens > 200000:
            print_success(f"Input tokens ({prompt_tokens:,}) > 200K — 应触发特殊倍率")
        else:
            print_warn(f"Input tokens ({prompt_tokens:,}) ≤ 200K — 未超过阈值，可能需要增加填充量")

    if quota_before is not None and quota_after is not None:
        quota_consumed = quota_before - quota_after
        print_info(f"额度消耗: {quota_consumed:,} (before={quota_before:,}, after={quota_after:,})")

    claude_200k_triggered = False
    if log:
        other = log.get("other", "")
        if isinstance(other, str):
            try:
                other = json.loads(other)
            except:
                other = {}

        print_info(f"日志 quota: {log.get('quota', 'N/A')}")
        print_info(f"日志 model_ratio: {other.get('model_ratio', 'N/A')}")
        print_info(f"日志 completion_ratio: {other.get('completion_ratio', 'N/A')}")

        if other.get("claude_200k"):
            claude_200k_triggered = True
            print_success(f"Claude 200K 倍率已触发!")
            print_info(f"  input_multiplier: {other.get('claude_200k_input_multiplier', 'N/A')}")
            print_info(f"  output_multiplier: {other.get('claude_200k_output_multiplier', 'N/A')}")
            print_info(f"  total_input_tokens: {other.get('claude_200k_total_input_tokens', 'N/A'):,}")
        else:
            if prompt_tokens > 200000:
                print_fail("Input tokens > 200K 但 Claude 200K 倍率未触发！请检查代码逻辑")
            else:
                print_warn("Claude 200K 倍率未触发（input tokens 未超过 200K）")

    print_success("长请求测试完成")
    return {
        "usage": usage,
        "log": log,
        "quota_consumed": (quota_before - quota_after) if quota_before and quota_after else None,
        "claude_200k_triggered": claude_200k_triggered,
    }


def test_compare_billing(
    base_url: str, api_key: str, model: str
):
    """
    测试 3: 对比短请求和长请求的计费比例
    """
    print_header("测试 3: 计费对比分析")

    print_info("运行短请求测试...")
    short_result = test_short_request(base_url, api_key, model)

    print_info("运行长请求测试...")
    long_result = test_long_request(base_url, api_key, model)

    print_header("计费对比结果")

    if not short_result or not long_result:
        print_fail("无法完成对比：部分测试失败")
        return

    short_usage = short_result["usage"]
    long_usage = long_result["usage"]

    short_prompt = short_usage.get("prompt_tokens", 0)
    long_prompt = long_usage.get("prompt_tokens", 0)
    short_completion = short_usage.get("completion_tokens", 0)
    long_completion = long_usage.get("completion_tokens", 0)

    short_quota = short_result.get("quota_consumed", 0) or 0
    long_quota = long_result.get("quota_consumed", 0) or 0

    print(f"\n{'指标':<30} {'短请求 (<200K)':<20} {'长请求 (>200K)':<20}")
    print(f"{'-'*70}")
    print(f"{'Input tokens':<30} {short_prompt:<20,} {long_prompt:<20,}")
    print(f"{'Output tokens':<30} {short_completion:<20,} {long_completion:<20,}")
    print(f"{'额度消耗':<30} {short_quota:<20,} {long_quota:<20,}")

    if short_prompt > 0 and long_prompt > 0 and short_quota > 0 and long_quota > 0:
        # 计算每 token 的费率
        short_rate = short_quota / short_prompt if short_prompt > 0 else 0
        long_rate = long_quota / long_prompt if long_prompt > 0 else 0
        rate_ratio = long_rate / short_rate if short_rate > 0 else 0

        print(f"\n{'每 input token 费率':<30} {short_rate:<20.4f} {long_rate:<20.4f}")
        print(f"{'费率比值 (长/短)':<30} {rate_ratio:.2f}x")

        if rate_ratio > 1.5:
            print_success(f"费率比值 {rate_ratio:.2f}x > 1.5x — Claude 200K 特殊倍率生效!")
        else:
            print_warn(f"费率比值 {rate_ratio:.2f}x — 可能未触发特殊倍率，请检查日志")

    # 检查日志中的 200K 标记
    if long_result.get("claude_200k_triggered"):
        print_success("\n最终验证: Claude >200K 分段计费功能正常工作!")
    else:
        if long_prompt > 200000:
            print_fail("\n最终验证: Input tokens > 200K 但倍率未触发，请检查代码")
        else:
            print_warn(f"\n注意: Input tokens ({long_prompt:,}) 未超过 200K 阈值")
            print_warn("请增加填充文本量或使用更长的输入重新测试")


# ==================== 主入口 ====================

def main():
    parser = argparse.ArgumentParser(
        description="Claude 200K 分段计费验证脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 运行全部测试（短请求 + 长请求 + 对比）
  python test_claude_200k_billing.py --url http://localhost:3000 --key sk-xxx

  # 只运行短请求测试
  python test_claude_200k_billing.py --url http://localhost:3000 --key sk-xxx --test short

  # 只运行长请求测试（1M 填充）
  python test_claude_200k_billing.py --url http://localhost:3000 --key sk-xxx --test long

  # 指定模型
  python test_claude_200k_billing.py --url http://localhost:3000 --key sk-xxx --model claude-opus-4-6-20260120
        """,
    )
    parser.add_argument(
        "--url",
        type=str,
        default=os.getenv("API_BASE_URL", "http://localhost:3000"),
        help="API Base URL (默认: http://localhost:3000，可用 API_BASE_URL 环境变量)",
    )
    parser.add_argument(
        "--key",
        type=str,
        default=os.getenv("API_KEY", ""),
        help="API Key (可用 API_KEY 环境变量)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-20250514",
        help="模型名称 (默认: claude-sonnet-4-20250514)",
    )
    parser.add_argument(
        "--test",
        type=str,
        choices=["short", "long", "compare", "all"],
        default="all",
        help="运行指定测试 (默认: all)",
    )

    args = parser.parse_args()

    if not args.key:
        print_fail("请提供 API Key: --key sk-xxx 或设置 API_KEY 环境变量")
        return

    print_header("Claude 200K 分段计费验证")
    print_info(f"API Base URL: {args.url}")
    print_info(f"Model: {args.model}")
    print_info(f"API Key: {args.key[:12]}...")
    print_info(f"Test: {args.test}")
    print()
    print_dim("Claude 200K 计费规则:")
    print_dim("  ≤ 200K input tokens: 正常费率")
    print_dim("  > 200K input tokens: input x2.0, output x1.5")
    print()

    if args.test == "short":
        test_short_request(args.url, args.key, args.model)
    elif args.test == "long":
        test_long_request(args.url, args.key, args.model)
    elif args.test == "compare":
        test_compare_billing(args.url, args.key, args.model)
    elif args.test == "all":
        test_compare_billing(args.url, args.key, args.model)

    print_header("测试完成")


if __name__ == "__main__":
    main()
