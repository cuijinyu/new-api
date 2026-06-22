INSERT INTO skills_registry (
  id, name, vendor, version, s3_prefix, status, created_from_job
) VALUES (
  'skill-1001ai-vendor-reconcile-v0',
  '1001AI Vendor Reconcile',
  '1001AI',
  'v0',
  's3://agent-workbench/skills/vendor-reconcile/1001ai/v0/',
  'active',
  'seed'
) ON CONFLICT (id) DO NOTHING;
