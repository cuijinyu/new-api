import { Bot, Download, FileText, Info, Loader2, Play, Receipt, Settings2 } from "lucide-react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, Field } from "../components/ui";
import { formatDate, shortId, statusText, stringValue } from "../lib/format";
import {
  artifactFilename,
  billingExecutionLabel,
  billingHasRealTotals,
  billingIsFixture,
  billingScopeLabel,
  billingStage,
  billingStageText,
  billingSummary,
  billingWorkflow,
  currentBillingFileIds,
  groupBillingArtifacts,
  hasBillingErrors,
  validateBillingForm,
} from "../lib/billing";
import type { BillingForm, PageId } from "../types";
import type { WorkbenchState } from "../hooks/useWorkbench";

const billTypeOptions: Array<{ value: BillingForm["bill_type"]; label: string; hint: string }> = [
  { value: "channel_cost_bill", label: "渠道成本", hint: "供应商/渠道对账" },
  { value: "internal_customer_bill", label: "内部版", hint: "内部复盘" },
  { value: "customer_invoice", label: "客户版", hint: "客户交付" },
  { value: "daily_channel_cost_snapshot", label: "日成本", hint: "日级快照" },
];

function formatUsd(value: unknown) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "-";
  return `$${num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatInt(value: unknown) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "-";
  return num.toLocaleString();
}

export function BillingPage({ wb, switchPage }: { wb: WorkbenchState; switchPage: (page: PageId) => void }) {
  const job = wb.jobDetail?.job;
  const billingRun = wb.jobDetail?.billing_run;
  const stage = billingStage(job, wb.runJobId, wb.artifactRows);
  // fixture/dry-run 即便 job 已 COMPLETED 也不展示“已完成”，以 stage 文案为准，避免误导。
  const useStageStatus = stage === "created" && String(job?.status || "").toLowerCase() === "completed";
  const status = useStageStatus
    ? billingStageText(stage)
    : job?.status
    ? statusText(job.status)
    : billingStageText(stage);
  const errors = validateBillingForm(wb.billingForm);
  const formHasErrors = hasBillingErrors(errors);
  const summary = billingSummary(job, billingRun);
  const kpi = wb.kpiPreview || {};
  const scopeLabel = billingScopeLabel(wb.billingForm);
  const artifactGroups = groupBillingArtifacts(wb.artifactRows);
  const currentFileIds = currentBillingFileIds(wb.uploadedFiles, job, billingRun);
  const billFiles = wb.uploadedFiles.filter((f) => currentFileIds.includes(f.id));
  const isBusy = wb.pending === "billing" || wb.pending === "run";
  const isRunning = stage === "running" || stage === "queued" || isBusy;
  const isCompleted = stage === "completed";
  const askAgentDisabled = !currentFileIds.length || wb.pending === "agent";
  const hasResultSignal = isCompleted || billingHasRealTotals(summary) || billingIsFixture(summary);
  const generatedFileCount = artifactGroups.reduce((sum, group) => sum + group.items.length, 0) + billFiles.length;
  const runModeLabel = billingExecutionLabel(summary);
  const stageTone = stage === "failed" ? "red" : stage === "completed" ? "green" : isRunning ? "amber" : "blue";

  function updateField<K extends keyof BillingForm>(field: K, value: BillingForm[K]) {
    wb.setBillingForm((prev) => ({ ...prev, [field]: value }));
  }

  async function askAgentWithResults() {
    if (!currentFileIds.length) return;
    await wb.referenceFilesToAgent(currentFileIds);
    switchPage("agent");
  }

  return (
    <div className="billing-page-flow">
      <div className="workflow-bar billing-workflow">
        {billingWorkflow(stage).map((step, index) => (
          <div className={`workflow-step ${step.state}`} key={step.label}>
            <span>{index + 1}</span>
            <strong>{step.label}</strong>
          </div>
        ))}
      </div>

      <section className="billing-command-panel">
        <div className="billing-command-copy">
          <Badge tone={stageTone}>{status}</Badge>
          <h3>{isCompleted ? "账单已生成，可以进入对账或交付" : isRunning ? "账单正在生成" : "配置账单后即可生成"}</h3>
          <p>
            {isCompleted
              ? `已归档 ${generatedFileCount} 个结果文件，可下载、进入账单库，或直接引用给 Agent。`
              : `当前范围：${scopeLabel}；预览会随账期、范围和配置版本自动刷新。`}
          </p>
        </div>
        <div className="billing-command-actions">
          <Button onClick={() => wb.createBillingRun(true)} disabled={isBusy || formHasErrors}>
            {isBusy ? <Loader2 size={15} className="spin" /> : <Play size={15} />}
            {isCompleted ? "重新生成" : "生成账单"}
          </Button>
          <Button variant="outline" onClick={() => switchPage("bills")}>
            <Receipt size={15} />
            打开账单库
          </Button>
          <Button variant="secondary" onClick={askAgentWithResults} disabled={askAgentDisabled}>
            <Bot size={15} />
            引用结果问 Agent
          </Button>
        </div>
      </section>

      <div className="billing-setup-grid">
      <Card>
        <CardHeader>
          <CardTitle>月度概览</CardTitle>
          <Badge tone={wb.kpiLoading ? "amber" : "blue"}>{wb.kpiLoading ? "查询中" : wb.billingForm.month}</Badge>
        </CardHeader>
        <CardContent>
          <div className="kpi-cards">
            <div className="kpi-card"><span>总费用 (USD)</span><strong>{wb.kpiLoading ? <Loader2 size={16} className="spin" /> : formatUsd(kpi.total_usd)}</strong></div>
            <div className="kpi-card"><span>总调用量</span><strong>{wb.kpiLoading ? <Loader2 size={16} className="spin" /> : formatInt(kpi.total_calls)}</strong></div>
            <div className="kpi-card"><span>活跃用户</span><strong>{wb.kpiLoading ? <Loader2 size={16} className="spin" /> : formatInt(kpi.unique_users)}</strong></div>
            <div className="kpi-card"><span>活跃模型</span><strong>{wb.kpiLoading ? <Loader2 size={16} className="spin" /> : formatInt(kpi.unique_models)}</strong></div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>出账参数</CardTitle>
          <Badge tone={stageTone}>{status}</Badge>
        </CardHeader>
        <CardContent>
          <div className="form-grid">
            <div className="span-2">
              <span className="field-label">账单类型</span>
              <div className="billing-type-grid">
                {billTypeOptions.map((option) => (
                  <button
                    type="button"
                    className={wb.billingForm.bill_type === option.value ? "active" : ""}
                    key={option.value}
                    onClick={() => updateField("bill_type", option.value)}
                  >
                    <strong>{option.label}</strong>
                    <small>{option.hint}</small>
                  </button>
                ))}
              </div>
            </div>
            <Field label="账期" hint="YYYY-MM">
              <input aria-invalid={Boolean(errors.month)} value={wb.billingForm.month} onChange={(e) => updateField("month", e.target.value)} />
            </Field>
            <Field label="供应商">
              <input value={wb.billingForm.vendor} onChange={(e) => updateField("vendor", e.target.value)} />
            </Field>
            <div className="span-2">
              <p className="field-hint-inline">
                出账使用当前刊例价和全局折扣。需要调整？
                <button type="button" className="link-btn" onClick={() => switchPage("pricing")}>打开价格管理</button>
                <button type="button" className="link-btn" onClick={() => switchPage("discounts")}>打开折扣管理</button>
              </p>
            </div>
            <div className="span-2">
              <span className="field-label">账单范围</span>
              <div className="segmented-control">
                {[["all", "全量"], ["channel", "渠道"], ["user", "用户"]].map(([value, label]) => (
                  <button type="button" className={wb.billingForm.scope === value ? "active" : ""} key={value} onClick={() => updateField("scope", value as BillingForm["scope"])}>{label}</button>
                ))}
              </div>
            </div>
            {wb.billingForm.scope === "channel" ? (
              <Field label="渠道 ID"><input value={wb.billingForm.channel_id} onChange={(e) => updateField("channel_id", e.target.value)} /></Field>
            ) : null}
            {wb.billingForm.scope === "user" ? (
              <Field label="用户 ID"><input value={wb.billingForm.user_id} onChange={(e) => updateField("user_id", e.target.value)} /></Field>
            ) : null}
          </div>

          <details className="advanced-panel section-block">
            <summary><Settings2 size={15} /> 高级设置</summary>
            <div className="toggle-grid section-block">
              <label className="toggle-card"><input type="checkbox" checked disabled readOnly /><span><strong>逐条明细</strong><small>所有账单固定导出明细</small></span></label>
              <label className="toggle-card"><input type="checkbox" checked={wb.billingForm.customer_view} onChange={(e) => updateField("customer_view", e.target.checked)} /><span><strong>客户视图</strong><small>隐藏成本/利润</small></span></label>
              <label className="toggle-card"><input type="checkbox" checked={wb.billingForm.flat_tier} onChange={(e) => updateField("flat_tier", e.target.checked)} /><span><strong>Flat tier</strong><small>降档口径</small></span></label>
              <label className="toggle-card"><input type="checkbox" checked={wb.billingForm.no_cache} onChange={(e) => updateField("no_cache", e.target.checked)} /><span><strong>绕过缓存</strong><small>强制重查 Athena</small></span></label>
            </div>
          </details>

          {formHasErrors ? <div className="billing-alert"><Info size={16} /><span>请先修正表单提示。</span></div> : null}
          {job?.error_message ? <div className="billing-alert billing-alert-error"><strong>生成失败</strong><span>{String(job.error_message)}</span></div> : null}

          <div className="billing-primary-actions">
            <Button onClick={() => wb.createBillingRun(true)} disabled={isBusy || formHasErrors}>
              {isBusy ? <Loader2 size={15} className="spin" /> : <Play size={15} />}
              {isCompleted ? "重新生成账单" : "生成账单"}
            </Button>
            <Button variant="secondary" onClick={askAgentWithResults} disabled={askAgentDisabled}><Bot size={15} />引用结果问 Agent</Button>
          </div>

          {isRunning ? (
            <div className="billing-run-progress">
              <Loader2 size={18} className="spin" />
              <span>正在生成账单… 已用时 {wb.pollElapsed}s</span>
            </div>
          ) : null}
        </CardContent>
      </Card>
      </div>

      {hasResultSignal ? (
        <Card>
          <CardHeader>
            <CardTitle>账单结果</CardTitle>
            {runModeLabel ? <Badge tone={runModeLabel.tone}>{runModeLabel.text}</Badge> : <Badge tone="green">已完成</Badge>}
          </CardHeader>
          <CardContent>
            {billingIsFixture(summary) ? (
              <div className="billing-banner billing-banner-warn">
                当前为示例数据（fixture），非真实 Athena 出账。真实出账需设置 <code>WORKBENCH_ATHENA_EXECUTION=real</code> 且不启用 <code>ATHENA_E2E_MODE=fixture</code>，并配置 AWS 凭证。
              </div>
            ) : null}
            <div className="billing-amount-summary">
              <div><span>总费用</span><strong>{formatUsd(summary.total_usd)}</strong></div>
              <div><span>调用量</span><strong>{formatInt(summary.total_calls)}</strong></div>
              <div><span>范围</span><strong>{scopeLabel}</strong></div>
              <div><span>执行模式</span><strong>{stringValue(summary.execution_mode, "-")}</strong></div>
              <div><span>任务</span><strong>{shortId(job?.id || wb.runJobId)}</strong></div>
              <div><span>完成时间</span><strong>{formatDate(job?.finished_at || billingRun?.finished_at)}</strong></div>
            </div>
            <div className="download-row">
              <Button variant="secondary" onClick={() => switchPage("bills")}>
                <Receipt size={15} />到账单库查看
              </Button>
              <Button variant="secondary" onClick={askAgentWithResults} disabled={askAgentDisabled}>
                <Bot size={15} />引用结果问 Agent
              </Button>
              {billFiles.map((file) => (
                <Button key={file.id} variant="outline" onClick={() => wb.downloadArtifact({ fileId: file.id, filename: file.filename })}>
                  <Download size={15} />{file.filename}
                </Button>
              ))}
              {artifactGroups.flatMap((g) => g.items).filter((item) => item.uri.endsWith(".xlsx") || item.uri.includes(".zip")).map((item) => (
                <Button key={item.uri} variant="outline" onClick={() => wb.downloadArtifact({ uri: item.uri, filename: artifactFilename(item.uri) })}>
                  <Download size={15} />{item.label}
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader><CardTitle>结果文件</CardTitle><Badge tone={artifactGroups.length ? "green" : "blue"}>{wb.artifactRows.length}</Badge></CardHeader>
        <CardContent>
          {artifactGroups.length ? (
            <div className="artifact-groups">
              {artifactGroups.map((group) => (
                <section className="artifact-group" key={group.id}>
                  <div className="artifact-group-head"><strong>{group.title}</strong><Badge tone="blue">{group.items.length}</Badge></div>
                  <div className="artifact-list">
                    {group.items.map((item) => (
                      <div className="artifact-row download-row-item" key={`${item.role}-${item.uri}`}>
                        <FileText size={16} />
                        <span><strong>{item.label}</strong><code>{item.uri}</code></span>
                        <Button variant="ghost" size="sm" onClick={() => wb.downloadArtifact({ uri: item.uri, filename: artifactFilename(item.uri) })}><Download size={14} />下载</Button>
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          ) : (
            <EmptyState icon={<FileText size={26} />} title="还没有结果文件" hint="生成完成后会在这里显示汇总、明细和价格方案快照。" />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
