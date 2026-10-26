"""Behavioral examples and generated valid programs for the custom linter."""

import ast
import string
import subprocess
import sys

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scripts.lint_custom import lint_source, main


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("handler", ["Exception", "BaseException", ""])
def test_broad_handler_rules(handler):
    source = f"try:\n    work()\nexcept {handler}:\n    pass\n"
    violations = lint_source(source, "src/lantern/example.py")
    assert len(violations) == 1
    assert violations[0].line == 3


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("handler", ["Exception", "BaseException", ""])
@pytest.mark.parametrize("body", ["raise", "logger.exception('Operation failed')"])
def test_broad_handlers_allow_reraise_and_exception_logging(handler, body):
    assert lint_source(f"try:\n    work()\nexcept {handler}:\n    {body}\n", "src/example.py") == []


@pytest.mark.ac("S0.1-AC5")
def test_nested_function_does_not_rescue_broad_handler():
    source = "try:\n    work()\nexcept Exception:\n    def unrelated():\n        raise\n"
    assert len(lint_source(source, "src/example.py")) == 1


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize(
    "comment", ["# type: ignore", "# type: ignore[arg-type]", "# noqa", "# noqa: F401"]
)
def test_suppression_requires_reason(comment):
    violations = lint_source(f"value = call()  {comment}\n", "src/example.py")
    assert len(violations) == 1
    assert violations[0].line == 1


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize(
    "comment",
    [
        "# type: ignore[arg-type]  # External library has incomplete stubs",
        "# noqa: F401  # Public re-export used by callers",
    ],
)
def test_suppression_with_reason_allowed(comment):
    assert lint_source(f"value = call()  {comment}\n", "src/example.py") == []


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize(
    "source",
    [
        "import pytest\npytest.skip('not ready')\n",
        "import pytest\npytest.importorskip('optional')\n",
        "import pytest\npytest.xfail('broken')\n",
        "import pytest\n@pytest.mark.skipif(True, reason='not ready')\ndef test_x():\n    pass\n",
        "import pytest\n@pytest.mark.xfail(reason='broken')\ndef test_x():\n    pass\n",
        "from pytest import skip as stop\nstop('not ready')\n",
    ],
)
def test_skip_requires_issue_url(source):
    assert len(lint_source(source, "tests/example.py")) == 1


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("call", ["pytest.skip", "pytest.xfail", "pytest.importorskip"])
def test_skip_with_issue_url_allowed(call):
    source = f"import pytest\n{call}('https://github.com/example/lantern/issues/1')\n"
    assert lint_source(source, "tests/example.py") == []


@pytest.mark.ac("S0.1-AC5")
def test_skip_decorator_with_issue_url_allowed():
    source = (
        "import pytest\n"
        "@pytest.mark.skipif(True, reason='https://github.com/example/lantern/issues/1')\n"
        "def test_x():\n    pass\n"
    )
    assert lint_source(source, "tests/example.py") == []


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("marker", ["skip", "xfail"])
def test_bare_decorator_with_issue_comment_allowed(marker):
    source = (
        f"import pytest\n@pytest.mark.{marker}  # https://github.com/example/lantern/issues/1\n"
        "def test_x():\n    pass\n"
    )
    assert lint_source(source, "tests/example.py") == []


@pytest.mark.ac("S0.1-AC5")
@given(st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=12))
def test_unrelated_imports_preserve_alias_rule_results(suffix):
    alias = "clock_" + suffix
    source = f"import time as {alias}\ndef wait():\n    {alias}.sleep(1)\n"
    unrelated = f"def other():\n    import logging as {alias}\n    {alias}.info('message')\n"
    assert lint_source(source + unrelated, "src/example.py") == lint_source(
        source, "src/example.py"
    )


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize(
    ("source", "rule"),
    [
        (
            (
                "import time as clock\nclass Example:\n    import math as clock\n"
                "    def wait(self):\n        clock.sleep(1)\n"
            ),
            "L004",
        ),
        (
            (
                "import pytest\n@pytest.mark.skip\ndef test_example():\n"
                "    import logging as pytest\n    pytest.info('message')\n"
            ),
            "L003",
        ),
        (
            (
                "from builtins import Exception as Failure\nclass Example:\n"
                "    from builtins import ValueError as Failure\n"
                "    def run(self):\n        try:\n            work()\n"
                "        except Failure:\n            pass\n"
            ),
            "L001",
        ),
    ],
)
def test_scope_rules_for_methods_and_decorators(source, rule):
    assert any(item.rule == rule for item in lint_source(source, "src/example.py"))


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize(
    "expression",
    [
        "lambda: time.sleep(1)",
        "[time.sleep(1) for item in [1]]",
        "{time.sleep(1) for item in [1]}",
        "{item: time.sleep(1) for item in [1]}",
        "(time.sleep(1) for item in [1])",
    ],
)
def test_class_imports_do_not_leak_into_expression_scopes(expression):
    source = f"import time\nclass Example:\n    import asyncio as time\n    wait = {expression}\n"
    assert any(item.rule == "L004" for item in lint_source(source, "src/example.py"))


