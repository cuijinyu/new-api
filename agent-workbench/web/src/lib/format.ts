import type { ApiResult } from "./api";
import type { AgentResultImpact, BillDocument, JobSummary, JsonObject, UploadedFile } from "../types";

export function textOf(value: unknown, fallback = "-") {
  return value === undefined || value === null || value === "" ? fallback : String(value);
}

export function stringValue(value: unknown, fallback = "") {
  return value === undefined || value === null || value === "" ? fallback : String(value);
}

export function formatMoney(amount: number, currency = "USD") {
  if (!Number.isFinite(amount)) return "—";
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 2 }).format(amount);
  } catch {
    return `$${amount.toFixed(2)}`;
  }
}

export function asJsonObject(value: unknown): JsonObject | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonObject) : null;
}

export function statusTone(status?: unknown): "default" | "green" | "amber" | "red" | "blue" {
  const value = String(status || "").toLowerCase();
  if (["completed", "active", "ok", "healthy", "uploaded", "generated", "delivered", "applied"].includes(value)) return "green";
  if (["created", "running", "open", "queued", "draft", "materializing_facts", "rendering", "paused", "sandbox_ready", "human_replied"].includes(value)) return "amber";
  if (["failed", "partial_failed", "error", "rejected", "ignored", "timed_out", "cancelled"].includes(value)) return "red";
  return "default";
}

export function statusText(status?: unknown) {
  const value = String(status || "").toLowerCase();
  const map: Record<string, string> = {
    created: "待运行",
    running: "运行中",
    completed: "已完成",
    failed: "失败",
    partial_failed: "部分失败",
    active: "进行中",
    uploaded: "已上传",
    open: "待处理",
    queued: "排队中",
    generated: "已生成",
    delivered: "已交付",
    materializing_facts: "生成事实表",
    rendering: "生成账单",
    applied: "已应用",
    ignored: "已忽略",
    rejected: "已驳回",
    timed_out: "已超时",
    paused: "已暂停",
    sandbox_ready: "沙箱就绪",
    human_replied: "人工已接力",
    cancelled: "已取消",
    ok: "正常",
    healthy: "健康",
  };
  return map[value] || textOf(status);
}

export function billTypeText(value?: unknown) {
  const map: Record<string, string> = {
    customer_invoice: "客户版账单",
    internal_customer_bill: "内部版账单",
    channel_cost_bill: "渠道账单",
    daily_channel_cost_snapshot: "每日渠道成本",
  };
  return map[String(value || "")] || textOf(value);
}

export function targetText(document: BillDocument) {
  const targetType = String(document.target_type || "all");
  const targetId = String(document.target_id || "").trim();
  const billType = String(document.bill_type || "");

  if (!targetId || targetId === "all" || targetType === "all") {
    if (billType === "customer_invoice" || billType === "internal_customer_bill") return "全部客户";
    if (billType === "channel_cost_bill" || billType === "daily_channel_cost_snapshot") return "全部渠道";
    return "全平台";
  }
  if (targetType === "customer" || targetType === "user") return `客户 #${targetId}`;
  if (targetType === "channel") return `渠道 #${targetId}`;
  return `#${targetId}`;
}

const displayTextReplacements: Array<[RegExp, string]> = [
  [/Agent\s+Agent\s+session created\.?/gi, "对话已创建，Agent 已准备好。"],
  [/Agent\s+session created\.?/gi, "对话已创建，Agent 已准备好。"],
  [/Agent stream started\.?/gi, "Agent 已开始分析。"],
  [/Human-in-loop/gi, "补充信息"],
  [/人工介入/g, "补充信息"],
  [/人工补充/g, "补充信息"],
  [/已收到补充信息信息/g, "已收到补充信息"],
  [/需要审批/g, "需要处理"],
  [/可审批/g, "可处理"],
  [/审批/g, "处理"],
  [/Athena CLI/gi, "账单工具"],
  [/Athena 出账/g, "生成账单"],
  [/Athena/gi, "账单系统"],
  [/Agent 调查/g, "问 Agent"],
  [/启动调查/g, "开始分析"],
  [/介入发送/g, "发送补充信息"],
  [/读取记录/g, "查看记录"],
  [/正在读取出账任务、pricing\s*(和|and|\/)\s*discounts\s*上下文。/gi, "正在核对本次账单和价格方案。"],
  [/正在调用\s*pricing\s*(和|and|\/)\s*discounts\s*检查工具，确认/gi, "正在核对价格方案，确认"],
  [/正在读取账单任务、价格\/折扣口径\s*上下文。/g, "正在核对本次账单和价格方案。"],
  [/正在调用\s*价格\/折扣口径\s*检查工具，确认/g, "正在核对价格方案，确认"],
  [/读取已上传/g, "结合已上传"],
  [/出账/g, "账单"],
  [/pricing\/discounts/gi, "价格方案"],
  [/pricing\s*(和|and|\/)\s*discounts/gi, "价格方案"],
  [/配置变更/g, "价格方案建议"],
  [/ClaudeCode\s*\/\s*CodingPlan/gi, "Agent"],
  [/ClaudeCode|CodingPlan/g, "Agent"],
  [/Agent\s+Agent/g, "Agent"],
  [/Agent\s+session created\.?/gi, "对话已创建，Agent 已准备好。"],
  [/Agent stream completed\.?/gi, "本轮分析已完成。"],
  [/沙箱运行时/g, "运行环境"],
  [/流式事件/g, "实时消息"],
  [/等待窗口/g, "补充信息入口"],
  [/本地 mock/gi, "本地模拟"],
  [/本地模拟\s*流结束/g, "本地模拟已结束"],
  [/真实模式/g, "正式运行"],
  [/智谱 Coding API/g, "Agent 服务"],
  [/正式运行会从Agent 服务 持续读取增量输出。/g, "正式运行会持续更新回复。"],
];

