"""S0.1-AC5: scripts/lint_custom.py flags every forbidden pattern and passes clean code."""

import textwrap
from pathlib import Path

import pytest

from scripts import lint_custom


def _rules(source: str, *, in_src: bool = False) -> list[str]:
    violations = lint_custom.check_source(textwrap.dedent(source), "sample.py", in_src=in_src)
    return [violation.rule for violation in violations]


# --- LC001: broad except without raise / log.exception ------------------------------------

LC001_BAD = {
    "except-exception-pass": """
        try:
            work()
        except Exception:
            pass
        """,
    "except-baseexception-logged-without-exception": """
        try:
            work()
        except BaseException as exc:
            log.info("failed", exc=exc)
        """,
    "bare-except": """
        try:
            work()
        except:
            cleanup()
        """,
    "tuple-with-exception": """
        try:
            work()
        except (ValueError, Exception):
            pass
        """,
    "builtins-exception": """
        import builtins
        try:
            work()
        except builtins.Exception:
            pass
        """,
    "raise-only-inside-nested-function": """
        try:
            work()
        except Exception:
            def later():
                raise RuntimeError("never runs here")
        """,
}
LC001_OK = {
    "log-exception": """
        try:
            work()
        except Exception:
            log.exception("work failed")
        """,
    "reraise-wrapped": """
        try:
            work()
        except Exception as exc:
            raise RuntimeError("wrapped") from exc
        """,
    "bare-reraise-after-cleanup": """
        try:
            work()
        except BaseException:
            cleanup()
            raise
        """,
    "narrow-except": """
        try:
            work()
        except ValueError:
            pass
        """,
}


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("source", LC001_BAD.values(), ids=LC001_BAD.keys())
def test_lc001_broad_except_flagged(source: str) -> None:
    assert _rules(source) == ["LC001"]


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("source", LC001_OK.values(), ids=LC001_OK.keys())
def test_lc001_allowed(source: str) -> None:
    assert _rules(source) == []


# --- LC002: type-ignore comments without a trailing reason ---------------------------------

LC002_BAD = [
    "x: int = y  # type: ignore\n",
    "x: int = y  # type: ignore[assignment]\n",
    "x: int = y  # type: ignore[assignment]  #\n",
    "x: int = y  # type: ignore[assignment]  #    \n",
    "x: int = y  # type: ignore[assignment] because stubs\n",
    "x: int = y  # TYPE: IGNORE\n",
]
LC002_OK = [
    "x: int = y  # type: ignore[assignment]  # stub is wrong, https://github.com/o/r/issues/1\n",
    'marker = "# type: ignore"\n',
    "x: int = 1  # ordinary comment\n",
]


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("source", LC002_BAD)
def test_lc002_type_ignore_without_reason_flagged(source: str) -> None:
    assert _rules(source) == ["LC002"]


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("source", LC002_OK)
def test_lc002_allowed(source: str) -> None:
    assert _rules(source) == []


# --- LC003: noqa comments without a trailing reason ----------------------------------------

LC003_BAD = [
    "import os  # noqa\n",
    "import os  # noqa: F401\n",
    "import os  # noqa: F401, E501\n",
    "import os  # NOQA: F401\n",
    "import os  # noqa: F401  #\n",
    "import os  # noqa: F401 re-exported\n",
]
LC003_OK = [
    "import os  # noqa: F401  # re-exported for plugins\n",
    'marker = "# noqa"\n',
]


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("source", LC003_BAD)
def test_lc003_noqa_without_reason_flagged(source: str) -> None:
    assert _rules(source) == ["LC003"]


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("source", LC003_OK)
def test_lc003_allowed(source: str) -> None:
    assert _rules(source) == []


@pytest.mark.ac("S0.1-AC5")
def test_chained_directives_share_trailing_reason() -> None:
    assert _rules("x = y  # type: ignore[misc]  # noqa: E501  # long generated URL\n") == []
    assert _rules("x = y  # type: ignore[misc]  # noqa: E501\n") == ["LC002", "LC003"]
    reasons = lint_custom.parse_suppressions("# noqa: E501  # why # type: ignore")
    assert [(s.kind, s.reason) for s in reasons] == [("noqa", "why"), ("type-ignore", "")]


