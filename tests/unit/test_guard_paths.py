"""S0.2-AC3: guard_paths refuses Edit/Write into the protected trees and allows src/**."""

import io
import json
import sys
from pathlib import Path, PurePosixPath

import pytest

from scripts.hooks import guard_paths

BLOCKED: dict[str, str] = {
    "tests/fixtures/search/basic.json": "GP001",
    "tests/fixtures": "GP001",
    "docs/proofs/PROOF-S0.1.md": "GP001",
    "docs/reviews/REVIEW-S0.1.json": "GP001",
    ".prove/stamp": "GP001",
    ".github/workflows/ci.yml": "GP001",
    "./tests/fixtures/../fixtures/search/basic.json": "GP001",
    r"tests\fixtures\search\basic.json": "GP001",
    ".env": "GP002",
    ".env.local": "GP002",
    "src/../.env": "GP002",
}

ALLOWED: tuple[str, ...] = (
    "src/lantern/cli.py",
    "src/lantern/tools/base.py",
    "tests/unit/test_guard_paths.py",
    "tests/fixtures_helpers.py",
    "tests/review/test_S0.2a_adversarial.py",
    ".env.example",
    "docs/plans/PLAN-S0.2a.md",
    "docs/design/overview.md",
    "scripts/hooks/guard_bash.py",
    "pyproject.toml",
    ".proverbs/notes.md",
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "repo"


@pytest.mark.ac("S0.2-AC3")
@pytest.mark.parametrize(("path", "rule"), sorted(BLOCKED.items()))
def test_blocked_relative_paths(path: str, rule: str, root: Path) -> None:
    violation = guard_paths.check_path(path, cwd=root, root=root)
    assert violation is not None, f"{path!r} must be blocked"
    assert violation.rule == rule
    assert violation.detail


@pytest.mark.ac("S0.2-AC3")
@pytest.mark.parametrize(("path", "rule"), sorted(BLOCKED.items()))
def test_blocked_absolute_paths(path: str, rule: str, root: Path) -> None:
    absolute = str(root / path.replace("\\", "/"))
    violation = guard_paths.check_path(absolute, cwd=root, root=root)
    assert violation is not None, f"{absolute!r} must be blocked"
    assert violation.rule == rule


@pytest.mark.ac("S0.2-AC3")
@pytest.mark.parametrize("path", ALLOWED)
def test_allowed_paths(path: str, root: Path) -> None:
    assert guard_paths.check_path(path, cwd=root, root=root) is None
    assert guard_paths.check_path(str(root / path), cwd=root, root=root) is None


@pytest.mark.ac("S0.2-AC3")
def test_paths_are_resolved_against_the_session_directory(root: Path) -> None:
    cwd = root / "src" / "lantern"
    violation = guard_paths.check_path("../../tests/fixtures/x.json", cwd=cwd, root=root)
    assert violation is not None
    assert violation.rule == "GP001"
    assert guard_paths.check_path("cli.py", cwd=cwd, root=root) is None


@pytest.mark.ac("S0.2-AC3")
def test_path_outside_the_repo_is_allowed_but_env_files_never_are(
    root: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "elsewhere" / "notes.md"
    assert guard_paths.check_path(str(outside), cwd=root, root=root) is None
    outside_env = tmp_path / "elsewhere" / ".env"
    violation = guard_paths.check_path(str(outside_env), cwd=root, root=root)
    assert violation is not None
    assert violation.rule == "GP002"


@pytest.mark.ac("S0.2-AC3")
@pytest.mark.parametrize("path", ["", "   "])
def test_missing_file_path_is_allowed(path: str, root: Path) -> None:
    assert guard_paths.check_path(path, cwd=root, root=root) is None


@pytest.mark.ac("S0.2-AC3")
def test_relative_to_repo_reports_outside_paths(root: Path, tmp_path: Path) -> None:
    assert guard_paths.relative_to_repo("src/lantern/cli.py", cwd=root, root=root) is not None
    assert guard_paths.relative_to_repo(str(tmp_path / "x.py"), cwd=root, root=root) is None


@pytest.mark.ac("S0.2-AC3")
@pytest.mark.parametrize("blank", ["", "   ", None])
def test_repo_root_falls_back_to_its_own_repository(blank: str | None, tmp_path: Path) -> None:
    """The harness passes --root; without one the guard still finds the repo it ships in."""
    assert guard_paths.repo_root(tmp_path) == tmp_path.resolve()
    assert (guard_paths.repo_root(blank) / "pyproject.toml").is_file()


@pytest.mark.ac("S0.2-AC3")
def test_protected_prefixes_cover_the_documented_trees() -> None:
    assert set(guard_paths.PROTECTED_PREFIXES) == {
        "tests/fixtures",
        "docs/proofs",
        "docs/reviews",
        ".prove",
        ".github/workflows",
    }


# --- edge cases and the hook entry point --------------------------------------------------


@pytest.mark.ac("S0.2-AC3")
def test_the_repo_root_itself_is_not_a_protected_path(root: Path) -> None:
    assert guard_paths.relative_to_repo(str(root), cwd=root, root=root) == PurePosixPath(".")
    assert guard_paths.check_path(str(root), cwd=root, root=root) is None


@pytest.mark.ac("S0.2-AC3")
@pytest.mark.parametrize("path", ["", "  ", '""'])
def test_relative_to_repo_ignores_empty_paths(path: str, root: Path) -> None:
    assert guard_paths.relative_to_repo(path, cwd=root, root=root) is None


def _payload(file_path: str, cwd: Path) -> str:
    return json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": file_path},
            "cwd": str(cwd),
        }
    )


@pytest.mark.ac("S0.2-AC3")
def test_main_blocks_a_protected_write(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(_payload("docs/proofs/PROOF-S0.1.md", root)))
    assert guard_paths.main(["--root", str(root)]) == 2
    assert "GP001" in capsys.readouterr().err


@pytest.mark.ac("S0.2-AC3")
def test_main_allows_a_src_write(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(_payload("src/lantern/cli.py", root)))
    assert guard_paths.main(["--root", str(root)]) == 0
    assert capsys.readouterr().err == ""


@pytest.mark.ac("S0.2-AC3")
def test_main_without_a_root_still_guards_env_files(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(_payload(".env", root)))
    assert guard_paths.main([]) == 2
    assert "GP002" in capsys.readouterr().err


@pytest.mark.ac("S0.2-AC3")
@pytest.mark.parametrize("payload", ["", "{not json}"])
def test_main_fails_closed_on_anything_it_cannot_read(
    payload: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    assert guard_paths.main([]) == 2
    assert capsys.readouterr().err.strip()
