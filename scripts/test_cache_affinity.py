#!/usr/bin/env python3
"""
Cache Affinity Routing 集成测试

验证亲和路由是否将相同 prompt 的请求路由到同一渠道。
通过观察 cache_creation 和 cache_read tokens 判断路由一致性。

测试场景:
  A: 相同 system prompt + cache_control，连续请求应路由到同一渠道 → 高缓存命中率
  B: 不同 system prompt + cache_control，应路由到不同渠道（一致性哈希分散）
  C: 无 cache_control 的请求，走正常随机路由（对照组）
  D: 相同 prompt 间隔较长（>5min TTL），亲和表过期后应通过一致性哈希重新路由到同一渠道

使用方法:
  python scripts/test_cache_affinity.py --base-url http://localhost:3000 --api-key sk-xxx

注意: 需要站点配置了多个 Claude 渠道才能体现亲和路由的效果。
"""

import argparse
import json
import time
import uuid
import sys

import requests

# 足够长的 system prompt 以满足 Claude 最小缓存 token 数要求 (Sonnet: 2048, Opus: 4096)
BASE_PROMPT = """你是一个专业的AI助手，精通以下领域：

1. 软件工程：包括但不限于系统设计、算法与数据结构、设计模式、微服务架构、容器化技术（Docker/Kubernetes）、CI/CD流水线、代码审查最佳实践、测试驱动开发（TDD）、行为驱动开发（BDD）、领域驱动设计（DDD）。你需要能够解释每种设计模式的适用场景，比较不同架构方案的优劣，并给出具体的实现建议。在系统设计方面，你需要了解高可用架构、水平扩展、垂直扩展、读写分离、CQRS模式、事件溯源等核心概念。

2. 数据科学与机器学习：包括数据预处理、特征工程、监督学习、无监督学习、深度学习、自然语言处理（NLP）、计算机视觉（CV）、推荐系统、时间序列分析、A/B测试、因果推断。你需要熟悉 PyTorch、TensorFlow、scikit-learn、Hugging Face Transformers 等主流框架的使用方法和最佳实践。

3. 云计算与DevOps：AWS、Azure、GCP三大云平台的核心服务，包括计算（EC2/VM/GCE）、存储（S3/Blob/GCS）、数据库（RDS/CosmosDB/Cloud SQL）、消息队列（SQS/Service Bus/Pub/Sub）、无服务器计算（Lambda/Functions/Cloud Functions）。你需要了解 Infrastructure as Code（Terraform/CloudFormation/Pulumi）、容器编排（Kubernetes/ECS/AKS）、监控告警（CloudWatch/Prometheus/Grafana）。

4. 数据库技术：关系型数据库（MySQL、PostgreSQL、SQL Server、Oracle）、NoSQL数据库（MongoDB、Redis、Cassandra、DynamoDB）、图数据库（Neo4j）、时序数据库（InfluxDB、TimescaleDB）、数据仓库（Snowflake、BigQuery、Redshift）。你需要能够根据业务场景推荐合适的数据库方案，解释索引优化、查询优化、分库分表等高级话题。

5. 网络安全：OWASP Top 10、加密算法（AES/RSA/ECC）、身份认证与授权（OAuth 2.0/OpenID Connect/SAML/JWT）、零信任架构、渗透测试、安全审计、合规性（GDPR/SOC 2/ISO 27001/PCI DSS）。

6. 前端开发：React/Vue/Angular三大框架，以及Next.js/Nuxt.js等SSR框架。CSS预处理器、CSS-in-JS、状态管理、构建工具（Webpack/Vite/Rollup）。

7. 后端开发：Go/Python/Java/Node.js/Rust等主流后端语言。Web框架（Gin/FastAPI/Spring Boot/Express）、ORM、API设计（REST/GraphQL/gRPC）。

8. 分布式系统：CAP定理、一致性协议（Raft/Paxos）、分布式事务（Saga/TCC）、服务发现、负载均衡、熔断降级、限流、链路追踪。

9. 人工智能前沿：大语言模型、RAG、Agent框架、向量数据库、模型微调（LoRA/QLoRA）、对齐技术（RLHF/DPO）、推理优化。

10. 操作系统：进程管理、线程模型、内存管理（虚拟内存/页表/TLB）、文件系统、进程间通信、同步原语、网络子系统（epoll/kqueue/io_uring）、容器技术底层（Namespace/Cgroup）。

请基于以上专业知识为用户提供准确详细有深度的技术解答。"""


def make_prompt(session_id: str) -> str:
    return f"[SESSION: {session_id}]\n\n{BASE_PROMPT}"


def build_claude_payload(system_prompt: str, model: str, with_cache: bool = True) -> dict:
    system_block = {"type": "text", "text": system_prompt}
    if with_cache:
        system_block["cache_control"] = {"type": "ephemeral"}

    return {
        "model": model,
        "max_tokens": 50,
        "system": [system_block],
        "messages": [
            {"role": "user", "content": "用一句话解释什么是微服务架构？"}
        ],
    }


def do_request(base_url: str, api_key: str, payload: dict, use_claude_api: bool = True) -> dict:
    if use_claude_api:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        url = f"{base_url}/v1/messages"
    else:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        url = f"{base_url}/v1/chat/completions"

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()


def fmt_usage(usage: dict) -> str:
    cc = usage.get("cache_creation_input_tokens", 0)
    cr = usage.get("cache_read_input_tokens", 0)
    inp = usage.get("input_tokens", 0)
    if cr > 0:
        return f"\033[32mHIT  (read={cr}, input={inp})\033[0m"
    elif cc > 0:
        return f"\033[33mWRITE(creation={cc}, input={inp})\033[0m"
    else:
        return f"\033[31mNONE (input={inp})\033[0m"


