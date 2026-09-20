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

Three properties the rules depend on, each of which was a hole once:
  * the command is tokenised, never executed, and every `&&`/`||`/`;`/`|`/newline segment is judged
    on its own, including the inside of a `$(...)` substitution, so chaining launders nothing;
  * the reviewer's allow-list only *narrows* what it may run — every other rule still applies to it;
  * "sanctioned" is decided by the program actually being run, not by a script's name appearing
    somewhere in the words, so `cp scripts/prove.py docs/proofs/…` sanctions nothing.
"""

import argparse
import posixpath
import re
import shlex
from collections.abc import Iterator, Mapping, Sequence
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
# Programs allowed to write the protected trees, matched against the program actually invoked.
SANCTIONED_WRITERS: Final[tuple[str, ...]] = (
    "scripts/record_fixture.py",
    "scripts/prove.py",
    "scripts/materialize_review_tests.py",
    "scripts/check_fixture_signatures.py",
)
# Only these write the protected trees; `make mutate` and `make evals` write elsewhere.
SANCTIONED_MAKE_TARGETS: Final = frozenset({"prove", "t3"})
# GB006 keeps its own, narrower exemption: only the recorder may carry the recording switch.
RECORD_FIXTURES_VAR: Final = "LANTERN_RECORD_FIXTURES"
RECORDER: Final = "scripts/record_fixture.py"
FALSEY: Final = frozenset({"", "0", "false", "no", "off"})

WRITE_COMMANDS: Final[frozenset[str]] = frozenset(
    {"rm", "mv", "cp", "tee", "touch", "mkdir", "rmdir", "truncate", "dd", "ln", "install", "shred"}
)
IN_PLACE_EDITORS: Final = frozenset({"sed", "perl"})
REDIRECTIONS: Final = frozenset({">", ">>", ">|", ">&", "&>"})
SEGMENT_SEPARATORS: Final = frozenset({"&&", "||", "|", "&", ";", ";;", "|&", "(", ")"})
DOWNLOADERS: Final = frozenset({"curl", "wget"})
SHELLS: Final = frozenset({"sh", "bash", "zsh", "dash", "ksh", "fish"})
PYTHONS: Final = frozenset({"python", "python3", "py"})
# Words that stand in front of the program that is really being run.
INTERPRETER_WRAPPERS: Final = frozenset({"uv", "run", "poetry", "pipx", "python", "python3", "py"})
WRAPPER_VALUE_FLAGS: Final = frozenset({"--directory", "--project", "--python", "--with"})
GIT_VALUE_FLAGS: Final = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix"}
)

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

# `$(` and a backtick open a nested command and a newline ends one; turning all three into
# separators makes each nested or following command a segment of its own, so `echo $(rm -rf /)`
# is judged on the `rm`, not on the `echo`.
SUBSTITUTION_RE: Final = re.compile(r"\$\(|`|\n")
# A heredoc body is data, not commands. Only a marker outside quotes opens one — text that merely
# looks like `<<EOF` inside a quoted string does not, or `echo 'a <<EOF b'` would hide what follows.
HEREDOC_RE: Final = re.compile(r"<<-?\s*(?P<quote>['\"]?)(?P<tag>[A-Za-z_][A-Za-z0-9_]*)(?P=quote)")
ENV_ASSIGNMENT_RE: Final = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$", re.S)
OPERAND_NAME_RE: Final = re.compile(r"^(?P<name>[A-Za-z_-][A-Za-z0-9_-]*)=(?P<value>.+)$")


def _unquoted_spans(text: str) -> Iterator[tuple[int, int]]:
    """The (start, end) spans of `text` that lie outside single and double quotes."""
    start, quote = 0, ""
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote, start = "", index + 1
        elif char in "'\"":
            yield start, index
            quote = char
    if not quote:
        yield start, len(text)


def _heredoc_match(command: str) -> re.Match[str] | None:
    """The first heredoc marker whose `<<` lies outside quotes.

    The tag itself is often quoted (`<< 'EOF'`), so only the operator's position decides:
    `cat << 'EOF'` opens a heredoc, `echo 'a <<EOF b'` does not.
    """
    if "<<" not in command:  # cheap exit: most commands carry no heredoc at all
        return None
    spans = list(_unquoted_spans(command))
    for match in HEREDOC_RE.finditer(command):
        if any(start <= match.start() < end for start, end in spans):
            return match
    return None


def strip_heredocs(command: str) -> str:
    """Remove every heredoc body, keeping the commands around it.

    `gh pr create --body-file - << 'EOF' … EOF && echo done` is judged on the `gh` call and on the
    `echo`; the body in between is text the caller is writing, not a command it is running. A
    marker inside quotes does not open a heredoc, and a heredoc whose terminator never arrives is
    refused rather than silently swallowing every command after it.
    """
    while True:
        match = _heredoc_match(command)
        if match is None:
            return command
        body_start = command.find("\n", match.end())
        # Whatever follows the marker on its own line is still part of the command
        # (`cat << EOF > out.json`), so it is kept; only the body below it goes.
        if body_start == -1:
            return command[: match.start()] + command[match.end() :]
        marker_tail = command[match.end() : body_start]
        terminator = re.compile(rf"^[ \t]*{re.escape(match.group('tag'))}[ \t]*$", re.M)
        end = terminator.search(command, body_start + 1)
        if end is None:
            raise HookInputError(f"heredoc <<{match.group('tag')} is never terminated")
        command = command[: match.start()] + marker_tail + command[end.end() :]


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


def _clean(word: str) -> str:
    return word.replace("\\", "/").strip("\"'")


def _name(word: str) -> str:
    """Executable name of a command word: `/usr/bin/rm` and `C:\\git.exe` become `rm` and `git`."""
    return posixpath.basename(_clean(word)).removesuffix(".exe").lower()


def invoked_program(words: Sequence[str]) -> str:
    """The program actually being run, seen through interpreter wrappers.

    `uv run --directory D:/osint python scripts/record_fixture.py x` is the recorder;
    `cp scripts/record_fixture.py docs/proofs/PROOF.md` is `cp`.
    """
    skip_next = False
    for word in words:
        if skip_next:
            skip_next = False
            continue
        if word in WRAPPER_VALUE_FLAGS:
            skip_next = True
            continue
        if word.startswith("-"):
            continue
        if _name(word) in INTERPRETER_WRAPPERS:
            continue
        return _clean(word)
    return _clean(words[0]) if words else ""


def _operand(word: str) -> str:
    """The path part of an operand: `of=tests/fixtures/a.json` and `--out=x` give their values."""
    text = _clean(word)
    match = OPERAND_NAME_RE.match(text)
    if match is None or "/" in match.group("name"):
        return text
    return match.group("value")


def _hits_protected(word: str) -> bool:
    text = _operand(word)
    if not text:
        return False
    candidate = posixpath.normpath(text).lstrip("/")
    padded = f"/{candidate}/"
    return any(f"/{prefix}/" in padded for prefix in PROTECTED_WRITE_PREFIXES)


def _flags(words: Sequence[str]) -> list[str]:
    return [word for word in words if word.startswith("-")]


def _is_sanctioned(words: Sequence[str]) -> bool:
    """True when the program being run is one of the scripts that owns the protected trees."""
    program = invoked_program(words)
    if any(program == writer or program.endswith(f"/{writer}") for writer in SANCTIONED_WRITERS):
        return True
    return _name(words[0]) == "make" and any(
        _clean(word) in SANCTIONED_MAKE_TARGETS for word in words[1:]
    )


def _is_recorder(words: Sequence[str]) -> bool:
    program = invoked_program(words)
    return program == RECORDER or program.endswith(f"/{RECORDER}")


def _git_subcommand(words: Sequence[str]) -> tuple[str, list[str]]:
    """The git subcommand and its arguments, skipping git's own global options and their values."""
    index = 1
    while index < len(words):
        word = words[index]
        if word in GIT_VALUE_FLAGS:
            index += 2
            continue
        if word.startswith("-"):
            index += 1
            continue
        return word, list(words[index + 1 :])
    return "", []


