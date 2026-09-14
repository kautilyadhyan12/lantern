"""Alembic environment: runs migrations over an async (asyncpg) engine."""

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from lantern.db.migrate import DATABASE_URL_ATTRIBUTE

config = context.config
target_metadata = None  # S0.5 points this at the ORM metadata.


def _database_url() -> str:
    url = config.attributes.get(DATABASE_URL_ATTRIBUTE)
    if not isinstance(url, str) or not url:
        raise RuntimeError("no database URL: run migrations via `lantern db upgrade`")
    return url


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine(_database_url(), poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("offline (--sql) migrations are not supported")
asyncio.run(_run_async())
