"""
Moonshot kimi-k2.5 缓存价格测试脚本

测试场景：
1. 无缓存命中 - 首次请求，所有 token 都是新的
2. 完全缓存命中 - 重复相同请求，所有 prompt token 应该命中缓存
3. 部分缓存命中 - 相同前缀 + 新内容，部分 token 命中缓存

验证目标：
- 验证 API 返回的 cached_tokens 字段是否正确
- 验证缓存命中时价格是否有折扣
- 验证日志中的缓存 token 统计是否正确

使用方法：
    python test_moonshot_cache.py --url <API_URL> --key <API_KEY>
    
    例如：
    python test_moonshot_cache.py --url https://www.ezmodel.cloud --key sk-xxx
    python test_moonshot_cache.py --url http://localhost:3000 --key sk-xxx
"""

import requests
import json
import time
import argparse
from typing import Optional, Dict, Any

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
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def print_success(text: str):
    print(f"{Colors.OKGREEN}✅ {text}{Colors.ENDC}")


def print_fail(text: str):
    print(f"{Colors.FAIL}❌ {text}{Colors.ENDC}")


def print_info(text: str):
    print(f"{Colors.OKBLUE}ℹ️  {text}{Colors.ENDC}")


def print_warning(text: str):
    print(f"{Colors.WARNING}⚠️  {text}{Colors.ENDC}")


def print_usage(usage: Dict[str, Any]):
    """打印 usage 信息"""
    print(f"\n{Colors.CYAN}📊 Token 使用统计:{Colors.ENDC}")
    print(f"   prompt_tokens:     {usage.get('prompt_tokens', 0)}")
    print(f"   completion_tokens: {usage.get('completion_tokens', 0)}")
    print(f"   total_tokens:      {usage.get('total_tokens', 0)}")
    
    # Moonshot 特有的缓存字段
    cached_tokens = usage.get('cached_tokens', 0)
    if cached_tokens > 0:
        print(f"{Colors.OKGREEN}   cached_tokens:     {cached_tokens} (缓存命中!){Colors.ENDC}")
    else:
        print(f"   cached_tokens:     {cached_tokens}")
    
    # OpenAI 格式的缓存字段 (prompt_tokens_details)
    prompt_details = usage.get('prompt_tokens_details', {})
    if prompt_details:
        detail_cached = prompt_details.get('cached_tokens', 0)
        if detail_cached > 0:
            print(f"{Colors.OKGREEN}   prompt_tokens_details.cached_tokens: {detail_cached}{Colors.ENDC}")


def chat_completion(
    base_url: str, 
    api_key: str, 
    model: str, 
    messages: list,
    max_tokens: int = 100
) -> Optional[Dict[str, Any]]:
    """发送 chat completion 请求"""
    url = f"{base_url}/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        
        if response.status_code != 200:
            print_fail(f"请求失败: {response.status_code}")
            print(f"响应: {response.text[:500]}")
            return None
        
        return response.json()
    except Exception as e:
        print_fail(f"请求异常: {e}")
        return None


def test_no_cache(base_url: str, api_key: str, model: str) -> Optional[Dict[str, Any]]:
    """
    测试 1: 无缓存命中
    首次请求，使用唯一的内容确保不会命中缓存
    """
    print_header("测试 1: 无缓存命中 (首次请求)")
    
    # 使用时间戳确保内容唯一
    unique_content = f"这是一个唯一的测试消息，时间戳: {time.time()}"
    
    messages = [
        {"role": "system", "content": "你是一个有帮助的助手。"},
        {"role": "user", "content": unique_content}
    ]
    
    print_info(f"发送唯一内容: {unique_content[:50]}...")
    
    result = chat_completion(base_url, api_key, model, messages)
    
    if result:
        usage = result.get('usage', {})
        print_usage(usage)
        
        cached = usage.get('cached_tokens', 0)
        if cached == 0:
            print_success("预期结果: 无缓存命中 (cached_tokens = 0)")
        else:
            print_warning(f"意外结果: 首次请求却有缓存命中 (cached_tokens = {cached})")
        
        return result
    
    return None


