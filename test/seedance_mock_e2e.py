#!/usr/bin/env python3
"""
Mocked local Seedance E2E billing check for Docker-started new-api.

The script never calls service-inference.ai. It starts a small local HTTP
server that implements the Service Inference video contract, temporarily points
the local ServiceInferenceVideo channel at it, and verifies final settlement.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "test" / "output"
QUOTA_PER_UNIT = 500_000

MP4_STUB = (
    b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
    b"\x00\x00\x00\x08free"
    b"\x00\x00\x00\x20mdat"
    + b"\x00" * 4096
)


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
            raise CheckFailed(f"response is not JSON: {self.body[:500]!r}") from exc


def log(message: str) -> None:
    print(f"[seedance-mock-e2e] {message}", flush=True)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run(cmd: list[str], *, timeout: int = 60, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise CheckFailed(f"command failed: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return proc


def psql_json(sql: str, args: argparse.Namespace) -> Any:
    proc = run(
        [
            "docker",
            "exec",
            "-i",
            args.pg_container,
            "psql",
            "-U",
            args.pg_user,
            "-d",
            args.pg_database,
            "-At",
            "-c",
            sql,
        ],
        input_text=None,
    )
    out = proc.stdout.strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise CheckFailed(f"psql did not return JSON: {out[:1000]}") from exc


def psql_exec(sql: str, args: argparse.Namespace) -> None:
    run(
        [
            "docker",
            "exec",
            "-i",
            args.pg_container,
            "psql",
            "-U",
            args.pg_user,
            "-d",
            args.pg_database,
            "-v",
            "ON_ERROR_STOP=1",
        ],
        input_text=sql,
    )


def http_request(
    method: str,
    url: str,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    read_limit: int | None = None,
) -> HttpResult:
    data = None
    req_headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    if token:
        req_headers["Authorization"] = "Bearer " + normalize_token(token)
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read(read_limit) if read_limit else resp.read()
            return HttpResult(resp.status, dict(resp.headers.items()), payload)
    except urllib.error.HTTPError as exc:
        return HttpResult(exc.code, dict(exc.headers.items()), exc.read())
    except urllib.error.URLError as exc:
        raise CheckFailed(f"{method} {url} failed: {exc}") from exc


def normalize_token(token: str) -> str:
    token = token.strip()
    if token.startswith("Bearer "):
        token = token[7:].strip()
    return token if token.startswith("sk-") else "sk-" + token


def mask_token(token: str) -> str:
    token = normalize_token(token)
    return token[:8] + "..." + token[-6:]


class MockState:
    def __init__(self, total_tokens: int, complete_after_fetches: int) -> None:
        self.total_tokens = total_tokens
        self.complete_after_fetches = complete_after_fetches
        self.lock = threading.Lock()
        self.tasks: dict[str, dict[str, Any]] = {}
        self.next_id = 1

    def create_task(self, payload: dict[str, Any], public_base_url: str) -> dict[str, Any]:
        with self.lock:
            task_id = f"mvt-mock-{int(time.time())}-{self.next_id}"
            self.next_id += 1
            task = {
                "id": task_id,
                "status": "pending",
                "model": payload.get("model", ""),
                "duration_seconds": float(payload.get("duration") or 4),
                "outputs": [],
                "error": None,
                "created_at": "2026-06-14T00:00:00.000Z",
                "completed_at": None,
                "fetch_count": 0,
                "video_url": public_base_url.rstrip("/") + f"/mock-video/{task_id}.mp4",
            }
            self.tasks[task_id] = task
            return task.copy()

    def fetch_task(self, task_id: str) -> dict[str, Any] | None:
        with self.lock:
            task = self.tasks.get(task_id)
            if task is None:
                return None
            task["fetch_count"] += 1
            if task["fetch_count"] >= self.complete_after_fetches:
                task["status"] = "completed"
                task["completed_at"] = "2026-06-14T00:00:10.000Z"
                task["outputs"] = [task["video_url"]]
                task["usage"] = {
                    "completion_tokens": self.total_tokens,
                    "total_tokens": self.total_tokens,
                }
            public = {k: v for k, v in task.items() if k not in {"fetch_count", "video_url"}}
            return public


def make_handler(state: MockState, public_base_url: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "SeedanceMock/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            log("mock " + fmt % args)

        def send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != "/v1/video/generate":
                self.send_json(404, {"error": "not_found"})
                return
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                self.send_json(400, {"error": "invalid_json"})
                return
            task = state.create_task(payload, public_base_url)
            self.send_json(200, {"task": task})

        def do_GET(self) -> None:
            if self.path.startswith("/v1/video/tasks/"):
                task_id = self.path.rsplit("/", 1)[-1]
                task = state.fetch_task(task_id)
                if task is None:
                    self.send_json(404, {"error": "task_not_found"})
                    return
                self.send_json(200, {"task": task})
                return
            if self.path.startswith("/mock-video/"):
                rng = self.headers.get("Range", "")
                body = MP4_STUB
                status = 200
                if rng.startswith("bytes=0-"):
                    end = int(rng.split("-", 1)[1] or "4095")
                    body = MP4_STUB[: end + 1]
                    status = 206
                    self.send_response(status)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Content-Range", f"bytes 0-{len(body)-1}/{len(MP4_STUB)}")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(status)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_json(404, {"error": "not_found"})

    return Handler


def find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def start_mock(total_tokens: int, complete_after_fetches: int, host_port: int) -> tuple[ThreadingHTTPServer, str, str]:
    bind_url = f"http://127.0.0.1:{host_port}"
    docker_url = f"http://host.docker.internal:{host_port}"
    state = MockState(total_tokens, complete_after_fetches)
    server = ThreadingHTTPServer(("0.0.0.0", host_port), make_handler(state, docker_url))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            res = http_request("GET", bind_url + "/health", timeout=1)
            if res.status == 404:
                break
        except CheckFailed:
            time.sleep(0.1)
    return server, bind_url, docker_url


def restart_app(args: argparse.Namespace) -> None:
    log(f"restarting {args.app_container} to refresh channel cache")
    run(["docker", "restart", args.app_container], timeout=90)
    deadline = time.time() + 90
    url = args.base_url.rstrip("/") + "/api/status"
    while time.time() < deadline:
        try:
            res = http_request("GET", url, timeout=5)
            if 200 <= res.status < 300 and res.json().get("success") is True:
                return
        except Exception:
            pass
        time.sleep(2)
    raise CheckFailed(f"{args.app_container} did not become healthy after restart")


def channel_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    sql = f"""
SELECT COALESCE(row_to_json(t), 'null'::json)
FROM (
  SELECT id, type, name, key, base_url, status, models, "group"
  FROM channels
  WHERE id = {int(args.channel_id)}
  LIMIT 1
) t;
"""
    row = psql_json(sql, args)
    require(row, f"channel {args.channel_id} not found")
    return row


def configure_channel(args: argparse.Namespace, docker_url: str) -> None:
    models = (
        "dreamina-seedance-2-0-260128,dreamina-seedance-2-0-ep,"
        "dreamina-seedance-2-0-fast-260128,service-inference-seedance-2-0-260128,"
        "service-inference-seedance-2-0-ep,service-inference-seedance-2-0-fast-260128"
    )
    sql = f"""
