"""Round two: reference oracles written from plans before reading implementation."""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from lantern.config import Settings
from scripts import check_acceptance_ids as trace
from scripts import check_dependencies, code_tree, coverage_gate, lint_custom, prove
from scripts.checks import StepResult


def reference_denied(names):
    prohibited = {
        "face-recognition",
        "face-recognition-models",
        "deepface",
        "insightface",
        "facenet-pytorch",
        "dlib",
        "litellm",
    }
    normalized = {re.sub(r"[-_.]+", "-", name.lower()) for name in names}
    return sorted(normalized & prohibited)


def reference_hash(entries, excluded=()):
    kept = []
    for path, raw in entries:
        if not any(
            path == p.rstrip("/") or path.startswith(p.rstrip("/") + "/")
            for p in ("docs", *excluded)
        ):
            kept.append(raw)
    return hashlib.sha256(b"".join(kept)).hexdigest()


def reference_coverage(covered, total, threshold):
    return total > 0 and 100 * covered >= threshold * total


def reference_ids(stories_and_counts, selected):
    return [
        f"{story}-AC{i}"
        for story, count in stories_and_counts
        if story in selected
        for i in range(1, count + 1)
    ]


def reference_marks(ids, path):
    result = {}
    for index, ac_id in enumerate(ids):
        result.setdefault(ac_id, []).append(f"{path}::test_case_{index}")
    return result


def reference_proof_pass(exit_codes):
    return bool(exit_codes) and all(code == 0 for code in exit_codes)


def reference_lint_for_generated_call(kind, source_path):
    # These generated cases contain exactly one call and no other rule triggers.
    return kind == "shell" or (source_path and kind in {"sleep", "print"})


def reference_database_url(driver, host, database):
    return driver == "postgresql+asyncpg" and bool(host) and bool(database)


@pytest.mark.ac("S0.2-AC6")
@given(
    st.lists(
        st.sampled_from(
            [
                "FACE__..Recognition",
                "dlib",
                "DLIB",
                "dlib-extra",
                "DeepFace",
                "pillow",
                "facenet.PYTORCH",
                "litellm",
                "insightface",
                "face-recognition-models",
                "dl\u0131b",
                "\u202edlib",
                "",
            ]
        ),
        max_size=40,
    )
)
def test_dependency_reference(names):
    assert check_dependencies.denied_packages(names) == reference_denied(names)


@pytest.mark.ac("S0.2-AC4")
@given(
    st.lists(
        st.tuples(
            st.sampled_from(
                [
                    "docs/a",
                    "docs2/a",
                    "src/é.py",
                    "src/\u202e.py",
                    "tests/review/x",
                    "tests/reviewer/x",
                    "src/a\nb.py",
                    "docs",
                ]
            ),
            st.binary(max_size=80),
        ),
        max_size=30,
    )
)
def test_hash_reference(entries):
    assert code_tree.hash_entries(entries, ["tests/review/"]) == reference_hash(
        entries, ["tests/review/"]
    )


@pytest.mark.ac("S0.2-AC2")
@given(st.integers(0, 10**6), st.integers(0, 10**6), st.integers(0, 100))
def test_coverage_reference(total, candidate, threshold):
    covered = min(candidate, total)
    summary = coverage_gate.Summary(
        covered_lines=covered,
        num_statements=total,
        covered_branches=0,
        num_branches=0,
        percent_covered=100,
    )
    report = coverage_gate.CoverageReport(totals=summary, files={})
    quality = coverage_gate.QualitySettings(
        coverage_total=threshold,
        coverage_critical=95,
        critical_paths=(),
    )
    assert (not coverage_gate.evaluate_coverage(report, quality, frozenset())) == (
        reference_coverage(covered, total, threshold)
    )


@pytest.mark.ac("S0.2-AC3")
@given(st.lists(st.integers(0, 8), min_size=1, max_size=10))
def test_backlog_reference(counts):
    sections = [(f"S8.{i + 1}", count) for i, count in enumerate(counts)]
    selected = [story for story, _ in sections][::-2]
    source = "\n".join(
        f"### {story} Example\n"
        + "\n".join(f"- {story}-AC{i} Requirement." for i in range(1, count + 1))
        for story, count in sections
    )
    assert trace.acceptance_ids(source, selected) == reference_ids(sections, selected)


@pytest.mark.ac("S0.2-AC3")
@given(st.lists(st.sampled_from(["S8.1-AC1", "S8.1-AC2"]), max_size=15), st.text())
def test_mark_reference(ids, distraction):
    source = f"DATA = {distraction!r}\n" + "\n".join(
        f"@pytest.mark.ac({ac!r})\ndef test_case_{i}(): pass\n" for i, ac in enumerate(ids)
    )
    path = "tests/test_reference.py"
    assert trace.test_marks(source, path) == reference_marks(ids, path)


