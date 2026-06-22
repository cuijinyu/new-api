export type ApiResult<T = unknown> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number; error: string; data?: unknown };

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;
const localApiBaseUrl =
  typeof window !== "undefined" && window.location.hostname
    ? `http://${window.location.hostname}:18088`
    : "http://localhost:18088";

// 前端默认连本地 Docker API；生产部署时通过 VITE_API_BASE_URL 注入真实网关地址。
export const API_BASE_URL = (configuredBaseUrl?.trim() || localApiBaseUrl).replace(/\/+$/, "");

function formatError(status: number, body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    return typeof detail === "string" ? detail : JSON.stringify(detail);
  }
  if (typeof body === "string" && body.trim()) {
    return body;
  }
  return fallback || `Request failed with HTTP ${status}`;
}

export async function apiRequest<T = unknown>(
  path: string,
  options: RequestInit & { bodyJson?: unknown } = {},
): Promise<ApiResult<T>> {
  // 统一包一层 ApiResult，页面层不需要在每个按钮里重复 try/catch。
  const headers = new Headers(options.headers);
  if (options.bodyJson !== undefined) {
    headers.set("Content-Type", "application/json");
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      body: options.bodyJson === undefined ? options.body : JSON.stringify(options.bodyJson),
    });

    const contentType = response.headers.get("content-type") || "";
    const body = contentType.includes("application/json") ? await response.json() : await response.text();

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        error: formatError(response.status, body, response.statusText),
        data: body,
      };
    }

    return { ok: true, status: response.status, data: body as T };
  } catch (error) {
    return {
      ok: false,
      status: 0,
      error: error instanceof Error ? error.message : "Network request failed",
    };
  }
}

// ---------------------------------------------------------------------------
// 后端 API 契约（与后端 agent 并行实现）。这里集中声明前端依赖的端点，
// 便于在契约变化时只改一处。带 [assumption] 注释的为前端先按合理命名实现的假设。
// ---------------------------------------------------------------------------

export type SessionQuery = {
  q?: string;
  status?: string;
  vendor?: string;
  month?: string;
  tag?: string;
  favorite?: boolean;
};

