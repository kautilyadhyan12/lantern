"""Custom lint rules for the Lantern codebase.

Usage: uv run python scripts/lint_custom.py [--root DIR] PATH [PATH ...]

Rules (LC005/LC007 apply only to files under <root>/src):
  LC000  file could not be read or parsed
  LC001  `except Exception` / `except BaseException` / bare `except` whose handler neither
         re-raises nor calls `<logger>.exception(...)`
  LC002  `# type: ignore` without a trailing reason comment
  LC003  `# noqa` without a trailing reason comment
  LC004  pytest skip/skipif/xfail/importorskip without an issue URL in a literal argument
  LC005  `time.sleep` in src/
  LC006  any call passing `shell=` anything but a literal falsy value
  LC007  `print` in src/

A suppression reason is a separate comment after the directive and its codes:
    value = thing()  # type: ignore[no-untyped-call]  # vendor lib ships no stubs
Directives chained back to back share the reason that follows the last one.
"""

import argparse
import ast
import io
import re
import sys
import tokenize
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

RULES: Final[Mapping[str, str]] = {
    "LC000": "file could not be read or parsed",
    "LC001": "broad except must re-raise or call <logger>.exception(...)",
    "LC002": "`# type: ignore` needs a trailing reason: `# type: ignore[code]  # why`",
    "LC003": "`# noqa` needs a trailing reason: `# noqa: CODE  # why`",
    "LC004": "pytest skip/xfail needs an issue URL (https://.../issues/<n>) in a literal reason",
    "LC005": "time.sleep is forbidden in src/ (use asyncio.sleep or an injected clock)",
    "LC006": "shell=True is forbidden; pass an argument list",
    "LC007": "print is forbidden in src/ (use structlog)",
}

BROAD_EXCEPTIONS: Final = frozenset(
    {"Exception", "BaseException", "builtins.Exception", "builtins.BaseException"}
)
SKIP_TARGETS: Final = frozenset(
    {
        "pytest.skip",
        "pytest.xfail",
        "pytest.importorskip",
        "pytest.mark.skip",
        "pytest.mark.skipif",
        "pytest.mark.xfail",
    }
)
SRC_ONLY_TARGETS: Final[Mapping[str, str]] = {
    "time.sleep": "LC005",
    "print": "LC007",
    "builtins.print": "LC007",
}
EXCLUDED_DIRS: Final = frozenset(
    {"__pycache__", "node_modules", "mutants", "build", "dist", "venv"}
)

_DIRECTIVE: Final = re.compile(
    r"#\s*(?:"
    r"(?P<type_ignore>type:\s*ignore\b(?:\[[^\]]*\])?)"
    r"|(?P<noqa>noqa\b(?::\s*[A-Z]+[0-9]+(?:[\s,]+[A-Z]+[0-9]+)*)?)"
    r")",
    re.IGNORECASE,
)
_REASON: Final = re.compile(r"\s*#(.*)", re.DOTALL)
_ISSUE_URL: Final = re.compile(r"https?://\S+/issues/\d+")


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    message: str


@dataclass(frozen=True)
class Suppression:
    kind: Literal["type-ignore", "noqa"]
    reason: str


def parse_suppressions(comment: str) -> list[Suppression]:
    """Every `type: ignore` / `noqa` directive in a comment, with its (stripped) reason."""
    matches = list(_DIRECTIVE.finditer(comment))
    found: list[Suppression] = []
    inherited = ""
    for index in reversed(range(len(matches))):
        match = matches[index]
        is_last = index == len(matches) - 1
        tail = comment[match.end() : len(comment) if is_last else matches[index + 1].start()]
        if not is_last and not tail.strip():
            reason = inherited  # chained directly into the next directive
        else:
            reason_match = _REASON.fullmatch(tail)
            reason = reason_match.group(1).strip() if reason_match else ""
        inherited = reason
        kind: Literal["type-ignore", "noqa"] = "type-ignore" if match["type_ignore"] else "noqa"
        found.append(Suppression(kind=kind, reason=reason))
    found.reverse()
    return found


def parse_suppression(comment: str) -> Suppression | None:
    """The first directive in a comment, or None if the comment has none."""
    found = parse_suppressions(comment)
    return found[0] if found else None


