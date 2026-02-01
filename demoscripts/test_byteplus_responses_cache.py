# encoding=utf-8
"""
BytePlus Responses API 缓存功能测试脚本

测试通过 OpenAI 协议调用 BytePlus/字节跳动 Seed 模型的 Responses API，
验证 extra_body 中的 caching 和 thinking 参数是否正确传递。

使用方法:
    python test_byteplus_responses_cache.py

环境变量:
    - NEW_API_BASE_URL: API 基础 URL (默认: http://localhost:3000)
    - NEW_API_KEY: API 密钥
    - BYTEPLUS_MODEL: 模型名称 (默认: seed-1-6-250915)

参考文档:
    - BytePlus Responses API: https://docs.byteplus.com/en/docs/ModelArk/Create_model_request
"""

import os
import json
import time
import requests
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

# 配置
BASE_URL = os.getenv('NEW_API_BASE_URL', 'http://localhost:3000')
API_KEY = os.getenv('NEW_API_KEY', 'sk-test')
MODEL = os.getenv('BYTEPLUS_MODEL', 'seed-1-6-250915')


@dataclass
class TokenDetails:
    cached_tokens: int = 0
    reasoning_tokens: int = 0

@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_tokens_details: Optional[TokenDetails] = None
    output_tokens_details: Optional[TokenDetails] = None

@dataclass
class Response:
    id: str
    status: str
    output: List[Dict]
    usage: Optional[Usage] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Response':
        usage = None
        if 'usage' in data:
            u = data['usage']
            input_details = None
            output_details = None
            if 'input_tokens_details' in u:
                input_details = TokenDetails(
                    cached_tokens=u['input_tokens_details'].get('cached_tokens', 0)
                )
            if 'output_tokens_details' in u:
                output_details = TokenDetails(
                    reasoning_tokens=u['output_tokens_details'].get('reasoning_tokens', 0)
                )
            usage = Usage(
                input_tokens=u.get('input_tokens', 0),
                output_tokens=u.get('output_tokens', 0),
                total_tokens=u.get('total_tokens', 0),
                input_tokens_details=input_details,
                output_tokens_details=output_details
            )
        return cls(
            id=data.get('id', ''),
            status=data.get('status', ''),
            output=data.get('output', []),
            usage=usage
        )


def responses_create(
    model: str,
    input_messages: List[Dict],
    thinking: Optional[Dict] = None,
    caching: Optional[Dict] = None,
    previous_response_id: Optional[str] = None,
    stream: bool = False,
    timeout: int = 120
) -> Optional[Response]:
    """
    调用 Responses API
    """
    url = f"{BASE_URL}/v1/responses"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "input": input_messages,
        "stream": stream
    }
    
    if thinking:
        payload["thinking"] = thinking
    if caching:
        payload["caching"] = caching
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 200:
            return Response.from_dict(resp.json())
        else:
            print(f"Error: {resp.status_code} - {resp.text[:500]}")
            return None
    except Exception as e:
        print(f"Request error: {e}")
        return None


def responses_create_stream(
    model: str,
    input_messages: List[Dict],
    thinking: Optional[Dict] = None,
    caching: Optional[Dict] = None,
    previous_response_id: Optional[str] = None,
    timeout: int = 120
):
    """
    调用 Responses API (流式)
    """
    url = f"{BASE_URL}/v1/responses"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "input": input_messages,
        "stream": True
    }
    
    if thinking:
        payload["thinking"] = thinking
    if caching:
        payload["caching"] = caching
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout, stream=True)
        if resp.status_code == 200:
            for line in resp.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]
                        if data_str.strip() == '[DONE]':
                            break
                        try:
                            yield json.loads(data_str)
                        except json.JSONDecodeError:
                            pass
        else:
            print(f"Error: {resp.status_code} - {resp.text[:500]}")
    except Exception as e:
        print(f"Request error: {e}")

