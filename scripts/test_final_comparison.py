#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终对比测试：两个不同上游渠道（fineapi + aws5101）

验证：
1. 带 cache_control 的请求 -> 亲和路由固定到同一渠道 -> 缓存命中
2. 不带 cache_control 的请求 -> 随机路由 -> 分散到两个渠道 -> 缓存无法命中
"""

import io
import sys
import time
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

PROXY_URL = "http://localhost:3001"
PROXY_KEY = "sk-YOUR-PROXY-KEY"

LONG_SYSTEM_TEXT = (
    "You are a helpful AI assistant specialized in software engineering. "
    "You have deep knowledge of Python, Go, Rust, TypeScript, and many other languages. "
    "You always provide clear, concise, and accurate answers. "
    "When writing code, you follow best practices and include proper error handling. "
    "You are familiar with cloud computing, distributed systems, databases, and DevOps. "
    "You can help with architecture design, code review, debugging, and optimization. "
    "You always explain your reasoning step by step. "
    "You are patient, thorough, and detail-oriented. "
    "You prioritize correctness over speed, but also consider performance implications. "
    "You are up to date with the latest developments in software engineering. "
    "You understand microservices architecture, event-driven systems, and message queues. "
    "You are proficient in Docker, Kubernetes, Terraform, and CI/CD pipelines. "
    "You know how to design RESTful APIs, GraphQL endpoints, and gRPC services. "
    "You can help with database schema design, query optimization, and data modeling. "
    "You understand SQL databases like PostgreSQL, MySQL, and SQLite. "
    "You are familiar with NoSQL databases like MongoDB, Redis, DynamoDB, and Cassandra. "
    "You know about caching strategies, CDN configuration, and load balancing. "
    "You can help with security best practices, authentication, and authorization. "
    "You understand OAuth2, JWT, SAML, and other authentication protocols. "
    "You are familiar with testing methodologies including unit, integration, and e2e tests. "
    "You know about design patterns like Factory, Observer, Strategy, and Decorator. "
    "You understand SOLID principles, DRY, KISS, and YAGNI. "
    "You can help with performance profiling, memory leak detection, and optimization. "
    "You are familiar with concurrency patterns, thread safety, and async programming. "
    "You know about WebSockets, Server-Sent Events, and real-time communication. "
    "You understand version control with Git, branching strategies, and code review. "
    "You can help with monitoring, logging, alerting, and observability. "
    "You are familiar with Prometheus, Grafana, ELK stack, and Datadog. "
    "You know about serverless computing, AWS Lambda, Azure Functions, and GCP Cloud Functions. "
    "You understand networking concepts like TCP/IP, DNS, HTTP/2, and TLS. "
) * 50

HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": PROXY_KEY,
    "anthropic-version": "2023-06-01",
}


def send(payload, label):
    try:
        t0 = time.time()
        resp = requests.post(f"{PROXY_URL}/v1/messages", headers=HEADERS, json=payload, timeout=120)
        elapsed = time.time() - t0
        data = resp.json()
        if "error" in data:
            print(f"  [{label}] ERROR: {data['error']} ({elapsed:.1f}s)")
            return "ERROR", 0, 0, elapsed
        usage = data.get("usage", {})
        cr = usage.get("cache_creation_input_tokens", 0)
        ch = usage.get("cache_read_input_tokens", 0)
        status = "HIT" if ch > 0 else ("CREATE" if cr > 0 else "NONE")
        return status, ch, cr, elapsed
    except Exception as e:
        print(f"  [{label}] EXCEPTION: {e}")
        return "FAIL", 0, 0, 0


def sep(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


if __name__ == "__main__":
    N = 10
    print("=" * 70)
    print("  最终对比测试：亲和路由 vs 随机路由")
    print(f"  渠道配置：fineapi + aws5101")
    print(f"  每组 {N} 次请求，间隔 1.5 秒")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # ============================================================
    sep(f"A: 带 cache_control（亲和路由）- {N}次相同 prompt")
    print("  亲和路由会把相同 prompt 指纹的请求固定到同一渠道")
    # ============================================================
    a_results = []
    for i in range(N):
        payload = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 10,
            "system": [
                {
                    "type": "text",
                    "text": LONG_SYSTEM_TEXT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [
                {"role": "user", "content": f"What is {i}+3?"}
            ],
        }
        status, ch, cr, elapsed = send(payload, f"affinity-{i+1}")
        a_results.append(status)
        mark = "[*]" if status == "HIT" else "[ ]"
        print(f"  {mark} #{i+1:2d}  {status:8s}  read={ch:6d}  create={cr:6d}  {elapsed:.1f}s")
        time.sleep(1.5)

    a_hits = a_results.count("HIT")
    a_creates = a_results.count("CREATE")
    a_errors = a_results.count("ERROR")
    print(f"\n  亲和路由: HIT={a_hits}/{N} ({a_hits/N*100:.0f}%)  CREATE={a_creates}  ERROR={a_errors}")

    # ============================================================
    sep(f"B: 不带 cache_control（随机路由）- {N}次")
    print("  随机路由会把请求分散到两个渠道，无法利用缓存")
    # ============================================================
    b_results = []
    for i in range(N):
        payload = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 10,
            "messages": [
                {
                    "role": "user",
                    "content": LONG_SYSTEM_TEXT[:2000] + f"\n\nWhat is {i}+4?"
                }
            ],
        }
        status, ch, cr, elapsed = send(payload, f"random-{i+1}")
        b_results.append(status)
        mark = "[*]" if status == "HIT" else "[ ]"
        print(f"  {mark} #{i+1:2d}  {status:8s}  read={ch:6d}  create={cr:6d}  {elapsed:.1f}s")
        time.sleep(1.5)

    b_hits = b_results.count("HIT")
    b_creates = b_results.count("CREATE")
    b_errors = b_results.count("ERROR")
    print(f"\n  随机路由: HIT={b_hits}/{N} ({b_hits/N*100:.0f}%)  CREATE={b_creates}  ERROR={b_errors}")

    # ============================================================
    sep("对比总结")
    # ============================================================
    print(f"  亲和路由（带 cache_control）:  缓存命中 {a_hits}/{N} = {a_hits/N*100:.0f}%")
    print(f"  随机路由（无 cache_control）:  缓存命中 {b_hits}/{N} = {b_hits/N*100:.0f}%")
    print()
    if a_hits > b_hits:
        print(f"  --> 亲和路由提升了缓存命中率! (+{a_hits-b_hits} hits, +{(a_hits-b_hits)/N*100:.0f}%)")
    elif a_hits == b_hits:
        print(f"  --> 命中率相同")
    else:
        print(f"  --> 随机路由命中率更高（异常情况，需分析）")

    print()
    print("  请查看 docker logs 中的 [CacheAffinity] 日志确认路由行为")
