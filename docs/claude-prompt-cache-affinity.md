# Claude Prompt Cache 亲和路由架构设计

## 1. 背景

### 1.1 业务现状

站点对接了多个上游 MAAS 供应商来提供 Claude 资源。用户在使用 Claude 模型时，通过 `cache_control: {"type": "ephemeral"}` 标记 system prompt 或 messages 中的内容块，期望利用 Anthropic 的 Prompt Caching 能力降低延迟和成本。

### 1.2 问题

当前缓存命中率不理想。根本原因是请求路径上存在**两层随机性**，导致相同 prompt 难以命中同一缓存：

```
用户请求
  │
  ├─ 第一层随机：站点按权重随机选择上游渠道（GetRandomSatisfiedChannel）
  │    → 同一用户的连续请求可能被分配到不同的上游供应商
  │
  └─ 第二层随机：上游供应商内部负载均衡
       → 请求可能被分配到不同的 Anthropic 后端节点
```

### 1.3 Claude Prompt Caching 机制

| 属性 | 说明 |
|------|------|
| 缓存粒度 | 按 prompt prefix 内容精确匹配（逐 token 比对） |
| 缓存位置 | 绑定在 Anthropic 后端的特定服务器节点 |
| 缓存 TTL | ephemeral 类型为 5 分钟（每次命中刷新 TTL） |
| 最小 token 数 | Claude Opus 4.6: 4096 tokens; Sonnet: 2048; Haiku: 1024 |
| 缓存 key 构成 | model + system blocks + messages（按顺序，到最后一个 cache_control 标记为止） |

关键约束：**缓存是节点级别的**，不同节点之间不共享缓存。因此，要提高命中率，必须确保相同 prompt 的请求尽可能路由到同一个后端节点。

---

## 2. 现有架构分析

### 2.1 当前渠道选择流程

```
middleware/distributor.go  Distribute()
        │
        ▼
service/channel_select.go  CacheGetRandomSatisfiedChannel()
        │
        ▼
model/channel_cache.go     GetRandomSatisfiedChannel()
        │
        ├─ 按 group + model 查找可用渠道列表
        ├─ 按 Priority 排序，选择当前优先级档位
        └─ 同优先级内按 Weight 加权随机选择
```

### 2.2 问题定位

`GetRandomSatisfiedChannel` 的选择逻辑是**纯随机**的（加权随机），不考虑请求内容。这意味着：

- 用户 A 发送带缓存的请求 → 随机选到渠道 1（供应商 X）→ 缓存创建在供应商 X 的节点 α
- 用户 A 发送相同请求 → 随机选到渠道 2（供应商 Y）→ 缓存未命中，重新创建
- 用户 A 再次发送 → 随机选到渠道 1（供应商 X）→ 但供应商 X 内部可能路由到节点 β → 仍然未命中

假设有 N 个等权重渠道，单次请求命中同一渠道的概率仅为 1/N。

---

## 3. 设计目标

1. **相同 prompt 模式的请求始终路由到同一上游渠道**，消除第一层随机性
2. **向上游传递亲和性信息**，协助消除第二层随机性（需上游配合）
3. **渠道不可用时平滑降级**，不影响可用性
4. **对无缓存请求零影响**，保持现有负载均衡行为

---

## 4. 架构方案

### 4.1 整体流程

```
请求进入
  │
  ▼
解析请求，检测是否包含 cache_control
  │
  ├─ 无 cache_control
  │    └─ 走现有 GetRandomSatisfiedChannel 逻辑（不变）
  │
  └─ 有 cache_control
       │
       ▼
  计算 Cache Affinity Key（prompt fingerprint）
       │
       ▼
  查询本地亲和表 (AffinityMap)
       │
       ├─ 命中且渠道可用且未过期
       │    └─ 直接路由到记录的渠道（+ Key Index）
       │
       └─ 未命中 / 已过期 / 渠道不可用
            │
            ▼
       一致性哈希选择渠道
            │
            ▼
       记录到亲和表（TTL = 5min）
            │
            ▼
       转发请求（注入 X-Cache-Affinity-Key Header）
```

### 4.2 Cache Affinity Key 生成

Affinity Key 是请求中缓存相关内容的指纹，用于标识"哪些请求应该路由到同一个地方"。

**生成规则：**

```
affinity_key = SHA256(model + sorted_cache_blocks)[:16]
```

其中 `sorted_cache_blocks` 是请求中所有带 `cache_control` 标记的内容块，按出现顺序拼接：

1. system 消息中带 `cache_control` 的 text 块
2. messages 中带 `cache_control` 的 content 块

