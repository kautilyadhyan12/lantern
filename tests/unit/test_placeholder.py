import importlib.metadata

import pytest

import lantern


@pytest.mark.ac("S0.1-AC1")
def test_package_imports_with_version() -> None:
    assert lantern.__version__ == importlib.metadata.version("lantern")
