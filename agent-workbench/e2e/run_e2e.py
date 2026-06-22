#!/usr/bin/env python3
"""Agent Workbench local Docker E2E smoke runner.

The script expects the Workbench API to expose the route contract below. Each
route can be overridden with an environment variable from `.env.example`.

Default flow:
  bootstrap fixtures
  create + run billing_run
  create + run supplier_reconcile
  create + run codex_investigation using the deterministic fake agent
  approve the generated config change request
  publish the generated skill draft
  verify expected artifacts are visible through the API
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKBENCH_ROOT.parent
FIXTURE_DIR = WORKBENCH_ROOT / "e2e" / "fixtures"
DEFAULT_TIMEOUT_SECONDS = 300
TERMINAL_OK = {"COMPLETED", "APPROVED", "PUBLISHED", "completed", "approved", "published"}
TERMINAL_BAD = {"FAILED", "TIMED_OUT", "CANCELLED", "REJECTED", "failed", "timed_out", "cancelled", "rejected"}


class E2EError(RuntimeError):
    pass


@dataclass
class Settings:
    api_url: str
    api_token: str | None
    month: str
    channel_id: int
    vendor: str
    fixture_dir: Path
    timeout_seconds: int
    bootstrap_path: str
    jobs_path: str
    approve_change_path: str
    publish_skill_path: str


def read_dotenv(path: Path) -> None:
    # 本地调试允许用 .env 覆盖 API 路径和 fixture，但不强制依赖 dotenv 包。
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def settings_from_env() -> Settings:
    dotenv = WORKBENCH_ROOT / "e2e" / ".env"
    read_dotenv(dotenv)
    fixture_dir = Path(os.environ.get("WORKBENCH_E2E_FIXTURE_DIR", str(FIXTURE_DIR)))
    if not fixture_dir.is_absolute():
        fixture_dir = Path.cwd() / fixture_dir
    return Settings(
        api_url=os.environ.get("WORKBENCH_API_URL", "http://localhost:18088").rstrip("/"),
        api_token=os.environ.get("WORKBENCH_API_TOKEN") or None,
        month=os.environ.get("WORKBENCH_E2E_MONTH", "2026-06"),
        channel_id=int(os.environ.get("WORKBENCH_E2E_CHANNEL_ID", "65")),
        vendor=os.environ.get("WORKBENCH_E2E_VENDOR", "1001AI"),
        fixture_dir=fixture_dir.resolve(),
        timeout_seconds=int(os.environ.get("WORKBENCH_E2E_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
        bootstrap_path=os.environ.get("WORKBENCH_BOOTSTRAP_PATH", "/api/workbench/e2e/bootstrap"),
        jobs_path=os.environ.get("WORKBENCH_JOBS_PATH", "/api/workbench/jobs"),
        approve_change_path=os.environ.get(
            "WORKBENCH_APPROVE_CHANGE_PATH",
            "/api/workbench/config-change-requests/{id}/approve",
        ),
        publish_skill_path=os.environ.get("WORKBENCH_PUBLISH_SKILL_PATH", "/api/workbench/skills/publish"),
    )


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)


def pick_id(payload: Any, *keys: str) -> str | None:
    # 兼容不同实现阶段的响应包裹格式，降低 E2E 对字段外壳的敏感度。
    if not isinstance(payload, dict):
        return None
    candidates: list[Any] = [payload]
    for key in ("data", "job", "result", "change_request", "skill", "file"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)
    for candidate in candidates:
        for key in keys:
            value = candidate.get(key)
            if value is not None:
                return str(value)
    return None


def extract_status(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for candidate in [payload, payload.get("data"), payload.get("job"), payload.get("result")]:
        if isinstance(candidate, dict) and candidate.get("status") is not None:
            return str(candidate["status"])
    return None


def find_artifact_names(payload: Any) -> set[str]:
    # Artifact 可能以 URI、路径或对象列表返回，这里统一抽取 basename 做断言。
    names: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key in ("name", "path", "key", "s3_key", "artifact_path"):
                item = value.get(key)
                if isinstance(item, str):
                    names.add(item)
                    names.add(Path(item).name)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            names.add(value)
            names.add(Path(value).name)

    walk(payload)
    return names


class WorkbenchClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def request(self, method: str, path: str, payload: Any | None = None) -> Any:
        url = urljoin(self.settings.api_url + "/", path.lstrip("/"))
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.settings.api_token:
            headers["Authorization"] = f"Bearer {self.settings.api_token}"

        req = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self.settings.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise E2EError(f"{method} {url} failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise E2EError(f"{method} {url} failed: {exc.reason}") from exc

        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise E2EError(f"{method} {url} returned non-JSON response: {raw[:500]}") from exc

    def post(self, path: str, payload: Any) -> Any:
        return self.request("POST", path, payload)

    def get(self, path: str) -> Any:
        return self.request("GET", path)


def fixture_payload(settings: Settings) -> dict[str, Any]:
    # 这份 payload 明确声明所有 fixture 路径，保证 Docker 内外路径可追踪。
    fixture_root = settings.fixture_dir
    expected_summary = json.loads(
        (fixture_root / "athena" / "expected_summary.json").read_text(encoding="utf-8")
    )
    return {
        "mode": "fixture",
        "month": settings.month,
        "channel_id": settings.channel_id,
        "vendor": settings.vendor,
        "config_version": "local-v0",
        "fixture_root": "/workspace/e2e/fixtures",
        "athena_fixture_dir": "/workspace/e2e/fixtures/athena",
        "pricing_file": "/workspace/e2e/fixtures/config/pricing.json",
        "discounts_file": "/workspace/e2e/fixtures/config/discounts.json",
        "supplier_bill_file": "/workspace/e2e/fixtures/athena/supplier_1001ai_2026_06.csv",
        "expected_summary": expected_summary,
    }


def create_job(client: WorkbenchClient, settings: Settings, payload: dict[str, Any]) -> tuple[str, Any]:
    response = client.post(settings.jobs_path, payload)
    job_id = pick_id(response, "id", "job_id")
    if not job_id:
        raise E2EError(f"create job response did not include id/job_id:\n{dump_json(response)}")
    return job_id, response


def run_job(client: WorkbenchClient, settings: Settings, job_id: str) -> Any:
    path = f"{settings.jobs_path.rstrip('/')}/{job_id}/run"
    return client.post(path, {"job_id": job_id})


def get_job(client: WorkbenchClient, settings: Settings, job_id: str) -> Any:
    return client.get(f"{settings.jobs_path.rstrip('/')}/{job_id}")


def wait_for_job(client: WorkbenchClient, settings: Settings, job_id: str) -> Any:
    # 当前 API 是同步执行，但保留轮询逻辑，方便未来切到异步 Worker 后复用同一脚本。
    deadline = time.monotonic() + settings.timeout_seconds
    last_payload: Any = None
    while time.monotonic() < deadline:
        last_payload = get_job(client, settings, job_id)
        status = extract_status(last_payload)
        if status in TERMINAL_OK:
            return last_payload
        if status in TERMINAL_BAD:
            raise E2EError(f"job {job_id} ended with {status}:\n{dump_json(last_payload)}")
        time.sleep(2)
    raise E2EError(f"timed out waiting for job {job_id}; last response:\n{dump_json(last_payload)}")


def assert_artifacts(
    client: WorkbenchClient,
    settings: Settings,
    job_id: str,
    job_payload: Any,
    required: list[str],
) -> Any:
    artifact_payload = job_payload
    if not find_artifact_names(artifact_payload):
        artifact_payload = client.get(f"{settings.jobs_path.rstrip('/')}/{job_id}/artifacts")

    names = find_artifact_names(artifact_payload)
    missing = [name for name in required if name not in names]
    if missing:
        raise E2EError(
            f"job {job_id} is missing artifacts {missing}; visible names:\n{dump_json(sorted(names))}"
        )
    return artifact_payload


def assert_has_artifact_suffix(payload: Any, suffix: str, context: str) -> None:
    names = find_artifact_names(payload)
    if not any(name.endswith(suffix) for name in names):
        raise E2EError(f"{context} is missing artifact suffix {suffix}; visible names:\n{dump_json(sorted(names))}")


def extract_change_request_id(job_payload: Any, artifact_payload: Any) -> str:
    # change_request_id 可能在 job.result、change_requests 列表或 artifact 响应中，递归找 cr-* 更稳。
    def walk(value: Any) -> str | None:
        if isinstance(value, dict):
            for key in ("config_change_request_id", "change_request_id", "request_id", "id"):
                item = value.get(key)
                if isinstance(item, str) and item.startswith("cr-"):
                    return item
            for item in value.values():
                found = walk(item)
                if found:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = walk(item)
                if found:
                    return found
        return None

    for payload in (job_payload, artifact_payload):
        deep_found = walk(payload)
        if deep_found:
            return deep_found
        found = pick_id(payload, "config_change_request_id", "change_request_id", "request_id", "id")
        if found and not found.startswith("job-"):
            return found
    raise E2EError(
        "could not find config change request id in job or artifact payload:\n"
        + dump_json({"job": job_payload, "artifacts": artifact_payload})
    )


def run_api_flow(settings: Settings) -> None:
    # 端到端验收顺序：配置入库 -> 出账 -> 对账 -> Agent 调查 -> 审批 -> Skill 沉淀。
    client = WorkbenchClient(settings)
    print(f"[e2e] API: {settings.api_url}")
    print(f"[e2e] fixtures: {settings.fixture_dir}")

    bootstrap_response = client.post(settings.bootstrap_path, fixture_payload(settings))
    config_version_id = pick_id(bootstrap_response, "config_version_id", "version_id", "id") or "cfg-local-v0"
    print(f"[e2e] bootstrap ok: config_version_id={config_version_id}")

    billing_job_id, _ = create_job(
        client,
        settings,
        {
            "type": "billing_run",
            "job_type": "billing_run",
            "month": settings.month,
            "channel_id": settings.channel_id,
            "flat_tier": True,
            "config_version_id": config_version_id,
            "fixture_mode": True,
        },
    )
    run_job(client, settings, billing_job_id)
    billing_payload = wait_for_job(client, settings, billing_job_id)
    billing_artifacts = assert_artifacts(client, settings, billing_job_id, billing_payload, ["summary.json"])
    assert_has_artifact_suffix(billing_artifacts, ".xlsx", f"billing job {billing_job_id}")
    billing_run_id = pick_id(billing_payload, "billing_run_id", "run_id", "id") or billing_job_id
    print(f"[e2e] billing_run ok: job_id={billing_job_id}, run_id={billing_run_id}")

    upload_response = client.post(
        "/api/files/upload",
        {
            "filename": "supplier_1001ai_2026_06.csv",
            "content_type": "text/csv",
            "content_base64": base64.b64encode(b"model,total_usd\nclaude-opus-4-6,100.00\n").decode("ascii"),
            "category": "supplier-bill",
            "job_id": billing_job_id,
            "uploaded_by": "local-e2e",
            "metadata": {"month": settings.month, "vendor": settings.vendor},
        },
    )
    upload_id = pick_id(upload_response, "id")
    if not upload_id:
        raise E2EError(f"file upload response missing id:\n{dump_json(upload_response)}")
    files_payload = client.get("/api/files")
    if "supplier_1001ai_2026_06.csv" not in dump_json(files_payload):
        raise E2EError(f"uploaded file not found in file list:\n{dump_json(files_payload)}")
    print(f"[e2e] file upload ok: file_id={upload_id}")

    reconcile_job_id, _ = create_job(
        client,
        settings,
        {
            "type": "supplier_reconcile",
            "job_type": "supplier_reconcile",
            "month": settings.month,
            "channel_id": settings.channel_id,
            "vendor": settings.vendor,
            "our_billing_run_id": billing_run_id,
            "supplier_bill_fixture": "/workspace/e2e/fixtures/athena/supplier_1001ai_2026_06.csv",
        },
    )
    run_job(client, settings, reconcile_job_id)
    reconcile_payload = wait_for_job(client, settings, reconcile_job_id)
    assert_artifacts(client, settings, reconcile_job_id, reconcile_payload, ["diff.csv", "anomalies.csv"])
    print(f"[e2e] supplier_reconcile ok: job_id={reconcile_job_id}")

    investigation_job_id = pick_id(reconcile_payload, "investigation_job_id", "codex_job_id")
    if not investigation_job_id:
        investigation_job_id, _ = create_job(
            client,
            settings,
            {
                "type": "codex_investigation",
                "job_type": "codex_investigation",
                "reason": "supplier_diff_over_threshold",
                "month": settings.month,
                "channel_id": settings.channel_id,
                "vendor": settings.vendor,
                "our_billing_run_id": billing_run_id,
                "supplier_reconcile_job_id": reconcile_job_id,
                "agent_mode": "fake",
            },
        )
    run_job(client, settings, investigation_job_id)
    investigation_payload = wait_for_job(client, settings, investigation_job_id)
    investigation_artifacts = assert_artifacts(
        client,
        settings,
        investigation_job_id,
        investigation_payload,
        ["report.md", "result.json", "config_change_request.json", "SKILL.md"],
    )
    change_request_id = extract_change_request_id(investigation_payload, investigation_artifacts)
    print(f"[e2e] fake-agent investigation ok: job_id={investigation_job_id}")

    approve_response = client.post(
        settings.approve_change_path.format(id=change_request_id),
        {
            "reviewer": "local-e2e",
            "review_comment": "Approved by deterministic local smoke flow.",
            "apply": True,
            "trigger_billing_rerun": True,
        },
    )
    approved_version = pick_id(approve_response, "config_version_id", "version_id", "id") or "local-v1"
    print(f"[e2e] config change approved: id={change_request_id}, version={approved_version}")

    publish_response = client.post(
        settings.publish_skill_path,
        {
            "source_job_id": investigation_job_id,
            "source_path": "output/skill_draft",
            "name": "1001AI Vendor Reconcile",
            "vendor": settings.vendor,
            "family": "vendor-reconcile",
            # E2E 可重复运行，版本交给 API 按当前 DB 自动递增。
            "reviewer": "local-e2e",
        },
    )
    skill_publish_job_id = pick_id(publish_response, "job_id", "id")
    if skill_publish_job_id and skill_publish_job_id.startswith("job-"):
        skill_payload = wait_for_job(client, settings, skill_publish_job_id)
        assert_artifacts(client, settings, skill_publish_job_id, skill_payload, ["SKILL.md", "manifest.json", "latest.json"])
    else:
        names = find_artifact_names(publish_response)
        missing = [name for name in ["SKILL.md", "manifest.json", "latest.json"] if name not in names]
        if missing:
            raise E2EError(f"skill publish response missing artifacts {missing}:\n{dump_json(publish_response)}")
    print("[e2e] skill publish ok")
    run_agent_stream_check(client)
    print("[e2e] smoke flow completed")


def run_agent_stream_check(client: WorkbenchClient) -> None:
    session = client.post(
        "/api/agent/sessions",
        {
            "provider": "claude_code",
            "runtime": "codingplan",
            "prompt": "请检查 1001AI 对账差异，并等待我补充一条运行中消息。",
            "metadata": {"e2e": True},
            "live": False,
        },
    )
    session_id = pick_id(session, "session_id", "id")
    if not session_id:
        raise E2EError(f"agent session response missing id:\n{dump_json(session)}")

    events: list[str] = []

    def read_stream() -> None:
        url = f"{client.settings.api_url}/api/agent/sessions/{session_id}/stream"
        with urlopen(url, timeout=60) as response:
            for raw in response:
                line = raw.decode("utf-8", errors="replace").strip()
                if line.startswith("data:"):
                    events.append(line)
                if "run.completed" in line:
                    break

    stream_thread = threading.Thread(target=read_stream, daemon=True)
    stream_thread.start()
    time.sleep(1.2)
    client.post(
        f"/api/agent/sessions/{session_id}/messages",
        {"role": "user", "content": "人工介入：请重点检查 ClaudeCode/CodingPlan 的流式事件，并确认等待窗口可接收消息。"},
    )
    stream_thread.join(timeout=20)
    if stream_thread.is_alive():
        raise E2EError("agent stream did not complete in time")

    snapshot = client.get(f"/api/agent/sessions/{session_id}/events")
    history = client.get(f"/api/agent/sessions/{session_id}/history")
    event_names = find_artifact_names(snapshot)
    serialized = dump_json(snapshot)
    if (
        "human.input.waiting" not in serialized
        or "operator.message.received" not in serialized
        or "assistant.delta" not in serialized
        or "tool.call" not in serialized
        or "tool.result" not in serialized
    ):
        raise E2EError(f"agent stream did not include expected streaming/ack events:\n{serialized}")
    if "messages" not in history or "events" not in history:
        raise E2EError(f"agent history response missing messages/events:\n{dump_json(history)}")
    if not events:
        raise E2EError("agent stream returned no SSE data lines")
    print(f"[e2e] agent stream ok: session_id={session_id}, sse_events={len(events)}, names={len(event_names)}")


def run_offline_fake_agent(settings: Settings) -> None:
    # 离线检查只验证 fake-agent 的文件契约，不依赖 API、DB 或 MinIO。
    output_dir = WORKBENCH_ROOT / "e2e" / ".tmp" / "fake-agent-output"
    if output_dir.exists():
        for child in sorted(output_dir.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
    output_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "WORKSPACE_DIR": str(settings.fixture_dir.parent),
            "INPUT_DIR": str(settings.fixture_dir / "input"),
            "SKILLS_DIR": str(settings.fixture_dir / "skills"),
            "OUTPUT_DIR": str(output_dir),
        }
    )
    subprocess.run(
        [sys.executable, str(WORKBENCH_ROOT / "runner" / "fake_agent.py")],
        check=True,
        env=env,
    )
    required = [
        output_dir / "report.md",
        output_dir / "result.json",
        output_dir / "config_change_request.json",
        output_dir / "skill_draft" / "SKILL.md",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise E2EError(f"offline fake-agent check missing files: {missing}")
    print(f"[e2e] offline fake-agent artifact check ok: {output_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Agent Workbench local E2E smoke flow.")
    parser.add_argument(
        "--offline-fake-agent-check",
        action="store_true",
        help="Run only the deterministic fake agent against local fixtures, without calling the API.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = settings_from_env()
    try:
        if args.offline_fake_agent_check:
            run_offline_fake_agent(settings)
        else:
            run_api_flow(settings)
    except E2EError as exc:
        print(f"[e2e] failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
