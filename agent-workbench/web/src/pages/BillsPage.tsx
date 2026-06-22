import { useMemo, useState } from "react";
import {
  Bot,
  Building2,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  Download,
  FileSpreadsheet,
  Folder,
  Info,
  Layers,
  Loader2,
  Receipt,
  RefreshCw,
  Search,
  UserRound,
} from "lucide-react";
import { Badge, Button } from "../components/ui";
import {
  BILL_SIDEBAR_GROUPS,
  BILL_TYPE_GROUPS,
  buildBillBusinessRows,
  billDocumentAmount,
  billDocumentBusinessMetrics,
  billDocumentMoneyBreakdown,
  billObjectAxis,
  billObjectAxisLabel,
  billObjectCell,
  billTargetLabel,
  billTypeShort,
  billUsageStats,
  collectBillDownloadItems,
  countSplitFiles,
  formatBillMonth,
  groupBillDownloadItems,
  isAggregateBillDocument,
  isSplitBillDocument,
  resolveBillDate,
} from "../lib/billLibrary";
import { billingExecutionLabel } from "../lib/billing";
import { asJsonObject, billTypeText, formatDate, formatMoney, shortId, statusText, statusTone, textOf } from "../lib/format";
import type { BillBusinessRow, BillDownloadItem, BillFileSection } from "../lib/billLibrary";
import type { BillDocument, JsonObject, PageId } from "../types";
import type { WorkbenchState } from "../hooks/useWorkbench";

function billSummary(doc: BillDocument): JsonObject {
  return asJsonObject(doc.summary) || {};
}

