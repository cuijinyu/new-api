#!/usr/bin/env python3
"""
原始 HTTP 请求测试 - 查看 EZModel 对 cache_control 的完整响应
"""

import json
import requests

API_KEY = "sk-YOUR-API-KEY"
BASE_URL = "https://YOUR-API-HOST"
MODEL = "claude-sonnet-4-6"

LONG_SYSTEM_PROMPT = """你是一个专业的AI助手，精通以下领域：

1. 软件工程：包括但不限于系统设计、算法与数据结构、设计模式、微服务架构、容器化技术（Docker/Kubernetes）、CI/CD流水线、代码审查最佳实践、测试驱动开发（TDD）、行为驱动开发（BDD）、领域驱动设计（DDD）。你需要能够解释每种设计模式的适用场景，比较不同架构方案的优劣，并给出具体的实现建议。

2. 数据科学与机器学习：包括数据预处理、特征工程、监督学习、无监督学习、深度学习、自然语言处理（NLP）、计算机视觉（CV）、推荐系统、时间序列分析、A/B测试、因果推断。你需要熟悉 PyTorch、TensorFlow、scikit-learn、Hugging Face Transformers 等主流框架的使用方法和最佳实践。

3. 云计算与DevOps：AWS、Azure、GCP三大云平台的核心服务，包括计算（EC2/VM/GCE）、存储（S3/Blob/GCS）、数据库（RDS/CosmosDB/Cloud SQL）、消息队列（SQS/Service Bus/Pub/Sub）、无服务器计算（Lambda/Functions/Cloud Functions）。你需要了解 Infrastructure as Code（Terraform/CloudFormation/Pulumi）、容器编排（Kubernetes/ECS/AKS）、监控告警（CloudWatch/Prometheus/Grafana）等运维工具。

4. 数据库技术：关系型数据库（MySQL、PostgreSQL、SQL Server、Oracle）、NoSQL数据库（MongoDB、Redis、Cassandra、DynamoDB）、图数据库（Neo4j）、时序数据库（InfluxDB、TimescaleDB）、数据仓库（Snowflake、BigQuery、Redshift）。你需要能够根据业务场景推荐合适的数据库方案，解释索引优化、查询优化、分库分表等高级话题。

5. 网络安全：OWASP Top 10、加密算法（AES、RSA、ECC）、身份认证与授权（OAuth 2.0、OpenID Connect、SAML）、零信任架构、渗透测试、安全审计、合规性（GDPR、SOC 2、ISO 27001）。你需要能够识别常见的安全漏洞，并给出修复建议和防护方案。

6. 前端开发：React、Vue、Angular三大框架，以及Next.js、Nuxt.js等SSR框架，CSS预处理器（Sass/Less）、CSS-in-JS（Styled Components/Emotion）、状态管理（Redux/Vuex/MobX/Zustand）、构建工具（Webpack/Vite/Rollup/esbuild）、测试工具（Jest/Vitest/Cypress/Playwright）。

7. 后端开发：Go、Python、Java、Node.js、Rust等主流后端语言，Web框架（Gin/FastAPI/Spring Boot/Express/Actix）、ORM（GORM/SQLAlchemy/Hibernate/Prisma）、API设计（REST/GraphQL/gRPC/WebSocket）、消息中间件（Kafka/RabbitMQ/NATS）、缓存策略（Redis/Memcached）。

8. 项目管理：敏捷开发（Scrum/Kanban）、项目估算、风险管理、团队协作、技术债务管理、代码质量度量、性能监控与优化。你需要了解 JIRA、Confluence、GitHub Projects 等项目管理工具的使用。

9. 人工智能前沿：大语言模型（LLM）、检索增强生成（RAG）、Agent 框架（LangChain/LlamaIndex/CrewAI）、向量数据库（Pinecone/Weaviate/Milvus/Qdrant）、模型微调（LoRA/QLoRA）、RLHF、Constitutional AI、多模态模型。

10. 分布式系统：CAP定理、一致性协议（Raft/Paxos）、分布式事务（2PC/3PC/Saga）、服务发现（Consul/etcd/ZooKeeper）、负载均衡（Nginx/HAProxy/Envoy）、熔断降级（Hystrix/Sentinel/Resilience4j）、链路追踪（Jaeger/Zipkin/OpenTelemetry）。

请基于以上专业知识，为用户提供准确、详细、有深度的技术解答。在回答时，请注意：
- 提供具体的代码示例和最佳实践
- 解释底层原理和设计思路
- 给出性能优化建议
- 考虑安全性和可维护性
- 推荐相关的工具和资源
- 对比不同方案的优劣势
- 给出循序渐进的学习路径

你的目标是成为用户最可靠的技术顾问，帮助他们解决复杂的技术问题，提升技术能力。无论问题多么简单或复杂，你都应该给出专业、准确、有价值的回答。"""


