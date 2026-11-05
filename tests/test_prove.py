"""Only the sanctioned writer may create proof, and failed checks remain visible."""

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from scripts import checks, prove


def git(root, *arguments):
    result = subprocess.run(  # noqa: S603  # Git argument lists in isolated synthetic repositories.
        ["git", *arguments],  # noqa: S607  # Installed Git, no shell or remote operations.
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env={
            **os.environ,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        },
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def commit(root):
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "Synthetic proof input")
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def proof_repo(tmp_path):
    git(tmp_path, "init", "--quiet")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/note.md").write_text("Documentation\n")
    (tmp_path / "code.py").write_text("VALUE = 1\n")
    (tmp_path / ".gitignore").write_text("coverage.json\n.coverage\n.coverage.*\n")
    commit(tmp_path)
    return tmp_path


def successful_step(command, root):
    return checks.StepResult(
        command=tuple(command),
        exit_code=0,
        duration_seconds=0.25,
        output_tail=("115 passed; total coverage 95%; 0 vulnerabilities",),
    )


def generated_report(root, story="S9.1"):
    path = root / f"docs/proofs/PROOF-{story}.md"
    assert path.is_file(), "The sanctioned proof writer must create the report"
    return path.read_text()


@pytest.mark.ac("S0.2-AC4")
@pytest.mark.parametrize("change", ["unstaged", "staged", "deleted"])
def test_dirty_code_refused(proof_repo, change):
    if change == "deleted":
        (proof_repo / "code.py").unlink()
    else:
        (proof_repo / "code.py").write_text("VALUE = 2\n")
        if change == "staged":
            git(proof_repo, "add", "code.py")
    seen = []

    def runner(command, root):
        seen.append(command)
        return successful_step(command, root)

    assert prove.prove("S9.1", [], proof_repo, runner=runner) != 0
    assert seen == []
    assert not (proof_repo / "docs/proofs/PROOF-S9.1.md").exists()


@pytest.mark.ac("S0.2-AC4")
@pytest.mark.parametrize("change", ["edit", "staged", "untracked"])
def test_docs_only_changes_allowed(proof_repo, change):
    path = proof_repo / ("docs/new.md" if change == "untracked" else "docs/note.md")
    path.write_text("Documentation changed\n")
    if change == "staged":
        git(proof_repo, "add", "docs/note.md")
    assert prove.prove("S9.1", [], proof_repo, runner=successful_step) == 0
    assert generated_report(proof_repo).rstrip().endswith("RESULT: PASS")


@pytest.mark.ac("S0.2-AC4")
@pytest.mark.parametrize("change", ["untracked", "code_to_docs", "docs_to_code"])
def test_renamed_or_untracked_code_refused(proof_repo, change):
    if change == "untracked":
        (proof_repo / "new.py").write_text("NEW = 1\n")
    elif change == "code_to_docs":
        git(proof_repo, "mv", "code.py", "docs/code.py")
    else:
        git(proof_repo, "mv", "docs/note.md", "note.md")
    assert prove.prove("S9.1", [], proof_repo, runner=successful_step) != 0
    assert not (proof_repo / "docs/proofs/PROOF-S9.1.md").exists()


@pytest.mark.ac("S0.2-AC4")
@pytest.mark.parametrize("failed_step", range(11))
def test_all_steps_run_after_failure(proof_repo, failed_step):
    seen = []

    def runner(command, root):
        index = len(seen)
        seen.append(tuple(command))
        return checks.StepResult(
            command=tuple(command),
            exit_code=7 if index == failed_step else 0,
            duration_seconds=0.25,
            output_tail=(f"STEP-{index}",),
        )

    assert prove.prove("S9.1", [], proof_repo, runner=runner) != 0
    assert len(seen) == 11
    assert seen[:10] == list(checks.CHECKS)
    assert "scripts/check_acceptance_ids.py" in seen[-1]
    output = generated_report(proof_repo)
    for index in range(11):
        assert f"STEP-{index}" in output
    assert output.rstrip().endswith("RESULT: FAIL")


@pytest.mark.ac("S0.2-AC4")
@pytest.mark.parametrize(
    ("story", "requested", "expected"),
    [
        ("S9.1", [], ["S9.1"]),
        ("M0", ["S0.1", "S0.2"], ["S0.1", "S0.2"]),
    ],
)
def test_defaults_and_combined_ac_stories(proof_repo, story, requested, expected):
    seen = []

    def runner(command, root):
        seen.append(tuple(command))
        return successful_step(command, root)

    assert prove.prove(story, requested, proof_repo, runner=runner) == 0
    assert seen[-1] == (
        "uv",
        "run",
        "python",
        "scripts/check_acceptance_ids.py",
        *expected,
        "--backlog",
        "docs/06_ROADMAP_BACKLOG.md",
    )
    assert generated_report(proof_repo, story).rstrip().endswith("RESULT: PASS")


