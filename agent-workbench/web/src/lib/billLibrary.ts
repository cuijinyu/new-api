import type { BillDocument, JsonObject } from "../types";
import { artifactFilename } from "./billing";
import { asJsonObject, billTypeText } from "./format";

export type BillFileKind = "summary" | "customer" | "channel" | "detail" | "log" | "other";
export type BillObjectAxis = "customer" | "channel";

export type ParsedBillFile = {
  kind: BillFileKind;
  entityId?: string;
  extension: string;
  rawName: string;
  title: string;
  subtitle: string;
};

export type BillDownloadItem = {
  uri: string;
  filename: string;
  parsed: ParsedBillFile;
};

export type BillFileSection = {
  id: string;
  title: string;
  hint?: string;
  items: BillDownloadItem[];
  collapsed?: boolean;
};

export type BillDateInfo = {
  kind: "day" | "month";
  raw: string;
  monthKey: string;
  label: string;
  dayLabel: string | null;
};

const MONTH_RE = /^(\d{4})-(\d{2})$/;
const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

export function formatBillMonth(value?: string): string {
  const raw = String(value || "").trim();
  if (!raw) return "—";
  const monthMatch = raw.match(MONTH_RE);
  if (monthMatch) {
    const [, y, m] = monthMatch;
    return `${y}年${Number(m)}月`;
  }
  const dateMatch = raw.match(DATE_RE);
  if (dateMatch) {
    const [, y, m] = dateMatch;
    return `${y}年${Number(m)}月`;
  }
  return raw;
}

export function formatBillDay(value?: string): string {
  const raw = String(value || "").trim();
  const dateMatch = raw.match(DATE_RE);
  if (!dateMatch) return "—";
  const [, y, m, d] = dateMatch;
  return `${y}年${Number(m)}月${Number(d)}日`;
}

/** @deprecated use formatBillMonth / resolveBillDate */
export function formatBillPeriod(value?: string, billType?: string): string {
  if (billType === "daily_channel_cost_snapshot" && value && DATE_RE.test(value)) {
    return formatBillDay(value);
  }
  if (value && DATE_RE.test(value)) return formatBillDay(value);
  return formatBillMonth(value);
}

export function billObjectAxis(document: BillDocument): BillObjectAxis {
  const billType = String(document.bill_type || "");
  if (billType === "channel_cost_bill" || billType === "daily_channel_cost_snapshot") return "channel";
  if (billType === "customer_invoice" || billType === "internal_customer_bill") return "customer";
  const targetType = String(document.target_type || "");
  if (targetType === "channel") return "channel";
  if (targetType === "customer" || targetType === "user") return "customer";
  return "customer";
}

export function billObjectAxisLabel(axis: BillObjectAxis): string {
  return axis === "customer" ? "客户" : "渠道";
}

function dateFromGeneratedFiles(summary: JsonObject): string | null {
  const generated = asJsonObject(summary.generated_files);
  if (!generated) return null;
  for (const name of Object.keys(generated)) {
    const daily = name.match(/daily_report_(\d{4}-\d{2}-\d{2})/);
    if (daily) return daily[1];
  }
  return null;
}

export function resolveBillDate(document: BillDocument): BillDateInfo {
  const summary = asJsonObject(document.summary) || {};
  const billType = String(document.bill_type || "");
  const candidates = [
    summary.snapshot_date,
    summary.period,
    dateFromGeneratedFiles(summary),
    billType === "daily_channel_cost_snapshot" ? document.month : null,
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean);

  for (const raw of candidates) {
    if (DATE_RE.test(raw)) {
      return {
        kind: "day",
        raw,
        monthKey: raw.slice(0, 7),
        label: formatBillDay(raw),
        dayLabel: formatBillDay(raw),
      };
    }
  }

  const monthRaw = String(document.month || candidates.find((v) => MONTH_RE.test(v)) || "").trim();
  return {
    kind: "month",
    raw: monthRaw,
    monthKey: monthRaw.match(DATE_RE) ? monthRaw.slice(0, 7) : monthRaw,
    label: formatBillMonth(monthRaw),
    dayLabel: null,
  };
}