@pytest.mark.ac("S0.2-AC4")
@given(st.lists(st.integers(-255, 255), max_size=20), st.integers(-1439, 1439))
def test_render_reference(codes, offset):
    recorded = datetime(2026, 1, 1, tzinfo=timezone(timedelta(minutes=offset)))
    context = prove.ProofContext(
        story="M0",
        commit_sha="a" * 40,
        code_tree="b" * 64,
        recorded_at=recorded,
        platform="synthetic",
    )
    results = [
        StepResult(command=("check",), exit_code=code, duration_seconds=0, output_tail=())
        for code in codes
    ]
    output = prove.render_proof(context, results)
    expected = "PASS" if reference_proof_pass(codes) else "FAIL"
    assert output.splitlines()[-1] == f"RESULT: {expected}"
    assert f"UTC: {recorded.astimezone(UTC).isoformat()}" in output
    assert output.count("## Check ") == len(codes)


@pytest.mark.ac("S0.1-AC5")
@given(st.sampled_from(["shell", "sleep", "print", "safe"]), st.booleans(), st.text())
def test_linter_reference(kind, source_path, distraction):
    statements = {
        "shell": "f(shell=True)",
        "sleep": "time.sleep(1)",
        "print": "print('example')",
        "safe": "f(shell=False)",
    }
    source = f"import time\nDATA = {distraction!r}\n{statements[kind]}\n"
    path = "src/example.py" if source_path else "tests/example.py"
    assert bool(lint_custom.lint_source(source, path)) == reference_lint_for_generated_call(
        kind, source_path
    )


@pytest.mark.ac("S0.1-AC3")
@given(
    st.sampled_from(["postgresql+asyncpg", "postgresql", "sqlite"]),
    st.sampled_from(["localhost", "127.0.0.1", ""]),
    st.sampled_from(["db", "", "example_1"]),
)
def test_settings_reference(driver, host, database):
    raw = f"{driver}://{host}/{database}"
    if reference_database_url(driver, host, database):
        assert Settings(database_url=raw).database_url.get_secret_value() == raw
    else:
        with pytest.raises(ValidationError):
            Settings(database_url=raw)


@pytest.mark.ac("S0.2-AC3")
def test_uncollected_helper_file_cannot_cover_ac(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "backlog.md").write_text("### S8.1 Example\n- S8.1-AC1 Required.\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/helper.py").write_text(
        "import pytest\n@pytest.mark.ac('S8.1-AC1')\ndef test_hidden(): assert False\n"
    )
    assert trace.main(["S8.1", "--backlog", "backlog.md"]) != 0


@pytest.mark.ac("S0.2-AC3")
def test_overwritten_test_cannot_cover_ac():
    source = (
        "import pytest\n@pytest.mark.ac('S8.1-AC1')\ndef test_case(): assert False\n"
        "def test_case(): pass\n"
    )
    try:
        marks = trace.test_marks(source, "tests/test_example.py")
    except ValueError:
        return
    assert "S8.1-AC1" not in marks


@pytest.mark.ac("S0.2-AC4")
@pytest.mark.parametrize("story", ["../outside", "M0/../../x", "M0\u202e", "M" * 10000])
def test_proof_path_boundary(story, tmp_path):
    assert prove.prove(story, [], tmp_path) == 2
    assert list(tmp_path.iterdir()) == []


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize("count", [None, True, "10", -1, float("inf")])
def test_malformed_coverage_counts(count):
    with pytest.raises(ValidationError):
        coverage_gate.Summary(
            covered_lines=count,
            num_statements=10,
            covered_branches=0,
            num_branches=0,
            percent_covered=100,
        )


@pytest.mark.review
def test_committed_proof_and_review_digests(repo):
    proof = (repo / "docs/proofs/PROOF-M0.md").read_text()
    recorded_commit = re.search(r"^Commit: ([a-f0-9]{40,64})$", proof, re.M)[1]
    recorded_digest = re.search(r"^Code tree: ([a-f0-9]{64})$", proof, re.M)[1]
    assert code_tree.code_tree(repo, commit=recorded_commit) == recorded_digest
    review = json.loads((repo / "docs/reviews/REVIEW-M0.json").read_text())
    assert (
        code_tree.code_tree(repo, commit=review["head_sha"], excluded_prefixes=["tests/review"])
        == review["code_tree"]
    )