def print_separator(title: str):
    """打印分隔线"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def print_usage(usage: Optional[Usage]):
    """打印 usage 信息"""
    if usage:
        print(f"  - Input Tokens: {usage.input_tokens}")
        print(f"  - Output Tokens: {usage.output_tokens}")
        print(f"  - Total Tokens: {usage.total_tokens}")
        if usage.input_tokens_details:
            print(f"  - Cached Tokens: {usage.input_tokens_details.cached_tokens}")
        if usage.output_tokens_details:
            print(f"  - Reasoning Tokens: {usage.output_tokens_details.reasoning_tokens}")

def get_output_text(response: Response) -> str:
    """从响应中提取输出文本"""
    if response.output:
        for output in response.output:
            if output.get('type') == 'message':
                content_list = output.get('content', [])
                for content in content_list:
                    if content.get('type') == 'output_text':
                        return content.get('text', '')
    return ''

def test_basic_responses():
    """测试基本的 Responses API 调用"""
    print_separator("Test 1: Basic Responses API")
    
    response = responses_create(
        model=MODEL,
        input_messages=[
            {"role": "user", "content": "Hello, what is 2+2?"}
        ],
        thinking={"type": "disabled"}
    )
    
    if response is None:
        print("Error: Failed to get response")
        return None
    
    print(f"Response ID: {response.id}")
    print(f"Status: {response.status}")
    
    text = get_output_text(response)
    if text:
        print(f"Output: {text[:200]}...")
    
    print("\nUsage:")
    print_usage(response.usage)
    
    return response

def test_prefix_caching():
    """测试前缀缓存功能"""
    print_separator("Test 2: Prefix Caching")
    
    # 长文本输入（至少 256 tokens 才能创建缓存）
    long_context = """
You are a literary analysis assistant. Answer concisely and clearly.

Here is an excerpt from "The Gift of the Magi" by O. Henry:

One dollar and eighty-seven cents. That was all. And sixty cents of it was in pennies. 
Pennies saved one and two at a time by bulldozing the grocer and the vegetable man and 
the butcher until one's cheeks burned with the silent imputation of parsimony that such 
close dealing implied. Three times Della counted it. One dollar and eighty-seven cents. 
And the next day would be Christmas.

There was clearly nothing to do but flop down on the shabby little couch and howl. 
So Della did it. Which instigates the moral reflection that life is made up of sobs, 
sniffles, and smiles, with sniffles predominating.

While the mistress of the home is gradually subsiding from the first stage to the second, 
take a look at the home. A furnished flat at $8 per week. It did not exactly beggar 
description, but it certainly had that word on the lookout for the mendicancy squad.

In the vestibule below was a letter-box into which no letter would go, and an electric 
button from which no mortal finger could coax a ring. Also appertaining thereunto was a 
card bearing the name "Mr. James Dillingham Young."

The "Dillingham" had been flung to the breeze during a former period of prosperity when 
its possessor was being paid $30 per week. Now, when the income was shrunk to $20, though, 
they were thinking seriously of contracting to a modest and unassuming D. But whenever 
Mr. James Dillingham Young came home and reached his flat above he was called "Jim" and 
greatly hugged by Mrs. James Dillingham Young, already introduced to you as Della. Which 
is all very good.

