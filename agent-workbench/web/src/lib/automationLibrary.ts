import {
  billObjectAxis,
  billObjectAxisLabel,
  billTargetLabel,
  billTypeShort,
  formatBillDay,
  formatBillMonth,
  isAggregateBillDocument,
  isSplitBillDocument,
  parseSplitTargetsFromGenerated,
  resolveBillDate,
} from "./billLibrary";
import { asJsonObject, billTypeText, shortId } from "./format";
import type { BillDocument, BillingBatch, JobQueue, JobSummary, JsonObject, Schedule, ScheduleRun } from "../types";

export type StageState = "done" | "active" | "pending" | "error";

export type ProgressStage = {
  id: string;
  label: string;
  state: StageState;
  detail?: string;
};

export type NextAction = {
  tone: "primary" | "warning" | "success" | "muted";
  title: string;
  description: string;
  action?: "retry" | "deliver" | "run_schedule" | "open_bills" | "refresh";
  actionLabel?: string;
  actionTarget?: string;
};

export type RunTaskPhase = "waiting" | "running" | "done" | "failed";

export type RunTaskItem = {
  index: number;
  jobId: string;
  billingRunId: string;
  billType: string;
  axis: "customer" | "channel";
  targetLabel: string;
  periodLabel: string;
  jobStatus: string;
  documentStatus: string;
  phase: RunTaskPhase;
  queuePosition: number | null;
  createdBy?: string;
  startedAt?: string;
  finishedAt?: string;
  error?: string;
  documentId?: string;
  documentLabel?: string;
  rowKind: "job" | "summary" | "split";
  jobTaskIndex?: number;
};

export type BillingQueueItem = {
  position: number;
  jobId: string;
  billType: string;
  periodLabel: string;
  status: string;
  createdBy?: string;
  isCurrentRun: boolean;
};

export type RunProgress = {
  run: ScheduleRun | null;
  batch: BillingBatch | null;
  documents: BillDocument[];
  jobs: JobSummary[];
  stages: ProgressStage[];
  progressPercent: number;
  isActive: boolean;
  title: string;
  subtitle: string;
  periodLabel: string;
};

const SCHEDULE_TYPE_LABELS: Record<string, string> = {
  daily_channel_cost_snapshot: "每日渠道成本",
  monthly_customer_invoices: "每月客户版",
  monthly_internal_channel_bills: "每月内部+渠道",
};

export function scheduleTypeLabel(scheduleType?: string): string {
  return SCHEDULE_TYPE_LABELS[String(scheduleType || "")] || billTypeText(scheduleType);
}

export function cronHumanLabel(cron?: string, timezone?: string): string {
  const expr = String(cron || "").trim();
  if (!expr) return "—";
  const parts = expr.split(/\s+/);
  if (parts.length < 5) return expr;
  const [min, hour, dom, ,] = parts;
  const time = `${hour.padStart(2, "0")}:${min.padStart(2, "0")}`;
  let cadence = expr;
  if (dom !== "*" && dom !== "?") cadence = `每月 ${dom} 日 ${time}`;
  else if (parts[4] !== "*" && parts[4] !== "?") cadence = `每周 ${time}`;
  else cadence = `每天 ${time}`;
  const tz = timezone === "Asia/Hong_Kong" ? "香港时间" : timezone || "";
  return tz ? `${cadence} · ${tz}` : cadence;
}

function normalizeStatus(value?: string): string {
  return String(value || "").toLowerCase();
}

function docsForRun(
  documents: BillDocument[],
  runId?: string,
  batchId?: string,
  run?: ScheduleRun | null,
  batch?: BillingBatch | null,
): BillDocument[] {
  if (!runId && !batchId) return [];
  const planned = plannedJobsFromRun(run || null, batch || null);
  const jobIds = new Set(planned.map((entry) => String(entry.job_id || "")).filter(Boolean));
  const billingRunIds = new Set(planned.map((entry) => String(entry.billing_run_id || "")).filter(Boolean));
  const merged = new Map<string, BillDocument>();
  for (const doc of documents) {
    const linked =
      doc.schedule_run_id === runId ||
      doc.batch_id === batchId ||
      (doc.job_id && jobIds.has(doc.job_id)) ||
      (doc.billing_run_id && billingRunIds.has(doc.billing_run_id));
    if (linked && doc.id) merged.set(doc.id, doc);
  }
  return [...merged.values()];
}

