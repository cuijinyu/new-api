import asyncio
import aiohttp
import argparse
import time
import json
import statistics
import uuid
import random
from collections import Counter

# 配置颜色输出
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

def generate_long_prompt(token_count):
    # 粗略估计：1个token约等于2个汉字或4个英文字符
    # 我们使用重复的字符串来构造长文本
    base_text = "这是一段用于压力测试的文本内容。我们要模拟大约8000个token的输入压力。为了达到这个目标，我们需要不断重复这段文字，直到它足够长。"
    # 假设每个 base_text 大约 50 tokens
    repeat_times = max(1, token_count // 50)
    return base_text * repeat_times

async def make_request(session, url, key, model, semaphore, stats, request_id, base_prompt):
    # 为每个请求添加唯一的随机前缀，防止 KV Cache 命中
    unique_id = str(uuid.uuid4())
    prompt = f"RandomID: {unique_id}\nContent: {base_prompt}"
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 50,
        "stream": True  # 启用流式传输以准确计算首字节时间
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }

    async with semaphore:
        start_time = time.time()
        first_byte_latency = None
        try:
            full_url = url.rstrip('/')
            if not full_url.endswith('/chat/completions'):
                if not full_url.endswith('/v1'):
                    full_url += '/v1'
                full_url += '/chat/completions'
            
            async with session.post(full_url, json=payload, headers=headers) as response:
                status = response.status
                
                # 读取第一块数据即视为首字节到达
                async for chunk in response.content.iter_any():
                    if first_byte_latency is None:
                        first_byte_latency = time.time() - start_time
                    # 继续读取直到完成
                    pass
                
                end_time = time.time()
                full_latency = end_time - start_time
                
                stats['total'] += 1
                stats['status_codes'][status] += 1
                
                if status == 200:
                    stats['success'] += 1
                    if first_byte_latency is not None:
                        stats['ttfb_latencies'].append(first_byte_latency)
                    stats['full_latencies'].append(full_latency)
                else:
                    stats['fail'] += 1

        except Exception as e:
            stats['total'] += 1
            stats['errors'] += 1

async def run_test(args):
    print(f"{Colors.HEADER}=== DeepSeek Stress Test ==={Colors.ENDC}")
    print(f"Target URL: {args.url}")
    print(f"Model: {args.model}")
    print(f"Target RPM (QPM): {args.qpm}")
    print(f"Input Tokens (Approx): {args.tokens}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Duration: {args.duration} seconds")
    print("-" * 30)
    
    stats = {
        'total': 0,
        'success': 0,
        'fail': 0,
        'errors': 0,
        'status_codes': Counter(),
        'ttfb_latencies': [], # 首字节延迟
        'full_latencies': []  # 完整返回延迟
    }

    prompt = generate_long_prompt(args.tokens)
    semaphore = asyncio.Semaphore(args.concurrency)
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        request_count = 0
        last_update = 0
        
        while time.time() - start_time < args.duration:
            now = time.time()
            # 根据 QPM 计算当前应该已经发出的总请求数
            expected_requests = int((now - start_time) * (args.qpm / 60.0))
            
            if request_count < expected_requests:
                request_count += 1
                task = asyncio.create_task(make_request(session, args.url, args.key, args.model, semaphore, stats, request_count, prompt))
                tasks.append(task)
            
            # 高 RPM 下需要更短的 sleep 甚至不 sleep
            if args.qpm > 10000:
                await asyncio.sleep(0)
            else:
                await asyncio.sleep(0.001)
            
            # 实时打印进度（改为基于时间更新，并强制刷新缓冲区）
            now = time.time()
            if now - last_update > 0.1:
                elapsed = now - start_time
                print(f"\rTime: {elapsed:.1f}s | Sent: {request_count} | Success: {stats['success']} | Fail: {stats['fail']} | QPS: {request_count/max(elapsed, 0.1):.2f}", end="", flush=True)
                last_update = now

        print(f"\n\n{Colors.WARNING}Waiting for pending requests to complete...{Colors.ENDC}")
        if tasks:
            total_tasks = len(tasks)
            while True:
                # 检查任务完成情况
                pending_tasks = [t for t in tasks if not t.done()]
                if not pending_tasks:
                    break
                print(f"\rClosing: {len(pending_tasks)}/{total_tasks} pending... ", end="", flush=True)
                await asyncio.sleep(0.1)
            
            # 确保所有任务都被收集（处理异常）
            await asyncio.gather(*tasks, return_exceptions=True)
        print(f"\r{Colors.OKGREEN}All requests completed. Generating report...{Colors.ENDC}       ")

    end_time = time.time()
    duration = end_time - start_time

    print(f"\n{Colors.OKGREEN}=== Test Results ==={Colors.ENDC}")
    print(f"Total Requests: {stats['total']}")
    print(f"Success Rate: {(stats['success']/max(stats['total'], 1))*100:.2f}%")
    print(f"Actual RPM: {stats['total'] / (duration / 60.0):.2f}")
    
    def print_metrics(name, latencies):
        if not latencies:
            return
        lats = sorted(latencies)
        avg = sum(lats) / len(lats)
        p95 = lats[int(len(lats) * 0.95)]
        p99 = lats[int(len(lats) * 0.99)]
        print(f"\n[{name}]")
        print(f"  Average: {avg:.3f}s")
        print(f"  P95:     {p95:.3f}s")
        print(f"  P99:     {p99:.3f}s")
        print(f"  Max:     {lats[-1]:.3f}s")
        print(f"  Min:     {lats[0]:.3f}s")

    print_metrics("First Byte (TTFB)", stats['ttfb_latencies'])
    print_metrics("Full Response", stats['full_latencies'])

    print("\nStatus Code Distribution:")
    for code, count in sorted(stats['status_codes'].items()):
        color = Colors.OKBLUE if code == 200 else Colors.FAIL
        print(f"  {color}{code}: {count}{Colors.ENDC}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Model Provider API Stress Test Script")
    parser.add_argument("--url", type=str, default="https://api.easyart.cc", help="API Base URL")
    parser.add_argument("--key", type=str, default="sk-", help="API Key")
    parser.add_argument("--model", type=str, default="deepseek-v3.2", help="Model name")
    parser.add_argument("--qpm", type=int, default=25000, help="Target RPM (Queries Per Minute)")
    parser.add_argument("--tokens", type=int, default=8000, help="Approximate input tokens")
    parser.add_argument("--concurrency", type=int, default=100, help="Max concurrent requests")
    parser.add_argument("--duration", type=int, default=10, help="Test duration in seconds")

    args = parser.parse_args()
    
    if args.key == "sk-" or not args.key:
        print(f"{Colors.WARNING}Warning: No API Key provided. Use --key to specify one.{Colors.ENDC}")
    
    try:
        asyncio.run(run_test(args))
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
