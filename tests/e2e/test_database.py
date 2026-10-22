"""Real Compose database checks plus safe, bounded failure cases."""
import asyncio
import json
import socket
import subprocess

import pytest
from lantern.cli import main
from lantern.config import Settings
from lantern.db.migrate import MigrationError, upgrade



def compose_config(repo):
    assert (repo / "compose.yaml").is_file(), "S0.1 must provide compose.yaml"
    result = subprocess.run(["docker", "compose", "config", "--format", "json"],
                            cwd=repo, text=True, capture_output=True, timeout=20, check=False)
    assert result.returncode == 0, "Compose configuration must validate"
    return json.loads(result.stdout)


@pytest.mark.ac("S0.1-AC3")
def test_compose_loopback_healthcheck(repo):
    config = compose_config(repo)
    db = config["services"]["db"]
    assert db["image"].startswith("pgvector/pgvector:pg16")
    assert "@sha256:" in db["image"], "Pin the verified image manifest"
    ports = db["ports"]
    assert len(ports) == 1 and str(ports[0]["target"]) == "5432"
    assert ports[0]["host_ip"] == "127.0.0.1" and str(ports[0]["published"]) == "5434"
    assert "pg_isready" in " ".join(db["healthcheck"]["test"])
    assert db["healthcheck"]["retries"] > 0
    assert db["volumes"], "Keep database data across ordinary stops"


def database_settings(repo):
    config = compose_config(repo)
    environment = config["services"]["db"]["environment"]
    user = environment["POSTGRES_USER"]
    password = environment["POSTGRES_PASSWORD"]
    database = environment["POSTGRES_DB"]
    port = config["services"]["db"]["ports"][0]["published"]
    return Settings(database_url=f"postgresql+asyncpg://{user}:{password}@127.0.0.1:{port}/{database}")


async def inspect_database(settings):
    import asyncpg
    url = settings.database_url.get_secret_value().replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = await asyncpg.connect(url, timeout=5, command_timeout=10)
    try:
        version = await connection.fetchval("SHOW server_version_num")
        vector = await connection.fetchval("SELECT default_version FROM pg_available_extensions WHERE name = 'vector'")
        revision = await connection.fetchval("SELECT version_num FROM alembic_version")
        tables = await connection.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        return int(version), vector, revision, {row["tablename"] for row in tables}
    finally:
        await connection.close()


@pytest.mark.ac("S0.1-AC3")
def test_upgrade_records_baseline(repo, monkeypatch, tmp_path):
    settings = database_settings(repo)
    monkeypatch.chdir(tmp_path)
    try:
        upgrade(settings)
    except MigrationError as error:
        raise AssertionError("Database unavailable. Run make db and retry these tests.") from error
    version, vector, revision, tables = asyncio.run(inspect_database(settings))
    assert 160000 <= version < 170000
    assert vector and revision == "0001_baseline"
    assert tables == {"alembic_version"}, "The baseline creates no application tables"


@pytest.mark.ac("S0.1-AC3")
def test_upgrade_is_idempotent(repo):
    settings = database_settings(repo)
    try:
        upgrade(settings)
        before = asyncio.run(inspect_database(settings))
        upgrade(settings)
    except MigrationError as error:
        raise AssertionError("Database unavailable. Run make db and retry these tests.") from error
    assert asyncio.run(inspect_database(settings)) == before


@pytest.mark.ac("S0.1-AC3")
def test_missing_database_guidance(monkeypatch, capsys):
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        port = unused.getsockname()[1]
        monkeypatch.setenv("LANTERN_DATABASE_URL", f"postgresql+asyncpg://example:synthetic-only@127.0.0.1:{port}/missing")
        assert main(["db", "upgrade"]) != 0
    output = capsys.readouterr()
    assert "make db" in output.out + output.err
    assert "synthetic-only" not in output.out + output.err


@pytest.mark.ac("S0.1-AC3")
def test_cli_never_echoes_credentials(monkeypatch, capsys):
    monkeypatch.setenv("LANTERN_DATABASE_URL", "sqlite://example:SYNTHETIC_SECRET_ONLY@localhost/db")
    assert main(["db", "upgrade"]) != 0
    captured = capsys.readouterr()
    assert "SYNTHETIC_SECRET_ONLY" not in captured.out + captured.err
    assert "database" in (captured.out + captured.err).lower()
