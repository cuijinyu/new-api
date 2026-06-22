"""计费口径版本管理：bootstrap / upsert / 版本递增。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import psycopg2.extras
from fastapi import HTTPException

from .artifacts import artifacts
from .core import (
    WORKBENCH_ROOT,
    checksum_config,
    fetch_all,
    fetch_one,
    json_safe,
    new_id,
    read_json,
    utc_now_iso,
)


def get_config_by_version(cur, version: str) -> dict[str, Any] | None:
    return normalize_config_row(fetch_one(cur, "SELECT * FROM billing_config_versions WHERE version = %s OR id = %s", (version, version)))


def get_latest_config(cur) -> dict[str, Any]:
    row = fetch_one(cur, """
        SELECT * FROM billing_config_versions
        WHERE status = 'active'
        ORDER BY activated_at DESC NULLS LAST, created_at DESC
        LIMIT 1
    """)
    if not row:
        raise HTTPException(status_code=409, detail="no active config version found; run /api/config/bootstrap first")
    return normalize_config_row(row)


def normalize_config_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    if not row.get("pricing_snapshot") and row.get("pricing_json"):
        row["pricing_snapshot"] = row["pricing_json"]
    if not row.get("discounts_snapshot") and row.get("discounts_json"):
        row["discounts_snapshot"] = row["discounts_json"]
    return row


def ensure_config_version(version: str) -> None:
    from .core import db_conn
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if get_config_by_version(cur, version):
                return
            if not fetch_all(cur, "SELECT id FROM billing_config_versions LIMIT 1"):
                pricing, discounts, _ = load_seed_config(None)
                insert_config_version(cur, "local-v0", pricing, discounts, "auto-bootstrap", None)
                conn.commit()
                if get_config_by_version(cur, version):
                    return
            if not get_config_by_version(cur, version):
                raise HTTPException(status_code=409, detail=f"config version {version} not found; run /api/config/bootstrap first")


def next_local_version(cur) -> str:
    rows = fetch_all(cur, "SELECT version FROM billing_config_versions WHERE version LIKE 'local-v%%'")
    max_n = 0
    for row in rows:
        match = re.fullmatch(r"local-v(\d+)", row["version"])
        if match:
            max_n = max(max_n, int(match.group(1)))
    return f"local-v{max_n + 1}"


def deactivate_other_versions(cur, keep_id: str) -> None:
    """保证全局只有一个生效配置：把除 keep_id 外的所有行置为 inactive。"""
    cur.execute("UPDATE billing_config_versions SET status = 'inactive' WHERE id <> %s AND status = 'active'", (keep_id,))


def insert_config_version(cur, version: str, pricing: dict[str, Any], discounts: dict[str, Any], created_by: str, source_change_request_id: str | None) -> dict[str, Any]:
    config_id = new_id("cfg")
    digest = checksum_config(pricing, discounts)
    prefix = f"config/{version}"
    pricing_uri = artifacts.put_json(f"{prefix}/pricing.json", pricing)
    discounts_uri = artifacts.put_json(f"{prefix}/discounts.json", discounts)
    manifest = {
        "id": config_id, "version": version, "checksum": digest,
        "pricing_snapshot_s3_uri": pricing_uri, "discounts_snapshot_s3_uri": discounts_uri,
        "source_change_request_id": source_change_request_id, "created_by": created_by, "created_at": utc_now_iso(),
    }
    manifest_uri = artifacts.put_json(f"{prefix}/config_version.json", manifest)
    cur.execute(
        """
        INSERT INTO billing_config_versions (
            id, version, status, pricing_snapshot, discounts_snapshot,
            pricing_json, discounts_json,
            pricing_snapshot_s3_uri, discounts_snapshot_s3_uri, manifest_s3_uri,
            source_change_request_id, created_by, activated_by, activated_at,
            checksum, metadata
        )
        VALUES (%s, %s, 'active', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s)
        RETURNING *
        """,
        (config_id, version, psycopg2.extras.Json(pricing), psycopg2.extras.Json(discounts),
         psycopg2.extras.Json(pricing), psycopg2.extras.Json(discounts),
         pricing_uri, discounts_uri, manifest_uri, source_change_request_id,
         created_by, created_by, digest,
         psycopg2.extras.Json({"snapshot_prefix": artifacts.uri_for_prefix(prefix)})),
    )
    row = dict(cur.fetchone())
    deactivate_other_versions(cur, row["id"])
    return row


def update_config_version(cur, existing: dict[str, Any], pricing: dict[str, Any], discounts: dict[str, Any], updated_by: str) -> dict[str, Any]:
    digest = checksum_config(pricing, discounts)
    prefix = f"config/{existing['version']}"
    pricing_uri = artifacts.put_json(f"{prefix}/pricing.json", pricing)
    discounts_uri = artifacts.put_json(f"{prefix}/discounts.json", discounts)
    manifest = {"id": existing["id"], "version": existing["version"], "checksum": digest,
                "pricing_snapshot_s3_uri": pricing_uri, "discounts_snapshot_s3_uri": discounts_uri,
                "updated_by": updated_by, "updated_at": utc_now_iso()}
    manifest_uri = artifacts.put_json(f"{prefix}/config_version.json", manifest)
    cur.execute(
        """
        UPDATE billing_config_versions
        SET pricing_snapshot = %s, discounts_snapshot = %s, pricing_json = %s, discounts_json = %s,
            pricing_snapshot_s3_uri = %s, discounts_snapshot_s3_uri = %s, manifest_s3_uri = %s,
            activated_by = %s, activated_at = NOW(), checksum = %s, metadata = %s
        WHERE id = %s
        RETURNING *
        """,
        (psycopg2.extras.Json(pricing), psycopg2.extras.Json(discounts),
         psycopg2.extras.Json(pricing), psycopg2.extras.Json(discounts),
         pricing_uri, discounts_uri, manifest_uri, updated_by, digest,
         psycopg2.extras.Json({"snapshot_prefix": artifacts.uri_for_prefix(prefix), "force_refreshed": True}),
         existing["id"]),
    )
    row = dict(cur.fetchone())
    deactivate_other_versions(cur, row["id"])
    return row


def upsert_config_version(version: str, pricing: dict[str, Any], discounts: dict[str, Any], created_by: str, source_change_request_id: str | None, force: bool) -> dict[str, Any]:
    from .core import db_conn
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            existing = get_config_by_version(cur, version)
            if existing and not force:
                return existing
            if existing and force:
                return update_config_version(cur, existing, pricing, discounts, created_by)
            return insert_config_version(cur, version, pricing, discounts, created_by, source_change_request_id)


def update_active_discounts(discounts: dict[str, Any], updated_by: str) -> dict[str, Any]:
    """折扣全局化：原地覆盖当前生效配置的折扣，不生成新版本。

    若系统中尚无任何配置，则自动 bootstrap 一份 local-v0 再写入。
    """
    from .core import db_conn
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            try:
                current = get_latest_config(cur)
            except HTTPException:
                pricing_seed, discounts_seed, _ = load_seed_config(None)
                current = insert_config_version(cur, "local-v0", pricing_seed, discounts_seed, "auto-bootstrap", None)
            pricing = current.get("pricing_snapshot") if isinstance(current.get("pricing_snapshot"), dict) else {}
            updated = update_config_version(cur, current, pricing, discounts, updated_by)
            conn.commit()
            return updated


def update_active_pricing(pricing: dict[str, Any], updated_by: str) -> dict[str, Any]:
    """Overwrite the active pricing snapshot in place, preserving discounts."""
    from .core import db_conn
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            try:
                current = get_latest_config(cur)
            except HTTPException:
                pricing_seed, discounts_seed, _ = load_seed_config(None)
                current = insert_config_version(cur, "local-v0", pricing_seed, discounts_seed, "auto-bootstrap", None)
            discounts = current.get("discounts_snapshot") if isinstance(current.get("discounts_snapshot"), dict) else {}
            updated = update_config_version(cur, current, pricing, discounts, updated_by)
            conn.commit()
            return updated


def collapse_to_single_active(updated_by: str = "collapse") -> dict[str, Any]:
    """把历史上多条 status='active' 收敛为唯一生效：保留最新一条，其余置 inactive。"""
    from .core import db_conn
    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            actives = fetch_all(cur, """
                SELECT id, version, activated_at, created_at FROM billing_config_versions
                WHERE status = 'active'
                ORDER BY activated_at DESC NULLS LAST, created_at DESC
            """)
            if not actives:
                return {"kept": None, "deactivated": 0}
            keep_id = actives[0]["id"]
            cur.execute("UPDATE billing_config_versions SET status = 'inactive' WHERE id <> %s AND status = 'active'", (keep_id,))
            deactivated = cur.rowcount
            conn.commit()
            return {"kept": actives[0]["version"], "kept_id": keep_id, "deactivated": deactivated}


def load_seed_config(repo_root: str | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    root = Path(repo_root or os.getenv("REPO_ROOT") or "/repo")
    pricing_path = root / "scripts" / "athena" / "pricing.json"
    discounts_path = root / "scripts" / "athena" / "discounts.json"
    if pricing_path.exists() and discounts_path.exists():
        return read_json(pricing_path), read_json(discounts_path), {"pricing": str(pricing_path), "discounts": str(discounts_path)}
    pricing_env = os.getenv("WORKBENCH_PRICING_JSON")
    discounts_env = os.getenv("WORKBENCH_DISCOUNTS_JSON")
    if pricing_env and discounts_env:
        return json.loads(pricing_env), json.loads(discounts_env), {"pricing": "env", "discounts": "env"}
    workspace_root = WORKBENCH_ROOT.parent
    workspace_pricing = workspace_root / "scripts" / "athena" / "pricing.json"
    workspace_discounts = workspace_root / "scripts" / "athena" / "discounts.json"
    if workspace_pricing.exists() and workspace_discounts.exists():
        return read_json(workspace_pricing), read_json(workspace_discounts), {"pricing": str(workspace_pricing), "discounts": str(workspace_discounts)}
    raise HTTPException(status_code=400, detail="seed config not found; set REPO_ROOT or WORKBENCH_PRICING_JSON/WORKBENCH_DISCOUNTS_JSON")
