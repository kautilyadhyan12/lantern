"""Suite-wide pytest configuration."""

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# The clean-clone test (S0.1-AC1) runs `make test` inside a copy of the repo. Inside that
# copy this env var is set and the clean-clone test deselects itself, otherwise it would
# recurse forever. Deselection is reported by pytest; nothing is skipped silently.
CLEAN_CLONE_ENV = "LANTERN_CLEAN_CLONE"
CLEAN_CLONE_NODEID = "tests/e2e/test_clean_clone.py::test_clean_clone_uv_sync_and_make_green"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get(CLEAN_CLONE_ENV) != "1":
        return
    deselected = [item for item in items if item.nodeid == CLEAN_CLONE_NODEID]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = [item for item in items if item.nodeid != CLEAN_CLONE_NODEID]
