"""配置管理路由：bootstrap、配置版本列表。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services.config import (
    get_config_by_version,
    load_seed_config,
    upsert_config_version,
)
from ..services.core import db_conn, read_json

import psycopg2.extras

router = APIRouter(tags=["config"])


class BootstrapRequest(BaseModel):
    repo_root: str | None = None
    created_by: str = "bootstrap"
    force: bool = False


@router.post("/api/config/bootstrap")
def bootstrap_config(req: BootstrapRequest) -> dict[str, Any]:
    pricing, discounts, source = load_seed_config(req.repo_root)
    config_version = upsert_config_version(
        version="local-v0",
        pricing=pricing,
        discounts=discounts,
        created_by=req.created_by,
        source_change_request_id=None,
        force=req.force,
    )
    return {
        "status": "bootstrapped",
        "id": config_version["id"],
        "config_version_id": config_version["id"],
        "version_id": config_version["id"],
        "version_name": config_version["version"],
        "version": config_version,
        "source": source,
    }


@router.post("/api/workbench/e2e/bootstrap")
def bootstrap_config_e2e(payload: dict[str, Any]) -> dict[str, Any]:
    pricing_file = payload.get("pricing_file")
    discounts_file = payload.get("discounts_file")
    if pricing_file and discounts_file and Path(pricing_file).exists() and Path(discounts_file).exists():
        pricing = read_json(Path(pricing_file))
        discounts = read_json(Path(discounts_file))
        source = {"pricing": pricing_file, "discounts": discounts_file}
        config_version = upsert_config_version(
            version=payload.get("config_version", "local-v0"),
            pricing=pricing,
            discounts=discounts,
            created_by="e2e-bootstrap",
            source_change_request_id=None,
            force=bool(payload.get("force", True)),
        )
        return {
            "status": "bootstrapped",
            "id": config_version["id"],
            "config_version_id": config_version["id"],
            "version_id": config_version["id"],
            "version_name": config_version["version"],
            "version": config_version,
            "source": source,
        }
    return bootstrap_config(BootstrapRequest(repo_root=payload.get("repo_root"), created_by="e2e-bootstrap", force=True))


@router.get("/api/config/versions")
def list_config_versions() -> dict[str, Any]:
    from ..services.core import fetch_all
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rows = fetch_all(cur, "SELECT id, version, status, created_by, created_at, activated_at, checksum FROM billing_config_versions ORDER BY created_at DESC LIMIT 50")
    return {"items": rows}
