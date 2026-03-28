# CloudWatch EMF Metrics 监控打点

## 概述

本项目通过 CloudWatch Embedded Metric Format (EMF) + **应用内聚合**实现全量监控指标上报。高频请求级指标在内存中按维度聚合，每 60 秒批量 Emit 一次 EMF JSON 到 CloudWatch Logs，CloudWatch 自动提取为 Metrics。

**核心优势：**
- 复用现有 CloudWatch Logs 通道（`logger/cloudwatch.go`），零额外 API 调用
- 应用内聚合：无论 RPM 80 还是 RPM 80,000，每分钟只产生 ~几十条 EMF 日志
- 支持 CloudWatch Statistic Set（Min/Max/Sum/Count），保留分布信息
- 零吞吐瓶颈：不受 `PutLogEvents` 5 次/秒/流的限制

## 架构

```
热路径（每个请求）                       冷路径（每60秒）
─────────────────                       ──────────────
MetricsMiddleware                       Aggregator flush loop
  → logger.RecordRequest()                → aggRequest.flush()  → EMF JSON → CloudWatch Logs
                                          → aggUpstream.flush() → EMF JSON → CloudWatch Logs
api_request.go                            → aggBilling.flush()  → EMF JSON → CloudWatch Logs
  → logger.RecordUpstream()               → aggDB.flush()      → EMF JSON → CloudWatch Logs
                                          → aggRedis.flush()   → EMF JSON → CloudWatch Logs
compatible_handler.go
  → logger.RecordBilling()              RuntimeCollector (每60s)
                                          → 直接 EMF Emit（已是低频）
controller/relay.go
  → logger.RecordChannelFallback()      PipelineReporter (每60s)
                                          → 直接 EMF Emit（已是低频）
GORM Callbacks
  → logger.RecordDB()

Redis Hook
  → logger.RecordRedis()
```

**数据流：**
1. 热路径调用 `Record*()` → 写入内存 map（加锁，纳秒级）
2. 聚合器每 60 秒 flush → 按维度组合生成 EMF JSON
3. EMF JSON 写入 CloudWatch Logs sink → CloudWatch 自动提取 Metrics

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CLOUDWATCH_METRICS_ENABLED` | `false` | 是否启用 EMF 指标上报（需先启用 `CLOUDWATCH_LOG_ENABLED=true`） |
| `CLOUDWATCH_METRICS_NAMESPACE` | `EZModel/API` | CloudWatch Metrics 命名空间 |
| `CLOUDWATCH_LOG_ENABLED` | `false` | 前置条件：CloudWatch Logs 必须启用 |
| `CLOUDWATCH_LOG_GROUP` | - | CloudWatch Logs 日志组名 |
| `CLOUDWATCH_LOG_REGION` | - | CloudWatch 区域 |

## 指标清单

### 一、API 请求层（聚合，middleware/metrics.go → MetricsMiddleware）

| 指标 | 维度 | 单位 | 聚合方式 |
|------|------|------|----------|
| `RequestCount` | Channel / Model | Count | Sum |
| `RequestLatencyMs` | Channel / Model | Milliseconds | Statistic Set (Min/Max/Sum/Count) |
| `ErrorCount` | Channel / Model | Count | Sum |
| `InputTokens` | Channel / Model | Count | Sum |
| `OutputTokens` | Channel / Model | Count | Sum |

### 二、上游渠道健康度（聚合，relay/channel/api_request.go）

| 指标 | 维度 | 单位 | 聚合方式 |
|------|------|------|----------|
| `UpstreamLatencyMs` | Channel | Milliseconds | Statistic Set |
| `UpstreamErrorCount` | Channel | Count | Sum |
| `UpstreamTimeoutCount` | Channel | Count | Sum |
| `ChannelFallbackCount` | Channel | Count | Sum |

### 三、计费与配额（聚合，relay/compatible_handler.go）

| 指标 | 维度 | 单位 | 聚合方式 |
|------|------|------|----------|
| `QuotaConsumed` | Channel | Count | Sum |
| `BillingFailureCount` | Channel | Count | Sum |

### 四、日志管道健康度（直接 Emit，service/usage_log_s3.go, raw_log_s3.go）

| 指标 | 维度 | 单位 | 触发位置 |
|------|------|------|----------|
| `LogQueueDepth` | Pipeline(usage/raw/error) | Count | `reportDropStats` 每60秒 |
| `LogUploadFailureCount` | Pipeline | Count | `flushBatch` 失败时累加 |
| `LogDropCount` | Pipeline | Count | `enqueue` 队列满丢弃时 |

### 五、进程/运行时（直接 Emit，logger/metrics_runtime.go）

| 指标 | 维度 | 单位 | 触发位置 |
|------|------|------|----------|
| `ActiveConnections` | - | Count | middleware/stats.go 的原子计数器 |
| `GoroutineCount` | - | Count | `runtime.NumGoroutine()` |
| `HeapAllocMB` | - | Megabytes | `runtime.ReadMemStats` |
| `GCPauseMs` | - | Milliseconds | 最近一次 GC 暂停时间 |

### 六、DB & Redis（聚合）

| 指标 | 维度 | 单位 | 聚合方式 |
|------|------|------|----------|
| `DBQueryLatencyMs` | Operation(Query/Create/Update/Delete) | Milliseconds | Statistic Set |
| `DBSlowQueryCount` | Operation | Count | Sum |
| `RedisLatencyMs` | Command | Milliseconds | Statistic Set |
| `RedisErrorCount` | Command | Count | Sum |

## 文件结构

```
logger/
  metrics.go              # EMF 核心：Builder、Emit、预定义指标集、EmitPipelineMetrics
  metrics_aggregator.go   # 应用内聚合器：metricSetAggregator、Record*() 公共函数、flush 循环
  metrics_runtime.go      # 运行时指标定时采集器

