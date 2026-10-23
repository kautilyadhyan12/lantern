"""Approved S0.2 interfaces, pending implementation."""

from collections.abc import Sequence

from pydantic import BaseModel


class Summary(BaseModel):
    covered_lines: int
    num_statements: int
    covered_branches: int
    num_branches: int
    percent_covered: float


class CoveredFile(BaseModel):
    summary: Summary


class CoverageReport(BaseModel):
    totals: Summary
    files: dict[str, CoveredFile]


class QualitySettings(BaseModel):
    coverage_total: float
    coverage_critical: float
    critical_paths: tuple[str, ...]


def evaluate_coverage(
    report: CoverageReport, quality: QualitySettings, present_paths: frozenset[str]
) -> list[str]:
    raise NotImplementedError("S0.2: not implemented yet")


def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError("S0.2: not implemented yet")
