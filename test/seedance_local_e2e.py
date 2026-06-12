#!/usr/bin/env python3
"""
Local Seedance E2E billing check for new-api.

This script intentionally runs a real video generation only when explicitly
confirmed with --yes-run-real or NEWAPI_ALLOW_REAL_SEEDANCE=1.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ATHENA_DIR = REPO_ROOT / "scripts" / "athena"
OUTPUT_DIR = REPO_ROOT / "test" / "output"
QUOTA_TO_USD = 500_000.0


class CheckFailed(RuntimeError):
    pass


@dataclass
class HttpResult:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> dict[str, Any]:
        try:
            return json.loads(self.body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            preview = self.body[:500].decode("utf-8", errors="replace")
            raise CheckFailed(f"HTTP response is not JSON: {preview}") from exc


def log(message: str) -> None:
    print(f"[seedance-e2e] {message}", flush=True)


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if value.startswith("Bearer "):
        value = value[7:]
    if len(value) <= 12:
        return value[:3] + "***"
    return f"{value[:6]}...{value[-6:]}"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_psql_json(sql: str, container: str, user: str, database: str) -> Any:
    cmd = [
        "docker",
        "exec",
        "-i",
        container,
        "psql",
        "-U",
        user,
        "-d",
        database,
        "-At",
        "-c",
        sql,
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise CheckFailed(f"psql failed:\n{proc.stderr.strip()}")
    out = proc.stdout.strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise CheckFailed(f"psql did not return JSON: {out[:500]}") from exc


def http_request(
    method: str,
    url: str,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout: int = 30,
    read_limit: int | None = None,
) -> HttpResult:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + normalize_token(token)
    if extra_headers:
        headers.update(extra_headers)

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read(read_limit) if read_limit else resp.read()
            return HttpResult(resp.status, dict(resp.headers.items()), payload)
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        return HttpResult(exc.code, dict(exc.headers.items()), payload)
    except urllib.error.URLError as exc:
        raise CheckFailed(f"HTTP request failed: {method} {url}: {exc}") from exc


def normalize_token(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("Bearer "):
        raw = raw[7:].strip()
    if raw.startswith("sk-"):
        return raw
    return "sk-" + raw


def select_local_token(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if args.api_key:
        token = normalize_token(args.api_key)
        return token, {"source": "NEWAPI_API_KEY", "masked": mask_secret(token)}

    sql = """
SELECT COALESCE(row_to_json(t), '{}'::json)
FROM (
  SELECT id, user_id, key, name, remain_quota, unlimited_quota, used_quota, "group"
  FROM tokens
  WHERE status = 1
    AND deleted_at IS NULL
    AND (unlimited_quota = true OR remain_quota > 0)
  ORDER BY unlimited_quota DESC, remain_quota DESC, id DESC
  LIMIT 1
) t;
"""
    row = run_psql_json(sql, args.pg_container, args.pg_user, args.pg_database)
    require(row and row.get("key"), "No usable local token found. Set NEWAPI_API_KEY.")
    token = normalize_token(str(row["key"]))
    row["key"] = mask_secret(token)
    row["source"] = "local postgres tokens table"
    return token, row


def fetch_token_snapshot(token_key: str, args: argparse.Namespace) -> dict[str, Any] | None:
    clean = token_key.removeprefix("sk-")
    sql = f"""
SELECT COALESCE(row_to_json(t), 'null'::json)
FROM (
  SELECT id, user_id, name, remain_quota, unlimited_quota, used_quota, "group"
  FROM tokens
  WHERE key = {sql_literal(clean)}
  LIMIT 1
) t;
"""
    return run_psql_json(sql, args.pg_container, args.pg_user, args.pg_database)


def fetch_user_snapshot(user_id: int, args: argparse.Namespace) -> dict[str, Any] | None:
    sql = f"""