@pytest.mark.ac("S0.2-AC4")
def test_report_metadata_and_last_30_lines(proof_repo):
    head = git(proof_repo, "rev-parse", "HEAD")
    entries = subprocess.run(
        ["git", "ls-tree", "-r", "HEAD", "--", "code.py", ".gitignore"],  # noqa: S607  # Synthetic local tree only.
        cwd=proof_repo,
        capture_output=True,
        timeout=10,
        check=True,
    ).stdout
    expected_digest = hashlib.sha256(entries).hexdigest()
    before = datetime.now(UTC)

    def runner(command, root):
        return checks.run_step(
            [sys.executable, "-c", "print(*[f'OUTPUT-{i:03}' for i in range(50)], sep='\\n')"],
            root,
        ).model_copy(update={"command": tuple(command)})

    assert prove.prove("S9.1", [], proof_repo, runner=runner) == 0
    after = datetime.now(UTC)
    output = generated_report(proof_repo)
    assert head in output
    assert expected_digest in output
    assert "platform" in output.lower()
    assert "exit" in output.lower()
    assert "duration" in output.lower()
    assert "OUTPUT-000" not in output
    assert "OUTPUT-019" not in output
    assert "OUTPUT-020" in output
    assert "OUTPUT-049" in output
    timestamp = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\+00:00|Z)", output)
    assert timestamp, "Report must include an explicit UTC timestamp"
    instant = datetime.fromisoformat(timestamp[0])
    assert before.replace(microsecond=0) <= instant <= after


@pytest.mark.ac("S0.2-AC4")
@pytest.mark.parametrize("mutation", ["head", "unstaged", "untracked"])
def test_head_or_code_change_fails(proof_repo, mutation):
    calls = []

    def runner(command, root):
        if not calls:
            if mutation == "untracked":
                (root / "new.py").write_text("NEW = 1\n")
            else:
                (root / "code.py").write_text("VALUE = 2\n")
                if mutation == "head":
                    commit(root)
        calls.append(tuple(command))
        return successful_step(command, root)

    assert prove.prove("S9.1", [], proof_repo, runner=runner) != 0
    assert generated_report(proof_repo).rstrip().endswith("RESULT: FAIL")


@pytest.mark.ac("S0.2-AC4")
def test_no_stale_coverage_pass(proof_repo):
    stale = proof_repo / "coverage.json"
    stale.write_text('{"stale": true}')
    observations = []

    def runner(command, root):
        if "pytest" in command:
            observations.append(not stale.exists())
            return successful_step(command, root).model_copy(update={"exit_code": 1})
        if "scripts/coverage_gate.py" in command:
            return successful_step(command, root).model_copy(update={"exit_code": 1})
        return successful_step(command, root)

    assert prove.prove("S9.1", [], proof_repo, runner=runner) != 0
    assert observations == [True]
    assert generated_report(proof_repo).rstrip().endswith("RESULT: FAIL")


@pytest.mark.ac("S0.2-AC4")
def test_coverage_cleanup_does_not_delete_symlink_target(proof_repo, tmp_path):
    target = tmp_path.parent / f"{tmp_path.name}-retained.txt"
    target.write_text("User data\n")
    (proof_repo / "coverage.json").symlink_to(target)
    result = prove.prove("S9.1", [], proof_repo, runner=successful_step)
    assert result in {0, 1, 2}
    assert target.read_text() == "User data\n"


@pytest.mark.ac("S0.2-AC4")
def test_sensitive_values_redacted(proof_repo, monkeypatch):
    value = "synthetic-private-value-42"
    monkeypatch.setenv("LANTERN_TEST_TOKEN", value)

    def runner(command, root):
        return successful_step(command, root).model_copy(
            update={"output_tail": (f"token={value}",)}
        )

    assert prove.prove("S9.1", [], proof_repo, runner=runner) == 0
    assert value not in generated_report(proof_repo)


@pytest.mark.ac("S0.2-AC4")
def test_runner_redacts_sensitive_environment(tmp_path, monkeypatch):
    value = "synthetic-private-value-43"
    monkeypatch.setenv("LANTERN_TEST_TOKEN", value)
    command = [sys.executable, "-c", "import os; print(os.environ['LANTERN_TEST_TOKEN'])"]
    result = checks.run_step(command, tmp_path)
    assert result.exit_code == 0
    assert value not in "\n".join(result.output_tail)
    assert result.output_tail