export function billTargetLabel(document: BillDocument): string {
  const axis = billObjectAxis(document);
  const targetType = String(document.target_type || "all");
  const targetId = String(document.target_id || "").trim();

  if (!targetId || targetId === "all" || targetType === "all") {
    return axis === "customer" ? "全部客户" : "全部渠道";
  }
  if (targetType === "customer" || targetType === "user") return `客户 #${targetId}`;
  if (targetType === "channel") return `渠道 #${targetId}`;
  return axis === "customer" ? `客户 #${targetId}` : `渠道 #${targetId}`;
}

/** 列表「对象」列：轴 + 具体对象 */
export function billObjectCell(document: BillDocument): { axis: BillObjectAxis; axisLabel: string; target: string } {
  return {
    axis: billObjectAxis(document),
    axisLabel: billObjectAxisLabel(billObjectAxis(document)),
    target: billTargetLabel(document),
  };
}

export type BillMoneyMetric = {
  id: "total" | "revenue" | "cost" | "list_price" | "profit" | "parent_total";
  label: string;
  amount: number;
};

export type BillBusinessMetrics = {
  listPriceUsd: number | null;
  payableUsd: number | null;
  revenueUsd: number | null;
  costUsd: number | null;
  profitUsd: number | null;
};

export type BillBusinessRow = BillBusinessMetrics & {
  axis: BillObjectAxis;
  targetId: string;
  targetLabel: string;
  displayName: string;
  documentCount: number;
  latestPeriod: string;
  sourceTypes: string[];
};

function moneyNumber(value: unknown): number | null {
  const amount = Number(value);
  return Number.isFinite(amount) ? amount : null;
}

function firstMoney(summary: JsonObject, keys: string[]): number {
  for (const key of keys) {
    const amount = moneyNumber(summary[key]);
    if (amount !== null) return amount;
  }
  return Number.NaN;
}

function firstNullableMoney(summary: JsonObject, keys: string[]): number | null {
  for (const key of keys) {
    const amount = moneyNumber(summary[key]);
    if (amount !== null) return amount;
  }
  return null;
}

export function billDocumentAmount(document: BillDocument): BillMoneyMetric {
  const summary = asJsonObject(document.summary) || {};
  const billType = String(document.bill_type || "");
  if (billType === "channel_cost_bill" || billType === "daily_channel_cost_snapshot") {
    return { id: "cost", label: "成本金额", amount: firstMoney(summary, ["cost_usd", "total_usd"]) };
  }
  if (billType === "customer_invoice") {
    return { id: "revenue", label: "应收金额", amount: firstMoney(summary, ["revenue_usd", "total_usd"]) };
  }
  if (billType === "internal_customer_bill") {
    return { id: "revenue", label: "收入金额", amount: firstMoney(summary, ["revenue_usd", "total_usd"]) };
  }
  return { id: "total", label: "账单金额", amount: firstMoney(summary, ["total_usd"]) };
}

export function billDocumentMoneyBreakdown(document: BillDocument): BillMoneyMetric[] {
  const summary = asJsonObject(document.summary) || {};
  const metrics: BillMoneyMetric[] = [];
  const add = (id: BillMoneyMetric["id"], label: string, value: unknown) => {
    const amount = moneyNumber(value);
    if (amount === null) return;
    metrics.push({ id, label, amount });
  };
  add("revenue", "收入金额", summary.revenue_usd);
  add("cost", "成本金额", summary.cost_usd);
  add("list_price", "刊例价", summary.list_price_usd);
  add("profit", "利润", summary.profit_usd);
  add("parent_total", "母单合计", summary.parent_total_usd);
  return metrics;
}

export function billBusinessMetricsFromSummary(summary: JsonObject, billType?: unknown): BillBusinessMetrics {
  const type = String(billType || summary.bill_type || "");
  const listPriceUsd = firstNullableMoney(summary, ["list_price_usd", "list_price", "gross_usd", "pre_discount_usd"]);
  const revenueUsd = firstNullableMoney(summary, ["revenue_usd", "receivable_usd", "income_usd"]);
  const totalUsd = firstNullableMoney(summary, ["total_usd"]);
  let payableUsd = firstNullableMoney(summary, ["payable_usd", "amount_due_usd", "revenue_usd", "receivable_usd"]);
  let costUsd = firstNullableMoney(summary, ["cost_usd", "our_cost_usd", "upstream_cost_usd"]);

  if (payableUsd === null && (type === "customer_invoice" || type === "internal_customer_bill")) {
    payableUsd = totalUsd;
  }
  if (costUsd === null && (type === "channel_cost_bill" || type === "daily_channel_cost_snapshot")) {
    costUsd = totalUsd;
  }

  let profitUsd = firstNullableMoney(summary, ["profit_usd", "gross_profit_usd", "margin_usd"]);
  const profitBase = payableUsd ?? revenueUsd;
  if (profitUsd === null && profitBase !== null && costUsd !== null) {
    profitUsd = profitBase - costUsd;
  }

  return { listPriceUsd, payableUsd, revenueUsd, costUsd, profitUsd };
}

