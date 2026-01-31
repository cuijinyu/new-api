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
from openai import OpenAI

# 配置
BASE_URL = os.getenv('NEW_API_BASE_URL', 'http://localhost:3000')
API_KEY = os.getenv('NEW_API_KEY', 'sk-test')
MODEL = os.getenv('BYTEPLUS_MODEL', 'seed-1-6-250915')

# 初始化客户端
client = OpenAI(
    base_url=f'{BASE_URL}/v1',
    api_key=API_KEY,
)

def print_separator(title: str):
    """打印分隔线"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def print_usage(usage):
    """打印 usage 信息"""
    if usage:
        print(f"  - Input Tokens: {usage.input_tokens}")
        print(f"  - Output Tokens: {usage.output_tokens}")
        print(f"  - Total Tokens: {usage.total_tokens}")
        if hasattr(usage, 'input_tokens_details') and usage.input_tokens_details:
            cached = getattr(usage.input_tokens_details, 'cached_tokens', 0)
            print(f"  - Cached Tokens: {cached}")

def test_basic_responses():
    """测试基本的 Responses API 调用"""
    print_separator("Test 1: Basic Responses API")
    
    try:
        response = client.responses.create(
            model=MODEL,
            input=[
                {"role": "user", "content": "Hello, what is 2+2?"}
            ],
            extra_body={
                "thinking": {"type": "disabled"}
            }
        )
        
        print(f"Response ID: {response.id}")
        print(f"Status: {response.status}")
        if response.output:
            for output in response.output:
                if hasattr(output, 'content') and output.content:
                    for content in output.content:
                        if hasattr(content, 'text'):
                            # 处理可能的编码问题
                            text = content.text[:200].encode('utf-8', errors='replace').decode('utf-8')
                            print(f"Output: {text}...")
        
        print("\nUsage:")
        print_usage(response.usage)
        
        return response
    except Exception as e:
        print(f"Error: {e}")
        return None

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
    try:
        # 第一次请求：启用前缀缓存
        response1 = client.responses.create(
            model=MODEL,
            input=[
                {"role": "system", "content": long_context},
                {"role": "user", "content": "What is the main theme of this story?"}
            ],
            extra_body={
                "caching": {"type": "enabled", "prefix": True},
                "thinking": {"type": "disabled"}
            }
        )
        
        print(f"Response 1 ID: {response1.id}")
        print("\nUsage (First Request):")
        print_usage(response1.usage)
        
        if response1.output:
            for output in response1.output:
                if hasattr(output, 'content') and output.content:
                    for content in output.content:
                        if hasattr(content, 'text'):
                            print(f"\nOutput: {content.text[:300]}...")
        
        # 等待缓存创建 - BytePlus 缓存需要较长时间来处理
        print("\nWaiting for cache to be created (15 seconds)...")
        time.sleep(15)
        
        # 第二次请求：使用 previous_response_id 利用缓存
        print("\nStep 2: Using previous_response_id to leverage cache...")
        response2 = client.responses.create(
            model=MODEL,
            previous_response_id=response1.id,
            input=[
                {"role": "user", "content": "Who are the main characters?"}
            ],
            extra_body={
                "caching": {"type": "enabled"},
                "thinking": {"type": "disabled"}
            }
        )
        
        print(f"Response 2 ID: {response2.id}")
        print("\nUsage (Second Request - Should show cached tokens):")
        print_usage(response2.usage)
        
        if response2.output:
            for output in response2.output:
                if hasattr(output, 'content') and output.content:
                    for content in output.content:
                        if hasattr(content, 'text'):
                            print(f"\nOutput: {content.text[:300]}...")
        
        # 检查缓存命中
        if response2.usage and hasattr(response2.usage, 'input_tokens_details'):
            details = response2.usage.input_tokens_details
            if details and hasattr(details, 'cached_tokens') and details.cached_tokens > 0:
                print(f"\n[OK] Cache HIT! Cached tokens: {details.cached_tokens}")
            else:
                print("\n[WARN] No cache hit detected (cached_tokens = 0)")
        
        return response1, response2
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def test_thinking_mode():
    """测试思考模式配置"""
    print_separator("Test 3: Thinking Mode Configuration")
    
    print("Testing with thinking disabled...")
    try:
        response = client.responses.create(
            model=MODEL,
            input=[
                {"role": "user", "content": "What is the square root of 144?"}
            ],
            extra_body={
                "thinking": {"type": "disabled"}
            }
        )
        
        print(f"Response ID: {response.id}")
        print("\nUsage:")
        print_usage(response.usage)
        
        if response.output:
            for output in response.output:
                if hasattr(output, 'content') and output.content:
                    for content in output.content:
                        if hasattr(content, 'text'):
                            print(f"\nOutput: {content.text}")
        
        return response
    except Exception as e:
        print(f"Error: {e}")
        return None

def test_streaming():
    """测试流式响应"""
    print_separator("Test 4: Streaming Response")
    
    print("Testing streaming with caching...")
    try:
        stream = client.responses.create(
            model=MODEL,
            input=[
                {"role": "user", "content": "Count from 1 to 5."}
            ],
            stream=True,
            extra_body={
                "thinking": {"type": "disabled"}
            }
        )
        
        print("Streaming output:")
        full_text = ""
        for event in stream:
            if hasattr(event, 'type'):
                if event.type == 'response.output_text.delta':
                    if hasattr(event, 'delta'):
                        print(event.delta, end='', flush=True)
                        full_text += event.delta
                elif event.type == 'response.completed':
                    if hasattr(event, 'response') and event.response:
                        print("\n\nFinal Usage:")
                        print_usage(event.response.usage)
        
        print(f"\n\nFull text: {full_text}")
        return True
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

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
