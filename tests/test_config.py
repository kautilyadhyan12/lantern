"""Settings accept one database driver and never expose credentials."""

import string

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import SecretStr, ValidationError

from lantern.config import Settings

FAKE_URL = "postgresql+asyncpg://example:synthetic-only@127.0.0.1:5434/lantern"
SEGMENT = st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=20)


@pytest.mark.ac("S0.1-AC3")
def test_database_url_valid_driver(monkeypatch):
    monkeypatch.setenv("LANTERN_DATABASE_URL", FAKE_URL)
    settings = Settings()
    assert isinstance(settings.database_url, SecretStr)
    assert settings.database_url.get_secret_value() == FAKE_URL
    assert "synthetic-only" not in repr(settings)
    assert "synthetic-only" not in settings.model_dump_json()


@pytest.mark.ac("S0.1-AC3")
@pytest.mark.parametrize("driver", ["postgresql", "postgresql+psycopg", "sqlite", "mysql"])
def test_reject_other_drivers(driver):
    with pytest.raises(ValidationError):
        Settings(database_url=FAKE_URL.replace("postgresql+asyncpg", driver))


@pytest.mark.ac("S0.1-AC3")
@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "not a URL",
        "postgresql+asyncpg:///db",
        "postgresql+asyncpg://localhost",
        "postgresql+asyncpg://localhost:bad/db",
    ],
)
def test_missing_or_malformed_url(value):
    with pytest.raises(ValidationError):
        Settings(**({} if value is None else {"database_url": value}))


@pytest.mark.ac("S0.1-AC3")
def test_secrets_hidden_in_errors_and_repr():
    marker = "SYNTHETIC_PASSWORD_ONLY"
    with pytest.raises(ValidationError) as caught:
        Settings(database_url=f"sqlite://example:{marker}@localhost/db")
    assert marker not in str(caught.value)
    assert marker not in repr(caught.value)
    assert "database" in str(caught.value).lower()


@pytest.mark.ac("S0.1-AC3")
@given(host=SEGMENT, database=SEGMENT, password=SEGMENT)
def test_valid_url_property(host, database, password):
    secret = SecretStr(f"postgresql+asyncpg://example:{password}@{host}/{database}")
    result = Settings.validate_database_url(secret)
    assert isinstance(result, SecretStr)
    assert result.get_secret_value() == secret.get_secret_value()


@pytest.mark.ac("S0.1-AC3")
@given(driver=st.sampled_from(["https", "sqlite", "postgresql", "mysql+asyncmy"]), db=SEGMENT)
def test_invalid_driver_property(driver, db):
    with pytest.raises(ValueError):  # noqa: PT011  # Any invalid driver must be rejected.
        Settings.validate_database_url(SecretStr(f"{driver}://example:synthetic@localhost/{db}"))