export function billDocumentBusinessMetrics(document: BillDocument): BillBusinessMetrics {
  return billBusinessMetricsFromSummary(asJsonObject(document.summary) || {}, document.bill_type);
}

function hasBusinessMetric(metrics: BillBusinessMetrics): boolean {
  return Object.values(metrics).some((value) => typeof value === "number" && Number.isFinite(value));
}

function addNullable(current: number | null, value: number | null): number | null {
  if (value === null || !Number.isFinite(value)) return current;
  return (current ?? 0) + value;
}

function entityIdForDocument(document: BillDocument, axis: BillObjectAxis): string {
  const summary = asJsonObject(document.summary) || {};
  const targetType = String(document.target_type || summary.target_type || "").trim();
  const targetId = String(document.target_id || summary.target_id || "").trim();
  if (axis === "customer") {
    return String(summary.user_id || (targetType === "customer" || targetType === "user" ? targetId : "") || "").trim();
  }
  return String(summary.channel_id || (targetType === "channel" ? targetId : "") || "").trim();
}

function entityNameFromSummary(summary: JsonObject, axis: BillObjectAxis): string {
  const keys = axis === "customer" ? ["username", "user_name", "customer_name", "name"] : ["channel_name", "vendor", "name"];
  for (const key of keys) {
    const value = String(summary[key] || "").trim();
    if (value) return value;
  }
  return "";
}

function businessDateKey(document: BillDocument): string {
  const date = resolveBillDate(document);
  return date.raw || date.monthKey || String(document.month || "");
}

function sourceKey(document: BillDocument, axis: BillObjectAxis, targetId: string, monthOnly = false): string {
  const date = resolveBillDate(document);
  return [monthOnly ? date.monthKey : businessDateKey(document), axis, targetId].join("|");
}

function perEntitySummaryMap(summary: JsonObject, axis: BillObjectAxis): JsonObject {
  const billSummary = asJsonObject(summary.bill_summary) || {};
  const key = axis === "channel" ? "per_channel_summary" : "per_customer_summary";
  return asJsonObject(billSummary[key]) || asJsonObject(summary[key]) || {};
}

function documentUpdatedMs(document: BillDocument): number {
  const raw = String(document.updated_at || document.created_at || "");
  const value = Date.parse(raw);
  return Number.isFinite(value) ? value : 0;
}

function businessDocumentKey(document: BillDocument): string {
  const axis = billObjectAxis(document);
  const targetId = entityIdForDocument(document, axis) || "all";
  return [document.bill_type || "", businessDateKey(document), axis, targetId].join("|");
}

function latestBusinessDocuments(documents: BillDocument[]): BillDocument[] {
  const byKey = new Map<string, BillDocument>();
  for (const document of documents) {
    const key = businessDocumentKey(document);
    const existing = byKey.get(key);
    if (!existing || documentUpdatedMs(document) >= documentUpdatedMs(existing)) {
      byKey.set(key, document);
    }
  }
  return [...byKey.values()];
}

type MutableBusinessRow = BillBusinessRow & { sourceTypeSet: Set<string> };

