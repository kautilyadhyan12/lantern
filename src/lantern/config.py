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


class AppSettings(BaseSettings):
    """Settings for running investigations. Keys come only from the environment."""

    model_config = SettingsConfigDict(
        env_prefix="LANTERN_", extra="ignore", hide_input_in_errors=True
    )
    tavily_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-120b"
    cerebras_api_key: SecretStr | None = None
    cerebras_model: str = "gpt-oss-120b"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    data_dir: str = "var"
    user_agent: str = "LanternResearch/0.1 (+https://github.com/kautilyadhyan12/lantern)"
    daily_run_limit: int = 10
    max_questions: int = 4
    max_pages: int = 10
    max_llm_calls: int = 40
    social_enabled: bool = True
    max_posts: int = 8
    mastodon_instance: str = "https://mastodon.social"
