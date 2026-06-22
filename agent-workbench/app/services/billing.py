"""账单生成相关业务逻辑：命令构建、执行、产物归档。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import psycopg2.extras
from fastapi import HTTPException

from .artifacts import artifacts, billing_artifacts
from .core import (
    BILL_TYPES,
    WORKBENCH_ROOT,
    content_type_for_filename,
    content_type_for_path,
    dumps_json,
    env_int,
    fetch_one,
    filename_from_uri,
    int_or_none,
    json_safe,
    new_id,
    safe_filename,
    slug,
    uri_to_prefix,
    utc_now,
    utc_now_iso,
)


def previous_month_label(now=None) -> str:
    current = now or utc_now()
    first = current.replace(day=1)
    previous = first - timedelta(days=1)
    return previous.strftime("%Y-%m")


def period_bounds_for_month(month: str) -> tuple[str, str]:
    from datetime import datetime

    start = datetime.strptime(f"{month}-01", "%Y-%m-%d").date()
    if start.month == 12:
        next_start = start.replace(year=start.year + 1, month=1)
    else:
        next_start = start.replace(month=start.month + 1)
    return start.isoformat(), (next_start - timedelta(days=1)).isoformat()


def normalize_bill_type(value: str | None, metadata: dict[str, Any] | None = None, channel_id: int | None = None) -> str:
    metadata = metadata or {}
    raw = value or metadata.get("bill_type")
    if raw:
        bill_type = str(raw)
    elif metadata.get("customer_view"):
        bill_type = "customer_invoice"
    elif channel_id is not None:
        bill_type = "channel_cost_bill"
    else:
        bill_type = "internal_customer_bill"
    if bill_type not in BILL_TYPES:
        raise HTTPException(status_code=400, detail=f"unsupported bill_type: {bill_type}")
    return bill_type


def infer_target(bill_type: str, channel_id: int | None, metadata: dict[str, Any] | None = None) -> tuple[str, str | None]:
    metadata = metadata or {}
    target_type = str(metadata.get("target_type") or "").strip()
    target_id = metadata.get("target_id")
    if target_type:
        return target_type, str(target_id) if target_id is not None and str(target_id) != "" else None
    user_id = metadata.get("user_id")
    if bill_type == "customer_invoice":
        return "customer", str(user_id) if user_id is not None and str(user_id) != "" else "all"
    if bill_type == "channel_cost_bill":
        return "channel", str(channel_id) if channel_id is not None else "all"
    return "all", None


def structured_billing_prefix(bill_type: str, month: str, target_type: str | None, target_id: str | None, run_id: str) -> str:
    """按 账单类型/年/月/对象 组织 S3 路径：bills/{bill_type}/{YYYY}/{MM}/{target}/{run_id}。

    target 形如 all / channel-65 / customer-89，便于人工按结构浏览与归档。
    """
    bt = slug(bill_type or "bill") or "bill"
    parts = str(month or "").split("-")
    year = parts[0] if parts and parts[0] else "unknown"
    mm = parts[1] if len(parts) > 1 and parts[1] else "00"
    tt = (target_type or "all").strip() or "all"
    tid = (str(target_id).strip() if target_id not in (None, "", "all") else "")
    target = f"{tt}-{tid}" if tid else (tt if tt != "all" else "all")
    return f"bills/{bt}/{year}/{mm}/{slug(target) or 'all'}/{run_id}"


_RERUN_METADATA_DROP_KEYS = {
    "batch_id",
    "billing_run_id",
    "command_hash",
    "fact_manifest_id",
    "generated_at",
    "generated_files",
    "job_id",
    "output_dir",
    "parent_document_id",
    "real_execution",
    "schedule_id",
    "schedule_run_id",
    "split_document_ids",
    "split_from_document_id",
}


def _clean_rerun_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    cleaned = json_safe(metadata)
    if not isinstance(cleaned, dict):
        return {}
    for key in _RERUN_METADATA_DROP_KEYS:
        cleaned.pop(key, None)
    return cleaned


def build_bill_document_rerun_payload(
    document: dict[str, Any],
    *,
    source_job: dict[str, Any] | None = None,
    source_run: dict[str, Any] | None = None,
    actor: str = "ops",
    comment: str | None = None,
    no_cache: bool = True,
    config_version_id: str | None = None,
) -> dict[str, Any]:
    """Build a fresh billing_run request from an existing bill document.

    The new run intentionally uses the current active pricing/discount config
    unless a config_version_id is explicitly provided. Old output paths and
    scheduler ids are dropped so reruns remain separate, auditable artifacts.
    """
    summary = document.get("summary") if isinstance(document.get("summary"), dict) else {}
    source_payload = source_job.get("request_payload") if source_job and isinstance(source_job.get("request_payload"), dict) else {}
    source_metadata = source_payload.get("metadata") if isinstance(source_payload.get("metadata"), dict) else {}

    raw_bill_type = document.get("bill_type") or (source_run or {}).get("bill_type") or (source_job or {}).get("bill_type")
    bill_type = normalize_bill_type(
        str(raw_bill_type) if raw_bill_type else None,
        source_metadata,
        int_or_none((source_run or {}).get("channel_id") or (source_job or {}).get("channel_id")),
    )
    target_type = str(
        document.get("target_type")
        or (source_run or {}).get("target_type")
        or (source_job or {}).get("target_type")
        or source_payload.get("target_type")
        or "all"
    )
    target_id_raw = (
        document.get("target_id")
        if document.get("target_id") not in (None, "")
        else (source_run or {}).get("target_id")
        or (source_job or {}).get("target_id")
        or source_payload.get("target_id")
    )
    target_id = str(target_id_raw) if target_id_raw not in (None, "", "all") else None

    month = str(document.get("month") or (source_run or {}).get("month") or (source_job or {}).get("month") or "")
    if bill_type == "daily_channel_cost_snapshot":
        month = str(summary.get("snapshot_date") or summary.get("period") or month)

    channel_id = int_or_none((source_run or {}).get("channel_id") or (source_job or {}).get("channel_id") or source_payload.get("channel_id"))
    metadata = _clean_rerun_metadata(source_metadata)
    metadata.update(
        {
            "source": "bill_document_rerun",
            "rerun_from_document_id": document.get("id"),
            "rerun_from_job_id": document.get("job_id") or (source_job or {}).get("id"),
            "rerun_from_billing_run_id": document.get("billing_run_id") or (source_run or {}).get("id"),
            "rerun_requested_by": actor,
            "rerun_requested_at": utc_now_iso(),
            "detail": True,
            "no_cache": bool(no_cache),
        }
    )
    if comment:
        metadata["rerun_comment"] = comment

    if target_type == "customer" and target_id:
        user_id = int_or_none(target_id)
        metadata["user_id"] = user_id if user_id is not None else target_id
    if target_type == "channel" and target_id:
        channel_id = int_or_none(target_id) or channel_id

    if bill_type == "customer_invoice":
        metadata["customer_view"] = True
    if bill_type == "daily_channel_cost_snapshot" and month:
        metadata["period"] = month
        metadata["snapshot_date"] = month

    payload: dict[str, Any] = {
        "month": month,
        "channel_id": channel_id,
        "vendor": (source_run or {}).get("vendor") or (source_job or {}).get("vendor") or source_payload.get("vendor"),
        "bill_type": bill_type,
        "target_type": target_type,
        "target_id": target_id,
        "created_by": actor,
        "metadata": metadata,
    }
    if config_version_id:
        payload["config_version_id"] = config_version_id
    return payload


def build_athena_bill_command(job: dict[str, Any], run: dict[str, Any], config: dict[str, Any], billing_prefix: str) -> dict[str, Any]:
    payload = job.get("request_payload") if isinstance(job.get("request_payload"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    output_dir = str(metadata.get("output_dir") or f"/tmp/agent-workbench-athena-output/{run['id']}")
    bill_type = str(run.get("bill_type") or job.get("bill_type") or payload.get("bill_type") or normalize_bill_type(None, metadata, run.get("channel_id")))
    if bill_type == "daily_channel_cost_snapshot":
        run_period = str(run["month"])
        default_snapshot_date = run_period if re.fullmatch(r"\d{4}-\d{2}-\d{2}", run_period) else f"{run_period}-01"
        snapshot_date = str(metadata.get("snapshot_date") or payload.get("period") or metadata.get("date") or default_snapshot_date)
        args = ["python", "bill_cli.py", "daily", "--date", snapshot_date, "-o", output_dir]
        if metadata.get("no_cache"):
            args.append("--no-cache")
        if metadata.get("split_channels") is False:
            args.append("--no-split-channels")
        elif metadata.get("split_channels", True):
            args.append("--split-channels")
        args.append("--detail")
        if run.get("channel_id") is not None:
            args.extend(["--channel-id", str(run["channel_id"])])
        return {
            "mode": "athena-bill-cli",
            "command_family": "scripts/athena/bill_cli.py",
            "original_cli": "python bill_cli.py daily",
            "job_id": job["id"],
            "billing_run_id": run["id"],
            "bill_type": bill_type,
            "target_type": run.get("target_type") or job.get("target_type"),
            "target_id": run.get("target_id") or job.get("target_id"),
            "config_version": config["version"],
            "worker_dir": str(WORKBENCH_ROOT / "athena_worker"),
            "output_dir": output_dir,
            "snapshot_date": snapshot_date,
            "artifact_prefix": billing_prefix,
            "argv": args,
            "shell": " ".join(shlex.quote(part) for part in args),
        }
    args = ["python", "bill_cli.py", "bill", "--month", str(run["month"]), "-o", output_dir]
    if metadata.get("no_cache"):
        args.append("--no-cache")
    if run.get("channel_id") is not None:
        args.extend(["--channel-id", str(run["channel_id"])])
    user_id = payload.get("user_id") if payload.get("user_id") is not None else metadata.get("user_id")
    currency = payload.get("currency") or metadata.get("currency")
    exchange_rate = payload.get("exchange_rate") or metadata.get("exchange_rate")
    if user_id is not None:
        args.extend(["--user-id", str(user_id)])
    if currency:
        args.extend(["--currency", str(currency)])
    if exchange_rate:
        args.extend(["--exchange-rate", str(exchange_rate)])
    if metadata.get("flat_tier") or metadata.get("flat_tier_since"):
        args.append("--flat-tier")
    args.append("--detail")
    if metadata.get("customer_view") or bill_type == "customer_invoice":
        args.append("--customer-view")
    if metadata.get("split_customers") is False:
        args.append("--no-split-customers")
    if bill_type in {"internal_customer_bill", "channel_cost_bill", "customer_invoice"}:
        args.extend(["--bill-type", bill_type])
    if bill_type == "internal_customer_bill":
        if metadata.get("split_internal_customers") is False:
            args.append("--no-split-internal-customers")
        elif metadata.get("split_internal_customers", True) and run.get("channel_id") is None and not payload.get("user_id"):
            args.append("--split-internal-customers")
    if bill_type == "channel_cost_bill":
        if metadata.get("split_channels") is False:
            args.append("--no-split-channels")
        elif metadata.get("split_channels", True) and run.get("channel_id") is None:
            args.append("--split-channels")
    if metadata.get("end_day"):
        args.extend(["--end-day", str(metadata["end_day"])])
    if metadata.get("flat_tier_since"):
        args.extend(["--flat-tier-since", str(metadata["flat_tier_since"])])
    if metadata.get("upload_to_athena_s3"):
        args.append("--upload")
    return {
        "mode": "athena-bill-cli",
        "command_family": "scripts/athena/bill_cli.py",
        "original_cli": "python bill_cli.py bill",
        "job_id": job["id"],
        "billing_run_id": run["id"],
        "bill_type": bill_type,
        "target_type": run.get("target_type") or job.get("target_type"),
        "target_id": run.get("target_id") or job.get("target_id"),
        "config_version": config["version"],
        "worker_dir": str(WORKBENCH_ROOT / "athena_worker"),
        "output_dir": output_dir,
        "artifact_prefix": billing_prefix,
        "argv": args,
        "shell": " ".join(shlex.quote(part) for part in args),
    }


def athena_worker_manifest() -> dict[str, Any]:
    worker_dir = WORKBENCH_ROOT / "athena_worker"
    files: list[dict[str, Any]] = []
    for path in sorted(worker_dir.glob("*")):
        if path.is_file():
            raw = path.read_bytes()
            files.append({"name": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    return {"source": "scripts/athena copied into agent-workbench/athena_worker", "worker_dir": str(worker_dir), "files": files, "generated_at": utc_now_iso()}


def prepare_athena_worker_runtime(config: dict[str, Any]) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    tmp = tempfile.TemporaryDirectory(prefix="agent-workbench-athena-")
    runtime_dir = Path(tmp.name) / "athena_worker"
    shutil.copytree(WORKBENCH_ROOT / "athena_worker", runtime_dir, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.log"))
    (runtime_dir / "pricing.json").write_text(json.dumps(json_safe(config["pricing_snapshot"]), ensure_ascii=False, indent=2), encoding="utf-8")
    (runtime_dir / "discounts.json").write_text(json.dumps(json_safe(config["discounts_snapshot"]), ensure_ascii=False, indent=2), encoding="utf-8")
    return tmp, runtime_dir


def collect_generated_files(output_dir: Path) -> list[Path]:
    if not output_dir.exists():
        return []
    return sorted(path for path in output_dir.rglob("*") if path.is_file())


def execute_real_athena_bill(command: dict[str, Any], config: dict[str, Any], billing_prefix: str) -> dict[str, Any]:
    timeout_seconds = env_int("WORKBENCH_ATHENA_REAL_TIMEOUT_SECONDS", 6 * 60 * 60, minimum=60, maximum=24 * 60 * 60)
    tmp, runtime_dir = prepare_athena_worker_runtime(config)
    try:
        output_dir = Path(command["output_dir"])
        if not output_dir.is_absolute():
            output_dir = Path(tmp.name) / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        argv = list(command["argv"])
        argv[0] = sys.executable
        for index, part in enumerate(argv):
            if part == command["output_dir"]:
                argv[index] = str(output_dir)
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        started_at = time.time()
        proc = subprocess.run(argv, cwd=runtime_dir, env=env, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_seconds)
        duration_ms = int((time.time() - started_at) * 1000)
        stdout_uri = billing_artifacts.put_text(f"{billing_prefix}/stdout.log", proc.stdout or "", "text/plain; charset=utf-8")
        stderr_uri = billing_artifacts.put_text(f"{billing_prefix}/stderr.log", proc.stderr or "", "text/plain; charset=utf-8")
        generated: dict[str, str] = {}
        bill_summary: dict[str, Any] = {}
        for path in collect_generated_files(output_dir):
            rel = path.relative_to(output_dir).as_posix()
            generated[rel] = billing_artifacts.put_file(
                f"{billing_prefix}/generated/{rel}",
                path,
                content_type_for_path(path),
            )
            if rel == "bill_summary.json":
                try:
                    bill_summary = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    bill_summary = {}
        return {
            "returncode": proc.returncode,
            "duration_ms": duration_ms,
            "stdout": stdout_uri,
            "stderr": stderr_uri,
            "stderr_text": proc.stderr or "",
            "generated": generated,
            "output_dir": str(output_dir),
            "bill_summary": bill_summary,
        }
    finally:
        tmp.cleanup()


def _is_xlsx_bill_artifact(name: str) -> bool:
    basename = str(name).lower().replace("\\", "/").rsplit("/", 1)[-1]
    return basename.endswith(".xlsx") and "_detail" not in basename and basename != "bill_summary.json"


def primary_bill_uri(generated: dict[str, str]) -> str | None:
    for name, uri in generated.items():
        if _is_xlsx_bill_artifact(name) and parse_split_entity_from_filename(name) is None:
            return uri
    for name, uri in generated.items():
        if _is_xlsx_bill_artifact(name):
            return uri
    for name, uri in generated.items():
        if name.lower().endswith(".xlsx"):
            return uri
    for name, uri in generated.items():
        if name.lower().endswith((".zip", ".csv", ".json")):
            return uri
    return next(iter(generated.values()), None) if generated else None


def has_bill_workbook(generated: dict[str, str]) -> bool:
    return any(_is_xlsx_bill_artifact(name) for name in generated)


def resolve_billing_run_status(failed_message: str, generated: dict[str, str]) -> tuple[str, str]:
    """Return (summary_status, job_db_status). Artifacts present → COMPLETED even if CLI exited non-zero."""
    if not failed_message:
        return "completed", "COMPLETED"
    if has_bill_workbook(generated):
        return "partial", "FAILED"
    return "failed", "FAILED"


def summarize_batch_completion(
    job_statuses: list[str] | tuple[str, ...],
    document_statuses: list[str] | tuple[str, ...],
    *,
    expected_jobs: int = 0,
) -> dict[str, Any]:
    """Summarize async billing batch completion from child job/document states."""
    success_jobs = {"COMPLETED"}
    failed_jobs = {"FAILED", "ERROR", "TIMED_OUT", "CANCELLED"}
    success_docs = {"GENERATED", "DELIVERED"}
    failed_docs = {"FAILED", "PARTIAL_FAILED"}

    jobs = [str(status or "").upper() for status in job_statuses]
    docs = [str(status or "").upper() for status in document_statuses]
    missing_jobs = max(0, int(expected_jobs or 0) - len(jobs))

    completed_jobs = sum(1 for status in jobs if status in success_jobs)
    failed_job_count = sum(1 for status in jobs if status in failed_jobs)
    pending_jobs = len(jobs) - completed_jobs - failed_job_count + missing_jobs

    completed_docs = sum(1 for status in docs if status in success_docs)
    failed_doc_count = sum(1 for status in docs if status in failed_docs)
    pending_docs = len(docs) - completed_docs - failed_doc_count

    if pending_jobs or pending_docs or (expected_jobs and not jobs):
        status = "RENDERING"
    elif failed_job_count or failed_doc_count:
        status = "PARTIAL_FAILED" if completed_jobs or completed_docs else "FAILED"
    elif completed_jobs or completed_docs:
        status = "COMPLETED"
    else:
        status = "RENDERING"

    return {
        "status": status,
        "expected_jobs": int(expected_jobs or 0),
        "jobs_seen": len(jobs),
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_job_count,
        "pending_jobs": pending_jobs,
        "documents_seen": len(docs),
        "completed_documents": completed_docs,
        "failed_documents": failed_doc_count,
        "pending_documents": pending_docs,
    }


def bill_document_status_for_type(
    bill_type: str,
    execution_mode: str,
    generated: dict[str, str],
    *,
    is_fixture: bool = False,
) -> str:
    if execution_mode != "real":
        return "DRAFT"
    if is_fixture:
        return "DRAFT" if generated else "FAILED"
    if has_bill_workbook(generated):
        return "GENERATED"
    return "FAILED"


def bill_document_idempotency(job: dict[str, Any], run: dict[str, Any], config: dict[str, Any], command: dict[str, Any]) -> str:
    payload = job.get("request_payload") if isinstance(job.get("request_payload"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    command_hash = hashlib.sha256(dumps_json(command).encode("utf-8")).hexdigest()
    idempotency_payload = {
        "schedule_id": metadata.get("schedule_id") or payload.get("schedule_id"),
        "period": run["month"],
        "billing_run_id": run["id"],
        "bill_type": run.get("bill_type") or job.get("bill_type"),
        "target_type": run.get("target_type") or job.get("target_type"),
        "target_id": run.get("target_id") or job.get("target_id"),
        "config_version_id": config["id"],
        "command_hash": command_hash,
    }
    return hashlib.sha256(dumps_json(idempotency_payload).encode("utf-8")).hexdigest()


def split_bill_document_idempotency(
    job: dict[str, Any],
    run: dict[str, Any],
    config: dict[str, Any],
    command: dict[str, Any],
    *,
    target_type: str,
    target_id: str,
) -> str:
    base = bill_document_idempotency(job, run, config, command)
    return hashlib.sha256(f"{base}:{target_type}:{target_id}".encode("utf-8")).hexdigest()


def parse_split_entity_from_filename(name: str) -> tuple[str, str] | None:
    """Return (target_type, target_id) for primary split workbook outputs."""
    lower = name.lower().replace("\\", "/")
    basename = lower.rsplit("/", 1)[-1]
    if not basename.endswith(".xlsx"):
        return None
    if "_detail" in basename or basename in {"bill_summary.json"}:
        return None
    user_match = re.search(r"_user(\d+)", basename, re.I)
    if user_match:
        return ("customer", user_match.group(1))
    channel_match = re.search(r"_ch(\d+)", basename, re.I)
    if channel_match:
        return ("channel", channel_match.group(1))
    return None


def parse_split_artifact_entity_from_filename(name: str) -> tuple[str, str] | None:
    """Return split target for any per-customer/per-channel artifact, including detail files."""
    lower = name.lower().replace("\\", "/")
    basename = lower.rsplit("/", 1)[-1]
    if basename in {"bill_summary.json"}:
        return None
    if not (
        basename.endswith(".xlsx")
        or basename.endswith(".csv")
        or basename.endswith(".zip")
        or basename.endswith(".csv.zip")
    ):
        return None
    user_match = re.search(r"_user(\d+)", basename, re.I)
    if user_match:
        return ("customer", user_match.group(1))
    channel_match = re.search(r"_ch(\d+)", basename, re.I)
    if channel_match:
        return ("channel", channel_match.group(1))
    return None


def _split_generated_files_by_target(generated: dict[str, str]) -> list[tuple[str, str, str, str, dict[str, str]]]:
    """Group split workbook plus its matching detail artifacts for each target."""
    all_target_files: dict[tuple[str, str], dict[str, str]] = {}
    primary_files: list[tuple[str, str, str, str]] = []
    seen_targets: set[tuple[str, str]] = set()

    for name, uri in generated.items():
        if not uri:
            continue
        artifact_entity = parse_split_artifact_entity_from_filename(name)
        if artifact_entity:
            all_target_files.setdefault(artifact_entity, {})[name] = uri

        primary_entity = parse_split_entity_from_filename(name)
        if not primary_entity:
            continue
        target_type, target_id = primary_entity
        key = (target_type, target_id)
        if key in seen_targets:
            continue
        seen_targets.add(key)
        primary_files.append((name, uri, target_type, target_id))

    split_files: list[tuple[str, str, str, str, dict[str, str]]] = []
    for name, uri, target_type, target_id in primary_files:
        child_generated = all_target_files.get((target_type, target_id), {}).copy()
        child_generated.setdefault(name, uri)
        split_files.append((name, uri, target_type, target_id, child_generated))
    return split_files


_SPLIT_CHILD_SUMMARY_KEYS = (
    "status",
    "mode",
    "execution_mode",
    "athena_e2e_mode",
    "is_fixture",
    "bill_type",
    "target_type",
    "target_id",
    "month",
    "period",
    "snapshot_date",
    "channel_id",
    "vendor",
    "config_version",
    "pricing_models",
    "command_hash",
    "error_message",
    "generated_at",
)


def _split_metric_map(base_summary: dict[str, Any], target_type: str) -> tuple[str, dict[str, Any]]:
    bill_summary = base_summary.get("bill_summary") if isinstance(base_summary.get("bill_summary"), dict) else {}
    if target_type == "channel":
        return "bill_summary.per_channel_summary", bill_summary.get("per_channel_summary") if isinstance(bill_summary.get("per_channel_summary"), dict) else {}
    return "bill_summary.per_customer_summary", bill_summary.get("per_customer_summary") if isinstance(bill_summary.get("per_customer_summary"), dict) else {}


def _execution_log_summary(base_summary: dict[str, Any]) -> dict[str, Any]:
    real_execution = base_summary.get("real_execution") if isinstance(base_summary.get("real_execution"), dict) else {}
    return {key: real_execution[key] for key in ("stdout", "stderr", "duration_ms", "returncode") if key in real_execution}


def _build_split_bill_document_summary(
    base_summary: dict[str, Any],
    *,
    child_generated: dict[str, str],
    parent_document_id: str | None,
    target_type: str,
    target_id: str,
    schedule_run_id: str | None,
    batch_id: str | None,
) -> dict[str, Any]:
    safe_base = json_safe(base_summary)
    child_summary = {
        key: safe_base[key]
        for key in _SPLIT_CHILD_SUMMARY_KEYS
        if key in safe_base and safe_base[key] is not None
    }
    child_summary.update(
        {
            "generated_files": child_generated,
            "split_from_document_id": parent_document_id,
            "split_entity": True,
            "target_type": target_type,
            "target_id": target_id,
            "schedule_run_id": schedule_run_id,
            "batch_id": batch_id,
        }
    )
    if target_type == "customer":
        child_summary["user_id"] = target_id
    elif target_type == "channel":
        child_summary["channel_id"] = target_id

    for key in ("total_usd", "total_calls", "unique_users", "unique_models", "total_input_tokens", "total_output_tokens"):
        if key in safe_base:
            child_summary[f"parent_{key}"] = safe_base[key]

    metric_source, metric_map = _split_metric_map(safe_base, target_type)
    target_metrics = metric_map.get(str(target_id)) if isinstance(metric_map, dict) else None
    if isinstance(target_metrics, dict):
        child_summary.update(json_safe(target_metrics))
        child_summary["split_metric_source"] = metric_source
    else:
        child_summary["metrics_missing"] = True
        child_summary["split_metric_source"] = "unavailable"

    real_execution = _execution_log_summary(safe_base)
    if real_execution:
        child_summary["real_execution"] = real_execution
    return child_summary


def sync_split_bill_documents(
    cur,
    *,
    job: dict[str, Any],
    run: dict[str, Any],
    config: dict[str, Any],
    command: dict[str, Any],
    execution_mode: str,
    generated: dict[str, str],
    parent_document: dict[str, Any],
    base_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    """Create or update bill_document rows for each split workbook emitted by a billing job."""
    payload = job.get("request_payload") if isinstance(job.get("request_payload"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    parent_summary = parent_document.get("summary") if isinstance(parent_document.get("summary"), dict) else {}
    schedule_run_id = parent_document.get("schedule_run_id") or metadata.get("schedule_run_id") or parent_summary.get("schedule_run_id")
    batch_id = parent_document.get("batch_id") or metadata.get("batch_id") or parent_summary.get("batch_id")
    bill_type = str(run.get("bill_type") or job.get("bill_type") or "internal_customer_bill")
    is_fixture = bool(base_summary.get("is_fixture"))

    split_files = _split_generated_files_by_target(generated)

    if not split_files:
        return [parent_document]

    child_documents: list[dict[str, Any]] = []
    for name, uri, target_type, target_id, child_generated in split_files:
        child_summary = _build_split_bill_document_summary(
            base_summary,
            child_generated=child_generated,
            parent_document_id=parent_document.get("id"),
            target_type=target_type,
            target_id=target_id,
            schedule_run_id=schedule_run_id,
            batch_id=batch_id,
        )
        child_status = bill_document_status_for_type(
            bill_type,
            execution_mode,
            child_generated,
            is_fixture=is_fixture,
        )
        idempotency = split_bill_document_idempotency(
            job, run, config, command, target_type=target_type, target_id=target_id,
        )
        document_id = new_id("billdoc")
        cur.execute(
            """
            INSERT INTO bill_documents (
                id, batch_id, schedule_run_id, job_id, billing_run_id,
                bill_type, target_type, target_id, month, status, s3_uri, summary, idempotency_key
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (idempotency_key) DO UPDATE
            SET status = EXCLUDED.status,
                s3_uri = EXCLUDED.s3_uri,
                summary = EXCLUDED.summary,
                job_id = EXCLUDED.job_id,
                billing_run_id = EXCLUDED.billing_run_id,
                schedule_run_id = COALESCE(bill_documents.schedule_run_id, EXCLUDED.schedule_run_id),
                batch_id = COALESCE(bill_documents.batch_id, EXCLUDED.batch_id),
                target_type = EXCLUDED.target_type,
                target_id = EXCLUDED.target_id,
                updated_at = NOW()
            RETURNING *
            """,
            (
                document_id,
                batch_id,
                schedule_run_id,
                job["id"],
                run["id"],
                bill_type,
                target_type,
                target_id,
                run["month"],
                child_status,
                uri,
                psycopg2.extras.Json(child_summary),
                idempotency,
            ),
        )
        child_documents.append(dict(cur.fetchone()))

    split_ids = [doc["id"] for doc in child_documents]
    merged_parent_summary = {
        **json_safe(parent_summary),
        **json_safe(base_summary),
        "split_document_ids": split_ids,
        "split_count": len(split_ids),
    }
    cur.execute(
        """
        UPDATE bill_documents
        SET summary = %s, job_id = COALESCE(job_id, %s), billing_run_id = COALESCE(billing_run_id, %s), updated_at = NOW()
        WHERE id = %s
        RETURNING *
        """,
        (psycopg2.extras.Json(merged_parent_summary), job["id"], run["id"], parent_document["id"]),
    )
    updated_parent = dict(cur.fetchone())
    return [updated_parent, *child_documents]


def insert_file_index(cur, *, filename: str, s3_uri: str, category: str, job_id: str | None = None, session_id: str | None = None, uploaded_by: str = "system", metadata: dict[str, Any] | None = None, content_type: str | None = None, byte_size: int = 0, sha256: str = "") -> dict[str, Any]:
    existing = fetch_one(cur, "SELECT * FROM uploaded_files WHERE s3_uri = %s AND COALESCE(job_id, '') = COALESCE(%s, '') AND COALESCE(session_id, '') = COALESCE(%s, '') LIMIT 1", (s3_uri, job_id, session_id))
    if existing:
        return existing
    file_id = new_id("file")
    cur.execute(
        """
        INSERT INTO uploaded_files (
            id, filename, content_type, byte_size, sha256, category,
            job_id, session_id, s3_uri, uploaded_by, metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (file_id, safe_filename(filename), content_type or content_type_for_filename(filename), byte_size, sha256, slug(category), job_id, session_id, s3_uri, uploaded_by, psycopg2.extras.Json(metadata or {})),
    )
    return dict(cur.fetchone())


def collect_bill_document_reference_artifacts(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Return bill document artifact URIs that can be indexed for Agent context."""
    summary = document.get("summary") if isinstance(document.get("summary"), dict) else {}
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(uri: Any, filename: str, role: str) -> None:
        text = str(uri or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        safe = safe_filename(filename or filename_from_uri(text, "bill-artifact"))
        entries.append(
            {
                "filename": safe,
                "s3_uri": text,
                "content_type": content_type_for_filename(safe),
                "metadata": {"artifact_role": role},
            }
        )

    generated = summary.get("generated_files") if isinstance(summary.get("generated_files"), dict) else {}
    for name, uri in generated.items():
        add(uri, str(name), "generated")

    if document.get("s3_uri"):
        add(document.get("s3_uri"), filename_from_uri(str(document.get("s3_uri")), "bill-document"), "document")

    real_execution = summary.get("real_execution") if isinstance(summary.get("real_execution"), dict) else {}
    for key in ("stdout", "stderr"):
        if real_execution.get(key):
            add(real_execution.get(key), filename_from_uri(str(real_execution.get(key)), f"{key}.log"), key)

    return entries


def _zero_kpi() -> dict[str, float | int]:
    return {
        "total_usd": 0.0,
        "total_calls": 0,
        "unique_users": 0,
        "unique_models": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }


def normalize_kpi_payload(raw: dict[str, Any] | None) -> dict[str, float | int]:
    data = raw or {}
    return {
        "total_usd": float(data.get("total_usd") or 0),
        "total_calls": int(data.get("total_calls") or 0),
        "unique_users": int(data.get("unique_users") or 0),
        "unique_models": int(data.get("unique_models") or 0),
        "total_input_tokens": int(data.get("total_input_tokens") or 0),
        "total_output_tokens": int(data.get("total_output_tokens") or 0),
    }


def run_kpi_preview(
    config: dict[str, Any],
    month: str,
    *,
    channel_id: int | None = None,
    user_id: int | None = None,
    no_cache: bool = False,
) -> dict[str, float | int]:
    timeout_seconds = env_int("WORKBENCH_ATHENA_KPI_TIMEOUT_SECONDS", 120, minimum=10, maximum=600)
    tmp, runtime_dir = prepare_athena_worker_runtime(config)
    try:
        argv = [sys.executable, "bill_cli.py", "kpi", "--month", month, "--json"]
        if no_cache:
            argv.append("--no-cache")
        if channel_id is not None:
            argv.extend(["--channel-id", str(channel_id)])
        if user_id is not None:
            argv.extend(["--user-id", str(user_id)])
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        proc = subprocess.run(
            argv,
            cwd=runtime_dir,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
        if proc.returncode != 0:
            raise HTTPException(status_code=502, detail=f"KPI preview failed: {(proc.stderr or proc.stdout or '').strip()[:500]}")
        line = (proc.stdout or "").strip().splitlines()[-1] if (proc.stdout or "").strip() else "{}"
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            payload = {}
        return normalize_kpi_payload(payload if isinstance(payload, dict) else {})
    finally:
        tmp.cleanup()
