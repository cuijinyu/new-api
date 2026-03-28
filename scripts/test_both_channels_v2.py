#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双渠道缓存命中率对比 v2
- 加大请求间隔到 3s（等缓存创建完成）
- 每组用不同的 system prompt 避免跨组缓存干扰
"""

import io, sys, time, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

PROXY_URL = "http://localhost:3001"
PROXY_KEY = "sk-YOUR-PROXY-KEY"

AWS_URL = "http://YOUR-AWS-HOST:PORT"
AWS_KEY = "sk-YOUR-AWS-KEY"

FINE_URL = "https://YOUR-FINE-API-HOST"
FINE_KEY = "sk-YOUR-FINE-KEY"

BASE_TEXT = (
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


def make_payload(system_text, q):
    return {
        "model": "claude-sonnet-4-6",
        "max_tokens": 10,
        "system": [{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": [{"type": "text", "text": q, "cache_control": {"type": "ephemeral"}}]}],
    }


def send(url, key, payload):
    headers = {"Content-Type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"}
    try:
        t0 = time.time()
        r = requests.post(f"{url}/v1/messages", headers=headers, json=payload, timeout=120)
        elapsed = time.time() - t0
        d = r.json()
        if "error" in d:
            return "ERROR", 0, 0, elapsed
        u = d.get("usage", {})
        cr = u.get("cache_creation_input_tokens", 0)
        ch = u.get("cache_read_input_tokens", 0)
        return ("HIT" if ch > 0 else ("CREATE" if cr > 0 else "NONE")), ch, cr, elapsed
    except Exception as e:
        return "FAIL", 0, 0, 0


def run_test(label, url, key, system_text, n=10, delay=3):
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"  URL: {url}")
    print(f"  {n} 次请求, 间隔 {delay}s")
    print(f"{'='*70}")
    results = []
    for i in range(n):
        payload = make_payload(system_text, f"What is {i}+1?")
        status, ch, cr, elapsed = send(url, key, payload)
        results.append(status)
        mark = "[*]" if status == "HIT" else "[ ]"
        print(f"  {mark} #{i+1:2d}  {status:8s}  read={ch:6d}  create={cr:6d}  {elapsed:.1f}s")
        if i < n - 1:
            time.sleep(delay)
    hits = results.count("HIT")
    creates = results.count("CREATE")
    errors = sum(1 for r in results if r in ("ERROR", "FAIL"))
    print(f"\n  结果: HIT={hits}/{n} ({hits/n*100:.0f}%)  CREATE={creates}  ERROR={errors}")
    return hits, creates, errors, n


if __name__ == "__main__":
    N = 10
    DELAY = 3
    print("=" * 70)
    print("  双渠道缓存命中率对比测试 v2")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  每组 {N} 次, 间隔 {DELAY}s, system prompt ~24000 tokens")
    print(f"  每组使用独立的 system prompt 避免跨组缓存干扰")
    print("=" * 70)

    sys_a = "GROUP_A_AWS. " + BASE_TEXT
    sys_b = "GROUP_B_FINE. " + BASE_TEXT
    sys_c = "GROUP_C_PROXY. " + BASE_TEXT

    r_aws  = run_test("A: 直接调用 aws5101 上游", AWS_URL, AWS_KEY, sys_a, N, DELAY)
    r_fine = run_test("B: 直接调用 fineapi(anyfast) 上游", FINE_URL, FINE_KEY, sys_b, N, DELAY)
    r_proxy = run_test("C: 通过代理 + 亲和路由", PROXY_URL, PROXY_KEY, sys_c, N, DELAY)

    print(f"\n{'='*70}")
    print(f"  总结对比")
    print(f"{'='*70}")
    for label, (hits, creates, errors, total) in [
        ("A: aws5101 直接", r_aws),
        ("B: fineapi 直接", r_fine),
        ("C: 代理+亲和", r_proxy),
    ]:
        pct = hits / total * 100 if total > 0 else 0
        bar = "*" * hits + "." * (total - hits - errors) + "x" * errors
        print(f"  {label:18s}  HIT={hits:2d}/{total}  ({pct:3.0f}%)  [{bar}]")

    print()
    if r_proxy[0] > r_aws[0] and r_proxy[0] > r_fine[0]:
        print("  --> 代理+亲和路由 缓存命中率最高!")
    elif r_proxy[0] >= max(r_aws[0], r_fine[0]):
        print("  --> 代理+亲和路由 达到或超过直接调用的缓存命中率!")
    elif r_proxy[0] > 0:
        print(f"  --> 代理+亲和路由 有 {r_proxy[0]} 次命中 (aws直接={r_aws[0]}, fineapi直接={r_fine[0]})")
    else:
        print("  --> 所有方式均未命中缓存，上游内部负载均衡分散了请求")
