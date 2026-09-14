import re
from pathlib import Path

import pytest
import yaml


def _db_service(repo_root: Path) -> dict[str, object]:
    path = repo_root / "docker-compose.yml"
    assert path.is_file(), "docker-compose.yml missing"
    compose = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(compose, dict)
    services = compose.get("services")
    assert isinstance(services, dict)
    assert "db" in services, "compose file has no `db` service"
    db = services["db"]
    assert isinstance(db, dict)
    return db


@pytest.mark.ac("S0.1-AC3")
def test_db_service_is_pgvector_pg16(repo_root: Path) -> None:
    image = _db_service(repo_root).get("image")
    assert isinstance(image, str)
    # A pinned pgvector release built on Postgres 16 (no floating `pg16` / `latest`).
    assert re.fullmatch(r"pgvector/pgvector:\d+\.\d+\.\d+-pg16(-[a-z]+)?", image), image


@pytest.mark.ac("S0.1-AC3")
def test_db_service_healthcheck_and_local_bind(repo_root: Path) -> None:
    db = _db_service(repo_root)

    healthcheck = db.get("healthcheck")
    assert isinstance(healthcheck, dict)
    assert "pg_isready" in " ".join(map(str, healthcheck.get("test", [])))

    ports = db.get("ports")
    assert isinstance(ports, list)
    assert ports, "db must publish a port for local development"
    assert all(str(port).startswith("127.0.0.1:") for port in ports), "bind to loopback only"

    environment = db.get("environment")
    assert isinstance(environment, dict)
    password = environment.get("POSTGRES_PASSWORD")
    assert isinstance(password, str)
    assert password.startswith("${POSTGRES_PASSWORD"), "password must come from .env, not the file"