function addBusinessRow(
  rows: Map<string, MutableBusinessRow>,
  params: {
    axis: BillObjectAxis;
    targetId: string;
    targetLabel: string;
    displayName: string;
    period: string;
    billType: string;
    metrics: BillBusinessMetrics;
  },
) {
  if (!hasBusinessMetric(params.metrics)) return;
  const id = params.targetId || "all";
  const key = `${params.axis}:${id}`;
  const row =
    rows.get(key) ||
    ({
      axis: params.axis,
      targetId: id,
      targetLabel: params.targetLabel,
      displayName: params.displayName,
      documentCount: 0,
      latestPeriod: "",
      sourceTypes: [],
      sourceTypeSet: new Set<string>(),
      listPriceUsd: null,
      payableUsd: null,
      revenueUsd: null,
      costUsd: null,
      profitUsd: null,
    } satisfies MutableBusinessRow);

  row.targetLabel = params.targetLabel || row.targetLabel;
  row.displayName = params.displayName || row.displayName;
  row.documentCount += 1;
  row.latestPeriod = !row.latestPeriod || params.period.localeCompare(row.latestPeriod) > 0 ? params.period : row.latestPeriod;
  row.sourceTypeSet.add(params.billType);
  row.listPriceUsd = addNullable(row.listPriceUsd, params.metrics.listPriceUsd);
  row.payableUsd = addNullable(row.payableUsd, params.metrics.payableUsd);
  row.revenueUsd = addNullable(row.revenueUsd, params.metrics.revenueUsd);
  row.costUsd = addNullable(row.costUsd, params.metrics.costUsd);
  row.profitUsd = addNullable(row.profitUsd, params.metrics.profitUsd);
  rows.set(key, row);
}

export function buildBillBusinessRows(documents: BillDocument[]): BillBusinessRow[] {
  const businessDocuments = latestBusinessDocuments(documents);
  const rows = new Map<string, MutableBusinessRow>();
  const internalCustomerKeys = new Set<string>();
  const monthlyChannelKeys = new Set<string>();
  const splitKeys = new Set<string>();

  for (const document of businessDocuments) {
    const axis = billObjectAxis(document);
    const targetId = entityIdForDocument(document, axis);
    if (!targetId || !isSplitBillDocument(document)) continue;
    if (document.bill_type === "internal_customer_bill" && axis === "customer") {
      internalCustomerKeys.add(sourceKey(document, axis, targetId));
    }
    if (document.bill_type === "channel_cost_bill" && axis === "channel") {
      monthlyChannelKeys.add(sourceKey(document, axis, targetId, true));
    }
  }

  for (const document of businessDocuments) {
    const axis = billObjectAxis(document);
    const targetId = entityIdForDocument(document, axis);
    if (!targetId || !isSplitBillDocument(document)) continue;
    if (axis === "customer" && document.bill_type === "customer_invoice" && internalCustomerKeys.has(sourceKey(document, axis, targetId))) {
      continue;
    }
    if (
      axis === "channel" &&
      document.bill_type === "daily_channel_cost_snapshot" &&
      monthlyChannelKeys.has(sourceKey(document, axis, targetId, true))
    ) {
      continue;
    }
    splitKeys.add(sourceKey(document, axis, targetId));
    const summary = asJsonObject(document.summary) || {};
    addBusinessRow(rows, {
      axis,
      targetId,
      targetLabel: axis === "customer" ? `客户 #${targetId}` : `渠道 #${targetId}`,
      displayName: entityNameFromSummary(summary, axis),
      period: businessDateKey(document),
      billType: String(document.bill_type || ""),
      metrics: billBusinessMetricsFromSummary(summary, document.bill_type),
    });
  }

  for (const document of businessDocuments) {
    if (!isAggregateBillDocument(document)) continue;
    const axis = billObjectAxis(document);
    const summary = asJsonObject(document.summary) || {};
    const map = perEntitySummaryMap(summary, axis);
    for (const [targetId, rawMetrics] of Object.entries(map)) {
      if (!targetId || typeof rawMetrics !== "object" || rawMetrics === null || Array.isArray(rawMetrics)) continue;
      const metricsSummary = rawMetrics as JsonObject;
      if (splitKeys.has(sourceKey(document, axis, targetId))) continue;
      if (axis === "customer" && document.bill_type === "customer_invoice" && internalCustomerKeys.has(sourceKey(document, axis, targetId))) continue;
      if (
        axis === "channel" &&
        document.bill_type === "daily_channel_cost_snapshot" &&
        monthlyChannelKeys.has(sourceKey(document, axis, targetId, true))
      ) {
        continue;
      }
      addBusinessRow(rows, {
        axis,
        targetId,
        targetLabel: axis === "customer" ? `客户 #${targetId}` : `渠道 #${targetId}`,
        displayName: entityNameFromSummary(metricsSummary, axis),
        period: businessDateKey(document),
        billType: String(document.bill_type || ""),
        metrics: billBusinessMetricsFromSummary(metricsSummary, document.bill_type),
      });
    }

    const targetId = entityIdForDocument(document, axis) || "all";
    if (targetId === "all" && Object.keys(map).length) continue;
    addBusinessRow(rows, {
      axis,
      targetId,
      targetLabel: billTargetLabel(document),
      displayName: entityNameFromSummary(summary, axis),
      period: businessDateKey(document),
      billType: String(document.bill_type || ""),
      metrics: billBusinessMetricsFromSummary(summary, document.bill_type),
    });
  }

  return [...rows.values()]
    .map(({ sourceTypeSet, ...row }) => ({
      ...row,
      sourceTypes: [...sourceTypeSet].filter(Boolean).sort(),
    }))
    .sort((a, b) => {
      if (a.axis !== b.axis) return a.axis === "channel" ? -1 : 1;
      const aPrimary = a.axis === "channel" ? a.costUsd ?? a.payableUsd ?? a.listPriceUsd ?? 0 : a.payableUsd ?? a.revenueUsd ?? a.listPriceUsd ?? 0;
      const bPrimary = b.axis === "channel" ? b.costUsd ?? b.payableUsd ?? b.listPriceUsd ?? 0 : b.payableUsd ?? b.revenueUsd ?? b.listPriceUsd ?? 0;
      if (bPrimary !== aPrimary) return bPrimary - aPrimary;
      return a.targetId.localeCompare(b.targetId, undefined, { numeric: true });
    });
}

