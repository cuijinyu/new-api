import { Bot, Database, FileText, LayoutList, Loader2, MessageSquare, Play, RefreshCw, ShieldCheck } from "lucide-react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, DataTable, EmptyState, JsonBlock } from "../components/ui";
import { categoryText, displayText, formatBytes, formatDate, jobNextAction, jobTitle, jobTypeText, shortId, statusText, statusTone } from "../lib/format";
import type { PageId } from "../types";
import type { WorkbenchState } from "../hooks/useWorkbench";

export function OverviewPage({ wb, switchPage }: { wb: WorkbenchState; switchPage: (page: PageId) => void }) {
  const { jobs, jobQueue, sessions, uploadedFiles, changeRequests, lastAction, pending } = wb;
  const openSuggestions = changeRequests.filter((item) => String(item.status).toLowerCase() === "open").length;
  const runningCount = jobQueue?.counts?.running ?? jobs.filter((job) => String(job.status).toUpperCase() === "RUNNING").length;
  const queuedCount = jobQueue?.counts?.queued ?? jobs.filter((job) => String(job.status).toUpperCase() === "QUEUED").length;
  const recentJobs = jobs.slice(0, 8);
  const recentSessions = sessions.slice(0, 5);
  const recentFiles = uploadedFiles.slice(0, 5);

  const latestBilling = jobs.find((job) => String(job.type).toLowerCase() === "billing_run");
  const latestBillingDone = latestBilling && String(latestBilling.status).toUpperCase() === "COMPLETED";

  // 主流程引导：根据当前状态推断"下一步该做什么"。
  const nextStep = (() => {
    if (openSuggestions > 0) {
      return {
        title: `有 ${openSuggestions} 条建议待处理`,
        hint: "查看差异原因、影响金额，选择应用 / 忽略 / 保存经验 / 重新生成账单。",
        action: "处理建议",
        page: "governance" as PageId,
        icon: ShieldCheck,
      };
    }
    if (latestBillingDone) {
      return {
        title: "账单已生成，去问 Agent 核对差异",
        hint: "Agent 会带上本次账单、供应商资料和价格方案，帮你找出对账差异并给建议。",
        action: "对账 Agent",
        page: "agent" as PageId,
        icon: Bot,
      };
    }
    if (!jobs.length) {
      return {
        title: "从生成账单开始",
        hint: "配置账期与范围，一键生成账单结果，再交给 Agent 核对。",
        action: "生成账单",
        page: "billing" as PageId,
        icon: Database,
      };
    }
    return {
      title: "继续推进当前账单流程",
      hint: "查看最近任务进度，或进入账单自动化追踪月结批次。",
      action: "账单自动化",
      page: "automation" as PageId,
      icon: LayoutList,
    };
  })();

  const NextIcon = nextStep.icon;

  const flowSteps: Array<{ page: PageId; label: string; desc: string; icon: typeof Database }> = [
    { page: "billing", label: "生成账单", desc: "配置账期与范围，确定性出账", icon: Database },
    { page: "automation", label: "账单自动化", desc: "定时月结、批次追踪、交付", icon: LayoutList },
    { page: "agent", label: "对账 Agent", desc: "上传资料，问 Agent 找差异", icon: Bot },
    { page: "governance", label: "建议与经验", desc: "处理建议、沉淀经验", icon: ShieldCheck },
  ];

  return (
    <>
      <Card className="next-step-card">
        <CardContent>
          <div className="next-step">
            <div className="next-step-icon">
              <NextIcon size={26} />
            </div>
            <div className="next-step-body">
              <span>下一步</span>
              <h3>{nextStep.title}</h3>
              <p>{nextStep.hint}</p>
            </div>
            <Button onClick={() => switchPage(nextStep.page)}>{nextStep.action}</Button>
          </div>
        </CardContent>
      </Card>

      <section className="kpi-grid overview-kpi">
        <div className="metric">
          <span>数据库</span>
          <Badge tone={wb.health?.db ? "green" : "red"}>{wb.health?.db ? "正常" : "未知"}</Badge>
        </div>
        <div className="metric">
          <span>运行中</span>
          <strong>{runningCount}</strong>
        </div>
        <div className="metric">
          <span>排队中</span>
          <strong>{queuedCount}</strong>
        </div>
        <div className="metric">
          <span>待处理建议</span>
          <strong>{openSuggestions}</strong>
        </div>
      </section>

      <div className="flow-cards">
        {flowSteps.map((step, index) => {
          const Icon = step.icon;
          return (
            <button className="flow-card" key={step.page} onClick={() => switchPage(step.page)}>
              <span className="flow-card-index">{index + 1}</span>
              <Icon size={20} />
              <strong>{step.label}</strong>
              <small>{step.desc}</small>
            </button>
          );
        })}
      </div>

      <div className="detail-grid">
        <Card>
          <CardHeader>
            <CardTitle>最近任务</CardTitle>
            <Badge tone="blue">{recentJobs.length} 条</Badge>
          </CardHeader>
          <CardContent>
            <DataTable
              columns={["任务", "状态", "创建时间", "下一步"]}
              rows={recentJobs.map((job) => [
                <div className="file-cell" key={`${job.id}-title`}>
                  <strong>{jobTitle(job)}</strong>
                  <span>
                    {jobTypeText(job.type)} · {shortId(job.id)}
                  </span>
                </div>,
                <Badge tone={statusTone(job.status)} key={`${job.id}-status`}>
                  {statusText(job.status)}
                </Badge>,
                formatDate(job.created_at),
                <Button
                  key={`${job.id}-action`}
                  variant={String(job.status).toUpperCase() === "COMPLETED" ? "outline" : "default"}
                  size="sm"
                  onClick={() => wb.runJobFromCenter(job.id)}
                  disabled={pending === "run"}
                >
                  {jobNextAction(job.status)}
                </Button>,
              ])}
              empty="暂无任务，先去生成账单"
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>最近会话</CardTitle>
            <Button variant="outline" size="sm" onClick={() => switchPage("agent")}>
              <Bot size={14} />
              打开
            </Button>
          </CardHeader>
          <CardContent>
            <div className="compact-list">
              {recentSessions.map((session) => (
                <button className="compact-list-row" key={session.id} onClick={() => switchPage("agent")}>
                  <MessageSquare size={16} />
                  <span>
                    <strong>{session.title || shortId(session.id)}</strong>
                    <small>{displayText(session.prompt || "").slice(0, 64) || "-"}</small>
                  </span>
                  <Badge tone={statusTone(session.status)}>{statusText(session.status)}</Badge>
                </button>
              ))}
              {!recentSessions.length ? <div className="empty-cell">暂无会话</div> : null}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="detail-grid overview-secondary">
        <Card>
          <CardHeader>
            <CardTitle>最近资料</CardTitle>
            <Button variant="outline" size="sm" onClick={() => switchPage("files")}>
              资料库
            </Button>
          </CardHeader>
          <CardContent>
            <div className="compact-list">
              {recentFiles.map((file) => (
                <button className="compact-list-row" key={file.id} onClick={() => switchPage("files")}>
                  <FileText size={16} />
                  <span>
                    <strong>{file.filename}</strong>
                    <small>
                      {categoryText(file.category)} · {formatBytes(file.byte_size)}
                    </small>
                  </span>
                  <small>{formatDate(file.created_at)}</small>
                </button>
              ))}
              {!recentFiles.length ? (
                <EmptyState title="暂无资料" hint="可在生成账单或 Agent 页就近上传供应商账单与凭证。" />
              ) : null}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>技术详情</CardTitle>
            <Button variant="outline" size="sm" onClick={wb.refreshWorkCenter} disabled={pending === "jobs" || pending === "queue"}>
              {pending === "jobs" || pending === "queue" ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
              刷新
            </Button>
          </CardHeader>
          <CardContent>
            <details className="advanced-panel">
              <summary>任务队列 / 运行下一条 / 技术响应</summary>
              <div className="advanced-panel-inner">
                <div className="queue-summary">
                  <div>
                    <span>运行中</span>
                    <strong>{runningCount}</strong>
                  </div>
                  <div>
                    <span>排队中</span>
                    <strong>{queuedCount}</strong>
                  </div>
                  <div>
                    <span>最近任务</span>
                    <strong>{jobs.length}</strong>
                  </div>
                </div>
                <div className="button-row section-block">
                  <Button onClick={wb.runNextQueuedJob} disabled={!queuedCount || pending === "queue"}>
                    {pending === "queue" ? <Loader2 size={15} className="spin" /> : <Play size={15} />}
                    运行下一条
                  </Button>
                  <Button variant="outline" onClick={() => switchPage("billing")}>
                    <Database size={15} />
                    新建账单
                  </Button>
                </div>
                <div className="section-block">
                  <span className="field-label">最近技术响应</span>
                  <JsonBlock value={lastAction?.detail} empty="暂无操作记录" />
                </div>
              </div>
            </details>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
