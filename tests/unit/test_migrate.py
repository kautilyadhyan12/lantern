"""Alembic wiring for `lantern db upgrade` that needs no database (S0.1-AC3)."""

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from lantern.db import migrate

URL_MARKER = "postgresql+asyncpg://lantern@localhost/lantern-marker-5d1e"


@pytest.mark.ac("S0.1-AC3")
def test_config_points_at_packaged_migrations_and_hides_url() -> None:
    config = migrate.alembic_config(URL_MARKER)
    assert config.get_main_option("script_location") == str(migrate.MIGRATIONS_DIR)
    assert config.attributes[migrate.DATABASE_URL_ATTRIBUTE] == URL_MARKER
    assert config.get_main_option("sqlalchemy.url") is None, "URL must not go through the ini"


@pytest.mark.ac("S0.1-AC3")
def test_single_empty_baseline_head() -> None:
    script = ScriptDirectory.from_config(migrate.alembic_config(URL_MARKER))
    assert script.get_heads() == ["0001"]
    baseline = script.get_revision("0001")
    assert baseline is not None
    assert baseline.down_revision is None


@pytest.mark.ac("S0.1-AC3")
def test_offline_sql_mode_is_refused() -> None:
    with pytest.raises(RuntimeError, match="offline"):
        command.upgrade(migrate.alembic_config(URL_MARKER), "head", sql=True)


@pytest.mark.ac("S0.1-AC3")
def test_env_refuses_to_run_without_url() -> None:
    config = Config()
    config.set_main_option("script_location", str(migrate.MIGRATIONS_DIR))
    with pytest.raises(RuntimeError, match="lantern db upgrade"):
        command.upgrade(config, "head")