function jobsForDocuments(jobs: JobSummary[], documents: BillDocument[]): JobSummary[] {
  const ids = new Set<string>();
  for (const doc of documents) {
    if (doc.job_id) ids.add(doc.job_id);
    if (doc.billing_run_id) ids.add(doc.billing_run_id);
  }
  return jobs.filter((job) => ids.has(String(job.id)) || (job.billing_run_id && ids.has(String(job.billing_run_id))));
}

function periodLabelForRun(run?: ScheduleRun | null, batch?: BillingBatch | null): string {
  const period = String(run?.period || batch?.month || "").trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(period)) return formatBillDay(period);
  if (/^\d{4}-\d{2}$/.test(period)) return formatBillMonth(period);
  return period || "—";
}

export function pickLatestRunContext(
  scheduleRuns: ScheduleRun[],
  batches: BillingBatch[],
  documents: BillDocument[],
  jobQueue: JobQueue | null,
): { run: ScheduleRun | null; batch: BillingBatch | null } {
  const queueJobs = (jobQueue?.items || []).filter((job) => normalizeStatus(job.type) === "billing_run");
  const activeBatch = batches.find((batch) => normalizeStatus(batch.status) === "rendering");
  if (activeBatch) {
    const run = scheduleRuns.find((item) => item.id === activeBatch.schedule_run_id) || null;
    return { run, batch: activeBatch };
  }

  if (queueJobs.length) {
    const runIds = new Set(documents.map((doc) => doc.schedule_run_id).filter(Boolean));
    const latestRun = scheduleRuns.find((run) => runIds.has(run.id)) || scheduleRuns[0] || null;
    const batch = batches.find((item) => item.schedule_run_id === latestRun?.id) || batches[0] || null;
    return { run: latestRun, batch };
  }

  const latestRun = scheduleRuns[0] || null;
  const batch = batches.find((item) => item.schedule_run_id === latestRun?.id) || batches[0] || null;
  return { run: latestRun, batch };
}

export function buildRunProgress(
  run: ScheduleRun | null,
  batch: BillingBatch | null,
  allDocuments: BillDocument[],
  allJobs: JobSummary[],
  jobQueue: JobQueue | null,
): RunProgress {
  const documents = docsForRun(allDocuments, run?.id, batch?.id, run, batch);
  const queueItems = (jobQueue?.items || []).filter((job) => normalizeStatus(job.type) === "billing_run");
  const runJobIds = new Set(plannedJobsFromRun(run, batch).map((entry) => String(entry.job_id || "")).filter(Boolean));
  const relatedJobs = [
    ...allJobs.filter((job) => runJobIds.has(job.id) || documents.some((doc) => doc.job_id === job.id || doc.billing_run_id === job.billing_run_id)),
    ...queueItems.filter((job) => runJobIds.has(job.id) || documents.some((doc) => doc.job_id === job.id)),
  ].filter((job, index, arr) => arr.findIndex((item) => item.id === job.id) === index);
  const jobs = relatedJobs.length ? relatedJobs : jobsForDocuments([...allJobs, ...queueItems], documents);

  const totalDocs = documents.length;
  const generatedDocs = documents.filter((doc) => normalizeStatus(doc.status) === "generated").length;
  const deliveredDocs = documents.filter((doc) => normalizeStatus(doc.status) === "delivered").length;
  const failedDocs = documents.filter((doc) => normalizeStatus(doc.status).includes("failed")).length;
  const pendingDocs = documents.filter((doc) => ["created", "draft"].includes(normalizeStatus(doc.status))).length;

  const runningJobs = jobs.filter((job) => normalizeStatus(job.status) === "running").length;
  const queuedJobs = jobs.filter((job) => normalizeStatus(job.status) === "queued").length;
  const failedJobs = jobs.filter((job) => normalizeStatus(job.status) === "failed").length;

  const customerGenerated = documents.filter(
    (doc) => doc.bill_type === "customer_invoice" && normalizeStatus(doc.status) === "generated",
  ).length;

  const stages: ProgressStage[] = [
    {
      id: "batch",
      label: "创建批次",
      state: batch || run ? "done" : "pending",
      detail: batch ? `批次 ${batch.month || ""}`.trim() : undefined,
    },
    {
      id: "queue",
      label: "排队出账",
      state: failedJobs ? "error" : queuedJobs ? "active" : batch || jobs.length ? "done" : "pending",
      detail: queuedJobs ? `${queuedJobs} 个任务排队中` : jobs.length ? "已进入执行队列" : undefined,
    },
    {
      id: "generate",
      label: "生成账单",
      state: failedDocs ? "error" : runningJobs || pendingDocs ? "active" : totalDocs && generatedDocs === totalDocs ? "done" : totalDocs ? "active" : "pending",
      detail: totalDocs ? `${generatedDocs}/${totalDocs} 已生成` : undefined,
    },
    {
      id: "deliver",
      label: "客户交付",
      state: customerGenerated ? "active" : deliveredDocs ? "done" : totalDocs && generatedDocs === totalDocs ? "pending" : "pending",
      detail: customerGenerated ? `${customerGenerated} 份待交付` : deliveredDocs ? `${deliveredDocs} 份已交付` : "无客户版或已完成",
    },
  ];

  const completedStages = stages.filter((stage) => stage.state === "done").length;
  const activeStages = stages.filter((stage) => stage.state === "active").length;
  const progressPercent = Math.min(
    100,
    Math.round(((completedStages + activeStages * 0.5) / stages.length) * 100),
  );

  const isActive = Boolean(
    runningJobs ||
      queuedJobs ||
      pendingDocs ||
      normalizeStatus(batch?.status) === "rendering" ||
      (totalDocs > 0 && generatedDocs + failedDocs < totalDocs),
  );

  const title = run?.schedule_name || scheduleTypeLabel(run?.schedule_type) || "最近运行";
  const subtitle = run ? cronHumanLabel(undefined, undefined) : "尚未触发定时任务";
  const periodLabel = periodLabelForRun(run, batch);

  return {
    run,
    batch,
    documents,
    jobs,
    stages,
    progressPercent,
    isActive,
    title,
    subtitle: run?.schedule_type ? scheduleTypeLabel(run.schedule_type) : subtitle,
    periodLabel,
  };
}

