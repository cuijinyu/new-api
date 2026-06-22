CREATE TABLE IF NOT EXISTS workbench_jobs (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  status TEXT NOT NULL,
  month TEXT,
  channel_id INTEGER,
  vendor TEXT,
  s3_prefix TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS billing_config_versions (
  id TEXT PRIMARY KEY,
  version TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL,
  pricing_snapshot_s3_uri TEXT,
  discounts_snapshot_s3_uri TEXT,
  checksum TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pricing_rules (
  id TEXT PRIMARY KEY,
  model_pattern TEXT NOT NULL,
  channel_id INTEGER,
  vendor TEXT,
  input_price NUMERIC(18, 8) NOT NULL,
  output_price NUMERIC(18, 8) NOT NULL,
  unit TEXT NOT NULL DEFAULT '1M tokens',
  currency TEXT NOT NULL DEFAULT 'USD',
  priority INTEGER NOT NULL DEFAULT 100,
  status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS discount_rules (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  scope_type TEXT NOT NULL,
  vendor TEXT,
  channel_id INTEGER,
  model_pattern TEXT,
  discount_type TEXT NOT NULL,
  discount_value_json JSONB NOT NULL,
  priority INTEGER NOT NULL DEFAULT 100,
  status TEXT NOT NULL DEFAULT 'active',
  reason TEXT
);

CREATE TABLE IF NOT EXISTS billing_config_change_requests (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  status TEXT NOT NULL,
  proposed_by TEXT NOT NULL,
  job_id TEXT,
  reason TEXT NOT NULL,
  change_payload_json JSONB NOT NULL,
  impact_summary_json JSONB,
  reviewer TEXT,
  review_comment TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_at TIMESTAMPTZ,
  applied_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS skills_registry (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  vendor TEXT,
  version TEXT NOT NULL,
  s3_prefix TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_from_job TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
