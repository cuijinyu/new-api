# new-api Quota 整数溢出漏洞分析（EZModel 分支）

> 针对 new-api 官方公告（horizon ≥ 0.6.0-rc.6 / 开源 ≥ v1.0.0-rc.18，建议 rc.19）所修复漏洞的本地复核。
> 结论先行：**我们这个分支缺少上游的输入约束与溢出防护，相关危险代码形状确实存在，应视为受影响。**

---

## 一、上游修复的是什么 Bug

**漏洞类型**：计费（quota）计算中的**有符号整数溢出 → 变负 → 扣费变成充值**。

**机制**：

1. 用户在请求里传入**超大**的乘性参数：
   - `n`（图片张数，`/v1/images/generations`）
   - `duration` / `seconds`（视频秒数，`/v1/video/generations`、Seedance 等）
   - `max_tokens`（文本/对话补全）
2. 这些参数进入 quota 计算公式（`quota = 单价 × 数量 × 倍率 × QuotaPerUnit`）。
3. 中间结果超出有符号整数范围（int32 上界 `2,147,483,647`；int64 上界 `9.2×10¹⁸`），发生**回绕（wrap‑around）变成负数**。
4. 计费代码的退款分支把“非正 quota”当成退款处理：`if quota > 0 {扣} else {充 -quota}`。
5. 于是本该扣费的操作，变成了给用户**增加余额**——无限“铸造”额度。

**上游对应**：GitHub `QuantumNous/new-api` 的 PR —— *"fix: avoid quota int overflow on 32-bit platforms"*，以及 issue #5877（32 位环境下 `quota` 字段 int 溢出）。官方因此建议升级并复核异常增长的账户余额。

---

## 二、我们平台是否存在 —— 逐点核实

### 1. 输入侧：`n` / `duration` / `max_tokens` 几乎没有任何上界校验 ✅ 确认存在缺口

| 参数 | 位置 | 现状 |
|---|---|---|
| 图片 `n` | `relay/helper/valid_request.go:328-415`（`GetAndValidOpenAIImageRequest`） | 只有 `N==0 → 1` 的下限补默认值，**没有上限**（无 `if N > 10` 之类）。`dto/openai_image.go:14` 中 `N` 类型为 `uint`。 |
| 视频 `duration` / `seconds` | `relay/common/relay_utils.go:207-240`（`ValidateBasicTaskRequestWithOptions`） | **完全不校验** min/max/正负；multipart 分支 `relay_utils.go:100-104` 同样不校验。只有 Kling 适配器自己做了白名单（`relay/channel/task/kling/adaptor.go:760`），serviceinference / doubao / sora / vidu / hailuo / jimeng / ali / gemini **均未约束**。 |
| `max_tokens`（Claude） | `relay/helper/valid_request.go:417-441`（`GetAndValidateClaudeRequest`） | **完全没有** `MaxTokens` 上界检查；`relay/claude_handler.go:48-50` 仅处理 `==0` 的默认填充。 |
| `max_tokens`（OpenAI 文本） | `relay/helper/valid_request.go:457-459` | 仅 `> MaxInt32/2`（约 10.7 亿）才拒绝——门槛远高于任何真实模型上限，**形同虚设**。 |

### 2. 计算侧：`int(uint)` / `int(float64(...))` 无保护强转 ✅ 确认存在

**最干净的攻击面 —— 图片生成**：`relay/image_handler.go:122-127`

```go
if usage.(*dto.Usage).TotalTokens == 0 {
    usage.(*dto.Usage).TotalTokens = int(request.N)   // request.N 是 uint
}
if usage.(*dto.Usage).PromptTokens == 0 {
    usage.(*dto.Usage).PromptTokens = int(request.N)
}
```

- `request.N` 是 `uint`（64 位）。当 `N ≥ 2⁶³`（如 `9223372036854775808`）时，`int(request.N)` 直接**变成负数**（有符号位重解释，纯整数层面，不涉及浮点）。
- 这两个 token 数随后进入 `postConsumeQuota(...)`，最终经 `decimal` 算出一个**负的 quota**（decimal 不会回绕，但会忠实保留负号）。
- 上游说“**image 生图需要先关闭**”正是因为这条路径。

**预扣费侧的 `int(float64(...))` 强转**：`relay/helper/price.go`

```go
// 181 行（倍率模式）
preConsumedQuota = int(float64(preConsumedTokens) * ratio * claudeInputMult * condMult)
// 186 行（价格模式，modelPrice 已在 184 行乘进 ImagePriceRatio = sizeRatio*qualityRatio*float64(N)）
preConsumedQuota = int(modelPrice * common.QuotaPerUnit * groupRatioInfo.GroupRatio * condMult)
// 106-107 行（阶梯定价，含 += meta.MaxTokens）
preConsumedQuota := int((float64(preConsumedTokens)*maxTier.InputPrice/1000000 + ...) * common.QuotaPerUnit * ...)
```

