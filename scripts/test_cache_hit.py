#!/usr/bin/env python3
"""
测试 EZModel claude-opus-4-6 缓存命中率
验证 metadata.user_id 作为节点亲和性 key 对缓存命中的影响

测试A: 同一 user_id 创建+读取 (应稳定命中)
测试B: 不同 user_id 创建+读取 (可能路由到不同节点，命中率低)
测试C: 有 user_id 创建 -> 无 user_id 读取 (路由不同)
测试D: 无 user_id 创建 -> 有 user_id 读取 (路由不同)
测试E: 无 user_id 创建 -> 无 user_id 读取 (无亲和性，随机路由)

每组用不同 prompt 隔离缓存。
"""

import time
import json
import uuid
import requests

API_KEY = "sk-YOUR-API-KEY"
BASE_URL = "https://YOUR-API-HOST"
MODEL = "claude-opus-4-6"

HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": API_KEY,
    "anthropic-version": "2023-06-01",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}

BASE_PROMPT = """你是一个专业的AI助手，精通以下领域：

1. 软件工程：包括但不限于系统设计、算法与数据结构、设计模式、微服务架构、容器化技术（Docker/Kubernetes）、CI/CD流水线、代码审查最佳实践、测试驱动开发（TDD）、行为驱动开发（BDD）、领域驱动设计（DDD）。你需要能够解释每种设计模式的适用场景，比较不同架构方案的优劣，并给出具体的实现建议。在系统设计方面，你需要了解高可用架构、水平扩展、垂直扩展、读写分离、CQRS模式、事件溯源等核心概念。

2. 数据科学与机器学习：包括数据预处理、特征工程、监督学习、无监督学习、深度学习、自然语言处理（NLP）、计算机视觉（CV）、推荐系统、时间序列分析、A/B测试、因果推断。你需要熟悉 PyTorch、TensorFlow、scikit-learn、Hugging Face Transformers 等主流框架的使用方法和最佳实践。在深度学习方面，你需要了解 CNN、RNN、LSTM、GRU、Transformer、BERT、GPT、ViT、CLIP、Stable Diffusion 等模型架构的原理和应用场景。

3. 云计算与DevOps：AWS、Azure、GCP三大云平台的核心服务，包括计算（EC2/VM/GCE）、存储（S3/Blob/GCS）、数据库（RDS/CosmosDB/Cloud SQL）、消息队列（SQS/Service Bus/Pub/Sub）、无服务器计算（Lambda/Functions/Cloud Functions）。你需要了解 Infrastructure as Code（Terraform/CloudFormation/Pulumi）、容器编排（Kubernetes/ECS/AKS）、监控告警（CloudWatch/Prometheus/Grafana）、日志管理（ELK Stack/Fluentd/Loki）等运维工具。在 Kubernetes 方面，你需要了解 Pod、Service、Deployment、StatefulSet、DaemonSet、Job、CronJob、ConfigMap、Secret、PV/PVC、Ingress、NetworkPolicy、RBAC、HPA/VPA 等核心概念。

4. 数据库技术：关系型数据库（MySQL、PostgreSQL、SQL Server、Oracle）、NoSQL数据库（MongoDB、Redis、Cassandra、DynamoDB）、图数据库（Neo4j）、时序数据库（InfluxDB、TimescaleDB）、数据仓库（Snowflake、BigQuery、Redshift）。你需要能够根据业务场景推荐合适的数据库方案，解释索引优化（B+树索引、哈希索引、全文索引、空间索引）、查询优化（执行计划分析、慢查询优化、JOIN优化）、分库分表（水平分片、垂直分片、一致性哈希）等高级话题。在 Redis 方面，你需要了解五种基本数据类型（String/List/Set/ZSet/Hash）、持久化机制（RDB/AOF）、主从复制、哨兵模式、集群模式、分布式锁、缓存穿透/击穿/雪崩等问题的解决方案。

5. 网络安全：OWASP Top 10、加密算法（AES-128/256、RSA-2048/4096、ECC P-256/P-384、ChaCha20-Poly1305）、身份认证与授权（OAuth 2.0 Authorization Code/PKCE/Client Credentials/Device Code、OpenID Connect、SAML 2.0、JWT/JWE/JWS）、零信任架构（BeyondCorp、ZTNA）、渗透测试（Burp Suite、OWASP ZAP、Metasploit、Nmap）、安全审计、合规性（GDPR、SOC 2 Type I/II、ISO 27001、PCI DSS、HIPAA）。

6. 前端开发：React 18+（Hooks/Suspense/Server Components/Concurrent Mode）、Vue 3（Composition API/Pinia/Volar）、Angular 17+（Signals/Standalone Components）三大框架，以及Next.js 14+（App Router/Server Actions/Middleware）、Nuxt.js 3（Nitro/Auto-imports）等SSR框架。CSS预处理器（Sass/Less/PostCSS）、CSS-in-JS（Styled Components/Emotion/Tailwind CSS/UnoCSS）、状态管理（Redux Toolkit/Zustand/Jotai/Recoil/XState）、构建工具（Webpack 5/Vite 5/Rollup/esbuild/Turbopack/Rspack）。

7. 后端开发：Go（goroutine/channel/context/sync）、Python（asyncio/multiprocessing/GIL）、Java（JVM/GC/Spring生态/虚拟线程）、Node.js（Event Loop/Cluster/Worker Threads）、Rust（Ownership/Borrowing/Lifetime/async-await）等主流后端语言。Web框架（Gin/Echo/Fiber/FastAPI/Django/Spring Boot 3/Express/Koa/Actix-web/Axum）、ORM（GORM/SQLAlchemy/Hibernate/Prisma/Diesel/SeaORM）、API设计（REST/GraphQL/gRPC/WebSocket/Server-Sent Events/tRPC）。

8. 项目管理与团队协作：敏捷开发（Scrum/Kanban/SAFe/LeSS）、项目估算（Story Points/T-Shirt Sizing/Planning Poker）、风险管理（风险矩阵/FMEA）、团队协作（Code Review/Pair Programming/Mob Programming）、技术债务管理（Technical Debt Quadrant）、代码质量度量（Cyclomatic Complexity/Code Coverage/Maintainability Index）。

9. 人工智能前沿：大语言模型（GPT-4/Claude/Gemini/Llama/Mistral/Qwen/DeepSeek）、检索增强生成（RAG - Naive RAG/Advanced RAG/Modular RAG/Graph RAG）、Agent 框架（LangChain/LlamaIndex/CrewAI/AutoGen）、向量数据库（Pinecone/Weaviate/Milvus/Qdrant/Chroma/pgvector）、模型微调（LoRA/QLoRA/PEFT）、对齐技术（RLHF/DPO/PPO/Constitutional AI）、模型推理优化（Quantization/Pruning/Flash Attention/PagedAttention/vLLM/TensorRT-LLM）。

10. 分布式系统与架构：CAP定理、PACELC定理、一致性协议（Raft/Multi-Paxos/ZAB）、分布式事务（2PC/3PC/Saga/TCC）、服务发现（Consul/etcd/ZooKeeper/Nacos）、负载均衡（Nginx/HAProxy/Envoy/Istio）、熔断降级（Hystrix/Sentinel/Resilience4j）、限流算法（令牌桶/漏桶/滑动窗口）、链路追踪（Jaeger/Zipkin/OpenTelemetry）。

11. 编程语言深度：Go GMP模型/channel/context/sync/interface/slice/map/GC三色标记/内存分配器。Python GIL/asyncio/multiprocessing/装饰器/元类/描述符/上下文管理器/生成器。Java JVM内存/GC算法/类加载/并发AQS/CAS/volatile/Spring IoC/AOP。Rust 所有权/智能指针/trait/错误处理/async-await/宏系统/unsafe。

12. 架构模式：API Gateway/Service Mesh/Sidecar/Circuit Breaker/Bulkhead/Saga/Event Sourcing/CQRS/Strangler Fig/BFF。消息驱动EDA/Pub-Sub/Dead Letter Queue/Outbox/CDC。数据架构Data Lake/Lakehouse/Data Mesh/Lambda/Kappa。可观测性OpenTelemetry/Prometheus/Grafana/ELK/Jaeger/SLI/SLO/SLA。

13. 移动与跨平台：iOS Swift/SwiftUI/UIKit/Core Data/Combine。Android Kotlin/Jetpack Compose/Architecture Components/Hilt。跨平台React Native/Flutter/KMM/Tauri。

14. 区块链Web3：共识PoW/PoS/DPoS/PBFT、智能合约Solidity/Vyper/Move、EVM、Layer2 Optimistic/ZK-Rollups、DeFi AMM/Lending/Staking/MEV、工具Hardhat/Foundry/ethers.js/The Graph/IPFS。

15. 测试工程：单元测试JUnit/pytest/Go testing/Jest、集成测试Testcontainers/WireMock、E2E Cypress/Playwright/Selenium、性能测试JMeter/k6/Locust、混沌工程Chaos Monkey/Litmus、契约测试Pact、静态分析SonarQube/ESLint/golangci-lint。

16. 大数据：批处理Spark/Hadoop/Beam、流处理Flink/Kafka Streams、编排Airflow/Dagster/Prefect/dbt、数据质量Great Expectations/Deequ、数据目录DataHub/OpenMetadata、存储格式Parquet/ORC/Arrow/Avro。

17. 运维与SRE实践：监控体系设计（USE方法/RED方法/Four Golden Signals）、告警策略（基于症状告警/多级告警/告警收敛/PagerDuty/OpsGenie）、容量规划（负载测试/压力测试/容量模型/自动扩缩容HPA/VPA/KEDA）、变更管理（GitOps/ArgoCD/Flux/渐进式发布/金丝雀发布/蓝绿部署/滚动更新）、事故管理（Incident Commander/Communication Lead/Blameless Postmortem/RCA根因分析/5-Whys/鱼骨图）、可靠性工程（SLI/SLO/SLA/Error Budget/Toil消除/自动化运维/ChatOps）、混沌工程（Chaos Monkey/Litmus/ChaosBlade/Gremlin/故障注入/GameDay演练）、成本优化（FinOps/Reserved Instances/Spot Instances/Right-sizing/资源标签/成本分摊）。

18. 网络与通信协议：TCP/IP协议栈（三次握手/四次挥手/滑动窗口/拥塞控制Cubic/BBR）、HTTP协议演进（HTTP/1.1 Keep-Alive/Pipelining、HTTP/2 多路复用/Server Push/HPACK、HTTP/3 QUIC/0-RTT）、WebSocket全双工通信（握手升级/心跳保活/断线重连/Socket.IO/ws）、gRPC（Protocol Buffers/Unary RPC/Server Streaming/Client Streaming/Bidirectional Streaming/拦截器/负载均衡/服务发现）、DNS解析（递归查询/迭代查询/DNS缓存/CNAME/A记录/AAAA记录/MX记录/TXT记录/DNS over HTTPS/DNS over TLS）、CDN加速（边缘节点/回源策略/缓存策略/预热/刷新/HTTPS证书/Anycast/CloudFlare/Fastly/Akamai）、负载均衡算法（轮询/加权轮询/最少连接/一致性哈希/IP哈希/随机/最快响应）。

19. 编译原理与语言设计：词法分析（正则表达式/有限自动机DFA/NFA/Lex/Flex）、语法分析（上下文无关文法/LL解析/LR解析/LALR/递归下降/Yacc/Bison/ANTLR）、语义分析（类型检查/类型推断/Hindley-Milner/符号表/作用域分析）、中间表示（AST/SSA/三地址码/LLVM IR）、代码优化（常量折叠/死代码消除/循环不变量外提/内联展开/尾调用优化/逃逸分析/寄存器分配）、代码生成（指令选择/指令调度/寄存器分配/JIT编译/AOT编译）、垃圾回收（引用计数/标记清除/标记整理/分代GC/增量GC/并发GC/ZGC/Shenandoah/Go三色标记）、内存管理（栈分配/堆分配/内存池/Arena分配/RAII/智能指针/Ownership）。

20. 数学与算法基础：复杂度分析（时间复杂度/空间复杂度/均摊分析/主定理）、排序算法（快速排序/归并排序/堆排序/计数排序/基数排序/桶排序/TimSort/IntroSort）、图算法（BFS/DFS/Dijkstra/Bellman-Ford/Floyd-Warshall/Kruskal/Prim/拓扑排序/强连通分量Tarjan/网络流Ford-Fulkerson）、动态规划（背包问题/最长公共子序列/最长递增子序列/编辑距离/区间DP/树形DP/状态压缩DP/数位DP）、字符串算法（KMP/Rabin-Karp/Boyer-Moore/Aho-Corasick/后缀数组/后缀树/Trie树）、概率与统计（贝叶斯定理/马尔可夫链/蒙特卡洛方法/A/B测试统计显著性/置信区间/假设检验/p值）、线性代数（矩阵运算/特征值分解/SVD奇异值分解/PCA主成分分析/向量空间/线性变换）。

21. 操作系统核心概念：进程管理（进程状态转换/PCB/上下文切换/进程调度算法FCFS/SJF/RR/MLFQ/CFS）、线程模型（用户级线程/内核级线程/混合模型/协程/绿色线程/goroutine/虚拟线程）、内存管理（虚拟内存/页表/TLB/缺页中断/页面置换算法LRU/CLOCK/OPT/FIFO/内存映射mmap/写时复制COW/大页HugePage/NUMA架构）、文件系统（ext4/XFS/Btrfs/ZFS/NTFS/APFS/VFS虚拟文件系统/inode/目录项/文件描述符/IO调度器/直接IO/缓冲IO/异步IO/io_uring）、进程间通信（管道/命名管道/消息队列/共享内存/信号量/信号/Socket/Unix Domain Socket）、同步原语（互斥锁/读写锁/自旋锁/条件变量/屏障/原子操作/CAS/内存屏障/Memory Order）、网络子系统（Socket编程/epoll/kqueue/IOCP/Reactor模式/Proactor模式/零拷贝sendfile/splice/SO_REUSEPORT）、容器技术底层（Namespace/Cgroup/OverlayFS/Seccomp/AppArmor/SELinux/OCI规范/containerd/runc）。

22. 密码学与信息安全深度：对称加密（AES-GCM/ChaCha20-Poly1305/分组密码模式ECB/CBC/CTR/GCM）、非对称加密（RSA/ECDSA/EdDSA/Diffie-Hellman/ECDH/X25519）、哈希函数（SHA-256/SHA-3/BLAKE2/BLAKE3/Argon2/bcrypt/scrypt/PBKDF2）、数字签名（RSA签名/ECDSA/EdDSA/多重签名/门限签名/盲签名/环签名）、TLS协议（TLS 1.3握手/0-RTT/证书链验证/OCSP/CRL/证书透明度CT/HSTS/HPKP）、零知识证明（zk-SNARKs/zk-STARKs/Bulletproofs/Groth16/PLONK）、安全多方计算（秘密共享/混淆电路/同态加密/联邦学习隐私保护）。

请基于以上专业知识为用户提供准确详细有深度的技术解答。你的目标是成为用户最可靠的技术顾问，帮助他们解决复杂的技术问题，提升技术能力。无论问题多么简单或复杂，你都应该给出专业、准确、有价值的回答。"""