def test_raw():
    """直接用 HTTP 请求 Anthropic /messages 接口，查看完整响应"""
    url = f"{BASE_URL}/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    }
    payload = {
        "model": MODEL,
        "max_tokens": 50,
        "system": [
            {
                "type": "text",
                "text": LONG_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [
            {"role": "user", "content": "用一句话解释什么是微服务架构？"},
        ],
    }

    print("=" * 60)
    print("  请求 1: 创建缓存 (无 metadata)")
    print("=" * 60)
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    print(f"  HTTP Status: {resp.status_code}")
    print(f"  Response Headers (selected):")
    for k in ["content-type", "x-request-id", "cf-ray"]:
        if k in resp.headers:
            print(f"    {k}: {resp.headers[k]}")
    data = resp.json()
    print(f"  Full usage: {json.dumps(data.get('usage', {}), indent=2, ensure_ascii=False)}")
    print(f"  Model: {data.get('model', 'N/A')}")
    print()

    import time
    print("  等待 3 秒...\n")
    time.sleep(3)

    print("=" * 60)
    print("  请求 2: 命中缓存 (无 metadata)")
    print("=" * 60)
    payload["messages"][0]["content"] = "用一句话解释什么是微服务架构？(round 2)"
    resp2 = requests.post(url, headers=headers, json=payload, timeout=120)
    print(f"  HTTP Status: {resp2.status_code}")
    data2 = resp2.json()
    print(f"  Full usage: {json.dumps(data2.get('usage', {}), indent=2, ensure_ascii=False)}")
    print()

    print("  等待 3 秒...\n")
    time.sleep(3)

    print("=" * 60)
    print("  请求 3: 带 metadata (user_id: test1234)")
    print("=" * 60)
    payload["metadata"] = {"user_id": "test1234"}
    payload["messages"][0]["content"] = "用一句话解释什么是微服务架构？(round 3)"
    resp3 = requests.post(url, headers=headers, json=payload, timeout=120)
    print(f"  HTTP Status: {resp3.status_code}")
    data3 = resp3.json()
    print(f"  Full usage: {json.dumps(data3.get('usage', {}), indent=2, ensure_ascii=False)}")
    print()

    print("  等待 3 秒...\n")
    time.sleep(3)

    print("=" * 60)
    print("  请求 4: 带 metadata 再次请求")
    print("=" * 60)
    payload["messages"][0]["content"] = "用一句话解释什么是微服务架构？(round 4)"
    resp4 = requests.post(url, headers=headers, json=payload, timeout=120)
    print(f"  HTTP Status: {resp4.status_code}")
    data4 = resp4.json()
    print(f"  Full usage: {json.dumps(data4.get('usage', {}), indent=2, ensure_ascii=False)}")
    print()

    print("=" * 60)
    print("  对比总结")
    print("=" * 60)
    for i, d in enumerate([data, data2, data3, data4], 1):
        u = d.get("usage", {})
        meta_label = "无meta" if i <= 2 else "有meta"
        cache_create = u.get("cache_creation_input_tokens", 0)
        cache_read = u.get("cache_read_input_tokens", 0)
        print(f"  请求{i} ({meta_label}): input={u.get('input_tokens',0)}, cache_create={cache_create}, cache_read={cache_read}")


if __name__ == "__main__":
    test_raw()
