"""Typed runtime configuration (stub; S0.1 implements database_url only)."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: SecretStr

    def __init__(self, **values: object) -> None:
        raise NotImplementedError("S0.1: Settings not implemented yet")