export function buildSessionQuery(query: SessionQuery): string {
  const params = new URLSearchParams();
  if (query.q?.trim()) params.set("q", query.q.trim());
  if (query.status?.trim() && query.status.trim() !== "all") params.set("status", query.status.trim());
  if (query.vendor?.trim()) params.set("vendor", query.vendor.trim());
  if (query.month?.trim()) params.set("month", query.month.trim());
  if (query.tag?.trim()) params.set("tag", query.tag.trim());
  if (query.favorite) params.set("favorite", "true");
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export const endpoints = {
  health: () => "/health",
  jobs: (limit = 500) => `/api/jobs?limit=${limit}`,
  jobsQueue: () => "/api/jobs/queue",
  runNextQueued: () => "/api/jobs/queue/run-next",
  billingRun: () => "/api/jobs/billing-run",
  job: (id: string) => `/api/jobs/${id}`,
  jobRun: (id: string) => `/api/jobs/${id}/run`,
  jobArtifacts: (id: string) => `/api/jobs/${id}/artifacts`,
  schedules: () => "/api/schedules",
  scheduleRun: (id: string) => `/api/schedules/${id}/run`,
  scheduleRuns: () => "/api/schedule-runs",
  retryScheduleRun: (id: string) => `/api/schedule-runs/${id}/retry-failed`,
  billingBatches: () => "/api/billing-batches",
  billDocuments: () => "/api/bill-documents",
  // 即时 KPI 预览（同步秒级）。
  kpiPreview: () => "/api/billing/kpi-preview",
  // 结果文件下载：file_id 优先，回退 uri；API 流式返回文件内容。
  billingDownload: (params: { fileId?: string; uri?: string }) => {
    const search = new URLSearchParams();
    if (params.fileId) search.set("file_id", params.fileId);
    else if (params.uri) search.set("uri", params.uri);
    return `/api/billing/download?${search.toString()}`;
  },
  // 价格方案折扣读写（默认当前生效方案）。
  pricing: (version?: string) => (version ? `/api/billing/pricing?version=${encodeURIComponent(version)}` : "/api/billing/pricing"),
  // 从 scripts/athena/pricing.json 重新导入刊例价（整体覆盖当前生效配置）。
  reseedPricing: () => "/api/billing/pricing/reseed",
  discounts: (version?: string) => (version ? `/api/billing/discounts?version=${encodeURIComponent(version)}` : "/api/billing/discounts"),
  // 从 scripts/athena/discounts.json 重新导入折扣（整体覆盖当前生效配置）。
  reseedDiscounts: () => "/api/billing/discounts/reseed",
  // 价格方案版本列表 + 缺省初始化。
  configVersions: () => "/api/config/versions",
  configBootstrap: () => "/api/config/bootstrap",
  // 单一状态流：/publish 直接生效，无 approve 前置。
  publishBillDocument: (id: string) => `/api/bill-documents/${id}/publish`,
  billDocumentReferenceFiles: (id: string) => `/api/bill-documents/${id}/reference-files`,
  files: () => "/api/files",
  fileUpload: () => "/api/files/upload",
  fileDownload: (fileId: string, inline = false) => {
    const params = new URLSearchParams();
    if (inline) params.set("disposition", "inline");
    const qs = params.toString();
    return `/api/files/${encodeURIComponent(fileId)}/download${qs ? `?${qs}` : ""}`;
  },
  filePreview: (fileId: string) => `/api/files/${encodeURIComponent(fileId)}/preview`,
  // config_change_requests：状态 open；动作 apply / ignore / save-experience。
  changeRequests: () => "/api/change-requests",
  applyChangeRequest: (id: string) => `/api/change-requests/${id}/apply`,
  ignoreChangeRequest: (id: string) => `/api/change-requests/${id}/ignore`,
  saveChangeRequestExperience: (id: string) => `/api/change-requests/${id}/save-experience`,
  // [assumption] 一键重新生成账单：创建 billing_rerun_after_suggestion job。
  rerunBillForChangeRequest: (id: string) => `/api/change-requests/${id}/rerun-bill`,
  // agent 会话：列表支持 q,status,favorite 查询参数；vendor/month/tag 仅保留为旧入口兼容。
  sessions: (query: SessionQuery = {}) => `/api/agent/sessions${buildSessionQuery(query)}`,
  session: (id: string) => `/api/agent/sessions/${id}`,
  sessionHistory: (id: string) => `/api/agent/sessions/${id}/history`,
  sessionEvents: (id: string, afterSeq = 0) => `/api/agent/sessions/${id}/events?after_seq=${afterSeq}`,
  sessionStream: (id: string, live = false) => `/api/agent/sessions/${id}/stream?live=${live ? "true" : "false"}`,
  sessionMessages: (id: string) => `/api/agent/sessions/${id}/messages`,
  sessionFiles: (id: string) => `/api/agent/sessions/${id}/files/reference`,
  // 经验已统一为 Skills 知识库自动注入；会话仅记录需排除的技能 id。
  sessionSkillExclusions: (id: string) => `/api/agent/sessions/${id}/skill-exclusions`,
  // 经验/技能知识库 CRUD（经验 = Skills）。
  skills: () => "/api/skills",
  skill: (id: string) => `/api/skills/${encodeURIComponent(id)}`,
  skillsPreview: (params: { vendor?: string; bill_type?: string; month?: string; excluded?: string[] } = {}) => {
    const search = new URLSearchParams();
    if (params.vendor?.trim()) search.set("vendor", params.vendor.trim());
    if (params.bill_type?.trim()) search.set("bill_type", params.bill_type.trim());
    if (params.month?.trim()) search.set("month", params.month.trim());
    if (params.excluded?.length) search.set("excluded", params.excluded.join(","));
    const qs = search.toString();
    return `/api/skills/preview${qs ? `?${qs}` : ""}`;
  },
  sessionPause: (id: string) => `/api/agent/sessions/${id}/pause`,
  sessionResume: (id: string) => `/api/agent/sessions/${id}/resume`,
  // [assumption] 结论结果文件：返回 result.json 内容。
  sessionResult: (id: string) => `/api/agent/sessions/${id}/result`,
  // [assumption] 收藏 / 标签：以实际后端为准。
  sessionFavorite: (id: string) => `/api/agent/sessions/${id}/favorite`,
  sessionTags: (id: string) => `/api/agent/sessions/${id}/tags`,
  rawlogsConfig: () => "/api/rawlogs/config",
  rawlogsObjects: (qs: string) => `/api/rawlogs/objects?${qs}`,
  rawlogsObject: (qs: string) => `/api/rawlogs/object?${qs}`,
  rawlogsSearch: () => "/api/rawlogs/search",
};