@pytest.mark.ac("S0.2-AC4")
@pytest.mark.parametrize(
    "story", ["", "../escape", "S9.1/../../escape", "S9.1; touch SENTINEL", "S9.1\nM0"]
)
def test_story_path_traversal_rejected(proof_repo, story):
    seen = []

    def runner(command, root):
        seen.append(command)
        return successful_step(command, root)

    assert prove.prove(story, [], proof_repo, runner=runner) != 0
    assert seen == []
    assert not (proof_repo / "docs/proofs").exists()


@pytest.mark.ac("S0.2-AC4")
def test_make_variables_are_data(repo, tmp_path):
    log = tmp_path / "make-arguments.json"
    fake_uv = tmp_path / "uv"
    fake_uv.write_text(
        f"#!{sys.executable}\nimport json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['MAKE_LOG']).write_text(json.dumps({"
        "'args': sys.argv[1:], 'story': os.environ.get('STORY'),"
        "'ac_stories': os.environ.get('AC_STORIES')}))\n"
    )
    fake_uv.chmod(0o755)
    payload = "S9.1; touch SENTINEL"
    result = subprocess.run(  # noqa: S603  # Shell punctuation is deliberately passed as Make data.
        ["make", "-f", str(repo / "Makefile"), "prove", f"STORY={payload}", "AC_STORIES=S0.1 S0.2"],  # noqa: S607  # Inspect Make's data passing using an isolated fake uv.
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env={
            **os.environ,
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "MAKE_LOG": str(log),
        },
    )
    assert not (tmp_path / "SENTINEL").exists()
    assert result.returncode == 0, result.stdout + result.stderr
    assert log.exists(), "make prove must invoke the Python entry point through uv"
    recorded = json.loads(log.read_text())
    assert recorded == {
        "args": ["run", "python", "-m", "scripts.prove"],
        "story": payload,
        "ac_stories": "S0.1 S0.2",
    }


@pytest.mark.ac("S0.2-AC4")
def test_cli_positional_and_environment_ids(monkeypatch, tmp_path):
    seen = []

    def writer(story, ac_stories, root, **kwargs):
        seen.append((story, tuple(ac_stories), root))
        return 1

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(prove, "prove", writer)
    assert prove.main(["M0", "--ac-stories", "S0.1", "S0.2"]) == 1
    monkeypatch.setenv("STORY", "M0")
    monkeypatch.setenv("AC_STORIES", "S0.1 S0.2")
    assert prove.main([]) == 1
    assert seen == [("M0", ("S0.1", "S0.2"), tmp_path)] * 2


def context():
    return prove.ProofContext(
        story="S9.1",
        commit_sha="a" * 40,
        code_tree="b" * 64,
        recorded_at=datetime(2026, 10, 23, tzinfo=UTC),
        platform="Synthetic test platform",
    )


@pytest.mark.ac("S0.2-AC4")
def test_render_preserves_key_numbers():
    result = successful_step(("uv", "run", "pytest"), None)
    output = prove.render_proof(context(), [result])
    for text in ["115 passed", "95%", "0 vulnerabilities", "0.25", "uv run pytest"]:
        assert text in output
    assert output.rstrip().endswith("RESULT: PASS")


@pytest.mark.ac("S0.2-AC4")
@given(st.text(alphabet="`~ abcXYZ012\n", max_size=200), st.booleans())
def test_render_arbitrary_backticks_and_failure(text, failed):
    result = checks.StepResult(
        command=("synthetic", text),
        exit_code=1 if failed else 0,
        duration_seconds=0,
        output_tail=tuple(text.splitlines()[-30:]),
    )
    output = prove.render_proof(context(), [result])
    expected = "RESULT: FAIL" if failed else "RESULT: PASS"
    assert output.rstrip().endswith(expected)
    fences = re.findall(r"(?m)^(`{3,}|~{3,})(?:[a-z]*)$", output)
    assert len(fences) >= 2
    assert len(fences) % 2 == 0
    for opening, closing in zip(fences[::2], fences[1::2], strict=True):
        assert opening == closing
        assert opening not in text


@pytest.mark.ac("S0.2-AC4")
def test_proof_context_requires_timezone():
    fields = context().model_dump() | {"recorded_at": datetime(2026, 10, 23)}  # noqa: DTZ001  # Deliberately invalid boundary input.
    with pytest.raises(ValidationError):
        prove.ProofContext.model_validate(fields)
