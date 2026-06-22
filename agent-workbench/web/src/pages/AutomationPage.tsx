import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Building2,
  CalendarClock,
  CheckCircle2,
  CircleDashed,
  Clock3,
  Loader2,
  Play,
  RefreshCw,
  Search,
  UserRound,
  Zap,
} from "lucide-react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from "../components/ui";
import {
  buildGlobalBillingQueue,
  buildNextAction,
  buildRunProgress,
  buildRunTasks,
  countRunTaskDocuments,
  countRunTaskJobs,
  createdByLabel,
  cronHumanLabel,
  pickLatestRunContext,
  runDocumentsSummary,
  scheduleTypeLabel,
  taskPhaseLabel,
} from "../lib/automationLibrary";
import { billObjectAxisLabel, billTypeShort } from "../lib/billLibrary";
import { asJsonObject, formatDate, shortId, statusText, statusTone } from "../lib/format";
import type { JobSummary, JsonObject, PageId } from "../types";
import type { WorkbenchState } from "../hooks/useWorkbench";

function stageIcon(state: string) {
  if (state === "done") return <CheckCircle2 size={16} className="automation-stage-done" />;
  if (state === "active") return <Loader2 size={16} className="spin automation-stage-active" />;
  if (state === "error") return <Zap size={16} className="automation-stage-error" />;
  return <CircleDashed size={16} className="automation-stage-pending" />;
}

function jobPayload(job: JobSummary): JsonObject {
  return asJsonObject(job.request_payload) || {};
}

function jobBillType(job: JobSummary): string {
  const payload = jobPayload(job);
  return String(job.bill_type || payload.bill_type || job.type || "");
}

function jobPeriodLabel(job: JobSummary): string {
  const payload = jobPayload(job);
  return String(job.month || payload.period || payload.snapshot_date || payload.month || "-");
}

function jobTargetLabel(job: JobSummary): string {
  const payload = jobPayload(job);
  const targetType = String(job.target_type || payload.target_type || "");
  const targetId = String(job.target_id || payload.target_id || job.channel_id || "");
  if (targetId && targetId !== "all") {
    if (targetType === "channel" || job.channel_id) return `渠道 ${targetId}`;
    if (targetType === "customer") return `客户 ${targetId}`;
    return `目标 ${targetId}`;
  }
  if (targetType === "channel") return "全部渠道";
  if (targetType === "customer") return "全部客户";
  return "全部";
}

function jobErrorText(job: JobSummary): string {
  const result = asJsonObject(job.result);
  return String(job.error_message || result?.error_message || result?.reason || "");
}

function jobStatusBucket(job: JobSummary): "queued" | "running" | "failed" | "completed" | "other" {
  const status = String(job.status || "").toLowerCase();
  if (status.includes("fail") || status.includes("error")) return "failed";
  if (status.includes("running") || status.includes("processing")) return "running";
  if (status.includes("queue") || status.includes("created") || status.includes("pending")) return "queued";
  if (status.includes("complete") || status.includes("done") || status.includes("success")) return "completed";
  return "other";
}

