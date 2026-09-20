"""T3 adversarial tests for S0.2a — the PreToolUse guard hooks.

Every test here asserts the behaviour the PLAN and docs/05_ENGINEERING_WORKFLOW.md describe.
A failure is therefore a defect in the guards, not in the test.
"""

import io
import json
import posixpath
import shlex
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.hooks import guard_bash, guard_paths, hookio

STORY = "S0.2a"
T3 = guard_bash.T3_REVIEWER_AGENT


def _rule(command: str, *, agent_type: str | None = None) -> str | None:
    violation = guard_bash.check_command(command, agent_type=agent_type)
    return None if violation is None else violation.rule


# ---------------------------------------------------------------------------------------
# 1. Boundary / bypass attacks on GB001 (destructive git)
# ---------------------------------------------------------------------------------------


@pytest.mark.ac("S0.2-AC2")
def test_a_bundled_force_flag_on_git_push_is_still_a_force_push() -> None:
    """`-fu` is `-f -u`. GB001 recognises `-f` alone but not the bundled form.

    guard_bash._is_force_flag already handles bundling for `git clean`; `push` and `checkout`
    compare the flag by equality instead, so the short bundled form escapes.
    """
    assert _rule("git push -fu origin main") == "GB001"


@pytest.mark.ac("S0.2-AC2")
def test_a_bundled_force_flag_on_git_checkout_is_still_a_forced_checkout() -> None:
    assert _rule("git checkout -fB main origin/main") == "GB001"


@pytest.mark.ac("S0.2-AC2")
def test_a_git_global_option_before_the_subcommand_does_not_hide_it() -> None:
    """`git -C <dir> push --force` is a force push; the subcommand scan stops at `-C`'s value."""
    assert _rule("git -C . push --force") == "GB001"


# ---------------------------------------------------------------------------------------
# 2. Heredoc stripping swallows real commands
# ---------------------------------------------------------------------------------------


@pytest.mark.ac("S0.2-AC2")
def test_a_quoted_heredoc_lookalike_cannot_swallow_the_next_command() -> None:
    """`<<WORD` inside a quoted string is not a heredoc, but strip_heredocs treats it as one.

    With no terminator line, everything after the first line is discarded, so a genuinely
    dangerous second command is never judged.
    """
    command = "echo 'a <<EOF b'\nrm -rf /"
    stripped = guard_bash.strip_heredocs(command)
    assert "rm" in stripped, stripped
    assert _rule(command) == "GB002"


@pytest.mark.ac("S0.2-AC2")
def test_a_heredoc_lookalike_cannot_hide_a_force_push() -> None:
    assert _rule('echo "x<<EOF"\ngit push --force') == "GB001"


# ---------------------------------------------------------------------------------------
# 3. GB005 — the sanctioned-writer test is a substring match over every word
# ---------------------------------------------------------------------------------------


@pytest.mark.ac("S0.2-AC2")
def test_naming_a_sanctioned_script_as_an_argument_does_not_sanction_the_write() -> None:
    """_is_sanctioned looks for the writer's name in *any* word, not in the program word.

    So a copy whose *source* happens to be scripts/prove.py may overwrite a PROOF file.
    """
    assert _rule("cp scripts/prove.py docs/proofs/PROOF-S0.2a.md") == "GB005"


@pytest.mark.ac("S0.2-AC2")
def test_reading_the_recorder_does_not_license_writing_a_fixture() -> None:
    assert _rule("cat scripts/record_fixture.py > tests/fixtures/a.json") == "GB005"


@pytest.mark.ac("S0.2-AC2")
def test_dd_writes_are_caught_on_their_output_operand() -> None:
    """`dd` is in WRITE_COMMANDS but names its target as `of=<path>`, which never matches."""
    assert _rule("dd if=/dev/zero of=tests/fixtures/search/basic.json") == "GB005"


# ---------------------------------------------------------------------------------------
# 4. GB006 — 05 section 3.1 scopes the exemption to one script
# ---------------------------------------------------------------------------------------


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize(
    "command",
    [
        "LANTERN_RECORD_FIXTURES=1 make prove STORY=S0.2a",
        "LANTERN_RECORD_FIXTURES=1 make evals",
        "LANTERN_RECORD_FIXTURES=1 uv run python scripts/prove.py S0.2a",
    ],
)
def test_the_recorder_switch_is_refused_outside_the_recorder(command: str) -> None:
    """05 section 3.1 says to block "any command containing LANTERN_RECORD_FIXTURES=1 outside
    scripts/record_fixture.py". The guard widens that exemption to every sanctioned writer and
    to four make targets, so fixtures can be re-recorded from inside `make prove`.
    """
    assert _rule(command) == "GB006"


# ---------------------------------------------------------------------------------------
# 5. GB007 — the reviewer allow-list short-circuits every other rule
# ---------------------------------------------------------------------------------------


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize(
    "command",
    [
        "git diff > .prove/stamp",
        "git show HEAD:pyproject.toml > docs/proofs/PROOF-S0.2a.md",
        "uv run pytest --junitxml=docs/reviews/REVIEW-S0.2a.json",
    ],
)
def test_the_reviewer_allow_list_does_not_also_permit_protected_writes(command: str) -> None:
    """check_segment returns early for an allow-listed reviewer command, so GB005 never runs.

    The reviewer is the one agent that must never be able to forge a proof stamp or a proof file.
    """
    assert _rule(command, agent_type=T3) == "GB005"