def _is_force_flag(flag: str) -> bool:
    """`--force`, `--force-with-lease`, `-f`, and bundled short forms such as `-fu` or `-fdx`."""
    return flag.startswith("--force") if flag.startswith("--") else "f" in flag[1:]


def _is_recursive_flag(flag: str) -> bool:
    return flag in {"--recursive", "-R"} if flag.startswith("--") else "r" in flag[1:].lower()


def _git_violation(words: Sequence[str]) -> Violation | None:
    if _name(words[0]) != "git":
        return None
    subcommand, rest = _git_subcommand(words)
    flags = _flags(rest)
    forced = any(_is_force_flag(flag) for flag in flags)
    # A refspec beginning with `+` forces the update, with or without `--force`.
    forced_refspec = any(word.startswith("+") for word in rest)
    destructive: Mapping[str, tuple[bool, str]] = {
        "push": (forced or forced_refspec, "`git push` with force"),
        "reset": ("--hard" in flags, "`git reset --hard`"),
        "clean": (forced, "`git clean -f`"),
        "checkout": (forced, "`git checkout --force`"),
        "restore": ("." in rest, "`git restore .`"),
    }
    fires, detail = destructive.get(subcommand, (False, ""))
    return Violation("GB001", detail) if fires else None


def _rm_violation(words: Sequence[str]) -> Violation | None:
    if _name(words[0]) != "rm":
        return None
    flags = _flags(words[1:])
    recursive = any(_is_recursive_flag(flag) for flag in flags)
    forced = any(_is_force_flag(flag) for flag in flags)
    if recursive and forced:
        return Violation("GB002", f"`{' '.join(words[:3])}`")
    return None


