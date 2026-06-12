# 评估：是否迁移到官方「表达式计费引擎」(billingexpr)

> 类型：纯调研评估，不改动业务代码。
> 范围：对比我们现状的「固定档位价格表」计费范式与上游官方的「表达式引擎」(`pkg/billingexpr`) 计费范式，评估迁移价值、路径、对账冲击、工作量与风险，并给出明确建议。
> 结论先行：**当前不建议全量迁移；建议「部分采纳 + 观望」**——优先在我们现有结构上补「按请求头/体条件计费」能力，仅当出现明确业务需求（时段折扣、service_tier 差异计费、多模态统一公式批量化）时再评估渐进引入表达式引擎。核心理由见第 5 节。

---

## 0. 两种范式速览

| 维度 | 我们现状（固定档位价格表） | 官方（表达式引擎 billingexpr） |
|---|---|---|
| 配置载体 | `tieredPricingMap`（结构化档位）+ `modelRatioMap`/`modelPriceMap` + `imageRatioMap`/`audioRatioMap` | 每模型一条字符串表达式 `billing_expr` + 模式开关 `billing_mode` |
| 计费逻辑 | Go 代码硬编码（分段 > ModelPrice > ModelRatio），档位按输入 token K 区间匹配 | 表达式自身即逻辑，`expr-lang/expr` 编译执行，AST 自省决定 token 归一 |
| 价格语义 | 档位内 `InputPrice/OutputPrice/CacheHitPrice/CacheStorePrice(+5m/1h)`，均为 $/M | 表达式系数即真实 $/1M（`p*2.5` = $2.5/1M），无倍率换算 |
| 条件能力 | 仅「输入 token 档位」一个维度 | token 档位 + 时段 + 请求头 + 请求体 + 任意数学/逻辑组合 |
| 多模态 | 走独立 `imageRatioMap`/`audioRatioMap`，与文本计费分离 | `img/img_o/ai/ao` 变量统一进同一公式 |
| 防重复计费 | 代码内手工拆分 token（如 cache 单独减） | AST 自省「自动排除」：用了 `cr` 才从 `p` 减 cache |
| 对账侧 | `pricing.json`（`tiers` 结构与 Go 一一对应）+ `pricing_engine.py` 复算 | 表达式只存在于运行时，对账侧**无对应结构** ⚠️ |

---

## 1. 能力差距分析

### 1.1 官方表达式引擎能做、我们做不到的

参考 `pkg/billingexpr/expr.md` 的设计与 `run.go` 暴露的内置函数：

1. **时段折扣 / 按时间计费**
   - 内置 `hour(tz)/minute(tz)/weekday(tz)/month(tz)/day(tz)`，可写「夜间折扣」「周末折扣」「整点活动价」。
   - 例：`hour("Asia/Shanghai") >= 0 && hour("Asia/Shanghai") < 8 ? tier("night", p*1.5+c*7.5) : tier("day", p*3+c*15)`。
   - 我们现状**完全无法表达时间维度**——价格表是静态的，只能靠人工改配置切换。

2. **按请求头条件计费（Claude fast-mode / service_tier 等）**
   - `header("anthropic-beta")` + `has(...)` + `|||` 请求规则可对「fast-mode」请求加价（`expr.md` 示例：`...|||when(header("anthropic-beta") has "fast-mode") * 6`）。
   - `param("service_tier")` 读请求体 JSON 路径，可对 `service_tier=fast/priority` 等做差异计费。
   - 我们现状**没有任何「按请求特征改价」的钩子**——计费链路只看 token 数和模型名，对 fast-mode/priority tier 这类「同模型不同 SLA 不同价」无能为力。这是当前最实际的能力缺口（Claude/OpenAI 都已上线 service tier 差异定价）。

3. **多模态统一公式**
   - `img/img_o/ai/ao` 与 `p/c` 在同一表达式里，便于表达「文本 + 图片输入 + 音频输入 + 音频输出」复合定价。
   - 我们现状图片/音频走独立 `imageRatioMap`/`audioRatioMap`，且**与分段档位互斥**（分段路径只处理 input/output/cache，多模态走另一条 ModelRatio 路径），难以表达「分段 + 多模态」交叉。