UPDATE channels
SET type = 57,
    status = 1,
    key = 'mock-seedance-key',
    base_url = {sql_literal(docker_url)},
    models = {sql_literal(models)},
    "group" = 'default',
    model_mapping = ''
WHERE id = {int(args.channel_id)};
"""
    psql_exec(sql, args)


def restore_channel(args: argparse.Namespace, snapshot: dict[str, Any]) -> None:
    sql = f"""
UPDATE channels
SET type = {int(snapshot["type"])},
    status = {int(snapshot["status"])},
    key = {sql_literal(str(snapshot["key"]))},
    base_url = {sql_literal(str(snapshot.get("base_url") or ""))},
    models = {sql_literal(str(snapshot.get("models") or ""))},
    "group" = {sql_literal(str(snapshot.get("group") or "default"))}
WHERE id = {int(snapshot["id"])};
"""
    psql_exec(sql, args)


def select_token(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if args.api_key:
        token = normalize_token(args.api_key)
        return token, {"source": "argument", "masked": mask_token(token)}
    sql = """
SELECT COALESCE(row_to_json(t), 'null'::json)
FROM (
  SELECT id, user_id, name, key, remain_quota, used_quota, unlimited_quota, "group"
  FROM tokens
  WHERE status = 1 AND deleted_at IS NULL AND (unlimited_quota = true OR remain_quota > 0)
  ORDER BY id DESC
  LIMIT 1
) t;
"""
    row = psql_json(sql, args)
    require(row and row.get("key"), "no usable local token found")
    token = normalize_token(str(row["key"]).strip())
    row["key"] = mask_token(token)
    row["source"] = "postgres-local"
    return token, row


def task_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "model": args.model,
        "prompt": args.prompt,
        "duration": args.duration,
        "size": args.resolution,
        "metadata": {
            "resolution": args.resolution,
            "ratio": args.ratio,
            "generate_audio": False,
            "watermark": False,
        },
    }


def submit_and_poll(args: argparse.Namespace, token: str) -> tuple[str, dict[str, Any]]:
    submit = http_request(
        "POST",
        args.base_url.rstrip("/") + "/v1/video/generations",
        token=token,
        body=task_payload(args),
        timeout=30,
    )
    require(200 <= submit.status < 300, f"submit HTTP {submit.status}: {submit.body[:1000]!r}")
    submit_data = submit.json()
    task_id = submit_data.get("task_id") or submit_data.get("id")
    require(isinstance(task_id, str) and task_id, f"submit response missing task_id: {submit_data}")
    log(f"submitted task_id={task_id}")
    last: dict[str, Any] = {}
    deadline = time.time() + args.max_wait_seconds
    while time.time() < deadline:
        res = http_request("GET", args.base_url.rstrip("/") + f"/v1/video/generations/{task_id}", token=token, timeout=30)
        require(200 <= res.status < 300, f"fetch HTTP {res.status}: {res.body[:1000]!r}")
        data = res.json()
        last = data.get("data") if isinstance(data.get("data"), dict) else data
        status = str(last.get("status", "")).upper()
        log(f"poll status={status or 'UNKNOWN'} progress={last.get('progress')}")
        if status == "SUCCESS":
            return task_id, last
        if status == "FAILURE":
            raise CheckFailed(f"task failed: {json.dumps(last, ensure_ascii=False)[:1200]}")
        time.sleep(args.poll_interval_seconds)
    raise CheckFailed(f"task did not complete: {json.dumps(last, ensure_ascii=False)[:1200]}")


def probe_video(args: argparse.Namespace, token: str, task_id: str) -> dict[str, Any]:
    res = http_request(
        "GET",
        args.base_url.rstrip("/") + f"/v1/videos/{task_id}/content",
        token=token,
        headers={"Accept": "video/mp4,*/*", "Range": "bytes=0-4095"},
        timeout=30,
        read_limit=4096,
    )
    ctype = res.headers.get("Content-Type", res.headers.get("content-type", ""))
    require(res.status in {200, 206}, f"video HTTP {res.status}: {res.body[:300]!r}")
    require(b"ftyp" in res.body[:64], "video probe did not find mp4 ftyp header")
    return {"http_status": res.status, "content_type": ctype, "bytes_checked": len(res.body)}


def fetch_task_row(args: argparse.Namespace, task_id: str) -> dict[str, Any]:
    sql = f"""
