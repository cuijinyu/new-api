#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
缓存亲和路由测试脚本

测试场景：
1. 无 cache_control 请求 -> 应走随机路由，两个渠道都可能被选中
2. 带 cache_control 请求 -> 应走亲和路由，相同 prompt 始终路由到同一渠道
3. 多次发送相同 cache_control 请求 -> 验证缓存命中率提升
4. 不同 cache_control 内容 -> 应可能路由到不同渠道
"""

import io
import sys
import json
import time
import requests
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE_URL = "http://localhost:3001"
API_KEY = "sk-YOUR-API-KEY"

HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": API_KEY,
    "anthropic-version": "2023-06-01",
}

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
) * 50  # ~5000+ tokens to trigger Claude prompt caching


def call_api(payload: dict, label: str = "") -> dict:
    try:
        resp = requests.post(
            f"{BASE_URL}/v1/messages",
            headers=HEADERS,
            json=payload,
            timeout=60,
        )
        data = resp.json()
        if "error" in data:
            print(f"  [{label}] ERROR: {data['error']}")
            return data
        return data
    except Exception as e:
        print(f"  [{label}] EXCEPTION: {e}")
        return {}


def extract_info(data: dict) -> dict:
    usage = data.get("usage", {})
    return {
        "model": data.get("model", "unknown"),
        "id": data.get("id", ""),
        "input_tokens": usage.get("input_tokens", 0),
        "cache_creation": usage.get("cache_creation_input_tokens", 0),
        "cache_read": usage.get("cache_read_input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "text": data.get("content", [{}])[0].get("text", "") if data.get("content") else "",
    }


def cache_status(info: dict) -> str:
    if info["cache_read"] > 0:
        return "CACHE_HIT"
    elif info["cache_creation"] > 0:
        return "CACHE_CREATE"
    return "NO_CACHE"


def sep(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ============================================================
# 测试 1：无 cache_control 请求（随机路由）
# ============================================================
def test_random_routing():
    sep("测试 1: 无 cache_control 请求 -> 随机路由")
    print("发送 6 次不带 cache_control 的请求，观察渠道分布...")

    ids = []
    for i in range(6):
        payload = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 20,
            "messages": [
                {"role": "user", "content": f"Say hello #{i}"}
            ],
        }
        data = call_api(payload, f"random-{i}")
        info = extract_info(data)
        ids.append(info["id"])
        print(f"  请求 {i+1}: id={info['id'][:40]}  cache_read={info['cache_read']}  cache_create={info['cache_creation']}")
        time.sleep(0.5)

    print(f"\n  所有响应 ID: ")
    for mid in ids:
        print(f"    {mid}")
    print("  (随机路由下，请求可能分散到不同渠道)")
    return ids


# ============================================================
# 测试 2：带 cache_control 的请求（亲和路由 - 相同 prompt）
# ============================================================
def test_affinity_same_prompt():
    sep("测试 2: 带 cache_control 的相同 prompt -> 亲和路由")
    print("发送 6 次带 cache_control 的相同 system prompt，应路由到同一渠道...")
    print("(亲和路由确保相同 prompt 指纹始终路由到同一上游渠道)")

    results = []
    for i in range(6):
        payload = {
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
                {"role": "user", "content": f"What is 1+{i}?"}
            ],
        }
        data = call_api(payload, f"affinity-same-{i}")
        if "error" in data:
            results.append({"id": "", "cache_read": 0, "cache_creation": 0})
            continue
        info = extract_info(data)
        results.append(info)
        status = cache_status(info)
        print(f"  请求 {i+1}: status={status}  cache_read={info['cache_read']}  cache_create={info['cache_creation']}  text={info['text'][:30]}")
        time.sleep(1.5)

    cache_hits = sum(1 for r in results if r.get("cache_read", 0) > 0)
    cache_creates = sum(1 for r in results if r.get("cache_creation", 0) > 0)
    total_valid = sum(1 for r in results if r.get("id"))
    print(f"\n  统计: 有效响应={total_valid}/6, 缓存命中={cache_hits}, 缓存创建={cache_creates}")

    if cache_hits >= 3:
        print("  [OK] 缓存命中率良好，亲和路由有效保持了缓存命中!")
    elif cache_hits >= 1:
        print("  [PARTIAL] 有部分缓存命中，亲和路由部分生效")
    elif total_valid > 0:
        print("  [WARN] 无缓存命中，可能上游内部负载均衡影响了缓存")
    else:
        print("  [FAIL] 所有请求失败")

    return results


# ============================================================
# 测试 3：不同 cache_control 内容
# ============================================================
def test_affinity_different_prompts():
    sep("测试 3: 不同 cache_control 内容 -> 可能路由到不同渠道")
    print("发送 4 次带不同 system prompt 的请求...")

    results = []
    for i in range(4):
        different_text = f"You are assistant #{i}. Unique marker: {i*12345}. " + LONG_SYSTEM_TEXT
        payload = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 20,
            "system": [
                {
                    "type": "text",
                    "text": different_text,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [
                {"role": "user", "content": "What is 1+1?"}
            ],
        }
        data = call_api(payload, f"affinity-diff-{i}")
        if "error" in data:
            continue
        info = extract_info(data)
        results.append(info)
        print(f"  请求 {i+1}: id={info['id'][:40]}  cache_read={info['cache_read']}  cache_create={info['cache_creation']}")
        time.sleep(1)

    if len(results) > 0:
        print(f"\n  共 {len(results)} 个有效响应")
        print("  (不同 prompt 内容会产生不同的 affinity key，可能路由到不同渠道)")
    return results


# ============================================================
# 测试 4：缓存持久性验证
# ============================================================
def test_cache_persistence():
    sep("测试 4: 缓存持久性验证（间隔发送相同请求）")
    print("发送相同 cache_control 请求，间隔 3 秒，验证缓存是否持续命中...")

    cache_text = "This is a persistent cache test. " + LONG_SYSTEM_TEXT
    results = []
    for i in range(5):
        payload = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 20,
            "system": [
                {
                    "type": "text",
                    "text": cache_text,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [
                {"role": "user", "content": f"Count to {i+1}"}
            ],
        }
        data = call_api(payload, f"persist-{i}")
        if "error" in data:
            continue
        info = extract_info(data)
        results.append(info)
        status = cache_status(info)
        print(f"  请求 {i+1}: status={status}  cache_read={info['cache_read']}  cache_create={info['cache_creation']}")
        if i < 4:
            print(f"  等待 3 秒...")
            time.sleep(3)

    if results:
        cache_hits = sum(1 for r in results if r["cache_read"] > 0)
        cache_creates = sum(1 for r in results if r["cache_creation"] > 0)
        print(f"\n  统计: 缓存命中={cache_hits}/{len(results)}, 缓存创建={cache_creates}/{len(results)}")
        print(f"  (理想情况: 第1次 CACHE_CREATE, 后续 CACHE_HIT)")
        if cache_hits >= len(results) - 1:
            print("  [OK] 缓存持久性验证通过，亲和路由有效保持了缓存命中!")
        elif cache_hits >= 2:
            print("  [PARTIAL] 部分缓存命中，亲和路由部分生效")
        else:
            print("  [WARN] 缓存命中率偏低")


# ============================================================
# 主函数
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("  Claude 缓存亲和路由测试")
    print(f"  API: {BASE_URL}")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    test_random_routing()
    test_affinity_same_prompt()
    test_affinity_different_prompts()
    test_cache_persistence()

    sep("测试完成")
    print("\n  请查看 docker logs new-api-local 中的 [CacheAffinity] 日志")
    print("  来确认亲和路由的内部行为（命中/未命中/渠道选择等）")
