import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import psycopg2.extras

from .services.core import db_conn, env_int, fetch_all, fetch_scalar, init_schema, seed_default_schedules, utc_now, utc_now_iso
from .routers.billing import ScheduleRunRequest, trigger_schedule_run


LOCK_NAME = "agent-workbench:scheduler"


def log_event(event: str, payload: dict[str, Any]) -> None:
    print(json.dumps({"event": event, "at": utc_now_iso(), **payload}, ensure_ascii=False, sort_keys=True), flush=True)


def cron_field_matches(field: str, value: int) -> bool:
    field = field.strip()
    if field == "*":
        return True
    return any(part.strip().isdigit() and int(part.strip()) == value for part in field.split(","))


def cron_matches(expr: str, dt: datetime) -> bool:
    parts = expr.split()
    if len(parts) != 5:
        return False
    minute, hour, day, month, weekday = parts
    cron_weekday = (dt.weekday() + 1) % 7
    return (
        cron_field_matches(minute, dt.minute)
        and cron_field_matches(hour, dt.hour)
        and cron_field_matches(day, dt.day)
        and cron_field_matches(month, dt.month)
        and cron_field_matches(weekday, cron_weekday)
    )


def next_run_after(expr: str, tz_name: str, after_utc: datetime) -> datetime:
    tz = ZoneInfo(tz_name or "UTC")
    candidate = after_utc.astimezone(tz).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60):
        if cron_matches(expr, candidate):
            return candidate.astimezone(timezone.utc)
        candidate += timedelta(minutes=1)
    raise ValueError(f"cannot find next run for cron expression: {expr}")


def scheduler_lock(cur) -> bool:
    return bool(fetch_scalar(cur, "SELECT pg_try_advisory_xact_lock(hashtext(%s)) AS acquired", (LOCK_NAME,)))


def tick() -> dict[str, Any]:
    now = utc_now()
    triggered: list[dict[str, Any]] = []
    updated = 0
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not scheduler_lock(cur):
                return {"status": "standby", "triggered": []}
            schedules = fetch_all(cur, "SELECT * FROM schedules WHERE enabled = TRUE ORDER BY created_at ASC")
            for schedule in schedules:
                next_at = schedule.get("next_run_at")
                if not next_at:
                    next_at = next_run_after(str(schedule["cron_expr"]), str(schedule["timezone"]), now - timedelta(minutes=1))
                    cur.execute("UPDATE schedules SET next_run_at = %s, updated_at = NOW() WHERE id = %s", (next_at, schedule["id"]))
                    updated += 1
                if next_at > now:
                    continue
                result = trigger_schedule_run(cur, schedule, ScheduleRunRequest(created_by="scheduler"))
                following = next_run_after(str(schedule["cron_expr"]), str(schedule["timezone"]), now)
                cur.execute(
                    "UPDATE schedules SET last_run_at = NOW(), next_run_at = %s, updated_at = NOW() WHERE id = %s",
                    (following, schedule["id"]),
                )
                triggered.append({"schedule_id": schedule["id"], "period": result["schedule_run"]["period"], "jobs": result.get("jobs", [])})
    return {"status": "ok", "updated": updated, "triggered": triggered}


def main() -> None:
    init_schema()
    seed_default_schedules()
    poll_seconds = env_int("WORKBENCH_SCHEDULER_POLL_SECONDS", 60, minimum=5, maximum=3600)
    log_event("scheduler_started", {"poll_seconds": poll_seconds})
    while True:
        try:
            result = tick()
            if result.get("triggered"):
                log_event("scheduler_tick", result)
        except Exception as exc:
            log_event("scheduler_error", {"error": str(exc)})
        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
