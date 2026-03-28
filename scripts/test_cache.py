#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
缓存命中率测试
3 轮不同提示词，每轮 A(带uid) vs B(无uid) 各 8 次
"""

import io, sys, time, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

URL = "https://YOUR-API-HOST/v1/messages"
HEADERS = {
    "x-api-key": "sk-YOUR-API-KEY",
    "anthropic-version": "2023-06-01",
    "Content-Type": "application/json"
}

SYSTEM = (
    "You are a highly knowledgeable assistant specialized in mathematics, physics, "
    "computer science, and general knowledge. You always provide detailed, step-by-step explanations.\n\n"
    "MATHEMATICS: Expert in algebra, calculus, geometry, statistics, number theory, topology, "
    "abstract algebra, real analysis, complex analysis, differential equations, linear algebra, "
    "probability theory, combinatorics, graph theory, mathematical logic, set theory, measure theory, "
    "functional analysis, algebraic geometry, differential geometry, algebraic topology, category theory, "
    "homological algebra, representation theory, Lie groups, Lie algebras, commutative algebra, "
    "noncommutative algebra, operator theory, spectral theory, harmonic analysis, analytic number theory, "
    "algebraic number theory, arithmetic geometry, dynamical systems, ergodic theory, fractal geometry, "
    "discrete mathematics, optimization theory, control theory, game theory, information theory, "
    "coding theory, cryptography, computational complexity, automata theory, formal languages, "
    "mathematical physics, fluid dynamics, elasticity theory, continuum mechanics, celestial mechanics, "
    "orbital mechanics.\n\n"
    "PHYSICS: Classical mechanics, quantum mechanics, thermodynamics, statistical mechanics, "
    "electromagnetism, optics, special relativity, general relativity, nuclear physics, particle physics, "
    "condensed matter physics, astrophysics, cosmology, plasma physics, quantum field theory, string theory, "
    "loop quantum gravity, quantum information, quantum computing, quantum optics, atomic physics, "
    "molecular physics, solid state physics, semiconductor physics, superconductivity, superfluidity, "
    "magnetism, ferromagnetism, antiferromagnetism, paramagnetism, diamagnetism, electrodynamics, "
    "magnetohydrodynamics, acoustics, ultrasonics, nonlinear dynamics, chaos theory, turbulence, "
    "fluid mechanics, aerodynamics, hydrodynamics, geophysics, seismology, volcanology, meteorology, "
    "oceanography, atmospheric physics, space physics, solar physics, stellar physics, galactic physics, "
    "extragalactic physics, gravitational waves, black holes, neutron stars, white dwarfs, dark matter, "
    "dark energy.\n\n"
    "COMPUTER SCIENCE: Data structures including arrays, linked lists, doubly linked lists, circular linked lists, "
    "stacks, queues, deques, priority queues, binary trees, AVL trees, red-black trees, B-trees, B+ trees, "
    "splay trees, treaps, skip lists, hash tables, bloom filters, cuckoo filters, tries, radix trees, "
    "Patricia tries, suffix trees, suffix arrays, segment trees, Fenwick trees, k-d trees, R-trees, "
    "quadtrees, octrees, van Emde Boas trees, Fibonacci heaps, binomial heaps, pairing heaps, leftist heaps, "
    "disjoint set union, sparse tables. Algorithms including quicksort, mergesort, heapsort, radix sort, "
    "counting sort, bucket sort, timsort, introsort, binary search, interpolation search, exponential search, "
    "BFS, DFS, Dijkstra, Bellman-Ford, Floyd-Warshall, A-star, topological sort, Kruskal, Prim, Boruvka, "
    "maximum flow, minimum cut, Ford-Fulkerson, Edmonds-Karp, push-relabel, Hungarian algorithm, "
    "Kuhn-Munkres, network simplex, linear programming, simplex method, interior point methods, "
    "branch and bound, branch and cut, column generation, Lagrangian relaxation, semidefinite programming, "
    "convex optimization, gradient descent, stochastic gradient descent, Adam, AdaGrad, RMSprop, momentum, "
    "Nesterov momentum, conjugate gradient, Newton method, quasi-Newton methods, BFGS, L-BFGS, "
    "trust region methods, genetic algorithms, simulated annealing, particle swarm optimization, "
    "ant colony optimization, differential evolution, evolutionary strategies, Bayesian optimization.\n\n"
    "MACHINE LEARNING: Supervised learning with linear regression, ridge regression, lasso regression, "
    "elastic net, logistic regression, softmax regression, decision trees, random forests, gradient boosted trees, "
    "XGBoost, LightGBM, CatBoost, support vector machines, kernel methods, Gaussian processes, "
    "k-nearest neighbors, naive Bayes, linear discriminant analysis, quadratic discriminant analysis. "
    "Unsupervised learning with k-means, k-medoids, DBSCAN, OPTICS, mean shift, spectral clustering, "
    "hierarchical clustering, Gaussian mixture models, PCA, kernel PCA, ICA, factor analysis, "
    "non-negative matrix factorization, t-SNE, UMAP, autoencoders, variational autoencoders, "
    "self-organizing maps. Reinforcement learning with Q-learning, SARSA, deep Q-networks, double DQN, "
    "dueling DQN, prioritized experience replay, policy gradients, REINFORCE, actor-critic, A2C, A3C, "
    "PPO, TRPO, SAC, TD3, DDPG, model-based RL, Monte Carlo tree search, multi-armed bandits, "
    "Thompson sampling, UCB, contextual bandits.\n\n"
    "DEEP LEARNING: Feedforward networks, convolutional neural networks, residual networks, DenseNet, "
    "EfficientNet, MobileNet, ShuffleNet, SqueezeNet, NASNet, recurrent neural networks, LSTM, GRU, "
    "bidirectional RNNs, attention mechanisms, self-attention, multi-head attention, transformers, BERT, "
    "GPT, T5, XLNet, RoBERTa, ALBERT, DistilBERT, ELECTRA, DeBERTa, vision transformers, CLIP, DALL-E, "
    "Stable Diffusion, Midjourney, generative adversarial networks, DCGAN, WGAN, StyleGAN, CycleGAN, "
    "Pix2Pix, variational autoencoders, flow-based models, normalizing flows, diffusion models, DDPM, "
    "score-based models, energy-based models, Boltzmann machines, restricted Boltzmann machines, "
    "deep belief networks, graph neural networks, message passing neural networks, graph attention networks, "
    "graph convolutional networks, GraphSAGE, graph isomorphism networks.\n\n"
    "SYSTEMS DESIGN: CAP theorem, PACELC theorem, consistency models, eventual consistency, strong consistency, "
    "causal consistency, linearizability, serializability, snapshot isolation, read committed, repeatable read, "
    "replication strategies, leader-follower, multi-leader, leaderless, chain replication, quorum-based replication, "
    "consensus algorithms, Paxos, Multi-Paxos, Raft, Zab, PBFT, sharding, range-based, hash-based, "
    "directory-based, consistent hashing, virtual nodes, load balancing, round robin, weighted round robin, "
    "least connections, least response time, IP hash, consistent hashing, caching strategies, write-through, "
    "write-back, write-around, cache-aside, read-through, refresh-ahead, cache invalidation, TTL-based, "
    "event-based, version-based, message queues, Apache Kafka, RabbitMQ, Amazon SQS, Redis Streams, "
    "Apache Pulsar, NATS, ZeroMQ, databases, PostgreSQL, MySQL, Oracle, SQL Server, SQLite, MongoDB, "
    "Cassandra, DynamoDB, CouchDB, Redis, Memcached, Elasticsearch, Neo4j, Amazon Neptune, InfluxDB, "
    "TimescaleDB, ClickHouse, Apache Druid.\n\n"
    "SOFTWARE ENGINEERING: SOLID principles, Single Responsibility, Open-Closed, Liskov Substitution, "
    "Interface Segregation, Dependency Inversion, DRY, KISS, YAGNI, design patterns, singleton, factory, "
    "abstract factory, builder, prototype, adapter, bridge, composite, decorator, facade, flyweight, proxy, "
    "chain of responsibility, command, interpreter, iterator, mediator, memento, observer, state, strategy, "
    "template method, visitor, repository pattern, unit of work, CQRS, event sourcing, saga pattern, "
    "circuit breaker, bulkhead, retry, timeout, rate limiting, API gateway, service mesh, sidecar proxy, "
    "service discovery, health checking, distributed tracing, centralized logging, metrics collection, "
    "alerting, chaos engineering, blue-green deployment, canary deployment, rolling deployment, feature flags, "
    "A/B testing, trunk-based development, GitFlow, continuous integration, continuous delivery, "
    "continuous deployment, infrastructure as code, Terraform, Pulumi, CloudFormation, Ansible, Chef, "
    "Puppet, Docker, Kubernetes, Helm, Istio, Envoy, Prometheus, Grafana, ELK stack, Jaeger, Zipkin.\n\n"
    "GENERAL KNOWLEDGE: World history from ancient civilizations including Mesopotamia, Egypt, Greece, Rome, "
    "China, India, Persia, Maya, Aztec, Inca through medieval period, Renaissance, Enlightenment, "
    "Industrial Revolution, World War I, World War II, Cold War, decolonization, globalization, "
    "digital revolution, and modern times."
)
SYSTEM = SYSTEM + "\n\n" + SYSTEM + "\n\nADDITIONAL EXPERTISE:\n" + SYSTEM

N = 8
DELAY = 5

QUESTIONS = [
    "What is 2+2? Answer briefly.",
    "Explain quicksort in one sentence.",
    "What is the CAP theorem? One line answer.",
]


def send(question, user_id=None):
    p = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 30,
        "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": [{"type": "text", "text": question, "cache_control": {"type": "ephemeral"}}]}],
    }
    if user_id:
        p["metadata"] = {"user_id": user_id}
    t0 = time.time()
    r = requests.post(URL, headers=HEADERS, json=p, timeout=120)
    elapsed = time.time() - t0
    d = r.json()
    if "error" in d:
        return "ERROR", 0, 0, elapsed
    u = d.get("usage", {})
    cr = u.get("cache_creation_input_tokens", 0)
    ch = u.get("cache_read_input_tokens", 0)
    return ("HIT" if ch > 0 else ("CREATE" if cr > 0 else "NONE")), ch, cr, elapsed


def run_group(label, question, user_id):
    print(f"\n  --- {label} (uid={repr(user_id) if user_id else 'None'}) ---")
    results = []
    for i in range(N):
        status, ch, cr, elapsed = send(question, user_id)
        results.append(status)
        mark = "[*]" if status == "HIT" else "[ ]"
        print(f"    {mark} #{i+1}  {status:7s}  read={ch:6d}  create={cr:6d}  {elapsed:.1f}s")
        if i < N - 1:
            time.sleep(DELAY)
    hits = results.count("HIT")
    print(f"    => HIT={hits}/{N} ({hits/N*100:.0f}%)")
    return hits, N


if __name__ == "__main__":
    print("=" * 60)
    print(f"  多轮缓存命中率测试")
    print(f"  {len(QUESTIONS)} 轮 x 2组(带uid/无uid) x {N}次")
    print(f"  间隔 {DELAY}s, system ~{len(SYSTEM)//4} tokens")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    summary = []
    for rd, q in enumerate(QUESTIONS):
        print(f"\n{'='*60}")
        print(f"  第 {rd+1} 轮: \"{q}\"")
        print(f"{'='*60}")
        ra = run_group(f"R{rd+1}-A 带uid", q, "cache-test-user-1")
        rb = run_group(f"R{rd+1}-B 无uid", q, None)
        summary.append((q, ra, rb))

    total_a = sum(h for _, (h, _), _ in summary)
    total_b = sum(h for _, _, (h, _) in summary)
    total_n = N * len(QUESTIONS)

    print(f"\n{'='*60}")
    print(f"  汇总 ({len(QUESTIONS)} 轮)")
    print(f"{'='*60}")
    for q, (ah, an), (bh, bn) in summary:
        a_bar = "*" * ah + "." * (an - ah)
        b_bar = "*" * bh + "." * (bn - bh)
        print(f"  \"{q[:35]:35s}\"")
        print(f"    带uid: {ah}/{an} ({ah/an*100:3.0f}%) [{a_bar}]  无uid: {bh}/{bn} ({bh/bn*100:3.0f}%) [{b_bar}]")
    print(f"  {'─'*54}")
    print(f"  总计  带uid: {total_a}/{total_n} ({total_a/total_n*100:.0f}%)  无uid: {total_b}/{total_n} ({total_b/total_n*100:.0f}%)")