def has_issue_url(text: str) -> bool:
    return _ISSUE_URL.search(text) is not None


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    """Local name -> fully qualified name for absolute imports anywhere in the module."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname is not None:
                    aliases[alias.asname] = alias.name
                else:
                    top = alias.name.partition(".")[0]
                    aliases[top] = top
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _qualified_name(node: ast.expr, aliases: Mapping[str, str]) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(aliases.get(current.id, current.id))
    return ".".join(reversed(parts))


def _walk_same_scope(nodes: Iterable[ast.AST]) -> Iterator[ast.AST]:
    """Walk nodes without descending into nested functions, lambdas or classes."""
    stack = list(nodes)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | ast.ClassDef):
            stack.extend(ast.iter_child_nodes(node))


def _is_broad(handler: ast.ExceptHandler, aliases: Mapping[str, str]) -> bool:
    if handler.type is None:
        return True
    types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(_qualified_name(exc, aliases) in BROAD_EXCEPTIONS for exc in types)


def _escalates(handler: ast.ExceptHandler) -> bool:
    for node in _walk_same_scope(handler.body):
        if isinstance(node, ast.Raise):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "exception"
        ):
            return True
    return False


def _cites_issue(call: ast.Call | None) -> bool:
    if call is None:
        return False
    values = [*call.args, *(keyword.value for keyword in call.keywords)]
    literals = [v.value for v in values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
    return any(has_issue_url(text) for text in literals)


def _is_falsy_literal(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and not node.value


def _is_load(node: ast.expr) -> bool:
    return isinstance(node, ast.Name | ast.Attribute) and isinstance(node.ctx, ast.Load)


def _ast_violations(tree: ast.AST, *, in_src: bool) -> Iterator[tuple[int, str]]:
    aliases = _import_aliases(tree)
    calls = {id(node.func): node for node in ast.walk(tree) if isinstance(node, ast.Call)}
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if _is_broad(node, aliases) and not _escalates(node):
                yield node.lineno, "LC001"
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "shell" and not _is_falsy_literal(keyword.value):
                    yield node.lineno, "LC006"
        if not (isinstance(node, ast.expr) and _is_load(node)):
            continue
        name = _qualified_name(node, aliases)
        if name is None:
            continue
        if name in SKIP_TARGETS and not _cites_issue(calls.get(id(node))):
            yield node.lineno, "LC004"
        elif in_src and name in SRC_ONLY_TARGETS:
            yield node.lineno, SRC_ONLY_TARGETS[name]


def _comment_violations(source: str) -> Iterator[tuple[int, str]]:
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        for suppression in parse_suppressions(token.string):
            if not suppression.reason:
                yield token.start[0], "LC002" if suppression.kind == "type-ignore" else "LC003"


def check_source(source: str, path: str, *, in_src: bool) -> list[Violation]:
    """All violations in one module's source text, sorted by (line, rule)."""
    try:
        tree = ast.parse(source, filename=path)
        found = [*_ast_violations(tree, in_src=in_src), *_comment_violations(source)]
    except (SyntaxError, ValueError, tokenize.TokenError) as exc:
        line = getattr(exc, "lineno", None) or 1
        return [Violation(path, line, "LC000", f"{RULES['LC000']}: {exc}")]
    return [Violation(path, line, rule, RULES[rule]) for line, rule in sorted(set(found))]


def _excluded(part: str) -> bool:
    return part in EXCLUDED_DIRS or (part.startswith(".") and part not in {".", ".."})


def iter_python_files(paths: Sequence[Path]) -> Iterator[Path]:
    """Python files under the given files/directories, skipping venvs, caches and dot-dirs."""
    for path in paths:
        if path.is_file():
            if path.suffix == ".py":
                yield path
        elif path.is_dir() and not _excluded(path.name):
            for candidate in sorted(path.rglob("*.py")):
                if not any(_excluded(part) for part in candidate.relative_to(path).parts[:-1]):
                    yield candidate


def _check_file(file: Path, root: Path) -> list[Violation]:
    resolved = file.resolve()
    relative = resolved.relative_to(root) if resolved.is_relative_to(root) else None
    display = relative.as_posix() if relative is not None else file.as_posix()
    in_src = relative is not None and relative.parts[:1] == ("src",)
    try:
        source = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [Violation(display, 1, "LC000", f"{RULES['LC000']}: {exc}")]
    return check_source(source, display, in_src=in_src)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lantern custom lint")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repo root (decides src/)")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()
    paths: list[Path] = args.paths

    missing = [path for path in paths if not path.exists()]
    if missing:
        print(f"lint_custom: no such path: {', '.join(map(str, missing))}", file=sys.stderr)
        return 2

    files = list(iter_python_files(paths))
    violations = [violation for file in files for violation in _check_file(file, root)]
    for violation in violations:
        print(f"{violation.path}:{violation.line}: {violation.rule} {violation.message}")
    print(f"lint_custom: {len(files)} files, {len(violations)} violation(s)", file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
