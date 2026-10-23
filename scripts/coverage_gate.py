"""Apply configured coverage thresholds to validated line and branch counts."""

import argparse
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, Field, ValidationError, model_validator

Count = Annotated[int, Field(strict=True, ge=0)]
Percent = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]


class Summary(BaseModel):
    covered_lines: Count
    num_statements: Count
    covered_branches: Count
    num_branches: Count
    percent_covered: Percent

    @model_validator(mode="after")
    def counts_are_possible(self) -> Self:
        if self.covered_lines > self.num_statements or self.covered_branches > self.num_branches:
            raise ValueError("Covered counts cannot exceed total opportunities.")
        return self


class CoveredFile(BaseModel):
    summary: Summary


class CoverageReport(BaseModel):
    totals: Summary
    files: dict[str, CoveredFile]


class QualitySettings(BaseModel):
    coverage_total: Percent
    coverage_critical: Percent
    critical_paths: tuple[str, ...]


def evaluate_coverage(
    report: CoverageReport, quality: QualitySettings, present_paths: frozenset[str]
) -> list[str]:
    errors = []
    totals = report.totals
    covered = totals.covered_lines + totals.covered_branches
    opportunities = totals.num_statements + totals.num_branches
    if not opportunities or 100 * covered < quality.coverage_total * opportunities:
        errors.append(f"Total coverage is below {quality.coverage_total}% or has no measured code.")
    for path in quality.critical_paths:
        present = {name for name in present_paths if name == path or name.startswith(path + "/")}
        if not present:
            continue
        measured = {
            name: file.summary
            for name, file in report.files.items()
            if name == path or name.startswith(path + "/")
        }
        if not measured or any(name.endswith(".py") and name not in measured for name in present):
            errors.append(f"{path}: existing critical code was not measured.")
            continue
        covered = sum(item.covered_lines + item.covered_branches for item in measured.values())
        opportunities = sum(item.num_statements + item.num_branches for item in measured.values())
        if not opportunities or 100 * covered < quality.coverage_critical * opportunities:
            errors.append(f"{path}: coverage is below {quality.coverage_critical}%.")
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        config = tomllib.loads(Path("pyproject.toml").read_text())
        quality = QualitySettings.model_validate(config["tool"]["lantern"]["quality"])
        report = CoverageReport.model_validate_json(Path("coverage.json").read_text())
        present: set[str] = set()
        for name in quality.critical_paths:
            path = Path(name)
            if path.exists():
                present.add(name)
                if path.is_dir():
                    present.update(str(file) for file in path.rglob("*.py"))
            else:
                print(f"{name}: not present")
        errors = evaluate_coverage(report, quality, frozenset(present))
    except (OSError, ValueError, KeyError, ValidationError):
        print("Cannot read valid coverage and quality settings. Run the tests with coverage again.")
        return 1
    print(f"Total coverage: {report.totals.percent_covered}%")
    for error in errors:
        print(error)
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
