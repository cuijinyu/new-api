INSERT INTO discount_rules (
  id, name, scope_type, vendor, channel_id, model_pattern, discount_type, discount_value_json, priority, reason
) VALUES
  (
    'discount-1001ai-claude-ch65-v0',
    '1001AI Claude channel 65 baseline',
    'channel',
    '1001AI',
    65,
    'claude-*',
    'multiplier',
    '{"multiplier": 0.90}'::jsonb,
    10,
    'Baseline local E2E seed before fake-agent recommendation.'
  )
ON CONFLICT (id) DO NOTHING;