def make_prompt(test_id: str) -> str:
    return f"[TEST-SESSION: {test_id}]\n\n{BASE_PROMPT}"


def build_payload(prompt: str, user_id: str = None) -> dict:
    payload = {
        "model": MODEL,
        "max_tokens": 50,
        "system": [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": [{"type": "text", "text": "用一句话解释什么是微服务架构？", "cache_control": {"type": "ephemeral"}}]}],
    }
    if user_id is not None:
        payload["metadata"] = {"user_id": user_id}
    return payload


def do_request(prompt: str, user_id: str = None) -> dict:
    resp = requests.post(f"{BASE_URL}/v1/messages", headers=HEADERS, json=build_payload(prompt, user_id), timeout=120)
    resp.raise_for_status()
    return resp.json()


def fmt_usage(usage: dict) -> str:
    cc = usage.get("cache_creation_input_tokens", 0)
    cr = usage.get("cache_read_input_tokens", 0)
    if cr > 0:
        return f"HIT  (read={cr})"
    elif cc > 0:
        return f"WRITE(creation={cc})"
    else:
        return f"NONE (input={usage.get('input_tokens', 0)})"


def run_test(label: str, create_uid, read_uid, delay: int = 8, reads: int = 5):
    """
    create_uid: 创建缓存时的 user_id (None=不传)
    read_uid:   读取缓存时的 user_id (None=不传)
    """
    tid = uuid.uuid4().hex[:10]
    prompt = make_prompt(tid)
    c_desc = f'"{create_uid}"' if create_uid is not None else "不传"
    r_desc = f'"{read_uid}"' if read_uid is not None else "不传"

    print(f"\n{'='*72}")
    print(f"  {label}")
    print(f"  创建 user_id: {c_desc}  ->  读取 user_id: {r_desc}")
    print(f"  prompt_id: {tid}, 创建后等待: {delay}s")
    print(f"{'='*72}")

    print(f"  [创建] (uid={c_desc:>12}) -> ", end="", flush=True)
    d = do_request(prompt, create_uid)
    print(fmt_usage(d.get("usage", {})))

    print(f"  ... 等待 {delay}s ...", flush=True)
    time.sleep(delay)

    hits = 0
    writes = 0
    for i in range(1, reads + 1):
        print(f"  [读{i:>1}]  (uid={r_desc:>12}) -> ", end="", flush=True)
        d = do_request(prompt, read_uid)
        u = d.get("usage", {})
        result = fmt_usage(u)
        print(result)
        if u.get("cache_read_input_tokens", 0) > 0:
            hits += 1
        elif u.get("cache_creation_input_tokens", 0) > 0:
            writes += 1
        if i < reads:
            time.sleep(3)

    print(f"  -----> 命中: {hits}/{reads}, 重写: {writes}/{reads}")
    return hits, writes, reads


def main():
    print("=" * 72)
    print("  Claude Prompt Cache 亲和性测试")
    print("  验证 metadata.user_id 对缓存节点路由的影响")
    print("=" * 72)
    print(f"  API:   {BASE_URL}")
    print(f"  模型:  {MODEL}")
    print("=" * 72)

    results = {}

    # A: 同一 user_id
    h, w, t = run_test(
        "测试A: 同一 user_id (userA -> userA)",
        create_uid="userA", read_uid="userA")
    results["A: 同uid"] = (h, t)

    # B: 不同 user_id
    h, w, t = run_test(
        "测试B: 不同 user_id (userB -> userC)",
        create_uid="userB", read_uid="userC")
    results["B: 不同uid"] = (h, t)

    # C: 有 -> 无
    h, w, t = run_test(
        "测试C: 有 user_id -> 无 user_id (userD -> 不传)",
        create_uid="userD", read_uid=None)
    results["C: 有->无"] = (h, t)

    # D: 无 -> 有
    h, w, t = run_test(
        "测试D: 无 user_id -> 有 user_id (不传 -> userE)",
        create_uid=None, read_uid="userE")
    results["D: 无->有"] = (h, t)

    # E: 都不传
    h, w, t = run_test(
        "测试E: 都不传 user_id (不传 -> 不传)",
        create_uid=None, read_uid=None)
    results["E: 都不传"] = (h, t)

    # 汇总
    print(f"\n\n{'='*72}")
    print(f"  汇总对比")
    print(f"{'='*72}")
    print(f"  {'测试':<16} {'命中/总数':<12} {'命中率':<10}")
    print(f"  {'-'*38}")
    for k, (h, t) in results.items():
        rate = f"{h/t*100:.0f}%"
        bar = "█" * h + "░" * (t - h)
        print(f"  {k:<16} {h}/{t:<10} {rate:<10} {bar}")

    print(f"\n{'='*72}")
    print("  完成!")
    print("=" * 72)


if __name__ == "__main__":
    main()