export function billScopeLabel(document: BillDocument): string {
  return billTargetLabel(document);
}

export function billTypeShort(value?: unknown): string {
  const map: Record<string, string> = {
    customer_invoice: "客户版",
    internal_customer_bill: "内部版",
    channel_cost_bill: "渠道成本",
    daily_channel_cost_snapshot: "日成本",
  };
  return map[String(value || "")] || billTypeText(value);
}

export function billDocumentTitle(document: BillDocument): string {
  const date = resolveBillDate(document);
  return `${date.label} · ${billTypeShort(document.bill_type)}`;
}

export function billDocumentListHint(document: BillDocument): string {
  return billTargetLabel(document);
}

function periodFromFilename(name: string): { month?: string; day?: string } {
  const billMonth = name.match(/bill_(\d{4}-\d{2})/);
  if (billMonth) return { month: billMonth[1] };
  const daily = name.match(/daily_report_(\d{4}-\d{2}-\d{2})/);
  if (daily) return { day: daily[1], month: daily[1].slice(0, 7) };
  return {};
}

export function parseBillArtifactFilename(name: string, axis: BillObjectAxis = "customer"): ParsedBillFile {
  const rawName = name.split("/").pop() || name;
  const lower = rawName.toLowerCase();
  const extension = lower.includes(".") ? lower.slice(lower.lastIndexOf(".") + 1) : "";
  const { month, day } = periodFromFilename(rawName);
  const periodLabel = day ? formatBillDay(day) : month ? formatBillMonth(month) : undefined;

  const userMatch = rawName.match(/_user(\d+)/);
  const channelMatch = rawName.match(/_ch(\d+)/);
  const isDetail = lower.includes("_detail") || (extension === "zip" && lower.includes("detail")) || (extension === "csv" && lower.includes("detail"));

  if (lower.includes("stdout") || lower.includes("stderr") || extension === "log") {
    return {
      kind: "log",
      extension,
      rawName,
      title: lower.includes("stderr") ? "错误日志" : "运行日志",
      subtitle: "排查问题时查看",
    };
  }

  if (isDetail) {
    const entityId = userMatch?.[1] || channelMatch?.[1];
    const scope = userMatch ? `客户 #${userMatch[1]}` : channelMatch ? `渠道 #${channelMatch[1]}` : axis === "channel" ? "全部渠道" : "全部客户";
    return {
      kind: "detail",
      entityId,
      extension,
      rawName,
      title: "逐条明细",
      subtitle: entityId ? `${scope} · ${periodLabel || ""}`.trim() : periodLabel || "按请求展开的明细数据",
    };
  }

  if (userMatch) {
    return {
      kind: "customer",
      entityId: userMatch[1],
      extension,
      rawName,
      title: `客户 #${userMatch[1]}`,
      subtitle: [periodLabel, extension === "xlsx" ? "Excel 账单" : extension.toUpperCase()].filter(Boolean).join(" · "),
    };
  }

  if (channelMatch) {
    return {
      kind: "channel",
      entityId: channelMatch[1],
      extension,
      rawName,
      title: `渠道 #${channelMatch[1]}`,
      subtitle: [periodLabel, extension === "xlsx" ? "Excel 账单" : extension.toUpperCase()].filter(Boolean).join(" · "),
    };
  }

  if (lower.startsWith("daily_report_")) {
    return {
      kind: "summary",
      extension,
      rawName,
      title: day ? `${formatBillDay(day)} 日成本汇总` : "日成本汇总",
      subtitle: "全部渠道合计",
    };
  }

  if (lower.startsWith("bill_")) {
    const isCustomerView = lower.includes("_customer");
    const summaryTitle = axis === "channel" ? "渠道成本汇总" : isCustomerView ? "客户版汇总" : "内部版汇总";
    const summaryScope = axis === "channel" ? "全部渠道合计" : "全部客户合计";
    return {
      kind: "summary",
      extension,
      rawName,
      title: summaryTitle,
      subtitle: periodLabel ? `${periodLabel} · ${summaryScope}` : summaryScope,
    };
  }

  const extLabel = extension === "xlsx" ? "Excel" : extension === "csv" ? "CSV" : extension.toUpperCase();
  return {
    kind: "other",
    extension,
    rawName,
    title: rawName.replace(/\.[^.]+$/, ""),
    subtitle: extLabel || "文件",
  };
}

