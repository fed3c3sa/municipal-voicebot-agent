"""Database access: a small psycopg connection pool and a couple of helpers.

We deliberately keep this thin. Tools open a connection from the pool, run a
query with dict rows, and close it. SQL lives next to the code that uses it.
Vectors are passed as text literals and cast with ::vector, so we do not need
any extra pgvector Python binding.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import get_settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Return the process-wide connection pool, creating it on first use."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(conninfo=settings.pg_dsn, min_size=1, max_size=5, open=True)
    return _pool


def close_pool() -> None:
    """Close the connection pool, if one was created. Call this from short-lived scripts."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    """Yield a pooled connection with dict-style rows."""
    with get_pool().connection() as conn:
        conn.row_factory = dict_row
        yield conn


def vector_literal(values: Sequence[float]) -> str:
    """Format a float sequence as a pgvector text literal, e.g. '[0.1,0.2]'."""
    return "[" + ",".join(repr(float(v)) for v in values) + "]"