function compactNumber(value: unknown): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("zh-CN", {
    notation: n >= 100000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(n);
}

function fileKindIcon(kind: string) {
  if (kind === "customer") return UserRound;
  if (kind === "channel") return Building2;
  if (kind === "summary") return Layers;
  return FileSpreadsheet;
}

function ObjectAxisBadge({ axis }: { axis: "customer" | "channel" }) {
  return (
    <span className={`bills-axis-badge bills-axis-badge-${axis}`}>
      {axis === "customer" ? <UserRound size={11} /> : <Building2 size={11} />}
      {billObjectAxisLabel(axis)}
    </span>
  );
}

function formatBusinessMoney(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? formatMoney(value) : "—";
}

function businessMargin(row: BillBusinessRow) {
  const base = row.payableUsd ?? row.revenueUsd ?? row.listPriceUsd;
  if (typeof base !== "number" || !Number.isFinite(base) || base === 0) return null;
  if (typeof row.profitUsd !== "number" || !Number.isFinite(row.profitUsd)) return null;
  return row.profitUsd / base;
}

function formatBusinessMargin(row: BillBusinessRow) {
  const margin = businessMargin(row);
  return margin === null ? "—" : `${(margin * 100).toFixed(1)}%`;
}

function sumBusinessMetric(rows: BillBusinessRow[], key: keyof Pick<BillBusinessRow, "listPriceUsd" | "payableUsd" | "revenueUsd" | "costUsd" | "profitUsd">) {
  const values = rows.map((row) => row[key]).filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  return values.length ? values.reduce((sum, value) => sum + value, 0) : null;
}

function businessPeriodLabel(value: string) {
  if (!value) return "—";
  return value.length === 7 ? formatBillMonth(value) : value;
}

function BusinessOverviewCard({ axis, rows }: { axis: "customer" | "channel"; rows: BillBusinessRow[] }) {
  const title = axis === "channel" ? "渠道经营概览" : "客户经营概览";
  const subtitle = axis === "channel" ? "按渠道汇总刊例价、成本和利润" : "按客户汇总刊例价、应付、成本和利润";
  const primaryLabel = axis === "channel" ? "渠道数" : "客户数";
  const revenueLabel = axis === "channel" ? "收入/应付" : "应付";
  const primaryAmount = axis === "channel" ? sumBusinessMetric(rows, "costUsd") : sumBusinessMetric(rows, "payableUsd");
  const primaryAmountLabel = axis === "channel" ? "成本" : "应付";

  return (
    <section className="bills-business-card">
      <div className="bills-business-head">
        <div>
          <span>{subtitle}</span>
          <strong>{title}</strong>
        </div>
        <ObjectAxisBadge axis={axis} />
      </div>
      <div className="bills-business-totals">
        <div>
          <span>{primaryLabel}</span>
          <strong>{rows.length}</strong>
        </div>
        <div>
          <span>刊例价</span>
          <strong>{formatBusinessMoney(sumBusinessMetric(rows, "listPriceUsd"))}</strong>
        </div>
        <div>
          <span>{primaryAmountLabel}</span>
          <strong>{formatBusinessMoney(primaryAmount)}</strong>
        </div>
        <div>
          <span>利润</span>
          <strong className={(sumBusinessMetric(rows, "profitUsd") ?? 0) < 0 ? "is-negative" : ""}>{formatBusinessMoney(sumBusinessMetric(rows, "profitUsd"))}</strong>
        </div>
      </div>
      {rows.length ? (
        <div className="bills-business-table-wrap">
          <table className="bills-business-table">
            <thead>
              <tr>
                <th>{axis === "channel" ? "渠道" : "客户"}</th>
                <th>刊例价</th>
                <th>{revenueLabel}</th>
                <th>成本</th>
                <th>利润</th>
                <th>利润率</th>
                <th>单据</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.axis}-${row.targetId}`}>
                  <td>
                    <strong>{row.displayName || row.targetLabel}</strong>
                    <small>{row.displayName ? row.targetLabel : businessPeriodLabel(row.latestPeriod)}</small>
                  </td>
                  <td>{formatBusinessMoney(row.listPriceUsd)}</td>
                  <td>{formatBusinessMoney(row.payableUsd ?? row.revenueUsd)}</td>
                  <td>{formatBusinessMoney(row.costUsd)}</td>
                  <td className={(row.profitUsd ?? 0) < 0 ? "is-negative" : ""}>{formatBusinessMoney(row.profitUsd)}</td>
                  <td>{formatBusinessMargin(row)}</td>
                  <td>
                    <span>{row.documentCount}</span>
                    <small>{row.sourceTypes.map((type) => billTypeShort(type)).join(" / ")}</small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="bills-business-empty">当前筛选下暂无可汇总金额</div>
      )}
    </section>
  );
}

export function BillsPage({ wb, switchPage }: { wb: WorkbenchState; switchPage: (page: PageId) => void }) {
  const [activeType, setActiveType] = useState("all");
  const [activeMonth, setActiveMonth] = useState("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [showUsageDetail, setShowUsageDetail] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});

  const docs = wb.billDocuments;

  const splitDocumentIndex = useMemo(() => {
    const index = new Map<string, BillDocument>();
    docs.forEach((doc) => {
      if (!isSplitBillDocument(doc)) return;
      const targetType = String(doc.target_type || "").trim();
      const targetId = String(doc.target_id || "").trim();
      if (!targetType || !targetId) return;
      const date = resolveBillDate(doc);
      index.set([doc.bill_type || "", date.raw || date.monthKey, targetType, targetId].join("|"), doc);
    });
    return index;
  }, [docs]);

  const months = useMemo(() => {
    const set = new Set<string>();
    docs.forEach((doc) => {
      const date = resolveBillDate(doc);
      if (date.monthKey) set.add(date.monthKey);
    });
    return [...set].sort((a, b) => b.localeCompare(a));
  }, [docs]);

  const normalizedQuery = query.trim().toLowerCase();
  const visibleDocs = useMemo(() => {
    return docs
      .filter((doc) => activeType === "all" || doc.bill_type === activeType)
      .filter((doc) => {
        if (activeMonth === "all") return true;
        return resolveBillDate(doc).monthKey === activeMonth;
      })
      .filter((doc) => {
        if (!normalizedQuery) return true;
        const date = resolveBillDate(doc);
        const object = billObjectCell(doc);
        const haystack = [
          date.label,
          date.dayLabel,
          date.monthKey,
          doc.target_id,
          billTypeText(doc.bill_type),
          billTypeShort(doc.bill_type),
          object.axisLabel,
          object.target,
          doc.status,
        ]
          .filter(Boolean)
          .map((value) => String(value).toLowerCase());
        return haystack.some((value) => value.includes(normalizedQuery));
      })
      .sort((a, b) => {
        const da = resolveBillDate(a);
        const db = resolveBillDate(b);
        const rawCmp = db.raw.localeCompare(da.raw);
        if (rawCmp !== 0) return rawCmp;
        return String(a.updated_at || a.created_at || "").localeCompare(String(b.updated_at || b.created_at || ""));
      });
  }, [docs, activeType, activeMonth, normalizedQuery]);

  const selected = visibleDocs.find((doc) => doc.id === selectedId) || visibleDocs[0];
  const currentType = BILL_TYPE_GROUPS.find((type) => type.id === activeType) || BILL_TYPE_GROUPS[0];
  const showDayColumn = activeType === "daily_channel_cost_snapshot" || activeType === "all";
  const businessRows = useMemo(() => buildBillBusinessRows(visibleDocs), [visibleDocs]);
  const channelBusinessRows = useMemo(() => businessRows.filter((row) => row.axis === "channel"), [businessRows]);
  const customerBusinessRows = useMemo(() => businessRows.filter((row) => row.axis === "customer"), [businessRows]);

  const docsForTotal = visibleDocs.some(isAggregateBillDocument) ? visibleDocs.filter(isAggregateBillDocument) : visibleDocs;
  const totalAmount = docsForTotal.reduce((sum, doc) => {
    const amount = billDocumentAmount(doc).amount;
    return Number.isFinite(amount) ? sum + amount : sum;
  }, 0);
  const deliveredCount = visibleDocs.filter((doc) => String(doc.status).toLowerCase() === "delivered").length;
  const readyCount = visibleDocs.filter((doc) => String(doc.status).toLowerCase() === "generated").length;

  const isBusy = wb.pending === "automation";
  const isRerunBusy = wb.pending === "run" || wb.pending === "billing";
  const isAgentBusy = wb.pending === "agent" || wb.pending === "agentMessage" || wb.pending === "agentStream";

  const selectedSummary = selected ? billSummary(selected) : {};
  const selectedAxis = selected ? billObjectAxis(selected) : "customer";
  const selectedDate = selected ? resolveBillDate(selected) : null;
  const selectedObject = selected ? billObjectCell(selected) : null;
  const selectedItems = selected ? collectBillDownloadItems(selected) : [];
  const selectedSections = groupBillDownloadItems(selectedItems, selectedAxis);
  const selectedHasReferenceableFiles = selectedItems.length > 0;
  const splitCounts = countSplitFiles(selectedSections, selectedAxis);
  const execLabel = selected ? billingExecutionLabel(selectedSummary) : null;
  const selectedStats = billUsageStats(selectedSummary);
  const selectedAmount = selected ? billDocumentAmount(selected) : null;
  const selectedMoneyMetrics = selected
    ? billDocumentMoneyBreakdown(selected).filter((metric) => metric.id !== selectedAmount?.id)
    : [];

  function splitDocumentForItem(parent: BillDocument, item: BillDownloadItem): BillDocument | null {
    const targetType = item.parsed.kind === "customer" ? "customer" : item.parsed.kind === "channel" ? "channel" : "";
    const targetId = item.parsed.entityId;
    if (!targetType || !targetId) return null;
    const date = resolveBillDate(parent);
    return splitDocumentIndex.get([parent.bill_type || "", date.raw || date.monthKey, targetType, targetId].join("|")) || null;
  }

  function toggleSection(id: string, defaultOpen: boolean) {
    setExpandedSections((prev) => {
      const current = prev[id] ?? defaultOpen;
      return { ...prev, [id]: !current };
    });
  }

  function isSectionOpen(sectionId: string, collapsed?: boolean) {
    if (sectionId in expandedSections) return expandedSections[sectionId];
    return !collapsed;
  }

  function billAgentPrompt(doc: BillDocument) {
    const date = resolveBillDate(doc);
    const axis = billObjectAxis(doc);
    return [
      "请基于我刚从账单库引用的账单进行对账。",
      `账单：${date.dayLabel || date.label} · ${billTypeText(doc.bill_type)} · ${billObjectAxisLabel(axis)} · ${billTargetLabel(doc)}。`,
      "请检查可能的对账差异，所有对账均基于刊例价进行，并列出关键证据、影响金额和下一步处理建议。",
    ].join("\n");
  }

  async function askAgentAboutBill(doc: BillDocument) {
    const sessionId = await wb.referenceBillDocumentToAgent(doc.id);
    if (!sessionId) return;
    switchPage("agent");
    await wb.sendAndStream(billAgentPrompt(doc), sessionId);
  }

  async function rerunBill(doc: BillDocument) {
    const confirmed = window.confirm(
      "确认重新生成这份账单？\n\n系统会使用当前生效的刊例价、折扣、成本和出账逻辑创建一份新账单，旧账单会保留。",
    );
    if (!confirmed) return;
    await wb.rerunBillDocument(doc.id);
  }

  return (
    <div className="bills-page">
      <section className="overview-strip overview-strip-compact bills-hero">
        <div className="overview-title">
          <span>账单库</span>
          <h3>客户与渠道分开管理 — 月账单看账期，日成本看具体日期</h3>
        </div>
        <div className="summary-card">
          <div>
            <span>本页账单</span>
            <strong>{visibleDocs.length}</strong>
          </div>
          <div>
            <span>合计金额</span>
            <strong>{formatMoney(totalAmount)}</strong>
          </div>
          <div>
            <span>待交付</span>
            <strong>{readyCount}</strong>
          </div>
          <div>
            <span>已交付</span>
            <strong>{deliveredCount}</strong>
          </div>
        </div>
      </section>

      <div className="bills-business-overview">
        <BusinessOverviewCard axis="channel" rows={channelBusinessRows} />
        <BusinessOverviewCard axis="customer" rows={customerBusinessRows} />
      </div>

      <div className="file-explorer bills-explorer">
        <div className="explorer-toolbar">
          <div className="explorer-nav">
            <Button variant="outline" size="icon" onClick={wb.refreshAutomation} disabled={isBusy} title="刷新列表">
              {isBusy ? <Loader2 size={16} className="spin" /> : <RefreshCw size={16} />}
            </Button>
          </div>
          <div className="breadcrumb-bar">
            <Receipt size={14} />
            <span>账单库</span>
            <strong>{currentType.label}</strong>
          </div>
          <label className="explorer-search">
            <Search size={15} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索日期、客户号、渠道号…" />
          </label>
          <div className="explorer-actions">
            <select className="bills-month-select" value={activeMonth} onChange={(event) => setActiveMonth(event.target.value)} title="账期月份">
              <option value="all">全部月份</option>
              {months.map((month) => (
                <option key={month} value={month}>
                  {formatBillMonth(month)}
                </option>
              ))}
            </select>
          </div>
        </div>

        <aside className="explorer-sidebar">
          <div className="explorer-tree">
            <button
              className={`tree-item ${activeType === "all" ? "active" : ""}`}
              onClick={() => {
                setActiveType("all");
                setSelectedId("");
              }}
            >
              <Folder size={16} />
              <span className="tree-item-text">
                <strong>全部账单</strong>
              </span>
              <small className="tree-item-count">{docs.length}</small>
            </button>

            {BILL_SIDEBAR_GROUPS.map((group) => (
              <div className="bills-tree-group" key={group.axis}>
                <div className="bills-tree-group-label">
                  <ObjectAxisBadge axis={group.axis} />
                </div>
                {BILL_TYPE_GROUPS.filter((type) => group.typeIds.includes(type.id)).map((type) => {
                  const count = docs.filter((doc) => doc.bill_type === type.id).length;
                  return (
                    <button
                      key={type.id}
                      className={`tree-item tree-item-nested ${activeType === type.id ? "active" : ""}`}
                      onClick={() => {
                        setActiveType(type.id);
                        setSelectedId("");
                      }}
                    >
                      <FileSpreadsheet size={15} />
                      <span className="tree-item-text">
                        <strong>{type.label}</strong>
                      </span>
                      <small className="tree-item-count">{count}</small>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </aside>

        <main className="explorer-main">
          <div className={`bill-list-head ${showDayColumn ? "bill-list-head-with-day" : ""}`}>
            <span>账期</span>
            {showDayColumn ? <span>具体日期</span> : null}
            <span>具体对象</span>
            <span>类型</span>
            <span>刊例价</span>
            <span>应付/收入</span>
            <span>成本</span>
            <span>利润</span>
            <span>状态</span>
          </div>
          <div className="file-list-body">
            {visibleDocs.map((doc) => {
              const amount = billDocumentAmount(doc);
              const business = billDocumentBusinessMetrics(doc);
              const date = resolveBillDate(doc);
              const object = billObjectCell(doc);
              const axis = billObjectAxis(doc);
              const splits = countSplitFiles(groupBillDownloadItems(collectBillDownloadItems(doc), axis), axis);
              return (
                <button
                  className={`bill-row ${showDayColumn ? "bill-row-with-day" : ""} ${selected?.id === doc.id ? "active" : ""}`}
                  key={doc.id}
                  onClick={() => setSelectedId(doc.id)}
                >
                  <span className="bill-month-cell">
                    <CalendarDays size={15} />
                    <strong>{formatBillMonth(date.monthKey)}</strong>
                  </span>
                  {showDayColumn ? (
                    <span className="bill-day-cell">
                      <strong>{date.dayLabel || "—"}</strong>
                    </span>
                  ) : null}
                  <span className="bill-target-cell">{object.target}</span>
                  <span className="bill-name-cell">
                    <strong>{billTypeShort(doc.bill_type)}</strong>
                    {splits.total > 0 ? <small>{splits.total} 份拆分</small> : null}
                  </span>
                  <span className="bill-amount" title="刊例价">
                    {formatBusinessMoney(business.listPriceUsd)}
                  </span>
                  <span className="bill-amount" title={amount.label}>
                    {formatBusinessMoney(business.payableUsd ?? business.revenueUsd)}
                  </span>
                  <span className="bill-amount" title="成本">
                    {formatBusinessMoney(business.costUsd)}
                  </span>
                  <span className={`bill-amount ${(business.profitUsd ?? 0) < 0 ? "is-negative" : ""}`} title="利润">
                    {formatBusinessMoney(business.profitUsd)}
                  </span>
                  <span>
                    <Badge tone={statusTone(doc.status)}>{statusText(doc.status)}</Badge>
                  </span>
                </button>
              );
            })}
            {!visibleDocs.length ? (
              <div className="explorer-empty">
                <Receipt size={28} />
                <span>当前筛选下暂无账单</span>
                <small>可在「自动化」页触发定时任务，或到「出账」页手动生成</small>
              </div>
            ) : null}
          </div>
        </main>

        <aside className="explorer-detail bills-detail-panel">
          {selected && selectedDate && selectedObject ? (
            <>
              <div className="bills-detail-header">
                <div className="detail-icon bills-detail-icon">
                  {selectedAxis === "customer" ? <UserRound size={28} /> : <Building2 size={28} />}
                </div>
                <div>
                  <div className="bills-detail-meta bills-detail-meta-top">
                    <ObjectAxisBadge axis={selectedObject.axis} />
                    <span className="bills-type-chip">{billTypeText(selected.bill_type)}</span>
                  </div>
                  <h3>
                    {selectedDate.dayLabel || selectedDate.label}
                    {selectedDate.dayLabel ? <small>{formatBillMonth(selectedDate.monthKey)}</small> : null}
                  </h3>
                  <div className="bills-detail-meta">
                    <Badge tone={statusTone(selected.status)}>{statusText(selected.status)}</Badge>
                    <span className="bills-scope-chip">{selectedObject.target}</span>
                    {splitCounts.total > 0 ? (
                      <span className="bills-split-chip">
                        {splitCounts.total} 份{selectedAxis === "customer" ? "客户" : "渠道"}拆分
                      </span>
                    ) : null}
                  </div>
                </div>
              </div>

              {execLabel ? <div className={`billing-banner billing-banner-${execLabel.tone}`}>{execLabel.text}</div> : null}

              <div className="bills-agent-actions">
                <Button variant="outline" onClick={() => void rerunBill(selected)} disabled={isRerunBusy}>
                  {isRerunBusy ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />}
                  重新出这份账单
                </Button>
                <span>使用当前生效的刊例价、折扣、成本和出账逻辑重新生成，旧账单保留。</span>
                <Button onClick={() => void askAgentAboutBill(selected)} disabled={isAgentBusy || !selectedHasReferenceableFiles}>
                  {isAgentBusy ? <Loader2 size={15} className="spin" /> : <Bot size={15} />}
                  引用账单并开始对账
                </Button>
                <span>{selectedHasReferenceableFiles ? "Agent 会读取此账单的汇总、Excel 和可用日志，并按刊例价口径核对。" : "此账单暂无可引用文件。"}</span>
              </div>

              <div className="bills-date-strip">
                <div>
                  <span>账期</span>
                  <strong>{formatBillMonth(selectedDate.monthKey)}</strong>
                </div>
                <div>
                  <span>具体日期</span>
                  <strong>{selectedDate.dayLabel || "—"}</strong>
                </div>
                <div>
                  <span>对象</span>
                  <strong>{billObjectAxisLabel(selectedAxis)} · {billTargetLabel(selected)}</strong>
                </div>
              </div>

              <div className="bill-kpi-grid bills-kpi-compact">
                <div className="bill-kpi bill-kpi-primary">
                  <span>{selectedAmount?.label || "账单金额"}</span>
                  <strong>{formatMoney(selectedAmount?.amount ?? Number.NaN)}</strong>
                </div>
                <div className="bill-kpi">
                  <span>调用次数</span>
                  <strong>{compactNumber(selectedStats.calls)}</strong>
                </div>
                <div className="bill-kpi">
                  <span>{selectedAxis === "customer" ? "涉及客户" : "涉及用户"}</span>
                  <strong>{compactNumber(selectedStats.users)}</strong>
                </div>
              </div>
              {selectedMoneyMetrics.length ? (
                <div className="bill-kpi-grid bills-kpi-money">
                  {selectedMoneyMetrics.map((metric) => (
                    <div className="bill-kpi" key={metric.id}>
                      <span>{metric.label}</span>
                      <strong>{formatMoney(metric.amount)}</strong>
                    </div>
                  ))}
                </div>
              ) : null}

              <button type="button" className="bills-usage-toggle" onClick={() => setShowUsageDetail((open) => !open)}>
                <ChevronDown size={14} className={showUsageDetail ? "is-open" : ""} />
                {showUsageDetail ? "收起用量详情" : "查看更多用量数据"}
              </button>
              {showUsageDetail ? (
                <div className="bill-kpi-grid bills-kpi-secondary">
                  <div className="bill-kpi">
                    <span>活跃模型</span>
                    <strong>{compactNumber(selectedStats.models)}</strong>
                  </div>
                  <div className="bill-kpi">
                    <span>输入 Token</span>
                    <strong>{compactNumber(selectedStats.inputTokens)}</strong>
                  </div>
                  <div className="bill-kpi">
                    <span>输出 Token</span>
                    <strong>{compactNumber(selectedStats.outputTokens)}</strong>
                  </div>
                  <div className="bill-kpi">
                    <span>最近更新</span>
                    <strong className="bill-kpi-date">{formatDate(selected.updated_at || selected.created_at)}</strong>
                  </div>
                </div>
              ) : null}

              <div className="bill-files-block">
                <div className="bill-files-title">
                  {selectedAxis === "customer" ? "客户账单文件" : "渠道账单文件"}
                </div>
                {selectedSections.length ? (
                  selectedSections.map((section: BillFileSection) => {
                    const open = isSectionOpen(section.id, section.collapsed);
                    const Icon = section.id === "customer" ? UserRound : section.id === "channel" ? Building2 : Layers;
                    return (
                      <div className={`bill-file-section ${open ? "is-open" : "is-collapsed"}`} key={section.id}>
                        <button type="button" className="bill-file-section-head" onClick={() => toggleSection(section.id, !section.collapsed)}>
                          <Icon size={15} />
                          <span className="bill-file-section-title">{section.title}</span>
                          <span className="bill-file-section-count">{section.items.length} 个</span>
                          <ChevronDown size={14} className={open ? "is-open" : ""} />
                        </button>
                        {section.hint && open ? <p className="bill-file-section-hint">{section.hint}</p> : null}
                        {open ? (
                          <div className="bill-file-cards">
                            {section.items.map((item: BillDownloadItem) => {
                              const ItemIcon = fileKindIcon(item.parsed.kind);
                              const itemDocument = splitDocumentForItem(selected, item);
                              const itemAmount = itemDocument ? billDocumentAmount(itemDocument) : null;
                              return (
                                <button
                                  key={item.uri}
                                  type="button"
                                  className="bill-file-card"
                                  onClick={() => wb.downloadArtifact({ uri: item.uri, filename: item.filename })}
                                >
                                  <div className={`bill-file-card-icon bill-file-card-icon-${item.parsed.kind}`}>
                                    <ItemIcon size={16} />
                                  </div>
                                  <div className="bill-file-card-body">
                                    <strong>{item.parsed.title}</strong>
                                    <span>{item.parsed.subtitle}</span>
                                    {itemAmount ? (
                                      <small className="bill-file-card-amount">
                                        {itemAmount.label}: {formatMoney(itemAmount.amount)}
                                      </small>
                                    ) : null}
                                  </div>
                                  <Download size={15} className="bill-file-card-dl" />
                                </button>
                              );
                            })}
                          </div>
                        ) : null}
                      </div>
                    );
                  })
                ) : (
                  <p className="muted-inline">暂无可下载文件。若为演练任务，需切换为真实出账后才会生成 Excel。</p>
                )}
              </div>

              {selected.bill_type === "customer_invoice" && String(selected.status).toLowerCase() === "generated" ? (
                <Button className="section-block bills-deliver-btn" onClick={() => wb.publishBillDocument(selected.id)} disabled={isBusy}>
                  {isBusy ? <Loader2 size={15} className="spin" /> : <CheckCircle2 size={15} />}
                  标记为已交付
                </Button>
              ) : null}
              {selected.bill_type === "customer_invoice" && String(selected.status).toLowerCase() === "delivered" ? (
                <div className="bills-delivered-note">
                  <CheckCircle2 size={14} />
                  已交付给客户
                </div>
              ) : null}

              <details className="advanced-panel bills-tech-panel">
                <summary>技术信息</summary>
                <div className="detail-kv bills-tech-kv">
                  <span>文档 ID</span>
                  <strong>{shortId(selected.id)}</strong>
                  <span>任务 ID</span>
                  <strong>{shortId(selected.billing_run_id || selected.job_id)}</strong>
                  {selectedDate.raw ? (
                    <>
                      <span>数据日期</span>
                      <strong>{selectedDate.raw}</strong>
                    </>
                  ) : null}
                  <span>配置版本</span>
                  <strong>{textOf(selectedSummary.config_version, "—")}</strong>
                  {selected.s3_uri ? (
                    <>
                      <span>存储</span>
                      <strong className="bills-tech-uri">{selected.s3_uri}</strong>
                    </>
                  ) : null}
                </div>
              </details>
            </>
          ) : (
            <>
              <div className="detail-icon">
                <Info size={30} />
              </div>
              <h3>{currentType.label}</h3>
              <div className="detail-kv">
                <span>账单数</span>
                <strong>{visibleDocs.length}</strong>
                <span>合计金额</span>
                <strong>{formatMoney(totalAmount)}</strong>
              </div>
              <p className="muted-inline">左侧按客户 / 渠道分类，点击列表中的账单查看详情与下载。</p>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
