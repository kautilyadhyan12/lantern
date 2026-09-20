"""Guard hook for shell commands: it reads a proposed command and refuses the dangerous ones.

Refuses, with exit code 2 and a reason on stderr:
  GB001 destructive git — force push, hard reset, `clean -f`, forced checkout/restore
  GB002 `rm -rf`
  GB003 `pip install` (dependencies are added with `uv add`)
  GB004 a download piped into a shell
  GB005 writes into tests/fixtures/, docs/proofs/, docs/reviews/ or .prove/ from anything but the
        sanctioned scripts — those trees are evidence, and only their recorder may write them
  GB006 LANTERN_RECORD_FIXTURES outside scripts/record_fixture.py
  GB007 anything outside the read-only allow-list while running as the t3-reviewer subagent

Everything else is allowed: this is a safety net against mistakes, not a sandbox. Reading a
protected path stays allowed (T3 must read proofs); only write-shaped commands are refused.
The command is tokenised, never executed, and each `&&`/`||`/`;`/`|` segment — including the inside
of a `$(...)` substitution — is checked on its own, so chaining launders nothing.
"""

import argparse
import posixpath
import re
import shlex
from collections.abc import Mapping, Sequence
from typing import Final

from scripts.hooks.hookio import HookInputError, Violation, allow, block, read_hook_input

RULES: Final[Mapping[str, str]] = {
    "GB001": "destructive git command refused",
    "GB002": "recursive force delete refused",
    "GB003": "pip install refused; use `uv add <pkg>`",
    "GB004": "download piped into a shell refused",
    "GB005": "write to a protected path refused; use the script that owns it",
    "GB006": "LANTERN_RECORD_FIXTURES refused; only scripts/record_fixture.py may set it",
    "GB007": "command not on the t3-reviewer allow-list",
}

PROTECTED_WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "tests/fixtures",
    "docs/proofs",
    "docs/reviews",
    ".prove",
)
SANCTIONED_WRITERS: Final[tuple[str, ...]] = (
    "scripts/record_fixture.py",
    "scripts/prove.py",
    "scripts/materialize_review_tests.py",
    "scripts/check_fixture_signatures.py",
)
SANCTIONED_MAKE_TARGETS: Final = frozenset({"prove", "t3", "mutate", "evals"})
WRITE_COMMANDS: Final[frozenset[str]] = frozenset(
    {"rm", "mv", "cp", "tee", "touch", "mkdir", "rmdir", "truncate", "dd", "ln", "install", "shred"}
)
IN_PLACE_EDITORS: Final = frozenset({"sed", "perl"})
REDIRECTIONS: Final = frozenset({">", ">>", ">|", ">&", "&>"})
SEGMENT_SEPARATORS: Final = frozenset({"&&", "||", "|", "&", ";", ";;", "|&", "(", ")"})
DOWNLOADERS: Final = frozenset({"curl", "wget"})
SHELLS: Final = frozenset({"sh", "bash", "zsh", "dash", "ksh", "fish"})
PYTHONS: Final = frozenset({"python", "python3", "py"})

T3_ALLOWED_PREFIXES: Final[tuple[tuple[str, ...], ...]] = (
    ("git", "diff"),
    ("git", "log"),
    ("git", "show"),
    ("git", "status"),
    ("git", "rev-parse"),
    ("uv", "run", "pytest"),
    ("uv", "run", "ruff"),
    ("uv", "run", "mypy"),
)
T3_REVIEWER_AGENT: Final = "t3-reviewer"

RECORD_FIXTURES_VAR: Final = "LANTERN_RECORD_FIXTURES"
FALSEY: Final = frozenset({"", "0", "false", "no", "off"})

# `$(` and a backtick open a nested command and a newline ends one; turning all three into
# separators makes each nested or following command a segment of its own, so `echo $(rm -rf /)`
# is judged on the `rm`, not on the `echo`.
SUBSTITUTION_RE: Final = re.compile(r"\$\(|`|\n")
# A heredoc body is data, not commands: `cat << EOF` … `EOF` may hold apostrophes, quotes and
# prose about dangerous commands. Bodies are removed before parsing; what surrounds them is not.
HEREDOC_RE: Final = re.compile(r"<<-?\s*(?P<quote>['\"]?)(?P<tag>[A-Za-z_][A-Za-z0-9_]*)(?P=quote)")
ENV_ASSIGNMENT_RE: Final = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$", re.S)


