"""Shared test fixtures.

The integration_db fixture creates a disposable Postgres database, applies the
db/init/*.sql schema to it, and points the application at it. If Postgres is not
reachable, integration tests that depend on this fixture are skipped.

Run integration tests with a database up, for example:
    docker compose up -d db
    PG_HOST=localhost pytest -m integration
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent
INIT_DIR = ROOT / "db" / "init"
TEST_DB = "municipal_test"


def _dsn(dbname: str) -> str:
    host = os.environ.get("PG_HOST", "localhost")
    port = os.environ.get("PG_PORT", "5432")
    user = os.environ.get("PG_USER", "app")
    password = os.environ.get("PG_PASSWORD", "app")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def _run_sql_file(conn: psycopg.Connection, path: Path) -> None:
    """Apply a .sql file statement by statement.

    Line comments are stripped first, because they may contain semicolons that
    would otherwise split a statement incorrectly. Our SQL has no `--` inside
    string literals, so this is safe.
    """
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        marker = line.find("--")
        lines.append(line if marker == -1 else line[:marker])
    cleaned = "\n".join(lines)
    for raw in cleaned.split(";"):
        statement = raw.strip()
        if statement:
            conn.execute(statement)


@pytest.fixture(scope="session")
def integration_db():
    # Skip cleanly if no database is reachable.
    try:
        admin = psycopg.connect(_dsn("postgres"), autocommit=True, connect_timeout=3)
    except Exception:  # noqa: BLE001 - any connection problem means "no DB available"
        pytest.skip("Postgres is not available for integration tests")

    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        cur.execute(f"CREATE DATABASE {TEST_DB}")
    admin.close()

    with psycopg.connect(_dsn(TEST_DB), autocommit=True) as conn:
        for sql_file in sorted(INIT_DIR.glob("*.sql")):
            _run_sql_file(conn, sql_file)

    # Point the application at the test database and run lexical-only search
    # (so we do not need the embedding service in tests).
    os.environ["PG_DB"] = TEST_DB
    os.environ["VECTOR_SEARCH_ENABLED"] = "false"

    from municipal_mcp import config, db

    config.get_settings.cache_clear()
    if db._pool is not None:
        db._pool.close()
        db._pool = None

    yield

    if db._pool is not None:
        db._pool.close()
        db._pool = None
    with psycopg.connect(_dsn("postgres"), autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
