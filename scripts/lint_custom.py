"""Small static checks for the patterns forbidden by the engineering workflow."""

import argparse
import ast
import io
import re
import tokenize
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    message: str


def _name(node: ast.AST, aliases: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return f"{_name(node.value, aliases)}.{node.attr}"
    return ""


def _reports(node: ast.AST) -> bool:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
        return False
    if isinstance(node, ast.Raise):
        return True
    if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "exception":
        return True
    return any(_reports(child) for child in ast.iter_child_nodes(node))


def _call_rules(node: ast.Call, name: str, source: str, in_src: bool) -> list[tuple[str, str]]:
    rules = []
    skip = re.fullmatch(r"pytest\.(?:mark\.)?(?:skip|skipif|xfail|importorskip)", name)
    issue = re.search(
        r"https?://[^\s'\"]+/(?:issues|pull)/\S+", ast.get_source_segment(source, node) or ""
    )
    if skip and not issue:
        rules.append(("L003", "Link an issue explaining this skip or expected failure."))
    if in_src and name == "time.sleep":
        rules.append(("L004", "Use bounded async waits instead of time.sleep in src/."))
    for keyword in node.keywords:
        if keyword.arg == "shell" and not (
            isinstance(keyword.value, ast.Constant) and keyword.value.value is False
        ):
            rules.append(("L005", "Use argument lists; shell must be absent or literal False."))
    if in_src and name in {"print", "builtins.print"}:
        rules.append(("L006", "Use the output or logging boundary instead of print."))
    return rules


def lint_source(source: str, path: str) -> list[Violation]:
    tree = ast.parse(source, filename=path)
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            prefix = f"{node.module}." if isinstance(node, ast.ImportFrom) else ""
            for alias in node.names:
                aliases[alias.asname or alias.name] = prefix + alias.name
    violations = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        suppression = re.match(r"#\s*(?:type:\s*ignore|noqa)\b", token.string)
        reason = token.string[1:].partition("#")[2].strip()
        if token.type == tokenize.COMMENT and suppression and not reason:
            message = "Explain the suppression in a trailing comment."
            violations.append(Violation(path, token.start[0], "L002", message))
    broad = {"Exception", "BaseException", "builtins.Exception", "builtins.BaseException"}
    for node in ast.walk(tree):
        rules = []
        if isinstance(node, ast.ExceptHandler):
            catches_broad = node.type is None or any(
                _name(part, aliases) in broad for part in ast.walk(node.type)
            )
            if catches_broad and not any(_reports(statement) for statement in node.body):
                rules.append(
                    ("L001", "Re-raise broad exceptions or log them with .exception(...).")
                )
        elif isinstance(node, ast.Call):
            rules = _call_rules(node, _name(node.func, aliases), source, "src" in Path(path).parts)
        for rule, message in rules:
            violations.append(Violation(path, getattr(node, "lineno", 1), rule, message))
    return sorted(violations, key=lambda item: (item.line, item.rule))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=["src", "scripts", "tests"])
    arguments = parser.parse_args(argv)
    failed = False
    for argument in arguments.paths:
        path = Path(argument)
        paths = sorted(path.rglob("*.py")) if path.is_dir() else [path]
        for file in paths:
            try:
                violations = lint_source(file.read_text(), str(file))
            except (OSError, SyntaxError, tokenize.TokenError) as error:
                print(f"{file}: cannot check this Python file ({type(error).__name__}).")
                failed = True
                continue
            for violation in violations:
                print(f"{violation.path}:{violation.line}: {violation.rule} {violation.message}")
                failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