**示例：**

```json
{
  "model": "claude-sonnet-4-20250514",
  "system": [
    {
      "type": "text",
      "text": "You are a helpful coding assistant...(very long prompt)",
      "cache_control": {"type": "ephemeral"}
    }
  ],
  "messages": [...]
}
```

→ `affinity_key = SHA256("claude-sonnet-4-20250514" + system_text)[:16]`

**设计考量：**

- 只取带 `cache_control` 的块，因为只有这些块会被 Anthropic 缓存
- 包含 model 名称，因为不同模型的缓存不互通
- 使用 SHA256 前 16 字节，碰撞概率极低且节省内存
- 不包含 messages 中的用户消息（除非也带 cache_control），因为 Anthropic 的缓存是 prefix-based 的

### 4.3 本地亲和表 (Affinity Map)

```go
type CacheAffinityEntry struct {
    ChannelID    int       // 上次使用的渠道 ID
    KeyIndex     int       // 多 Key 场景下的具体 Key 索引
    CreatedAt    time.Time // 创建时间
    LastHitAt    time.Time // 最后命中时间
    HitCount     int64     // 命中次数（监控用）
    TTL          time.Duration // 过期时间，默认 5 分钟
}

// 使用 sync.Map 或分片 map，key 为 affinity_key (string)
var cacheAffinityMap sync.Map
```

**生命周期管理：**

| 事件 | 行为 |
|------|------|
| 首次请求（cache creation） | 创建条目，TTL = 5min |
| 后续请求命中亲和表 | 刷新 LastHitAt，HitCount++ |
| 响应中 cache_read > 0 | 确认缓存有效，刷新 TTL |
| 响应中 cache_creation > 0 | 缓存被重建（可能节点变了），更新条目 |
| TTL 过期 | 惰性删除 + 定期 GC（每 1 分钟扫描） |
| 渠道被禁用 | 删除该渠道的所有亲和条目 |

**内存估算：**

- 每个条目约 100 bytes
- 1 万个活跃 prompt 模式 ≈ 1 MB
- 完全可以放在内存中，无需持久化

### 4.4 一致性哈希选择

当亲和表未命中时，使用一致性哈希（而非随机）选择渠道，确保相同 affinity_key 在渠道集合不变时始终选择同一渠道。

```go
type ConsistentHash struct {
    ring     []uint32          // 排序的哈希环
    nodeMap  map[uint32]int    // hash -> channelID
    replicas int               // 每个节点的虚拟节点数
}

func (h *ConsistentHash) Get(key string) int {
    hash := crc32.ChecksumIEEE([]byte(key))
    idx := sort.Search(len(h.ring), func(i int) bool {
        return h.ring[i] >= hash
    })
    if idx >= len(h.ring) {
        idx = 0
    }
    return h.nodeMap[h.ring[idx]]
}
```

**参数选择：**

- 虚拟节点数：150（平衡均匀性和内存）
- 哈希函数：CRC32（速度快，一致性哈希场景够用）
- 权重支持：高权重渠道分配更多虚拟节点

**渠道变更处理：**

- 渠道增加：只影响哈希环上相邻的少量 key 映射
- 渠道减少：该渠道的 key 自动迁移到环上下一个节点
- 渠道权重变化：重建哈希环（低频操作）

### 4.5 上游亲和性 Header

在转发请求到上游时，注入亲和性 Header，供上游供应商做内部路由优化：

```
X-Cache-Affinity-Key: <affinity_key_hex>
```

上游供应商可以：
- 基于此 key 做内部一致性哈希，将请求路由到固定的 Anthropic 后端节点
- 忽略此 Header（向后兼容，不影响现有行为）

**需与上游供应商协商确认：**

1. 是否支持接收亲和性 Header
2. Header 名称和格式约定
3. 他们内部是否已有类似机制（避免重复）

### 4.6 降级策略

```
亲和渠道不可用？
  │
  ├─ 渠道被禁用 → 从亲和表删除，走一致性哈希选下一个
  ├─ 渠道请求失败 → 现有重试机制接管（retry 选下一优先级）
  └─ 亲和表 GC 延迟 → 惰性检查渠道状态，不可用则跳过
```

降级后的请求会创建新缓存（cache_creation），亲和表更新为新渠道，后续请求继续保持亲和。

---

## 5. 代码改动范围

### 5.1 新增文件

| 文件 | 说明 |
|------|------|
| `service/cache_affinity.go` | 亲和表管理、affinity key 计算、一致性哈希 |
| `service/consistent_hash.go` | 一致性哈希环实现 |

