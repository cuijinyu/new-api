# encoding=utf-8
"""
BytePlus (Volcengine) Direct Responses API Test Script
调用字节跳动原厂 Responses API (v3/responses) 的示例脚本

功能：
1. 直接调用 Volcengine/BytePlus API，不经过 new-api
2. 验证 Context Caching (上下文缓存) 功能
3. 验证 cache_creation_input_tokens 和 cached_tokens 字段

使用方法:
    export VOLC_API_KEY="your-api-key"
    export VOLC_ENDPOINT_ID="ep-2025xxxx-xxxxx"
    python test_byteplus_direct_responses.py
"""

import os
import json
import time
import requests
from typing import Dict, Any

import argparse

# 配置
# 默认使用 BytePlus 国际版接入点，如果是火山引擎国内版请使用 https://ark.cn-beijing.volces.com
DEFAULT_BASE_URL = os.getenv('VOLC_BASE_URL', 'https://ark.ap-southeast.bytepluses.com')
DEFAULT_API_KEY = os.getenv('VOLC_API_KEY', '')
# 模型接入点 ID (Endpoint ID)，例如 ep-2024060401xxxx-xxxxx
DEFAULT_ENDPOINT_ID = os.getenv('VOLC_ENDPOINT_ID', 'ep-20260131174442-stlj2')

def print_separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def print_usage(usage: Dict[str, Any]):
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

def test_direct_responses_api(api_key, endpoint_id, base_url):
    if not api_key or not endpoint_id:
        print("Error: Please provide API Key and Endpoint ID.")
        return

    print_separator("Test: Direct BytePlus Responses API with Caching")
    print(f"Base URL: {base_url}")
    print(f"Endpoint ID: {endpoint_id}")
    
    # 长文本输入
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
    
    url = f"{base_url}/api/v3/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 第一次请求：启用前缀缓存
    print("Step 1: Creating initial response with prefix caching enabled...")
    payload1 = {
        "model": endpoint_id,
        "input": [
            {"role": "system", "content": long_context},
            {"role": "user", "content": "What is the main theme of this story?"}
        ],
        "caching": {"type": "enabled", "prefix": True},
        "thinking": {"type": "disabled"}
    }
    
    try:
        print(f"Requesting {url}...")
        resp1 = requests.post(url, headers=headers, json=payload1, timeout=120)
        print(f"Response 1 Status: {resp1.status_code}")
        
        if resp1.status_code == 200:
            data1 = resp1.json()
            response_id = data1.get('id')
            print(f"Response 1 ID: {response_id}")
            
            # 打印完整响应以便检查字段
            print("\nFull Response 1 Body:")
            print(json.dumps(data1, indent=2))
            
            print("\nUsage (First Request):")
            print_usage(data1.get('usage', {}))
            
            # 检查缓存写入 tokens
            usage1 = data1.get('usage', {})
            input_details1 = usage1.get('input_tokens_details', {})
            cache_creation = input_details1.get('cache_creation_input_tokens', 0)
            
            if cache_creation > 0:
                print(f"\n[OK] Cache creation detected! cache_creation_input_tokens: {cache_creation}")
            else:
                print("\n[INFO] No cache_creation_input_tokens in first request")
            
            if not response_id:
                print("Error: No response ID received.")
                return

            # 等待缓存创建
            print("\nWaiting for cache to be created (10 seconds)...")
            time.sleep(10)
            
            # 第二次请求：使用 previous_response_id 利用缓存
            print("\nStep 2: Using previous_response_id to leverage cache...")
            payload2 = {
                "model": endpoint_id,
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
                
                # 打印完整响应以便检查字段
                print("\nFull Response 2 Body:")
                print(json.dumps(data2, indent=2))
                
                print("\nUsage (Second Request):")
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
                print(f"Error Response 2: {resp2.text}")
        else:
            print(f"Error Response 1: {resp1.text}")
            
    except Exception as e:
        print(f"Request error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test BytePlus Responses API with Caching')
    parser.add_argument('--api-key', default=DEFAULT_API_KEY, help='BytePlus API Key')
    parser.add_argument('--endpoint-id', default=DEFAULT_ENDPOINT_ID, help='Model Endpoint ID')
    parser.add_argument('--base-url', default=DEFAULT_BASE_URL, help='API Base URL')
    
    args = parser.parse_args()
    
    test_direct_responses_api(args.api_key, args.endpoint_id, args.base_url)
