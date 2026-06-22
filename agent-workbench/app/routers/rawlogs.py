"""S3 日志搜索路由。"""

from __future__ import annotations

import gzip
import json
import os
import re
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.core import clamp_int, json_safe

router = APIRouter(tags=["rawlogs"])


def rawlogs_default_bucket() -> str:
    return (os.getenv("WORKBENCH_RAWLOGS_S3_BUCKET") or os.getenv("ATHENA_RAWLOGS_BUCKET") or os.getenv("ATHENA_LOG_BUCKET") or os.getenv("ATHENA_RESULT_BUCKET") or "ezmodel-log").strip()


def rawlogs_default_prefix() -> str:
    return (os.getenv("WORKBENCH_RAWLOGS_PREFIX") or "llm-raw-logs").strip("/")


def rawlogs_client():
    endpoint = os.getenv("WORKBENCH_RAWLOGS_S3_ENDPOINT") or os.getenv("WORKBENCH_S3_ENDPOINT")
    access_key = os.getenv("WORKBENCH_RAWLOGS_S3_ACCESS_KEY_ID") or os.getenv("WORKBENCH_S3_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("WORKBENCH_RAWLOGS_S3_SECRET_ACCESS_KEY") or os.getenv("WORKBENCH_S3_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")
    kwargs: dict[str, Any] = {"region_name": os.getenv("WORKBENCH_RAWLOGS_S3_REGION") or os.getenv("WORKBENCH_S3_REGION", "us-east-1"), "config": Config(s3={"addressing_style": "path"})}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
    return boto3.client("s3", **kwargs)


def normalize_s3_bucket(bucket: str | None) -> str:
    normalized = (bucket or rawlogs_default_bucket()).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.\-_]{1,253}[A-Za-z0-9]", normalized):
        raise HTTPException(status_code=400, detail="bucket is not a valid S3 bucket name")
    return normalized


def normalize_partition(value: str | None, digits: int, name: str) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    if not re.fullmatch(r"\d{1,4}", text):
        raise HTTPException(status_code=400, detail=f"{name} must be numeric")
    number = int(text)
    if name == "year" and not 2000 <= number <= 2100:
        raise HTTPException(status_code=400, detail="year is outside the supported range")
    if name == "month" and not 1 <= number <= 12:
        raise HTTPException(status_code=400, detail="month must be between 1 and 12")
    if name == "day" and not 1 <= number <= 31:
        raise HTTPException(status_code=400, detail="day must be between 1 and 31")
    if name == "hour" and not 0 <= number <= 23:
        raise HTTPException(status_code=400, detail="hour must be between 0 and 23")
    return f"{number:0{digits}d}"


def normalize_rawlogs_prefix(prefix: str | None, year: str | None = None, month: str | None = None, day: str | None = None, hour: str | None = None) -> str:
    parts = [(prefix or rawlogs_default_prefix()).strip().strip("/")]
    partition_parts = [normalize_partition(year, 4, "year"), normalize_partition(month, 2, "month"), normalize_partition(day, 2, "day"), normalize_partition(hour, 2, "hour")]
    parts.extend([part for part in partition_parts if part])
    normalized = "/".join(part.strip("/") for part in parts if part and part.strip("/"))
    if not normalized:
        raise HTTPException(status_code=400, detail="prefix is required")
    if any(segment in {".", ".."} for segment in normalized.split("/")):
        raise HTTPException(status_code=400, detail="prefix contains unsupported path segments")
    return f"{normalized.rstrip('/')}/"


def s3_error(exc: Exception, action: str) -> HTTPException:
    return HTTPException(status_code=502, detail=f"{action} failed: {exc}")


def rawlog_object_payload(bucket: str, item: dict[str, Any]) -> dict[str, Any]:
    key = item["Key"]
    return {"key": key, "filename": Path(key).name or key.rstrip("/").split("/")[-1], "uri": f"s3://{bucket}/{key}", "size": item.get("Size", 0), "last_modified": json_safe(item.get("LastModified")), "etag": str(item.get("ETag") or "").strip('"'), "storage_class": item.get("StorageClass")}


def iter_rawlog_objects(bucket: str, prefix: str, limit: int) -> list[dict[str, Any]]:
    client = rawlogs_client()
    paginator = client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix, PaginationConfig={"PageSize": min(limit, 1000)}):
            for item in page.get("Contents", []):
                key = str(item.get("Key") or "")
                if key.endswith("/"):
                    continue
                objects.append(rawlog_object_payload(bucket, item))
                if len(objects) >= limit:
                    return objects
    except Exception as exc:
        raise s3_error(exc, "list rawlogs")
    return objects


def read_rawlog_text(bucket: str, key: str, max_bytes: int) -> dict[str, Any]:
    if not key or key.endswith("/"):
        raise HTTPException(status_code=400, detail="key is required")
    max_bytes = clamp_int(max_bytes, 512 * 1024, 4 * 1024, 5 * 1024 * 1024)
    client = rawlogs_client()
    try:
        obj = client.get_object(Bucket=bucket, Key=key)
        content_length = int(obj.get("ContentLength") or 0)
        content_type = obj.get("ContentType") or "application/octet-stream"
        body = obj["Body"]
        compression = "gzip" if key.lower().endswith(".gz") or content_type == "application/gzip" else None
        if compression == "gzip":
            try:
                with gzip.GzipFile(fileobj=body) as gz:
                    raw = gz.read(max_bytes + 1)
            except Exception:
                obj = client.get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{max_bytes}")
                raw = obj["Body"].read(max_bytes + 1)
                compression = "gzip-preview-fallback"
        else:
            raw = body.read(max_bytes + 1)
    except HTTPException:
        raise
    except Exception as exc:
        raise s3_error(exc, "read rawlog object")
    truncated = len(raw) > max_bytes
    raw = raw[:max_bytes]
    text = raw.decode("utf-8", errors="replace")
    return {"text": text, "decoded_bytes": len(raw), "object_size": content_length, "content_type": content_type, "compression": compression, "truncated": truncated or (compression is None and content_length > max_bytes)}