middleware/
  metrics.go              # MetricsMiddleware + EmitDBMetrics/EmitRedisMetrics + GetActiveConnections

model/
  db_metrics.go           # GORM callback 注册（Before/After Query/Create/Update/Delete）

common/
  redis_metrics_hook.go   # go-redis v8 Hook 实现

relay/
  compatible_handler.go   # emitBillingMetric + context 设置 metric_input/output_tokens

relay/channel/
  api_request.go          # emitUpstreamMetric（上游 HTTP 延迟/错误/超时）

controller/
  relay.go                # emitChannelFallbackMetric（渠道重试/降级）

router/
  relay-router.go         # MetricsMiddleware 挂载

main.go                   # InitMetrics、StartAggregator、DB/Redis hook 注册、RuntimeCollector 启停
```

## 聚合器工作原理

### 内存结构

```
metricSetAggregator
  └── buckets: map[dimKey]*dimBucket
        └── dimBucket
              ├── dims: {"Channel": "aws-claude", "Model": "claude-3-sonnet"}
              └── metrics: map[metricName]*metricValue
                    └── metricValue { Sum, Count, Min, Max }
```

### 聚合规则

- **Counter 类指标**（RequestCount, ErrorCount, InputTokens 等）：Emit `Sum` 值
- **Latency/Gauge 类指标**（RequestLatencyMs, UpstreamLatencyMs 等）：Emit CloudWatch **Statistic Set** `{Min, Max, Sum, Count}`，CloudWatch 可据此计算 Average

### 热路径性能

`Record*()` 函数只做一次 map 查找 + 数值累加，加锁范围极小（~100ns），对请求延迟无可感知影响。

## 成本估算（应用内聚合方案）

| 场景 | EMF 条数/月 | Logs 摄入 | Metrics 费 | 总月费 |
|------|------------|-----------|-----------|--------|
| RPM 80, 3 实例 | ~13 万 | ~0.07 GB ≈ $0.05 | $99 | **~$100** |
| RPM 800, 3 实例 | ~13 万 | ~0.07 GB ≈ $0.05 | $99 | **~$100** |
| RPM 8000, 3 实例 | ~13 万 | ~0.07 GB ≈ $0.05 | $99 | **~$100** |

**Logs 摄入量与请求量完全解耦** — 只取决于维度组合数 × 每分钟 1 条 × 实例数。

## 成本控制要点

1. **维度基数**是成本主因 — 不要把 StatusCode、UserID、TokenID 放进 Dimensions
2. 设置 Logs 短保留期（1-7 天），指标提取后日志可丢弃
3. 聚合方案下 Logs 摄入已极低，无需采样

## 启用步骤

1. 确保 CloudWatch Logs 已启用：
   ```
   CLOUDWATCH_LOG_ENABLED=true
   CLOUDWATCH_LOG_GROUP=your-log-group
   CLOUDWATCH_LOG_REGION=ap-southeast-1
   ```

2. 启用 Metrics：
   ```
   CLOUDWATCH_METRICS_ENABLED=true
   CLOUDWATCH_METRICS_NAMESPACE=EZModel/API   # 可选，默认值
   ```

3. 部署后在 CloudWatch 控制台 → Metrics → Custom Namespaces → `EZModel/API` 查看指标。

## 多实例部署

- 3 个实例各自独立聚合、独立 Emit
- 同维度指标 CloudWatch 自动跨实例聚合
- 不需要额外配置
- 成本不随实例数线性增长（Metrics 费不变，Logs 费 ×N 但极低）

## 告警建议

| 告警 | 条件 | 严重级别 |
|------|------|----------|
| 渠道不可用 | `UpstreamErrorCount / RequestCount > 5%` 持续 5 分钟 | Critical |
| 上游超时 | `UpstreamTimeoutCount > 50` / 5 分钟 | Critical |
| 计费失败 | `BillingFailureCount > 0` | Critical |
| 日志丢弃 | `LogDropCount > 0` | Warning |
| P99 延迟飙升 | `RequestLatencyMs P99 > 30s` 持续 5 分钟 | Warning |
| Goroutine 泄漏 | `GoroutineCount > 10000` | Warning |
| 内存异常 | `HeapAllocMB > 2048` 持续 10 分钟 | Warning |

> 注意：聚合方案下 Latency 指标使用 Statistic Set，CloudWatch 可计算 Average 但**无法精确计算 P99**。
> 如需精确分位数，可对关键路径（如 RequestLatencyMs）改回逐条 Emit 或使用 CloudWatch Logs Insights 查询。

## 扩展指南

添加新指标的步骤：

1. 在 `logger/metrics.go` 中定义 `MetricDef` 和 `Dims`
2. 在 `logger/metrics_aggregator.go` 中：
   - 新增 `aggXxx *metricSetAggregator` 变量
   - 在 `initAggregators()` 中初始化
   - 在 `flushAll()` 中添加 flush 调用
   - 新增 `RecordXxx()` 公共函数
3. 在业务代码中调用 `logger.RecordXxx()`
4. 注意避免循环依赖：`service` 包不能导入 `middleware`，应使用 `logger` 包的函数或回调模式

### 低频指标（已是每分钟级）

Pipeline 和 Runtime 指标已经是每 60 秒触发一次，不需要走聚合器，直接使用 `NewEMF().Emit()` 即可。
