# Local Docker Checks

## Core Commands

Run from `E:\new-api` unless a different working directory is shown.

```powershell
python -m py_compile .\agent-workbench\app\main.py .\agent-workbench\e2e\run_e2e.py
```

```powershell
cd .\agent-workbench\web
cmd /c npm run build
```

```powershell
cd .\agent-workbench
cmd /c docker compose -f docker-compose.e2e.yml up -d --build
cmd /c docker compose -f docker-compose.e2e.yml ps
```

```powershell
cd E:\new-api
python .\agent-workbench\e2e\run_e2e.py
```

## Health Checks

```powershell
Invoke-RestMethod -Uri http://localhost:18088/api/health | ConvertTo-Json -Depth 6
```

Expected:

- `ok: true`
- database available
- artifact store available

## Agent Upload Context Check

Use this when validating that Agent page uploads enter the current session context.

```powershell
$sessionPayload = @{
  prompt='请核验上传资料'
  provider='claude_code'
  runtime='codingplan'
  model='glm-5.2'
  metadata=@{ source='agent-upload-check' }
} | ConvertTo-Json -Depth 6
$session = Invoke-RestMethod -Method Post -Uri http://localhost:18088/api/agent/sessions -ContentType 'application/json' -Body $sessionPayload

$content = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("vendor,total`n1001AI,123.45"))
$uploadPayload = @{
  filename='supplier-check.csv'
  content_type='text/csv'
  content_base64=$content
  category='supplier-bill'
  session_id=$session.session_id
  uploaded_by='codex-check'
  metadata=@{ source='agent-page'; usage='agent-reconcile-context' }
} | ConvertTo-Json -Depth 8
Invoke-RestMethod -Method Post -Uri http://localhost:18088/api/files/upload -ContentType 'application/json' -Body $uploadPayload | Out-Null

$history = Invoke-RestMethod -Uri "http://localhost:18088/api/agent/sessions/$($session.session_id)/history"
@{
  session_id=$session.session_id
  files=$history.files.Count
  upload_events=($history.events | Where-Object { $_.payload.source -eq 'agent-page' }).Count
} | ConvertTo-Json
```

Passing result:

- `files` is at least `1`
- `upload_events` is at least `1`

## Billing Command Artifact Check

Use when validating Athena billing command generation.

```powershell
$payload = @{
  month='2026-05'
  channel_id=65
  vendor='1001AI-Claude'
  config_version='local-v0'
  created_by='codex-check'
  metadata=@{
    athena_command='bill'
    original_interaction='scripts/athena/bill_cli.py bill'
    currency='CNY'
    exchange_rate=7.31
    flat_tier=$true
    flat_tier_since='2026-05-01'
    end_day='2026-05-31'
    detail=$true
    customer_view=$true
    upload_to_athena_s3=$true
    no_cache=$true
  }
} | ConvertTo-Json -Depth 8
$job = Invoke-RestMethod -Method Post -Uri http://localhost:18088/api/jobs/billing-run -ContentType 'application/json' -Body $payload
Invoke-RestMethod -Method Post -Uri "http://localhost:18088/api/jobs/$($job.job_id)/run" | Out-Null
Invoke-RestMethod -Uri "http://localhost:18088/api/jobs/$($job.job_id)/artifacts" | ConvertTo-Json -Depth 8
```

Passing result:

- job status is completed
- artifacts include `command`
- command JSON includes expected `argv` options

## Browser Checks

Use a cache-busting URL after rebuild:

- `http://localhost:18089/?verify=<timestamp>#billing`
- `http://localhost:18089/?verify=<timestamp>#agent`
- `http://localhost:18089/?verify=<timestamp>#files`

For Agent upload UI, confirm visible text:

- `对账资料`
- `上传并加入会话`
- `自动进入当前 Agent 会话上下文`

## Common Problems

- **Stale UI:** rebuild compose and reload with a new query string.
- **API not healthy:** check `docker logs --tail 80 agent-workbench-api`.
- **MinIO missing objects:** ensure `agent-workbench-minio-init` exited successfully and API env uses the expected bucket.
- **PowerShell Chinese text appears garbled:** verify semantic JSON fields such as `payload.source`, `file_id`, and counts instead of matching Chinese console output.