SELECT COALESCE(row_to_json(t), 'null'::json)
FROM (
  SELECT id, username, quota, used_quota, request_count, "group"
  FROM users
  WHERE id = {int(user_id)}
  LIMIT 1
) t;
"""
    return run_psql_json(sql, args.pg_container, args.pg_user, args.pg_database)


def build_seedance_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "model": args.model,
        "prompt": args.prompt,
        "duration": args.duration,
        "size": args.resolution,
        "metadata": {
            "resolution": args.resolution,
            "ratio": args.ratio,
            "generate_audio": args.generate_audio,
            "watermark": args.watermark,
        },
    }


def submit_task(args: argparse.Namespace, token: str) -> str:
    payload = build_seedance_payload(args)
    url = args.base_url.rstrip("/") + "/v1/video/generations"
    res = http_request("POST", url, token=token, body=payload, timeout=args.submit_timeout)
    require(200 <= res.status < 300, f"submit failed HTTP {res.status}: {res.body[:1000]!r}")
    data = res.json()
    task_id = data.get("task_id") or data.get("id")
    require(isinstance(task_id, str) and task_id, f"submit response missing task_id: {data}")
    log(f"submitted task_id={task_id}")
    return task_id


def poll_task(args: argparse.Namespace, token: str, task_id: str) -> dict[str, Any]:
    url = args.base_url.rstrip("/") + f"/v1/video/generations/{task_id}"
    deadline = time.time() + args.max_wait_seconds
    last_data: dict[str, Any] = {}
    while time.time() < deadline:
        res = http_request("GET", url, token=token, timeout=30)
        require(200 <= res.status < 300, f"task fetch failed HTTP {res.status}: {res.body[:1000]!r}")
        data = res.json()
        last_data = data
        task_data = data.get("data") if isinstance(data.get("data"), dict) else data
        status = str(task_data.get("status", "")).upper()
        progress = task_data.get("progress", "")
        log(f"poll task status={status or 'UNKNOWN'} progress={progress}")
        if status in {"SUCCESS", "COMPLETED", "SUCCEEDED"}:
            return task_data
        if status in {"FAILURE", "FAILED", "CANCELLED", "CANCELED"}:
            raise CheckFailed(f"task failed: {json.dumps(task_data, ensure_ascii=False)[:1500]}")
        time.sleep(args.poll_interval_seconds)
    raise CheckFailed(
        "task did not finish before timeout; last response="
        + json.dumps(last_data, ensure_ascii=False)[:1500]
    )


def fetch_video_probe(args: argparse.Namespace, token: str, task_id: str) -> dict[str, Any]:
    url = args.base_url.rstrip("/") + f"/v1/videos/{task_id}/content"
    res = http_request(
        "GET",
        url,
        token=token,
        extra_headers={"Range": "bytes=0-4095", "Accept": "video/mp4,*/*"},
        timeout=args.video_timeout,
        read_limit=4096,
    )
    require(res.status in {200, 206}, f"video proxy failed HTTP {res.status}: {res.body[:500]!r}")
    ctype = res.headers.get("Content-Type", res.headers.get("content-type", ""))
    body = res.body
    is_mp4 = b"ftyp" in body[:32] or "video/" in ctype.lower() or "octet-stream" in ctype.lower()
    require(len(body) >= 64, f"video probe too small: {len(body)} bytes")
    require(is_mp4, f"video response does not look like media: content-type={ctype}, head={body[:32]!r}")
    return {
        "http_status": res.status,
        "content_type": ctype,
        "bytes_checked": len(body),
        "has_mp4_ftyp": b"ftyp" in body[:32],
    }


def fetch_task_row(task_id: str, args: argparse.Namespace) -> dict[str, Any]:
    sql = f"""