### 5.2 修改文件

| 文件 | 改动 |
|------|------|
| `middleware/distributor.go` | 在 `Distribute()` 中检测 cache_control，调用亲和路由 |
| `service/channel_select.go` | 新增 `CacheGetAffinityChannel()` 方法 |
| `model/channel_cache.go` | `CacheUpdateChannelStatus` 中清理亲和表 |
| `relay/channel/claude/relay-claude.go` | 注入 `X-Cache-Affinity-Key` Header |
| `relay/channel/claude/relay-claude.go` | 响应处理中更新亲和表（确认 cache hit/creation） |

### 5.3 伪代码：核心选择逻辑

```go
// service/cache_affinity.go

func GetChannelForCacheRequest(
    c *gin.Context,
    group, model string,
    affinityKey string,
) (*model.Channel, error) {
    // 1. 查亲和表
    if entry, ok := cacheAffinityMap.Load(affinityKey); ok {
        e := entry.(*CacheAffinityEntry)
        if time.Since(e.LastHitAt) < e.TTL {
            ch, err := model.CacheGetChannel(e.ChannelID)
            if err == nil && ch.Status == common.ChannelStatusEnabled {
                e.LastHitAt = time.Now()
                e.HitCount++
                return ch, nil
            }
            // 渠道不可用，删除条目
            cacheAffinityMap.Delete(affinityKey)
        } else {
            // 已过期，删除
            cacheAffinityMap.Delete(affinityKey)
        }
    }

    // 2. 一致性哈希选择
    channels := getAvailableChannels(group, model)
    if len(channels) == 0 {
        return nil, errors.New("no available channel")
    }

    ring := buildConsistentHashRing(channels)
    selectedID := ring.Get(affinityKey)
    ch, err := model.CacheGetChannel(selectedID)
    if err != nil {
        // 降级到随机选择
        return model.GetRandomSatisfiedChannel(group, model, 0)
    }

    // 3. 记录到亲和表
    cacheAffinityMap.Store(affinityKey, &CacheAffinityEntry{
        ChannelID: ch.Id,
        CreatedAt: time.Now(),
        LastHitAt: time.Now(),
        TTL:       5 * time.Minute,
    })

    return ch, nil
}
```

### 5.4 伪代码：Affinity Key 提取

```go
// service/cache_affinity.go

func ExtractAffinityKey(req *dto.GeneralOpenAIRequest) string {
    // 仅在请求包含 cache_control 时生成 affinity key
    h := sha256.New()
    h.Write([]byte(req.Model))

    hasCacheControl := false

    // 检查 system 消息
    if req.System != nil {
        // system 可能是 string 或 []MediaContent
        for _, block := range req.ParsedSystemContent {
            if block.CacheControl != nil {
                hasCacheControl = true
                h.Write([]byte(block.Text))
            }
        }
    }

    // 检查 messages 中的 cache_control
    for _, msg := range req.Messages {
        if content, ok := msg.ParsedContent(); ok {
            for _, block := range content {
                if block.CacheControl != nil {
                    hasCacheControl = true
                    h.Write([]byte(block.Text))
                }
            }
        }
    }

    if !hasCacheControl {
        return "" // 无缓存标记，走正常路由
    }

    sum := h.Sum(nil)
    return hex.EncodeToString(sum[:16])
}
```

---

## 6. 监控与可观测性

### 6.1 关键指标

| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| `cache_affinity_hit_rate` | 亲和表命中率 | < 50% 告警 |
| `cache_affinity_map_size` | 亲和表条目数 | > 100K 告警 |
| `upstream_cache_hit_rate` | 上游实际缓存命中率（cache_read > 0 的比例） | < 30% 需排查 |
| `upstream_cache_creation_rate` | 缓存创建率 | 持续 > 70% 说明亲和失效 |
| `affinity_channel_unavailable` | 亲和渠道不可用降级次数 | 突增告警 |

### 6.2 日志

```
[CacheAffinity] key=abc123 action=hit channel=5 hit_count=42
[CacheAffinity] key=def456 action=miss -> consistent_hash -> channel=3
[CacheAffinity] key=abc123 action=degrade channel=5 reason=disabled -> channel=7
```

### 6.3 效果评估

上线后对比以下数据（按天聚合）：