- 在 amd64 上，当 `float64` 值超过 `MaxInt64`，Go 用 `CVTTSD2SI` 指令，对**任何**越界值都返回哨兵值 `MinInt64`（`-9.2×10¹⁸`，负数）。
- `common.QuotaPerUnit = 500000.0`（`common/constants.go:21`），放大 5×10⁵ 倍，配合超大 `n/duration/max_tokens` 很容易把中间结果推过 int64 上界。

**视频任务侧**：`controller/task_video.go:261-273`

```go
actualQuota = int(value * (actualUsage * dynamicScale) * finalGroupRatio * common.QuotaPerUnit)  // 266
...
quotaDelta := actualQuota - preConsumedQuota   // 273，纯 int 减法
```

### 3. 落账侧：负 quota → 直接充值 ✅ 退款/充值分支确实存在

**文本/图片公共结算**：`service/quota.go:656-662`

```go
func PostConsumeQuota(relayInfo, quota int, preConsumedQuota int, sendEmail bool) (err error) {
    if quota > 0 {
        err = model.DecreaseUserQuota(relayInfo.UserId, quota)
    } else {
        err = model.IncreaseUserQuota(relayInfo.UserId, -quota, false)   // ← 负数 = 充值
    }
```

**视频任务结算**：`controller/task_video.go:330-333`

```go
} else if quotaDelta < 0 {
    refundQuota := -quotaDelta
    if err := model.IncreaseUserQuota(task.UserId, refundQuota, false); err == nil { ... }
```

### 4. 数据库列：`quota` 是 32 位 `INT` ✅ 本身就是溢出点（即 issue #5877）

`model/user.go:36-43`：

```go
Quota     int `json:"quota" gorm:"type:int;default:0"`
UsedQuota int `json:"used_quota" gorm:"type:int;default:0;column:used_quota"`
```

`model/log.go:29` 的 `Quota int`、`model/invoice.go` 同样是 `int`。MySQL 的 `INT` 是**有符号 32 位**（上界 `2,147,483,647`）。对比之下 `channel.go:39` 的 `UsedQuota` 用的是 `int64 gorm:"bigint"`——说明项目里混用了两种宽度，user/log 表恰恰是窄的那一种。

### 5. 现有缓解（部分有效，但不完整）⚠️

- `model.IncreaseUserQuota` / `DecreaseUserQuota`（`model/user.go:766-793`）都有 `if quota < 0 { error }` 守卫——**能挡住直接传入负数**的情形。
- `service.PreConsumeTokenQuota`（`service/quota.go:632`）同样有 `<0` 守卫——预扣费若算出负数会被拒。
- **后**结算（`relay/compatible_handler.go` 的 `postConsumeQuota`、`service/quota.go:335-371`）全程用 `shopspring/decimal`——**不会回绕**。

但这些守卫**不构成完整防御**：
- `image_handler.go` 的 `int(request.N)` 强转发生在守卫**之前**，负 token 直接喂给 decimal，算出负 quota，再走 `PostConsumeQuota` 的 `else` 分支被 `IncreaseUserQuota(-quota)` 充值（`-quota` 为正，绕过 Increase 的 `<0` 守卫）。
- 视频 `quotaDelta = 实际 - 预扣` 若实际为负（int 强转溢出），差额为大负数，`refundQuota = -quotaDelta` 为大正数，同样绕过守卫。

---

## 三、总体判定

| 维度 | 状态 |
|---|---|
| 输入上界缺失（n / duration / max_tokens） | ✅ 确认缺失 |
| `int(uint)` / `int(float64)` 无保护强转 | ✅ 确认存在（图片路径最直接） |
| 负 quota → 充值 的落账分支 | ✅ 确认存在 |
| `quota` 列 32 位 INT | ✅ 确认（上游 #5877 同款） |
| decimal 后结算 / `<0` 守卫 | ⚠️ 部分缓解，可被绕过 |
| **结论** | **分支未含上游 rc.18/rc.19 的加固，计费面应视为暴露。建议立即按下方清单处置。** |

> 说明：本次为静态代码审计（沙箱内无 Go 工具链，未跑动态 PoC）。上述结论基于代码形状与 Go 在 amd64 上的既定转换语义（`CVTTSD2SI` 哨兵值、`uint→int` 符号位重解释）。

---

## 四、修复与处置清单

### A. 立即缓解（无需改代码 / 重启）
1. **临时关闭图片生成入口**（`/v1/images/generations`、`/v1/images/edits`），与官方“image 生图需要先关闭”一致。
2. 在网关/WAF 层对 `n`、`duration`/`seconds`、`max_tokens` 加请求体大小/数值上限拦截。

### B. 代码加固（对齐上游思路）
1. **加输入上界**（参考 Kling 白名单做法）：
   - `relay/helper/valid_request.go`：`GetAndValidateClaudeRequest` 补 `max_tokens` 上限；`GetAndValidateTextRequest` 把 `MaxInt32/2` 收紧到真实模型上限（如 200k–1M）；`GetAndValidOpenAIImageRequest` 加 `if N > 10 { error }`。
   - `relay/common/relay_utils.go:207-240` 与 `:100-104`：对 `Duration`/`Seconds` 做最大值（如 600s）与正数校验。
   - `relay/channel/task/serviceinference/adaptor.go:477`（`requestDurationSeconds`）：返回前 clamp。
