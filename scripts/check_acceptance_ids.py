"""Trace backlog acceptance criteria to literal test decorators without imports."""

import argparse
import ast
import re
from collections.abc import Sequence
from pathlib import Path


def acceptance_ids(backlog_text: str, stories: Sequence[str]) -> list[str]:
    sections: dict[str, list[str]] = {}
    current = ""
    for line in backlog_text.splitlines():
        heading = re.match(r"^###\s+(S\d+(?:\.\d+)+)\b", line)
        if line.startswith("#"):
            current = heading[1] if heading else ""
            if current:
                sections.setdefault(current, [])
        criterion = re.match(r"^-\s+(S\d+(?:\.\d+)+-AC\d+)\b", line)
        if criterion and current and criterion[1].startswith(current + "-AC"):
            sections[current].append(criterion[1])
    missing = set(stories) - sections.keys()
    if missing:
        raise ValueError("Unknown story: " + ", ".join(sorted(missing)))
    return list(
        dict.fromkeys(ac for story, ids in sections.items() if story in stories for ac in ids)
    )


def test_marks(source: str, path: str) -> dict[str, list[str]]:
    marks: dict[str, list[str]] = {}

    def visit(node: ast.AST, parents: tuple[str, ...] = ()) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if ast.unparse(decorator) == "pytest.mark.ac":
                    raise ValueError(f"{path}: AC marker needs one literal string.")
                if (
                    isinstance(decorator, ast.Call)
                    and ast.unparse(decorator.func) == "pytest.mark.ac"
                ):
                    if (
                        len(decorator.args) != 1
                        or decorator.keywords
                        or not isinstance(decorator.args[0], ast.Constant)
                        or not isinstance(decorator.args[0].value, str)
                        or not node.name.startswith("test_")
                        or any(not parent.startswith("Test") for parent in parents)
                    ):
                        raise ValueError(f"{path}: AC marker needs one literal string on a test.")
                    name = "::".join((path, *parents, node.name))
                    marks.setdefault(decorator.args[0].value, []).append(name)
            return
        for child in ast.iter_child_nodes(node):
            visit(child, (*parents, node.name) if isinstance(node, ast.ClassDef) else parents)

    visit(ast.parse(source, filename=path))
    return marks


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stories", nargs="+")
    parser.add_argument("--backlog", type=Path, default=Path("docs/06_ROADMAP_BACKLOG.md"))
    arguments = parser.parse_args(argv)
    filename = str(arguments.backlog)
    try:
        backlog = arguments.backlog.read_text()
        selected = acceptance_ids(backlog, arguments.stories)
        all_stories = re.findall(r"^###\s+(S\d+(?:\.\d+)+)\b", backlog, re.M)
        known = set(acceptance_ids(backlog, all_stories))
        marks: dict[str, list[str]] = {}
        for path in sorted(Path("tests").rglob("*.py")):
            filename = str(path)
            for ac, names in test_marks(path.read_text(), str(path)).items():
                marks.setdefault(ac, []).extend(names)
    except (OSError, ValueError, SyntaxError) as error:
        print(f"{filename}: cannot trace requirements ({type(error).__name__}). Check IDs/markers.")
        return 1
    for ac in selected:
        print(f"{ac} -> {', '.join(marks.get(ac, [])) or 'MISSING TEST'}")
    unknown = sorted(marks.keys() - known)
    if unknown:
        print("Unknown acceptance IDs: " + ", ".join(unknown))
    return int(bool(unknown) or not selected or any(not marks.get(ac) for ac in selected))


if __name__ == "__main__":
    raise SystemExit(main())
