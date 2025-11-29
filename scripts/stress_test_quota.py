import asyncio
import aiohttp
import argparse
import time
import json
from collections import Counter

# 配置颜色输出
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

async def make_request(session, url, key, model, semaphore, stats):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }

    async with semaphore:
        start_time = time.time()
        try:
            async with session.post(f"{url}/chat/completions", json=payload, headers=headers) as response:
                status = response.status
                content = await response.text()
                
                # 简单的统计
                stats['total'] += 1
                stats['status_codes'][status] += 1
                
                if status == 200:
                    stats['success'] += 1
                else:
                    stats['fail'] += 1
                    # print(f"{Colors.FAIL}[Error {status}]{Colors.ENDC} {content[:100]}")

        except Exception as e:
            stats['total'] += 1
            stats['errors'] += 1
            print(f"{Colors.FAIL}[Exception]{Colors.ENDC} {str(e)}")

async def run_test(args):
    print(f"{Colors.HEADER}Starting stress test...{Colors.ENDC}")
    print(f"Target QPM: {args.qpm}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Duration: {args.duration} seconds")
    print(f"Model: {args.model}")
    
    stats = {
        'total': 0,
        'success': 0,
        'fail': 0,
        'errors': 0,
        'status_codes': Counter()
    }

    semaphore = asyncio.Semaphore(args.concurrency)
    start_time = time.time()
    
    # 计算请求间隔 (秒)
    interval = 60.0 / args.qpm
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        request_count = 0
        
        while time.time() - start_time < args.duration:
            # 检查是否需要发起新请求
            now = time.time()
            expected_requests = int((now - start_time) * (args.qpm / 60.0))
            
            if request_count < expected_requests:
                task = asyncio.create_task(make_request(session, args.url, args.key, args.model, semaphore, stats))
                tasks.append(task)
                request_count += 1
            
            # 清理已完成的任务 (可选，防止内存无限增长，但简单的脚本可以忽略)
            
            # 稍微睡眠以释放CPU
            await asyncio.sleep(0.01)
            
            # 实时打印进度 (每秒)
            if int(now) % 1 == 0 and int(now * 10) % 10 == 0:
                print(f"\rTime: {int(now - start_time)}s | Sent: {request_count} | Success: {stats['success']} | Fail: {stats['fail']} (429s: {stats['status_codes'][429]})", end="")

        print(f"\n{Colors.HEADER}Waiting for pending requests...{Colors.ENDC}")
        await asyncio.gather(*tasks)

    end_time = time.time()
    duration = end_time - start_time

    print(f"\n{Colors.OKGREEN}=== Test Completed ==={Colors.ENDC}")
    print(f"Total Requests: {stats['total']}")
    print(f"Success: {stats['success']}")
    print(f"Failed: {stats['fail']}")
    print(f"Errors (Exceptions): {stats['errors']}")
    print(f"Actual QPM: {stats['total'] / (duration / 60.0):.2f}")
    print("Status Code Distribution:")
    for code, count in stats['status_codes'].items():
        color = Colors.OKBLUE if code == 200 else Colors.FAIL
        print(f"  {color}{code}: {count}{Colors.ENDC}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM API Quota Stress Test Script")
    parser.add_argument("--url", type=str, default="http://localhost:3000/v1", help="API Base URL (e.g., http://localhost:3000/v1)")
    parser.add_argument("--key", type=str, required=True, help="API Key (sk-…)")
    parser.add_argument("--model", type=str, default="gpt-3.5-turbo", help="Model name to use")
    parser.add_argument("--qpm", type=int, default=60, help="Target Queries Per Minute")
    parser.add_argument("--concurrency", type=int, default=10, help="Max concurrent requests")
    parser.add_argument("--duration", type=int, default=30, help="Test duration in seconds")

    args = parser.parse_args()
    
    try:
        asyncio.run(run_test(args))
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
