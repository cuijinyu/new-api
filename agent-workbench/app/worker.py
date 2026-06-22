import json
import os
import time
from typing import Any

import psycopg2.extras

from .services.core import (
    db_conn,
    env_int,
    init_schema,
    recover_interrupted_running_jobs,
    seed_default_schedules,
    utc_now,
    utc_now_iso,
)
from .services.jobs import reconcile_open_billing_batches, run_next_queued_job_once


def log_event(event: str, payload: dict[str, Any]) -> None:
    print(json.dumps({"event": event, "at": utc_now_iso(), **payload}, ensure_ascii=False, sort_keys=True), flush=True)


def main() -> None:
    worker_started_at = utc_now()
    init_schema()
    seed_default_schedules()
    family = os.getenv("WORKBENCH_WORKER_FAMILY", "billing_run").strip() or None
    poll_seconds = env_int("WORKBENCH_WORKER_POLL_SECONDS", 10, minimum=1, maximum=300)
    batch_limit = env_int("WORKBENCH_WORKER_BATCH_LIMIT", 1, minimum=1, maximum=16)
    log_event("worker_started", {"family": family or "all", "poll_seconds": poll_seconds, "batch_limit": batch_limit})
    if os.getenv("WORKBENCH_RECOVER_RUNNING_ON_STARTUP", "true").lower() not in {"0", "false", "no"}:
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                recovered = recover_interrupted_running_jobs(cur, family, worker_started_at)
        if recovered:
            log_event(
                "worker_recovered_interrupted_jobs",
                {"family": family or "all", "count": len(recovered), "job_ids": [row["id"] for row in recovered]},
            )
        with db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                reconciled = reconcile_open_billing_batches(cur)
        if reconciled:
            log_event(
                "worker_reconciled_billing_batches",
                {"family": family or "all", "count": len(reconciled), "batch_ids": [row["id"] for row in reconciled]},
            )

    while True:
        ran = 0
        blocked = False
        for _ in range(batch_limit):
            result = run_next_queued_job_once(family)
            status = str(result.get("status") or "unknown").lower()
            if status == "empty":
                break
            ran += 1
            log_event("worker_job_result", {"family": family or "all", "result": result})
            if status == "queued":
                blocked = True
                break
        time.sleep(1 if ran and not blocked else poll_seconds)


if __name__ == "__main__":
    main()
