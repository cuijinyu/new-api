# Local Seedance E2E Test

This directory contains a local end-to-end script for Service Inference
Seedance 2.0 through the Docker-started new-api service.

The script checks:

- local `/api/status`
- `POST /v1/video/generations`
- polling `/v1/video/generations/{task_id}`
- video proxy `/v1/videos/{task_id}/content`
- local Postgres `tasks` and `logs` billing fields
- Athena `pricing_engine.recalc_from_raw`
- postpaid customer detail collapse via `collapse_postpaid_detail_rows`

## Run

The script can create a real paid video generation. It will not submit unless
you explicitly confirm:

```powershell
python test\seedance_local_e2e.py --yes-run-real
```

Optional environment variables:

```powershell
$env:NEWAPI_BASE_URL = "http://localhost:3001"
$env:NEWAPI_API_KEY = "sk-..."        # optional; otherwise reads local Docker Postgres tokens table
$env:SEEDANCE_MODEL = "dreamina-seedance-2-0-260128"
$env:SEEDANCE_RESOLUTION = "480p"
$env:SEEDANCE_DURATION = "4"
$env:SEEDANCE_MAX_WAIT_SECONDS = "900"
```

If the local Docker database has no enabled tokens, create one in the local UI
first or set `NEWAPI_API_KEY`.

Docker/Postgres defaults:

```powershell
$env:NEWAPI_PG_CONTAINER = "postgres-local"
$env:NEWAPI_PG_USER = "root"
$env:NEWAPI_PG_DATABASE = "new-api"
```

Dry-run payload preview:

```powershell
python test\seedance_local_e2e.py
```

## Expected Billing Checks

For Service Inference Seedance settlement rows, the script recomputes:

```text
expected_actual_quota =
  int(price_or_ratio * (actual_usage * unit_scale) * group_ratio * 500000)

expected_delta_quota = expected_actual_quota - preconsumed_quota
```

It then verifies:

- `task.quota == other.actual_quota`
- `other.quota_delta == expected_delta_quota`
- `SUM(logs.quota) == other.actual_quota`
- Athena `diff_usd == 0`
- Athena customer postpaid detail collapses to one row with `quota = actual_quota`

Reports are written to:

```text
test/output/seedance-local-e2e-{task_id}.json
```