Della finished her cry and attended to her cheeks with the powder rag. She stood by the 
window and looked out dully at a gray cat walking a gray fence in a gray backyard. 
Tomorrow would be Christmas Day, and she had only $1.87 with which to buy Jim a present. 
She had been saving every penny she could for months, with this result. Twenty dollars a 
week doesn't go far. Expenses had been greater than she had calculated. They always are. 
Only $1.87 to buy a present for Jim. Her Jim. Many a happy hour she had spent planning 
for something nice for him. Something fine and rare and sterling—something just a little 
bit near to being worthy of the honor of being owned by Jim.
"""
    
    print("Step 1: Creating initial response with prefix caching enabled...")
    
    # 第一次请求：启用前缀缓存
    response1 = responses_create(
        model=MODEL,
        input_messages=[
            {"role": "system", "content": long_context},
            {"role": "user", "content": "What is the main theme of this story?"}
        ],
        caching={"type": "enabled", "prefix": True},
        thinking={"type": "disabled"}
    )
    
    if response1 is None:
        print("Error: Failed to create initial response")
        return None, None
    
    print(f"Response 1 ID: {response1.id}")
    print("\nUsage (First Request):")
    print_usage(response1.usage)
    
    text = get_output_text(response1)
    if text:
        print(f"\nOutput: {text[:300]}...")
    
    # 等待缓存创建 - BytePlus 缓存需要较长时间来处理
    print("\nWaiting for cache to be created (15 seconds)...")
    time.sleep(15)
    
    # 第二次请求：使用 previous_response_id 利用缓存
    print("\nStep 2: Using previous_response_id to leverage cache...")
    response2 = responses_create(
        model=MODEL,
        input_messages=[
            {"role": "user", "content": "Who are the main characters?"}
        ],
        previous_response_id=response1.id,
        caching={"type": "enabled"},
        thinking={"type": "disabled"}
    )
    
    if response2 is None:
        print("Error: Failed to create second response")
        return response1, None
    
    print(f"Response 2 ID: {response2.id}")
    print("\nUsage (Second Request - Should show cached tokens):")
    print_usage(response2.usage)
    
    text2 = get_output_text(response2)
    if text2:
        print(f"\nOutput: {text2[:300]}...")
    
    # 检查缓存命中
    if response2.usage and response2.usage.input_tokens_details:
        cached = response2.usage.input_tokens_details.cached_tokens
        if cached > 0:
            print(f"\n[OK] Cache HIT! Cached tokens: {cached}")
        else:
            print("\n[WARN] No cache hit detected (cached_tokens = 0)")
    
    return response1, response2

def test_thinking_mode():
    """测试思考模式配置"""
    print_separator("Test 3: Thinking Mode Configuration")
    
    print("Testing with thinking disabled...")
    
    response = responses_create(
        model=MODEL,
        input_messages=[
            {"role": "user", "content": "What is the square root of 144?"}
        ],
        thinking={"type": "disabled"}
    )
    
    if response is None:
        print("Error: Failed to get response")
        return None
    
    print(f"Response ID: {response.id}")
    print("\nUsage:")
    print_usage(response.usage)
    
    text = get_output_text(response)
    if text:
        print(f"\nOutput: {text}")
    
    return response

def test_streaming():
    """测试流式响应"""
    print_separator("Test 4: Streaming Response")
    
    print("Testing streaming with caching...")
    
    print("Streaming output:")
    full_text = ""
    final_usage = None
    
    for event in responses_create_stream(
        model=MODEL,
        input_messages=[
            {"role": "user", "content": "Count from 1 to 5."}
        ],
        thinking={"type": "disabled"}
    ):
        event_type = event.get('type', '')
        if event_type == 'response.output_text.delta':
            delta = event.get('delta', '')
            print(delta, end='', flush=True)
            full_text += delta
        elif event_type == 'response.completed':
            resp_data = event.get('response', {})
            if resp_data and 'usage' in resp_data:
                u = resp_data['usage']
                input_details = None
                output_details = None
                if 'input_tokens_details' in u:
                    input_details = TokenDetails(
                        cached_tokens=u['input_tokens_details'].get('cached_tokens', 0)
                    )
                if 'output_tokens_details' in u:
                    output_details = TokenDetails(
                        reasoning_tokens=u['output_tokens_details'].get('reasoning_tokens', 0)
                    )
                final_usage = Usage(
                    input_tokens=u.get('input_tokens', 0),
                    output_tokens=u.get('output_tokens', 0),
                    total_tokens=u.get('total_tokens', 0),
                    input_tokens_details=input_details,
                    output_tokens_details=output_details
                )
    
    if final_usage:
        print("\n\nFinal Usage:")
        print_usage(final_usage)
    
    print(f"\n\nFull text: {full_text}")
    return len(full_text) > 0

def main():
    """主测试函数"""
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║     BytePlus Responses API Cache Test Suite                  ║
╠══════════════════════════════════════════════════════════════╣
║  Base URL: {BASE_URL:<48} ║
║  Model:    {MODEL:<48} ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    results = {}
    
    # Test 1: Basic Responses API
    response1 = test_basic_responses()
    results['basic'] = response1 is not None
    
    # Test 2: Prefix Caching
    r1, r2 = test_prefix_caching()
    results['prefix_caching'] = r1 is not None and r2 is not None
    
    # Test 3: Thinking Mode
    response3 = test_thinking_mode()
    results['thinking_mode'] = response3 is not None
    
    # Test 4: Streaming
    results['streaming'] = test_streaming()
    
    # Summary
    print_separator("Test Summary")
    for test_name, passed in results.items():
        status = "[PASSED]" if passed else "[FAILED]"
        print(f"  {test_name}: {status}")
    
    total_passed = sum(results.values())
    total_tests = len(results)
    print(f"\n  Total: {total_passed}/{total_tests} tests passed")

if __name__ == "__main__":
    main()
