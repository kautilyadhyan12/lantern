"""Alembic's async engine bridge; the URL remains an in-memory secret."""

import asyncio

from alembic import context
from pydantic import SecretStr
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    secret: SecretStr = context.config.attributes["database_url"]
    engine = create_async_engine(
        secret.get_secret_value(),
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"timeout": 5, "command_timeout": 10},
    )
    try:
        async with asyncio.timeout(15), engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


asyncio.run(run_async_migrations())
