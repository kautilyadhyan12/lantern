"""The digest identifies committed code using Git's exact tree-entry bytes."""

import hashlib
import os
import subprocess

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scripts import code_tree as tree


def git(root, *arguments):
    result = subprocess.run(  # noqa: S603  # Git argument lists in isolated synthetic repositories.
        ["git", *arguments],  # noqa: S607  # Installed Git, no shell or remote operations.
        cwd=root,
        capture_output=True,
        timeout=10,
        check=False,
        env={
            **os.environ,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        },
    )
    assert result.returncode == 0, result.stderr.decode()
    return result.stdout


def commit(root):
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "Synthetic test tree")
    return git(root, "rev-parse", "HEAD").decode().strip()


@pytest.fixture
def tree_repo(tmp_path):
    git(tmp_path, "init", "--quiet")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/note.md").write_text("Documentation\n")
    (tmp_path / "code.py").write_text("VALUE = 1\n")
    commit(tmp_path)
    return tmp_path


@pytest.mark.ac("S0.2-AC4")
def test_git_entries_match_digest(tree_repo):
    entries = git(tree_repo, "-c", "core.quotePath=true", "ls-tree", "-r", "HEAD")
    code_entries = b"".join(
        line for line in entries.splitlines(keepends=True) if b"\tdocs/" not in line
    )
    assert tree.code_tree(tree_repo) == hashlib.sha256(code_entries).hexdigest()


@pytest.mark.ac("S0.2-AC4")
def test_docs_changes_do_not_change_hash(tree_repo):
    before = tree.code_tree(tree_repo)
    (tree_repo / "docs/note.md").write_text("New documentation\n")
    commit(tree_repo)
    assert tree.code_tree(tree_repo) == before


@pytest.mark.ac("S0.2-AC4")
def test_code_changes_change_hash(tree_repo):
    old_commit = git(tree_repo, "rev-parse", "HEAD").decode().strip()
    before = tree.code_tree(tree_repo)
    (tree_repo / "code.py").write_text("VALUE = 2\n")
    commit(tree_repo)
    assert tree.code_tree(tree_repo) != before
    assert tree.code_tree(tree_repo, commit=old_commit) == before
    (tree_repo / "code.py").write_text("VALUE = 3\n")
    assert tree.code_tree(tree_repo, commit=old_commit) == before


@pytest.mark.ac("S0.2-AC4")
def test_extra_exclusions_and_prefix_boundaries(tree_repo):
    (tree_repo / "tests/review").mkdir(parents=True)
    (tree_repo / "tests/review/test_review.py").write_text("FIRST = 1\n")
    (tree_repo / "docs-backup").mkdir()
    (tree_repo / "docs-backup/keep.md").write_text("Retained\n")
    commit(tree_repo)
    before = tree.code_tree(tree_repo, excluded_prefixes=("tests/review",))
    (tree_repo / "tests/review/test_review.py").write_text("SECOND = 2\n")
    commit(tree_repo)
    assert tree.code_tree(tree_repo, excluded_prefixes=("tests/review",)) == before
    (tree_repo / "docs-backup/keep.md").write_text("Changed\n")
    commit(tree_repo)
    assert tree.code_tree(tree_repo, excluded_prefixes=("tests/review",)) != before


@pytest.mark.ac("S0.2-AC4")
def test_unusual_paths(tree_repo):
    for path in ["docs/quoted\tfile.md", "tabs\tfile.py", "line\nbreak.py", 'quote".py', "café.py"]:
        (tree_repo / path).write_text("# synthetic\n")
    commit(tree_repo)
    quoted = git(tree_repo, "-c", "core.quotePath=true", "ls-tree", "-r", "HEAD")
    raw = git(tree_repo, "ls-tree", "-r", "-z", "HEAD")
    paths = [entry.split(b"\t", 1)[1].decode() for entry in raw.split(b"\0") if entry]
    included = [
        entry
        for path, entry in zip(paths, quoted.splitlines(keepends=True), strict=True)
        if not path.startswith("docs/")
    ]
    assert tree.code_tree(tree_repo) == hashlib.sha256(b"".join(included)).hexdigest()


@pytest.mark.ac("S0.2-AC4")
@given(st.binary(max_size=100), st.sampled_from(["docs", "tests/review"]))
def test_hash_exclusions_preserve_exact_entry_bytes(content, prefix):
    retained = (prefix + "-backup/file.py", b"retained\t" + content + b"\n")
    excluded = (prefix + "/file.py", b"excluded\t" + content + b"\n")
    entries = [excluded, retained]
    expected = hashlib.sha256(retained[1]).hexdigest()
    assert tree.hash_entries(entries, excluded_prefixes=(prefix,)) == expected
    assert tree.hash_entries([retained], excluded_prefixes=(prefix,)) == expected


@pytest.mark.ac("S0.2-AC4")
def test_hash_order_is_significant():
    entries = [("a.py", b"a\n"), ("b.py", b"b\n")]
    assert tree.hash_entries(entries) == hashlib.sha256(b"a\nb\n").hexdigest()
    assert tree.hash_entries(entries) != tree.hash_entries(list(reversed(entries)))


@pytest.mark.ac("S0.2-AC4")
def test_code_tree_cli(tree_repo, monkeypatch, capsys):
    monkeypatch.chdir(tree_repo)
    expected = tree.code_tree(tree_repo)
    assert tree.main([]) == 0
    assert capsys.readouterr().out.strip() == expected
