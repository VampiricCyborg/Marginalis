"""Postgres connection and plain numbered-SQL migrations (db/migrations/NNN_*.sql)."""

from __future__ import annotations

import logging
import os

import psycopg
from dotenv import load_dotenv

from marginalis.config import ROOT

log = logging.getLogger(__name__)

MIGRATIONS_DIR = ROOT / "db" / "migrations"
DEFAULT_URL = "postgresql://marginalis:marginalis@localhost:5433/marginalis"


def database_url() -> str:
    load_dotenv()
    return os.environ.get("DATABASE_URL", "").strip() or DEFAULT_URL


def connect(url: str | None = None) -> psycopg.Connection:
    return psycopg.connect(url or database_url())


def migrate(conn: psycopg.Connection) -> list[str]:
    """Apply unapplied migrations in filename order, each in its own transaction."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    conn.commit()
    done = {r[0] for r in conn.execute("SELECT filename FROM schema_migrations")}
    applied = []
    for path in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")):
        if path.name in done:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
        log.info("applied %s", path.name)
        applied.append(path.name)
    return applied
