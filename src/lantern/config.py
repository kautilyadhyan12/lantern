"""S0.1 settings boundary, awaiting implementation."""
from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: SecretStr

    def __init__(self, **values: object) -> None:
        raise NotImplementedError("S0.1: not implemented yet")

    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        raise NotImplementedError("S0.1: not implemented yet")
