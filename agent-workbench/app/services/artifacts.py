"""产物归档 S3/本地文件系统，从 main.py 的 ArtifactStore 类提取。"""

from __future__ import annotations

import json
import mimetypes
import os
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import quote

import boto3
from botocore.config import Config
from fastapi.responses import StreamingResponse

from ..env import (
    workbench_s3_access_key_id,
    workbench_s3_bucket,
    workbench_s3_endpoint,
    workbench_s3_region,
    workbench_s3_secret_access_key,
)
from .core import json_safe


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def content_disposition(filename: str, disposition: str = "attachment") -> str:
    """Build a Content-Disposition header value safe for non-ASCII filenames.

    Emits both an ASCII ``filename`` fallback and an RFC 5987 ``filename*``
    so that downloads of Chinese-named artifacts keep their original name.
    """
    safe = (filename or "").strip() or "download"
    ascii_fallback = safe.encode("ascii", "ignore").decode("ascii").strip() or "download"
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(safe)}"


def stream_download_response(
    store: "ArtifactStore",
    target_uri: str,
    filename: str,
    *,
    inline: bool = False,
    content_type: str | None = None,
) -> StreamingResponse:
    """Stream object bytes through API so browsers download without redirecting to S3."""
    data = store.get_bytes(target_uri)
    disp = "inline" if inline else "attachment"
    guessed, _ = mimetypes.guess_type(filename)
    media_type = content_type or guessed or "application/octet-stream"
    return StreamingResponse(
        iter([data]),
        media_type=media_type,
        headers={"Content-Disposition": content_disposition(filename, disposition=disp)},
    )


