"""Additional negative cases found by S0.2's advisory test audit."""

import subprocess

import pytest

from scripts import check_acceptance_ids as trace
from scripts import checks


@pytest.mark.ac("S0.2-AC3")
def test_nested_function_is_not_a_collected_test():
    source = (
        "def helper():\n    @pytest.mark.ac('S0.2-AC3')\n    def test_nested():\n        pass\n"
    )
    assert trace.test_marks(source, "tests/test_example.py") == {}


@pytest.mark.ac("S0.2-AC3")
@pytest.mark.parametrize(
    "source",
    [
        "@pytest.mark.ac\ndef test_case(): pass\n",
        "class Helper:\n    @pytest.mark.ac('S0.2-AC3')\n    def test_case(self): pass\n",
    ],
)
def test_malformed_or_uncollected_marker_cannot_satisfy_requirement(source):
    try:
        trace.test_marks(source, "tests/test_example.py")
    except ValueError:
        return
    raise AssertionError("Malformed markers and non-test classes must not satisfy requirements")


@pytest.mark.ac("S0.2-AC1")
@pytest.mark.parametrize("failure", ["spawn", "timeout", "invalid_result"])
def test_runner_boundary_failure_is_recorded_and_later_steps_run(tmp_path, failure):
    seen = []

    def runner(command, root):
        seen.append(tuple(command))
        result = checks.StepResult(
            command=tuple(command),
            exit_code=0,
            duration_seconds=0,
            output_tail=(),
        )
        if len(seen) == 4:
            if failure == "spawn":
                raise OSError("Synthetic process error")
            if failure == "timeout":
                raise subprocess.TimeoutExpired(command, 1)
            return result.model_copy(update={"duration_seconds": float("nan")})
        return result

    try:
        results = checks.run_checks(tmp_path, runner=runner, continue_on_error=True)
    except (OSError, ValueError, subprocess.SubprocessError):
        results = []
    assert len(results) == 10
    assert seen == list(checks.CHECKS)
    assert results[3].exit_code != 0
    assert results[3].output_tail
    assert results[-1].exit_code == 0