def strip_heredocs(command: str) -> str:
    """Remove every heredoc body, keeping the commands around it.

    `gh pr create --body-file - << 'EOF' … EOF && echo done` is judged on the `gh` call and on
    the `echo`; the body in between is text the caller is writing, not a command it is running.
    """
    while True:
        match = HEREDOC_RE.search(command)
        if match is None:
            return command
        body_start = command.find("\n", match.end())
        # Whatever follows the marker on its own line is still part of the command
        # (`cat << EOF > out.json`), so it is kept; only the body below it goes.
        if body_start == -1:  # the body never starts: nothing follows the marker line
            return command[: match.start()] + command[match.end() :]
        marker_tail = command[match.end() : body_start]
        terminator = re.compile(rf"^[ \t]*{re.escape(match.group('tag'))}[ \t]*$", re.M)
        end = terminator.search(command, body_start + 1)
        rest = command[end.end() :] if end else ""
        command = command[: match.start()] + marker_tail + rest


def split_segments(command: str) -> list[list[str]]:
    """Tokenise a command line into its `&&`/`||`/`;`/`|`-separated segments."""
    command = strip_heredocs(command)
    lexer = shlex.shlex(SUBSTITUTION_RE.sub(" ; ", command), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.escape = ""  # keep Windows paths (tests\fixtures\a.json) intact
    try:
        tokens = list(lexer)
    except ValueError as exc:
        raise HookInputError(f"command cannot be parsed ({exc})") from exc

    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in SEGMENT_SEPARATORS:
            if current:
                segments.append(current)
            current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


def strip_env_assignments(segment: Sequence[str]) -> tuple[dict[str, str], list[str]]:
    """Split leading `NAME=value` prefixes off a segment."""
    env: dict[str, str] = {}
    words = list(segment)
    while words:
        match = ENV_ASSIGNMENT_RE.match(words[0])
        if match is None:
            break
        env[match.group("name")] = match.group("value")
        words.pop(0)
    return env, words


def _name(word: str) -> str:
    """Executable name of a command word: `/usr/bin/rm` and `C:\\git.exe` become `rm` and `git`."""
    return posixpath.basename(_clean(word)).removesuffix(".exe").lower()


def _clean(word: str) -> str:
    return word.replace("\\", "/").strip("\"'")


def _hits_protected(word: str) -> bool:
    text = _clean(word)
    if not text:
        return False
    candidate = posixpath.normpath(text).lstrip("/")
    padded = f"/{candidate}/"
    return any(f"/{prefix}/" in padded for prefix in PROTECTED_WRITE_PREFIXES)


def _flags(words: Sequence[str]) -> list[str]:
    return [word for word in words if word.startswith("-")]


def _is_sanctioned(words: Sequence[str]) -> bool:
    cleaned = [_clean(word) for word in words]
    if any(writer in word for word in cleaned for writer in SANCTIONED_WRITERS):
        return True
    return _name(words[0]) == "make" and any(word in SANCTIONED_MAKE_TARGETS for word in cleaned)


def _git_violation(words: Sequence[str]) -> Violation | None:
    if _name(words[0]) != "git":
        return None
    rest = words[1:]
    subcommand = next((word for word in rest if not word.startswith("-")), "")
    flags = _flags(rest)
    destructive: Mapping[str, tuple[bool, str]] = {
        "push": (
            any(f == "-f" or f.startswith("--force") for f in flags),
            "`git push --force`",
        ),
        "reset": ("--hard" in flags, "`git reset --hard`"),
        "clean": (
            any(_is_force_flag(f) for f in flags),
            "`git clean -f`",
        ),
        "checkout": (
            any(f in {"-f", "--force"} for f in flags),
            "`git checkout --force`",
        ),
        "restore": ("." in rest, "`git restore .`"),
    }
    fires, detail = destructive.get(subcommand, (False, ""))
    return Violation("GB001", detail) if fires else None


def _is_force_flag(flag: str) -> bool:
    return flag == "--force" if flag.startswith("--") else "f" in flag[1:]


def _is_recursive_force(words: Sequence[str]) -> bool:
    flags = _flags(words)
    recursive = any(f in {"--recursive", "-R"} or "r" in f[1:].lower() for f in flags)
    force = any(f == "--force" or "f" in f[1:] for f in flags if not f.startswith("--force="))
    return recursive and force


def _rm_violation(words: Sequence[str]) -> Violation | None:
    if _name(words[0]) == "rm" and _is_recursive_force(words[1:]):
        return Violation("GB002", f"`{' '.join(words[:3])}`")
    return None


def _pip_violation(words: Sequence[str]) -> Violation | None:
    if "install" not in [_clean(word) for word in words[1:]]:
        return None
    first = _name(words[0])
    second = _clean(words[1]) if len(words) > 1 else ""
    uses_pip = (
        first in {"pip", "pip3"}
        or (first in PYTHONS and "-m" in words and "pip" in [_clean(w) for w in words])
        or (first == "uv" and second == "pip")
    )
    if uses_pip:
        return Violation("GB003", f"`{' '.join(words[:3])}`")
    return None


def _protected_write(words: Sequence[str]) -> Violation | None:
    if _is_sanctioned(words):
        return None
    for index, word in enumerate(words[:-1]):
        if word in REDIRECTIONS and _hits_protected(words[index + 1]):
            return Violation("GB005", f"redirecting output into {_clean(words[index + 1])}")
    name = _name(words[0])
    edits_in_place = name in IN_PLACE_EDITORS and any(w.startswith("-i") for w in _flags(words))
    if name in WRITE_COMMANDS or edits_in_place:
        targets = [w for w in words[1:] if not w.startswith("-") and _hits_protected(w)]
        if targets:
            return Violation("GB005", f"`{name}` would write {_clean(targets[0])}")
    return None


def _t3_allowed(words: Sequence[str]) -> bool:
    probe = (_name(words[0]), *(_clean(word) for word in words[1:]))
    return any(probe[: len(prefix)] == prefix for prefix in T3_ALLOWED_PREFIXES)


def _records_fixtures(env: Mapping[str, str]) -> bool:
    return env.get(RECORD_FIXTURES_VAR, "").strip().lower() not in FALSEY


def check_segment(
    segment: Sequence[str], env: Mapping[str, str], *, agent_type: str | None
) -> Violation | None:
    """Judge one command segment; None means "nothing objectionable"."""
    words = list(segment)
    if not words:
        return None

    if agent_type == T3_REVIEWER_AGENT:
        if _t3_allowed(words):
            return None
        return Violation(
            "GB007",
            f"`{' '.join(words[:3])}` is not on the allow-list "
            "(git diff/log/show/status/rev-parse, uv run pytest/ruff/mypy)",
        )

    if _records_fixtures(env) and not _is_sanctioned(words):
        return Violation("GB006", f"{RECORD_FIXTURES_VAR} set for `{' '.join(words[:3])}`")
    for rule in (_rm_violation, _git_violation, _pip_violation, _protected_write):
        violation = rule(words)
        if violation is not None:
            return violation
    return None


def check_command(command: str, *, agent_type: str | None = None) -> Violation | None:
    """Judge a whole command line, segment by segment."""
    if not command.strip():
        return None
    segments = split_segments(command)
    if agent_type != T3_REVIEWER_AGENT and _pipes_a_download_into_a_shell(segments):
        return Violation("GB004", "a downloaded script would be run unread")
    for segment in segments:
        env, words = strip_env_assignments(segment)
        violation = check_segment(words, env, agent_type=agent_type)
        if violation is not None:
            return violation
    return None


def _pipes_a_download_into_a_shell(segments: Sequence[Sequence[str]]) -> bool:
    downloaded = False
    for segment in segments:
        _, words = strip_env_assignments(segment)
        if not words:
            continue
        name = _name(words[0])
        if name in DOWNLOADERS:
            downloaded = True
        elif downloaded and name in SHELLS:
            return True
    return False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guard hook: refuse dangerous shell commands")
    parser.parse_args(argv)
    try:
        hook = read_hook_input()
        violation = check_command(hook.command, agent_type=hook.agent_type)
    except HookInputError as exc:
        return block(f"guard_bash: refusing the call: {exc}")
    if violation is None:
        return allow()
    return block(f"guard_bash: {violation.rule} {RULES[violation.rule]}: {violation.detail}")


if __name__ == "__main__":
    raise SystemExit(main())
