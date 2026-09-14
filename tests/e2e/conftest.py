"""Fixtures for end-to-end tests that need the compose Postgres (`make db`)."""

import asyncio

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from lantern.config import Settings


async def _ping(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def database_url() -> str:
    """URL of the dev/CI Postgres. Fails loudly (never skips) when it is not available."""
    try:
        url = Settings().database_url.get_secret_value()
    except ValidationError as exc:
        pytest.fail(
            f"LANTERN_DATABASE_URL missing or invalid ({exc.error_count()} error(s)): "
            "copy .env.example to .env, set the password, then run `make db`",
            pytrace=False,
        )
    try:
        asyncio.run(_ping(url))
    except OSError as exc:
        pytest.fail(f"Postgres unreachable ({type(exc).__name__}): run `make db`", pytrace=False)
    return url