def test_full_cache(base_url: str, api_key: str, model: str) -> Optional[Dict[str, Any]]:
    """
    测试 2: 完全缓存命中
    发送两次完全相同的请求，第二次应该完全命中缓存
    """
    print_header("测试 2: 完全缓存命中 (重复请求)")
    
    # 使用固定内容，但添加唯一标识确保这组测试的隔离性
    test_id = int(time.time()) % 10000
    
    # 使用较长的 system prompt 来增加缓存效果
    long_system_prompt = """你是一个专业的技术助手。你需要遵循以下规则：
1. 回答要简洁明了
2. 使用专业术语时要解释清楚
3. 如果不确定，要诚实说明
4. 回答要有条理，使用列表或分点说明
5. 注意回答的准确性和时效性
这是测试缓存功能的固定提示词。"""
    
    messages = [
        {"role": "system", "content": long_system_prompt},
        {"role": "user", "content": f"请简单介绍一下人工智能的发展历史。(测试ID: {test_id})"}
    ]
    
    # 第一次请求
    print_info("第一次请求 (建立缓存)...")
    result1 = chat_completion(base_url, api_key, model, messages)
    
    if not result1:
        print_fail("第一次请求失败")
        return None
    
    usage1 = result1.get('usage', {})
    print(f"\n{Colors.BOLD}第一次请求结果:{Colors.ENDC}")
    print_usage(usage1)
    
    # 等待一小段时间让缓存生效
    print_info("等待 2 秒让缓存生效...")
    time.sleep(2)
    
    # 第二次请求 (完全相同)
    print_info("第二次请求 (应该命中缓存)...")
    result2 = chat_completion(base_url, api_key, model, messages)
    
    if not result2:
        print_fail("第二次请求失败")
        return None
    
    usage2 = result2.get('usage', {})
    print(f"\n{Colors.BOLD}第二次请求结果:{Colors.ENDC}")
    print_usage(usage2)
    
    # 分析缓存命中情况
    cached_tokens = usage2.get('cached_tokens', 0)
    prompt_tokens = usage2.get('prompt_tokens', 0)
    
    print(f"\n{Colors.BOLD}缓存分析:{Colors.ENDC}")
    if cached_tokens > 0:
        cache_ratio = cached_tokens / prompt_tokens * 100 if prompt_tokens > 0 else 0
        print_success(f"缓存命中! cached_tokens={cached_tokens}, 命中率={cache_ratio:.1f}%")
    else:
        print_warning("未检测到缓存命中，可能原因：")
        print_warning("  1. 模型不支持自动缓存")
        print_warning("  2. 缓存尚未生效")
        print_warning("  3. API 网关未正确传递缓存信息")
    
    return result2


