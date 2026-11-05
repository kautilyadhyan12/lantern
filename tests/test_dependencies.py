"""Every locked package, including transitives, is checked by normalized name."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scripts import check_dependencies as dependencies

PROHIBITED = (
    "face-recognition",
    "face-recognition-models",
    "deepface",
    "insightface",
    "facenet-pytorch",
    "dlib",
    "litellm",
)


@pytest.mark.ac("S0.2-AC6")
@pytest.mark.parametrize("name", PROHIBITED)
def test_each_denied_name_fails(name):
    assert dependencies.denied_packages(["pydantic", name]) == [name]
    assert name in dependencies.DENIED


@pytest.mark.ac("S0.2-AC6")
@pytest.mark.parametrize("name", ["FACE__RECOGNITION", "Face.Recognition", "face---recognition"])
def test_normalized_names(name):
    assert dependencies.denied_packages([name, "face-recognition"]) == ["face-recognition"]


@pytest.mark.ac("S0.2-AC6")
def test_allowed_image_packages():
    assert dependencies.denied_packages(["Pillow", "numpy", "opencv-python", "dlib-tools"]) == []


@pytest.mark.ac("S0.2-AC6")
@pytest.mark.parametrize("name", PROHIBITED)
def test_transitive_package_is_checked(tmp_path, monkeypatch, capsys, name):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "uv.lock").write_text(
        'version = 1\n[[package]]\nname = "lantern"\nversion = "0.1.0"\n'
        f'dependencies = [{{ name = "{name}" }}]\n'
        f'[[package]]\nname = "{name}"\nversion = "1.0.0"\n'
    )
    assert dependencies.main([]) != 0
    assert name in capsys.readouterr().out


@pytest.mark.ac("S0.2-AC6")
@pytest.mark.parametrize(
    "body", [None, "", "not toml [", "version = 1", 'package = "wrong"', '[[package]]\nversion="1"']
)
def test_invalid_lock_fails(tmp_path, monkeypatch, capsys, body):
    monkeypatch.chdir(tmp_path)
    if body is not None:
        (tmp_path / "uv.lock").write_text(body)
    assert dependencies.main([]) != 0
    output = capsys.readouterr()
    assert output.out or output.err
    assert "Traceback" not in output.out + output.err


@pytest.mark.ac("S0.2-AC6")
def test_cli_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "uv.lock").write_text('version=1\n[[package]]\nname="pydantic"\nversion="2.14.1"\n')
    assert dependencies.main([]) == 0


@pytest.mark.ac("S0.2-AC6")
@given(st.sampled_from(PROHIBITED), st.sampled_from(["-", "_", ".", "__", "-._"]))
def test_normalization_is_idempotent_and_case_equivalent(name, separator):
    variant = name.upper().replace("-", separator)
    result = dependencies.denied_packages([variant, name])
    assert result == [name]
    assert dependencies.denied_packages(result) == result
