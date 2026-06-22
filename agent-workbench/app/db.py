import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

import psycopg2
import psycopg2.extras


def database_url() -> str:
    # 小工具模块默认连接本地 Workbench DB；主应用也可以通过 DATABASE_URL 覆盖。
    return os.getenv(
        "DATABASE_URL",
        "postgresql://workbench:workbench@localhost:5432/agent_workbench",
    )


@contextmanager
def connect():
    # 所有 DB 操作统一在这里提交/回滚，避免脚本型调用遗漏事务处理。
    conn = psycopg2.connect(database_url())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    # schema.sql 设计为幂等执行，适合本地 Docker 反复重建验证。
    schema = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(schema.read_text(encoding="utf-8"))


def fetchone(query: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row else None


def fetchall(query: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]


def execute(query: str, params: Iterable[Any] = ()) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)


def as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
