export type JsonObject = Record<string, unknown>;

// 主流程一级导航 + 二级"更多"入口（资料库 / 日志检索）。
export type PageId =
  | "overview"
  | "billing"
  | "pricing"
  | "discounts"
  | "automation"
  | "bills"
  | "agent"
  | "governance"
  | "files"
  | "rawlogs";

export type ActionName =
  | "health"
  | "billing"
  | "automation"
  | "run"
  | "job"
  | "jobs"
  | "queue"
  | "upload"
  | "rawlogs"
  | "rawlogPreview"
  | "rawlogSearch"
  | "agent"
  | "agentStream"
  | "agentMessage"
  | "agentResult"
  | "agentPause"
  | "agentResume"
  | "sessionFavorite"
  | "change"
  | "changeRerun"
  | "kpiPreview"
  | "download"
  | "pricing"
  | "discounts"
  | "config"
  | "skills"
  | "skillPreview";

export type Health = {
  ok?: boolean;
  db?: boolean;
  artifact_store?: string;
};

export type JobDetail = {
  job?: JsonObject;
  billing_run?: JsonObject | null;
  change_requests?: JsonObject[];
};

export type JobArtifacts = {
  artifacts?: Record<string, string>;
  listed?: string[];
  s3_prefix?: string;
  billing_prefix?: string;
};

export type JobSummary = {
  id: string;
  type?: string;
  status?: string;
  created_by?: string;
  created_at?: string;
  started_at?: string;
  finished_at?: string;
  month?: string;
  channel_id?: number;
  vendor?: string;
  billing_run_id?: string;
  bill_type?: string;
  target_type?: string;
  target_id?: string;
  error_message?: string;
  result?: JsonObject;
  request_payload?: JsonObject;
};

export type JobQueue = {
  counts?: { queued?: number; running?: number };
  families?: Record<string, { queued?: number; running?: number }>;
  items?: JobSummary[];
};

export type Schedule = {
  id: string;
  name?: string;
  schedule_type?: string;
  cron_expr?: string;
  timezone?: string;
  enabled?: boolean;
  next_run_at?: string;
  last_run_at?: string;
  payload?: JsonObject;
};

export type ScheduleRun = {
  id: string;
  schedule_id?: string;
  schedule_name?: string;
  schedule_type?: string;
  status?: string;
  period?: string;
  created_at?: string;
  finished_at?: string;
  summary?: JsonObject;
};

export type BillingBatch = {
  id: string;
  schedule_run_id?: string;
  month?: string;
  status?: string;
  config_version_id?: string;
  fact_manifest_id?: string;
  created_at?: string;
  finished_at?: string;
  summary?: JsonObject;
};

// 账单文档单一状态流：GENERATED -> DELIVERED（/publish 直接生效，无 approve 前置）。
export type BillDocument = {
  id: string;
  schedule_run_id?: string;
  batch_id?: string;
  bill_type?: string;
  target_type?: string;
  target_id?: string;
  month?: string;
  status?: string;
  s3_uri?: string;
  job_id?: string;
  billing_run_id?: string;
  created_at?: string;
  updated_at?: string;
  delivered_by?: string;
  published_by?: string;
  summary?: JsonObject;
};

// session 对象新增 title / tags[] / favorite（历史经验搜索/筛选/收藏）。
export type AgentSession = {
  id: string;
  provider?: string;
  runtime?: string;
  status?: string;
  prompt?: string;
  title?: string;
  tags?: string[];
  favorite?: boolean;
  vendor?: string;
  month?: string;
  created_at?: string;
  updated_at?: string;
  metadata?: JsonObject;
};

export type AgentEvent = {
  id?: string;
  seq?: number;
  event_type?: string;
  role?: string;
  content?: string;
  created_at?: string;
  payload?: JsonObject;
};

// result.json 真实结论结构（差异原因/影响金额/建议动作/可保存经验/结果文件）。
export type AgentResultImpact = {
  amount_usd_delta?: number;
  amount_cny_delta?: number;
  currency?: string;
  [key: string]: unknown;
};