export type SplitBillTarget = {
  targetType: "customer" | "channel";
  targetId: string;
  filename: string;
  uri: string;
};

/** 从 generated_files 解析按客户/渠道拆分的账单产物（用于任务计划展开）。 */
export function parseSplitTargetsFromGenerated(summary: JsonObject, axis: BillObjectAxis = "customer"): SplitBillTarget[] {
  const generated = asJsonObject(summary.generated_files);
  if (!generated) return [];
  const targets: SplitBillTarget[] = [];
  const seen = new Set<string>();
  for (const [name, uri] of Object.entries(generated)) {
    if (typeof uri !== "string" || !uri) continue;
    const parsed = parseBillArtifactFilename(name, axis);
    if ((parsed.kind !== "customer" && parsed.kind !== "channel") || !parsed.entityId) continue;
    const targetType = parsed.kind;
    const key = `${targetType}:${parsed.entityId}`;
    if (seen.has(key)) continue;
    seen.add(key);
    targets.push({ targetType, targetId: parsed.entityId, filename: name, uri });
  }
  return targets.sort((a, b) => a.targetId.localeCompare(b.targetId, undefined, { numeric: true }));
}

export function isAggregateBillDocument(document: BillDocument): boolean {
  const targetId = String(document.target_id || "").trim();
  const targetType = String(document.target_type || "").trim();
  return !targetId || targetId === "all" || targetType === "all";
}

export function isSplitBillDocument(document: BillDocument): boolean {
  const summary = asJsonObject(document.summary) || {};
  if (summary.split_entity === true) return true;
  return !isAggregateBillDocument(document);
}

export function collectBillDownloadItems(document: BillDocument): BillDownloadItem[] {
  const summary = asJsonObject(document.summary) || {};
  const axis = billObjectAxis(document);
  const items: BillDownloadItem[] = [];
  const seen = new Set<string>();

  const generated = asJsonObject(summary.generated_files);
  if (generated) {
    for (const [name, uri] of Object.entries(generated)) {
      if (typeof uri !== "string" || !uri || seen.has(uri)) continue;
      seen.add(uri);
      items.push({ uri, filename: name, parsed: parseBillArtifactFilename(name, axis) });
    }
  }

  if (!items.length && document.s3_uri) {
    const name = artifactFilename(document.s3_uri);
    items.push({ uri: document.s3_uri, filename: name, parsed: parseBillArtifactFilename(name, axis) });
  }

  const realExec = asJsonObject(summary.real_execution);
  if (realExec) {
    for (const [key, uri] of Object.entries(realExec)) {
      if ((key !== "stdout" && key !== "stderr") || typeof uri !== "string" || !uri || seen.has(uri)) continue;
      seen.add(uri);
      const name = artifactFilename(uri);
      items.push({ uri, filename: name, parsed: parseBillArtifactFilename(name, axis) });
    }
  }

  return items;
}