export function buildNextAction(
  progress: RunProgress,
  schedules: Schedule[],
  allDocuments: BillDocument[],
): NextAction {
  const { run, batch, documents, jobs, isActive } = progress;
  const failedDocs = documents.filter((doc) => normalizeStatus(doc.status).includes("failed"));
  const customerPending = documents.filter(
    (doc) => doc.bill_type === "customer_invoice" && normalizeStatus(doc.status) === "generated",
  );
  const runningJobs = jobs.filter((job) => normalizeStatus(job.status) === "running");
  const queuedJobs = jobs.filter((job) => normalizeStatus(job.status) === "queued");

  if (failedDocs.length && run?.id) {
    return {
      tone: "warning",
      title: "有账单生成失败",
      description: `${failedDocs.length} 份账单失败，可重试失败项后继续流程。`,
      action: "retry",
      actionLabel: "重试失败账单",
      actionTarget: run.id,
    };
  }

  if (runningJobs.length) {
    const job = runningJobs[0];
    return {
      tone: "primary",
      title: "正在生成账单",
      description: `出账任务运行中（${billTypeShort(job.result?.bill_type || documents[0]?.bill_type)}），请稍候刷新查看进度。`,
      action: "refresh",
      actionLabel: "刷新进度",
    };
  }

  if (queuedJobs.length) {
    return {
      tone: "primary",
      title: "等待 Worker 执行",
      description: `${queuedJobs.length} 个出账任务已排队，Worker 拉取后将开始生成 Excel。`,
      action: "refresh",
      actionLabel: "刷新进度",
    };
  }

  if (customerPending.length) {
    return {
      tone: "success",
      title: "客户账单已就绪",
      description: `${customerPending.length} 份客户版账单待标记交付，完成后可在账单库下载。`,
      action: "deliver",
      actionLabel: `交付 ${customerPending.length} 份客户账单`,
      actionTarget: customerPending[0]?.id,
    };
  }

  if (isActive) {
    return {
      tone: "primary",
      title: "月结流程进行中",
      description: `当前账期 ${progress.periodLabel}，系统仍在处理批次任务。`,
      action: "refresh",
      actionLabel: "刷新进度",
    };
  }

  const enabledSchedules = schedules.filter((schedule) => schedule.enabled !== false);
  const daily = enabledSchedules.find((schedule) => schedule.schedule_type === "daily_channel_cost_snapshot");
  const monthly = enabledSchedules.find((schedule) => schedule.schedule_type === "monthly_customer_invoices");

  if (allDocuments.some((doc) => normalizeStatus(doc.status) === "generated")) {
    return {
      tone: "muted",
      title: "暂无进行中的任务",
      description: "有已生成账单可在账单库查看；如需补跑，可选择左侧定时任务立即运行。",
      action: "open_bills",
      actionLabel: "打开账单库",
    };
  }

  const suggest = daily || monthly || enabledSchedules[0];
  if (suggest) {
    return {
      tone: "muted",
      title: "下一步建议",
      description: `可手动触发「${suggest.name || scheduleTypeLabel(suggest.schedule_type)}」，或等待 ${cronHumanLabel(suggest.cron_expr, suggest.timezone)} 自动执行。`,
      action: "run_schedule",
      actionLabel: "立即运行",
      actionTarget: suggest.id,
    };
  }

  return {
    tone: "muted",
    title: "暂无定时任务",
    description: "请先在系统中配置账单自动化任务。",
  };
}

