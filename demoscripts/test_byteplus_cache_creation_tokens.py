# encoding=utf-8
"""
BytePlus 缓存写入 Token 解析验证脚本

验证 cache_creation_input_tokens 字段是否正确解析和返回

使用方法:
    python test_byteplus_cache_creation_tokens.py

环境变量:
    - NEW_API_BASE_URL: API 基础 URL (默认: http://localhost:3000)
    - NEW_API_KEY: API 密钥
    - BYTEPLUS_MODEL: 模型名称 (默认: seed-1-6-250915)
"""

import os
import json
import time
import requests
from typing import Optional, Dict, Any

# 配置
BASE_URL = os.getenv('NEW_API_BASE_URL', 'http://localhost:3000')
API_KEY = os.getenv('NEW_API_KEY', 'sk-test')
MODEL = os.getenv('BYTEPLUS_MODEL', 'seed-1-6-250915')


def print_separator(title: str):
    """打印分隔线"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_usage(usage: Dict[str, Any]):
    """打印 usage 信息"""
    if not usage:
        print("  No usage data")
        return
    
    print(f"  - Input Tokens: {usage.get('input_tokens', 'N/A')}")
    print(f"  - Output Tokens: {usage.get('output_tokens', 'N/A')}")
    print(f"  - Total Tokens: {usage.get('total_tokens', 'N/A')}")
    
    input_details = usage.get('input_tokens_details', {})
    if input_details:
        print(f"  - Input Token Details:")
        print(f"    - Cached Tokens: {input_details.get('cached_tokens', 0)}")
        print(f"    - Cache Creation Tokens: {input_details.get('cache_creation_input_tokens', 0)}")
    
    output_details = usage.get('output_tokens_details', {})
    if output_details:
        print(f"  - Output Token Details:")
        print(f"    - Reasoning Tokens: {output_details.get('reasoning_tokens', 0)}")


def test_responses_api_with_caching():
    """测试 Responses API 缓存功能"""
    print_separator("Test: Responses API with Caching")
    
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
    
    url = f"{BASE_URL}/v1/responses"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 第一次请求：启用前缀缓存
    print("Step 1: Creating initial response with prefix caching enabled...")
    payload1 = {
        "model": MODEL,
        "input": [
            {"role": "system", "content": long_context},
            {"role": "user", "content": "What is the main theme of this story?"}
        ],
        "caching": {"type": "enabled", "prefix": True},
        "thinking": {"type": "disabled"}
    }
    
    try:
        resp1 = requests.post(url, headers=headers, json=payload1, timeout=120)
        print(f"Response 1 Status: {resp1.status_code}")
        
        if resp1.status_code == 200:
            data1 = resp1.json()
            print(f"Response 1 ID: {data1.get('id', 'N/A')}")
            print("\nUsage (First Request - Should show cache_creation_input_tokens):")
            print_usage(data1.get('usage', {}))
            
            # 检查缓存写入 tokens
            usage1 = data1.get('usage', {})
            input_details1 = usage1.get('input_tokens_details', {})
            cache_creation = input_details1.get('cache_creation_input_tokens', 0)
            
            if cache_creation > 0:
                print(f"\n[OK] Cache creation detected! cache_creation_input_tokens: {cache_creation}")
            else:
                print("\n[INFO] No cache_creation_input_tokens in first request (may be expected)")
            
            response_id = data1.get('id')
            
            # 等待缓存创建
            print("\nWaiting for cache to be created (10 seconds)...")
            time.sleep(10)
            
            # 第二次请求：使用 previous_response_id 利用缓存
            print("\nStep 2: Using previous_response_id to leverage cache...")
            payload2 = {
                "model": MODEL,
                "input": [
                    {"role": "user", "content": "Who are the main characters?"}
                ],
                "previous_response_id": response_id,
                "caching": {"type": "enabled"},
                "thinking": {"type": "disabled"}
            }
            
            resp2 = requests.post(url, headers=headers, json=payload2, timeout=120)
            print(f"Response 2 Status: {resp2.status_code}")
            
            if resp2.status_code == 200:
                data2 = resp2.json()
                print(f"Response 2 ID: {data2.get('id', 'N/A')}")
                print("\nUsage (Second Request - Should show cached_tokens):")
                print_usage(data2.get('usage', {}))
                
                # 检查缓存命中
                usage2 = data2.get('usage', {})
                input_details2 = usage2.get('input_tokens_details', {})
                cached_tokens = input_details2.get('cached_tokens', 0)
                
                if cached_tokens > 0:
                    print(f"\n[OK] Cache HIT! cached_tokens: {cached_tokens}")
                else:
                    print("\n[WARN] No cache hit detected (cached_tokens = 0)")
            else:
                print(f"Error: {resp2.text[:500]}")
        else:
            print(f"Error: {resp1.text[:500]}")
    except Exception as e:
        print(f"Request error: {e}")


def test_mock_response_parsing():
    """测试模拟响应解析（不需要实际 API 调用）"""
    print_separator("Test: Mock Response Parsing")
    
    # 模拟 BytePlus API 响应
    mock_response = {
        "id": "resp_test_123",
        "status": "completed",
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 500,
            "total_tokens": 1500,
            "input_tokens_details": {
                "cached_tokens": 200,
                "cache_creation_input_tokens": 800
            },
            "output_tokens_details": {
                "reasoning_tokens": 0
            }
        }
    }
    
    print("Mock BytePlus Response:")
    print(json.dumps(mock_response, indent=2))
    
    print("\nParsed Usage:")
    print_usage(mock_response.get('usage', {}))
    
    # 验证字段
    usage = mock_response.get('usage', {})
    input_details = usage.get('input_tokens_details', {})
    
    expected_cached = 200
    expected_creation = 800
    
    actual_cached = input_details.get('cached_tokens', 0)
    actual_creation = input_details.get('cache_creation_input_tokens', 0)
    
    print("\nValidation:")
    if actual_cached == expected_cached:
        print(f"  [OK] cached_tokens: {actual_cached} == {expected_cached}")
    else:
        print(f"  [FAIL] cached_tokens: {actual_cached} != {expected_cached}")
    
    if actual_creation == expected_creation:
        print(f"  [OK] cache_creation_input_tokens: {actual_creation} == {expected_creation}")
    else:
        print(f"  [FAIL] cache_creation_input_tokens: {actual_creation} != {expected_creation}")


def check_api_health():
    """检查 API 健康状态"""
    print_separator("API Health Check")
    
    try:
        resp = requests.get(f"{BASE_URL}/api/status", timeout=10)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            return data.get('success', False)
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False


def main():
    print("="*60)
    print("  BytePlus Cache Creation Tokens Verification")
    print("="*60)
    print(f"\nConfiguration:")
    print(f"  - Base URL: {BASE_URL}")
    print(f"  - Model: {MODEL}")
    print(f"  - API Key: {API_KEY[:10]}...")
    
    # 检查 API 健康状态
    if not check_api_health():
        print("\n[WARN] API health check failed, but continuing with tests...")
    
    # 测试模拟响应解析
    test_mock_response_parsing()
    
    # 测试实际 API（如果配置了有效的 API Key）
    if API_KEY != 'sk-test':
        test_responses_api_with_caching()
    else:
        print("\n[INFO] Skipping actual API test (using default API key)")
        print("       Set NEW_API_KEY environment variable to test with real API")
    
    print("\n" + "="*60)
    print("  Verification Complete")
    print("="*60)


if __name__ == "__main__":
    main()
