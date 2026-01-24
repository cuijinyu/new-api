"""
Claude SDK 测试脚本
使用 Anthropic 官方 SDK 调用 ezmodel 的 Claude 模型
"""

import anthropic
import httpx
import requests
import json
import time
import argparse
from typing import Optional


def create_client(base_url: str, api_key: str) -> anthropic.Anthropic:
    """创建自定义 HTTP 客户端的 Anthropic Client，避免被 WAF 拦截"""
    # 自定义 httpx 客户端，修改 User-Agent 等请求头
    custom_http_client = httpx.Client(
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
        timeout=60.0,
    )
    
    return anthropic.Anthropic(
        api_key=api_key,
        base_url=base_url,
        http_client=custom_http_client,
    )

# 配置颜色输出
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*50}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*50}{Colors.ENDC}\n")


def print_success(text: str):
    print(f"{Colors.OKGREEN}✅ {text}{Colors.ENDC}")


def print_fail(text: str):
    print(f"{Colors.FAIL}❌ {text}{Colors.ENDC}")


def print_info(text: str):
    print(f"{Colors.OKBLUE}ℹ️  {text}{Colors.ENDC}")


def test_basic_message(client: anthropic.Anthropic, model: str) -> bool:
    """测试基本的消息请求（非流式）"""
    print_header("测试 1: 基本消息请求（非流式）")
    
    try:
        start_time = time.time()
        
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[
                {"role": "user", "content": "Hello! Please introduce yourself in one sentence."}
            ]
        )
        
        latency = time.time() - start_time
        
        print_info(f"模型: {message.model}")
        print_info(f"停止原因: {message.stop_reason}")
        print_info(f"输入 tokens: {message.usage.input_tokens}")
        print_info(f"输出 tokens: {message.usage.output_tokens}")
        print_info(f"延迟: {latency:.3f}s")
        print(f"\n{Colors.BOLD}响应内容:{Colors.ENDC}")
        print(f"{message.content[0].text}\n")
        
        print_success("基本消息请求测试通过！")
        return True
        
    except anthropic.APIStatusError as e:
        print_fail(f"基本消息请求测试失败:")
        print_fail(f"  状态码: {e.status_code}")
        print_fail(f"  错误信息: {e.message}")
        if hasattr(e, 'body'):
            print_fail(f"  响应体: {e.body}")
        if hasattr(e, 'response'):
            print_fail(f"  响应头: {dict(e.response.headers)}")
            try:
                print_fail(f"  原始响应: {e.response.text}")
            except:
                pass
        # 打印所有可用属性
        print_fail(f"  错误属性: {[attr for attr in dir(e) if not attr.startswith('_')]}")
        return False
    except Exception as e:
        print_fail(f"基本消息请求测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_streaming_message(client: anthropic.Anthropic, model: str) -> bool:
    """测试流式消息请求"""
    print_header("测试 2: 流式消息请求")
    
    try:
        start_time = time.time()
        first_token_time = None
        full_response = ""
        
        print(f"{Colors.BOLD}流式响应:{Colors.ENDC}")
        
        with client.messages.stream(
            model=model,
            max_tokens=1024,
            messages=[
                {"role": "user", "content": "Write a short 4-line poem about coding."}
            ]
        ) as stream:
            for text in stream.text_stream:
                if first_token_time is None:
                    first_token_time = time.time()
                print(text, end="", flush=True)
                full_response += text
        
        print("\n")
        
        total_latency = time.time() - start_time
        ttfb = first_token_time - start_time if first_token_time else 0
        
        # 获取最终的消息对象以获取 usage 信息
        final_message = stream.get_final_message()
        
        print_info(f"首字节延迟 (TTFB): {ttfb:.3f}s")
        print_info(f"总延迟: {total_latency:.3f}s")
        print_info(f"输入 tokens: {final_message.usage.input_tokens}")
        print_info(f"输出 tokens: {final_message.usage.output_tokens}")
        
        print_success("流式消息请求测试通过！")
        return True
        
    except anthropic.APIStatusError as e:
        print_fail(f"流式消息请求测试失败:")
        print_fail(f"  状态码: {e.status_code}")
        print_fail(f"  错误信息: {e.message}")
        if hasattr(e, 'body'):
            print_fail(f"  响应体: {e.body}")
        if hasattr(e, 'response'):
            print_fail(f"  响应头: {dict(e.response.headers)}")
        return False
    except Exception as e:
        print_fail(f"流式消息请求测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multi_turn_conversation(client: anthropic.Anthropic, model: str) -> bool:
    """测试多轮对话"""
    print_header("测试 3: 多轮对话")
    
    try:
        messages = []
        
        # 第一轮
        messages.append({"role": "user", "content": "I want to learn Python. Give me 3 tips."})
        
        response1 = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=messages
        )
        
        assistant_response1 = response1.content[0].text
        messages.append({"role": "assistant", "content": assistant_response1})
        
        print(f"{Colors.BOLD}用户:{Colors.ENDC} {messages[0]['content']}")
        print(f"{Colors.BOLD}助手:{Colors.ENDC} {assistant_response1[:200]}...\n")
        
        # 第二轮
        messages.append({"role": "user", "content": "Can you elaborate on the first tip?"})
        
        response2 = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=messages
        )
        
        assistant_response2 = response2.content[0].text
        
        print(f"{Colors.BOLD}用户:{Colors.ENDC} {messages[2]['content']}")
        print(f"{Colors.BOLD}助手:{Colors.ENDC} {assistant_response2[:200]}...\n")
        
        total_input = response1.usage.input_tokens + response2.usage.input_tokens
        total_output = response1.usage.output_tokens + response2.usage.output_tokens
        
        print_info(f"总输入 tokens: {total_input}")
        print_info(f"总输出 tokens: {total_output}")
        
        print_success("多轮对话测试通过！")
        return True
        
    except anthropic.APIStatusError as e:
        print_fail(f"多轮对话测试失败: {e.status_code} - {e.message}")
        return False
    except Exception as e:
        print_fail(f"多轮对话测试失败: {type(e).__name__}: {e}")
        return False


