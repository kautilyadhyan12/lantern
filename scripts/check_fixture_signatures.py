"""Fixture signature policy check: recorded fixtures must carry a valid recorder signature.

S0.1 form: no fixtures have been recorded yet, so this passes only while tests/fixtures/
holds no fixture (*.json) files. Real verification (recorder block, HMAC signature,
adapter version) arrives with S0.3-AC4; until then any fixture fails loudly instead of
being waved through unverified.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

FIXTURES_DIR: Final = Path("tests") / "fixtures"


def find_fixtures(root: Path) -> list[Path]:
    directory = root / FIXTURES_DIR
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.rglob("*.json") if path.is_file())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify recorded fixture signatures")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    args = parser.parse_args(argv)

    fixtures = find_fixtures(args.root)
    if not fixtures:
        print("fixture signatures: no fixtures recorded yet")
        return 0
    for fixture in fixtures:
        print(f"{fixture}: cannot verify signature before S0.3 (S0.3-AC4)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
