"""Exercise fresh-tool installation without downloading or running real tools."""

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


def setup_source(repo):
    path = repo / ".devcontainer/setup.sh"
    assert path.is_file(), "ADR 0005 requires the verified setup installer"
    return path.read_text()


def archive(path, members):
    mode = "w:xz" if path.name.endswith(".xz") else "w:gz"
    with tarfile.open(path, mode) as bundle:
        for name, output in members.items():
            content = f"#!/bin/sh\nprintf '%s\\n' '{output}'\n".encode()
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            entry.mode = 0o755
            bundle.addfile(entry, io.BytesIO(content))


def prepare(repo, tmp_path):
    source = setup_source(repo)
    versions = {}
    for tool in ["NODE", "UV", "CODEX"]:
        match = re.search(rf"\b{tool}_VERSION=['\"]?([\d.]+)", source)
        assert match, f"Commit the exact {tool} release version"
        versions[tool] = match[1]

    downloads = tmp_path / "downloads"
    downloads.mkdir()
    names = {
        "NODE": f"node-v{versions['NODE']}-linux-x64.tar.xz",
        "UV": "uv-x86_64-unknown-linux-gnu.tar.gz",
        "CODEX": "codex-x86_64-unknown-linux-musl.tar.gz",
    }
    archive(
        downloads / names["NODE"],
        {
            f"node-v{versions['NODE']}-linux-x64/bin/{name}": f"v{versions['NODE']}"
            for name in ["node", "npm", "npx"]
        },
    )
    archive(
        downloads / names["UV"],
        {f"uv-x86_64-unknown-linux-gnu/{name}": f"uv {versions['UV']}" for name in ["uv", "uvx"]},
    )
    archive(
        downloads / names["CODEX"],
        {"codex-x86_64-unknown-linux-musl": f"codex-cli {versions['CODEX']}"},
    )
    # Substitute only test archive digests in a temporary installer copy. The
    # real checksum program and extraction/installation commands still run.
    for tool, name in names.items():
        digest = hashlib.sha256((downloads / name).read_bytes()).hexdigest()
        source, count = re.subn(
            rf"(\b{tool}_SHA256=['\"]?)[a-f0-9]{{64}}", rf"\g<1>{digest}", source
        )
        assert count == 1, f"Commit one SHA256 pin for {tool}"
    installer = tmp_path / "setup.sh"
    installer.write_text(source)
    commands = tmp_path / "commands"
    commands.mkdir()
    curl = commands / "curl"
    curl.write_text(
        f"#!{sys.executable}\n"
        "import os, pathlib, shutil, sys\n"
        "args = sys.argv[1:]\n"
        "assert '--proto' in args and args[args.index('--proto') + 1] == '=https'\n"
        "assert '--proto-redir' in args\n"
        "assert args[args.index('--proto-redir') + 1] == '=https'\n"
        "assert '--max-time' in args and any(x in args for x in ['--fail', '-f'])\n"
        "url = next(x for x in args if x.startswith('https://'))\n"
        "name = url.rsplit('/', 1)[1]\n"
        "assert url.startswith(('https://nodejs.org/dist/', "
        "'https://github.com/astral-sh/uv/releases/download/', "
        "'https://github.com/openai/codex/releases/download/'))\n"
        "with open(os.environ['SETUP_TRACE'], 'a') as trace:\n"
        "    trace.write(name + '\\n')\n"
        "if os.environ.get('SETUP_FAIL') == name:\n"
        "    sys.exit(22)\n"
        "output = args[args.index('--output') + 1]\n"
        "if os.environ.get('SETUP_CORRUPT') == name:\n"
        "    pathlib.Path(output).write_bytes(b'unauthenticated archive')\n"
        "else:\n"
        "    shutil.copyfile(pathlib.Path(os.environ['SETUP_DOWNLOADS']) / name, output)\n"
    )
    curl.chmod(0o755)
    env = {
        "PATH": f"{commands}:/usr/bin:/bin",
        "TMPDIR": str(tmp_path),
        "SETUP_DOWNLOADS": str(downloads),
        "SETUP_TRACE": str(tmp_path / "trace"),
    }
    return installer, tmp_path / "installed", commands, names, versions, env


