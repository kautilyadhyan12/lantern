from pathlib import Path

import pytest
import yaml

# hook id -> substring its entry must contain
REQUIRED_HOOKS = {
    "ruff-check": "uv run ruff check",
    "ruff-format": "uv run ruff format",
    "mypy": "uv run mypy",
    "detect-secrets": "uv run detect-secrets-hook --baseline .secrets.baseline",
    "fixture-signatures": "uv run python scripts/check_fixture_signatures.py",
}


def _repos(repo_root: Path) -> list[dict[str, object]]:
    path = repo_root / ".pre-commit-config.yaml"
    assert path.is_file(), ".pre-commit-config.yaml missing"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(config, dict)
    repos = config.get("repos")
    assert isinstance(repos, list)
    return repos


def _hooks(repo_root: Path) -> dict[str, dict[str, object]]:
    hooks: dict[str, dict[str, object]] = {}
    for repo in _repos(repo_root):
        entries = repo.get("hooks")
        assert isinstance(entries, list)
        for hook in entries:
            assert isinstance(hook, dict)
            hooks[str(hook["id"])] = hook
    return hooks


@pytest.mark.ac("S0.1-AC4")
def test_required_local_hooks_present(repo_root: Path) -> None:
    hooks = _hooks(repo_root)
    for hook_id, entry in REQUIRED_HOOKS.items():
        assert hook_id in hooks, f"missing pre-commit hook {hook_id!r}"
        assert entry in str(hooks[hook_id].get("entry", "")), f"{hook_id}: unexpected entry"
    assert (repo_root / ".secrets.baseline").is_file(), "detect-secrets baseline missing"
    assert hooks["fixture-signatures"].get("always_run") is True


@pytest.mark.ac("S0.1-AC4")
def test_hooks_need_no_network(repo_root: Path) -> None:
    """Local hooks run the locked tool versions from uv.lock; nothing is cloned at install."""
    assert {repo.get("repo") for repo in _repos(repo_root)} == {"local"}
