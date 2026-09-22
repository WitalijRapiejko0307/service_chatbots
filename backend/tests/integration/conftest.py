"""PostgreSQL integration test fixtures."""

from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urlparse

import asyncpg
import pytest

from app.config import Settings, get_settings
from app.storage.postgres import PostgreSQLClient, close_pool

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _database_url() -> str | None:
    """Resolve the database to run integration tests against.

    These tests TRUNCATE tables, so a plain DATABASE_URL is accepted only when the
    database name marks it as a test database. Use TEST_DATABASE_URL to opt in explicitly.
    """
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit

    url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL")
    if not url:
        return None

    database_name = urlparse(url).path.lstrip("/")
    if "test" not in database_name.lower():
        return None
    return url


def _parse_migration_statements() -> list[str]:
    """Split migration SQL files into executable statements (same logic as init_db.py)."""
    statements: list[str] = []
    migration_files = sorted(
        name for name in os.listdir(MIGRATIONS_DIR) if name.endswith(".sql")
    )
    for name in migration_files:
        sql = (MIGRATIONS_DIR / name).read_text(encoding="utf-8")
        for block in sql.split(";"):
            lines: list[str] = []
            for line in block.split("\n"):
                if line.strip().startswith("--"):
                    continue
                lines.append(line)
            stmt = "\n".join(lines).strip()
            if stmt:
                statements.append(stmt + ";")
    return statements


async def _run_migrations(conn: asyncpg.Connection) -> None:
    for stmt in _parse_migration_statements():
        try:
            await conn.execute(stmt)
        except Exception as exc:
            err_msg = str(exc).lower()
            if "already exists" in err_msg:
                continue
            if "duplicate key" in err_msg or "unique constraint" in err_msg:
                continue
            if "extension" in err_msg and "not available" in err_msg:
                continue
            raise


async def _truncate_test_data(conn: asyncpg.Connection) -> None:
    """Remove rows that integration tests create; keep schema and seed data (e.g. crm_stages)."""
    await conn.execute(
        """
        TRUNCATE TABLE
            messages,
            conversations,
            agents
        RESTART IDENTITY CASCADE
        """
    )


@pytest.fixture(scope="session")
async def pg_database() -> AsyncIterator[str]:
    """Connect to PostgreSQL, apply migrations once per session; skip if unavailable."""
    url = _database_url()
    if not url:
        pytest.skip("Set TEST_DATABASE_URL (or a DATABASE_URL pointing at a *test* database)")

    try:
        probe = await asyncpg.connect(url, timeout=5)
    except Exception as exc:
        pytest.skip(f"Cannot connect to PostgreSQL: {exc}")
    else:
        await probe.close()

    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()

    conn = await asyncpg.connect(url, timeout=30)
    try:
        await _run_migrations(conn)
    finally:
        await conn.close()

    yield url

    # The connection pool is closed by the function-scoped pg_client fixture. Closing it
    # here would run on the session finalizer's already-closed event loop.
    get_settings.cache_clear()


@pytest.fixture
async def pg_client(pg_database: str) -> AsyncIterator[PostgreSQLClient]:
    """PostgreSQLClient backed by a real database; data cleaned between tests."""
    await close_pool()
    get_settings.cache_clear()

    settings = Settings()
    client = PostgreSQLClient(settings)

    pool = await asyncpg.create_pool(pg_database, min_size=1, max_size=3, command_timeout=60)
    async with pool.acquire() as conn:
        await _truncate_test_data(conn)
    await pool.close()

    yield client

    await close_pool()
    pool = await asyncpg.create_pool(pg_database, min_size=1, max_size=3, command_timeout=60)
    async with pool.acquire() as conn:
        await _truncate_test_data(conn)
    await pool.close()
