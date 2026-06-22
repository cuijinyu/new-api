"""加载仓库根目录 .env，并提供 S3 配置的统一回退链。"""

from __future__ import annotations

import os
from pathlib import Path

_DOTENV_LOADED = False
DEFAULT_WORKBENCH_S3_BUCKET = "ezmodel-agent-workbench-prod"


def repo_root() -> Path:
    # agent-workbench/app/env.py -> new-api/
    return Path(__file__).resolve().parents[2]


def load_repo_dotenv() -> None:
    """加载仓库根 .env；不覆盖进程里已存在的环境变量。"""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    dotenv_path = repo_root() / ".env"
    if not dotenv_path.is_file():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def workbench_s3_bucket() -> str:
    # 资料库/产物使用独立桶，不回退到 RAW_LOG / Athena 日志桶。
    return env_first("WORKBENCH_S3_BUCKET", default=DEFAULT_WORKBENCH_S3_BUCKET)


def workbench_s3_region() -> str:
    return env_first(
        "WORKBENCH_S3_REGION",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "RAW_LOG_S3_REGION",
        default="ap-southeast-1",
    )


def workbench_s3_endpoint() -> str:
    return env_first("WORKBENCH_S3_ENDPOINT", "RAW_LOG_S3_ENDPOINT", default="")


def workbench_s3_access_key_id() -> str:
    return env_first(
        "WORKBENCH_S3_ACCESS_KEY_ID",
        "RAW_LOG_S3_ACCESS_KEY_ID",
        "AWS_ACCESS_KEY_ID",
        default="",
    )


def workbench_s3_secret_access_key() -> str:
    return env_first(
        "WORKBENCH_S3_SECRET_ACCESS_KEY",
        "RAW_LOG_S3_SECRET_ACCESS_KEY",
        "AWS_SECRET_ACCESS_KEY",
        default="",
    )