@pytest.mark.ac("S0.1-AC5")
def test_first_comprehension_iterable_uses_enclosing_class_scope():
    source = (
        "import time\nclass Example:\n    import asyncio as time\n"
        "    values = [item for item in [time.sleep(1)]]\n"
    )
    assert lint_source(source, "src/example.py") == []


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize(
    "source",
    [
        "import time\ntime.sleep(1)\n",
        "import time as clock\nclock.sleep(1)\n",
        "from time import sleep as pause\npause(1)\n",
    ],
)
def test_sleep_only_forbidden_in_src(source):
    assert len(lint_source(source, "src/lantern/example.py")) == 1
    assert lint_source(source, "tests/example.py") == []


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("value", ["True", "1", "0", "None", "flag", "bool(False)"])
def test_shell_requires_literal_false(value):
    assert len(lint_source(f"subprocess.run(['echo'], shell={value})\n", "scripts/example.py")) == 1


@pytest.mark.ac("S0.1-AC5")
def test_subprocess_without_shell_or_literal_false_allowed():
    assert lint_source("subprocess.run(['echo'], shell=False)\n", "src/example.py") == []
    assert lint_source("subprocess.run(['echo'])\n", "src/example.py") == []


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize(
    "source", ["print('hello')\n", "from builtins import print as show\nshow('hello')\n"]
)
def test_print_only_forbidden_in_src(source):
    assert len(lint_source(source, "src/lantern/example.py")) == 1
    assert lint_source(source, "scripts/example.py") == []


@pytest.mark.ac("S0.1-AC5")
def test_clean_code():
    source = (
        "# A useful comment\nvalue = 'print( and # noqa are data'\n"
        "try:\n    work()\nexcept ValueError:\n    recover()\n"
    )
    assert lint_source(source, "src/lantern/example.py") == []


@st.composite
def valid_programs(draw):
    values = draw(st.lists(st.integers(), min_size=1, max_size=8))
    literal = repr(draw(st.text(max_size=100)))
    name = "value_" + draw(st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=12))
    body = "\n".join(f"{name}_{index} = {value!r}" for index, value in enumerate(values))
    return (
        f"{body}\ndef example(argument):\n    if argument:\n"
        f"        return {literal}\n    return None\n"
    )


@pytest.mark.ac("S0.1-AC5")
@given(source=valid_programs())
def test_valid_python_never_raises(source):
    ast.parse(source)
    assert lint_source(source, "src/lantern/example.py") == []


@pytest.mark.ac("S0.1-AC5")
@given(prefix=st.integers(min_value=0, max_value=30))
def test_line_positions_and_determinism(prefix):
    source = "\n" * prefix + "print('hello')\n"
    first = lint_source(source, "src/example.py")
    assert first == lint_source(source, "src/example.py")
    assert len(first) == 1
    assert first[0].line == prefix + 1
    assert first[0].path == "src/example.py"
    assert first[0].rule
    assert first[0].message


@pytest.mark.ac("S0.1-AC5")
def test_rules_have_stable_distinct_ids():
    sources = [
        "try:\n    work()\nexcept Exception:\n    pass\n",
        "value = call()  # noqa\n",
        "import pytest\npytest.skip('later')\n",
        "import time\ntime.sleep(1)\n",
        "subprocess.run([], shell=True)\n",
        "print('hello')\n",
    ]
    ids = []
    for source in sources:
        found = lint_source(source, "src/example.py")
        assert len(found) == 1
        ids.append(found[0].rule)
    assert len(set(ids)) == 6


@pytest.mark.ac("S0.1-AC5")
def test_cli_exit_and_diagnostics(tmp_path, capsys):
    source = tmp_path / "unsafe.py"
    source.write_text("subprocess.run([], shell=True)\n")
    assert main([str(source)]) != 0
    output = capsys.readouterr().out
    assert "unsafe.py" in output
    assert "1" in output
    assert "shell" in output.lower()
    source.write_text("value = 1\n")
    assert main([str(source)]) == 0


@pytest.mark.ac("S0.1-AC5")
def test_script_exit_and_diagnostics(repo, tmp_path):
    source = tmp_path / "unsafe.py"
    source.write_text("subprocess.run([], shell=True)\n")
    command = [sys.executable, str(repo / "scripts/lint_custom.py"), str(source)]
    result = subprocess.run(  # noqa: S603  # Only repository tools and temporary test paths.
        command, cwd=tmp_path, capture_output=True, text=True, timeout=10, check=False
    )
    assert result.returncode != 0, "The executable linter must run its checks"
    assert "unsafe.py" in result.stdout + result.stderr