4. **自动排除（防重复计费）做成机制而非靠人工**
   - 上游通过 AST 自省 `usedVars`：表达式引用了 `cr` 才从 `p` 里减 cache，引用了 `img` 才减图片（见 `compile.go: extractUsedVars` + `service/tiered_settle.go: BuildTieredTokenParams`）。GPT 格式下尤其关键（`prompt_tokens` 含全部子类）。
   - 我们现状是在 `service/quota.go` 里**手工**按字段拆 token、手工记录 `tiered_*` 价格到 `other`。逻辑正确但易随新增 token 子类（如图片输入 token）出现遗漏或重复计费。

5. **任意逻辑组合 / `max`/`min`/`ceil`/`floor`**
   - 可表达「保底价」「封顶价」「阶梯叠加」等复杂规则，无需改 Go 代码、无需发版。
   - 我们现状任何新计费形态都要改 `price.go`/`quota.go` 并走 ECS 发版。

### 1.2 我们现状已能覆盖的常见场景

要点：**绝大多数日常计费场景，我们现有结构已经覆盖且运行稳定。**

1. **输入 token 长上下文分档**——`tieredPricingMap` 的核心场景，已在用：
   - GPT-5.5 >272K 输入 2x/输出 1.5x（`tiered_pricing.go` 内置默认）；
   - Claude Sonnet/Opus 200K 分档（`pricing.json` 已配 2 档）。
   - 等价于官方 `len <= 200000 ? tier(...) : tier(...)` 示例。
2. **缓存精细计费**——`CacheHitPrice` + `CacheStorePrice5m/1h`，已区分 Claude 5m/1h TTL（`relay/helper/price.go` + `service/quota.go` 的 `tiered_cache_*` 字段）。
3. **模型名通配**——`matchWildcard`（`doubao-seed-*`）等价表达式按模型名 key 配置。
4. **分组倍率 / 用户特殊倍率**——`HandleGroupRatio`，这部分**两套范式都依赖**，不在迁移范围内。
5. **多模态（图片生成）**——`imageRatioMap` + 对账侧 `multimodal` 类型（`pricing.json` 的 Gemini image 模型 `ip/op_text/op_image`）。
6. **优先级覆盖**——分段 > ModelPrice > ModelRatio，逻辑清晰、可预测。

**小结**：官方引擎的增量能力集中在「时间维度」「请求条件维度」「多模态统一表达」「自动排除机制化」四块。前两块我们**完全做不到**，是真实差距；后两块我们**能做但靠人工**，是工程质量差距而非功能空白。

---

## 2. 迁移路径

### 2.1 若采纳，需要引入的组件

| 层 | 需引入/改造 | 来源 |
|---|---|---|
| 表达式引擎 | `pkg/billingexpr/` 整包（compile/run/settle/round/types）+ 依赖 `github.com/expr-lang/expr`、`github.com/tidwall/gjson` | `git show upstream/main:pkg/billingexpr/` |
| 存储 | `setting/billing_setting/tiered_billing.go`：DB option 键 `billing_setting.billing_mode` / `billing_setting.billing_expr`；`GetPricingSyncData` 把两者并入定价同步 | upstream |
| 预扣费 | `relay/helper/price.go` 增 `modelPriceHelperTiered()` 分支 + `relay/helper/billing_expr_request.go`（构造 `RequestInput` 供 `header()/param()`） | upstream |
| 结算 | `service/tiered_settle.go`（`BuildTieredTokenParams` + `TryTieredSettle`）+ `service/quota.go` 接入冻结快照 `BillingSnapshot` | upstream |
| 日志 | `service/log_info_generate.go`：`InjectTieredBillingInfo()` 写 `billing_mode/expr_b64/matched_tier` 到 `other` | upstream |
| 前端 | `web/src/pages/Setting/Ratio/components/TieredPricingEditor.jsx`（可视化 + 原始两种编辑模式、SmokeTest 校验、模板）+ 日志/明细展示侧解析 `expr_b64` | upstream |

依赖与可序列化设计良好：`BillingSnapshot` 不含编译指针、完全可 JSON 化，编译结果按 SHA-256 缓存（`compile.go`），运行期成本低。

### 2.2 与我们重度定制部分的共存/替换关系

**冲突热点**（我们已深度定制，与官方实现重叠）：

