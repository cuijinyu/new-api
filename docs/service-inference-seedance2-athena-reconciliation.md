# Service Inference Seedance 2.0 Athena Reconciliation

## Conclusion

The S3 usage log payload is sufficient for two-stage Seedance billing after the
runtime changes:

- preconsume is written as `type = 2` with positive `quota`;
- final refund or negative adjustment is written as `type = 6` with negative
  `quota`;
- positive supplements remain `type = 2`;
- `other` carries `provider = service-inference`, `billing_event`,
  `task_id`, `total_tokens`, `duration_seconds`, `price_or_ratio`,
  `preconsumed_quota`, `actual_quota`, and `quota_delta`.

For balance-ledger reconciliation, Athena can sum `quota` across both consume
and refund rows. For the real 480p no-reference E2E task:

```text
preconsume quota = 168000
refund quota     = -25922
final quota      = 142078
final USD        = 142078 / 500000 = $0.284156
```

For postpaid customer invoicing, do not invoice the balance rows directly. Use
the settlement row's `other.actual_quota` as the final billable quota and ignore
the preconsume row.

If a balance-ledger report keeps only `type = 2`, it will incorrectly show
`$0.336000` instead of `$0.284156` for this task.

## Required Athena Table Migration

`usage_log_s3.go` now writes a JSON `type` field. Existing Athena tables should
expose it:

```sql
ALTER TABLE ezmodel_logs.usage_logs
ADD COLUMNS (
  `type` int COMMENT 'log type: 2=consume, 6=refund/settlement adjustment'
);
```

Athena JSON SerDe tolerates the extra field before the column exists, but the
column is required for audits and type-aware reconciliation.

## Query And Report Rules

- Revenue/customer billing uses postpaid billable quota:
  - Seedance settlement rows: `other.actual_quota`.
  - Seedance non-settlement rows: `0`.
  - Other rows: `quota`.
- Do not filter to `type = 2` for task/video billing.
- Postpaid customer bills should count one logical request per `request_id`;
  two-stage rows must not double-count calls.
- Customer-facing detail exports should collapse rows sharing the same
  `request_id` into one final line item. Internal audit exports may keep raw
  preconsume/refund rows.
- For task-level crosscheck, collapse duplicate local rows by `request_id` or
  upstream `task_id` before comparing with vendor rows.
- For Seedance recalc reports, use the Service Inference settlement metadata to
  independently recompute the settlement delta. Do not apply text-model
  prompt/output token pricing.
- When Service Inference exports vendor rows by `task_id`, map that to our
  `other.task_id` (`upstream_task_id` in Athena detail queries).

## Recalculation Engine

`scripts/athena/pricing_engine.py` has a provider-specific Seedance branch for
rows with:

```text
provider = service-inference
billing_event = video_task_settlement
model_name contains seedance
```

The branch recomputes the final task quota from the persisted settlement
snapshot:

```text
expected_actual_quota =
  int(price_or_ratio * (total_tokens * unit_scale) * group_ratio * 500000)

expected_delta_quota = expected_actual_quota - preconsumed_quota
expected_usd = expected_delta_quota / 500000
```

`unit_scale` is read from the log instead of hardcoding `1e-6`, because the Go
runtime persists the effective float scale used during settlement. This avoids
one-quota drift on boundary cases.

For the verified E2E task:

```text
expected_actual_quota = int(7.00 * (40594 * 0.0000009999999974752427) * 1 * 500000)
                      = 142078
expected_delta_quota  = 142078 - 168000
                      = -25922
```

The recalc output also includes diagnostic columns:

- `seedance_expected_actual_quota`
- `seedance_expected_delta_quota`
- `seedance_logged_actual_quota`
- `seedance_logged_quota_delta`
- `seedance_actual_quota_diff`
- `seedance_delta_quota_diff`
- `recalc_source = service_inference_seedance`

## Postpaid Billing Presentation

For postpaid user billing, balance movements are not the invoice surface. The
invoice surface should show the final logical task:

```text
raw accounting rows:
  preconsume  +168000 quota
  settlement   -25922 quota

customer bill line:
  final        142078 quota
```

The Athena query helpers now use logical call counting:

```sql
COUNT(DISTINCT CASE
  WHEN request_id IS NOT NULL AND request_id <> '' THEN request_id
  ELSE ...
END) AS call_count
```

This keeps task call counts at 1. Amounts use postpaid billable quota rather
than raw `SUM(quota)`, so a task that crosses a day or month boundary is billed
in the settlement period at its final `actual_quota`.

Customer-facing detail exports call `collapse_postpaid_detail_rows`, which
uses Seedance settlement `actual_quota`, drops preconsume balance rows, sums
money/token fields for duplicate `request_id` rows, and keeps one line item.
Internal detail exports still keep raw rows for audit and debugging.

## Patched Code Paths

- `scripts/athena/export_db_bill.py`: includes `type IN (2, 6)` instead of only
  `type = 2`.
- `scripts/athena/queries.py`: detail queries expose `type` and
  `upstream_task_id`.
- `scripts/athena/cost_import.py`: treats `task_id` and `upstream_task_id` as
  request-id aliases for vendor imports.
- `scripts/athena/report_builder.py`: row-level crosscheck can match vendor
  `task_id` against our `upstream_task_id`; customer-facing detail exports
  collapse two-stage task rows into one postpaid bill line.
- `scripts/athena/pricing_engine.py`: collapses duplicate request rows and
  independently recalculates Service Inference Seedance settlement deltas from
  `total_tokens`, `unit_scale`, `price_or_ratio`, `group_ratio`, and
  `preconsumed_quota`; exposes `collapse_postpaid_detail_rows` for invoice
  presentation.
- `scripts/athena/queries.py`: bill summary amounts use postpaid billable quota,
  and call counts use logical `request_id` distinct counting instead of raw row
  counts.