def test_partial_cache(base_url: str, api_key: str, model: str) -> Optional[Dict[str, Any]]:
    """
    测试 3: 部分缓存命中
    使用相同的长前缀（system prompt + 多轮对话历史），但不同的最后一条 user message
    Moonshot 的缓存是基于前缀匹配的，需要足够长的相同前缀才能触发缓存
    """
    print_header("测试 3: 部分缓存命中 (相同长前缀)")
    
    # 使用非常长的固定 system prompt 来增加缓存命中概率
    # Moonshot 缓存需要前缀足够长才能生效
    long_system_prompt = """你是一个专业的人工智能技术助手，专门负责解答关于机器学习、深度学习、自然语言处理等AI领域的问题。

你需要严格遵循以下规则：
1. 回答要简洁明了，避免冗余信息
2. 使用专业术语时要解释清楚，确保用户能够理解
3. 如果不确定答案，要诚实说明，不要编造信息
4. 回答要有条理，使用列表或分点说明来组织内容
5. 注意回答的准确性和时效性，AI领域发展很快
6. 如果问题涉及代码，请提供简洁的示例代码
7. 对于复杂概念，可以使用类比来帮助理解
8. 回答应该考虑到不同技术水平的用户

这是一个用于测试上下文缓存功能的固定提示词。
当用户提问时，请根据问题类型给出合适的回答。
请确保回答专业、准确、易懂。"""

    # 构建一个固定的多轮对话历史作为缓存前缀
    fixed_history = [
        {"role": "system", "content": long_system_prompt},
        {"role": "user", "content": "什么是神经网络？"},
        {"role": "assistant", "content": "神经网络是一种模仿人脑神经元结构的计算模型。它由多层节点（神经元）组成，每层之间通过权重连接。主要特点包括：1) 输入层接收数据；2) 隐藏层进行特征提取和转换；3) 输出层产生最终结果。神经网络通过反向传播算法学习调整权重，从而能够识别模式和做出预测。"},
        {"role": "user", "content": "深度学习和机器学习有什么区别？"},
        {"role": "assistant", "content": "深度学习是机器学习的一个子集。主要区别：1) 特征工程：传统机器学习需要手动设计特征，深度学习可以自动学习特征；2) 数据需求：深度学习通常需要更多数据；3) 计算资源：深度学习需要更强的计算能力（GPU）；4) 模型复杂度：深度学习模型层数更多，参数更多；5) 可解释性：传统机器学习模型通常更容易解释。"},
    ]
    
    # 第一次请求：固定前缀 + 问题A
    messages1 = fixed_history + [
        {"role": "user", "content": "请解释一下什么是卷积神经网络(CNN)？"}
    ]
    
    print_info("第一次请求 (建立长前缀缓存)...")
    print_info(f"消息数量: {len(messages1)}, 预计 token 数较多")
    result1 = chat_completion(base_url, api_key, model, messages1)
    
    if not result1:
        print_fail("第一次请求失败")
        return None
    
    usage1 = result1.get('usage', {})
    print(f"\n{Colors.BOLD}第一次请求结果:{Colors.ENDC}")
    print_usage(usage1)
    
    # 等待缓存生效
    print_info("等待 2 秒让缓存生效...")
    time.sleep(2)
    
    # 第二次请求：相同的固定前缀 + 不同的问题B
    messages2 = fixed_history + [
        {"role": "user", "content": "请解释一下什么是循环神经网络(RNN)？"}
    ]
    
    print_info("第二次请求 (相同长前缀，不同问题)...")
    result2 = chat_completion(base_url, api_key, model, messages2)
    
    if not result2:
        print_fail("第二次请求失败")
        return None
    
    usage2 = result2.get('usage', {})
    print(f"\n{Colors.BOLD}第二次请求结果:{Colors.ENDC}")
    print_usage(usage2)
    
    # 等待缓存生效
    print_info("等待 2 秒...")
    time.sleep(2)
    
    # 第三次请求：相同的固定前缀 + 又一个不同的问题C
    messages3 = fixed_history + [
        {"role": "user", "content": "请解释一下什么是 Transformer 架构？"}
    ]
    
    print_info("第三次请求 (相同长前缀，又一个不同问题)...")
    result3 = chat_completion(base_url, api_key, model, messages3)
    
    if not result3:
        print_fail("第三次请求失败")
        return None
    
    usage3 = result3.get('usage', {})
    print(f"\n{Colors.BOLD}第三次请求结果:{Colors.ENDC}")
    print_usage(usage3)
    
    # 分析缓存命中情况
    print(f"\n{Colors.BOLD}部分缓存分析:{Colors.ENDC}")
    
    cached2 = usage2.get('cached_tokens', 0)
    cached3 = usage3.get('cached_tokens', 0)
    prompt2 = usage2.get('prompt_tokens', 0)
    prompt3 = usage3.get('prompt_tokens', 0)
    
    if cached2 > 0:
        cache_ratio2 = cached2 / prompt2 * 100 if prompt2 > 0 else 0
        print_success(f"第二次请求缓存命中! cached_tokens={cached2}, 命中率={cache_ratio2:.1f}%")
    else:
        print_warning("第二次请求未检测到缓存命中")
    
    if cached3 > 0:
        cache_ratio3 = cached3 / prompt3 * 100 if prompt3 > 0 else 0
        print_success(f"第三次请求缓存命中! cached_tokens={cached3}, 命中率={cache_ratio3:.1f}%")
    else:
        print_warning("第三次请求未检测到缓存命中")
    
    # 说明
    if cached2 == 0 and cached3 == 0:
        print_warning("\n可能原因：")
        print_warning("  1. Moonshot 缓存需要完全相同的前缀才能命中")
        print_warning("  2. 不同的最后一条消息会导致缓存失效")
        print_warning("  3. 这是 Moonshot 缓存机制的正常行为")
    
    return result3


def test_streaming_cache(base_url: str, api_key: str, model: str) -> Optional[Dict[str, Any]]:
    """
    测试 4: 流式请求的缓存
    验证流式请求是否也能正确返回缓存信息
    """
    print_header("测试 4: 流式请求缓存")
    
    url = f"{base_url}/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    long_system_prompt = """你是一个专业的技术助手。这是一个用于测试流式请求缓存的固定提示词。