- `relay/helper/price.go` 的 `ModelPriceHelper`：我们已加分段分支 + Claude200K 预扣乘数（`GetClaude200KMultipliers`）+ 自用模式错误文案。官方在同一函数加 `tiered_expr` 分支。**两者改的是同一函数，合并时需手工裁剪**，不能直接覆盖。
- `service/quota.go`：我们已有大段 `tiered_*` 字段写入 + Claude200K 输入/输出乘数逻辑。官方用 `TryTieredSettle` 替代。**直接替换会丢失我们的 Claude200K 与既有 `other` 字段语义**，导致历史日志/对账字段不一致。
- `setting/ratio_setting/tiered_pricing.go`、`model_ratio.go`：官方表达式范式下，这些档位表/倍率表理论上可被表达式取代，但我们对账强依赖它们的结构（见第 3 节）。

**两种共存策略对比：**

| 策略 | A. 全量替换 | B. 渐进并存（推荐） |
|---|---|---|
| 做法 | 所有模型迁到 `billing_expr`，废弃 `tieredPricingMap`/部分 ratio 表 | 保留现状为默认；仅对「需要表达式能力」的模型设 `billing_mode=tiered_expr`，其余仍走 ratio/tiered |
| 优先级链 | 表达式成为唯一真相 | `billing_mode==tiered_expr` 时走表达式，否则回落现有「分段>ModelPrice>ModelRatio」 |
| 代码改动 | 大：删除/重写计费链路 | 中：在 `ModelPriceHelper` 入口加一个 mode 判断分支（官方本来就是这么做的） |
| 回归风险 | 高：全模型计费行为变化 | 低：未开启的模型行为零变化 |
| 对账冲击 | 全量：对账侧必须实现表达式求值 | 局部：仅开启表达式的模型需对账侧适配 |
| 回滚 | 难 | 易：关掉 mode 即回落 |

**结论：若迁移，必须走 B（渐进并存）**。官方设计本身就是 mode 开关式并存（`GetBillingMode` 默认 `ratio`），天然支持灰度。全量替换在我们这种「重度定制 + 强对账」的环境下风险不可控。

---

## 3. 对账体系冲击（最高风险点，重点）

这是整个评估**最敏感、最可能踩雷**的部分。

### 3.1 现状对账为何能成立

对账侧（`scripts/athena/pricing_engine.py` + `pricing.json` + `discounts.json`）能独立复算账单，**前提是计费规则是「结构化、可在 Athena 侧重建」的**：

- `pricing.json` 的 `tiers`/`flat`/`multimodal` 结构与 Go 端 `tieredPricingMap`/`imageRatioMap` **一一对应**；
- `pricing_engine.py` 用 `prompt_tokens // 1000` 选档（`_assign_prices`），与 Go 端 `GetPriceTierForTokens` 同算法；
- 即便如此，对账还做了双保险：优先用日志 `other` 里**系统实记的** `tiered_input_price/...`（`is_new` 分支 `recalc_from_raw`），lookup 表只是兜底。
- 也就是说：**对账目前同时持有「规则副本（pricing.json）」和「逐条快照（other 字段）」两套真相**，可交叉验证。

### 3.2 改用表达式后，对账面临的根本问题

表达式是**运行时字符串 + 请求上下文求值**，对账侧若仍靠「结构化规则副本」复算就**失效了**，因为：

1. **规则不再结构化**——`billing_expr` 是一行代码，`pricing.json` 的 `tiers` 字段无法表达 `hour()/header()/param()` 等条件。Athena 侧拿不到这些维度的规则定义。
2. **计费依赖请求上下文**——`header("anthropic-beta")`、`param("service_tier")` 的值在 S3 离线日志里**未必完整保留**。若表达式依赖请求头/体，而日志 `other` 没存这些字段，对账**无法重建求值环境**。
3. **时间维度不可复现**——`hour(tz)` 取的是「计费发生那一刻」的时间。离线对账只能拿 `created_at`，需保证 tz 与求值口径完全一致，否则边界时刻（如 07:59:59）会算错档。

### 3.3 三条对账保持一致的可选方案

