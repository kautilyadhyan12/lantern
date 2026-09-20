"""Guard hook for file edits: it reads the path about to be written and refuses protected ones.

Refuses, with exit code 2 and a reason on stderr:
  GP001 edits under tests/fixtures/, docs/proofs/, docs/reviews/, .prove/ or .github/workflows/ —
        recorded evidence and proof artefacts are written by their own scripts, never by hand
  GP002 edits to any `.env` file except `.env.example` — that is where the recorder's signing key
        and the API keys live

Everything else, `src/**` first of all, is allowed. Paths are normalised (relative to the session's
working directory, `..` resolved, Windows separators folded) before comparison, so
`src/../.env` and `tests\\fixtures\\a.json` are judged as what they are.
"""

import argparse
import os
import posixpath
import re
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Final

from scripts.hooks.hookio import HookInputError, Violation, allow, block, read_hook_input

PROTECTED_PREFIXES: Final[tuple[str, ...]] = (
    "tests/fixtures",
    "docs/proofs",
    "docs/reviews",
    ".prove",
    ".github/workflows",
)
ENV_FILE_ALLOWED: Final = ".env.example"

DRIVE_RE: Final = re.compile(r"^[A-Za-z]:/")


def repo_root(override: str | Path | None = None) -> Path:
    """The project root: what the caller passed, else the repo this file lives in.

    The harness knows its own project directory and passes it with `--root`; nothing here
    depends on a particular harness's environment variables.
    """
    if override is not None and str(override).strip():
        return Path(override).resolve()
    return Path(__file__).resolve().parents[2]


def _posix(value: object) -> str:
    return str(value).replace("\\", "/").strip("\"'")


def _key(text: str) -> str:
    """Comparison key: Windows paths differ only in case, POSIX paths do not."""
    return text.casefold() if os.name == "nt" else text


def relative_to_repo(path: str, *, cwd: Path, root: Path) -> PurePosixPath | None:
    """`path` as a repo-relative path, or None when it points outside the repo."""
    text = _posix(path.strip())
    if not text:
        return None
    if not (text.startswith("/") or DRIVE_RE.match(text)):
        text = f"{_posix(cwd)}/{text}"
    resolved = posixpath.normpath(text)
    base = posixpath.normpath(_posix(root))
    if _key(resolved) == _key(base):
        return PurePosixPath(".")
    if not _key(resolved).startswith(_key(base) + "/"):
        return None
    return PurePosixPath(resolved[len(base) + 1 :])


def _is_env_file(name: str) -> bool:
    if name == ENV_FILE_ALLOWED:
        return False
    return name == ".env" or name.startswith(".env.")


def check_path(path: str, *, cwd: Path, root: Path) -> Violation | None:
    """Judge one edited path; None means "nothing objectionable"."""
    text = path.strip()
    if not text:
        return None

    name = PurePosixPath(_posix(text).rstrip("/") or "/").name
    if _is_env_file(name):
        return Violation("GP002", f"{name} holds secrets and is edited by hand only")

    relative = relative_to_repo(text, cwd=cwd, root=root)
    if relative is None:
        return None
    inside = relative.as_posix()
    for prefix in PROTECTED_PREFIXES:
        if inside == prefix or inside.startswith(f"{prefix}/"):
            return Violation("GP001", f"{inside} is written by its own script, never by hand")
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guard hook: refuse edits to protected paths")
    parser.add_argument("--root", type=Path, default=None, help="repository root to judge against")
    args = parser.parse_args(argv)
    try:
        hook = read_hook_input()
    except HookInputError as exc:
        return block(f"guard_paths: refusing the call — {exc}")

    root = repo_root(args.root)
    violation = check_path(hook.file_path, cwd=hook.cwd, root=root)
    if violation is None:
        return allow()
    return block(f"guard_paths: {violation.rule} {violation.detail}")


if __name__ == "__main__":
    raise SystemExit(main())
