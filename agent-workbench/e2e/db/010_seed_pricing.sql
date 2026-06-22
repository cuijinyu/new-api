INSERT INTO pricing_rules (
  id, model_pattern, channel_id, vendor, input_price, output_price, priority
) VALUES
  ('price-claude-sonnet-ch65', 'claude-3-5-sonnet*', 65, '1001AI', 3.00000000, 15.00000000, 10),
  ('price-claude-haiku-ch65', 'claude-3-5-haiku*', 65, '1001AI', 0.80000000, 4.00000000, 20),
  ('price-gpt4o-ch65', 'gpt-4o*', 65, '1001AI', 2.50000000, 10.00000000, 30)
ON CONFLICT (id) DO NOTHING;

INSERT INTO billing_config_versions (
  id, version, status, pricing_snapshot_s3_uri, discounts_snapshot_s3_uri, checksum, created_by
) VALUES (
  'cfg-local-v0',
  'local-v0',
  'active',
  's3://agent-workbench/config/local-v0/pricing.json',
  's3://agent-workbench/config/local-v0/discounts.json',
  'sha256:e2e-local-v0',
  'e2e-seed'
) ON CONFLICT (id) DO NOTHING;
