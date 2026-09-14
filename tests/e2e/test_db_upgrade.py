"""S0.1-AC3 against a real Postgres (compose `db` locally, service container in CI)."""

import asyncio
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from lantern import cli


async def _scalar(url: str, sql: str) -> object:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return (await conn.execute(text(sql))).scalar_one()
    finally:
        await engine.dispose()


async def _autocommit(url: str, sql: str) -> None:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text(sql))
    finally:
        await engine.dispose()


@pytest.fixture
def fresh_database_url(database_url: str) -> Iterator[str]:
    """A throwaway database on the configured server, dropped afterwards."""
    name = f"lantern_test_{uuid.uuid4().hex[:12]}"
    asyncio.run(_autocommit(database_url, f'CREATE DATABASE "{name}"'))
    try:
        yield make_url(database_url).set(database=name).render_as_string(hide_password=False)
    finally:
        asyncio.run(_autocommit(database_url, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.mark.ac("S0.1-AC3")
def test_server_is_postgres_16_with_pgvector(database_url: str) -> None:
    version = asyncio.run(_scalar(database_url, "SHOW server_version_num"))
    assert isinstance(version, str)
    assert 160000 <= int(version) < 170000, f"expected Postgres 16, got {version}"
    available = asyncio.run(
        _scalar(database_url, "SELECT count(*) FROM pg_available_extensions WHERE name = 'vector'")
    )
    assert available == 1, "pgvector extension is not available on the server"


@pytest.mark.ac("S0.1-AC3")
def test_lantern_db_upgrade_applies_baseline(
    fresh_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANTERN_DATABASE_URL", fresh_database_url)
    assert cli.main(["db", "upgrade"]) == 0
    assert asyncio.run(_scalar(fresh_database_url, "SELECT version_num FROM alembic_version")) == (
        "0001"
    )
    # Idempotent: a second upgrade is a no-op.
    assert cli.main(["db", "upgrade"]) == 0
    # pgvector can be enabled and used in a fresh database.
    asyncio.run(_autocommit(fresh_database_url, "CREATE EXTENSION IF NOT EXISTS vector"))
    vec = asyncio.run(_scalar(fresh_database_url, "SELECT '[1,2,3]'::vector::text"))
    assert vec == "[1,2,3]"