SELECT COALESCE(row_to_json(t), 'null'::json)
FROM (
  SELECT
    id, created_at, updated_at, task_id, platform, user_id, "group",
    channel_id, quota, action, status, fail_reason, submit_time,
    start_time, finish_time, progress,
    properties::text AS properties,
    data::text AS data
  FROM tasks
  WHERE task_id = {sql_literal(task_id)}
  ORDER BY id DESC
  LIMIT 1
) t;
"""
    row = run_psql_json(sql, args.pg_container, args.pg_user, args.pg_database)
    require(row, f"task row not found for {task_id}")
    return row


def parse_json_maybe(value: Any) -> Any:
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return {}


def fetch_logs(task_id: str, request_id: str, args: argparse.Namespace) -> list[dict[str, Any]]:
    where = [f"other::text LIKE '%' || {sql_literal(task_id)} || '%'"]
    if request_id:
        where.append(f"request_id = {sql_literal(request_id)}")
    sql = f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (
  SELECT
    id, user_id, created_at, type, content, username, token_name, model_name,
    quota, prompt_tokens, completion_tokens, use_time, is_stream, channel_id,
    token_id, "group", ip, other::text AS other, request_id, upstream_request_id
  FROM logs
  WHERE ({" OR ".join(where)})
    AND (model_name ILIKE '%seedance%' OR other::text ILIKE '%seedance%')
  ORDER BY id
) t;
"""
    rows = run_psql_json(sql, args.pg_container, args.pg_user, args.pg_database)
    require(isinstance(rows, list) and rows, f"no Seedance logs found for task_id={task_id}, request_id={request_id}")
    return rows