def test_system_prompt(client: anthropic.Anthropic, model: str) -> bool:
    """测试系统提示词"""
    print_header("测试 4: 系统提示词")
    
    try:
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            system="You are a friendly pirate. Speak like a pirate.",
            messages=[
                {"role": "user", "content": "How is the weather today?"}
            ]
        )
        
        print(f"{Colors.BOLD}系统提示词:{Colors.ENDC} You are a friendly pirate. Speak like a pirate.")
        print(f"{Colors.BOLD}用户:{Colors.ENDC} How is the weather today?")
        print(f"{Colors.BOLD}助手:{Colors.ENDC} {message.content[0].text}\n")
        
        print_info(f"输入 tokens: {message.usage.input_tokens}")
        print_info(f"输出 tokens: {message.usage.output_tokens}")
        
        print_success("系统提示词测试通过！")
        return True
        
    except anthropic.APIStatusError as e:
        print_fail(f"系统提示词测试失败: {e.status_code} - {e.message}")
        return False
    except Exception as e:
        print_fail(f"系统提示词测试失败: {type(e).__name__}: {e}")
        return False


def test_long_context(client: anthropic.Anthropic, model: str) -> bool:
    """测试长上下文处理"""
    print_header("测试 5: 长上下文处理")
    
    try:
        # 生成较长的输入文本
        long_text = """
        The history of artificial intelligence (AI) dates back to the 1950s. 
        In 1956, at the Dartmouth Conference, the term "artificial intelligence" was first coined.
        
        Early AI research focused on symbolic reasoning and expert systems. Notable achievements include:
        1. ELIZA - an early natural language processing program
        2. SHRDLU - a natural language understanding system
        3. Expert systems like MYCIN for medical diagnosis
        
        However, due to computational limitations and algorithmic constraints, AI experienced two "AI winters" 
        in the 1970s and 1980s.
        
        In the 21st century, with the development of big data, cloud computing, and deep learning, 
        AI has experienced a renaissance. The breakthrough performance of AlexNet in the 2012 ImageNet 
        competition marked the beginning of the deep learning era.
        
        Recently, large language models (LLMs) have sparked a new AI revolution. Models like GPT and Claude 
        demonstrate powerful language understanding and generation capabilities, transforming how we interact 
        with technology.
        """ * 3  # 重复3次增加长度
        
        start_time = time.time()
        
        message = client.messages.create(
            model=model,
            max_tokens=512,
            messages=[
                {"role": "user", "content": f"Please read the following article and summarize it in 3 sentences:\n\n{long_text}"}
            ]
        )
        
        latency = time.time() - start_time
        
        print(f"{Colors.BOLD}输入文本长度:{Colors.ENDC} {len(long_text)} 字符")
        print(f"{Colors.BOLD}摘要:{Colors.ENDC}")
        print(f"{message.content[0].text}\n")
        
        print_info(f"输入 tokens: {message.usage.input_tokens}")
        print_info(f"输出 tokens: {message.usage.output_tokens}")
        print_info(f"延迟: {latency:.3f}s")
        
        print_success("长上下文处理测试通过！")
        return True
        
    except anthropic.APIStatusError as e:
        print_fail(f"长上下文处理测试失败: {e.status_code} - {e.message}")
        return False
    except Exception as e:
        print_fail(f"长上下文处理测试失败: {type(e).__name__}: {e}")
        return False