| 方案 | 做法 | 优点 | 缺点/风险 |
|---|---|---|---|
| **方案一：Python 侧实现表达式求值器** | 在 `pricing_engine.py` 引入等价的表达式解析/求值（Python 端复刻 `expr-lang` 语义 + 内置函数 + 自动排除 AST 自省 + v1 quota 换算） | 对账保持「规则副本独立复算」的能力 | **极高成本与极高一致性风险**：要 1:1 复刻 Go `expr-lang/expr` 行为、`gjson` 路径语义、时区、round 规则（`QuotaRound` half-away-from-zero）、自动排除 AST 逻辑。任何细微差异都变成「对账偏差」。**不推荐。** |
| **方案二：逐条计费快照（强烈推荐）** | 计费时把求值所需的一切落到日志 `other`：表达式 hash/版本、命中 tier、各 token 子类拆分、最终 quota，必要时连求值用到的 header/param 值也快照 | 对账退化为「核对快照自洽性 + 与供应商账单 crosscheck」，**不需要在 Athena 侧重跑表达式**；与现状 `is_new` 分支思路一致，平滑延续 | 依赖「快照字段足够全」；对「表达式误配」类问题，对账只能发现「我们内部前后不一致」需结合供应商账单兜底；`expr_b64` 仅供展示，不足以复算条件类计费 |
| **方案三：双轨过渡** | 迁移期对开启表达式的模型，同时保留结构化档位 + 表达式，两边算一遍存日志，定期 diff | 迁移期安全网，能量化「新旧计费偏差」 | 临时方案，代码与存储双倍开销，不可长期 |

**建议组合**：若真迁移，**以方案二为对账主干**（计费快照），**方案三作迁移期验证**（双算 diff），**绝不走方案一**（Python 复刻求值器一致性风险过高）。

### 3.4 对账侧必须新增的字段（若采纳方案二）

至少需在 `other` 落地并被 `pricing_engine.py` 消费：
- `billing_mode`、`expr_version`、`expr_hash`（识别用哪条规则）；
- `matched_tier`、`expr_cost`（求值原始 $）、`final_quota`（换算后）；
- 各 token 子类拆分（`p/c/cr/cc/cc1h/img/img_o/ai/ao` 的实际值，对应 `BuildTieredTokenParams` 的归一结果）；
- 若表达式含条件：被引用的 `header()/param()` 实际取值快照。

> `pricing.json` 的 `tiers` 结构对「表达式模型」将不再适用，需要在 `pricing_engine.py` 增一条「expr 模型走快照、不查 lookup」的分支，类似现有 `is_new` 双保险但更彻底。

---

## 4. 工作量与风险

### 4.1 粗略工作量（按模块，含合并已有定制的额外成本）

| 模块 | 工作内容 | 量级 |
|---|---|---|
| 后端-引擎引入 | 移植 `pkg/billingexpr/` + 加依赖 + 单测 | 中（1~2 人日，含 SmokeTest） |
| 后端-存储 | `billing_setting` 接入 config 注册 + 定价同步 | 小（0.5 人日） |
| 后端-计费链路合并 | 在我们已定制的 `price.go`/`quota.go` 上**安全合并** mode 分支，保住 Claude200K 预扣/输出乘数与既有 `other` 字段 | **高（3~5 人日，最易出回归）** |
| 前端-编辑器 | 移植 `TieredPricingEditor.jsx`（可视化+原始模式+模板+校验） | 中（2~3 人日） |
| 前端-展示 | 日志/明细解析 `expr_b64`、命中 tier 展示 | 小~中（1~2 人日） |
| **对账适配（重点）** | `pricing_engine.py` 增 expr 快照分支 + 新 `other` 字段消费 + 迁移期双算 diff 脚本 | **高（3~5 人日，且需长期验证）** |
| 测试/灰度 | 端到端计费回归、双算对比、灰度上线监控 | 高（贯穿） |

合计粗估 **13~20 人日**，关键路径在「计费链路合并」与「对账适配」两块（均为高风险高工时）。

### 4.2 主要风险

1. **计费回归（最高）**——`price.go`/`quota.go` 已重度定制（Claude200K、自用模式、既有 tiered 字段）。合并官方分支若处理不当，会改变**未迁移模型**的计费行为或破坏历史 `other` 字段语义。
2. **对账偏差**——一旦运行时改用表达式而对账仍按结构化复算，账单会对不上；方案一（Python 复刻求值）尤其会引入持续性微差（round/时区/AST 自动排除不一致）。
3. **表达式误配**——一行字符串即生产计费规则，写错系数/条件直接造成多收或少收。SmokeTest 只校验「非负 + 可编译」，**不校验金额正确性**。需要强制评审 + 双算 diff + 灰度。
4. **请求上下文依赖导致不可复算**——条件计费用到的 header/param 若未快照进日志，离线对账无法重建。
5. **性能**——表达式编译有缓存（SHA-256 keyed，`maxCacheSize=256`），单次求值成本低；风险点是缓存被频繁失效（规则频繁改）或表达式数量超 256 触发整表重建。常规规模下可忽略。
6. **多真相源漂移**——迁移期同时存在 `tieredPricingMap`、`pricing.json`、`billing_expr` 三套，若不统一来源会出现「改了一处忘改另一处」。