def settlement_other(log_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    for row in log_rows:
        other = parse_json_maybe(row.get("other"))
        if other.get("billing_event") == "video_task_settlement":
            return row, other
    raise CheckFailed("settlement log with billing_event=video_task_settlement not found")


def validate_billing(
    task: dict[str, Any],
    log_rows: list[dict[str, Any]],
    before_token: dict[str, Any] | None,
    after_token: dict[str, Any] | None,
    before_user: dict[str, Any] | None,
    after_user: dict[str, Any] | None,
) -> dict[str, Any]:
    settle_row, other = settlement_other(log_rows)

    actual_usage = float(other["actual_usage"])
    unit_scale = float(other["unit_scale"])
    group_ratio = float(other["group_ratio"])
    price_or_ratio = float(other["price_or_ratio"])
    preconsumed = int(other["preconsumed_quota"])
    logged_actual = int(other["actual_quota"])
    logged_delta = int(other["quota_delta"])
    total_tokens = int(other.get("total_tokens") or settle_row.get("completion_tokens") or 0)

    expected_actual = int(price_or_ratio * (actual_usage * unit_scale) * group_ratio * QUOTA_TO_USD)
    expected_delta = expected_actual - preconsumed
    raw_quota_sum = sum(int(row.get("quota") or 0) for row in log_rows)

    require(other.get("provider") == "service-inference", f"unexpected provider: {other.get('provider')}")
    require(total_tokens > 0, "settlement total_tokens must be positive")
    require(int(task["quota"]) == logged_actual, f"task.quota={task['quota']} != logged actual_quota={logged_actual}")
    require(logged_actual == expected_actual, f"actual_quota mismatch: logged={logged_actual}, expected={expected_actual}")
    require(logged_delta == expected_delta, f"quota_delta mismatch: logged={logged_delta}, expected={expected_delta}")
    require(raw_quota_sum == logged_actual, f"sum(log.quota)={raw_quota_sum} != actual_quota={logged_actual}")

    token_delta = None
    user_delta = None
    if before_token and after_token:
        token_delta = int(after_token["used_quota"]) - int(before_token["used_quota"])
    if before_user and after_user:
        user_delta = int(after_user["used_quota"]) - int(before_user["used_quota"])

    return {
        "provider": other.get("provider"),
        "billing_event": other.get("billing_event"),
        "task_id": other.get("task_id"),
        "model_name": other.get("model_name"),
        "upstream_model_name": other.get("upstream_model_name"),
        "actual_usage": actual_usage,
        "total_tokens": total_tokens,
        "unit_scale": unit_scale,
        "group_ratio": group_ratio,
        "price_or_ratio": price_or_ratio,
        "preconsumed_quota": preconsumed,
        "actual_quota": logged_actual,
        "quota_delta": logged_delta,
        "raw_log_quota_sum": raw_quota_sum,
        "actual_usd": logged_actual / QUOTA_TO_USD,
        "expected_actual_quota": expected_actual,
        "expected_delta_quota": expected_delta,
        "token_used_quota_delta": token_delta,
        "user_used_quota_delta": user_delta,
    }


def athena_recalc(log_rows: list[dict[str, Any]]) -> dict[str, Any]:
    sys.path.insert(0, str(ATHENA_DIR))
    try:
        import pandas as pd
        import pricing_engine
    except Exception as exc:
        raise CheckFailed(f"failed to import Athena pricing engine dependencies: {exc}") from exc

    df = pd.DataFrame(log_rows)
    required_defaults = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "quota": 0,
        "other": "",
        "request_id": "",
        "user_id": 0,
        "channel_id": 0,
        "model_name": "",
        "created_at": 0,
        "type": 0,
    }
    for col, default in required_defaults.items():
        if col not in df.columns:
            df[col] = default

    recalced = pricing_engine.recalc_from_raw(df)
    seedance_rows = recalced[recalced.get("recalc_source", "").astype(str).eq("service_inference_seedance")]
    require(len(seedance_rows) == 1, f"expected one service_inference_seedance settlement row, got {len(seedance_rows)}")
    row = seedance_rows.iloc[0]
    require(abs(float(row["diff_usd"])) < 0.000001, f"Athena diff_usd is not zero: {row['diff_usd']}")
    require(float(row["seedance_actual_quota_diff"]) == 0, f"Athena actual quota diff: {row['seedance_actual_quota_diff']}")
    require(float(row["seedance_delta_quota_diff"]) == 0, f"Athena delta quota diff: {row['seedance_delta_quota_diff']}")

    customer = pricing_engine.collapse_postpaid_detail_rows(recalced)
    require(len(customer) == 1, f"customer postpaid detail should collapse to one row, got {len(customer)}")
    customer_row = customer.iloc[0]
    require(
        int(customer_row["quota"]) == int(row["seedance_logged_actual_quota"]),
        "customer postpaid quota does not equal settlement actual_quota",
    )

    return {
        "row_count_raw": int(len(recalced)),
        "row_count_customer_view": int(len(customer)),
        "recalc_source": str(row["recalc_source"]),
        "expected_usd": float(row["expected_usd"]),
        "billed_usd": float(row["billed_usd"]),
        "diff_usd": float(row["diff_usd"]),
        "seedance_expected_actual_quota": int(row["seedance_expected_actual_quota"]),
        "seedance_expected_delta_quota": int(row["seedance_expected_delta_quota"]),
        "seedance_actual_quota_diff": int(row["seedance_actual_quota_diff"]),
        "seedance_delta_quota_diff": int(row["seedance_delta_quota_diff"]),
        "customer_view_quota": int(customer_row["quota"]),
        "customer_view_billed_usd": float(customer_row["billed_usd"]),
    }


