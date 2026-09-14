"""Typed runtime configuration from the environment (prefix ``LANTERN_``) and ``.env``.

S0.1 needs only the database URL; S0.5 grows this into the full settings model.
"""

from typing import Final

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ASYNC_DRIVER: Final = "postgresql+asyncpg"


class Settings(BaseSettings):
    # hide_input_in_errors: a bad URL must not echo its password into a ValidationError.
    model_config = SettingsConfigDict(
        env_prefix="LANTERN_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    database_url: SecretStr

    @field_validator("database_url")
    @classmethod
    def _require_async_driver(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
        except ArgumentError:
            raise ValueError("database_url is not a valid SQLAlchemy URL") from None
        if url.drivername != ASYNC_DRIVER:
            raise ValueError(f"database_url must use {ASYNC_DRIVER!r}, got {url.drivername!r}")
        return value