# ---------------------------------------------------------------------------------------
# 6. The reviewer cannot write the artefact the workflow asks it for
# ---------------------------------------------------------------------------------------


@pytest.mark.ac("S0.2-AC3")
def test_the_reviewer_can_write_its_own_review_file() -> None:
    """05 section 4 runs T3 with `Write(docs/reviews/*)` and tells it to write
    REVIEW-<story>.json, while guard_paths GP001 protected docs/reviews/ against every Edit/Write.

    T3 raised the contradiction; it was resolved on 2026-09-20 in favour of keeping the tree
    protected and exempting the reviewer alone (ADR-0004). This test pins that resolution: an
    ordinary session is still refused, a reviewer payload is not.
    """
    root = Path.cwd()
    review = f"docs/reviews/REVIEW-{STORY}.json"
    assert guard_paths.check_path(review, cwd=root, root=root) is not None
    assert guard_paths.check_path(review, cwd=root, root=root, agent_type=T3) is None


# ---------------------------------------------------------------------------------------
# 7. Robustness: unicode/RTL, oversized input, malformed payloads, idempotency
# ---------------------------------------------------------------------------------------


RTL = "‮"
ARABIC = "احذف"


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize(
    "command",
    [
        "echo " + RTL + "gnp.txt",
        "echo " + ARABIC + " && rm -rf /",
        "echo é́你好",
        "echo \U0001f600",
        "rm -rf /",
        "echo x > tests/fixtures/أ.json",
    ],
)
def test_unicode_and_rtl_commands_are_parsed_without_crashing(command: str) -> None:
    violation = guard_bash.check_command(command)
    assert violation is None or violation.rule in guard_bash.RULES


@pytest.mark.ac("S0.2-AC2")
def test_rtl_and_arabic_do_not_launder_a_recursive_delete() -> None:
    assert _rule("echo " + ARABIC + " && rm -rf /") == "GB002"


@pytest.mark.ac("S0.2-AC2")
def test_an_oversized_command_is_judged_quickly_and_correctly() -> None:
    padding = " ".join(["echo", *["x" * 64] * 20000])
    command = padding + " && rm -rf /"
    started = time.monotonic()
    assert _rule(command) == "GB002"
    elapsed = time.monotonic() - started
    # The bound matters: settings.json gives the hook 10s, and a hook that times out fails open.
    # Under coverage a tracer makes every line several times slower, so the clock is only read
    # when nothing is tracing (measured 2.4s for this command untraced, 2026-09-20).
    if sys.gettrace() is None:
        assert elapsed < 10, f"judging a {len(command):,}-char command took {elapsed:.1f}s"


@pytest.mark.ac("S0.2-AC2")
def test_deeply_chained_segments_do_not_blow_the_stack() -> None:
    command = " && ".join(["true"] * 5000) + " && git push --force"
    assert _rule(command) == "GB001"


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        '{"tool_input": null}',
        '{"tool_input": {"command": {"nested": "rm -rf /"}}}',
        '{"tool_input": {"command": "rm -rf /"}, "agent_type": 7}',
        '{"tool_input": {"file_path": 12}}',
        '{"hook_event_name": "PreToolUse", "cwd": 5}',
    ],
)
def test_malformed_but_parseable_payloads_never_crash_the_reader(payload: str) -> None:
    hook = hookio.parse_hook_input(payload)
    assert isinstance(hook.command, str)
    assert isinstance(hook.file_path, str)


@pytest.mark.ac("S0.2-AC2")
def test_a_wrongly_typed_agent_type_does_not_grant_reviewer_powers() -> None:
    hook = hookio.parse_hook_input(
        json.dumps({"tool_input": {"command": "uv add httpx"}, "agent_type": 7})
    )
    assert hook.agent_type is None


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize(
    "command",
    ["git push --force", "uv run pytest", "echo x > tests/fixtures/a.json", "rm -rf /"],
)
def test_judging_the_same_command_twice_gives_the_same_answer(command: str) -> None:
    assert guard_bash.check_command(command) == guard_bash.check_command(command)


# ---------------------------------------------------------------------------------------
# 8. guard_paths: traversal, separators, boundaries
# ---------------------------------------------------------------------------------------


