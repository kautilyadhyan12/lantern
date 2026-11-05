"""Independent round-three oracles derived from the approved plans."""

import hashlib
import re
from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scripts.check_acceptance_ids import acceptance_ids
from scripts.check_acceptance_ids import test_marks as collect_marks
from scripts.check_dependencies import denied_packages
from scripts.checks import StepResult
from scripts.code_tree import hash_entries
from scripts.coverage_gate import CoverageReport, QualitySettings, Summary, evaluate_coverage
from scripts.lint_custom import lint_source
from scripts.prove import ProofContext, render_proof


def reference_denied(names):
    banned = {
        "face-recognition",
        "face-recognition-models",
        "deepface",
        "insightface",
        "facenet-pytorch",
        "dlib",
        "litellm",
    }
    return sorted({re.sub(r"[-_.]+", "-", n.lower()) for n in names} & banned)


def reference_hash(entries):
    return hashlib.sha256(
        b"".join(raw for path, raw in entries if path != "docs" and not path.startswith("docs/"))
    ).hexdigest()


def reference_coverage(lines, branches, threshold):
    hit = lines[0] + branches[0]
    count = lines[1] + branches[1]
    return count > 0 and hit * 100 >= threshold * count


def reference_ids(counts):
    return [f"S9.{j}-AC{i}" for j, count in enumerate(counts, 1) for i in range(1, count + 1)]


def reference_marks(ids):
    result = {}
    for i, ac in enumerate(ids):
        result.setdefault(ac, []).append(f"tests/test_generated.py::test_{i}")
    return result


def reference_render(codes):
    return "RESULT: PASS" if codes and all(c == 0 for c in codes) else "RESULT: FAIL"


def reference_lint(call, is_src):
    return call == "f(shell=True)" or (is_src and call == "print(1)")


@pytest.mark.ac("S0.2-AC6")
@given(
    st.lists(
        st.sampled_from(
            [
                "DLIB",
                "face___recognition",
                "deepface",
                "numpy",
                "\u202edlib",
                "dl\u0456b",
                "litellm",
                "dlib-extra",
            ]
        )
    )
)
def test_reference_dependency_normalization(names):
    assert denied_packages(names) == reference_denied(names)


@pytest.mark.ac("S0.2-AC4")
@given(
    st.lists(
        st.tuples(
            st.sampled_from(["docs/a", "docs2/a", "src/\u202e.py", "docs", "src/é\n.py"]),
            st.binary(),
        )
    )
)
def test_reference_exact_tree_bytes(entries):
    assert hash_entries(entries) == reference_hash(entries)


@pytest.mark.ac("S0.2-AC2")
@given(st.integers(0, 10000), st.integers(0, 10000), st.integers(0, 100))
def test_reference_branch_weighting(a, b, threshold):
    summary = Summary(
        covered_lines=a,
        num_statements=a + b,
        covered_branches=b,
        num_branches=b * 2,
        percent_covered=100,
    )
    report = CoverageReport(totals=summary, files={})
    quality = QualitySettings(coverage_total=threshold, coverage_critical=95, critical_paths=())
    assert (not evaluate_coverage(report, quality, frozenset())) == reference_coverage(
        (a, a + b), (b, b * 2), threshold
    )


@pytest.mark.ac("S0.2-AC3")
@given(st.lists(st.integers(1, 8), min_size=1, max_size=8))
def test_reference_backlog(counts):
    source = "\n".join(
        f"### S9.{j} Story\n" + "\n".join(f"- S9.{j}-AC{i} Required" for i in range(1, count + 1))
        for j, count in enumerate(counts, 1)
    )
    assert acceptance_ids(source, [f"S9.{j}" for j in range(1, len(counts) + 1)]) == (
        reference_ids(counts)
    )


@pytest.mark.ac("S0.2-AC3")
@given(st.lists(st.sampled_from(["S9.1-AC1", "S9.1-AC2"])), st.text())
def test_reference_markers(ids, payload):
    source = f"DATA = {payload!r}\n" + "\n".join(
        f"@pytest.mark.ac({ac!r})\ndef test_{i}(): pass" for i, ac in enumerate(ids)
    )
    assert collect_marks(source, "tests/test_generated.py") == reference_marks(ids)


@pytest.mark.ac("S0.2-AC4")
@given(st.lists(st.integers(-5, 5)), st.integers(-1439, 1439))
def test_reference_proof_timezone(codes, offset):
    instant = datetime(2026, 12, 31, 23, 59, tzinfo=timezone(timedelta(minutes=offset)))
    context = ProofContext(
        story="M0", commit_sha="a" * 40, code_tree="b" * 64, recorded_at=instant, platform="test"
    )
    results = [
        StepResult(command=("check",), exit_code=c, duration_seconds=0, output_tail=())
        for c in codes
    ]
    report = render_proof(context, results)
    assert report.splitlines()[-1] == reference_render(codes)
    assert f"UTC: {instant.astimezone(UTC).isoformat()}" in report


@pytest.mark.ac("S0.1-AC5")
@given(st.sampled_from(["print(1)", "f(shell=True)", "f(shell=False)"]), st.booleans())
def test_reference_lint(call, is_src):
    assert bool(lint_source(call, "src/x.py" if is_src else "tests/x.py")) == (
        reference_lint(call, is_src)
    )


@pytest.mark.ac("S0.2-AC3")
@pytest.mark.parametrize("suffix", ["test_case = None\n", "del test_case\n"])
def test_removed_test_does_not_satisfy_acceptance(suffix):
    source = "@pytest.mark.ac('S9.1-AC1')\ndef test_case(): assert False\n" + suffix
    try:
        marks = collect_marks(source, "tests/test_removed.py")
    except ValueError:
        return
    assert "S9.1-AC1" not in marks