def write_report(report: dict[str, Any], task_id: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"seedance-local-e2e-{task_id}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local Seedance E2E and Athena billing checks.")
    parser.add_argument("--yes-run-real", action="store_true", help="Actually submit a real Seedance generation.")
    parser.add_argument("--base-url", default=os.getenv("NEWAPI_BASE_URL", "http://localhost:3001"))
    parser.add_argument("--api-key", default=os.getenv("NEWAPI_API_KEY", ""))
    parser.add_argument("--model", default=os.getenv("SEEDANCE_MODEL", "dreamina-seedance-2-0-260128"))
    parser.add_argument("--prompt", default=os.getenv("SEEDANCE_PROMPT", "A calm four second product video of a white ceramic mug on a wooden desk, soft morning light, subtle camera push in."))
    parser.add_argument("--duration", type=int, default=int(os.getenv("SEEDANCE_DURATION", "4")))
    parser.add_argument("--resolution", default=os.getenv("SEEDANCE_RESOLUTION", "480p"))
    parser.add_argument("--ratio", default=os.getenv("SEEDANCE_RATIO", "16:9"))
    parser.add_argument("--generate-audio", action="store_true", default=os.getenv("SEEDANCE_GENERATE_AUDIO", "").lower() in {"1", "true", "yes"})
    parser.add_argument("--watermark", action="store_true", default=os.getenv("SEEDANCE_WATERMARK", "").lower() in {"1", "true", "yes"})
    parser.add_argument("--poll-interval-seconds", type=int, default=int(os.getenv("SEEDANCE_POLL_INTERVAL_SECONDS", "15")))
    parser.add_argument("--max-wait-seconds", type=int, default=int(os.getenv("SEEDANCE_MAX_WAIT_SECONDS", "900")))
    parser.add_argument("--submit-timeout", type=int, default=int(os.getenv("SEEDANCE_SUBMIT_TIMEOUT", "90")))
    parser.add_argument("--video-timeout", type=int, default=int(os.getenv("SEEDANCE_VIDEO_TIMEOUT", "60")))
    parser.add_argument("--pg-container", default=os.getenv("NEWAPI_PG_CONTAINER", "postgres-local"))
    parser.add_argument("--pg-user", default=os.getenv("NEWAPI_PG_USER", "root"))
    parser.add_argument("--pg-database", default=os.getenv("NEWAPI_PG_DATABASE", "new-api"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    allow_real = args.yes_run_real or os.getenv("NEWAPI_ALLOW_REAL_SEEDANCE", "").lower() in {"1", "true", "yes"}
    if not allow_real:
        log("real generation is disabled; pass --yes-run-real to submit a paid Seedance task")
        log("payload preview: " + json.dumps(build_seedance_payload(args), ensure_ascii=False))
        return 0

    status = http_request("GET", args.base_url.rstrip("/") + "/api/status", timeout=20)
    require(200 <= status.status < 300, f"local new-api is not healthy: HTTP {status.status}")
    require(status.json().get("success") is True, "local new-api /api/status success is not true")

    token, token_info = select_local_token(args)
    before_token = fetch_token_snapshot(token, args)
    before_user = fetch_user_snapshot(int(before_token["user_id"]), args) if before_token else None
    log(f"using token source={token_info.get('source')} key={token_info.get('key') or token_info.get('masked')}")

    task_id = submit_task(args, token)
    task_resp = poll_task(args, token, task_id)
    video_probe = fetch_video_probe(args, token, task_id)
    task_row = fetch_task_row(task_id, args)
    task_props = parse_json_maybe(task_row.get("properties"))
    request_id = str(task_props.get("request_id") or "")
    log_rows = fetch_logs(task_id, request_id, args)

    after_token = fetch_token_snapshot(token, args)
    after_user = fetch_user_snapshot(int(task_row["user_id"]), args)
    billing = validate_billing(task_row, log_rows, before_token, after_token, before_user, after_user)
    athena = athena_recalc(log_rows)

    report = {
        "ok": True,
        "base_url": args.base_url,
        "task_id": task_id,
        "task_response": task_resp,
        "video_probe": video_probe,
        "task_row": {
            "status": task_row.get("status"),
            "progress": task_row.get("progress"),
            "quota": task_row.get("quota"),
            "channel_id": task_row.get("channel_id"),
            "user_id": task_row.get("user_id"),
            "request_id": request_id,
        },
        "billing": billing,
        "athena": athena,
        "log_ids": [row.get("id") for row in log_rows],
    }
    report_path = write_report(report, task_id)

    log(f"video ok: {video_probe}")
    log(f"billing ok: actual_quota={billing['actual_quota']} usd={billing['actual_usd']:.6f}")
    log(f"athena ok: diff_usd={athena['diff_usd']:.8f}, customer_quota={athena['customer_view_quota']}")
    log(f"report written: {report_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckFailed as exc:
        log(f"FAILED: {exc}")
        raise SystemExit(1)