# --- LC004: pytest skip / xfail without an issue URL ----------------------------------------

ISSUE = "https://github.com/acme/lantern/issues/12"
LC004_BAD = {
    "mark-skip-reason-no-url": """
        import pytest
        @pytest.mark.skip(reason="flaky")
        def test_a(): ...
        """,
    "mark-skip-bare": """
        import pytest
        @pytest.mark.skip
        def test_b(): ...
        """,
    "mark-skipif": """
        import sys
        import pytest
        @pytest.mark.skipif(sys.platform == "win32", reason="no fork on windows")
        def test_c(): ...
        """,
    "mark-xfail": """
        import pytest
        @pytest.mark.xfail(reason="bug")
        def test_d(): ...
        """,
    "imperative-skip": """
        import pytest
        def test_e():
            pytest.skip("later")
        """,
    "imperative-xfail": """
        import pytest
        def test_f():
            pytest.xfail("later")
        """,
    "importorskip": """
        import pytest
        yaml = pytest.importorskip("yaml")
        """,
    "from-import-mark-alias": """
        from pytest import mark as m
        @m.skip(reason="x")
        def test_g(): ...
        """,
    "module-level-pytestmark": """
        import pytest
        pytestmark = pytest.mark.skip
        """,
    "non-literal-reason": f"""
        import pytest
        REASON = "{ISSUE}"
        @pytest.mark.skip(reason=REASON)
        def test_h(): ...
        """,
}
LC004_OK = {
    "mark-skip-with-issue": f"""
        import pytest
        @pytest.mark.skip(reason="blocked upstream {ISSUE}")
        def test_a(): ...
        """,
    "imperative-skip-with-issue": f"""
        import pytest
        def test_b():
            pytest.skip("waiting on {ISSUE}")
        """,
    "skipif-with-issue": f"""
        import sys
        import pytest
        @pytest.mark.skipif(sys.platform == "win32", reason="no fork, {ISSUE}")
        def test_c(): ...
        """,
    "unrelated-skip-attribute": """
        class Reader:
            def skip(self) -> None: ...
        Reader().skip()
        """,
}


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("source", LC004_BAD.values(), ids=LC004_BAD.keys())
def test_lc004_skip_without_issue_url_flagged(source: str) -> None:
    assert _rules(source) == ["LC004"]


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("source", LC004_OK.values(), ids=LC004_OK.keys())
def test_lc004_allowed(source: str) -> None:
    assert _rules(source) == []


# --- LC005: time.sleep in src/ ----------------------------------------------------------------

LC005_BAD = {
    "module-attr": "import time\ntime.sleep(1)\n",
    "from-import": "from time import sleep\nsleep(1)\n",
    "from-import-alias": "from time import sleep as nap\nnap(1)\n",
    "module-alias": "import time as t\nt.sleep(1)\n",
    "reference-not-call": "import time\ndelay = time.sleep\n",
}


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("source", LC005_BAD.values(), ids=LC005_BAD.keys())
def test_lc005_time_sleep_in_src_flagged(source: str) -> None:
    assert _rules(source, in_src=True) == ["LC005"]
    assert _rules(source, in_src=False) == []


@pytest.mark.ac("S0.1-AC5")
def test_lc005_asyncio_sleep_allowed() -> None:
    source = "import asyncio\nasync def pause():\n    await asyncio.sleep(1)\n"
    assert _rules(source, in_src=True) == []


# --- LC006: shell=True anywhere -------------------------------------------------------------