```sql
-- 缓存命中率变化
SELECT
    DATE(created_at) AS day,
    SUM(cached_tokens) AS total_cache_read,
    SUM(cached_creation_tokens) AS total_cache_creation,
    ROUND(SUM(cached_tokens) * 100.0 /
        NULLIF(SUM(cached_tokens) + SUM(cached_creation_tokens), 0), 2
    ) AS cache_hit_rate_pct
FROM logs
WHERE model_name LIKE 'claude-%'
    AND (cached_tokens > 0 OR cached_creation_tokens > 0)
GROUP BY DATE(created_at)
ORDER BY day;
```

---

## 7. 上游供应商协作要点

### 7.1 需确认的问题

| # | 问题 | 目的 |
|---|------|------|
| 1 | 是否支持缓存亲和路由（如接收 `X-Cache-Affinity-Key` Header）？ | 消除第二层随机性 |
| 2 | Claude 后端节点池规模有多大？ | 评估随机命中概率 |
| 3 | 是否已在做 prompt hash 路由？ | 避免重复优化 |
| 4 | 是否支持将 API Key 绑定到特定节点池？ | 利用多 Key 轮询做分区 |
| 5 | 缓存 TTL 实际表现是否为 5 分钟？是否有延长机制？ | 校准亲和表 TTL |

### 7.2 理想合作模式

```
我方                              上游供应商
 │                                    │
 │  X-Cache-Affinity-Key: abc123      │
 ├───────────────────────────────────►│
 │                                    ├─ 基于 key 一致性哈希
 │                                    ├─ 路由到固定 Claude 节点
 │  cache_read_input_tokens: 4096     │
 │◄───────────────────────────────────┤
```

如果上游不支持亲和路由，我方的一致性哈希仍然能保证请求始终到达同一供应商，由供应商内部的缓存机制尽力命中。

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 亲和导致负载不均 | 热门 prompt 集中在少数渠道 | 一致性哈希 + 权重虚拟节点天然分散；极端情况下可设置单渠道并发上限 |
| 渠道频繁上下线 | 亲和表大量失效，缓存重建 | 一致性哈希最小化迁移；渠道恢复后自动重新亲和 |
| 亲和表内存泄漏 | 内存持续增长 | 定期 GC（每分钟）+ 条目上限（100K） |
| Affinity Key 碰撞 | 不同 prompt 路由到同一渠道 | SHA256 前 128 bit，碰撞概率 ~2^-64，可忽略 |
| 上游供应商不配合 | 第二层随机性无法消除 | 我方一致性哈希仍有效；长期推动供应商支持 |

---

## 9. 分阶段实施计划

### Phase 1：站点层一致性哈希（1-2 天）

- 实现 Affinity Key 提取
- 实现一致性哈希渠道选择
- 在 `Distribute()` 中集成，检测 `cache_control` 走亲和路由
- 添加基础日志

**预期效果：** 消除第一层随机性，缓存命中率提升与渠道数成正比（N 个渠道 → 命中率提升约 N 倍）

### Phase 2：本地亲和表（1 天）

- 实现亲和表数据结构和生命周期管理
- 响应回调更新亲和表
- 渠道状态变更联动清理
- 添加监控指标

**预期效果：** 进一步提升命中率，减少一致性哈希在渠道变更时的缓存重建

### Phase 3：上游协商与 Header 注入（视供应商配合）

- 与各上游供应商沟通亲和路由方案
- 实现 `X-Cache-Affinity-Key` Header 注入
- 按供应商逐步灰度上线

**预期效果：** 消除第二层随机性，缓存命中率达到理论最优

### Phase 4：监控与调优（持续）

- 上线效果评估 SQL
- 按渠道/供应商维度分析命中率
- 调优亲和表 TTL、一致性哈希参数
- 考虑按用户维度的亲和（如果上游按用户隔离缓存）

---

## 10. 附录

### A. Anthropic Prompt Caching 定价

| Token 类型 | 价格倍率（相对 input） |
|------------|----------------------|
| Base input | 1x |
| Cache write (creation) | 1.25x |
| Cache read (hit) | 0.1x |

缓存命中时成本降低 90%，这是优化缓存命中率的核心经济动力。

### B. 当前渠道选择代码位置

```
model/channel_cache.go:96     GetRandomSatisfiedChannel()  -- 加权随机选择
service/channel_select.go:14  CacheGetRandomSatisfiedChannel()  -- 入口
middleware/distributor.go:101  Distribute()  -- 调用点
controller/relay.go:159       Relay()  -- 重试逻辑
```

### C. 相关测试脚本

```
scripts/test_cache.py       -- 基础缓存创建/命中测试
scripts/test_cache_hit.py   -- metadata 对缓存影响的交叉测试
scripts/test_cache_raw.py   -- 原始 HTTP 请求观察
```
