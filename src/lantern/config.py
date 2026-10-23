"""Typed environment settings; secret values never appear in validation text."""

from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LANTERN_", extra="ignore", hide_input_in_errors=True
    )
    database_url: SecretStr

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            url = urlsplit(value.get_secret_value())
            valid = (
                url.scheme == "postgresql+asyncpg"
                and url.hostname
                and url.path.strip("/")
                and (url.port is None or url.port > 0)
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("Use a postgresql+asyncpg database URL with a host and database name.")
        return value
