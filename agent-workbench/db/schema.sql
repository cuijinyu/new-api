-- Agent Workbench 的独立业务库，不复用 new-api 主库。
-- 这里保存账单配置版本、任务状态、处理建议和沉淀后的经验资产。

-- 每次出账都绑定一个不可变配置版本，避免 pricing/discounts 调整后无法复盘历史账单。
CREATE TABLE IF NOT EXISTS billing_config_versions (
    id TEXT PRIMARY KEY,
    version TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    pricing_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    discounts_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    pricing_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    discounts_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    pricing_snapshot_s3_uri TEXT,
    discounts_snapshot_s3_uri TEXT,
    manifest_s3_uri TEXT,
    source_change_request_id TEXT,
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_by TEXT,
    activated_at TIMESTAMPTZ,
    checksum TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- 统一任务表：账单、供应商对账、Agent 对话、经验沉淀都先落在这里。
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL DEFAULT 'CREATED',
    created_by TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    month TEXT,
    channel_id INTEGER,
    vendor TEXT,
    bill_type TEXT NOT NULL DEFAULT 'internal_customer_bill',
    target_type TEXT NOT NULL DEFAULT 'all',
    target_id TEXT,
    s3_prefix TEXT,
    sandbox_id TEXT,
    billing_run_id TEXT,
    request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT
);

-- 账单执行记录，和 Athena Billing Worker 的一次出账结果一一对应。
CREATE TABLE IF NOT EXISTS billing_runs (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    month TEXT NOT NULL,
    channel_id INTEGER,
    vendor TEXT,
    bill_type TEXT NOT NULL DEFAULT 'internal_customer_bill',
    target_type TEXT NOT NULL DEFAULT 'all',
    target_id TEXT,
    config_version_id TEXT REFERENCES billing_config_versions(id),
    status TEXT NOT NULL DEFAULT 'CREATED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    artifacts JSONB NOT NULL DEFAULT '{}'::jsonb,
    s3_prefix TEXT
);

CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    schedule_type TEXT NOT NULL,
    cron_expr TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Hong_Kong',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    next_run_at TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ,
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS schedule_runs (
    id TEXT PRIMARY KEY,
    schedule_id TEXT REFERENCES schedules(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'CREATED',
    period TEXT NOT NULL,
    period_start DATE,
    period_end DATE,
    idempotency_key TEXT NOT NULL,
    config_version_id TEXT REFERENCES billing_config_versions(id),
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    UNIQUE (idempotency_key)
);

CREATE TABLE IF NOT EXISTS billing_batches (
    id TEXT PRIMARY KEY,
    schedule_run_id TEXT REFERENCES schedule_runs(id) ON DELETE SET NULL,
    month TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'CREATED',
    config_version_id TEXT REFERENCES billing_config_versions(id),
    fact_manifest_id TEXT,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS billing_fact_manifests (
    id TEXT PRIMARY KEY,
    batch_id TEXT REFERENCES billing_batches(id) ON DELETE CASCADE,
    month TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'CREATED',
    config_version_id TEXT REFERENCES billing_config_versions(id),
    s3_uri TEXT NOT NULL,
    row_count BIGINT NOT NULL DEFAULT 0,
    scanned_bytes BIGINT NOT NULL DEFAULT 0,
    query_cost_usd NUMERIC(18, 8) NOT NULL DEFAULT 0,
    manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bill_documents (
    id TEXT PRIMARY KEY,
    batch_id TEXT REFERENCES billing_batches(id) ON DELETE SET NULL,
    schedule_run_id TEXT REFERENCES schedule_runs(id) ON DELETE SET NULL,
    job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
    billing_run_id TEXT REFERENCES billing_runs(id) ON DELETE SET NULL,
    bill_type TEXT NOT NULL,
    target_type TEXT NOT NULL DEFAULT 'all',
    target_id TEXT,
    month TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    s3_uri TEXT,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    published_by TEXT,
    published_at TIMESTAMPTZ,
    UNIQUE (idempotency_key)
);

CREATE TABLE IF NOT EXISTS bill_publish_records (
    id TEXT PRIMARY KEY,
    bill_document_id TEXT NOT NULL REFERENCES bill_documents(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'ops',
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Agent 产出调整建议；用户选择应用后才会生成新的计费口径版本。
-- 不再做阻塞审批：状态默认 open，动作收敛为 apply/ignore/save-experience。
CREATE TABLE IF NOT EXISTS config_change_requests (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL DEFAULT 'discount',
    status TEXT NOT NULL DEFAULT 'open',
    proposed_by TEXT NOT NULL DEFAULT 'user',
    job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
    reason TEXT,
    change_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    impact_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    dry_run_before_s3_uri TEXT,
    dry_run_after_s3_uri TEXT,
    patch_diff_s3_uri TEXT,
    reviewer TEXT,
    review_comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    applied_at TIMESTAMPTZ,
    generated_config_version_id TEXT REFERENCES billing_config_versions(id)
);

-- Skills 发布后的索引表；正文和 manifest 仍沉淀到 S3/MinIO。
CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    vendor TEXT NOT NULL DEFAULT '*',
    status TEXT NOT NULL DEFAULT 'active',
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    s3_prefix TEXT NOT NULL,
    created_from_job TEXT REFERENCES jobs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (category, name, version)
);

-- 任务产物索引，便于 UI 聚合展示 S3/MinIO 上的报告、diff、配置快照。
CREATE TABLE IF NOT EXISTS job_artifacts (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    s3_uri TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Agent 会话表，用于 ClaudeCode/CodingPlan 这类可交互运行时。
CREATE TABLE IF NOT EXISTS agent_sessions (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT 'claude_code',
    runtime TEXT NOT NULL DEFAULT 'codingplan',
    status TEXT NOT NULL DEFAULT 'RUNNING',
    job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
    prompt TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Agent 事件流表，UI 和 E2E 都从这里读取增量事件。
CREATE TABLE IF NOT EXISTS agent_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    seq BIGSERIAL,
    event_type TEXT NOT NULL,
    role TEXT,
    content TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 下面的 ALTER 用于本地快速迭代和未来小版本迁移，保证重复初始化不会破坏已有数据。
ALTER TABLE billing_config_versions ADD COLUMN IF NOT EXISTS pricing_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE billing_config_versions ADD COLUMN IF NOT EXISTS discounts_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE billing_config_versions ADD COLUMN IF NOT EXISTS pricing_json JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE billing_config_versions ADD COLUMN IF NOT EXISTS discounts_json JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE billing_config_versions ADD COLUMN IF NOT EXISTS manifest_s3_uri TEXT;
ALTER TABLE billing_config_versions ADD COLUMN IF NOT EXISTS source_change_request_id TEXT;
ALTER TABLE billing_config_versions ADD COLUMN IF NOT EXISTS activated_by TEXT;
ALTER TABLE billing_config_versions ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ;
ALTER TABLE billing_config_versions ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE billing_config_versions DROP CONSTRAINT IF EXISTS billing_config_versions_checksum_key;

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS created_by TEXT NOT NULL DEFAULT 'user';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS month TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS channel_id INTEGER;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS vendor TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS bill_type TEXT NOT NULL DEFAULT 'internal_customer_bill';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS target_type TEXT NOT NULL DEFAULT 'all';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS target_id TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS billing_run_id TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS request_payload JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS result JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE billing_runs ADD COLUMN IF NOT EXISTS vendor TEXT;
ALTER TABLE billing_runs ADD COLUMN IF NOT EXISTS bill_type TEXT NOT NULL DEFAULT 'internal_customer_bill';
ALTER TABLE billing_runs ADD COLUMN IF NOT EXISTS target_type TEXT NOT NULL DEFAULT 'all';
ALTER TABLE billing_runs ADD COLUMN IF NOT EXISTS target_id TEXT;
ALTER TABLE billing_runs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE billing_runs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ;
ALTER TABLE billing_runs ADD COLUMN IF NOT EXISTS summary JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE billing_runs ADD COLUMN IF NOT EXISTS artifacts JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE billing_runs ADD COLUMN IF NOT EXISTS s3_prefix TEXT;

ALTER TABLE config_change_requests ADD COLUMN IF NOT EXISTS proposed_by TEXT NOT NULL DEFAULT 'user';
ALTER TABLE config_change_requests ADD COLUMN IF NOT EXISTS dry_run_before_s3_uri TEXT;
ALTER TABLE config_change_requests ADD COLUMN IF NOT EXISTS dry_run_after_s3_uri TEXT;
ALTER TABLE config_change_requests ADD COLUMN IF NOT EXISTS generated_config_version_id TEXT REFERENCES billing_config_versions(id);
-- 建议详情新增字段：前后配置 diff、证据文件链接、来源会话。
ALTER TABLE config_change_requests ADD COLUMN IF NOT EXISTS evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE config_change_requests ADD COLUMN IF NOT EXISTS before_config_json JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE config_change_requests ADD COLUMN IF NOT EXISTS after_config_json JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE config_change_requests ADD COLUMN IF NOT EXISTS session_id TEXT;
-- 历史遗留：把旧的 pending_review 收敛为 open，去掉阻塞审批语义。
UPDATE config_change_requests SET status = 'open' WHERE status = 'pending_review';

ALTER TABLE skills ADD COLUMN IF NOT EXISTS vendor TEXT NOT NULL DEFAULT '*';
ALTER TABLE skills ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE skills ADD COLUMN IF NOT EXISTS manifest JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS uploaded_files (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    byte_size BIGINT NOT NULL DEFAULT 0,
    sha256 TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
    session_id TEXT REFERENCES agent_sessions(id) ON DELETE SET NULL,
    s3_uri TEXT NOT NULL,
    uploaded_by TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS agent_file_references (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    file_id TEXT NOT NULL REFERENCES uploaded_files(id) ON DELETE CASCADE,
    created_by TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (session_id, file_id)
);

ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'application/octet-stream';
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS byte_size BIGINT NOT NULL DEFAULT 0;
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS sha256 TEXT NOT NULL DEFAULT '';
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'general';
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL;
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS session_id TEXT REFERENCES agent_sessions(id) ON DELETE SET NULL;
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

-- 历史经验检索/收藏/打标签：会话增加标题、标签、收藏与绑定的长生命周期沙箱。
ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS favorite BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS vendor TEXT;
ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS month TEXT;
ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS sandbox_id TEXT;

-- Agent 任务执行时绑定的一次性/长生命周期沙箱，便于回收和审计。
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS sandbox_id TEXT;

CREATE TABLE IF NOT EXISTS agent_sessions (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT 'claude_code',
    runtime TEXT NOT NULL DEFAULT 'codingplan',
    status TEXT NOT NULL DEFAULT 'RUNNING',
    job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
    prompt TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    seq BIGSERIAL,
    event_type TEXT NOT NULL,
    role TEXT,
    content TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_type_created_at ON jobs(type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_billing_runs_job_id ON billing_runs(job_id);
CREATE INDEX IF NOT EXISTS idx_billing_runs_month_channel ON billing_runs(month, channel_id);
CREATE INDEX IF NOT EXISTS idx_schedules_enabled ON schedules(enabled, next_run_at);
CREATE INDEX IF NOT EXISTS idx_schedule_runs_schedule ON schedule_runs(schedule_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_billing_batches_month ON billing_batches(month, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fact_manifests_batch ON billing_fact_manifests(batch_id);
CREATE INDEX IF NOT EXISTS idx_bill_documents_lookup ON bill_documents(month, bill_type, status);
CREATE INDEX IF NOT EXISTS idx_bill_documents_job ON bill_documents(job_id);
CREATE INDEX IF NOT EXISTS idx_change_requests_status ON config_change_requests(status);
CREATE INDEX IF NOT EXISTS idx_skills_lookup ON skills(category, name, status);
CREATE INDEX IF NOT EXISTS idx_agent_events_session_seq ON agent_events(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_created_at ON uploaded_files(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_job_id ON uploaded_files(job_id);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_session_id ON uploaded_files(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_file_references_session ON agent_file_references(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_file_references_file ON agent_file_references(file_id);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_favorite ON agent_sessions(favorite, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_vendor_month ON agent_sessions(vendor, month);
