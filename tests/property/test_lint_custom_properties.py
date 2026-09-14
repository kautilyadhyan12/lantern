"""Property tests for the pure functions in scripts/lint_custom.py (S0.1-AC5)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scripts import lint_custom

DIRECTIVES = {
    "type: ignore": "type-ignore",
    "type: ignore[misc]": "type-ignore",
    "type:ignore[attr-defined, misc]": "type-ignore",
    "noqa": "noqa",
    "noqa: E501": "noqa",
    "noqa: E501,F401": "noqa",
    "noqa: PLR0913, S603": "noqa",
}
line_text = st.text(
    st.characters(blacklist_categories=("Cc", "Cs"), blacklist_characters="\n\r"), max_size=40
)
slug = st.from_regex(r"[a-z][a-z0-9-]{0,15}", fullmatch=True)

# Statements drawn from the rule examples: valid Python, mixed so rules interact.
SNIPPETS = [
    "import time\n",
    "from time import sleep\n",
    "import pytest\n",
    "import subprocess\n",
    "time.sleep(1)\n",
    "sleep(2)\n",
    'print("x")\n',
    "x = 1  # noqa: E501\n",
    "y = 2  # type: ignore[misc]  # reason\n",
    'subprocess.run(["ls"], shell=True)\n',
    "try:\n    pass\nexcept Exception:\n    pass\n",
    "@pytest.mark.skip\ndef test_x(): ...\n",
    "def f():\n    return 1\n",
]


@pytest.mark.ac("S0.1-AC5")
@given(directive=st.sampled_from(sorted(DIRECTIVES)), reason=line_text)
def test_suppression_reason_required(directive: str, reason: str) -> None:
    parsed = lint_custom.parse_suppression(f"# {directive}  # {reason}")
    assert parsed is not None
    assert parsed.kind == DIRECTIVES[directive]
    assert parsed.reason.strip() == reason.strip()

    bare = lint_custom.parse_suppression(f"# {directive}")
    assert bare is not None
    assert bare.reason == ""


@pytest.mark.ac("S0.1-AC5")
@given(comment=line_text.filter(lambda s: "noqa" not in s.lower() and "ignore" not in s.lower()))
def test_plain_comments_are_not_suppressions(comment: str) -> None:
    assert lint_custom.parse_suppression(f"# {comment}") is None


@pytest.mark.ac("S0.1-AC5")
@given(
    owner=slug,
    repo=slug,
    number=st.integers(min_value=1, max_value=10**6),
    before=line_text.filter(lambda s: "://" not in s),
    after=line_text,
)
def test_issue_url_detection(owner: str, repo: str, number: int, before: str, after: str) -> None:
    url = f"https://github.com/{owner}/{repo}/issues/{number}"
    assert lint_custom.has_issue_url(f"{before} {url} {after}")
    assert not lint_custom.has_issue_url(before)


@pytest.mark.ac("S0.1-AC5")
@given(parts=st.lists(st.sampled_from(SNIPPETS), max_size=12))
def test_check_source_line_numbers_valid_and_scoping(parts: list[str]) -> None:
    source = "".join(parts)
    line_count = source.count("\n") + 1
    in_src = lint_custom.check_source(source, "src/lantern/m.py", in_src=True)
    outside = lint_custom.check_source(source, "scripts/m.py", in_src=False)
    assert all(1 <= v.line <= line_count for v in in_src + outside)
    assert all(v.rule in lint_custom.RULES for v in in_src + outside)
    assert not {v.rule for v in outside} & {"LC005", "LC007"}
    # Scoping only ever removes src-only findings; it never invents or hides others.
    src_only = {"LC005", "LC007"}
    assert [(v.line, v.rule) for v in in_src if v.rule not in src_only] == [
        (v.line, v.rule) for v in outside
    ]


@pytest.mark.ac("S0.1-AC5")
@given(source=st.text(max_size=200))
def test_check_source_never_raises(source: str) -> None:
    violations = lint_custom.check_source(source, "fuzz.py", in_src=True)
    assert all(v.rule in lint_custom.RULES for v in violations)
