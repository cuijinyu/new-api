#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
密集缓存测试 - 快速连续发送相同 prompt，最大化缓存命中概率
"""

import io
import sys
import time
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

PROXY_URL = "http://localhost:3001"
PROXY_KEY = "sk-YOUR-PROXY-KEY"

UPSTREAM_URL = "http://YOUR-AWS-HOST:PORT"
UPSTREAM_KEY = "sk-YOUR-AWS-KEY"

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

HEADERS_UPSTREAM = {
    "Content-Type": "application/json",
    "x-api-key": UPSTREAM_KEY,
    "anthropic-version": "2023-06-01",
}

HEADERS_PROXY = {
    "Content-Type": "application/json",
    "x-api-key": PROXY_KEY,
    "anthropic-version": "2023-06-01",
}


def make_payload(question: str) -> dict:
    return {
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
            {"role": "user", "content": question}
        ],
    }


def send(url, headers, payload, label):
    try:
        t0 = time.time()
        resp = requests.post(f"{url}/v1/messages", headers=headers, json=payload, timeout=120)
        elapsed = time.time() - t0
        data = resp.json()
        if "error" in data:
            return "ERROR", 0, 0, elapsed
        usage = data.get("usage", {})
        cr = usage.get("cache_creation_input_tokens", 0)
        ch = usage.get("cache_read_input_tokens", 0)
        return ("HIT" if ch > 0 else ("CREATE" if cr > 0 else "NONE")), ch, cr, elapsed
    except Exception as e:
        return "FAIL", 0, 0, 0


def sep(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


if __name__ == "__main__":
    N = 10
    print("=" * 70)
    print("  密集缓存命中测试")
    print(f"  每组 {N} 次请求，相同 system prompt，间隔 1 秒")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # A: 直接调用上游
    sep(f"A: 直接调用上游 aws5101（{N}次，间隔1秒）")
    a_results = []
    for i in range(N):
        payload = make_payload(f"What is {i}+1?")
        status, ch, cr, elapsed = send(UPSTREAM_URL, HEADERS_UPSTREAM, payload, f"A-{i+1}")
        a_results.append(status)
        mark = "[*]" if status == "HIT" else "[ ]"
        print(f"  {mark} #{i+1:2d}  {status:8s}  read={ch:6d}  create={cr:6d}  {elapsed:.1f}s")
        time.sleep(1)

    a_hits = a_results.count("HIT")
    a_creates = a_results.count("CREATE")
    print(f"\n  直接上游: HIT={a_hits}/{N} ({a_hits/N*100:.0f}%)  CREATE={a_creates}/{N}")

    # B: 通过代理（亲和路由）
    sep(f"B: 通过代理+亲和路由（{N}次，间隔1秒）")
    b_results = []
    for i in range(N):
        payload = make_payload(f"What is {i}+2?")
        status, ch, cr, elapsed = send(PROXY_URL, HEADERS_PROXY, payload, f"B-{i+1}")
        b_results.append(status)
        mark = "[*]" if status == "HIT" else "[ ]"
        print(f"  {mark} #{i+1:2d}  {status:8s}  read={ch:6d}  create={cr:6d}  {elapsed:.1f}s")
        time.sleep(1)

    b_hits = b_results.count("HIT")
    b_creates = b_results.count("CREATE")
    print(f"\n  代理亲和: HIT={b_hits}/{N} ({b_hits/N*100:.0f}%)  CREATE={b_creates}/{N}")

    sep("对比总结")
    print(f"  直接上游:   缓存命中 {a_hits}/{N} = {a_hits/N*100:.0f}%")
    print(f"  代理+亲和:  缓存命中 {b_hits}/{N} = {b_hits/N*100:.0f}%")
    if b_hits > a_hits:
        print(f"  --> 亲和路由提升了缓存命中率! (+{b_hits-a_hits} hits)")
    elif b_hits == a_hits:
        print(f"  --> 命中率相同（上游内部负载均衡是主要瓶颈）")
    else:
        print(f"  --> 直接调用命中率更高（需要进一步分析）")
