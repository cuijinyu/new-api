import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE_URL, apiRequest, endpoints, type ApiResult } from "../lib/api";
import { compactPayload, fileToBase64, parseJsonInput } from "../lib/format";
import { buildBillingMetadata } from "../lib/billing";
import { useToast } from "./useToast";
import type {
  ActionName,
  AgentEvent,
  AgentForm,
  AgentResult,
  AgentSession,
  AgentUploadForm,
  BillDocument,
  BillingBatch,
  BillingForm,
  ChangeRequest,
  ConfigVersion,
  CostDiscountRow,
  DiscountsResponse,
  FileForm,
  Health,
  JobArtifacts,
  JobDetail,
  JobQueue,
  JobSummary,
  JsonObject,
  KpiPreview,
  LastAction,
  PricingResponse,
  PricingRow,
  RawLogObject,
  RawLogPreview,
  RawLogSearchResult,
  RawLogsConfig,
  RawLogsForm,
  RevenueDiscountRow,
  Schedule,
  ScheduleRun,
  SessionFilter,
  Skill,
  SkillContent,
  SkillForm,
  SkillPreviewItem,
  UploadedFile,
  FilePreview,
} from "../types";

// 表单里的逗号分隔字符串 -> 去空白去重的数组。
function splitList(value: string): string[] {
  return Array.from(
    new Set(
      (value || "")
        .split(/[,，\n]/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

const nowMonth = new Date().toISOString().slice(0, 7);
const rawLogDefaultDate = (() => {
  const date = new Date();
  return {
    year: String(date.getFullYear()),
    month: String(date.getMonth() + 1).padStart(2, "0"),
    day: String(date.getDate()).padStart(2, "0"),
  };
})();

const streamEventTypes = [
  "session.created",
  "sandbox.ready",
  "skills.injected",
  "message",
  "file.reference",
  "context.injected",
  "assistant.delta",
  "operator.message.received",
  "human.input.waiting",
  "tool.call",
  "tool.result",
  "run.started",
  "run.completed",
  "run.error",
  "run.warning",
];

const resultPendingStatuses = new Set(["CREATED", "RUNNING", "SANDBOX_READY", "HUMAN_REPLIED", "PAUSED"]);
const activeAgentStatuses = new Set(["CREATED", "RUNNING", "SANDBOX_READY", "HUMAN_REPLIED", "PAUSED"]);

function canLoadAgentResult(status?: string) {
  const normalized = String(status || "").toUpperCase();
  return !normalized || !resultPendingStatuses.has(normalized);
}

function statusFromAgentEvent(event: AgentEvent) {
  if (event.event_type === "session.created") return "CREATED";
  if (event.event_type === "sandbox.ready") return "SANDBOX_READY";
  if (event.event_type === "run.started") return "RUNNING";
  if (event.event_type === "run.completed") return "COMPLETED";
  if (event.event_type === "run.error") return "FAILED";
  if (event.event_type === "message" && event.payload?.["continuation"]) return "HUMAN_REPLIED";
  return null;
}

function resultFromAgentEvent(event: AgentEvent): AgentResult | null {
  const result = event.payload?.["result"];
  return result && typeof result === "object" && !Array.isArray(result) ? (result as AgentResult) : null;
}

function mergeUploadedFiles(current: UploadedFile[], incoming: UploadedFile[]) {
  const seen = new Set(current.map((file) => file.id).filter(Boolean));
  const next = [...current];
  incoming.forEach((file) => {
    if (file.id && seen.has(file.id)) return;
    if (file.id) seen.add(file.id);
    next.push(file);
  });
  return next;
}

function sessionTimestamp(session?: AgentSession | null) {
  const time = Date.parse(session?.updated_at || "");
  return Number.isFinite(time) ? time : 0;
}

function mergeAgentSessionSnapshot(local: AgentSession | undefined, remote: AgentSession) {
  const metadata = remote.metadata ? { ...(local?.metadata || {}), ...remote.metadata } : local?.metadata;
  const merged: AgentSession = { ...(local || {}), ...remote, metadata };
  if (local && sessionTimestamp(local) > sessionTimestamp(remote)) {
    return {
      ...merged,
      status: local.status || merged.status,
      updated_at: local.updated_at || merged.updated_at,
      metadata: { ...(remote.metadata || {}), ...(local.metadata || {}) },
    };
  }
  return merged;
}

const toastTitle: Partial<Record<ActionName, string>> = {
  health: "刷新服务状态",
  billing: "创建账单任务",
  run: "生成账单",
  kpiPreview: "KPI 预览",
  pricing: "保存刊例价",
  discounts: "保存折扣",
  upload: "上传资料",
  agent: "Agent 操作",
  agentMessage: "发送消息",
  change: "处理建议",
  changeRerun: "重新生成账单",
  automation: "账单自动化",
};

export function useWorkbench() {
  const toast = useToast();

  const [health, setHealth] = useState<Health | null>(null);
  const [pending, setPending] = useState<ActionName | null>(null);
  const [lastAction, setLastAction] = useState<LastAction>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [jobQueue, setJobQueue] = useState<JobQueue | null>(null);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [scheduleRuns, setScheduleRuns] = useState<ScheduleRun[]>([]);
  const [billingBatches, setBillingBatches] = useState<BillingBatch[]>([]);
  const [billDocuments, setBillDocuments] = useState<BillDocument[]>([]);

  const [billingForm, setBillingForm] = useState<BillingForm>({
    month: nowMonth,
    bill_type: "channel_cost_bill",
    scope: "channel",
    channel_id: "65",
    user_id: "",
    vendor: "1001AI-Claude",
    config_version: "local-v0",
    created_by: "ops",
    currency: "USD",
    exchange_rate: "7.3",
    flat_tier: true,
    flat_tier_since: "",
    end_day: "",
    detail: true,
    customer_view: false,
    upload_to_athena_s3: false,
    no_cache: false,
    output_dir: "",
    extra_metadata: "",
  });
  const [configVersions, setConfigVersions] = useState<ConfigVersion[]>([]);
  const [kpiPreview, setKpiPreview] = useState<KpiPreview | null>(null);
  const [kpiLoading, setKpiLoading] = useState(false);
  const [pollElapsed, setPollElapsed] = useState(0);
  const [pricingRows, setPricingRows] = useState<PricingRow[]>([]);
  const [pricingMetadata, setPricingMetadata] = useState<PricingResponse["metadata"] | null>(null);
  const [costDiscountRows, setCostDiscountRows] = useState<CostDiscountRow[]>([]);
  const [revenueDiscountRows, setRevenueDiscountRows] = useState<RevenueDiscountRow[]>([]);
  const kpiDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [runJobId, setRunJobId] = useState("");
  const [lookupJobId, setLookupJobId] = useState("");
  const [jobDetail, setJobDetail] = useState<JobDetail | null>(null);
  const [jobArtifacts, setJobArtifacts] = useState<JobArtifacts | null>(null);

  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [fileForm, setFileForm] = useState<FileForm>({ category: "supplier-bill", job_id: "", session_id: "", uploaded_by: "ops" });
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [filePreview, setFilePreview] = useState<FilePreview | null>(null);
  const [filePreviewLoading, setFilePreviewLoading] = useState(false);
  const [filePreviewError, setFilePreviewError] = useState("");
  const [filePreviewFileId, setFilePreviewFileId] = useState("");
  const [changeRequests, setChangeRequests] = useState<ChangeRequest[]>([]);

  // 经验/技能知识库（经验 = Skills）。skillPreview 为对账会话即将注入的技能列表。
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillPreview, setSkillPreview] = useState<SkillPreviewItem[]>([]);
  const [excludedSkillIds, setExcludedSkillIds] = useState<string[]>([]);

  const [rawLogsConfig, setRawLogsConfig] = useState<RawLogsConfig | null>(null);
  const [rawLogsForm, setRawLogsForm] = useState<RawLogsForm>({
    bucket: "",
    prefix: "llm-raw-logs",
    year: rawLogDefaultDate.year,
    month: rawLogDefaultDate.month,
    day: rawLogDefaultDate.day,
    hour: "",
    query: "",
    recursive: false,
  });
  const [rawLogPrefixes, setRawLogPrefixes] = useState<string[]>([]);
  const [rawLogObjects, setRawLogObjects] = useState<RawLogObject[]>([]);
  const [rawLogsNextToken, setRawLogsNextToken] = useState("");
  const [selectedRawLogKey, setSelectedRawLogKey] = useState("");
  const [rawLogPreview, setRawLogPreview] = useState<RawLogPreview | null>(null);
  const [rawLogSearchResult, setRawLogSearchResult] = useState<RawLogSearchResult | null>(null);

  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [sessionFilter, setSessionFilter] = useState<SessionFilter>({ q: "", vendor: "", month: "", tag: "", favorite: false });
  const [agentSessionId, setAgentSessionId] = useState("");
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([]);
  const [agentFiles, setAgentFiles] = useState<UploadedFile[]>([]);
  const [agentResult, setAgentResult] = useState<AgentResult | null>(null);
  const [agentSelectedFiles, setAgentSelectedFiles] = useState<File[]>([]);
  const [agentStreamActive, setAgentStreamActive] = useState(false);
  const [agentUploadForm, setAgentUploadForm] = useState<AgentUploadForm>({ category: "reconcile-evidence", job_id: "", uploaded_by: "ops" });
  const [streamStatus, setStreamStatus] = useState("待开始");
  const [agentForm, setAgentForm] = useState<AgentForm>({
    prompt: "你已带上本次账单、供应商资料和价格方案。所有对账均基于刊例价进行；请先检查可能的对账差异，说明原因，并给出下一步处理建议。",
    provider: "claude_code",
    runtime: "codingplan",
    model: "glm-5.2",
    live: true,
  });
  const [agentMessage, setAgentMessage] = useState("");

  const streamRef = useRef<EventSource | null>(null);
  const streamSessionIdRef = useRef("");
  const agentSessionIdRef = useRef("");
  const newAgentDraftRef = useRef(false);

  useEffect(() => {
    agentSessionIdRef.current = agentSessionId;
  }, [agentSessionId]);

  const currentSession = sessions.find((session) => session.id === agentSessionId);
  const hasActiveAgentSession = useMemo(
    () => sessions.some((session) => activeAgentStatuses.has(String(session.status || "").toUpperCase())),
    [sessions],
  );

  const patchAgentSession = useCallback((id: string, patch: Partial<AgentSession>) => {
    if (!id) return;
    const nextPatch = patch.status && !patch.updated_at ? { ...patch, updated_at: new Date().toISOString() } : patch;
    setSessions((prev) =>
      prev.map((session) => {
        if (session.id !== id) return session;
        const metadata = nextPatch.metadata ? { ...(session.metadata || {}), ...nextPatch.metadata } : session.metadata;
        return { ...session, ...nextPatch, metadata };
      }),
    );
  }, []);

  const upsertAgentSession = useCallback((session?: AgentSession | null) => {
    if (!session?.id) return;
    setSessions((prev) => {
      if (prev.some((item) => item.id === session.id)) {
        return prev.map((item) => (item.id === session.id ? mergeAgentSessionSnapshot(item, session) : item));
      }
      return [session, ...prev];
    });
  }, []);

  const appendAgentEvents = useCallback((events: AgentEvent[]) => {
    const cleanEvents = events.filter(Boolean);
    if (!cleanEvents.length) return;
    setAgentEvents((prev) => {
      const seen = new Set(prev.map((item) => item.id).filter(Boolean));
      const next = cleanEvents.filter((item) => !item.id || !seen.has(item.id));
      return next.length ? [...prev, ...next] : prev;
    });
  }, []);

  const applyAgentEvent = useCallback(
    (sessionId: string, event: AgentEvent) => {
      if (!sessionId) return;
      const status = statusFromAgentEvent(event);
      const embeddedResult = resultFromAgentEvent(event);
      const patch: Partial<AgentSession> = {};
      if (status) patch.status = status;
      if (event.created_at) patch.updated_at = event.created_at;
      if (embeddedResult) {
        patch.metadata = { result: embeddedResult };
        if (agentSessionIdRef.current === sessionId) setAgentResult(embeddedResult);
      }
      if (Object.keys(patch).length) patchAgentSession(sessionId, patch);
    },
    [patchAgentSession],
  );

  const artifactRows = useMemo(() => {
    const resultArtifacts = Object.entries(jobArtifacts?.artifacts || {}).map(([name, uri]) => [name, uri]);
    const listed = (jobArtifacts?.listed || []).map((uri) => ["归档文件", uri]);
    return [...resultArtifacts, ...listed];
  }, [jobArtifacts]);

  // 统一动作执行 + 全局 toast 反馈（loading -> success/error）。
  const submitAction = useCallback(
    async <T>(label: string, action: ActionName, request: () => Promise<ApiResult<T>>, options: { silent?: boolean } = {}) => {
      setPending(action);
      const toastId = options.silent ? null : toast.push({ tone: "loading", title: label, description: "处理中…" });
      const result = await request();
      setPending(null);
      setLastAction({ label, ok: result.ok, detail: result.ok ? result.data : result.error });
      if (toastId) {
        if (result.ok) {
          toast.update(toastId, { tone: "success", title: label, description: "已完成" });
        } else {
          toast.update(toastId, { tone: "error", title: `${label}失败`, description: result.error });
        }
      }
      return result;
    },
    [toast],
  );

  // ---- 刷新类（静默，不弹 toast）-----------------------------------------
  const refreshHealth = useCallback(async () => {
    const result = await apiRequest<Health>(endpoints.health());
    if (result.ok) setHealth(result.data);
  }, []);

  const refreshJobs = useCallback(async () => {
    const result = await apiRequest<{ items: JobSummary[] }>(endpoints.jobs());
    if (result.ok) setJobs(result.data.items || []);
  }, []);

  const refreshJobQueue = useCallback(async () => {
    const result = await apiRequest<JobQueue>(endpoints.jobsQueue());
    if (result.ok) setJobQueue(result.data);
  }, []);

  const refreshWorkCenter = useCallback(async () => {
    await Promise.all([refreshJobs(), refreshJobQueue()]);
  }, [refreshJobs, refreshJobQueue]);

  const refreshAutomation = useCallback(async () => {
    const [scheduleResult, runResult, batchResult, documentResult, queueResult, jobsResult] = await Promise.all([
      apiRequest<{ items: Schedule[] }>(endpoints.schedules()),
      apiRequest<{ items: ScheduleRun[] }>(endpoints.scheduleRuns()),
      apiRequest<{ items: BillingBatch[] }>(endpoints.billingBatches()),
      apiRequest<{ items: BillDocument[] }>(endpoints.billDocuments()),
      apiRequest<JobQueue>(endpoints.jobsQueue()),
      apiRequest<{ items: JobSummary[] }>(endpoints.jobs()),
    ]);
    if (scheduleResult.ok) setSchedules(scheduleResult.data.items || []);
    if (runResult.ok) setScheduleRuns(runResult.data.items || []);
    if (batchResult.ok) setBillingBatches(batchResult.data.items || []);
    if (documentResult.ok) setBillDocuments(documentResult.data.items || []);
    if (queueResult.ok) setJobQueue(queueResult.data);
    if (jobsResult.ok) setJobs(jobsResult.data.items || []);
  }, []);

  const refreshFiles = useCallback(async () => {
    const result = await apiRequest<{ items: UploadedFile[] }>(endpoints.files());
    if (result.ok) setUploadedFiles(result.data.items || []);
  }, []);

  const refreshChangeRequests = useCallback(async () => {
    const result = await apiRequest<{ items: ChangeRequest[] }>(endpoints.changeRequests());
    if (result.ok) setChangeRequests(result.data.items || []);
  }, []);

  // ---- 经验/技能知识库 ----------------------------------------------------
  const refreshSkills = useCallback(async () => {
    const result = await apiRequest<{ items: Skill[] }>(endpoints.skills());
    if (result.ok) setSkills(result.data.items || []);
  }, []);

  const createSkill = useCallback(
    async (form: SkillForm) => {
      const applies_to: Record<string, unknown> = {};
      const billTypes = splitList(form.bill_type);
      const keywords = splitList(form.keywords);
      if (billTypes.length) applies_to.bill_type = billTypes;
      if (keywords.length) applies_to.keywords = keywords;
      const result = await submitAction("新增经验", "skills", () =>
        apiRequest<JsonObject>(endpoints.skills(), {
          method: "POST",
          bodyJson: {
            name: form.name.trim(),
            category: form.category.trim() || "billing-experience",
            vendor: form.vendor.trim() || "*",
            tags: splitList(form.tags),
            content: form.content,
            applies_to,
            source: "manual",
          },
        }),
      );
      if (result.ok) await refreshSkills();
      return result;
    },
    [submitAction, refreshSkills],
  );

  const updateSkill = useCallback(
    async (
      id: string,
      payload: { name?: string; vendor?: string; tags?: string[]; content?: string; applies_to?: Record<string, unknown> },
    ) => {
      const result = await submitAction("保存经验", "skills", () =>
        apiRequest<JsonObject>(endpoints.skill(id), { method: "PUT", bodyJson: payload }),
      );
      if (result.ok) await refreshSkills();
      return result;
    },
    [submitAction, refreshSkills],
  );

  const setSkillStatus = useCallback(
    async (id: string, status: "active" | "disabled") => {
      setSkills((prev) => prev.map((item) => (item.id === id ? { ...item, status } : item)));
      const result = await submitAction(status === "active" ? "启用经验" : "停用经验", "skills", () =>
        apiRequest<JsonObject>(endpoints.skill(id), { method: "PATCH", bodyJson: { status } }),
      );
      if (!result.ok) await refreshSkills();
      return result;
    },
    [submitAction, refreshSkills],
  );

  const deleteSkill = useCallback(
    async (id: string) => {
      const result = await submitAction("删除经验", "skills", () =>
        apiRequest<JsonObject>(endpoints.skill(id), { method: "DELETE" }),
      );
      if (result.ok) await refreshSkills();
      return result;
    },
    [submitAction, refreshSkills],
  );

  const loadSkillContent = useCallback(async (id: string) => {
    const result = await apiRequest<SkillContent>(endpoints.skill(id));
    return result.ok ? result.data : null;
  }, []);

  const previewSkills = useCallback(
    async (params: { vendor?: string; bill_type?: string; month?: string; excluded?: string[] } = {}) => {
      const result = await apiRequest<{ items: SkillPreviewItem[] }>(endpoints.skillsPreview(params));
      if (result.ok) setSkillPreview(result.data.items || []);
      return result;
    },
    [],
  );

  const saveAgentSkillExclusions = useCallback(
    async (sessionId: string, ids: string[]) => {
      if (!sessionId) return;
      const result = await submitAction("更新技能排除", "skills", () =>
        apiRequest<JsonObject>(endpoints.sessionSkillExclusions(sessionId), {
          method: "POST",
          bodyJson: { excluded_skill_ids: ids, updated_by: "ops" },
        }),
      );
      return result;
    },
    [submitAction],
  );

  const loadConfigVersions = useCallback(async () => {
    const result = await apiRequest<{ items: ConfigVersion[] }>(endpoints.configVersions());
    if (result.ok) {
      const items = result.data.items || [];
      setConfigVersions(items);
      const active = items.find((v) => v.status === "active") || items[0];
      if (active?.version) {
        setBillingForm((prev) => {
          const exists = items.some((v) => v.version === prev.config_version);
          if (!prev.config_version || !exists) {
            return { ...prev, config_version: active.version };
          }
          return prev;
        });
      }
    }
    return result;
  }, []);

  const ensureConfigBootstrap = useCallback(async () => {
    const versions = await loadConfigVersions();
    if (versions.ok && !(versions.data.items || []).length) {
      await apiRequest(endpoints.configBootstrap(), { method: "POST", bodyJson: { created_by: "web-bootstrap" } });
      await loadConfigVersions();
    }
  }, [loadConfigVersions]);

  const loadPricing = useCallback(async (version?: string) => {
    const result = await apiRequest<PricingResponse>(endpoints.pricing(version));
    if (result.ok) {
      setPricingRows(result.data.rows || []);
      setPricingMetadata(result.data.metadata || null);
    }
    return result;
  }, []);

  const savePricing = useCallback(
    async (rows: { rows: PricingRow[] }) => {
      const result = await submitAction("保存刊例价", "pricing", () =>
        apiRequest<PricingResponse>(endpoints.pricing(), {
          method: "PUT",
          bodyJson: { rows: rows.rows, created_by: "ops" },
        }),
      );
      if (result.ok) {
        await loadPricing();
      }
      return result;
    },
    [submitAction, loadPricing],
  );

  const reseedPricing = useCallback(async () => {
    const result = await submitAction("导入 scripts/athena 刊例价", "pricing", () =>
      apiRequest<PricingResponse>(endpoints.reseedPricing(), { method: "POST", bodyJson: { created_by: "seed-import" } }),
    );
    if (result.ok) {
      setPricingRows(result.data.rows || []);
      setPricingMetadata(result.data.metadata || null);
    }
    return result;
  }, [submitAction]);

  const loadDiscounts = useCallback(async (version?: string) => {
    const result = await apiRequest<DiscountsResponse>(endpoints.discounts(version));
    if (result.ok) {
      setCostDiscountRows(result.data.cost_rows || []);
      setRevenueDiscountRows(result.data.revenue_rows || []);
    }
    return result;
  }, []);

  const saveDiscounts = useCallback(
    async (rows: { cost_rows: CostDiscountRow[]; revenue_rows: RevenueDiscountRow[] }) => {
      const result = await submitAction("保存价格方案", "discounts", () =>
        apiRequest<DiscountsResponse>(endpoints.discounts(), {
          method: "PUT",
          bodyJson: { cost_rows: rows.cost_rows, revenue_rows: rows.revenue_rows, created_by: "ops" },
        }),
      );
      if (result.ok) {
        // 折扣全局生效，保存后直接回读当前生效配置即可。
        await loadDiscounts();
      }
      return result;
    },
    [submitAction, loadDiscounts],
  );

  const reseedDiscounts = useCallback(async () => {
    const result = await submitAction("导入 scripts/athena 折扣", "discounts", () =>
      apiRequest<DiscountsResponse>(endpoints.reseedDiscounts(), { method: "POST", bodyJson: { created_by: "seed-import" } }),
    );
    if (result.ok) {
      setCostDiscountRows(result.data.cost_rows || []);
      setRevenueDiscountRows(result.data.revenue_rows || []);
    }
    return result;
  }, [submitAction]);

  const previewKpi = useCallback(async () => {
    if (!billingForm.month.trim() || !billingForm.config_version.trim()) return;
    setKpiLoading(true);
    const payload = compactPayload({
      month: billingForm.month,
      config_version: billingForm.config_version,
      channel_id: billingForm.scope === "channel" && billingForm.channel_id ? Number(billingForm.channel_id) : undefined,
      user_id: billingForm.scope === "user" && billingForm.user_id ? Number(billingForm.user_id) : undefined,
      no_cache: billingForm.no_cache,
    });
    const result = await apiRequest<KpiPreview>(endpoints.kpiPreview(), { method: "POST", bodyJson: payload });
    setKpiLoading(false);
    if (result.ok) setKpiPreview(result.data);
    return result;
  }, [billingForm]);

  const scheduleKpiPreview = useCallback(() => {
    if (kpiDebounceRef.current) clearTimeout(kpiDebounceRef.current);
    kpiDebounceRef.current = setTimeout(() => void previewKpi(), 500);
  }, [previewKpi]);

  const downloadBlob = useCallback(
    async (url: string, filename: string, label = "下载") => {
      try {
        const response = await fetch(url);
        if (!response.ok) {
          const body = await response.text();
          let detail = body;
          try {
            const parsed = JSON.parse(body) as { detail?: unknown };
            if (typeof parsed.detail === "string") detail = parsed.detail;
          } catch {
            // keep raw body
          }
          throw new Error(detail || response.statusText || `HTTP ${response.status}`);
        }
        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = objectUrl;
        anchor.download = filename || "download";
        anchor.rel = "noopener";
        anchor.style.display = "none";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(objectUrl);
      } catch (error) {
        toast.push({
          tone: "error",
          title: `${label}失败`,
          description: error instanceof Error ? error.message : String(error),
        });
      }
    },
    [toast],
  );

  const downloadArtifact = useCallback(
    async (params: { fileId?: string; uri?: string; filename?: string }) => {
      const url = `${API_BASE_URL}${endpoints.billingDownload(params)}`;
      await downloadBlob(url, params.filename || "download", "下载账单文件");
    },
    [downloadBlob],
  );

  const resolveFileUrl = useCallback((url: string) => {
    if (!url) return "";
    if (url.startsWith("http://") || url.startsWith("https://")) return url;
    return `${API_BASE_URL}${url.startsWith("/") ? url : `/${url}`}`;
  }, []);

  const downloadFile = useCallback(
    async (fileId: string, filename?: string) => {
      const url = `${API_BASE_URL}${endpoints.fileDownload(fileId)}`;
      await downloadBlob(url, filename || "download", "下载文件");
    },
    [downloadBlob],
  );

  const clearFilePreview = useCallback(() => {
    setFilePreview(null);
    setFilePreviewError("");
    setFilePreviewFileId("");
    setFilePreviewLoading(false);
  }, []);

  const previewFile = useCallback(
    async (fileId: string) => {
      if (!fileId) {
        clearFilePreview();
        return;
      }
      setFilePreviewFileId(fileId);
      setFilePreviewLoading(true);
      setFilePreviewError("");
      const result = await apiRequest<FilePreview>(endpoints.filePreview(fileId));
      setFilePreviewLoading(false);
      if (result.ok) {
        setFilePreview(result.data);
      } else {
        setFilePreview(null);
        setFilePreviewError(result.error);
      }
    },
    [clearFilePreview],
  );

  const pollJob = useCallback(
    async (jobId: string) => {
      const terminal = new Set(["COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"]);
      const started = Date.now();
      setPollElapsed(0);
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      pollTimerRef.current = setInterval(() => setPollElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
      try {
        while (true) {
          const detail = await apiRequest<JobDetail>(endpoints.job(jobId));
          if (detail.ok) setJobDetail(detail.data);
          const artifacts = await apiRequest<JobArtifacts>(endpoints.jobArtifacts(jobId));
          if (artifacts.ok) setJobArtifacts(artifacts.data);
          const status = detail.ok ? String(detail.data.job?.status || "").toUpperCase() : "";
          if (terminal.has(status)) break;
          await new Promise((resolve) => setTimeout(resolve, 2000));
        }
      } finally {
        if (pollTimerRef.current) {
          clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
        }
        setPollElapsed(Math.floor((Date.now() - started) / 1000));
        await refreshWorkCenter();
        await refreshFiles();
      }
    },
    [refreshFiles, refreshWorkCenter],
  );

  const loadAgentHistory = useCallback(
    async (id = agentSessionId) => {
      if (!id) return;
      const result = await apiRequest<{ session?: AgentSession; events: AgentEvent[]; files: UploadedFile[] }>(endpoints.sessionHistory(id));
      if (result.ok) {
        const events = result.data.events || [];
        if (agentSessionIdRef.current === id) {
          setAgentEvents(events);
          setAgentFiles(result.data.files || []);
        }
        events.forEach((event) => applyAgentEvent(id, event));
        upsertAgentSession(result.data.session);
      }
    },
    [agentSessionId, applyAgentEvent, upsertAgentSession],
  );

  // 读取真实 result.json：优先专用端点，回退 session.metadata.result。
  const loadAgentResult = useCallback(async (id = agentSessionId, status?: string) => {
    if (!id) {
      setAgentResult(null);
      return;
    }
    if (!canLoadAgentResult(status)) {
      setAgentResult(null);
      return;
    }
    const detail = await apiRequest<AgentSession | { session?: AgentSession }>(endpoints.session(id));
    const detailSession = detail.ok
      ? ("session" in detail.data && detail.data.session ? detail.data.session : (detail.data as AgentSession))
      : null;
    if (detailSession) {
      upsertAgentSession(detailSession);
      const metadata = detailSession.metadata as JsonObject | undefined;
      const embedded = (metadata?.result || metadata?.result_json) as AgentResult | undefined;
      if (embedded && typeof embedded === "object") {
        setAgentResult(embedded);
        return;
      }
      if (!canLoadAgentResult(detailSession.status)) {
        setAgentResult(null);
        return;
      }
      if (String(detailSession.status || "").toUpperCase() && String(detailSession.status || "").toUpperCase() !== "COMPLETED") {
        setAgentResult(null);
        return;
      }
    }
    const result = await apiRequest<AgentResult>(endpoints.sessionResult(id));
    setAgentResult(result.ok && result.data && typeof result.data === "object" ? result.data : null);
  }, [agentSessionId, upsertAgentSession]);

  const refreshSessions = useCallback(
    async (options: { selectLatest?: boolean; filter?: SessionFilter } = {}) => {
      const filter = options.filter || sessionFilter;
      const result = await apiRequest<{ items: AgentSession[] }>(
        endpoints.sessions({ q: filter.q, vendor: filter.vendor, month: filter.month, tag: filter.tag, favorite: filter.favorite }),
      );
      if (!result.ok) return;
      const items = result.data.items || [];
      setSessions((prev) => {
        const localById = new Map(prev.map((item) => [item.id, item]));
        return items.map((item) => mergeAgentSessionSnapshot(localById.get(item.id), item));
      });
      if (options.selectLatest && items[0] && !agentSessionIdRef.current && !newAgentDraftRef.current) {
        agentSessionIdRef.current = items[0].id;
        setAgentSessionId(items[0].id);
        await loadAgentHistory(items[0].id);
        await loadAgentResult(items[0].id, items[0].status);
      }
    },
    [sessionFilter, loadAgentHistory, loadAgentResult],
  );

  const refreshRawLogsConfig = useCallback(async () => {
    const result = await apiRequest<RawLogsConfig>(endpoints.rawlogsConfig());
    if (!result.ok) return;
    setRawLogsConfig(result.data);
    setRawLogsForm((prev) => ({
      ...prev,
      bucket: prev.bucket || result.data.bucket || "",
      prefix: prev.prefix || result.data.prefix || "llm-raw-logs",
    }));
  }, []);

  useEffect(() => {
    void refreshHealth();
    void ensureConfigBootstrap();
    void refreshWorkCenter();
    void refreshAutomation();
    void refreshFiles();
    void refreshRawLogsConfig();
    void refreshSessions({ selectLatest: true });
    void refreshChangeRequests();
    void refreshSkills();
    return () => {
      streamRef.current?.close();
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      if (kpiDebounceRef.current) clearTimeout(kpiDebounceRef.current);
    };
    // 仅初始化执行一次。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!agentStreamActive && !hasActiveAgentSession) return;
    const timer = setInterval(() => {
      void refreshSessions();
      const id = agentSessionIdRef.current;
      if (id) void loadAgentHistory(id);
    }, 3000);
    return () => clearInterval(timer);
  }, [agentStreamActive, hasActiveAgentSession, refreshSessions, loadAgentHistory]);

  useEffect(() => {
    scheduleKpiPreview();
    return () => {
      if (kpiDebounceRef.current) clearTimeout(kpiDebounceRef.current);
    };
  }, [billingForm.month, billingForm.scope, billingForm.channel_id, billingForm.user_id, billingForm.config_version, billingForm.no_cache, scheduleKpiPreview]);

  // ---- 账单 ---------------------------------------------------------------
  const loadJob = useCallback(
    async (id = lookupJobId.trim()) => {
      if (!id) return;
      const detail = await submitAction("查询账单任务", "job", () => apiRequest<JobDetail>(endpoints.job(id)));
      if (detail.ok) setJobDetail(detail.data);
      const artifacts = await apiRequest<JobArtifacts>(endpoints.jobArtifacts(id));
      if (artifacts.ok) setJobArtifacts(artifacts.data);
    },
    [lookupJobId, submitAction],
  );

  const createBillingRun = useCallback(
    async (runAfterCreate = false) => {
      const extraMetadata = parseJsonInput(billingForm.extra_metadata);
      if (!extraMetadata.ok) {
        toast.push({ tone: "error", title: "创建账单任务失败", description: extraMetadata.error });
        return;
      }
      const payload = compactPayload({
        month: billingForm.month,
        channel_id: billingForm.scope === "channel" && billingForm.channel_id ? Number(billingForm.channel_id) : undefined,
        vendor: billingForm.vendor,
        bill_type: billingForm.bill_type,
        target_type: billingForm.scope === "user" ? "customer" : billingForm.scope === "channel" ? "channel" : "all",
        target_id: billingForm.scope === "user" ? billingForm.user_id : billingForm.scope === "channel" ? billingForm.channel_id : undefined,
        config_version: billingForm.config_version,
        created_by: billingForm.created_by,
        metadata: buildBillingMetadata(billingForm, extraMetadata.data),
      });
      const result = await submitAction(runAfterCreate ? "创建并生成账单" : "创建账单任务", "billing", () =>
        apiRequest<JsonObject>(endpoints.billingRun(), { method: "POST", bodyJson: payload }),
      );
      if (result.ok && typeof result.data.job_id === "string") {
        const jobId = String(result.data.job_id);
        setRunJobId(jobId);
        setLookupJobId(jobId);
        setJobDetail(null);
        setJobArtifacts(null);
        setFileForm((prev) => ({ ...prev, job_id: jobId }));
        setAgentUploadForm((prev) => ({ ...prev, job_id: jobId }));
        await refreshWorkCenter();
        if (runAfterCreate) {
          setPollElapsed(0);
          const runResult = await submitAction("生成账单", "run", () => apiRequest<JsonObject>(endpoints.jobRun(jobId), { method: "POST" }));
          if (runResult.ok) {
            const runStatus = String(runResult.data?.status || "").toUpperCase();
            if (runStatus === "RUNNING" || runStatus === "QUEUED") {
              await pollJob(jobId);
            } else {
              await loadJobInternal(jobId);
              await refreshFiles();
            }
          }
          await refreshWorkCenter();
        } else {
          const detail = await apiRequest<JobDetail>(endpoints.job(jobId));
          if (detail.ok) setJobDetail(detail.data);
          const artifacts = await apiRequest<JobArtifacts>(endpoints.jobArtifacts(jobId));
          if (artifacts.ok) setJobArtifacts(artifacts.data);
        }
      }
    },
    // loadJobInternal defined below via closure; depend on stable deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [billingForm, submitAction, refreshWorkCenter, refreshFiles, toast],
  );

  async function loadJobInternal(id: string) {
    const detail = await apiRequest<JobDetail>(endpoints.job(id));
    if (detail.ok) setJobDetail(detail.data);
    const artifacts = await apiRequest<JobArtifacts>(endpoints.jobArtifacts(id));
    if (artifacts.ok) setJobArtifacts(artifacts.data);
  }

  const runCurrentJob = useCallback(async () => {
    if (!runJobId.trim()) return;
    const id = runJobId.trim();
    setPollElapsed(0);
    const result = await submitAction("生成账单", "run", () => apiRequest<JsonObject>(endpoints.jobRun(id), { method: "POST" }));
    if (result.ok) {
      setLookupJobId(id);
      const runStatus = String(result.data?.status || "").toUpperCase();
      if (runStatus === "RUNNING" || runStatus === "QUEUED") {
        await pollJob(id);
      } else {
        await loadJobInternal(id);
        await refreshWorkCenter();
        await refreshFiles();
      }
    }
  }, [runJobId, submitAction, refreshWorkCenter, refreshFiles, pollJob]);

  const runJobFromCenter = useCallback(
    async (jobId: string) => {
      if (!jobId) return;
      setRunJobId(jobId);
      setLookupJobId(jobId);
      const result = await submitAction("继续处理任务", "run", () => apiRequest<JsonObject>(endpoints.jobRun(jobId), { method: "POST" }));
      if (result.ok) {
        await loadJobInternal(jobId);
        await refreshWorkCenter();
        await refreshFiles();
      }
    },
    [submitAction, refreshWorkCenter, refreshFiles],
  );

  const runNextQueuedJob = useCallback(async () => {
    const result = await submitAction("运行下一条排队任务", "queue", () => apiRequest<JsonObject>(endpoints.runNextQueued(), { method: "POST" }));
    if (result.ok) await refreshWorkCenter();
  }, [submitAction, refreshWorkCenter]);

  // ---- 文件上传 / 引用 ----------------------------------------------------
  const uploadSelectedFiles = useCallback(async () => {
    if (!selectedFiles.length) return;
    const uploaded: UploadedFile[] = [];
    for (const file of selectedFiles) {
      const payload = compactPayload({
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        content_base64: await fileToBase64(file),
        category: fileForm.category,
        job_id: fileForm.job_id,
        session_id: fileForm.session_id,
        uploaded_by: fileForm.uploaded_by,
        metadata: { source: "web-upload" },
      });
      const result = await submitAction(`上传 ${file.name}`, "upload", () =>
        apiRequest<{ file: UploadedFile }>(endpoints.fileUpload(), { method: "POST", bodyJson: payload }),
      );
      if (result.ok) uploaded.push(result.data.file);
    }
    setSelectedFiles([]);
    if (uploaded.length) setUploadedFiles((prev) => [...uploaded, ...prev]);
    if (agentSessionId) await loadAgentHistory(agentSessionId);
  }, [selectedFiles, fileForm, submitAction, agentSessionId, loadAgentHistory]);

  const createAgentSession = useCallback(
    async (excludedSkillIdsArg: string[] = excludedSkillIds, promptOverride?: string, options: { silent?: boolean } = {}) => {
      const result = await submitAction(
        "开启 Agent 对话",
        "agent",
        () =>
          apiRequest<{ session?: AgentSession; session_id?: string; id?: string; status?: string; metadata?: JsonObject }>(endpoints.sessions(), {
            method: "POST",
            bodyJson: compactPayload({
              prompt: promptOverride ?? agentForm.prompt,
              provider: agentForm.provider,
              runtime: agentForm.runtime,
              model: agentForm.model,
              job_id: agentUploadForm.job_id,
              live: agentForm.live,
              // 经验改为 Skills 自动注入；会话仅携带需排除的技能 id。
              metadata: { source: "web-console", excluded_skill_ids: excludedSkillIdsArg },
            }),
          }),
        { silent: options.silent ?? true },
      );
      if (result.ok) {
        const sessionId = result.data.session?.id || result.data.session_id || result.data.id || "";
        if (!sessionId) return null;
        const prompt = promptOverride ?? agentForm.prompt;
        newAgentDraftRef.current = false;
        agentSessionIdRef.current = sessionId;
        setAgentSessionId(sessionId);
        setFileForm((prev) => ({ ...prev, session_id: sessionId }));
        upsertAgentSession(
          result.data.session || {
            id: sessionId,
            provider: agentForm.provider,
            runtime: agentForm.runtime,
            status: result.data.status || "CREATED",
            prompt,
            title: prompt.trim().split(/\r?\n/)[0]?.slice(0, 80) || sessionId,
            metadata: result.data.metadata || { source: "web-console", excluded_skill_ids: excludedSkillIdsArg },
          },
        );
        await refreshSessions();
        await loadAgentHistory(sessionId);
        return sessionId;
      }
      return null;
    },
    [agentForm, agentUploadForm.job_id, excludedSkillIds, submitAction, upsertAgentSession, refreshSessions, loadAgentHistory],
  );

  const referenceFilesToAgent = useCallback(
    async (fileIds: string[]) => {
      const selectedIds = fileIds.filter(Boolean);
      if (!selectedIds.length) return null;
      const sessionId = agentSessionId || (await createAgentSession());
      if (!sessionId) return null;
      const result = await submitAction("引用资料到对话", "agent", () =>
        apiRequest<{ files: UploadedFile[]; event?: AgentEvent }>(endpoints.sessionFiles(sessionId), {
          method: "POST",
          bodyJson: { file_ids: selectedIds, referenced_by: "ops", metadata: { source: "web-console" } },
        }),
      );
      if (result.ok) {
        setAgentSessionId(sessionId);
        const files = result.data.files || [];
        if (files.length) {
          setAgentFiles((prev) => mergeUploadedFiles(prev, files));
          setUploadedFiles((prev) => mergeUploadedFiles(files, prev));
        }
        if (result.data.event) {
          appendAgentEvents([result.data.event]);
          applyAgentEvent(sessionId, result.data.event);
        }
        await loadAgentHistory(sessionId);
        if (files.length) setAgentFiles((prev) => mergeUploadedFiles(prev, files));
        if (result.data.event) {
          appendAgentEvents([result.data.event]);
          applyAgentEvent(sessionId, result.data.event);
        }
        await refreshSessions();
        return sessionId;
      }
      return null;
    },
    [agentSessionId, createAgentSession, submitAction, appendAgentEvents, applyAgentEvent, loadAgentHistory, refreshSessions],
  );

  const referenceBillDocumentToAgent = useCallback(
    async (documentId: string) => {
      if (!documentId) return null;
      const result = await submitAction("准备账单引用", "agent", () =>
        apiRequest<{ files: UploadedFile[] }>(endpoints.billDocumentReferenceFiles(documentId), {
          method: "POST",
          bodyJson: { referenced_by: "ops", metadata: { source: "bill-library" } },
        }),
      );
      if (!result.ok) return null;
      const files = result.data.files || [];
      if (files.length) {
        setUploadedFiles((prev) => {
          const seen = new Set(prev.map((file) => file.id));
          return [...files.filter((file) => !seen.has(file.id)), ...prev];
        });
      }
      const sessionId = await referenceFilesToAgent(files.map((file) => file.id));
      await refreshFiles();
      return sessionId;
    },
    [submitAction, referenceFilesToAgent, refreshFiles],
  );

  const uploadAgentFiles = useCallback(async () => {
    if (!agentSelectedFiles.length) return agentSessionId || null;
    const sessionId = agentSessionId || (await createAgentSession());
    if (!sessionId) return null;
    const uploaded: UploadedFile[] = [];
    for (const file of agentSelectedFiles) {
      const payload = compactPayload({
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        content_base64: await fileToBase64(file),
        category: agentUploadForm.category,
        job_id: agentUploadForm.job_id,
        session_id: sessionId,
        uploaded_by: agentUploadForm.uploaded_by,
        metadata: { source: "agent-workbench", usage: "agent-reconcile-context" },
      });
      const result = await submitAction(`上传 ${file.name}`, "upload", () =>
        apiRequest<{ file: UploadedFile }>(endpoints.fileUpload(), { method: "POST", bodyJson: payload }),
      );
      if (result.ok) uploaded.push(result.data.file);
    }
    setAgentSelectedFiles([]);
    if (uploaded.length) {
      setUploadedFiles((prev) => mergeUploadedFiles(uploaded, prev));
      setAgentFiles((prev) => mergeUploadedFiles(prev, uploaded));
    }
    await loadAgentHistory(sessionId);
    if (uploaded.length) setAgentFiles((prev) => mergeUploadedFiles(prev, uploaded));
    await refreshSessions();
    return sessionId;
  }, [agentSelectedFiles, agentSessionId, agentUploadForm, createAgentSession, submitAction, loadAgentHistory, refreshSessions]);

  // SSE 实时流，结束后刷新历史/结论。
  const startAgentStream = useCallback(
    (sessionId: string) => {
      if (!sessionId) return;
      if (streamRef.current && streamSessionIdRef.current === sessionId) {
        setAgentStreamActive(true);
        patchAgentSession(sessionId, { status: "RUNNING" });
        setStreamStatus((prev) => (prev && prev !== "待开始" ? prev : "运行中"));
        return;
      }
      streamRef.current?.close();
      streamSessionIdRef.current = sessionId;
      setAgentStreamActive(true);
      setPending("agentStream");
      patchAgentSession(sessionId, { status: "RUNNING" });
      setStreamStatus("运行中");
      const source = new EventSource(`${API_BASE_URL}${endpoints.sessionStream(sessionId, agentForm.live)}`);
      streamRef.current = source;
      const appendEvent = (event: MessageEvent) => {
        try {
          const parsed = JSON.parse(event.data) as AgentEvent;
          const isCurrentSession = agentSessionIdRef.current === sessionId;
          if (isCurrentSession) appendAgentEvents([parsed]);
          applyAgentEvent(sessionId, parsed);
          if (isCurrentSession && parsed.event_type === "human.input.waiting") setStreamStatus("等待补充信息");
          if (isCurrentSession && parsed.event_type === "operator.message.received") setStreamStatus("已收到补充信息");
          if (parsed.event_type === "run.completed" || parsed.event_type === "run.error") {
            if (isCurrentSession) setStreamStatus(parsed.event_type === "run.completed" ? "已完成" : "失败");
            setAgentStreamActive(false);
            setPending(null);
            source.close();
            streamRef.current = null;
            streamSessionIdRef.current = "";
            void loadAgentHistory(sessionId);
            void refreshSessions();
            void loadAgentResult(sessionId, statusFromAgentEvent(parsed) || undefined);
          }
        } catch {
          setStreamStatus("事件解析失败");
        }
      };
      streamEventTypes.forEach((type) => source.addEventListener(type, appendEvent));
      source.onerror = () => {
        setAgentStreamActive(false);
        setPending(null);
        setStreamStatus("连接已关闭");
        source.close();
        streamRef.current = null;
        streamSessionIdRef.current = "";
        void loadAgentHistory(sessionId);
        void refreshSessions();
      };
    },
    [agentForm.live, patchAgentSession, appendAgentEvents, applyAgentEvent, loadAgentHistory, refreshSessions, loadAgentResult],
  );

  // 直接提问即自动建会话 + 发送 + 开流，一个动作完成完整对话。
  const sendAndStream = useCallback(
    async (content?: string, targetSessionId?: string) => {
      const text = (content ?? agentMessage).trim();
      if (!text) return;
      let sessionId = targetSessionId || agentSessionId;
      if (!sessionId) {
        // 新会话用默认指令作为种子上下文，用户输入作为首条消息，避免重复内容。
        sessionId = (await createAgentSession([], undefined, { silent: false })) || "";
        if (!sessionId) return;
      }
      const result = await submitAction("发送给 Agent", "agentMessage", () =>
        apiRequest<JsonObject & { event?: AgentEvent; ack_event?: AgentEvent | null }>(endpoints.sessionMessages(sessionId), {
          method: "POST",
          bodyJson: { role: "user", content: text, metadata: { source: "web-console" } },
        }),
      );
      if (result.ok) {
        setAgentMessage("");
        const immediateEvents = [result.data.event, result.data.ack_event].filter(Boolean) as AgentEvent[];
        if (immediateEvents.length) {
          appendAgentEvents(immediateEvents);
          immediateEvents.forEach((event) => applyAgentEvent(sessionId, event));
        } else {
          patchAgentSession(sessionId, { status: "HUMAN_REPLIED" });
        }
        await loadAgentHistory(sessionId);
        if (immediateEvents.length) {
          appendAgentEvents(immediateEvents);
          immediateEvents.forEach((event) => applyAgentEvent(sessionId, event));
        }
        startAgentStream(sessionId);
      }
    },
    [agentMessage, agentSessionId, createAgentSession, submitAction, appendAgentEvents, applyAgentEvent, patchAgentSession, loadAgentHistory, startAgentStream],
  );

  const pauseAgentSession = useCallback(
    async (id?: string) => {
      const sessionId = id || agentSessionId;
      if (!sessionId) return;
      await submitAction("暂停对话", "agent", () =>
        apiRequest<JsonObject>(endpoints.sessionPause(sessionId), { method: "POST" }),
      );
      patchAgentSession(sessionId, { status: "PAUSED" });
    },
    [agentSessionId, submitAction, patchAgentSession],
  );

  const resumeAgentSession = useCallback(
    async (id?: string) => {
      const sessionId = id || agentSessionId;
      if (!sessionId) return;
      await submitAction("恢复对话", "agent", () =>
        apiRequest<JsonObject>(endpoints.sessionResume(sessionId), { method: "POST" }),
      );
      patchAgentSession(sessionId, { status: "RUNNING" });
    },
    [agentSessionId, submitAction, patchAgentSession],
  );

  const selectSession = useCallback(
    async (id: string) => {
      newAgentDraftRef.current = false;
      agentSessionIdRef.current = id;
      setAgentSessionId(id);
      await loadAgentHistory(id);
      const selected = sessions.find((session) => session.id === id);
      await loadAgentResult(id, selected?.status);
    },
    [loadAgentHistory, loadAgentResult, sessions],
  );

  const pauseSession = useCallback(
    async (id: string) => {
      const result = await submitAction("暂停对话", "agentPause", () =>
        apiRequest<JsonObject>(endpoints.sessionPause(id), { method: "POST" }),
      );
      if (result.ok) {
        patchAgentSession(id, { status: "PAUSED" });
      }
    },
    [submitAction, patchAgentSession],
  );

  const resumeSession = useCallback(
    async (id: string) => {
      const result = await submitAction("继续对话", "agentResume", () =>
        apiRequest<JsonObject>(endpoints.sessionResume(id), { method: "POST" }),
      );
      if (result.ok) {
        patchAgentSession(id, { status: "RUNNING" });
      }
    },
    [submitAction, patchAgentSession],
  );

  const favoriteSession = useCallback(
    async (id: string, favorite: boolean) => {
      // [assumption] 后端收藏端点。先按合理命名实现。
      const result = await submitAction(favorite ? "收藏经验" : "取消收藏", "sessionFavorite", () =>
        apiRequest<JsonObject>(endpoints.sessionFavorite(id), { method: "POST", bodyJson: { favorite, updated_by: "ops" } }),
      );
      if (result.ok) {
        setSessions((prev) => prev.map((session) => (session.id === id ? { ...session, favorite } : session)));
      }
    },
    [submitAction],
  );

  const startNewAgentTask = useCallback(() => {
    streamRef.current?.close();
    streamRef.current = null;
    streamSessionIdRef.current = "";
    setAgentStreamActive(false);
    newAgentDraftRef.current = true;
    agentSessionIdRef.current = "";
    setPending(null);
    setLastAction(null);
    setAgentSessionId("");
    setAgentEvents([]);
    setAgentFiles([]);
    setAgentResult(null);
    setAgentMessage("");
    setStreamStatus("待开始");
    setFileForm((prev) => ({ ...prev, session_id: "" }));
  }, []);

  // ---- raw logs -----------------------------------------------------------
  function rawLogsParams(form: RawLogsForm, nextToken = "") {
    const params = new URLSearchParams();
    if (form.bucket.trim()) params.set("bucket", form.bucket.trim());
    if (form.prefix.trim()) params.set("prefix", form.prefix.trim());
    if (form.year.trim()) params.set("year", form.year.trim());
    if (form.month.trim()) params.set("month", form.month.trim());
    if (form.day.trim()) params.set("day", form.day.trim());
    if (form.hour.trim()) params.set("hour", form.hour.trim());
    if (form.recursive) params.set("recursive", "true");
    if (nextToken) params.set("continuation_token", nextToken);
    params.set("limit", "100");
    return params;
  }

  const previewRawLog = useCallback(
    async (key = selectedRawLogKey, bucket = rawLogsForm.bucket) => {
      if (!key) return;
      const params = new URLSearchParams();
      if (bucket.trim()) params.set("bucket", bucket.trim());
      params.set("key", key);
      params.set("max_bytes", "524288");
      const result = await submitAction("预览日志对象", "rawlogPreview", () => apiRequest<RawLogPreview>(endpoints.rawlogsObject(params.toString())));
      if (result.ok) {
        setSelectedRawLogKey(key);
        setRawLogPreview(result.data);
      }
    },
    [selectedRawLogKey, rawLogsForm.bucket, submitAction],
  );

  const loadRawLogsObjects = useCallback(
    async (nextToken = "", override: Partial<RawLogsForm> = {}) => {
      const effectiveForm = { ...rawLogsForm, ...override };
      const result = await submitAction(nextToken ? "加载更多日志" : "读取日志列表", "rawlogs", () =>
        apiRequest<{ common_prefixes?: string[]; items?: RawLogObject[]; next_token?: string }>(
          endpoints.rawlogsObjects(rawLogsParams(effectiveForm, nextToken).toString()),
        ),
      );
      if (!result.ok) return;
      const items = result.data.items || [];
      setRawLogPrefixes(result.data.common_prefixes || []);
      setRawLogsNextToken(result.data.next_token || "");
      setRawLogObjects((prev) => (nextToken ? [...prev, ...items] : items));
      if (!nextToken && items[0]) {
        setSelectedRawLogKey(items[0].key);
        await previewRawLog(items[0].key, effectiveForm.bucket);
      }
      if (!nextToken && !items.length) {
        setSelectedRawLogKey("");
        setRawLogPreview(null);
      }
    },
    [rawLogsForm, submitAction, previewRawLog],
  );

  const openRawLogPrefix = useCallback(
    async (prefix: string) => {
      const override = { prefix, year: "", month: "", day: "", hour: "" };
      setRawLogsForm((prev) => ({ ...prev, ...override }));
      await loadRawLogsObjects("", override);
    },
    [loadRawLogsObjects],
  );

  const searchRawLogs = useCallback(async () => {
    if (!rawLogsForm.query.trim()) return;
    const payload = compactPayload({
      bucket: rawLogsForm.bucket,
      prefix: rawLogsForm.prefix,
      year: rawLogsForm.year,
      month: rawLogsForm.month,
      day: rawLogsForm.day,
      hour: rawLogsForm.hour,
      query: rawLogsForm.query,
      limit: 80,
      object_limit: 60,
      max_bytes_per_object: 256 * 1024,
    });
    const result = await submitAction("搜索日志", "rawlogSearch", () => apiRequest<RawLogSearchResult>(endpoints.rawlogsSearch(), { method: "POST", bodyJson: payload }));
    if (result.ok) setRawLogSearchResult(result.data);
  }, [rawLogsForm, submitAction]);

  // ---- 账单自动化（单一状态流，/publish 直接生效）------------------------
  const runSchedule = useCallback(
    async (scheduleId: string) => {
      const result = await submitAction("运行定时任务", "automation", () => apiRequest<JsonObject>(endpoints.scheduleRun(scheduleId), { method: "POST", bodyJson: {} }));
      if (result.ok) await refreshAutomation();
    },
    [submitAction, refreshAutomation],
  );

  const retryScheduleRun = useCallback(
    async (scheduleRunId: string) => {
      const result = await submitAction("重试失败账单", "automation", () => apiRequest<JsonObject>(endpoints.retryScheduleRun(scheduleRunId), { method: "POST" }));
      if (result.ok) await refreshAutomation();
    },
    [submitAction, refreshAutomation],
  );

  const publishBillDocument = useCallback(
    async (documentId: string) => {
      const result = await submitAction("交付账单", "automation", () =>
        apiRequest<JsonObject>(endpoints.publishBillDocument(documentId), {
          method: "POST",
          bodyJson: { actor: "ops", comment: "Delivered from billing automation UI." },
        }),
      );
      if (result.ok) await refreshAutomation();
    },
    [submitAction, refreshAutomation],
  );

  // ---- 建议处理（去审批化）----------------------------------------------
  const applyChangeRequest = useCallback(
    async (changeRequestId: string) => {
      const result = await submitAction("应用建议", "change", () =>
        apiRequest<JsonObject>(endpoints.applyChangeRequest(changeRequestId), { method: "POST", bodyJson: { actor: "ops" } }),
      );
      if (result.ok) await refreshChangeRequests();
    },
    [submitAction, refreshChangeRequests],
  );

  const ignoreChangeRequest = useCallback(
    async (changeRequestId: string) => {
      const result = await submitAction("忽略建议", "change", () =>
        apiRequest<JsonObject>(endpoints.ignoreChangeRequest(changeRequestId), { method: "POST", bodyJson: { actor: "ops" } }),
      );
      if (result.ok) await refreshChangeRequests();
    },
    [submitAction, refreshChangeRequests],
  );

  const saveChangeRequestExperience = useCallback(
    async (changeRequestId: string) => {
      const result = await submitAction("保存经验", "change", () =>
        apiRequest<JsonObject>(endpoints.saveChangeRequestExperience(changeRequestId), { method: "POST", bodyJson: { actor: "ops" } }),
      );
      if (result.ok) {
        await refreshChangeRequests();
        await refreshSessions();
      }
    },
    [submitAction, refreshChangeRequests, refreshSessions],
  );

  const rerunBillForChangeRequest = useCallback(
    async (changeRequestId: string) => {
      const result = await submitAction("重新生成账单", "changeRerun", () =>
        apiRequest<JsonObject>(endpoints.rerunBillForChangeRequest(changeRequestId), { method: "POST", bodyJson: { actor: "ops" } }),
      );
      if (result.ok) {
        await refreshChangeRequests();
        await refreshWorkCenter();
      }
    },
    [submitAction, refreshChangeRequests, refreshWorkCenter],
  );

  return {
    // state
    health,
    pending,
    lastAction,
    jobs,
    jobQueue,
    schedules,
    scheduleRuns,
    billingBatches,
    billDocuments,
    billingForm,
    setBillingForm,
    configVersions,
    kpiPreview,
    kpiLoading,
    pollElapsed,
    pricingRows,
    setPricingRows,
    pricingMetadata,
    costDiscountRows,
    setCostDiscountRows,
    revenueDiscountRows,
    setRevenueDiscountRows,
    runJobId,
    setRunJobId,
    lookupJobId,
    setLookupJobId,
    jobDetail,
    jobArtifacts,
    artifactRows,
    selectedFiles,
    setSelectedFiles,
    fileForm,
    setFileForm,
    uploadedFiles,
    filePreview,
    filePreviewLoading,
    filePreviewError,
    filePreviewFileId,
    changeRequests,
    skills,
    skillPreview,
    excludedSkillIds,
    setExcludedSkillIds,
    rawLogsConfig,
    rawLogsForm,
    setRawLogsForm,
    rawLogPrefixes,
    rawLogObjects,
    rawLogsNextToken,
    selectedRawLogKey,
    rawLogPreview,
    rawLogSearchResult,
    sessions,
    sessionFilter,
    setSessionFilter,
    agentSessionId,
    setAgentSessionId,
    agentEvents,
    agentFiles,
    agentResult,
    agentSelectedFiles,
    agentStreamActive,
    setAgentSelectedFiles,
    agentUploadForm,
    setAgentUploadForm,
    streamStatus,
    agentForm,
    setAgentForm,
    agentMessage,
    setAgentMessage,
    currentSession,
    // actions
    refreshHealth,
    refreshWorkCenter,
    refreshAutomation,
    refreshFiles,
    refreshChangeRequests,
    refreshSkills,
    createSkill,
    updateSkill,
    setSkillStatus,
    deleteSkill,
    loadSkillContent,
    previewSkills,
    saveAgentSkillExclusions,
    refreshSessions,
    ensureConfigBootstrap,
    loadConfigVersions,
    previewKpi,
    scheduleKpiPreview,
    loadPricing,
    savePricing,
    reseedPricing,
    loadDiscounts,
    saveDiscounts,
    reseedDiscounts,
    downloadArtifact,
    downloadFile,
    resolveFileUrl,
    previewFile,
    clearFilePreview,
    pollJob,
    loadAgentHistory,
    loadAgentResult,
    loadJob,
    createBillingRun,
    runCurrentJob,
    runJobFromCenter,
    runNextQueuedJob,
    uploadSelectedFiles,
    referenceFilesToAgent,
    referenceBillDocumentToAgent,
    createAgentSession,
    uploadAgentFiles,
    startAgentStream,
    sendAndStream,
    pauseAgentSession,
    resumeAgentSession,
    selectSession,
    pauseSession,
    resumeSession,
    favoriteSession,
    startNewAgentTask,
    previewRawLog,
    loadRawLogsObjects,
    openRawLogPrefix,
    searchRawLogs,
    runSchedule,
    retryScheduleRun,
    publishBillDocument,
    applyChangeRequest,
    ignoreChangeRequest,
    saveChangeRequestExperience,
    rerunBillForChangeRequest,
  };
}

export type WorkbenchState = ReturnType<typeof useWorkbench>;