export type AgentResult = {
  status?: string;
  summary?: string;
  reason?: string;
  suggestion_ready?: boolean;
  impact?: AgentResultImpact;
  recommended_next_job?: JsonObject | string | null;
  recommended_actions?: string[];
  saveable_experience?: string;
  result_files?: Array<{ label?: string; uri?: string; role?: string }>;
  change_request_id?: string;
  [key: string]: unknown;
};

export type UploadedFile = {
  id: string;
  filename: string;
  category?: string;
  byte_size?: number;
  sha256?: string;
  s3_uri?: string;
  job_id?: string;
  session_id?: string;
  created_at?: string;
  metadata?: JsonObject;
};

export type FilePreviewSheet = {
  name: string;
  columns: string[];
  rows: string[][];
  truncated?: boolean;
};

export type FilePreview =
  | {
      kind: "text";
      file_id?: string;
      filename?: string;
      content_type?: string;
      byte_size?: number;
      s3_uri?: string;
      text: string;
      truncated?: boolean;
    }
  | {
      kind: "json";
      file_id?: string;
      filename?: string;
      content_type?: string;
      byte_size?: number;
      s3_uri?: string;
      data: unknown;
      truncated?: boolean;
    }
  | {
      kind: "csv" | "sheet";
      file_id?: string;
      filename?: string;
      content_type?: string;
      byte_size?: number;
      s3_uri?: string;
      columns?: string[];
      rows?: string[][];
      sheets?: FilePreviewSheet[];
      truncated?: boolean;
    }
  | {
      kind: "image" | "pdf";
      file_id?: string;
      filename?: string;
      content_type?: string;
      byte_size?: number;
      s3_uri?: string;
      url: string;
    }
  | {
      kind: "binary";
      file_id?: string;
      filename?: string;
      content_type?: string;
      byte_size?: number;
      s3_uri?: string;
      download_url?: string;
      message?: string;
    };

export type RawLogsConfig = {
  bucket: string;
  prefix: string;
  uri_template?: string;
  max_preview_bytes?: number;
  max_search_objects?: number;
};

export type RawLogObject = {
  key: string;
  filename?: string;
  uri?: string;
  size?: number;
  last_modified?: string;
  etag?: string;
  storage_class?: string;
};

export type RawLogsList = {
  bucket: string;
  prefix: string;
  recursive?: boolean;
  common_prefixes?: string[];
  items?: RawLogObject[];
  next_token?: string;
};

export type RawLogPreview = {
  bucket: string;
  key: string;
  uri?: string;
  text?: string;
  rows?: JsonObject[];
  columns?: string[];
  parse_errors?: number;
  decoded_bytes?: number;
  object_size?: number;
  content_type?: string;
  compression?: string;
  truncated?: boolean;
};

export type RawLogSearchMatch = {
  key: string;
  uri?: string;
  line?: number;
  snippet?: string;
  size?: number;
  last_modified?: string;
  truncated_object?: boolean;
};

export type RawLogSearchResult = {
  bucket: string;
  prefix: string;
  query: string;
  scanned_objects?: number;
  matches?: RawLogSearchMatch[];
  truncated?: boolean;
};

export type RawLogsForm = {
  bucket: string;
  prefix: string;
  year: string;
  month: string;
  day: string;
  hour: string;
  query: string;
  recursive: boolean;
};

// config_change_requests 状态：open（不再是 pending_review）。
// 响应含 before/after 配置 diff、impact 金额、证据文件链接。
export type ChangeRequest = {
  id: string;
  type?: string;
  status?: string;
  proposed_by?: string;
  job_id?: string;
  session_id?: string;
  reason?: string;
  vendor?: string;
  month?: string;
  created_at?: string;
  processed_by?: string;
  processed_at?: string;
  change_payload?: JsonObject;
  before_config?: JsonObject;
  after_config?: JsonObject;
  impact?: AgentResultImpact;
  impact_summary_json?: JsonObject;
  evidence_files?: UploadedFile[];
};

export type BillingForm = {
  month: string;
  bill_type: "customer_invoice" | "internal_customer_bill" | "channel_cost_bill" | "daily_channel_cost_snapshot";
  scope: "all" | "channel" | "user";
  channel_id: string;
  user_id: string;
  vendor: string;
  config_version: string;
  created_by: string;
  currency: "USD" | "CNY";
  exchange_rate: string;
  flat_tier: boolean;
  flat_tier_since: string;
  end_day: string;
  detail: boolean;
  customer_view: boolean;
  upload_to_athena_s3: boolean;
  no_cache: boolean;
  output_dir: string;
  extra_metadata: string;
};