@pytest.mark.ac("S0.2-AC3")
@pytest.mark.parametrize(
    "path",
    [
        "src/../tests/fixtures/a.json",
        "src/./../.prove/stamp",
        "tests/fixtures/../fixtures/a.json",
        "./.github/./workflows/ci.yml",
        "docs/proofs/",
        "docs/proofs/sub/../PROOF-S0.1.md",
        "docs\\proofs\\PROOF-S0.1.md",
    ],
)
def test_traversal_forms_of_a_protected_path_are_all_refused(path: str, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    violation = guard_paths.check_path(path, cwd=root, root=root)
    assert violation is not None, path
    assert violation.rule == "GP001"


@pytest.mark.ac("S0.2-AC3")
def test_escaping_above_the_repo_root_is_not_reported_as_inside(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    assert guard_paths.relative_to_repo("../../../etc/passwd", cwd=root, root=root) is None


@pytest.mark.ac("S0.2-AC3")
def test_a_sibling_directory_with_a_protected_prefix_is_not_protected(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    for path in ("docs/proofsheet.md", "tests/fixtures_helpers.py", ".proverbs/x.md"):
        assert guard_paths.check_path(path, cwd=root, root=root) is None, path


@pytest.mark.ac("S0.2-AC3")
def test_the_default_root_still_protects_the_proof_stamp() -> None:
    root = guard_paths.repo_root("")
    violation = guard_paths.check_path(str(root / ".prove" / "stamp"), cwd=root, root=root)
    assert violation is not None
    assert violation.rule == "GP001"


# ---------------------------------------------------------------------------------------
# 9. N-version checks against the PLAN's definitions of the pure functions
# ---------------------------------------------------------------------------------------

WORD = st.text(alphabet=st.sampled_from(list("abAB01_=./-")), min_size=0, max_size=8)


def reference_strip_env_assignments(segment: list[str]) -> tuple[dict[str, str], list[str]]:
    """PLAN: split leading NAME=value prefixes off a segment."""
    env: dict[str, str] = {}
    for index, word in enumerate(segment):
        head, sep, tail = word.partition("=")
        ok = bool(sep) and bool(head) and not head[0].isdigit() and head.isascii()
        ok = ok and all(char.isalnum() or char == "_" for char in head)
        if not ok:
            return env, list(segment[index:])
        env[head] = tail
    return env, []


@pytest.mark.ac("S0.2-AC2")
@given(st.lists(WORD, max_size=6))
@settings(max_examples=300)
def test_nversion_strip_env_assignments(segment: list[str]) -> None:
    assert guard_bash.strip_env_assignments(segment) == reference_strip_env_assignments(segment)


SAFE_WORD = st.text(alphabet=st.sampled_from(list("abcXY012-_./")), min_size=1, max_size=6)


def reference_split_segments(command: str) -> list[list[str]]:
    """PLAN: tokenise into &&/||/;/|-separated segments (no quotes in this alphabet)."""
    segments: list[list[str]] = []
    current: list[str] = []
    for token in shlex.split(command):
        if token in guard_bash.SEGMENT_SEPARATORS:
            if current:
                segments.append(current)
            current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


@pytest.mark.ac("S0.2-AC2")
@given(st.lists(st.one_of(SAFE_WORD, st.sampled_from(["&&", "||", ";", "|"])), max_size=8))
@settings(max_examples=300)
def test_nversion_split_segments(words: list[str]) -> None:
    command = " ".join(words)
    assert guard_bash.split_segments(command) == reference_split_segments(command)


SEG = st.text(alphabet=st.sampled_from(list("abX01.-_")), min_size=1, max_size=5)


def reference_relative_to_repo(path: str, *, cwd: str, root: str) -> PurePosixPath | None:
    """PLAN: path as a repo-relative path, or None when it points outside the repo."""
    text = path.replace("\\", "/").strip().strip("\"'")
    if not text:
        return None
    drive = len(text) > 2 and text[1] == ":" and text[2] == "/"
    if not (text.startswith("/") or drive):
        text = cwd.replace("\\", "/") + "/" + text
    parts_resolved = posixpath.normpath(text).split("/")
    parts_base = posixpath.normpath(root.replace("\\", "/")).split("/")
    if parts_resolved == parts_base:
        return PurePosixPath(".")
    if parts_resolved[: len(parts_base)] != parts_base:
        return None
    return PurePosixPath("/".join(parts_resolved[len(parts_base) :]))


@pytest.mark.ac("S0.2-AC3")
@given(st.lists(SEG, min_size=1, max_size=4), st.lists(SEG, max_size=3))
@settings(max_examples=300)
def test_nversion_relative_to_repo(root_parts: list[str], tail: list[str]) -> None:
    root = "/repo/" + "/".join(root_parts)
    relative = "/".join(tail) if tail else "."
    got = guard_paths.relative_to_repo(relative, cwd=Path(root), root=Path(root))
    expected = reference_relative_to_repo(relative, cwd=root, root=root)
    assert got == expected, (relative, got, expected)


# ---------------------------------------------------------------------------------------
# 10. The hook entry points as the harness calls them
# ---------------------------------------------------------------------------------------


def _bash_payload(command: str, **extra: Any) -> str:
    payload: dict[str, Any] = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    payload.update(extra)
    return json.dumps(payload)


@pytest.mark.ac("S0.2-AC2")
@pytest.mark.parametrize(
    "payload",
    ["", "[]", '{"tool_input": {"command": "rm -rf /"}}', '{"tool_input": {"command": "ls"}}'],
)
def test_main_never_returns_anything_but_allow_or_block(
    payload: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    assert guard_bash.main([]) in {hookio.ALLOW, hookio.BLOCK}
    capsys.readouterr()