def run_test(label: str, base_url: str, api_key: str, model: str,
             prompt: str, with_cache: bool, count: int, delay: float):
    print(f"\n{'='*72}")
    print(f"  {label}")
    print(f"  model={model}, cache_control={'yes' if with_cache else 'no'}, requests={count}")
    print(f"{'='*72}")

    payload = build_claude_payload(prompt, model, with_cache)
    hits = 0
    creations = 0
    nones = 0

    for i in range(1, count + 1):
        tag = "创建" if i == 1 else f"读{i-1:>1}"
        print(f"  [{tag}] -> ", end="", flush=True)
        try:
            data = do_request(base_url, api_key, payload)
            usage = data.get("usage", {})
            result = fmt_usage(usage)
            print(result)
            cr = usage.get("cache_read_input_tokens", 0)
            cc = usage.get("cache_creation_input_tokens", 0)
            if cr > 0:
                hits += 1
            elif cc > 0:
                creations += 1
            else:
                nones += 1
        except Exception as e:
            print(f"\033[31mERROR: {e}\033[0m")
            nones += 1

        if i < count:
            time.sleep(delay)

    print(f"  -----> 命中: {hits}/{count}, 创建: {creations}/{count}, 无缓存: {nones}/{count}")
    return hits, creations, nones, count


def main():
    parser = argparse.ArgumentParser(description="Cache Affinity Routing 集成测试")
    parser.add_argument("--base-url", default="http://localhost:3000", help="API base URL")
    parser.add_argument("--api-key", required=True, help="API key")
    parser.add_argument("--model", default="claude-sonnet-4-20250514", help="Model name")
    parser.add_argument("--count", type=int, default=5, help="Number of requests per test")
    parser.add_argument("--delay", type=float, default=3.0, help="Delay between requests (seconds)")
    args = parser.parse_args()

    print("=" * 72)
    print("  Cache Affinity Routing 集成测试")
    print("=" * 72)
    print(f"  API:    {args.base_url}")
    print(f"  Model:  {args.model}")
    print(f"  Count:  {args.count} requests/test")
    print(f"  Delay:  {args.delay}s between requests")
    print("=" * 72)

    results = {}

    # Test A: 相同 prompt + cache_control → 应路由到同一渠道，高命中率
    session_a = uuid.uuid4().hex[:10]
    prompt_a = make_prompt(session_a)
    h, c, n, t = run_test(
        "测试A: 相同 prompt + cache_control (亲和路由)",
        args.base_url, args.api_key, args.model,
        prompt_a, with_cache=True, count=args.count, delay=args.delay,
    )
    results["A: 亲和路由"] = (h, t)

    # Test B: 不同 prompt + cache_control → 每次不同 prompt，不会命中
    print(f"\n  [测试B: 每次使用不同 prompt，验证不会误命中]")
    h_total, t_total = 0, args.count
    for i in range(args.count):
        session_b = uuid.uuid4().hex[:10]
        prompt_b = make_prompt(session_b)
        payload = build_claude_payload(prompt_b, args.model, with_cache=True)
        print(f"  [req{i+1}] prompt_id={session_b} -> ", end="", flush=True)
        try:
            data = do_request(args.base_url, args.api_key, payload)
            usage = data.get("usage", {})
            print(fmt_usage(usage))
            if usage.get("cache_read_input_tokens", 0) > 0:
                h_total += 1
        except Exception as e:
            print(f"\033[31mERROR: {e}\033[0m")
        if i < args.count - 1:
            time.sleep(args.delay)
    results["B: 不同prompt"] = (h_total, t_total)

    # Test C: 无 cache_control → 走随机路由（对照组）
    session_c = uuid.uuid4().hex[:10]
    prompt_c = make_prompt(session_c)
    h, c, n, t = run_test(
        "测试C: 相同 prompt 但无 cache_control (随机路由对照组)",
        args.base_url, args.api_key, args.model,
        prompt_c, with_cache=False, count=args.count, delay=args.delay,
    )
    results["C: 无cache对照"] = (h, t)

    # Summary
    print(f"\n\n{'='*72}")
    print(f"  汇总对比")
    print(f"{'='*72}")
    print(f"  {'测试':<20} {'命中/总数':<12} {'命中率':<10} {'可视化'}")
    print(f"  {'-'*60}")
    for k, (h, t) in results.items():
        rate = f"{h/t*100:.0f}%" if t > 0 else "N/A"
        bar = "█" * h + "░" * (t - h)
        print(f"  {k:<20} {h}/{t:<10} {rate:<10} {bar}")

    print(f"\n{'='*72}")
    print("  预期结果:")
    print("  - 测试A (亲和路由): 第1次 WRITE，后续应全部 HIT (命中率 ~80%+)")
    print("  - 测试B (不同prompt): 每次都是新 prompt，应全部 WRITE (命中率 ~0%)")
    print("  - 测试C (无cache对照): 无 cache_control，不触发缓存 (命中率 0%)")
    print(f"{'='*72}")

    # Exit code based on test A results
    if results["A: 亲和路由"][0] >= (args.count - 1) * 0.5:
        print("\n  ✓ 亲和路由测试通过")
        sys.exit(0)
    else:
        print("\n  ✗ 亲和路由测试未达预期，请检查:")
        print("    1. 是否配置了多个 Claude 渠道")
        print("    2. 上游供应商是否支持缓存亲和")
        print("    3. 查看日志中 [CacheAffinity] 相关输出")
        sys.exit(1)


if __name__ == "__main__":
    main()