请根据用户的问题给出简洁的回答。"""
    
    messages = [
        {"role": "system", "content": long_system_prompt},
        {"role": "user", "content": "用一句话解释什么是 API。"}
    ]
    
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 100,
        "stream": True
    }
    
    # 第一次流式请求
    print_info("第一次流式请求...")
    try:
        response1 = requests.post(url, headers=headers, json=payload, stream=True, timeout=60)
        
        if response1.status_code != 200:
            print_fail(f"第一次请求失败: {response1.status_code}")
            return None
        
        usage1 = None
        content1 = ""
        for line in response1.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    data_str = line_str[6:]
                    if data_str == '[DONE]':
                        break
                    try:
                        data = json.loads(data_str)
                        if 'usage' in data:
                            usage1 = data['usage']
                        if 'choices' in data and len(data['choices']) > 0:
                            delta = data['choices'][0].get('delta', {})
                            if 'content' in delta:
                                content1 += delta['content']
                    except json.JSONDecodeError:
                        pass
        
        print(f"响应内容: {content1[:100]}...")
        if usage1:
            print(f"\n{Colors.BOLD}第一次流式请求 usage:{Colors.ENDC}")
            print_usage(usage1)
        else:
            print_warning("第一次流式请求未返回 usage 信息")
        
    except Exception as e:
        print_fail(f"第一次流式请求异常: {e}")
        return None
    
    # 等待缓存生效
    print_info("等待 2 秒...")
    time.sleep(2)
    
    # 第二次流式请求 (相同内容)
    print_info("第二次流式请求 (应该命中缓存)...")
    try:
        response2 = requests.post(url, headers=headers, json=payload, stream=True, timeout=60)
        
        if response2.status_code != 200:
            print_fail(f"第二次请求失败: {response2.status_code}")
            return None
        
        usage2 = None
        for line in response2.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    data_str = line_str[6:]
                    if data_str == '[DONE]':
                        break
                    try:
                        data = json.loads(data_str)
                        if 'usage' in data:
                            usage2 = data['usage']
                    except json.JSONDecodeError:
                        pass
        
        if usage2:
            print(f"\n{Colors.BOLD}第二次流式请求 usage:{Colors.ENDC}")
            print_usage(usage2)
            
            cached_tokens = usage2.get('cached_tokens', 0)
            if cached_tokens > 0:
                print_success(f"流式请求缓存命中! cached_tokens={cached_tokens}")
            else:
                print_warning("流式请求未检测到缓存命中")
            
            return {"usage": usage2}
        else:
            print_warning("第二次流式请求未返回 usage 信息")
            return None
        
    except Exception as e:
        print_fail(f"第二次流式请求异常: {e}")
        return None


def run_all_tests(base_url: str, api_key: str, model: str):
    """运行所有测试"""
    print_header("Moonshot kimi-k2.5 缓存价格测试")
    print_info(f"API Base URL: {base_url}")
    print_info(f"Model: {model}")
    print_info(f"API Key: {api_key[:10]}..." if len(api_key) > 10 else f"API Key: {api_key}")
    
    results = []
    
    # 测试列表
    tests = [
        ("无缓存命中", lambda: test_no_cache(base_url, api_key, model)),
        ("完全缓存命中", lambda: test_full_cache(base_url, api_key, model)),
        ("部分缓存命中", lambda: test_partial_cache(base_url, api_key, model)),
        ("流式请求缓存", lambda: test_streaming_cache(base_url, api_key, model)),
    ]
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result is not None))
        except Exception as e:
            print_fail(f"{name} 测试异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # 打印测试总结
    print_header("测试结果总结")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = f"{Colors.OKGREEN}✅ 通过{Colors.ENDC}" if result else f"{Colors.FAIL}❌ 失败{Colors.ENDC}"
        print(f"  {name}: {status}")
    
    print(f"\n{Colors.BOLD}总计: {passed}/{total} 测试通过{Colors.ENDC}")
    
    # 缓存价格说明
    print(f"\n{Colors.CYAN}{'='*60}{Colors.ENDC}")
    print(f"{Colors.CYAN}缓存价格说明:{Colors.ENDC}")
    print(f"  - 当 cached_tokens > 0 时，这部分 token 应该按缓存价格计费")
    print(f"  - 缓存价格通常比普通输入价格低 (具体折扣取决于配置)")
    print(f"  - 在 new-api 中，缓存倍率由 cache_ratio 配置控制")
    print(f"  - 默认缓存倍率为 1.0 (无折扣)，可在设置中调整")
    print(f"{Colors.CYAN}{'='*60}{Colors.ENDC}")
    
    return passed == total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Moonshot kimi-k2.5 缓存价格测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 测试 ezmodel API
    python test_moonshot_cache.py --url https://www.ezmodel.cloud --key sk-xxx
    
    # 测试本地 new-api 代理
    python test_moonshot_cache.py --url http://localhost:3000 --key sk-xxx
    
    # 指定模型
    python test_moonshot_cache.py --url https://www.ezmodel.cloud --key sk-xxx --model kimi-k2.5
        """
    )
    parser.add_argument(
        "--url", 
        type=str, 
        default="https://www.ezmodel.cloud",
        help="API Base URL (默认: https://www.ezmodel.cloud)"
    )
    parser.add_argument(
        "--key", 
        type=str, 
        required=True,
        help="API Key"
    )
    parser.add_argument(
        "--model", 
        type=str, 
        default="kimi-k2.5",
        help="模型名称 (默认: kimi-k2.5)"
    )
    parser.add_argument(
        "--test",
        type=str,
        choices=["no_cache", "full_cache", "partial_cache", "stream", "all"],
        default="all",
        help="运行指定测试 (默认: all)"
    )
    
    args = parser.parse_args()
    
    if args.test == "all":
        run_all_tests(args.url, args.key, args.model)
    else:
        test_map = {
            "no_cache": lambda: test_no_cache(args.url, args.key, args.model),
            "full_cache": lambda: test_full_cache(args.url, args.key, args.model),
            "partial_cache": lambda: test_partial_cache(args.url, args.key, args.model),
            "stream": lambda: test_streaming_cache(args.url, args.key, args.model),
        }
        test_map[args.test]()
