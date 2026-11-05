"""Coverage uses raw counts, weighted critical paths and validated reports."""

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from scripts import coverage_gate as gate


def summary(covered=100, total=100, branches=0, branch_total=0):
    opportunities = total + branch_total
    return gate.Summary(
        covered_lines=covered,
        num_statements=total,
        covered_branches=branches,
        num_branches=branch_total,
        percent_covered=100 * (covered + branches) / opportunities if opportunities else 100,
    )


def settings(paths=()):
    return gate.QualitySettings(coverage_total=85, coverage_critical=95, critical_paths=paths)


def report(totals=None, files=None):
    return gate.CoverageReport(totals=totals or summary(), files=files or {})


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize(("covered", "failed"), [(84999, True), (85000, False), (85001, False)])
def test_total_boundary(covered, failed):
    errors = gate.evaluate_coverage(report(summary(covered, 100000)), settings(), frozenset())
    assert bool(errors) is failed


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize(("covered", "failed"), [(94999, True), (95000, False), (95001, False)])
def test_critical_boundary(covered, failed):
    path = "src/lantern/core/rules.py"
    data = report(files={path: gate.CoveredFile(summary=summary(covered, 100000))})
    errors = gate.evaluate_coverage(data, settings((path,)), frozenset({path}))
    assert bool(errors) is failed
    if failed:
        assert any(path in error for error in errors)


@pytest.mark.ac("S0.2-AC2")
def test_weighted_directory_coverage():
    paths = {"src/lantern/core/tiny.py", "src/lantern/core/large.py"}
    files = dict(
        zip(
            sorted(paths),
            [
                gate.CoveredFile(summary=summary(100, 100, 85, 100)),
                gate.CoveredFile(summary=summary(1, 1)),
            ],
            strict=True,
        )
    )
    errors = gate.evaluate_coverage(
        report(files=files), settings(("src/lantern/core",)), frozenset(paths)
    )
    assert errors, "186/201 is below 95%, although the mean of file percentages exceeds 95%"


@pytest.mark.ac("S0.2-AC2")
def test_missing_path_is_reported(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_inputs(tmp_path, report(), ("src/lantern/core",))
    assert gate.main([]) == 0
    output = capsys.readouterr().out.lower()
    assert "src/lantern/core" in output
    assert "not present" in output


@pytest.mark.ac("S0.2-AC2")
def test_existing_unmeasured_path_fails():
    errors = gate.evaluate_coverage(
        report(),
        settings(("src/lantern/core",)),
        frozenset({"src/lantern/core/rules.py"}),
    )
    assert errors
    assert any("src/lantern/core" in error for error in errors)


@pytest.mark.ac("S0.2-AC2")
def test_no_prefix_collision():
    files = {"src/lantern/core_extra/rules.py": gate.CoveredFile(summary=summary())}
    errors = gate.evaluate_coverage(
        report(files=files),
        settings(("src/lantern/core",)),
        frozenset({"src/lantern/core/rules.py", *files}),
    )
    assert errors, "A similarly named directory cannot cover an unmeasured critical path"


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize(
    "invalid",
    [
        {"covered_lines": -1},
        {"covered_lines": 101},
        {"num_branches": -1},
        {"covered_branches": 1},
        {"percent_covered": float("nan")},
        {"percent_covered": float("inf")},
        {"percent_covered": 101},
    ],
)
def test_summary_validation(invalid):
    fields = summary().model_dump() | invalid
    try:
        gate.Summary.model_validate(fields)
    except ValidationError:
        return
    raise AssertionError("Impossible or non-finite coverage summaries must be rejected")


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize("threshold", [-1, 101, float("nan"), float("inf")])
def test_threshold_validation(threshold):
    try:
        gate.QualitySettings(coverage_total=threshold, coverage_critical=95, critical_paths=())
    except ValidationError:
        return
    raise AssertionError("Coverage thresholds must be finite percentages")


@pytest.mark.ac("S0.2-AC2")
def test_rounded_percentage_cannot_hide_failure():
    totals = summary(84999, 100000).model_copy(update={"percent_covered": 85})
    assert gate.evaluate_coverage(report(totals), settings(), frozenset())


@pytest.mark.ac("S0.2-AC2")
def test_existing_file_missing_from_measured_directory_fails():
    files = {"src/lantern/core/measured.py": gate.CoveredFile(summary=summary())}
    errors = gate.evaluate_coverage(
        report(files=files),
        settings(("src/lantern/core",)),
        frozenset({*files, "src/lantern/core/unmeasured.py"}),
    )
    assert errors


def write_inputs(root, data, paths=()):
    (root / "coverage.json").write_text(data.model_dump_json())
    (root / "pyproject.toml").write_text(
        "[tool.lantern.quality]\ncoverage_total = 85\ncoverage_critical = 95\n"
        f"critical_paths = {json.dumps(paths)}\n"
    )


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize(
    "body", [None, "", "{}", "{not json", '{"totals": {"percent_covered": NaN}}']
)
def test_malformed_or_nonfinite_report_fails(tmp_path, monkeypatch, capsys, body):
    monkeypatch.chdir(tmp_path)
    write_inputs(tmp_path, report())
    if body is None:
        (tmp_path / "coverage.json").unlink()
    else:
        (tmp_path / "coverage.json").write_text(body)
    assert gate.main([]) != 0
    output = capsys.readouterr()
    assert "traceback" not in (output.out + output.err).lower()
    assert output.out or output.err


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize(("covered", "status"), [(84, 1), (85, 0)])
def test_cli_status(tmp_path, monkeypatch, covered, status):
    monkeypatch.chdir(tmp_path)
    write_inputs(tmp_path, report(summary(covered)))
    assert gate.main([]) == status


@pytest.mark.ac("S0.2-AC2")
@given(st.integers(85, 100), st.integers(0, 100))
def test_increasing_counts_cannot_break_pass(covered, additional):
    first = gate.evaluate_coverage(report(summary(covered)), settings(), frozenset())
    second = gate.evaluate_coverage(
        report(summary(min(100, covered + additional))),
        settings(),
        frozenset(),
    )
    assert first == second == []


@pytest.mark.ac("S0.2-AC2")
@given(st.lists(st.tuples(st.integers(0, 100), st.integers(1, 100)), min_size=1, max_size=8))
def test_aggregation_bounds_and_order(items):
    counts = [(min(covered, total), total) for covered, total in items]
    files = {
        f"src/lantern/core/f{index}.py": gate.CoveredFile(summary=summary(covered, total))
        for index, (covered, total) in enumerate(counts)
    }
    expected_failure = 100 * sum(c for c, _ in counts) < 95 * sum(t for _, t in counts)
    forwards = gate.evaluate_coverage(
        report(files=files), settings(("src/lantern/core",)), frozenset(files)
    )
    backwards = gate.evaluate_coverage(
        report(files=dict(reversed(list(files.items())))),
        settings(("src/lantern/core",)),
        frozenset(files),
    )
    assert bool(forwards) is expected_failure
    assert forwards == backwards