export function displayText(value: unknown, fallback = "-") {
  const raw = textOf(value, fallback);
  if (!raw || raw === fallback) return raw;
  return displayTextReplacements.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), raw);
}

export function resultValue(result?: ApiResult | null) {
  if (!result) return null;
  return result.ok ? result.data : result.error;
}

export function parseJsonInput(value: string): { ok: true; data: JsonObject } | { ok: false; error: string } {
  if (!value.trim()) return { ok: true, data: {} };
  try {
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { ok: false, error: "JSON 必须是对象" };
    }
    return { ok: true, data: parsed as JsonObject };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : "JSON 格式错误" };
  }
}

export function compactPayload(payload: JsonObject) {
  return Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== "" && value !== undefined && value !== null));
}

export function formatUsd(value?: unknown) {
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) return "-";
  return `$${num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatNumber(value?: unknown) {
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) return "-";
  return num.toLocaleString("en-US");
}

export function formatBytes(value?: number) {
  if (!value) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

export function shortId(value?: unknown) {
  const text = textOf(value, "");
  if (!text) return "-";
  return text.length > 18 ? `${text.slice(0, 10)}...${text.slice(-6)}` : text;
}

export function jobTypeText(type?: unknown) {
  const value = String(type || "").toLowerCase();
  if (value === "billing_run") return "生成账单";
  if (value === "supplier_reconcile") return "供应商对账";
  if (value.includes("codex") || value.includes("agent")) return "Agent 对话";
  if (value.includes("skill")) return "经验沉淀";
  return textOf(type, "任务");
}

export function jobTitle(job: JobSummary) {
  const parts = [job.month, job.vendor, job.channel_id ? `渠道 ${job.channel_id}` : ""].filter(Boolean);
  return parts.length ? parts.join(" · ") : jobTypeText(job.type);
}

export function jobNextAction(status?: unknown) {
  const value = String(status || "").toUpperCase();
  if (value === "QUEUED") return "运行下一条";
  if (value === "CREATED" || value === "FAILED") return "继续处理";
  if (value === "RUNNING") return "查看进展";
  if (value === "COMPLETED") return "查看结果";
  return "查看详情";
}

export function formatDate(value?: unknown) {
  if (!value) return "-";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

export function eventLabel(type?: string) {
  switch (type) {
    case "message":
      return "你";
    case "assistant.delta":
      return "Agent 回复";
    case "operator.message.received":
      return "已收到补充信息";
    case "human.input.waiting":
      return "等待补充信息";
    case "tool.call":
      return "检查步骤";
    case "tool.result":
      return "检查结果";
    case "run.started":
      return "开始分析";
    case "run.completed":
      return "分析完成";
    case "run.error":
      return "分析失败";
    case "session.created":
      return "对话创建";
    default:
      return type || "进展";
  }
}

export function categoryText(category?: unknown) {
  const value = String(category || "").toLowerCase();
  const map: Record<string, string> = {
    "billing-result": "账单结果",
    "supplier-bill": "供应商账单",
    "reconcile-evidence": "对账凭证",
    "agent-context": "对话资料",
    "platform-bill": "平台账单",
    "pricing-discount": "价格/折扣",
    contract: "合同",
    general: "通用文件",
  };
  return map[value] || textOf(category, "未分类");
}

export function fileExtension(filename?: string) {
  const name = filename || "";
  const index = name.lastIndexOf(".");
  return index > -1 ? name.slice(index + 1).toUpperCase() : "文件";
}

export function previewCell(value: unknown) {
  if (value === undefined || value === null || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function metadataValue(file: UploadedFile, key: string) {
  const value = file.metadata?.[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

export function fileDirectory(file: UploadedFile) {
  const fromMetadata = metadataValue(file, "directory_path");
  if (fromMetadata) return fromMetadata;
  if (file.category === "billing-result") {
    const month = metadataValue(file, "month") || "未分账期";
    const runId = metadataValue(file, "billing_run_id") || file.job_id || "未分组";
    return `账单结果/${month}/${runId}`;
  }
  return categoryText(file.category);
}

export function formatImpact(impact?: AgentResultImpact | null) {
  if (!impact) return "暂无";
  const usd = impact.amount_usd_delta;
  if (typeof usd === "number" && Number.isFinite(usd)) {
    const sign = usd > 0 ? "+" : "";
    return `${sign}${usd.toFixed(2)} USD`;
  }
  const cny = impact.amount_cny_delta;
  if (typeof cny === "number" && Number.isFinite(cny)) {
    const sign = cny > 0 ? "+" : "";
    return `${sign}${cny.toFixed(2)} CNY`;
  }
  return "暂无";
}

export async function fileToBase64(file: File) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 8192) {
    binary += String.fromCharCode(...bytes.slice(i, i + 8192));
  }
  return btoa(binary);
}
