import pytest
from pydantic import ValidationError
from sqlalchemy import URL

from lantern import cli
from lantern.config import Settings
from lantern.db import migrate

SAMPLE_SECRET = "sample-" + "pw-9f2c"  # pragma: allowlist secret


def _url(drivername: str, password: str | None = None) -> str:
    return URL.create(
        drivername, username="lantern", password=password, host="localhost", database="lantern"
    ).render_as_string(hide_password=False)


@pytest.mark.ac("S0.1-AC3")
def test_settings_rejects_non_asyncpg_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANTERN_DATABASE_URL", _url("postgresql+psycopg2", SAMPLE_SECRET))
    with pytest.raises(ValidationError, match="asyncpg") as exc:
        Settings(_env_file=None)
    assert SAMPLE_SECRET not in str(exc.value), "validation errors must not echo the password"


@pytest.mark.ac("S0.1-AC3")
def test_settings_rejects_garbage_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANTERN_DATABASE_URL", "not a url")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.ac("S0.1-AC3")
def test_settings_hides_password(monkeypatch: pytest.MonkeyPatch) -> None:
    url = _url("postgresql+asyncpg", SAMPLE_SECRET)
    monkeypatch.setenv("LANTERN_DATABASE_URL", url)
    settings = Settings(_env_file=None)
    assert settings.database_url.get_secret_value() == url
    assert SAMPLE_SECRET not in repr(settings)
    assert SAMPLE_SECRET not in str(settings.model_dump())


@pytest.mark.ac("S0.1-AC3")
def test_cli_db_upgrade_invokes_alembic_head(monkeypatch: pytest.MonkeyPatch) -> None:
    url = _url("postgresql+asyncpg", SAMPLE_SECRET)
    monkeypatch.setenv("LANTERN_DATABASE_URL", url)
    calls: list[tuple[str, str]] = []

    def fake_upgrade(database_url: str, revision: str = "head") -> None:
        calls.append((database_url, revision))

    monkeypatch.setattr(migrate, "upgrade", fake_upgrade)
    assert cli.main(["db", "upgrade"]) == 0
    assert calls == [(url, "head")]


@pytest.mark.ac("S0.1-AC3")
@pytest.mark.parametrize("argv", [[], ["db"], ["nope"]])
def test_cli_requires_a_known_subcommand(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 2