---

## 5. 明确建议

### 5.1 总体结论：**部分采纳 + 观望**，当前不全量迁移

**理由：**

1. **真实功能缺口只有两块**：时段计费、按请求头/体条件计费。其余（长上下文分档、缓存精细计费、多模态、通配）我们**现状已覆盖且稳定**。为两块尚无明确业务需求的能力，去承担「计费链路大改 + 对账体系重构」的高风险，性价比不足。
2. **对账是我们的核心资产与最大约束**：现状「结构化规则副本 + 逐条快照」双真相可交叉验证，是我们相对开源版的关键定制优势。表达式范式会**削弱对账的独立复算能力**，把对账推向「只能信任运行时快照」，这是战略上需要非常谨慎的让步。
3. **风险集中在我们最定制、最不该动的链路**（`price.go`/`quota.go` + Athena）。

### 5.2 推荐的「部分采纳」方案

**只把「按请求头/体条件计费」能力，以最小侵入方式补进我们现有结构**，而不引入整套表达式引擎：

- 在 `tiered_pricing.go` 的 `PriceTier` 或模型级配置上，增加**有限的、结构化的条件字段**（如 `when_header`/`when_service_tier` + `multiplier`），覆盖 Claude fast-mode / OpenAI service_tier 这类「同模型不同 SLA」差异计费。
- 计费链路只需在选档后乘一个「条件乘数」，且**该乘数与命中条件一并快照进 `other`**，对账侧只需读快照、新增一列乘数即可，**完全不破坏现有结构化复算**。
- 多模态如需「分段 + 多模态」交叉，再单独评估，不必为此上表达式。

好处：拿到最急需的能力，几乎零对账冲击，工作量小（估 2~4 人日），可灰度可回滚。

### 5.3 建议的「触发条件」——满足任一再重新评估全量/渐进迁移

- 出现**时段/动态定价**的明确商业需求（夜间折扣、活动价、按星期计价），且结构化条件字段已无法表达；
- 需要支持**大量异构多模态模型**且每个都有独立复合公式，维护 `imageRatioMap`+`tieredPricingMap`+代码分支的成本显著上升；
- 条件计费维度**膨胀到 3 个以上**（同时按 header + service_tier + 时段 + token 档），结构化字段组合爆炸，表达式的「一行即逻辑」才显出维护优势；
- 我们决定**向上游主线对齐**（减少 fork 维护负担）且愿意为对账侧投入「方案二快照体系」改造。

满足上述条件时，按**第 2.2 节策略 B（渐进并存）+ 第 3.3 节方案二（计费快照）+ 方案三（迁移期双算）** 推进，并把「计费链路合并」与「对账适配」作为重点验收项。

---

## 附录：关键文件索引

**我们现状：**
- `setting/ratio_setting/tiered_pricing.go` — 档位价格表 `tieredPricingMap` + `GetPriceTierForTokens`
- `setting/ratio_setting/model_ratio.go` — `imageRatioMap`/`audioRatioMap` 及各 ratio
- `relay/helper/price.go` — `ModelPriceHelper`（分段>ModelPrice>ModelRatio 优先级）
- `service/quota.go` — 结算与 `tiered_*` 字段写入 `other`
- `scripts/athena/pricing.json` / `pricing_engine.py` / `discounts.json` — 对账复算（tiers/flat/multimodal + 折扣四层）

**官方（上游可读）：**
- `pkg/billingexpr/expr.md` — 设计文档（变量 p/c/len/cr/cc/cc1h/img/img_o/ai/ao、自动排除、内置函数、`|||` 请求规则、v1 版本化）
- `pkg/billingexpr/{compile,run,settle,round,types}.go` — 编译缓存/求值/结算/取整/类型
- `setting/billing_setting/tiered_billing.go` — `billing_mode`/`billing_expr` 存储 + `SmokeTestExpr` + `GetPricingSyncData`
- `relay/helper/price.go`（上游版）— `modelPriceHelperTiered()` 分支
- `service/tiered_settle.go` — `BuildTieredTokenParams`（AST 自省自动排除）+ `TryTieredSettle`
