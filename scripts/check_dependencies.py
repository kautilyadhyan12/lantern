"""Reject prohibited packages anywhere in the complete uv lockfile."""

import argparse
import re
import tomllib
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

DENIED = frozenset(
    {
        "face-recognition",
        "face-recognition-models",
        "deepface",
        "insightface",
        "facenet-pytorch",
        "dlib",
        "litellm",
    }
)


class Package(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9.+!_-]*$")


class Lock(BaseModel):
    package: list[Package] = Field(min_length=1)


def denied_packages(names: Sequence[str]) -> list[str]:
    return sorted({re.sub(r"[-_.]+", "-", name).lower() for name in names} & DENIED)


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        lock = Lock.model_validate(tomllib.loads(Path("uv.lock").read_text()))
    except (OSError, ValueError, ValidationError):
        print("Cannot read a valid uv.lock. Resolve the project dependencies and try again.")
        return 1
    denied = denied_packages([package.name for package in lock.package])
    print("Prohibited dependencies: " + (", ".join(denied) if denied else "none"))
    return int(bool(denied))


if __name__ == "__main__":
    raise SystemExit(main())
