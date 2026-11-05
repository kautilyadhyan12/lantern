"""Run every gate and atomically record proof for one immutable committed code tree."""

import argparse
import os
import platform
import re
import shlex
import subprocess  # nosec B404 # Git inspection errors must prevent a false PASS.
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, Field

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.checks import StepResult, StepRunner, invoke_step, run_checks, run_step, sanitize
from scripts.code_tree import code_tree, git

ID = r"[A-Za-z][A-Za-z0-9]*(?:[._-][A-Za-z0-9]+)*"


class ProofContext(BaseModel):
    story: str = Field(pattern="^" + ID + "$", max_length=64)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
    code_tree: str = Field(pattern=r"^[0-9a-f]{64}$")
    recorded_at: AwareDatetime
    platform: str


def render_proof(context: ProofContext, results: Sequence[StepResult]) -> str:
    lines = [
        f"# PROOF {context.story}",
        f"Commit: {context.commit_sha}",
        f"Code tree: {context.code_tree}",
        f"UTC: {context.recorded_at.astimezone(UTC).isoformat()}",
        f"Platform: {context.platform}",
        "",
    ]
    for index, raw in enumerate(results, 1):
        result = StepResult.model_validate(raw)
        tail = "\n".join(result.output_tail).splitlines()[-30:]
        content = shlex.join(result.command) + "\n" + "\n".join(tail)
        fence = "`" * (1 + max([2, *(len(match[0]) for match in re.finditer(r"`+", content))]))
        lines.extend(
            [
                f"## Check {index}",
                f"Exit: {result.exit_code}; duration: {result.duration_seconds:.3f} seconds",
                fence + "text",
                content,
                fence,
                "",
            ]
        )
    passed = bool(results) and all(result.exit_code == 0 for result in results)
    lines.append("RESULT: PASS" if passed else "RESULT: FAIL")
    return sanitize("\n".join(lines) + "\n")


def dirty_code(root: Path) -> bool:
    entries = iter(
        git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").split(b"\0")
    )
    for entry in entries:
        if entry:
            paths = [entry[3:]]
            if b"R" in entry[:2] or b"C" in entry[:2]:
                paths.append(next(entries))
            if any(not path.startswith(b"docs/") for path in paths):
                return True
    return False


def prove(
    story: str, ac_stories: Sequence[str], root: Path, *, runner: StepRunner = run_step
) -> int:
    if any(len(item) > 64 or not re.fullmatch(ID, item) for item in [story, *ac_stories]):
        print("Use a filename-safe story ID, such as S0.2 or M0.")
        return 2
    try:
        head = git(root, "rev-parse", "--verify", "HEAD").decode().strip()
        if dirty_code(root):
            print("Commit code changes and untracked code before generating proof.")
            return 2
        context = ProofContext(
            story=story,
            commit_sha=head,
            code_tree=code_tree(root, commit=head),
            recorded_at=datetime.now(UTC),
            platform=platform.platform(),
        )
        tracked = set(git(root, "ls-files", "-z").split(b"\0"))
        for path in [root / "coverage.json", root / ".coverage", *root.glob(".coverage.*")]:
            if os.fsencode(path.name) not in tracked and (path.is_file() or path.is_symlink()):
                path.unlink()
        results = run_checks(root, runner=runner, continue_on_error=True)
        command = (
            "uv",
            "run",
            "python",
            "scripts/check_acceptance_ids.py",
            *(ac_stories or [story]),
            "--backlog",
            "docs/06_ROADMAP_BACKLOG.md",
        )
        results.append(invoke_step(command, root, runner))
        try:
            changed = git(root, "rev-parse", "HEAD").decode().strip() != head or dirty_code(root)
        except (OSError, subprocess.SubprocessError):
            changed = True
        if changed:
            results.append(
                StepResult(
                    command=("internal", "provenance"),
                    exit_code=1,
                    duration_seconds=0,
                    output_tail=(
                        "HEAD or code changed during the checks; rerun on committed code.",
                    ),
                )
            )
        directory = root / "docs/proofs"
        if (root / "docs").is_symlink() or directory.is_symlink():
            print("Proof directories must not be symlinks.")
            return 2
        directory.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(render_proof(context, results))
            temporary.replace(directory / f"PROOF-{story}.md")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return int(any(result.exit_code for result in results))
    except (OSError, ValueError, subprocess.SubprocessError):
        print(
            "Cannot generate trustworthy proof. Check Git, committed code and report permissions."
        )
        return 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("story", nargs="?", default=os.environ.get("STORY", ""))
    parser.add_argument("--ac-stories", nargs="+", default=os.environ.get("AC_STORIES", "").split())
    arguments = parser.parse_args(argv)
    return prove(arguments.story, arguments.ac_stories, Path.cwd())


if __name__ == "__main__":
    raise SystemExit(main())
