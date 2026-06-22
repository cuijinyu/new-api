---
name: verify-agent-workbench-docker
description: Validate the agent-workbench project in local Docker. Use when asked to verify, smoke-test, E2E-test, or troubleshoot agent-workbench locally with Docker Compose, including API health, Postgres/MinIO storage, billing worker flows, Agent streaming, file upload, and browser UI checks on localhost ports 18088/18089.
---

# Verify Agent Workbench Docker

Use this skill to validate `agent-workbench` from the repository root on Windows/PowerShell. Prefer the deterministic checks below before giving a human-facing pass/fail report.

## Preconditions

- Work from the repo root, normally `E:\new-api`.
- Treat secrets as sensitive. Do not print API keys or write them into files.
- Use the local compose file at `agent-workbench/docker-compose.e2e.yml`.
- Expected services:
  - API: `http://localhost:18088`
  - Web: `http://localhost:18089`
  - Postgres and MinIO are managed by the compose stack.

For command details and optional checks, read `references/local-docker-checks.md`.

## Standard Workflow

1. **Build static/frontend and Python syntax first**

   ```powershell
   python -m py_compile .\agent-workbench\app\main.py .\agent-workbench\e2e\run_e2e.py
   ```

   ```powershell
   cmd /c npm run build
   ```

   Run the npm command from `E:\new-api\agent-workbench\web`.

2. **Start or rebuild local Docker**

   ```powershell
   cmd /c docker compose -f docker-compose.e2e.yml up -d --build
   ```

   Run it from `E:\new-api\agent-workbench`. Wait until `agent-workbench-api` is healthy and `agent-workbench-web` is running.

3. **Run the canonical E2E**

   ```powershell
   python .\agent-workbench\e2e\run_e2e.py
   ```

   Passing output must include:
   - `bootstrap ok`
   - `billing_run ok`
   - `file upload ok`
   - `supplier_reconcile ok`
   - `config change approved`
   - `skill publish ok`
   - `agent stream ok`
   - `smoke flow completed`

4. **Verify focused behavior when relevant**

   For Agent upload/context work, create a session, upload a small CSV with `session_id`, then read `/api/agent/sessions/{id}/history`. Confirm:
   - `files.length >= 1`
   - an `agent_events` message exists for the uploaded file
   - the file row has `session_id`, `category`, `s3_uri`, and `metadata`

   For Athena billing work, create and run a billing job, then inspect `command.json` in MinIO or the artifact listing. Confirm `argv` contains expected `bill_cli.py bill` options.

5. **Browser verification**

   If the user asks to see or validate UI behavior, use the in-app browser skill and check `http://localhost:18089`.

   Minimum page checks:
   - `#billing`: business billing page loads, create/run controls are visible.
   - `#agent`: Agent page loads, conversation/history are visible, and the Agent upload panel appears when validating Agent context uploads.
   - `#files`: file archive remains available but is not required as a pre-step for Agent uploads.

6. **Report concisely**

   Include:
   - commands run
   - pass/fail status
   - key IDs only when useful, shortened when possible
   - browser URL checked
   - any remaining risk, especially skipped browser checks or real-provider checks

## Failure Handling

- If compose fails, inspect `docker compose -f docker-compose.e2e.yml ps` and `docker logs --tail 80 agent-workbench-api`.
- If E2E fails after schema changes, rebuild the compose stack before debugging code.
- If browser UI looks stale, rebuild compose and reload with a cache-busting query string.
- If real Agent streaming is requested, first confirm `ZHIPU_CODINGPLAN_API_KEY` is configured in the container without printing the value.