def test_temperature(client: anthropic.Anthropic, model: str) -> bool:
    """测试温度参数"""
    print_header("测试 6: 温度参数对比")
    
    try:
        prompt = "Describe the color of the sky in one word."
        
        # 低温度（更确定性）
        response_low = client.messages.create(
            model=model,
            max_tokens=50,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # 高温度（更随机）
        response_high = client.messages.create(
            model=model,
            max_tokens=50,
            temperature=1.0,
            messages=[{"role": "user", "content": prompt}]
        )
        
        print(f"{Colors.BOLD}提示词:{Colors.ENDC} {prompt}\n")
        print(f"{Colors.BOLD}温度 0.0 响应:{Colors.ENDC} {response_low.content[0].text}")
        print(f"{Colors.BOLD}温度 1.0 响应:{Colors.ENDC} {response_high.content[0].text}\n")
        
        print_success("温度参数测试通过！")
        return True
        
    except anthropic.APIStatusError as e:
        print_fail(f"温度参数测试失败: {e.status_code} - {e.message}")
        return False
    except Exception as e:
        print_fail(f"温度参数测试失败: {type(e).__name__}: {e}")
        return False


def test_raw_http_request(base_url: str, api_key: str, model: str) -> bool:
    """使用原始 HTTP 请求测试，用于诊断问题"""
    print_header("测试 0: 原始 HTTP 请求诊断")
    
    url = f"{base_url}/messages"
    
    # 测试两种认证方式
    auth_methods = [
        ("x-api-key (Claude原生)", {"x-api-key": api_key, "anthropic-version": "2023-06-01"}),
        ("Authorization Bearer (OpenAI兼容)", {"Authorization": f"Bearer {api_key}"}),
    ]
    
    payload = {
        "model": model,
        "max_tokens": 100,
        "messages": [
            {"role": "user", "content": "Say hello"}
        ]
    }
    
    success = False
    for auth_name, auth_headers in auth_methods:
        print(f"\n{Colors.BOLD}尝试认证方式: {auth_name}{Colors.ENDC}")
        
        headers = {
            "Content-Type": "application/json",
            **auth_headers
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            print_info(f"状态码: {response.status_code}")
            print_info(f"响应头: {dict(response.headers)}")
            
            try:
                resp_json = response.json()
                print_info(f"响应体: {json.dumps(resp_json, ensure_ascii=False, indent=2)}")
            except:
                print_info(f"响应体 (文本): {response.text[:500]}")
            
            if response.status_code == 200:
                print_success(f"认证方式 {auth_name} 成功！")
                success = True
            else:
                print_fail(f"认证方式 {auth_name} 失败")
                
        except Exception as e:
            print_fail(f"请求异常: {e}")
    
    # 测试模拟 SDK 请求头
    print(f"\n{Colors.BOLD}测试模拟 Anthropic SDK 请求头:{Colors.ENDC}")
    sdk_headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "User-Agent": f"anthropic-python/0.76.0",  # SDK 默认 User-Agent
        "Accept": "application/json",
    }
    print_info(f"请求头: {sdk_headers}")
    try:
        response = requests.post(url, json=payload, headers=sdk_headers, timeout=30)
        print_info(f"状态码: {response.status_code}")
        if response.status_code == 200:
            print_success("模拟 SDK 请求头成功！")
        else:
            print_fail(f"模拟 SDK 请求头失败: {response.text[:500]}")
    except Exception as e:
        print_fail(f"请求异常: {e}")
    
    return success


def run_all_tests(base_url: str, api_key: str, model: str):
    """运行所有测试"""
    print_header("ezmodel Claude SDK 测试套件")
    print_info(f"API Base URL: {base_url}")
    print_info(f"Model: {model}")
    print_info(f"API Key: {api_key[:10]}..." if len(api_key) > 10 else f"API Key: {api_key}")
    
    # 创建自定义 client（使用修改后的 User-Agent 避免 WAF 拦截）
    client = create_client(base_url, api_key)
    
    results = []
    
    # 运行各项测试
    tests = [
        ("原始HTTP诊断", lambda: test_raw_http_request(base_url, api_key, model)),
        ("基本消息请求", lambda: test_basic_message(client, model)),
        ("流式消息请求", lambda: test_streaming_message(client, model)),
        ("多轮对话", lambda: test_multi_turn_conversation(client, model)),
        ("系统提示词", lambda: test_system_prompt(client, model)),
        ("长上下文处理", lambda: test_long_context(client, model)),
        ("温度参数", lambda: test_temperature(client, model)),
    ]
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print_fail(f"{name} 测试异常: {e}")
            results.append((name, False))
    
    # 打印测试总结
    print_header("测试结果总结")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = f"{Colors.OKGREEN}✅ 通过{Colors.ENDC}" if result else f"{Colors.FAIL}❌ 失败{Colors.ENDC}"
        print(f"  {name}: {status}")
    
    print(f"\n{Colors.BOLD}总计: {passed}/{total} 测试通过{Colors.ENDC}")
    
    if passed == total:
        print(f"\n{Colors.OKGREEN}🎉 所有测试通过！ezmodel Claude 服务运行正常。{Colors.ENDC}")
    else:
        print(f"\n{Colors.WARNING}⚠️ 部分测试失败，请检查配置或服务状态。{Colors.ENDC}")
    
    return passed == total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ezmodel Claude SDK 测试脚本")
    parser.add_argument(
        "--url", 
        type=str, 
        default="https://www.ezmodel.cloud",
        help="API Base URL (默认: https://www.ezmodel.cloud)"
    )
    parser.add_argument(
        "--key", 
        type=str, 
        default="sk-",
        help="API Key"
    )
    parser.add_argument(
        "--model", 
        type=str, 
        default="claude-sonnet-4-20250514",
        help="模型名称 (默认: claude-sonnet-4-20250514)"
    )
    parser.add_argument(
        "--test",
        type=str,
        choices=["basic", "stream", "multi", "system", "long", "temp", "all"],
        default="all",
        help="运行指定测试 (默认: all)"
    )
    
    args = parser.parse_args()
    
    if args.key == "sk-" or not args.key:
        print(f"{Colors.WARNING}⚠️ 警告: 未提供有效的 API Key，请使用 --key 参数指定。{Colors.ENDC}")
    
    # 创建自定义 client（使用修改后的 User-Agent 避免 WAF 拦截）
    client = create_client(args.url, args.key)
    
    if args.test == "all":
        run_all_tests(args.url, args.key, args.model)
    else:
        test_map = {
            "basic": lambda: test_basic_message(client, args.model),
            "stream": lambda: test_streaming_message(client, args.model),
            "multi": lambda: test_multi_turn_conversation(client, args.model),
            "system": lambda: test_system_prompt(client, args.model),
            "long": lambda: test_long_context(client, args.model),
            "temp": lambda: test_temperature(client, args.model),
        }
        test_map[args.test]()
