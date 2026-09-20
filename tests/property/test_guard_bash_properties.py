"""S0.2-AC2: properties of the Bash guard's command parser and its protected-write rule."""

from hypothesis import given
from hypothesis import strategies as st

from scripts.hooks import guard_bash

# Text without quote characters is always balanced, so the lexer must never raise on it.
SAFE_TEXT = st.text(
    alphabet=st.sampled_from(list("abcXYZ0123456789 \t/-_.=&|;()<>$*~:,+@#!%^{}[]\\"))
)
WRITE_VERBS = st.sampled_from(["rm", "cp", "mv", "tee", "touch", "mkdir", "truncate"])
PROTECTED = st.sampled_from(["tests/fixtures", "docs/proofs", "docs/reviews", ".prove"])
LEAF = st.sampled_from(["a.json", "x/y.md", "deep/nested/file.txt", "stamp"])
GAP = st.sampled_from([" ", "  ", " \t "])
ALLOWED_COMMANDS = st.sampled_from(
    ["uv run pytest", "uv run pytest tests/unit -q", "git status", "make lint typecheck test"]
)


@given(SAFE_TEXT)
def test_split_segments_never_raises_on_balanced_text(command: str) -> None:
    segments = guard_bash.split_segments(command)
    assert all(isinstance(word, str) for segment in segments for word in segment)
    assert all(segment for segment in segments), "empty segments must be dropped"


@given(WRITE_VERBS, PROTECTED, LEAF, GAP)
def test_a_write_into_a_protected_tree_is_never_allowed(
    verb: str, protected: str, leaf: str, gap: str
) -> None:
    command = f"{verb}{gap}{protected}/{leaf}"
    assert guard_bash.check_command(command) is not None


@given(PROTECTED, LEAF, st.sampled_from([">", ">>"]))
def test_redirection_into_a_protected_tree_is_never_allowed(
    protected: str, leaf: str, operator: str
) -> None:
    assert guard_bash.check_command(f"echo x {operator} {protected}/{leaf}") is not None


@given(ALLOWED_COMMANDS, GAP, GAP)
def test_allowed_commands_survive_surrounding_whitespace(
    command: str, before: str, after: str
) -> None:
    assert guard_bash.check_command(f"{before}{command}{after}") is None


@given(SAFE_TEXT)
def test_check_command_returns_a_known_rule_or_nothing(command: str) -> None:
    violation = guard_bash.check_command(command)
    assert violation is None or violation.rule in guard_bash.RULES
