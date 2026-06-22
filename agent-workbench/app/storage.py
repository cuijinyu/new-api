import os
from pathlib import Path

import boto3
from botocore.client import Config

from .env import (
    DEFAULT_WORKBENCH_S3_BUCKET,
    workbench_s3_access_key_id,
    workbench_s3_bucket,
    workbench_s3_endpoint,
    workbench_s3_region,
    workbench_s3_secret_access_key,
)


def bucket_name() -> str:
    return workbench_s3_bucket() or DEFAULT_WORKBENCH_S3_BUCKET


def _client():
    # 使用 S3 兼容客户端：生产连 AWS S3（凭证来自 .env 的 RAW_LOG_S3_* / AWS_*），本地 Docker 连 MinIO。
    endpoint = workbench_s3_endpoint() or None
    access_key = workbench_s3_access_key_id()
    secret_key = workbench_s3_secret_access_key()
    kwargs: dict = {
        "region_name": workbench_s3_region(),
        "config": Config(signature_version="s3v4"),
    }
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
    elif endpoint:
        # MinIO 本地默认账号，仅在显式配置了 endpoint 且未提供 AWS 凭证时使用。
        kwargs["aws_access_key_id"] = os.getenv("WORKBENCH_S3_ACCESS_KEY_ID", "minio")
        kwargs["aws_secret_access_key"] = os.getenv("WORKBENCH_S3_SECRET_ACCESS_KEY", "minio123")
    return boto3.client("s3", **kwargs)


def ensure_bucket() -> None:
    # 仅 MinIO / 本地 S3 兼容端点自动建桶；正式 AWS 桶须预先存在。
    client = _client()
    bucket = bucket_name()
    endpoint = workbench_s3_endpoint() or None
    if not endpoint:
        return
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        client.create_bucket(Bucket=bucket)


def put_text(key: str, body: str, content_type: str = "text/plain; charset=utf-8") -> str:
    ensure_bucket()
    _client().put_object(
        Bucket=bucket_name(),
        Key=key,
        Body=body.encode("utf-8"),
        ContentType=content_type,
    )
    return f"s3://{bucket_name()}/{key}"


def put_file(key: str, path: str | Path, content_type: str | None = None) -> str:
    ensure_bucket()
    extra = {}
    if content_type:
        extra["ContentType"] = content_type
    _client().upload_file(str(path), bucket_name(), key, ExtraArgs=extra or None)
    return f"s3://{bucket_name()}/{key}"
