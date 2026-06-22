import type {
  BillingArtifactGroup,
  BillingForm,
  BillingFormErrors,
  BillingStage,
  JsonObject,
  UploadedFile,
} from "../types";
import { asJsonObject, compactPayload, metadataValue, parseJsonInput, stringValue } from "./format";

export function buildBillingMetadata(form: BillingForm, extra: JsonObject = {}) {
  return compactPayload({
    ...extra,
    athena_command: "bill",
    original_interaction: "scripts/athena/bill_cli.py bill",
    bill_type: form.bill_type,
    user_id: form.scope === "user" && form.user_id ? Number(form.user_id) : undefined,
    currency: form.currency,
    exchange_rate: form.exchange_rate ? Number(form.exchange_rate) : undefined,
    flat_tier: form.flat_tier,
    flat_tier_since: form.flat_tier_since,
    end_day: form.end_day,
    detail: true,
    customer_view: form.customer_view || form.bill_type === "customer_invoice",
    split_customers: form.bill_type === "customer_invoice" && form.scope !== "user" ? true : undefined,
    split_internal_customers:
      form.bill_type === "internal_customer_bill" && form.scope !== "user" ? true : undefined,
    split_channels:
      (form.bill_type === "channel_cost_bill" || form.bill_type === "daily_channel_cost_snapshot") && form.scope !== "channel" ? true : undefined,
    upload_to_athena_s3: form.upload_to_athena_s3,
    no_cache: form.no_cache,
    output_dir: form.output_dir,
  });
}

function quoteCli(value: string) {
  return /\s/.test(value) ? `"${value.replace(/"/g, '\\"')}"` : value;
}

export function buildAthenaCliPreview(form: BillingForm) {
  const args = ["python", "bill_cli.py", "bill", "--month", form.month || "<YYYY-MM>"];
  if (form.no_cache) args.push("--no-cache");
  if (form.scope === "channel" && form.channel_id) args.push("--channel-id", form.channel_id);
  if (form.scope === "user" && form.user_id) args.push("--user-id", form.user_id);
  if (form.currency) args.push("--currency", form.currency);
  if (form.exchange_rate) args.push("--exchange-rate", form.exchange_rate);
  if (form.flat_tier || form.flat_tier_since) args.push("--flat-tier");
  if (form.flat_tier_since) args.push("--flat-tier-since", form.flat_tier_since);
  if (form.end_day) args.push("--end-day", form.end_day);
  args.push("--detail");
  if (form.customer_view || form.bill_type === "customer_invoice") args.push("--customer-view");
  if (form.bill_type === "customer_invoice" && form.scope !== "user") args.push("--split-customers");
  if (form.bill_type === "internal_customer_bill" && form.scope !== "user") {
    args.push("--bill-type", "internal_customer_bill", "--split-internal-customers");
  }
  if ((form.bill_type === "channel_cost_bill" || form.bill_type === "daily_channel_cost_snapshot") && form.scope !== "channel") {
    args.push("--bill-type", form.bill_type, "--split-channels");
  }
  if (form.upload_to_athena_s3) args.push("--upload");
  args.push("-o", form.output_dir || "/tmp/agent-workbench-athena-output/<run_id>");
  return args.map(quoteCli).join(" ");
}

export function validateBillingForm(form: BillingForm): BillingFormErrors {
  const errors: BillingFormErrors = {};
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(form.month.trim())) {
    errors.month = "请输入 YYYY-MM 格式的账期";
  }
  if (form.scope === "channel") {
    if (!form.channel_id.trim()) {
      errors.channel_id = "渠道账单需要填写渠道 ID";
    } else if (!/^\d+$/.test(form.channel_id.trim())) {
      errors.channel_id = "渠道 ID 只能是数字";
    }
  }
  if (form.scope === "user") {
    if (!form.user_id.trim()) {
      errors.user_id = "用户账单需要填写用户 ID";
    } else if (!/^\d+$/.test(form.user_id.trim())) {
      errors.user_id = "用户 ID 只能是数字";
    }
  }
  if (form.exchange_rate.trim() && !Number.isFinite(Number(form.exchange_rate))) {
    errors.exchange_rate = "汇率必须是数字";
  }
  if (form.currency === "CNY" && !form.exchange_rate.trim()) {
    errors.exchange_rate = "CNY 账单需要填写汇率";
  }
  const extraMetadata = parseJsonInput(form.extra_metadata);
  if (!extraMetadata.ok) {
    errors.extra_metadata = extraMetadata.error;
  }
  return errors;
}

export function hasBillingErrors(errors: BillingFormErrors) {
  return Object.values(errors).some(Boolean);
}

export function billingScopeLabel(form: BillingForm) {
  if (form.scope === "all") return "全量用户";
  if (form.scope === "channel") return `渠道 ${form.channel_id || "-"}`;
  return `用户 ${form.user_id || "-"}`;
}

export function billingSummary(job?: JsonObject, billingRun?: JsonObject | null) {
  const result = asJsonObject(job?.result);
  const fromResult = asJsonObject(result?.summary);
  const fromRun = asJsonObject(billingRun?.summary);
  return { ...fromRun, ...fromResult };
}

export function billingIsFixture(summary: JsonObject) {
  if (summary.is_fixture === true) return true;
  return String(summary.athena_e2e_mode || "").toLowerCase() === "fixture";
}