def _pip_violation(words: Sequence[str]) -> Violation | None:
    cleaned = [_clean(word) for word in words]
    if "install" not in cleaned[1:]:
        return None
    first = _name(words[0])
    second = cleaned[1] if len(cleaned) > 1 else ""
    runs_pip_module = first in PYTHONS and any(
        word == "pip" or (word.startswith("-m") and "pip" in word) for word in cleaned
    )
    uses_pip = first.startswith("pip") or runs_pip_module or (first == "uv" and second == "pip")
    return Violation("GB003", f"`{' '.join(words[:3])}`") if uses_pip else None


def _protected_write(words: Sequence[str]) -> Violation | None:
    if _is_sanctioned(words):
        return None
    for index, word in enumerate(words[:-1]):
        if word in REDIRECTIONS and _hits_protected(words[index + 1]):
            return Violation("GB005", f"redirecting output into {_operand(words[index + 1])}")
    # `--junitxml=docs/reviews/x.json`: a protected path handed to a flag is an output path.
    for word in words[1:]:
        if word.startswith("-") and "=" in word and _hits_protected(word):
            return Violation("GB005", f"{word.split('=', 1)[0]} would write {_operand(word)}")
    name = _name(words[0])
    edits_in_place = name in IN_PLACE_EDITORS and any(w.startswith("-i") for w in _flags(words))
    if name in WRITE_COMMANDS or edits_in_place:
        targets = [word for word in words[1:] if _hits_protected(word)]
        if targets:
            return Violation("GB005", f"`{name}` would write {_operand(targets[0])}")
    return None


def _t3_allowed(words: Sequence[str]) -> bool:
    probe = (_name(words[0]), *(_clean(word) for word in words[1:]))
    return any(probe[: len(prefix)] == prefix for prefix in T3_ALLOWED_PREFIXES)


def _records_fixtures(env: Mapping[str, str]) -> bool:
    return env.get(RECORD_FIXTURES_VAR, "").strip().lower() not in FALSEY


def check_segment(
    segment: Sequence[str], env: Mapping[str, str], *, agent_type: str | None
) -> Violation | None:
    """Judge one command segment; None means "nothing objectionable".

    The reviewer's allow-list narrows this list, it does not replace it: a command may be on the
    allow-list and still be refused for redirecting into a protected path.
    """
    words = list(segment)
    if not words:
        return None

    if agent_type == T3_REVIEWER_AGENT and not _t3_allowed(words):
        return Violation(
            "GB007",
            f"`{' '.join(words[:3])}` is not on the allow-list "
            "(git diff/log/show/status/rev-parse, uv run pytest/ruff/mypy)",
        )
    if _records_fixtures(env) and not _is_recorder(words):
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
    if _pipes_a_download_into_a_shell(segments):
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
