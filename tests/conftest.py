"""Shared test boundaries; never read real service credentials."""

import os
from pathlib import Path

import pytest
from pytest_socket import disable_socket, socket_allow_hosts

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

    for name in list(os.environ):
        if name.startswith("LANTERN_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("UV_OFFLINE", "1")


@pytest.fixture(autouse=True)
def offline_sockets(request):
    if request.path.parent.name == "e2e":
        socket_allow_hosts(["127.0.0.1", "::1"], allow_unix_socket=True)
    else:
        disable_socket(allow_unix_socket=True)