SELECT COALESCE(row_to_json(t), 'null'::json)
FROM (
  SELECT id, task_id, user_id, channel_id, quota, status, progress, properties::text AS properties, data::text AS data
  FROM tasks
  WHERE task_id = {sql_literal(task_id)}
  LIMIT 1
) t;
"""
    row = psql_json(sql, args)
    require(row, f"task row not found for {task_id}")
    return row


def fetch_logs(args: argparse.Namespace, task_id: str, request_id: str) -> list[dict[str, Any]]:
    request_filter = "FALSE"
    if request_id:
        request_filter = f"request_id = {sql_literal(request_id)}"
    sql = f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (
  SELECT id, type, model_name, quota, completion_tokens, channel_id, token_id, request_id, content, other::text AS other
  FROM logs
  WHERE ({request_filter}
     OR other::text LIKE '%' || {sql_literal(task_id)} || '%'
     OR content LIKE '%' || {sql_literal(task_id)} || '%')
     OR (model_name ILIKE '%seedance%' AND id >= COALESCE((SELECT max(id)-20 FROM logs), 0))
  ORDER BY id
) t;
"""
    rows = psql_json(sql, args)
    require(isinstance(rows, list), "logs query did not return list")
    return rows


def parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def validate_billing(args: argparse.Namespace, task_id: str, task_row: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    settlement_row = None
    settlement_other: dict[str, Any] = {}
    for row in rows:
        other = parse_json(row.get("other"))
        if other.get("billing_event") == "video_task_settlement" and other.get("task_id") == task_id:
            settlement_row = row
            settlement_other = other
            break
    require(settlement_row is not None, "settlement log not found")

    preconsumed = int(settlement_other["preconsumed_quota"])
    actual_quota = int(settlement_other["actual_quota"])
    quota_delta = int(settlement_other["quota_delta"])
    total_tokens = int(settlement_other.get("total_tokens") or 0)
    unit_scale = float(settlement_other["unit_scale"])
    price_or_ratio = float(settlement_other["price_or_ratio"])
    actual_usage = float(settlement_other["actual_usage"])
    group_ratio = float(settlement_other["group_ratio"])

    expected_preconsume = int(args.model_price * (args.duration * 12000 / 1_000_000) * QUOTA_PER_UNIT)
    expected_actual = int(price_or_ratio * (actual_usage * unit_scale) * group_ratio * QUOTA_PER_UNIT)
    expected_delta = expected_actual - preconsumed

    require(preconsumed == expected_preconsume, f"preconsume quota {preconsumed} != expected {expected_preconsume}")
    require(total_tokens == args.total_tokens, f"total_tokens {total_tokens} != expected {args.total_tokens}")
    require(actual_quota == expected_actual, f"actual_quota {actual_quota} != expected {expected_actual}")
    require(quota_delta == expected_delta, f"quota_delta {quota_delta} != expected {expected_delta}")
    require(int(task_row["quota"]) == actual_quota, f"task quota {task_row['quota']} != actual_quota {actual_quota}")

    task_matching_rows = [
        r for r in rows
        if task_id in (r.get("content") or "")
        or task_id in (r.get("other") or "")
        or (r.get("request_id") and r.get("request_id") == settlement_row.get("request_id"))
    ]
    quota_sum = sum(int(r.get("quota") or 0) for r in task_matching_rows)
    require(quota_sum == actual_quota, f"task log quota sum {quota_sum} != actual_quota {actual_quota}")

    return {
        "preconsumed_quota": preconsumed,
        "actual_quota": actual_quota,
        "quota_delta": quota_delta,
        "total_tokens": total_tokens,
        "unit_scale": unit_scale,
        "price_or_ratio": price_or_ratio,
        "actual_usage": actual_usage,
        "usage_source": settlement_other.get("usage_source"),
        "task_log_quota_sum": quota_sum,
        "actual_usd": actual_quota / QUOTA_PER_UNIT,
        "settlement_log_id": settlement_row["id"],
    }


def write_report(report: dict[str, Any], task_id: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"seedance-mock-e2e-{task_id}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local mocked Seedance E2E without real upstream calls.")
    parser.add_argument("--base-url", default=os.getenv("NEWAPI_BASE_URL", "http://localhost:3001"))
    parser.add_argument("--api-key", default=os.getenv("NEWAPI_API_KEY", ""))
    parser.add_argument("--app-container", default=os.getenv("NEWAPI_APP_CONTAINER", "new-api-local"))
    parser.add_argument("--pg-container", default=os.getenv("NEWAPI_PG_CONTAINER", "postgres-local"))
    parser.add_argument("--pg-user", default=os.getenv("NEWAPI_PG_USER", "root"))
    parser.add_argument("--pg-database", default=os.getenv("NEWAPI_PG_DATABASE", "new-api"))
    parser.add_argument("--channel-id", type=int, default=int(os.getenv("SEEDANCE_CHANNEL_ID", "2")))
    parser.add_argument("--mock-port", type=int, default=int(os.getenv("SEEDANCE_MOCK_PORT", "0")))
    parser.add_argument("--complete-after-fetches", type=int, default=int(os.getenv("SEEDANCE_MOCK_COMPLETE_AFTER_FETCHES", "2")))
    parser.add_argument("--total-tokens", type=int, default=int(os.getenv("SEEDANCE_MOCK_TOTAL_TOKENS", "40594")))
    parser.add_argument("--model", default=os.getenv("SEEDANCE_MODEL", "dreamina-seedance-2-0-260128"))
    parser.add_argument("--model-price", type=float, default=float(os.getenv("SEEDANCE_MODEL_PRICE", "7.0")))
    parser.add_argument("--prompt", default=os.getenv("SEEDANCE_PROMPT", "A mocked four second Seedance product video."))
    parser.add_argument("--duration", type=int, default=int(os.getenv("SEEDANCE_DURATION", "4")))
    parser.add_argument("--resolution", default=os.getenv("SEEDANCE_RESOLUTION", "480p"))
    parser.add_argument("--ratio", default=os.getenv("SEEDANCE_RATIO", "16:9"))
    parser.add_argument("--poll-interval-seconds", type=int, default=3)
    parser.add_argument("--max-wait-seconds", type=int, default=90)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    port = args.mock_port or find_free_port()
    server, bind_url, docker_url = start_mock(args.total_tokens, args.complete_after_fetches, port)
    log(f"mock upstream listening on {bind_url}; docker URL {docker_url}")

    original_channel = channel_snapshot(args)
    restored = False
    try:
        configure_channel(args, docker_url)
        restart_app(args)
        token, token_info = select_token(args)
        log(f"using token source={token_info['source']} key={token_info.get('key') or token_info.get('masked')}")
        task_id, task_resp = submit_and_poll(args, token)
        video = probe_video(args, token, task_id)
        task_row = fetch_task_row(args, task_id)
        task_props = parse_json(task_row.get("properties"))
        request_id = str(task_props.get("request_id") or "")
        rows = fetch_logs(args, task_id, request_id)
        billing = validate_billing(args, task_id, task_row, rows)
        report = {
            "ok": True,
            "mock_bind_url": bind_url,
            "mock_docker_url": docker_url,
            "task_id": task_id,
            "task_response": task_resp,
            "video_probe": video,
            "task_row": {
                "status": task_row.get("status"),
                "progress": task_row.get("progress"),
                "quota": task_row.get("quota"),
                "channel_id": task_row.get("channel_id"),
                "request_id": request_id,
            },
            "billing": billing,
            "log_ids": [r.get("id") for r in rows],
        }
        report_path = write_report(report, task_id)
        log(f"billing ok: actual_quota={billing['actual_quota']} delta={billing['quota_delta']}")
        log(f"video ok: {video}")
        log(f"report written: {report_path}")
    finally:
        try:
            restore_channel(args, original_channel)
            restored = True
            restart_app(args)
        finally:
            server.shutdown()
            server.server_close()
        if restored:
            log("channel restored")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckFailed as exc:
        log(f"FAILED: {exc}")
        raise SystemExit(1)
