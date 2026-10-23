"""Requirements are traced to explicit test decorators without running tests."""

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scripts import check_acceptance_ids as trace

BACKLOG = """## M9 — Example
### S9.1 First job (size S)
- S9.1-AC1 First requirement.
- S9.1-AC2 Second requirement.
### S9.2 Other job (size S)
- S9.2-AC1 Another requirement.
"""


def marked_source(identifier, name="test_example"):
    return f"import pytest\n@pytest.mark.ac({identifier!r})\ndef {name}():\n    assert True\n"


def workspace(root, sources):
    (root / "backlog.md").write_text(BACKLOG)
    (root / "tests").mkdir()
    for filename, source in sources.items():
        (root / "tests" / filename).write_text(source)
    return ["S9.1", "--backlog", str(root / "backlog.md")]


@pytest.mark.ac("S0.2-AC3")
def test_selected_story_ids():
    assert trace.acceptance_ids(BACKLOG, ["S9.2", "S9.1"]) == [
        "S9.1-AC1",
        "S9.1-AC2",
        "S9.2-AC1",
    ]


@pytest.mark.ac("S0.2-AC3")
def test_class_test_names():
    source = (
        "import pytest\nclass TestRules:\n"
        "    @pytest.mark.ac('S9.1-AC1')\n    async def test_nested(self):\n        return\n"
    )
    assert trace.test_marks(source, "tests/test_rules.py") == {
        "S9.1-AC1": ["tests/test_rules.py::TestRules::test_nested"],
    }


@pytest.mark.ac("S0.2-AC3")
@pytest.mark.parametrize(
    "argument", ["VARIABLE", "'S9.1-' + 'AC1'", "", "123", "'S9.1-AC1', 'extra'"]
)
def test_literal_marker_required(argument):
    source = f"@pytest.mark.ac({argument})\ndef test_case():\n    pass\n"
    with pytest.raises(ValueError, match=r"(?i)(literal|marker|argument)"):
        trace.test_marks(source, "tests/test_case.py")


@pytest.mark.ac("S0.2-AC3")
def test_unknown_marker_anywhere_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    args = workspace(
        tmp_path,
        {
            "test_selected.py": marked_source("S9.1-AC1")
            + marked_source("S9.1-AC2", "test_second"),
            "test_other.py": marked_source("S99.9-AC1"),
        },
    )
    assert trace.main(args) != 0
    assert "S99.9-AC1" in capsys.readouterr().out


@pytest.mark.ac("S0.2-AC3")
def test_missing_ac_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    args = workspace(tmp_path, {"test_first.py": marked_source("S9.1-AC1")})
    assert trace.main(args) != 0
    assert "S9.1-AC2" in capsys.readouterr().out


@pytest.mark.ac("S0.2-AC3")
def test_unknown_story_fails():
    with pytest.raises(ValueError, match=r"S9\.3"):
        trace.acceptance_ids(BACKLOG, ["S9.3"])


@pytest.mark.ac("S0.2-AC3")
def test_never_imports_test_modules(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    trap = tmp_path / "imported.txt"
    source = (
        f"from pathlib import Path\nPath({str(trap)!r}).write_text('executed')\n"
        "raise RuntimeError('must never be imported')\n"
        + marked_source("S9.1-AC1")
        + marked_source("S9.1-AC2", "test_second")
    )
    args = workspace(tmp_path, {"test_trap.py": source})
    assert trace.main(args) == 0
    assert not trap.exists()
    output = capsys.readouterr().out
    assert "S9.1-AC1" in output
    assert "S9.1-AC2" in output
    assert "test_trap.py::test_second" in output


@pytest.mark.ac("S0.2-AC3")
@pytest.mark.parametrize(
    "body", ["def broken(:", "@pytest.mark.ac(SOMETHING)\ndef test_case(): pass"]
)
def test_invalid_source_fails_cleanly(tmp_path, monkeypatch, capsys, body):
    monkeypatch.chdir(tmp_path)
    args = workspace(tmp_path, {"test_broken.py": body})
    assert trace.main(args) != 0
    output = capsys.readouterr()
    assert "test_broken.py" in output.out + output.err
    assert "Traceback" not in output.out + output.err


@pytest.mark.ac("S0.2-AC3")
@given(st.integers(3, 999), st.integers(1, 9))
def test_unrelated_stories_and_duplicates_do_not_change_selection(story, repetitions):
    extra = f"\n### S9.{story} Unrelated\n- S9.{story}-AC1 Other.\n"
    assert trace.acceptance_ids(BACKLOG + extra, ["S9.1"] * repetitions) == [
        "S9.1-AC1",
        "S9.1-AC2",
    ]


@pytest.mark.ac("S0.2-AC3")
@given(st.text(max_size=200))
def test_strings_are_data_and_file_order_does_not_change_mappings(text):
    first = marked_source("S9.1-AC1") + f"\nEXAMPLE = {json.dumps(text)}\n"
    second = marked_source("S9.1-AC2") + "\nEXAMPLE = \"@pytest.mark.ac('S99.9-AC1')\"\n"
    inputs = [(first, "tests/test_a.py"), (second, "tests/test_b.py")]
    forward = {
        key: names
        for source, path in inputs
        for key, names in trace.test_marks(source, path).items()
    }
    backward = {
        key: names
        for source, path in reversed(inputs)
        for key, names in trace.test_marks(source, path).items()
    }
    assert (
        forward
        == backward
        == {
            "S9.1-AC1": ["tests/test_a.py::test_example"],
            "S9.1-AC2": ["tests/test_b.py::test_example"],
        }
    )
