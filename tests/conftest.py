"""Shared test boundaries; never read real service credentials."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo():
    return ROOT


@pytest.fixture
def project_file(repo):
    def read(relative):
        path = repo / relative
        assert path.is_file(), f"S0.1 must provide {relative}"
        return path.read_text()
    return read


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch):
    import os
    for name in list(os.environ):
        if name.startswith("LANTERN_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("UV_OFFLINE", "1")