export function documentProgressLabel(doc: BillDocument): string {
  const axis = billObjectAxisLabel(billObjectAxis(doc));
  const date = resolveBillDate(doc);
  return `${date.dayLabel || date.label} · ${axis} · ${billTargetLabel(doc)} · ${billTypeShort(doc.bill_type)}`;
}

export function runDocumentsSummary(documents: BillDocument[]) {
  const total = documents.length;
  const generated = documents.filter((doc) => normalizeStatus(doc.status) === "generated").length;
  const delivered = documents.filter((doc) => normalizeStatus(doc.status) === "delivered").length;
  const failed = documents.filter((doc) => normalizeStatus(doc.status).includes("failed")).length;
  const pending = total - generated - delivered - failed;
  return { total, generated, delivered, failed, pending };
}

function findJob(allJobs: JobSummary[], queueJobs: JobSummary[], jobId: string, billingRunId: string): JobSummary | undefined {
  return (
    allJobs.find((job) => job.id === jobId) ||
    queueJobs.find((job) => job.id === jobId) ||
    allJobs.find((job) => job.billing_run_id === billingRunId) ||
    queueJobs.find((job) => job.billing_run_id === billingRunId)
  );
}

function queuePositionFor(jobId: string, queueJobs: JobSummary[]): number | null {
  const billingQueued = queueJobs
    .filter((job) => normalizeStatus(job.type) === "billing_run" && normalizeStatus(job.status) === "queued")
    .sort((a, b) => String(a.created_at || "").localeCompare(String(b.created_at || "")));
  const index = billingQueued.findIndex((job) => job.id === jobId);
  return index >= 0 ? index + 1 : null;
}

function inferTaskPhase(jobStatus: string, documentStatus: string): RunTaskPhase {
  if (normalizeStatus(jobStatus) === "failed" || normalizeStatus(documentStatus).includes("failed")) return "failed";
  if (normalizeStatus(jobStatus) === "running") return "running";
  if (normalizeStatus(documentStatus) === "generated" || normalizeStatus(documentStatus) === "delivered") return "done";
  if (normalizeStatus(jobStatus) === "completed") return "done";
  if (normalizeStatus(jobStatus) === "queued" || normalizeStatus(jobStatus) === "created") return "waiting";
  return "waiting";
}

function taskPeriodLabel(doc: BillDocument | undefined, job: JobSummary | undefined, run: ScheduleRun | null, batch: BillingBatch | null): string {
  if (doc) return resolveBillDate(doc).dayLabel || resolveBillDate(doc).label;
  const period = String(run?.period || batch?.month || job?.month || "").trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(period)) return formatBillDay(period);
  if (/^\d{4}-\d{2}$/.test(period)) return formatBillMonth(period);
  return period || "—";
}

function documentsForJob(documents: BillDocument[], jobId: string, billingRunId: string): BillDocument[] {
  return documents.filter(
    (doc) => (jobId && doc.job_id === jobId) || (billingRunId && doc.billing_run_id === billingRunId),
  );
}

function sortTaskDocuments(documents: BillDocument[]): BillDocument[] {
  return [...documents].sort((a, b) => {
    const aAgg = isAggregateBillDocument(a);
    const bAgg = isAggregateBillDocument(b);
    if (aAgg !== bAgg) return aAgg ? -1 : 1;
    return String(a.target_id || "").localeCompare(String(b.target_id || ""), undefined, { numeric: true });
  });
}

