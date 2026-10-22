"""The front page explains Lantern and gives a usable beginner setup."""
import pytest



@pytest.mark.ac("S0.1-AC7")
def test_readme_explains_product_and_codespaces(project_file):
    text = project_file("README.md").lower()
    assert "lantern" in text
    assert "public" in text and ("evidence" in text or "information" in text)
    assert "citation" in text or "sources" in text
    assert "codespace" in text and "browser" in text


@pytest.mark.ac("S0.1-AC7")
def test_readme_has_setup_commands(project_file):
    text = project_file("README.md")
    for command in ["uv sync", "make db", "make hooks", "make check", "lantern db upgrade", "make db-down"]:
        assert command in text, f"README must explain {command}"
    assert "LANTERN_DATABASE_URL" in text and "export" in text


@pytest.mark.ac("S0.1-AC7")
def test_readme_has_only_placeholder_credentials(project_file):
    text = project_file("README.md")
    assert "Codespaces secrets" in text, "Explain where real secrets belong"
    assert "gh auth login" not in text and "github_pat_" not in text
    assert "local" in text.lower() and "credential" in text.lower(), "Label any development-only credentials"
