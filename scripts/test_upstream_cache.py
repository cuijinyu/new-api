#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接测试上游 aws5101 的缓存行为
对比：通过代理 vs 直接调用上游
"""

import io
import sys
import json
import time
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

UPSTREAM_URL = "http://YOUR-AWS-HOST:PORT"
UPSTREAM_KEY = "sk-YOUR-AWS-KEY"

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


def make_payload(question: str) -> dict:
    return {
        "model": "claude-sonnet-4-6",
        "max_tokens": 20,
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


def call(url: str, key: str, payload: dict, label: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }
    try:
        t0 = time.time()
        resp = requests.post(f"{url}/v1/messages", headers=headers, json=payload, timeout=120)
        elapsed = time.time() - t0
        data = resp.json()
        if "error" in data:
            print(f"  [{label}] ERROR: {data['error']} ({elapsed:.1f}s)")
            return {}
        usage = data.get("usage", {})
        cr = usage.get("cache_creation_input_tokens", 0)
        ch = usage.get("cache_read_input_tokens", 0)
        status = "CACHE_HIT" if ch > 0 else ("CACHE_CREATE" if cr > 0 else "NO_CACHE")
        print(f"  [{label}] {status}  cache_read={ch}  cache_create={cr}  ({elapsed:.1f}s)")
        return data
    except Exception as e:
        print(f"  [{label}] EXCEPTION: {e}")
        return {}


def sep(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


if __name__ == "__main__":
    print("=" * 70)
    print("  上游缓存行为对比测试")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # ============================================================
    sep("A: 直接调用上游 aws5101（6次相同 prompt）")
    print("  直接调用上游，不经过代理，观察上游自身的缓存行为")
    # ============================================================
    for i in range(6):
        payload = make_payload(f"What is 1+{i}?")
        call(UPSTREAM_URL, UPSTREAM_KEY, payload, f"direct-{i+1}")
        time.sleep(2)

    # ============================================================
    sep("B: 通过本地代理调用（6次相同 prompt）")
    print("  通过代理调用，亲和路由确保路由到同一渠道")
    print("  代理会注入 X-Cache-Affinity-Key header")
    # ============================================================
    for i in range(6):
        payload = make_payload(f"What is 2+{i}?")
        call(PROXY_URL, PROXY_KEY, payload, f"proxy-{i+1}")
        time.sleep(2)

    sep("测试完成")
    print("\n  对比 A 和 B 的缓存命中率：")
    print("  - 如果 A 也全是 CACHE_CREATE，说明上游内部负载均衡分散了请求")
    print("  - 如果 A 有 CACHE_HIT，说明直接调用上游时缓存可以命中")
    print("  - B 的行为取决于亲和路由 + 上游内部行为的组合效果")