function virtualSplitDocuments(parent: BillDocument, linked: BillDocument[]): BillDocument[] {
  const summary = asJsonObject(parent.summary) || {};
  const axis = billObjectAxis(parent);
  const splits = parseSplitTargetsFromGenerated(summary, axis);
  if (!splits.length) return [];

  const existingTargets = new Set(
    linked
      .filter((doc) => isSplitBillDocument(doc))
      .map((doc) => `${String(doc.target_type || "")}:${String(doc.target_id || "")}`),
  );

  return splits
    .filter((split) => !existingTargets.has(`${split.targetType}:${split.targetId}`))
    .map(
      (split) =>
        ({
          ...parent,
          id: `virtual-${parent.id}-${split.targetType}-${split.targetId}`,
          target_type: split.targetType,
          target_id: split.targetId,
          status: parent.status,
          summary: {
            ...summary,
            generated_files: { [split.filename]: split.uri },
            split_entity: true,
            virtual_split: true,
          },
        }) as BillDocument,
    );
}

function expandJobDocuments(
  documents: BillDocument[],
  jobId: string,
  billingRunId: string,
  fallback: BillDocument,
): BillDocument[] {
  const linked = sortTaskDocuments(documentsForJob(documents, jobId, billingRunId));
  if (linked.length > 1) return linked;

  const parent = linked[0] || fallback;
  const splitLinked = linked.filter((doc) => isSplitBillDocument(doc));
  if (splitLinked.length > 0) return sortTaskDocuments(linked);

  const virtuals = virtualSplitDocuments(parent, linked);
  if (virtuals.length) return sortTaskDocuments([parent, ...virtuals]);
  return linked.length ? linked : parent.id ? [parent] : [];
}

function documentRowKind(doc: BillDocument): RunTaskItem["rowKind"] {
  if (isSplitBillDocument(doc)) return "split";
  if (isAggregateBillDocument(doc)) return "summary";
  return "job";
}

function documentLabel(doc: BillDocument): string {
  const summary = asJsonObject(doc.summary) || {};
  if (summary.virtual_split) return "拆分产物（待入库）";
  if (isSplitBillDocument(doc)) return "拆分账单";
  if (isAggregateBillDocument(doc)) return "汇总账单";
  return "账单";
}

function buildTaskItemFromDocument(
  doc: BillDocument,
  ctx: {
    index: number;
    jobTaskIndex: number;
    jobId: string;
    billingRunId: string;
    billType: string;
    job: JobSummary | undefined;
    run: ScheduleRun | null;
    batch: BillingBatch | null;
    queueJobs: JobSummary[];
  },
): RunTaskItem {
  const jobStatus = normalizeStatus(ctx.job?.status || "created");
  const documentStatus = normalizeStatus(doc.status || "created");
  const axis = billObjectAxis(doc);
  return {
    index: ctx.index,
    jobTaskIndex: ctx.jobTaskIndex,
    jobId: ctx.jobId || ctx.job?.id || doc.job_id || "—",
    billingRunId: ctx.billingRunId || ctx.job?.billing_run_id || doc.billing_run_id || "—",
    billType: String(doc.bill_type || ctx.billType || ctx.job?.bill_type || ""),
    axis,
    targetLabel: billTargetLabel(doc),
    periodLabel: taskPeriodLabel(doc, ctx.job, ctx.run, ctx.batch),
    jobStatus,
    documentStatus,
    phase: inferTaskPhase(jobStatus, documentStatus),
    queuePosition: ctx.jobId ? queuePositionFor(ctx.jobId, ctx.queueJobs) : null,
    createdBy: ctx.job?.created_by,
    startedAt: ctx.job?.started_at,
    finishedAt: ctx.job?.finished_at,
    error: ctx.job?.error_message,
    documentId: doc.id?.startsWith("virtual-") ? undefined : doc.id,
    documentLabel: documentLabel(doc),
    rowKind: documentRowKind(doc),
  };
}

export function countRunTaskJobs(tasks: RunTaskItem[]): number {
  return new Set(tasks.map((task) => task.jobId).filter((id) => id !== "—")).size;
}

export function countRunTaskDocuments(tasks: RunTaskItem[]): number {
  return tasks.length;
}

