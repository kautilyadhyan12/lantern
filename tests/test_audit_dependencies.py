"""The strict auditor receives every installed third-party package as exact pins."""

import importlib.metadata
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scripts import audit_dependencies as audit_tool
from scripts.checks import StepResult


def distribution(name="pydantic", version="2.14.1", direct=None):
    return SimpleNamespace(
        metadata={"Name": name},
        version=version,
        read_text=lambda filename: direct if filename == "direct_url.json" else None,
    )


def editable(root, name="lantern"):
    return distribution(
        name,
        "0.1.0",
        json.dumps(
            {
                "url": root.resolve().as_uri(),
                "dir_info": {"editable": True},
            }
        ),
    )


@pytest.mark.ac("S0.2-AC1")
def test_complete_inventory_and_single_local_exception(tmp_path, monkeypatch):
    items = [editable(tmp_path), distribution(), distribution("pytest", "9.1.1")]
    monkeypatch.setattr(importlib.metadata, "distributions", lambda: iter(items))
    assert audit_tool.installed_requirements(tmp_path) == ["pydantic==2.14.1", "pytest==9.1.1"]


@pytest.mark.ac("S0.2-AC1")
@pytest.mark.parametrize(
    "invalid",
    [
        "other_editable",
        "foreign_lantern",
        "bad_json",
        "bad_name",
        "bad_version",
        "missing_name",
        "empty",
        "duplicate",
    ],
)
def test_invalid_inventory_fails_before_audit(tmp_path, monkeypatch, capsys, invalid):
    cases = {
        "other_editable": [editable(tmp_path, "other-project")],
        "foreign_lantern": [editable(tmp_path / "other")],
        "bad_json": [distribution(direct="{invalid")],
        "bad_name": [distribution(name="pydantic\nother")],
        "bad_version": [distribution(version="2.14.1\nother==1")],
        "missing_name": [distribution(name=None)],
        "empty": [],
        "duplicate": [distribution(), distribution()],
    }
    monkeypatch.setattr(importlib.metadata, "distributions", lambda: iter(cases[invalid]))
    calls = []

    def runner(command, root):
        calls.append(command)
        return StepResult(command=tuple(command), exit_code=0, duration_seconds=0, output_tail=())

    assert audit_tool.audit(tmp_path, runner=runner) != 0
    assert calls == []
    assert capsys.readouterr().out


@pytest.mark.ac("S0.2-AC1")
@pytest.mark.parametrize("status", [0, 1, 2, 124, 126])
def test_strict_arguments_status_and_manifest_cleanup(tmp_path, monkeypatch, status):
    monkeypatch.setattr(importlib.metadata, "distributions", lambda: iter([distribution()]))
    manifests = []

    def runner(command, root):
        assert root == tmp_path
        assert command[0] == "pip-audit"
        assert tuple(command[1:-1]) == (
            "--strict",
            "--no-deps",
            "--disable-pip",
            "--progress-spinner",
            "off",
            "--timeout",
            "30",
            "-r",
        )
        manifest = Path(command[-1])
        manifests.append(manifest)
        assert manifest.read_text() == "pydantic==2.14.1\n"
        return StepResult(
            command=tuple(command),
            exit_code=status,
            duration_seconds=0.01,
            output_tail=("Synthetic audit outcome",),
        )

    assert (audit_tool.audit(tmp_path, runner=runner) == 0) is (status == 0)
    assert len(manifests) == 1
    assert not manifests[0].exists()


@pytest.mark.ac("S0.2-AC1")
def test_real_process_boundary_and_error_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(importlib.metadata, "distributions", lambda: iter([distribution()]))
    log = tmp_path / "audit-arguments.json"
    binary = tmp_path / "pip-audit"
    binary.write_text(
        f"#!{sys.executable}\nimport json, os, sys\nfrom pathlib import Path\n"
        "manifest=Path(sys.argv[sys.argv.index('-r')+1])\n"
        "Path(os.environ['AUDIT_LOG']).write_text(json.dumps({'args':sys.argv[1:],'pins':manifest.read_text()}))\n"
        "print('Synthetic network failure')\nsys.exit(2)\n"
    )
    binary.chmod(0o755)
    monkeypatch.setenv("AUDIT_LOG", str(log))
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    assert audit_tool.audit(tmp_path) != 0
    assert "Synthetic network failure" in capsys.readouterr().out
    saved = json.loads(log.read_text())
    assert "--strict" in saved["args"]
    assert saved["pins"] == "pydantic==2.14.1\n"
    assert not Path(saved["args"][-1]).exists()


@pytest.mark.ac("S0.2-AC1")
@given(st.lists(st.integers(0, 10000), min_size=1, max_size=12))
def test_inventory_pins_are_sorted_and_order_independent(versions):
    items = [
        distribution(f"package{index}", f"1.{version}") for index, version in enumerate(versions)
    ]
    expected = sorted(f"package{index}==1.{version}" for index, version in enumerate(versions))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(importlib.metadata, "distributions", lambda: iter(items))
        assert audit_tool.installed_requirements(Path("/synthetic-lantern")) == expected
        patch.setattr(importlib.metadata, "distributions", lambda: iter(reversed(items)))
        assert audit_tool.installed_requirements(Path("/synthetic-lantern")) == expected