export function AutomationPage({ wb, switchPage }: { wb: WorkbenchState; switchPage: (page: PageId) => void }) {
  const isBusy = wb.pending === "automation";
  const queueJobs = wb.jobQueue?.items || [];
  const billingQueue = wb.jobQueue?.families?.billing_run;
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [taskStatusFilter, setTaskStatusFilter] = useState("all");
  const [taskQuery, setTaskQuery] = useState("");

  const autoContext = useMemo(
    () => pickLatestRunContext(wb.scheduleRuns, wb.billingBatches, wb.billDocuments, wb.jobQueue),
    [wb.scheduleRuns, wb.billingBatches, wb.billDocuments, wb.jobQueue],
  );

  const { run, batch } = useMemo(() => {
    if (!selectedRunId) return autoContext;
    const pickedRun = wb.scheduleRuns.find((item) => item.id === selectedRunId) || autoContext.run;
    const pickedBatch = wb.billingBatches.find((item) => item.schedule_run_id === pickedRun?.id) || null;
    return { run: pickedRun, batch: pickedBatch };
  }, [selectedRunId, autoContext, wb.scheduleRuns, wb.billingBatches]);

  const progress = useMemo(
    () => buildRunProgress(run, batch, wb.billDocuments, wb.jobs, wb.jobQueue),
    [run, batch, wb.billDocuments, wb.jobs, wb.jobQueue],
  );

  const runTasks = useMemo(
    () => buildRunTasks(run, batch, progress.documents, wb.jobs, queueJobs),
    [run, batch, progress.documents, wb.jobs, queueJobs],
  );

  const runJobCount = useMemo(() => countRunTaskJobs(runTasks), [runTasks]);
  const runDocumentCount = useMemo(() => countRunTaskDocuments(runTasks), [runTasks]);

  const currentRunJobIds = useMemo(() => new Set(runTasks.map((task) => task.jobId).filter((id) => id !== "—")), [runTasks]);

  const billingQueueItems = useMemo(
    () => buildGlobalBillingQueue(wb.jobs, queueJobs, currentRunJobIds),
    [wb.jobs, queueJobs, currentRunJobIds],
  );

  const allTrackedJobs = useMemo(() => {
    const byId = new Map<string, JobSummary>();
    [...wb.jobs, ...queueJobs].forEach((job) => {
      if (!job?.id) return;
      byId.set(job.id, { ...(byId.get(job.id) || {}), ...job });
    });
    return [...byId.values()].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
  }, [wb.jobs, queueJobs]);

  const taskStatusFilters = useMemo(() => {
    const counts = allTrackedJobs.reduce<Record<string, number>>(
      (acc, job) => {
        acc.all += 1;
        acc[jobStatusBucket(job)] += 1;
        return acc;
      },
      { all: 0, queued: 0, running: 0, failed: 0, completed: 0, other: 0 },
    );
    return [
      { id: "all", label: "全部", count: counts.all },
      { id: "queued", label: "排队", count: counts.queued },
      { id: "running", label: "运行中", count: counts.running },
      { id: "failed", label: "失败", count: counts.failed },
      { id: "completed", label: "完成", count: counts.completed },
      { id: "other", label: "其他", count: counts.other },
    ].filter((item) => item.id === "all" || item.count > 0);
  }, [allTrackedJobs]);

  const normalizedTaskQuery = taskQuery.trim().toLowerCase();
  const filteredTrackedJobs = useMemo(() => {
    return allTrackedJobs.filter((job) => {
      if (taskStatusFilter !== "all" && jobStatusBucket(job) !== taskStatusFilter) return false;
      if (!normalizedTaskQuery) return true;
      const payload = jobPayload(job);
      const haystack = [
        job.id,
        job.type,
        job.status,
        job.created_by,
        job.month,
        job.vendor,
        job.billing_run_id,
        jobBillType(job),
        jobTargetLabel(job),
        payload.schedule_run_id,
        payload.batch_id,
      ]
        .filter(Boolean)
        .map((value) => String(value).toLowerCase());
      return haystack.some((value) => value.includes(normalizedTaskQuery));
    });
  }, [allTrackedJobs, normalizedTaskQuery, taskStatusFilter]);

  const generatedCount = wb.billDocuments.filter((doc) => String(doc.status).toLowerCase() === "generated").length;
  const failedDocuments = wb.billDocuments.filter((doc) => String(doc.status).toLowerCase().includes("failed")).length;

  const nextAction = useMemo(
    () => buildNextAction(progress, wb.schedules, wb.billDocuments),
    [progress, wb.schedules, wb.billDocuments],
  );

  useEffect(() => {
    if (!progress.isActive && !billingQueueItems.length) return;
    const timer = window.setInterval(() => {
      void wb.refreshAutomation();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [progress.isActive, billingQueueItems.length, wb.refreshAutomation]);

  async function handleNextAction() {
    if (nextAction.action === "retry" && nextAction.actionTarget) {
      await wb.retryScheduleRun(nextAction.actionTarget);
      return;
    }
    if (nextAction.action === "run_schedule" && nextAction.actionTarget) {
      await wb.runSchedule(nextAction.actionTarget);
      return;
    }
    if (nextAction.action === "deliver") {
      switchPage("bills");
      return;
    }
    if (nextAction.action === "open_bills") {
      switchPage("bills");
      return;
    }
    await wb.refreshAutomation();
  }

  return (
    <div className="automation-page">
      <section className="overview-strip overview-strip-compact automation-hero">
        <div className="overview-title">
          <span>账单自动化</span>
          <h3>看清当前进度、下一步该做什么</h3>
        </div>
        <div className="summary-card">
          <div>
            <span>运行中</span>
            <strong>{(billingQueue?.running || 0) + (billingQueue?.queued || 0)}</strong>
          </div>
          <div>
            <span>当前账期</span>
            <strong>{progress.periodLabel}</strong>
          </div>
          <div>
            <span>待交付</span>
            <strong>{generatedCount}</strong>
          </div>
          <div>
            <span>失败</span>
            <strong>{failedDocuments}</strong>
          </div>
        </div>
      </section>

      <section className="automation-current-run">
        <div className="automation-current-main">
          <div className="automation-current-head">
            <div>
              <p className="automation-eyebrow">{progress.isActive ? "进行中" : "最近运行"}</p>
              <h2>{progress.title}</h2>
              <p className="automation-current-sub">
                {progress.subtitle} · 账期 {progress.periodLabel}
                {run ? ` · ${formatDate(run.created_at)}` : ""}
              </p>
            </div>
            <div className="automation-progress-ring" style={{ ["--progress" as string]: `${progress.progressPercent}%` }}>
              <strong>{progress.progressPercent}%</strong>
              <span>整体进度</span>
            </div>
          </div>

          <div className="automation-pipeline">
            {progress.stages.map((stage, index) => (
              <div className={`automation-pipeline-step automation-pipeline-${stage.state}`} key={stage.id}>
                <div className="automation-pipeline-icon">{stageIcon(stage.state)}</div>
                <div className="automation-pipeline-body">
                  <strong>{stage.label}</strong>
                  {stage.detail ? <span>{stage.detail}</span> : null}
                </div>
                {index < progress.stages.length - 1 ? <div className="automation-pipeline-line" /> : null}
              </div>
            ))}
          </div>

          {billingQueueItems.length ? (
            <div className="automation-worker-queue">
              <div className="automation-run-docs-head">
                <strong>Worker 出账队列</strong>
                <span>billing-worker 按顺序拉取以下任务（实时）</span>
              </div>
              <div className="automation-worker-queue-list">
                {billingQueueItems.map((item) => (
                  <div className={`automation-worker-queue-item ${item.isCurrentRun ? "is-current-run" : ""}`} key={item.jobId}>
                    <span className="automation-worker-pos">#{item.position}</span>
                    <span className="automation-worker-type">{billTypeShort(item.billType)}</span>
                    <span>{item.periodLabel}</span>
                    <Badge tone={statusTone(item.status)}>{statusText(item.status)}</Badge>
                    <span className="automation-worker-meta">{createdByLabel(item.createdBy)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {!billingQueueItems.length && runTasks.length ? (
            <p className="automation-queue-idle muted-inline">Worker 当前空闲 · 下方为本次调度已创建的子任务及执行结果</p>
          ) : null}

          {runTasks.length ? (
            <div className="automation-task-schedule">
              <div className="automation-run-docs-head">
                <strong>出账任务计划</strong>
                <span>
                  {selectedRunId && selectedRunId !== autoContext.run?.id ? "查看历史运行 · " : ""}
                  {runJobCount} 个子任务 · {runDocumentCount} 份账单 · 完成 {runTasks.filter((task) => task.phase === "done").length} · 进行中{" "}
                  {runTasks.filter((task) => task.phase === "running").length} · 排队{" "}
                  {runTasks.filter((task) => task.phase === "waiting").length}
                  {selectedRunId ? (
                    <>
                      {" "}
                      ·{" "}
                      <button type="button" className="automation-run-reset" onClick={() => setSelectedRunId(null)}>
                        回到当前
                      </button>
                    </>
                  ) : null}
                </span>
              </div>
              <div className="automation-task-table">
                <div className="automation-task-head">
                  <span>#</span>
                  <span>Job</span>
                  <span>对象</span>
                  <span>账单类型</span>
                  <span>账期/日期</span>
                  <span>文档</span>
                  <span>Job 状态</span>
                  <span>阶段</span>
                  <span>触发</span>
                </div>
                {runTasks.map((task) => (
                  <div
                    className={`automation-task-row automation-task-${task.phase} automation-task-row-${task.rowKind}`}
                    key={`${task.jobId}-${task.documentId || task.index}-${task.targetLabel}`}
                  >
                    <span>{task.index}</span>
                    <span>
                      {task.jobTaskIndex ? `#${task.jobTaskIndex}` : "—"}
                      {task.queuePosition ? <small>队列 #{task.queuePosition}</small> : null}
                    </span>
                    <span>
                      <span className={`automation-axis-badge automation-axis-${task.axis}`}>
                        {task.axis === "customer" ? <UserRound size={11} /> : <Building2 size={11} />}
                        {billObjectAxisLabel(task.axis)}
                      </span>
                      <small>{task.targetLabel}</small>
                    </span>
                    <span>{billTypeShort(task.billType)}</span>
                    <span>{task.periodLabel}</span>
                    <span>
                      <Badge tone={statusTone(task.documentStatus)}>{statusText(task.documentStatus)}</Badge>
                      <small>{task.documentLabel || "账单"}</small>
                      {task.documentId ? <small className="automation-doc-id">{shortId(task.documentId)}</small> : null}
                    </span>
                    <span>
                      <Badge tone={statusTone(task.jobStatus)}>{statusText(task.jobStatus)}</Badge>
                    </span>
                    <span className="automation-task-phase">{taskPhaseLabel(task.phase)}</span>
                    <span className="automation-task-trigger">{createdByLabel(task.createdBy)}</span>
                    {task.error ? <div className="automation-task-error">{task.error}</div> : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="automation-all-tasks">
            <div className="automation-run-docs-head">
              <strong>全部任务追踪</strong>
              <span>
                已加载 {allTrackedJobs.length} 个任务 - 当前显示 {filteredTrackedJobs.length} 个
              </span>
            </div>
            <div className="automation-task-toolbar">
              <div className="automation-task-filters">
                {taskStatusFilters.map((item) => (
                  <button
                    type="button"
                    className={`automation-task-filter ${taskStatusFilter === item.id ? "active" : ""}`}
                    key={item.id}
                    onClick={() => setTaskStatusFilter(item.id)}
                  >
                    <span>{item.label}</span>
                    <strong>{item.count}</strong>
                  </button>
                ))}
              </div>
              <label className="automation-task-search">
                <Search size={14} />
                <input
                  value={taskQuery}
                  onChange={(event) => setTaskQuery(event.target.value)}
                  placeholder="搜索任务、账期、对象、运行 ID"
                />
              </label>
            </div>
            <div className="automation-all-task-table">
              <div className="automation-all-task-head">
                <span>任务</span>
                <span>类型</span>
                <span>对象</span>
                <span>账期/日期</span>
                <span>状态</span>
                <span>时间</span>
                <span>触发</span>
              </div>
              {filteredTrackedJobs.map((job) => {
                const error = jobErrorText(job);
                const bucket = jobStatusBucket(job);
                return (
                  <div className={`automation-all-task-row automation-all-task-${bucket}`} key={job.id}>
                    <span>
                      <strong>{shortId(job.id)}</strong>
                      {job.billing_run_id ? <small>run {shortId(job.billing_run_id)}</small> : null}
                    </span>
                    <span>
                      <strong>{billTypeShort(jobBillType(job))}</strong>
                      <small>{job.type || "job"}</small>
                    </span>
                    <span>{jobTargetLabel(job)}</span>
                    <span>{jobPeriodLabel(job)}</span>
                    <span>
                      <Badge tone={statusTone(job.status)}>{statusText(job.status)}</Badge>
                    </span>
                    <span>
                      <small>创建 {formatDate(job.created_at)}</small>
                      {job.started_at ? <small>开始 {formatDate(job.started_at)}</small> : null}
                      {job.finished_at ? <small>结束 {formatDate(job.finished_at)}</small> : null}
                    </span>
                    <span>{createdByLabel(job.created_by)}</span>
                    {error ? <div className="automation-task-error">{error}</div> : null}
                  </div>
                );
              })}
              {!filteredTrackedJobs.length ? (
                <div className="automation-all-task-empty">
                  {allTrackedJobs.length ? "当前筛选下没有任务" : "暂无任务记录"}
                </div>
              ) : null}
            </div>
          </div>

          {!runTasks.length && !billingQueueItems.length ? (
            <p className="muted-inline">
              {wb.scheduleRuns.length
                ? "当前选中运行暂无子任务记录。可点击右侧运行记录查看其它调度，或手动触发定时任务。"
                : "暂无运行记录。触发定时任务后，这里会展示 Worker 队列与子任务计划。"}
            </p>
          ) : null}
        </div>

        <aside className={`automation-next-card automation-next-${nextAction.tone}`}>
          <p className="automation-eyebrow">下一步</p>
          <h3>{nextAction.title}</h3>
          <p>{nextAction.description}</p>
          {nextAction.action ? (
            <Button className="automation-next-btn" onClick={handleNextAction} disabled={isBusy}>
              {isBusy ? <Loader2 size={15} className="spin" /> : nextAction.action === "refresh" ? <RefreshCw size={15} /> : <ArrowRight size={15} />}
              {nextAction.actionLabel || "继续"}
            </Button>
          ) : null}
          <Button variant="outline" size="sm" onClick={() => switchPage("bills")}>
            前往账单库
          </Button>
        </aside>
      </section>

      <div className="automation-layout">
        <Card className="automation-schedules-card">
          <CardHeader>
            <CardTitle>定时任务</CardTitle>
            <Button variant="outline" size="sm" onClick={wb.refreshAutomation} disabled={isBusy}>
              {isBusy ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
              刷新
            </Button>
          </CardHeader>
          <CardContent className="automation-schedule-list">
            {wb.schedules.map((schedule) => {
              const scheduleType = String(schedule.schedule_type || "");
              const axis =
                scheduleType === "monthly_internal_channel_bills"
                  ? "mixed"
                  : scheduleType.includes("channel") || scheduleType === "daily_channel_cost_snapshot"
                    ? "channel"
                    : "customer";
              return (
                <div className="automation-schedule-card" key={schedule.id}>
                  <div className="automation-schedule-card-head">
                    <span className={`automation-axis-badge automation-axis-${axis === "mixed" ? "customer" : axis}`}>
                      {axis === "customer" ? <UserRound size={12} /> : axis === "channel" ? <Building2 size={12} /> : null}
                      {axis === "customer" ? "客户" : axis === "channel" ? "渠道" : "客户 + 渠道"}
                    </span>
                    <Badge tone={schedule.enabled ? "green" : "default"}>{schedule.enabled ? "启用" : "暂停"}</Badge>
                  </div>
                  <strong>{schedule.name || scheduleTypeLabel(schedule.schedule_type)}</strong>
                  <p>{scheduleTypeLabel(schedule.schedule_type)}</p>
                  <div className="automation-schedule-meta">
                    <CalendarClock size={14} />
                    <span>{cronHumanLabel(schedule.cron_expr, schedule.timezone)}</span>
                  </div>
                  <div className="automation-schedule-meta muted">
                    <Clock3 size={14} />
                    <span>上次运行 {formatDate(schedule.last_run_at)}</span>
                  </div>
                  <Button size="sm" onClick={() => wb.runSchedule(schedule.id)} disabled={isBusy || schedule.enabled === false}>
                    <Play size={14} />
                    立即运行
                  </Button>
                </div>
              );
            })}
            {!wb.schedules.length ? <p className="muted-inline">暂无定时任务</p> : null}
          </CardContent>
        </Card>

        <Card className="automation-runs-card">
          <CardHeader>
            <CardTitle>最近运行记录</CardTitle>
            {batch ? <Badge tone={statusTone(batch.status)}>{statusText(batch.status)}</Badge> : null}
          </CardHeader>
          <CardContent className="automation-run-timeline">
            <p className="automation-timeline-hint muted-inline">点击运行记录可查看该次调度的子任务明细</p>
            {wb.scheduleRuns.slice(0, 10).map((item) => {
              const itemBatch = wb.billingBatches.find((b) => b.schedule_run_id === item.id);
              const itemDocs = wb.billDocuments.filter((doc) => doc.schedule_run_id === item.id);
              const stats = runDocumentsSummary(itemDocs);
              return (
                <button
                  type="button"
                  className={`automation-timeline-item ${run?.id === item.id ? "is-current" : ""} ${selectedRunId === item.id ? "is-selected" : ""}`}
                  key={item.id}
                  onClick={() => setSelectedRunId(item.id)}
                >
                  <div className="automation-timeline-dot" />
                  <div className="automation-timeline-body">
                    <strong>{item.schedule_name || scheduleTypeLabel(item.schedule_type)}</strong>
                    <span>
                      {item.period || itemBatch?.month || "—"} · {formatDate(item.created_at)}
                    </span>
                    <div className="automation-timeline-stats">
                      <Badge tone={statusTone(item.status)}>{statusText(item.status)}</Badge>
                      {stats.total ? <span>账单 {stats.generated}/{stats.total}</span> : null}
                      {(() => {
                        const planned = asJsonObject(item.summary)?.jobs;
                        const count = Array.isArray(planned) ? planned.length : 0;
                        return count ? <span>{count} 个子任务</span> : null;
                      })()}
                    </div>
                    {stats.failed > 0 && item.id ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={(event) => {
                          event.stopPropagation();
                          void wb.retryScheduleRun(item.id);
                        }}
                        disabled={isBusy}
                      >
                        重试失败
                      </Button>
                    ) : null}
                  </div>
                </button>
              );
            })}
            {!wb.scheduleRuns.length ? <p className="muted-inline">还没有运行记录，可先手动触发定时任务。</p> : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