export function billingExecutionLabel(summary: JsonObject): { tone: "green" | "amber" | "red"; text: string } | null {
  const mode = String(summary.execution_mode || "").toLowerCase();
  if (!mode) return null;
  if (mode === "dry-run") return { tone: "amber", text: "演练模式（未生成真实账单）" };
  if (billingIsFixture(summary)) return { tone: "amber", text: "示例数据（fixture，非真实 Athena）" };
  return { tone: "green", text: "真实出账" };
}

export function billingHasRealTotals(summary: JsonObject) {
  const mode = String(summary.execution_mode || "").toLowerCase();
  if (mode === "dry-run") return false;
  if (billingIsFixture(summary)) return false;
  const total = Number(summary.total_usd);
  return Number.isFinite(total) && total > 0;
}

export function billingStage(job: JsonObject | undefined, runJobId: string, artifactRows: string[][]): BillingStage {
  const status = String(job?.status || "").toLowerCase();
  const summary = billingSummary(job);
  if (["failed", "timed_out", "cancelled"].includes(status)) return "failed";
  if (status === "running") return "running";
  if (status === "queued") return "queued";
  if (status === "completed") {
    const mode = String(summary.execution_mode || "").toLowerCase();
    // 演练/示例数据不算真正出账完成，避免误导。
    if (mode === "dry-run" || billingIsFixture(summary)) return "created";
    if (billingHasRealTotals(summary) || Object.keys(asJsonObject(summary.generated_files) || {}).length > 0) {
      return "completed";
    }
    return "completed";
  }
  if (status === "created" || job || runJobId) return "created";
  return "draft";
}

export function billingStageText(stage: BillingStage) {
  const map: Record<BillingStage, string> = {
    draft: "配置中",
    created: "已创建",
    queued: "排队中",
    running: "运行中",
    completed: "已完成",
    failed: "失败",
  };
  return map[stage];
}

export function billingWorkflow(stage: BillingStage) {
  if (stage === "failed") {
    return [
      { label: "配置账单", state: "done" },
      { label: "生成账单", state: "error" },
      { label: "查看结果", state: "" },
      { label: "问 Agent", state: "" },
    ];
  }
  if (stage === "completed") {
    return [
      { label: "配置账单", state: "done" },
      { label: "生成账单", state: "done" },
      { label: "查看结果", state: "active" },
      { label: "问 Agent", state: "ready" },
    ];
  }
  if (stage === "running" || stage === "queued" || stage === "created") {
    return [
      { label: "配置账单", state: "done" },
      { label: "生成账单", state: "active" },
      { label: "查看结果", state: "" },
      { label: "问 Agent", state: "" },
    ];
  }
  return [
    { label: "配置账单", state: "active" },
    { label: "生成账单", state: "" },
    { label: "查看结果", state: "" },
    { label: "问 Agent", state: "" },
  ];
}

export function artifactFilename(uri: string) {
  const clean = uri.split("?")[0].replace(/\/+$/, "");
  return clean.slice(clean.lastIndexOf("/") + 1) || uri;
}

function artifactLabel(role: string, uri: string) {
  const normalized = role.toLowerCase();
  const map: Record<string, string> = {
    summary: "汇总文件",
    detail: "明细 CSV",
    report: "生成报告",
    pricing: "价格表",
    discounts: "折扣规则",
    command: "执行命令",
    worker_manifest: "Worker 清单",
    job: "任务记录",
    result: "结果 JSON",
  };
  return map[normalized] || artifactFilename(uri);
}

export function groupBillingArtifacts(rows: string[][]): BillingArtifactGroup[] {
  const groups: BillingArtifactGroup[] = [
    { id: "bill", title: "账单文件", description: "运营优先查看的汇总、明细和报告。", items: [] },
    { id: "pricing", title: "价格方案", description: "本次账单使用的价格和折扣快照。", items: [] },
    { id: "technical", title: "技术记录", description: "排查和审计时使用的任务记录。", items: [] },
  ];
  const groupById = Object.fromEntries(groups.map((group) => [group.id, group]));
  const seenUris = new Set<string>();
  for (const [role, uri] of rows) {
    if (seenUris.has(uri)) continue;
    seenUris.add(uri);
    const normalized = String(role || "").toLowerCase();
    const item = { role: normalized || "artifact", label: artifactLabel(normalized, uri), uri };
    if (["summary", "detail", "report"].includes(normalized)) {
      groupById.bill.items.push(item);
    } else if (["pricing", "discounts"].includes(normalized)) {
      groupById.pricing.items.push(item);
    } else {
      groupById.technical.items.push(item);
    }
  }
  return groups.filter((group) => group.items.length > 0);
}

export function currentBillingFileIds(files: UploadedFile[], job?: JsonObject, billingRun?: JsonObject | null) {
  const jobId = stringValue(job?.id);
  const runId = stringValue(billingRun?.id || job?.billing_run_id);
  return files
    .filter((file) => {
      if (file.category !== "billing-result") return false;
      return (
        (jobId && file.job_id === jobId) ||
        (jobId && metadataValue(file, "job_id") === jobId) ||
        (runId && metadataValue(file, "billing_run_id") === runId)
      );
    })
    .map((file) => file.id);
}