def parse_json_preview(text: str, limit: int = 100) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    errors = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            errors += 1
            if rows:
                break
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
        else:
            rows.append({"value": parsed})
        if len(rows) >= limit:
            break
    if not rows:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                rows = [parsed]
            elif isinstance(parsed, list):
                rows = [item if isinstance(item, dict) else {"value": item} for item in parsed[:limit]]
        except json.JSONDecodeError:
            pass
    columns: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in columns:
                columns.append(key)
            if len(columns) >= 16:
                break
        if len(columns) >= 16:
            break
    return {"rows": rows, "columns": columns, "parse_errors": errors}


class RawLogsSearchRequest(BaseModel):
    bucket: str | None = None
    prefix: str | None = None
    year: str | None = None
    month: str | None = None
    day: str | None = None
    hour: str | None = None
    query: str
    limit: int = 50
    object_limit: int = 50
    max_bytes_per_object: int = 256 * 1024


@router.get("/api/rawlogs/config")
def rawlogs_config_endpoint() -> dict[str, Any]:
    return {"bucket": rawlogs_default_bucket(), "prefix": rawlogs_default_prefix(), "uri_template": f"s3://{rawlogs_default_bucket()}/{rawlogs_default_prefix()}/{{year}}/{{month}}/{{day}}/{{hour}}/", "max_preview_bytes": 5 * 1024 * 1024, "max_search_objects": 200}


@router.get("/api/rawlogs/objects")
def list_rawlogs_objects(bucket: str | None = None, prefix: str | None = None, year: str | None = None, month: str | None = None, day: str | None = None, hour: str | None = None, limit: int = 100, continuation_token: str | None = None, recursive: bool = False) -> dict[str, Any]:
    normalized_bucket = normalize_s3_bucket(bucket)
    normalized_prefix = normalize_rawlogs_prefix(prefix, year, month, day, hour)
    max_keys = clamp_int(limit, 100, 1, 1000)
    request: dict[str, Any] = {"Bucket": normalized_bucket, "Prefix": normalized_prefix, "MaxKeys": max_keys}
    if continuation_token:
        request["ContinuationToken"] = continuation_token
    if not recursive:
        request["Delimiter"] = "/"
    try:
        page = rawlogs_client().list_objects_v2(**request)
    except Exception as exc:
        raise s3_error(exc, "list rawlogs")
    return {
        "bucket": normalized_bucket, "prefix": normalized_prefix, "recursive": recursive,
        "common_prefixes": [item.get("Prefix") for item in page.get("CommonPrefixes", []) if item.get("Prefix")],
        "items": [rawlog_object_payload(normalized_bucket, item) for item in page.get("Contents", []) if not str(item.get("Key") or "").endswith("/")],
        "next_token": page.get("NextContinuationToken"),
    }


@router.get("/api/rawlogs/object")
def preview_rawlog_object(bucket: str | None = None, key: str | None = None, max_bytes: int = 512 * 1024) -> dict[str, Any]:
    normalized_bucket = normalize_s3_bucket(bucket)
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    payload = read_rawlog_text(normalized_bucket, key, max_bytes)
    preview = parse_json_preview(payload["text"])
    return {"bucket": normalized_bucket, "key": key, "uri": f"s3://{normalized_bucket}/{key}", **payload, **preview}


@router.post("/api/rawlogs/search")
def search_rawlogs(req: RawLogsSearchRequest) -> dict[str, Any]:
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    normalized_bucket = normalize_s3_bucket(req.bucket)
    normalized_prefix = normalize_rawlogs_prefix(req.prefix, req.year, req.month, req.day, req.hour)
    limit = clamp_int(req.limit, 50, 1, 200)
    object_limit = clamp_int(req.object_limit, 50, 1, 200)
    max_bytes = clamp_int(req.max_bytes_per_object, 256 * 1024, 4 * 1024, 1024 * 1024)
    lowered_query = query.lower()
    matches: list[dict[str, Any]] = []
    scanned = 0
    for item in iter_rawlog_objects(normalized_bucket, normalized_prefix, object_limit):
        scanned += 1
        text_payload = read_rawlog_text(normalized_bucket, item["key"], max_bytes)
        lines = text_payload["text"].splitlines() or [text_payload["text"]]
        for line_number, line in enumerate(lines, start=1):
            position = line.lower().find(lowered_query)
            if position < 0:
                continue
            start = max(0, position - 90)
            end = min(len(line), position + len(query) + 160)
            matches.append({"key": item["key"], "uri": item["uri"], "line": line_number, "snippet": line[start:end], "size": item["size"], "last_modified": item["last_modified"], "truncated_object": text_payload["truncated"]})
            if len(matches) >= limit:
                return {"bucket": normalized_bucket, "prefix": normalized_prefix, "query": query, "scanned_objects": scanned, "matches": matches, "truncated": True}
    return {"bucket": normalized_bucket, "prefix": normalized_prefix, "query": query, "scanned_objects": scanned, "matches": matches, "truncated": False}