class ArtifactStore:
    def __init__(
        self,
        *,
        bucket: str | None = None,
        endpoint: str | None = None,
        region: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        local_dir: str | None = None,
    ) -> None:
        self.bucket = bucket if bucket is not None else workbench_s3_bucket() or None
        self.endpoint = endpoint if endpoint is not None else workbench_s3_endpoint() or None
        self.region = region or workbench_s3_region()
        self.access_key_id = access_key_id or workbench_s3_access_key_id() or None
        self.secret_access_key = secret_access_key or workbench_s3_secret_access_key() or None
        self.local_dir = Path(local_dir or os.getenv("WORKBENCH_ARTIFACT_DIR", "/tmp/agent-workbench-artifacts"))
        self._client = None
        self._bucket_checked = False

    @property
    def enabled(self) -> bool:
        return bool(self.bucket)

    @property
    def client(self):
        if self._client is None:
            kwargs: dict[str, Any] = {
                "region_name": self.region,
                "config": Config(
                    s3={"addressing_style": "path"},
                    connect_timeout=_env_float("WORKBENCH_S3_CONNECT_TIMEOUT_SECONDS", 10.0),
                    read_timeout=_env_float("WORKBENCH_S3_READ_TIMEOUT_SECONDS", 120.0),
                    retries={
                        "max_attempts": _env_int("WORKBENCH_S3_MAX_ATTEMPTS", 3),
                        "mode": "standard",
                    },
                ),
            }
            if self.endpoint:
                kwargs["endpoint_url"] = self.endpoint
            if self.access_key_id and self.secret_access_key:
                kwargs["aws_access_key_id"] = self.access_key_id
                kwargs["aws_secret_access_key"] = self.secret_access_key
            self._client = boto3.client("s3", **kwargs)
        return self._client

    def ensure_bucket(self) -> None:
        if not self.enabled or self._bucket_checked:
            return
        # 仅 MinIO / 本地 S3 兼容端点自动建桶；正式 AWS 桶须预先存在。
        if self.endpoint:
            try:
                self.client.head_bucket(Bucket=self.bucket)
            except Exception:
                self.client.create_bucket(Bucket=self.bucket)
        self._bucket_checked = True

    def uri_for_prefix(self, prefix: str) -> str:
        prefix = prefix.strip("/")
        if self.enabled:
            return f"s3://{self.bucket}/{prefix}/"
        return f"file://{(self.local_dir / prefix).as_posix()}/"

    def put_json(self, key: str, data: Any) -> str:
        return self.put_text(key, json.dumps(json_safe(data), ensure_ascii=False, indent=2, sort_keys=True), "application/json")

    def put_text(self, key: str, body: str, content_type: str = "text/plain; charset=utf-8") -> str:
        key = key.strip("/")
        if self.enabled:
            self.ensure_bucket()
            self.client.put_object(Bucket=self.bucket, Key=key, Body=body.encode("utf-8"), ContentType=content_type)
            return f"s3://{self.bucket}/{key}"
        path = self.local_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return f"file://{path.as_posix()}"

    def put_bytes(self, key: str, body: bytes, content_type: str = "application/octet-stream") -> str:
        key = key.strip("/")
        if self.enabled:
            self.ensure_bucket()
            self.client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)
            return f"s3://{self.bucket}/{key}"
        path = self.local_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return f"file://{path.as_posix()}"

    def put_file(self, key: str, source: Path, content_type: str = "application/octet-stream") -> str:
        key = key.strip("/")
        source = Path(source)
        if self.enabled:
            self.ensure_bucket()
            with source.open("rb") as handle:
                self.client.upload_fileobj(
                    handle,
                    self.bucket,
                    key,
                    ExtraArgs={"ContentType": content_type},
                )
            return f"s3://{self.bucket}/{key}"
        path = self.local_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, path)
        return f"file://{path.as_posix()}"

    def list_prefix(self, prefix: str) -> list[str]:
        prefix = prefix.strip("/") + "/"
        if self.enabled:
            paginator = self.client.get_paginator("list_objects_v2")
            keys: list[str] = []
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                keys.extend(f"s3://{self.bucket}/{item['Key']}" for item in page.get("Contents", []))
            return keys
        root = self.local_dir / prefix
        if not root.exists():
            return []
        return [f"file://{path.as_posix()}" for path in root.rglob("*") if path.is_file()]

    def get_bytes(self, uri: str) -> bytes:
        if uri.startswith("s3://"):
            rest = uri.removeprefix("s3://")
            bucket, _, key = rest.partition("/")
            obj = self.client.get_object(Bucket=bucket, Key=key)
            return obj["Body"].read()
        if uri.startswith("file://"):
            return Path(uri.removeprefix("file://")).read_bytes()
        return (self.local_dir / uri.strip("/")).read_bytes()

    def parse_uri(self, uri: str) -> tuple[str, str]:
        """Return (kind, location) where kind is 's3' or 'file'."""
        if uri.startswith("s3://"):
            rest = uri.removeprefix("s3://")
            bucket, _, key = rest.partition("/")
            return "s3", f"{bucket}/{key}"
        if uri.startswith("file://"):
            return "file", uri.removeprefix("file://")
        return "file", str((self.local_dir / uri.strip("/")).resolve())

    def download_filename(self, uri: str, fallback: str = "download") -> str:
        clean = uri.split("?")[0].rstrip("/")
        name = clean.rsplit("/", 1)[-1] if "/" in clean else fallback
        return name or fallback

    @staticmethod
    def split_s3_uri(uri: str) -> tuple[str, str]:
        """Split an ``s3://bucket/key`` uri into ``(bucket, key)``.

        Returns empty strings for missing parts when the uri is malformed or
        not an s3 uri, so callers can fall back gracefully.
        """
        if not uri or not uri.startswith("s3://"):
            return "", ""
        rest = uri.removeprefix("s3://")
        bucket, _, key = rest.partition("/")
        return bucket, key

    def presign_url(
        self,
        uri: str,
        expires: int = 86400,
        filename: str | None = None,
        disposition: str = "attachment",
    ) -> str | None:
        """Return a presigned GET URL for an ``s3://`` uri.

        Returns ``None`` when the uri is not an s3 object or when no S3 backend
        is configured (local ``file://`` dev mode); callers then fall back to
        streaming the bytes directly.
        """
        if not self.enabled:
            return None
        bucket, key = self.split_s3_uri(uri)
        if not bucket or not key:
            return None
        params: dict[str, Any] = {"Bucket": bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = content_disposition(filename, disposition=disposition)
        try:
            return self.client.generate_presigned_url("get_object", Params=params, ExpiresIn=int(expires))
        except Exception:
            return None


artifacts = ArtifactStore()


def _build_billing_store() -> ArtifactStore:
    """账单产物专用存储：默认指向独立账单桶（生产为真实 AWS），未配置时回退到主 store。

    通过 WORKBENCH_BILLING_S3_* 覆盖；凭证/区域缺省继承 AWS_*/RAW_LOG_S3_*，
    便于把账单单独存到与日志桶分离的专用桶。
    """
    bucket = os.getenv("WORKBENCH_BILLING_S3_BUCKET")
    if not bucket:
        return artifacts
    return ArtifactStore(
        bucket=bucket,
        endpoint=os.getenv("WORKBENCH_BILLING_S3_ENDPOINT") or workbench_s3_endpoint() or None,
        region=os.getenv("WORKBENCH_BILLING_S3_REGION") or workbench_s3_region(),
        access_key_id=(
            os.getenv("WORKBENCH_BILLING_S3_ACCESS_KEY_ID")
            or workbench_s3_access_key_id()
            or None
        ),
        secret_access_key=(
            os.getenv("WORKBENCH_BILLING_S3_SECRET_ACCESS_KEY")
            or workbench_s3_secret_access_key()
            or None
        ),
        local_dir=os.getenv("WORKBENCH_BILLING_ARTIFACT_DIR"),
    )


billing_artifacts = _build_billing_store()