2. **所有 `int(float64(...))` 落点加保护**（`relay/helper/price.go:106/181/186/245`、`relay/relay_task.go:115`、`controller/task_video.go:266/270`）：
   - 先判 `math.IsInf/IsNaN`；
   - 再 clamp 到 `[0, MaxInt64]`；
   - 关键：**任何算出的 quota 若 `< 0`，一律拒绝请求/记错误日志，绝不下发到 Increase/Decrease**。
3. **`relay/image_handler.go:123/126`**：`int(request.N)` 前先判 `request.N > someMax`，或直接对 `N` 做上界校验（见 B-1）。`request.N`/`meta.MaxTokens` 的 `uint`→`int` 转换处统一加溢出检查。
4. **视频 `quotaDelta`**（`task_video.go:273-333`）：若 `actualQuota < 0` 视为异常，**走错误分支而非退款分支**。
5. **DB 迁移**：把 `users.quota` / `used_quota` / `logs.quota` 等 `INT` 列迁为 `BIGINT`（与 `channel.used_quota` 一致），并对历史数据做范围扫描。

### C. 数据库复核（抓异常增长账户）
对生产库执行（按严重度排序），重点看**没有充值记录但余额暴涨**或**消费日志里出现负数/异常大数**的账户：

```sql
-- 1. 消费日志里出现负数 quota 的记录（最直接的攻击痕迹）
SELECT user_id, model_name, quota, created_at, request_id, other
FROM logs
WHERE type = 2                               -- consume
  AND quota < 0
ORDER BY created_at DESC
LIMIT 200;

-- 2. 消费日志里 quota 异常大（接近 INT 上界 2.1e9）的记录
SELECT user_id, model_name, quota, created_at, request_id
FROM logs
WHERE type = 2 AND quota > 100000000          -- 1 亿以上，按业务调阈值
ORDER BY quota DESC
LIMIT 200;

-- 3. 余额为负 或 余额异常高的账户
SELECT id, username, quota, used_quota, status, created_at
FROM users
WHERE quota < 0 OR quota > 5000000000         -- 50 亿，按业务调
ORDER BY quota DESC;

-- 4. 短时间内余额净增异常的账户（按天聚合充值 vs 消费 vs 余额变化）
SELECT t.d, t.user_id,
       COALESCE(r.added, 0)   AS recharged,
       COALESCE(c.consumed, 0) AS consumed,
       COALESCE(r.added,0) - COALESCE(c.consumed,0) AS net
FROM (
  SELECT DATE(created_at) AS d, user_id FROM logs
  WHERE created_at > DATE_SUB(NOW(), INTERVAL 30 DAY)
  GROUP BY DATE(created_at), user_id
) t
LEFT JOIN (
  SELECT DATE(created_at) d, user_id, SUM(quota) added
  FROM logs WHERE type=1 /*topup*/ GROUP BY DATE(created_at), user_id
) r ON r.d=t.d AND r.user_id=t.user_id
LEFT JOIN (
  SELECT DATE(created_at) d, user_id, -SUM(quota) consumed
  FROM logs WHERE type=2 /*consume*/ GROUP BY DATE(created_at), user_id
) c ON c.d=t.d AND c.user_id=t.user_id
HAVING net > 100000000                        -- 净增超 1 亿且无对应充值 → 重点核查
ORDER BY net DESC
LIMIT 200;
```

对命中账户：冻结 token、回溯 `request_id` 对应的请求参数（看 `n`/`duration`/`max_tokens` 是否异常）、必要时回滚余额并封号。

---

## 五、关键证据索引

| 关注点 | 位置 |
|---|---|
| 图片 N→token 强转（最直接攻击面） | `relay/image_handler.go:122-127` |
| 预扣费算式（倍率/价格/阶梯） | `relay/helper/price.go:106-107, 181, 186` |
| 视频实际 quota 与差额 | `controller/task_video.go:266, 270, 273` |
| 负 quota→充值（公共） | `service/quota.go:656-662` |
| 负 quota→充值（视频） | `controller/task_video.go:330-333` |
| 输入校验缺失（图片/文本/Claude） | `relay/helper/valid_request.go:328-415, 417-441, 457-459` |
| 视频时长不校验 | `relay/common/relay_utils.go:100-104, 207-240` |
| serviceinference 时长→token 估算 | `relay/channel/task/serviceinference/adaptor.go:468-495` |
| `<0` 守卫（部分缓解） | `model/user.go:766-793`、`service/quota.go:632` |
| 后结算 decimal（不回绕） | `service/quota.go:56-79, 335-371` |
| quota 列 32 位 INT | `model/user.go:36-43`、`model/log.go:29` |
| QuotaPerUnit=5e5 放大系数 | `common/constants.go:21` |
| 上游对应 PR/issue | `QuantumNous/new-api` "fix: avoid quota int overflow on 32-bit platforms"；issue #5877 |