def run_setup(installer, root, env):
    return subprocess.run(  # noqa: S603  # Local installer copy and isolated test environment.
        ["/bin/bash", str(installer), str(root)],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


@pytest.mark.ac("S0.1-AC6")
def test_image_is_maintained_and_digest_pinned(repo):
    config = json.loads((repo / ".devcontainer/devcontainer.json").read_text())
    assert re.fullmatch(
        r"mcr\.microsoft\.com/devcontainers/universal:6(?:\.\d+){0,2}@sha256:[a-f0-9]{64}",
        config["image"],
    ), "Use the checked current Microsoft image with an immutable digest"


@pytest.mark.ac("S0.1-AC6")
def test_setup_registered_and_tools_selected_first(repo):
    config = json.loads((repo / ".devcontainer/devcontainer.json").read_text())
    assert ".devcontainer/setup.sh" in str(config.get("postCreateCommand", "")), (
        "Run the repository's verified setup instead of a downloaded installer"
    )
    assert config.get("remoteUser") == "codespace"
    expected = "/home/codespace/.local/share/lantern-tools/bin:"
    assert config.get("remoteEnv", {}).get("PATH", "").startswith(expected)
    assert not re.search(r"\|\s*(?:ba)?sh\b|npm install", str(config["postCreateCommand"]))


@pytest.mark.ac("S0.1-AC6")
def test_verified_archives_produce_working_tools(repo, tmp_path):
    installer, root, _, names, versions, env = prepare(repo, tmp_path)
    result = run_setup(installer, root, env)
    assert result.returncode == 0, result.stderr
    assert sorted(Path(env["SETUP_TRACE"]).read_text().splitlines()) == sorted(names.values())
    for tool in ["node", "npm", "npx", "uv", "uvx", "codex"]:
        executable = root / "bin" / tool
        assert executable.is_file(), tool
        assert os.access(executable, os.X_OK), tool
        output = subprocess.run(  # noqa: S603  # Executable is authored by this test.
            [str(executable), "--version"], capture_output=True, text=True, timeout=5, check=True
        ).stdout
        version = versions[{"npm": "NODE", "npx": "NODE", "uvx": "UV"}.get(tool, tool.upper())]
        assert version in output
    assert "nodejs.org" in setup_source(repo), "Node must come from its official release server"


@pytest.mark.ac("S0.1-AC6")
@pytest.mark.parametrize("tool", ["NODE", "UV", "CODEX"])
def test_bad_digest_never_extracts_or_installs(repo, tmp_path, tool):
    installer, root, commands, names, _, env = prepare(repo, tmp_path)
    env["SETUP_CORRUPT"] = names[tool]
    tar = commands / "tar"
    marker = tmp_path / "extracted"
    tar.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 89\n")
    tar.chmod(0o755)
    result = run_setup(installer, root, env)
    assert result.returncode != 0, "A checksum mismatch must fail setup"
    assert "checksum" in (result.stdout + result.stderr).lower()
    assert not marker.exists(), "Authenticate every download before extracting any archive"
    assert not root.exists() or not list(root.rglob("*")), "Do not install unauthenticated tools"


@pytest.mark.ac("S0.1-AC6")
def test_last_download_failure_keeps_previous_installation(repo, tmp_path):
    installer, root, _, names, _, env = prepare(repo, tmp_path)
    root.mkdir()
    sentinel = root / "keep"
    sentinel.write_text("previous installation")
    env["SETUP_FAIL"] = names["CODEX"]
    result = run_setup(installer, root, env)
    assert result.returncode != 0, "An HTTP failure must propagate"
    assert sentinel.read_text() == "previous installation"
    assert list(root.iterdir()) == [sentinel], "Do not partially install earlier downloads"


@pytest.mark.ac("S0.1-AC6")
def test_unsupported_architecture_rejected_before_download(repo, tmp_path):
    installer, root, commands, _, _, env = prepare(repo, tmp_path)
    uname = commands / "uname"
    uname.write_text('#!/bin/sh\ncase "$1" in -s) echo Linux;; *) echo aarch64;; esac\n')
    uname.chmod(0o755)
    result = run_setup(installer, root, env)
    assert result.returncode != 0
    assert "x86_64" in (result.stdout + result.stderr)
    assert not Path(env["SETUP_TRACE"]).exists(), "Reject unsupported hosts before downloading"
    assert not root.exists()
