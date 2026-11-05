"""Independent edge cases and specification-based reference comparisons for M0.

References cover bounded input grammars, not complete Python/Markdown parsers.
Implementation files had already been inspected before these references were written.
"""

import hashlib
from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from scripts import check_acceptance_ids as trace
from scripts import check_dependencies as dependencies
from scripts import code_tree, coverage_gate, lint_custom, prove
from scripts.checks import StepResult


def reference_hash(entries, exclusions):
    digest = hashlib.sha256()
    excluded_parts = [tuple(p.rstrip("/").split("/")) for p in ["docs", *exclusions]]
    for name, raw in entries:
        parts = tuple(name.split("/"))
        if all(parts[: len(prefix)] != prefix for prefix in excluded_parts):
            digest.update(raw)
    return digest.hexdigest()


def reference_normalize(name):
    result = ""
    for character in name.lower():
        if character in "-_.":
            if not result.endswith("-"):
                result += "-"
        else:
            result += character
    return result


@pytest.mark.ac("S0.2-AC4")
@given(
    st.lists(
        st.tuples(
            st.sampled_from(
                [
                    "docs/a",
                    "docs-backup/a",
                    "docs/\u202e.py",
                    "src/é.py",
                    "tests/review/a",
                    "tests/reviewer/a",
                ]
            ),
            st.binary(max_size=40),
        ),
        max_size=20,
    )
)
def test_reference_hash_with_unicode_and_prefix_collisions(entries):
    exclusions = ["tests/review/"]
    assert code_tree.hash_entries(entries, exclusions) == reference_hash(entries, exclusions)


@pytest.mark.ac("S0.2-AC6")
@given(
    st.lists(
        st.sampled_from(
            [
                "FACE_._Recognition",
                "DeepFace",
                "dlib",
                "dlib-tools",
                "litellm",
                "pillow",
                "INSiGHTFACE",
            ]
        ),
        max_size=30,
    )
)
def test_reference_dependency_names(names):
    denied = {
        "face-recognition",
        "face-recognition-models",
        "deepface",
        "insightface",
        "facenet-pytorch",
        "dlib",
        "litellm",
    }
    expected = sorted({reference_normalize(name) for name in names} & denied)
    assert dependencies.denied_packages(names) == expected


@pytest.mark.ac("S0.2-AC2")
@given(st.integers(1, 10000), st.integers(0, 10000), st.integers(0, 100))
def test_reference_coverage_threshold(total, proposed_covered, threshold):
    covered = min(total, proposed_covered)
    summary = coverage_gate.Summary(
        covered_lines=covered,
        num_statements=total,
        covered_branches=0,
        num_branches=0,
        percent_covered=100,
    )
    report = coverage_gate.CoverageReport(totals=summary, files={})
    quality = coverage_gate.QualitySettings(
        coverage_total=threshold, coverage_critical=95, critical_paths=()
    )
    expected_pass = covered * 100 >= total * threshold
    assert (not coverage_gate.evaluate_coverage(report, quality, frozenset())) == expected_pass


@pytest.mark.ac("S0.2-AC3")
@given(st.lists(st.integers(1, 30), unique=True, min_size=1), st.booleans())
def test_reference_backlog_order(numbers, reverse):
    sections = [(f"S9.{number}", [f"S9.{number}-AC1", f"S9.{number}-AC2"]) for number in numbers]
    source = "\n".join(
        f"### {story} Title\n" + "\n".join(f"- {ac} Text" for ac in acs) for story, acs in sections
    )
    selected = [story for story, _ in sections]
    if reverse:
        selected.reverse()
    expected = [ac for _, acs in sections for ac in acs]
    assert trace.acceptance_ids(source, selected) == expected


@pytest.mark.ac("S0.2-AC3")
@given(st.lists(st.integers(1, 30), unique=True), st.text(max_size=80))
def test_reference_literal_markers(numbers, distraction):
    source = f"DATA = {distraction!r}\n"
    expected = {}
    for number in numbers:
        identifier = f"S9.1-AC{number}"
        name = f"test_case_{number}"
        source += f"@pytest.mark.ac({identifier!r})\ndef {name}():\n    assert 1 == 1\n"
        expected[identifier] = [f"tests/test_generated.py::{name}"]
    assert trace.test_marks(source, "tests/test_generated.py") == expected


@pytest.mark.ac("S0.1-AC5")
@given(st.sampled_from(["print('x')", "time.sleep(1)", "f(shell=True)"]), st.text(max_size=30))
def test_reference_lint_rule_table(statement, text):
    table = {"print('x')": "L006", "time.sleep(1)": "L004", "f(shell=True)": "L005"}
    source = f"DATA = {text!r}\nimport time\n{statement}\n"
    assert [item.rule for item in lint_custom.lint_source(source, "src/sample.py")] == [
        table[statement]
    ]


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("marker", ["skip", "xfail"])
def test_bare_skip_decorators_require_issue(marker):
    source = f"import pytest\n@pytest.mark.{marker}\ndef test_case():\n    assert False\n"
    assert any(item.rule == "L003" for item in lint_custom.lint_source(source, "tests/test_x.py"))


@pytest.mark.ac("S0.1-AC5")
def test_unrelated_local_import_does_not_hide_forbidden_sleep():
    source = (
        "import time\ndef wait():\n    time.sleep(1)\n"
        "def other():\n    import logging as time\n    time.info('example')\n"
    )
    assert any(item.rule == "L004" for item in lint_custom.lint_source(source, "src/sample.py"))


@pytest.mark.ac("S0.2-AC4")
@given(st.lists(st.integers(-255, 255), max_size=20), st.integers(-23, 23))
def test_reference_proof_result_and_timezone(statuses, offset):
    recorded = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=offset)))
    context = prove.ProofContext(
        story="M0",
        commit_sha="a" * 40,
        code_tree="b" * 64,
        recorded_at=recorded,
        platform="synthetic",
    )
    results = [
        StepResult(command=("check",), exit_code=status, duration_seconds=0, output_tail=())
        for status in statuses
    ]
    rendered = prove.render_proof(context, results)
    expected = "PASS" if statuses and not any(statuses) else "FAIL"
    assert rendered.splitlines()[-1] == f"RESULT: {expected}"
    assert f"UTC: {recorded.astimezone(UTC).isoformat()}" in rendered
    assert rendered.count("## Check ") == len(statuses)


@pytest.mark.ac("S0.2-AC4")
def test_proof_rejects_naive_and_oversized_story():
    common = {"commit_sha": "a" * 40, "code_tree": "b" * 64, "platform": "synthetic"}
    with pytest.raises(ValidationError):
        prove.ProofContext(**common, story="M0", recorded_at="2026-01-01T00:00:00")
    with pytest.raises(ValidationError):
        prove.ProofContext(**common, story="M" * 65, recorded_at="2026-01-01T00:00:00Z")


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize("value", [None, float("inf"), float("nan"), -1])
def test_coverage_rejects_nonfinite_and_missing_counts(value):
    with pytest.raises(ValidationError):
        coverage_gate.Summary(
            covered_lines=value,
            num_statements=10,
            covered_branches=0,
            num_branches=0,
            percent_covered=100,
        )