function plannedJobsFromRun(run: ScheduleRun | null, batch: BillingBatch | null): Array<{ job_id?: string; billing_run_id?: string; bill_type?: string }> {
  const runSummary = summaryFromRun(run);
  const batchSummary = asJsonObject(batch?.summary) || {};
  const fromRun = Array.isArray(runSummary.jobs) ? runSummary.jobs : [];
  if (fromRun.length) return fromRun as Array<{ job_id?: string; billing_run_id?: string; bill_type?: string }>;
  const fromBatch = Array.isArray(batchSummary.jobs) ? batchSummary.jobs : [];
  return fromBatch as Array<{ job_id?: string; billing_run_id?: string; bill_type?: string }>;
}

export function buildRunTasks(
  run: ScheduleRun | null,
  batch: BillingBatch | null,
  documents: BillDocument[],
  allJobs: JobSummary[],
  queueJobs: JobSummary[],
): RunTaskItem[] {
  const planned = plannedJobsFromRun(run, batch);
  const tasks: RunTaskItem[] = [];
  let rowIndex = 0;

  if (planned.length) {
    planned.forEach((entry, jobIndex) => {
      const jobId = String(entry.job_id || "");
      const billingRunId = String(entry.billing_run_id || "");
      const billType = String(entry.bill_type || "");
      const job = findJob(allJobs, queueJobs, jobId, billingRunId);
      const seedDoc = documents.find((item) => item.job_id === jobId || item.billing_run_id === billingRunId);
      const fallback = seedDoc || ({
        bill_type: billType || job?.bill_type,
        target_type: job?.target_type,
        target_id: job?.target_id,
        month: job?.month || batch?.month,
        job_id: jobId || job?.id,
        billing_run_id: billingRunId || job?.billing_run_id,
        summary: {},
      } as BillDocument);
      const expanded = expandJobDocuments(documents, jobId, billingRunId, fallback);

      expanded.forEach((doc) => {
        rowIndex += 1;
        tasks.push(
          buildTaskItemFromDocument(doc, {
            index: rowIndex,
            jobTaskIndex: jobIndex + 1,
            jobId,
            billingRunId,
            billType,
            job,
            run,
            batch,
            queueJobs,
          }),
        );
      });
    });
    return tasks;
  }

  return sortTaskDocuments(documents).map((doc, index) => {
    const job = findJob(allJobs, queueJobs, String(doc.job_id || ""), String(doc.billing_run_id || ""));
    return buildTaskItemFromDocument(doc, {
      index: index + 1,
      jobTaskIndex: index + 1,
      jobId: String(doc.job_id || job?.id || ""),
      billingRunId: String(doc.billing_run_id || job?.billing_run_id || ""),
      billType: String(doc.bill_type || job?.bill_type || ""),
      job,
      run,
      batch,
      queueJobs,
    });
  });
}

export function buildGlobalBillingQueue(
  allJobs: JobSummary[],
  queueJobs: JobSummary[],
  currentRunJobIds: Set<string>,
): BillingQueueItem[] {
  const merged = new Map<string, JobSummary>();
  for (const job of [...allJobs, ...queueJobs]) {
    if (normalizeStatus(job.type) !== "billing_run") continue;
    if (!merged.has(job.id)) merged.set(job.id, job);
  }
  const active = [...merged.values()]
    .filter((job) => ["queued", "running"].includes(normalizeStatus(job.status)))
    .sort((a, b) => String(a.created_at || "").localeCompare(String(b.created_at || "")));

  return active.map((job, index) => ({
    position: index + 1,
    jobId: job.id,
    billType: String(job.bill_type || "internal_customer_bill"),
    periodLabel: /^\d{4}-\d{2}-\d{2}$/.test(String(job.month || "")) ? formatBillDay(job.month) : formatBillMonth(job.month),
    status: normalizeStatus(job.status),
    createdBy: job.created_by,
    isCurrentRun: currentRunJobIds.has(job.id),
  }));
}

export function taskPhaseLabel(phase: RunTaskPhase): string {
  const map: Record<RunTaskPhase, string> = {
    waiting: "排队等待",
    running: "正在出账",
    done: "已完成",
    failed: "失败",
  };
  return map[phase];
}

export function createdByLabel(value?: string): string {
  const raw = String(value || "").trim();
  if (!raw) return "—";
  if (raw === "scheduler") return "定时调度";
  if (raw === "ops" || raw === "user") return "手动触发";
  return raw;
}

export function summaryFromRun(run?: ScheduleRun | null): JsonObject {
  return asJsonObject(run?.summary) || {};
}