const SECTION_ORDER: BillFileKind[] = ["summary", "customer", "channel", "detail", "other", "log"];

const SECTION_META: Record<BillFileKind, { id: string; title: string; hint?: string; collapsed?: boolean }> = {
  summary: { id: "summary", title: "汇总", hint: "全量合计，优先查看" },
  customer: { id: "customer", title: "分客户", hint: "按客户 ID 拆分的独立账单" },
  channel: { id: "channel", title: "分渠道", hint: "按上游渠道 ID 拆分的独立账单" },
  detail: { id: "detail", title: "逐条明细", hint: "需要核对单笔请求时使用" },
  other: { id: "other", title: "其他文件" },
  log: { id: "technical", title: "运行日志", hint: "仅供排查问题", collapsed: true },
};

export function groupBillDownloadItems(items: BillDownloadItem[], axis: BillObjectAxis): BillFileSection[] {
  const allowedKinds: BillFileKind[] =
    axis === "customer" ? ["summary", "customer", "detail", "other", "log"] : ["summary", "channel", "detail", "other", "log"];

  const buckets = new Map<BillFileKind, BillDownloadItem[]>();
  for (const item of items) {
    if (!allowedKinds.includes(item.parsed.kind)) continue;
    const list = buckets.get(item.parsed.kind) || [];
    list.push(item);
    buckets.set(item.parsed.kind, list);
  }

  const sections: BillFileSection[] = [];
  for (const kind of SECTION_ORDER) {
    if (!allowedKinds.includes(kind)) continue;
    const bucket = buckets.get(kind);
    if (!bucket?.length) continue;
    const meta = SECTION_META[kind];
    const sorted = [...bucket].sort((a, b) => {
      const idA = Number(a.parsed.entityId || 0);
      const idB = Number(b.parsed.entityId || 0);
      if (idA && idB && idA !== idB) return idA - idB;
      return a.parsed.title.localeCompare(b.parsed.title, "zh-CN");
    });
    sections.push({
      id: meta.id,
      title: meta.title,
      hint: meta.hint,
      collapsed: meta.collapsed,
      items: sorted,
    });
  }
  return sections;
}

export function billUsageStats(summary: JsonObject) {
  return {
    amount: Number(summary.total_usd),
    calls: Number(summary.total_calls),
    users: Number(summary.unique_users),
    models: Number(summary.unique_models),
    inputTokens: Number(summary.total_input_tokens),
    outputTokens: Number(summary.total_output_tokens),
  };
}

export function countSplitFiles(sections: BillFileSection[], axis: BillObjectAxis) {
  const key = axis === "customer" ? "customer" : "channel";
  const count = sections.find((s) => s.id === key)?.items.length || 0;
  return { customer: axis === "customer" ? count : 0, channel: axis === "channel" ? count : 0, total: count };
}

export const BILL_TYPE_GROUPS: Array<{
  id: string;
  label: string;
  axis: BillObjectAxis | "all";
  types: string[];
}> = [
  { id: "all", label: "全部账单", axis: "all", types: [] },
  { id: "customer_invoice", label: "客户版", axis: "customer", types: ["customer_invoice"] },
  { id: "internal_customer_bill", label: "内部版", axis: "customer", types: ["internal_customer_bill"] },
  { id: "channel_cost_bill", label: "渠道成本", axis: "channel", types: ["channel_cost_bill"] },
  { id: "daily_channel_cost_snapshot", label: "日成本", axis: "channel", types: ["daily_channel_cost_snapshot"] },
];

export const BILL_SIDEBAR_GROUPS: Array<{ axis: BillObjectAxis; label: string; typeIds: string[] }> = [
  { axis: "customer", label: "客户", typeIds: ["customer_invoice", "internal_customer_bill"] },
  { axis: "channel", label: "渠道", typeIds: ["channel_cost_bill", "daily_channel_cost_snapshot"] },
];