LC006_BAD = [
    'import subprocess\nsubprocess.run("ls", shell=True)\n',
    "import subprocess\nsubprocess.Popen(cmd, shell=True)\n",
    "import subprocess\nsubprocess.check_output(cmd, shell=flag)\n",
    "run(cmd, shell=1)\n",
]
LC006_OK = [
    'import subprocess\nsubprocess.run(["ls"], shell=False)\n',
    'import subprocess\nsubprocess.run(["ls"], check=True)\n',
]


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("source", LC006_BAD)
@pytest.mark.parametrize("in_src", [True, False])
def test_lc006_shell_true_flagged(source: str, in_src: bool) -> None:
    assert _rules(source, in_src=in_src) == ["LC006"]


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("source", LC006_OK)
def test_lc006_allowed(source: str) -> None:
    assert _rules(source, in_src=True) == []


# --- LC007: print( in src/ -------------------------------------------------------------------

LC007_BAD = ['print("hello")\n', "print()\n", 'import builtins\nbuiltins.print("x")\n']


@pytest.mark.ac("S0.1-AC5")
@pytest.mark.parametrize("source", LC007_BAD)
def test_lc007_print_in_src_flagged(source: str) -> None:
    assert _rules(source, in_src=True) == ["LC007"]
    assert _rules(source, in_src=False) == []


@pytest.mark.ac("S0.1-AC5")
def test_lc007_lookalikes_allowed() -> None:
    source = "import pprint\npprint.pprint({})\nreport.print()\n"
    assert _rules(source, in_src=True) == []


# --- clean code, reporting, CLI ----------------------------------------------------------------

CLEAN_MODULE = f'''
"""A clean module that uses every allowed form."""
import asyncio
import logging
import subprocess

import pytest

log = logging.getLogger(__name__)


async def pause() -> None:
    await asyncio.sleep(0)


def run() -> None:
    try:
        subprocess.run(["git", "status"], check=True, shell=False)
    except Exception:
        log.exception("git failed")
        raise


VALUE: int = compute()  # type: ignore[no-untyped-call]  # third-party, no stubs


@pytest.mark.skip(reason="tracked in {ISSUE}")
def test_later() -> None: ...
'''


@pytest.mark.ac("S0.1-AC5")
def test_clean_code_passes() -> None:
    assert lint_custom.check_source(CLEAN_MODULE, "src/lantern/clean.py", in_src=True) == []


@pytest.mark.ac("S0.1-AC5")
def test_violation_reports_path_and_line() -> None:
    source = "import os\n\nprint(os.sep)\n"
    [violation] = lint_custom.check_source(source, "src/lantern/x.py", in_src=True)
    assert violation == lint_custom.Violation(
        path="src/lantern/x.py",
        line=3,
        rule="LC007",
        message=lint_custom.RULES["LC007"],
    )


@pytest.mark.ac("S0.1-AC5")
def test_syntax_error_reported() -> None:
    [violation] = lint_custom.check_source("def broken(:\n", "bad.py", in_src=False)
    assert violation.rule == "LC000"


@pytest.mark.ac("S0.1-AC5")
def test_cli_exit_codes_and_src_scoping(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "src" / "pkg" / "mod.py").write_text('print("hi")\n', encoding="utf-8")
    (tmp_path / "scripts" / "tool.py").write_text('print("hi")\n', encoding="utf-8")
    (tmp_path / "src" / "pkg" / "notes.txt").write_text('print("not python")\n', encoding="utf-8")

    assert lint_custom.main(["--root", str(tmp_path), str(tmp_path / "scripts")]) == 0
    capsys.readouterr()

    assert lint_custom.main(["--root", str(tmp_path), str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "LC007" in out
    assert "mod.py:1" in out
    assert "tool.py" not in out
    assert "notes.txt" not in out


@pytest.mark.ac("S0.1-AC5")
def test_iter_python_files_skips_virtualenvs_and_caches(tmp_path: Path) -> None:
    for rel in ("pkg/a.py", ".venv/lib/b.py", "pkg/__pycache__/c.py", "node_modules/d.py"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    single = tmp_path / "single.py"
    single.write_text("", encoding="utf-8")
    found = sorted(lint_custom.iter_python_files([tmp_path / "pkg", tmp_path / ".venv", single]))
    assert found == [tmp_path / "pkg" / "a.py", single]
