from pathlib import Path

import pytest

from scripts import check_fixture_signatures


@pytest.mark.ac("S0.1-AC4")
def test_no_fixtures_passes(tmp_path: Path) -> None:
    assert check_fixture_signatures.main(["--root", str(tmp_path)]) == 0
    fixtures = tmp_path / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "README.md").write_text("Recorded fixtures only.\n", encoding="utf-8")
    assert check_fixture_signatures.find_fixtures(tmp_path) == []
    assert check_fixture_signatures.main(["--root", str(tmp_path)]) == 0


@pytest.mark.ac("S0.1-AC4")
def test_any_fixture_fails_loudly_until_s03(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = tmp_path / "tests" / "fixtures" / "search.web" / "basic.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("{}", encoding="utf-8")
    assert check_fixture_signatures.find_fixtures(tmp_path) == [fixture]
    assert check_fixture_signatures.main(["--root", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "S0.3" in err
    assert "basic.json" in err
