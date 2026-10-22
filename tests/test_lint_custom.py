"""Behavioral examples and generated valid programs for the custom linter."""
import ast
import string

import pytest
from hypothesis import given, strategies as st

from scripts.lint_custom import lint_source, main

pytestmark = pytest.mark.ac("S0.1-AC5")


@pytest.mark.parametrize("handler", ["Exception", "BaseException", ""])
def test_broad_handler_rules(handler):
    source = f"try:\n    work()\nexcept {handler}:\n    pass\n"
    violations = lint_source(source, "src/lantern/example.py")
    assert len(violations) == 1
    assert violations[0].line == 3


@pytest.mark.parametrize("handler", ["Exception", "BaseException", ""])
@pytest.mark.parametrize("body", ["raise", "logger.exception('Operation failed')"])
def test_broad_handlers_allow_reraise_and_exception_logging(handler, body):
    assert lint_source(f"try:\n    work()\nexcept {handler}:\n    {body}\n", "src/example.py") == []


def test_nested_function_does_not_rescue_broad_handler():
    source = "try:\n    work()\nexcept Exception:\n    def unrelated():\n        raise\n"
    assert len(lint_source(source, "src/example.py")) == 1


@pytest.mark.parametrize("comment", ["# type: ignore", "# type: ignore[arg-type]", "# noqa", "# noqa: F401"])
def test_suppression_requires_reason(comment):
    violations = lint_source(f"value = call()  {comment}\n", "src/example.py")
    assert len(violations) == 1
    assert violations[0].line == 1


@pytest.mark.parametrize("comment", ["# type: ignore[arg-type]  # External library has incomplete stubs",
                                     "# noqa: F401  # Public re-export used by callers"])
def test_suppression_with_reason_allowed(comment):
    assert lint_source(f"value = call()  {comment}\n", "src/example.py") == []


@pytest.mark.parametrize("source", [
    "import pytest\npytest.skip('not ready')\n",
    "import pytest\npytest.importorskip('optional')\n",
    "import pytest\npytest.xfail('broken')\n",
    "import pytest\n@pytest.mark.skipif(True, reason='not ready')\ndef test_x():\n    pass\n",
    "import pytest\n@pytest.mark.xfail(reason='broken')\ndef test_x():\n    pass\n",
    "from pytest import skip as stop\nstop('not ready')\n",
])
def test_skip_requires_issue_url(source):
    assert len(lint_source(source, "tests/example.py")) == 1


@pytest.mark.parametrize("call", ["pytest.skip", "pytest.xfail", "pytest.importorskip"])
def test_skip_with_issue_url_allowed(call):
    source = f"import pytest\n{call}('https://github.com/example/lantern/issues/1')\n"
    assert lint_source(source, "tests/example.py") == []


def test_skip_decorator_with_issue_url_allowed():
    source = "import pytest\n@pytest.mark.skipif(True, reason='https://github.com/example/lantern/issues/1')\ndef test_x():\n    pass\n"
    assert lint_source(source, "tests/example.py") == []


@pytest.mark.parametrize("source", ["import time\ntime.sleep(1)\n",
                                     "import time as clock\nclock.sleep(1)\n",
                                     "from time import sleep as pause\npause(1)\n"])
def test_sleep_only_forbidden_in_src(source):
    assert len(lint_source(source, "src/lantern/example.py")) == 1
    assert lint_source(source, "tests/example.py") == []


@pytest.mark.parametrize("value", ["True", "1", "0", "None", "flag", "bool(False)"])
def test_shell_requires_literal_false(value):
    assert len(lint_source(f"subprocess.run(['echo'], shell={value})\n", "scripts/example.py")) == 1


def test_subprocess_without_shell_or_literal_false_allowed():
    assert lint_source("subprocess.run(['echo'], shell=False)\n", "src/example.py") == []
    assert lint_source("subprocess.run(['echo'])\n", "src/example.py") == []


@pytest.mark.parametrize("source", ["print('hello')\n",
                                     "from builtins import print as show\nshow('hello')\n"])
def test_print_only_forbidden_in_src(source):
    assert len(lint_source(source, "src/lantern/example.py")) == 1
    assert lint_source(source, "scripts/example.py") == []


def test_clean_code():
    source = "# A useful comment\nvalue = 'print( and # noqa are data'\ntry:\n    work()\nexcept ValueError:\n    recover()\n"
    assert lint_source(source, "src/lantern/example.py") == []


@st.composite
def valid_programs(draw):
    values = draw(st.lists(st.integers(), min_size=1, max_size=8))
    literal = repr(draw(st.text(max_size=100)))
    name = "value_" + draw(st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=12))
    body = "\n".join(f"{name}_{index} = {value!r}" for index, value in enumerate(values))
    return f"{body}\ndef example(argument):\n    if argument:\n        return {literal}\n    return None\n"


@given(source=valid_programs())
def test_valid_python_never_raises(source):
    ast.parse(source)
    assert lint_source(source, "src/lantern/example.py") == []


@given(prefix=st.integers(min_value=0, max_value=30))
def test_line_positions_and_determinism(prefix):
    source = "\n" * prefix + "print('hello')\n"
    first = lint_source(source, "src/example.py")
    assert first == lint_source(source, "src/example.py")
    assert len(first) == 1
    assert first[0].line == prefix + 1
    assert first[0].path == "src/example.py"
    assert first[0].rule and first[0].message


def test_rules_have_stable_distinct_ids():
    sources = ["try:\n    work()\nexcept Exception:\n    pass\n",
               "value = call()  # noqa\n", "import pytest\npytest.skip('later')\n",
               "import time\ntime.sleep(1)\n", "subprocess.run([], shell=True)\n", "print('hello')\n"]
    ids = []
    for source in sources:
        found = lint_source(source, "src/example.py")
        assert len(found) == 1
        ids.append(found[0].rule)
    assert len(set(ids)) == 6


def test_cli_exit_and_diagnostics(tmp_path, capsys):
    source = tmp_path / "unsafe.py"
    source.write_text("subprocess.run([], shell=True)\n")
    assert main([str(source)]) != 0
    output = capsys.readouterr().out
    assert "unsafe.py" in output and "1" in output and "shell" in output.lower()
    source.write_text("value = 1\n")
    assert main([str(source)]) == 0
