"""Audit validated installed third-party pins without masking collection failures."""

import argparse
import importlib.metadata
import re
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_dependencies import Package
from scripts.checks import StepResult, StepRunner, run_step


class DirectoryInfo(BaseModel):
    editable: bool = False


class DirectURL(BaseModel):
    url: str
    dir_info: DirectoryInfo | None = None


def installed_requirements(root: Path) -> list[str]:
    pins: dict[str, str] = {}
    seen: set[str] = set()
    for distribution in importlib.metadata.distributions():
        package = Package.model_validate(
            {
                "name": distribution.metadata.get("Name"),
                "version": distribution.version,
            }
        )
        name = re.sub(r"[-_.]+", "-", package.name).lower()
        if name in seen:
            raise ValueError("Duplicate installed package metadata.")
        seen.add(name)
        direct = distribution.read_text("direct_url.json")
        metadata = DirectURL.model_validate_json(direct) if direct is not None else None
        if metadata and metadata.dir_info and metadata.dir_info.editable:
            if name != "lantern" or metadata.url != root.resolve().as_uri():
                raise ValueError(
                    "Unexpected editable package. Install locked third-party releases."
                )
            continue
        pins[name] = f"{name}=={package.version}"
    if not pins:
        raise ValueError("No installed third-party packages were found.")
    return sorted(pins.values())


def audit(root: Path, *, runner: StepRunner = run_step) -> int:
    try:
        requirements = installed_requirements(root)
        with tempfile.TemporaryDirectory(prefix="lantern-audit-") as directory:
            manifest = Path(directory) / "requirements.txt"
            manifest.write_text("\n".join(requirements) + "\n")
            result = runner(
                (
                    "pip-audit",
                    "--strict",
                    "--no-deps",
                    "--disable-pip",
                    "--progress-spinner",
                    "off",
                    "--timeout",
                    "30",
                    "-r",
                    str(manifest),
                ),
                root,
            )
            result = StepResult.model_validate(result)
            print("\n".join(result.output_tail))
            return int(result.exit_code != 0)
    except (OSError, ValueError):
        print("Cannot audit this installed inventory. Sync the locked environment and try again.")
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    return audit(Path.cwd())


if __name__ == "__main__":
    raise SystemExit(main())