export type AgentUploadForm = {
  category: string;
  job_id: string;
  uploaded_by: string;
};

export type FileForm = {
  category: string;
  job_id: string;
  session_id: string;
  uploaded_by: string;
};

export type AgentForm = {
  prompt: string;
  provider: string;
  runtime: string;
  model: string;
  live: boolean;
};

export type SessionFilter = {
  q: string;
  status: string;
  favorite: boolean;
};

export type LastAction = { label: string; ok: boolean; detail: unknown } | null;

export type BillingFormErrors = Partial<
  Record<"month" | "channel_id" | "user_id" | "exchange_rate" | "config_version" | "extra_metadata", string>
>;
export type BillingStage = "draft" | "created" | "queued" | "running" | "completed" | "failed";
export type BillingArtifactItem = { role: string; label: string; uri: string };
export type BillingArtifactGroup = { id: string; title: string; description: string; items: BillingArtifactItem[] };

// 即时 KPI 预览（同步秒级，对标 Streamlit 选月份即出数）。
export type KpiPreview = {
  total_usd?: number;
  total_calls?: number;
  unique_users?: number;
  unique_models?: number;
  total_input_tokens?: number;
  total_output_tokens?: number;
  [key: string]: unknown;
};

// 价格方案版本（config_version=价格表+折扣的一份快照）。
export type ConfigVersion = {
  id: string;
  version: string;
  status?: string;
  created_by?: string;
  created_at?: string;
  activated_at?: string;
  checksum?: string;
};

// 折扣行：渠道成本折扣 / 客户收入折扣，展开为 对象 × 模型 × 折扣率 行。
export type CostDiscountRow = {
  channel_id: string;
  channel_name?: string;
  model: string;
  discount: number | string;
};

export type RevenueDiscountRow = {
  user_id: string;
  user_name?: string;
  model: string;
  discount: number | string;
};

export type DiscountsResponse = {
  version?: string | ConfigVersion;
  config_version_id?: string;
  cost_rows?: CostDiscountRow[];
  revenue_rows?: RevenueDiscountRow[];
};

export type PricingRow = {
  model: string;
  type: "flat" | "tiered" | "multimodal" | string;
  flat_tier?: boolean | string;
  tier_index?: number | string | null;
  min_k?: number | string | null;
  max_k?: number | string | null;
  ip?: number | string | null;
  op?: number | string | null;
  chp?: number | string | null;
  cwp?: number | string | null;
  cwp_1h?: number | string | null;
  op_text?: number | string | null;
  op_image?: number | string | null;
  note?: string | null;
};

export type PricingResponse = {
  version?: string | ConfigVersion;
  config_version_id?: string;
  metadata?: {
    version?: string;
    updated_at?: string;
    models?: number;
  };
  rows?: PricingRow[];
};

// 经验/技能知识库：经验 = Skills（手动录入、Agent 沉淀、模板都进 skills 表）。
// manifest 内含 applies_to（{bill_type:[], keywords:[]}）、source、uris 等元信息。
export type Skill = {
  id: string;
  category?: string;
  name: string;
  version?: string;
  vendor?: string;
  status?: string; // active | disabled
  tags?: string[];
  manifest?: JsonObject;
  s3_prefix?: string;
  created_from_job?: string;
  created_at?: string;
};

export type SkillContent = Skill & { content?: string };

// preview：在给定会话上下文下会被注入的技能（含相关性分数，按分数倒序）。
export type SkillPreviewItem = {
  id: string;
  name: string;
  category?: string;
  version?: string;
  vendor?: string;
  tags?: string[];
  score?: number;
  path?: string;
};

// 新建/编辑经验表单（tags / bill_type / keywords 在表单里用逗号分隔的字符串）。
export type SkillForm = {
  name: string;
  category: string;
  vendor: string;
  tags: string;
  bill_type: string;
  keywords: string;
  content: string;
};
