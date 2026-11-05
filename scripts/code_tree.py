"""Hash exact committed Git tree entries, excluding documentation by default."""

import argparse
import hashlib
import os
import shutil
import subprocess  # nosec B404 # Read-only Git inspection requires a bounded child process.
from collections.abc import Sequence
from pathlib import Path


def git(root: Path, *arguments: str) -> bytes:
    executable = shutil.which("git")
    if executable is None:
        raise FileNotFoundError("Install Git before inspecting this repository.")
    return subprocess.run(  # noqa: S603  # nosec B603 # Read-only Git argument lists; no shell.
        [executable, "-c", "core.quotePath=true", *arguments],
        cwd=root,
        capture_output=True,
        timeout=30,
        check=True,
    ).stdout


def hash_entries(
    entries: Sequence[tuple[str, bytes]], excluded_prefixes: Sequence[str] = ()
) -> str:
    prefixes = ("docs", *(prefix.rstrip("/") for prefix in excluded_prefixes))
    return hashlib.sha256(
        b"".join(
            entry
            for path, entry in entries
            if not any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes)
        )
    ).hexdigest()


def code_tree(
    root: Path, *, commit: str | None = None, excluded_prefixes: Sequence[str] = ()
) -> str:
    sha = git(root, "rev-parse", "--verify", "--end-of-options", f"{commit or 'HEAD'}^{{commit}}")
    revision = sha.decode().strip()
    lines = git(root, "ls-tree", "-r", revision).splitlines(keepends=True)
    raw = git(root, "ls-tree", "-r", "-z", revision).split(b"\0")
    paths = [os.fsdecode(entry.split(b"\t", 1)[1]) for entry in raw if entry]
    return hash_entries(list(zip(paths, lines, strict=True)), excluded_prefixes)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exclude", action="append", default=[])
    arguments = parser.parse_args(argv)
    try:
        print(code_tree(Path.cwd(), excluded_prefixes=arguments.exclude))
    except (OSError, ValueError, subprocess.SubprocessError):
        print("Cannot hash this committed Git tree. Commit the code and try again.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
