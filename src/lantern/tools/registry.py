"""The tools available to one run, and the menu the model chooses from."""

import json
from collections.abc import Iterable

from pydantic import BaseModel

from lantern.tools.base import RunBudget, Tool


def args_schema(model: type[BaseModel]) -> str:
    """A compact JSON outline of a tool's arguments: optional names end in "?"."""
    schema = model.model_json_schema()
    required = set(schema.get("required", []))
    outline: dict[str, object] = {}
    for name, spec in schema.get("properties", {}).items():
        options = [option for option in spec.get("anyOf", [spec]) if option.get("type") != "null"]
        kinds = [option.get("enum") or option.get("type", "any") for option in options]
        outline[name if name in required else f"{name}?"] = kinds[0] if len(kinds) == 1 else kinds
    return json.dumps(outline, separators=(",", ":"), ensure_ascii=False)


class Registry:
    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            msg = f"A tool named {tool.name} is already registered; tool names must be unique."
            raise ValueError(msg)
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def menu(self, allowed: Iterable[str], budget: RunBudget) -> str:
        """One line per allowed tool: name, what it is for, its arguments and calls left."""
        lines = []
        for name in allowed:
            tool = self._tools.get(name)
            if tool is None:
                continue
            lines.append(
                f"- {tool.name}: {tool.description} Args: {args_schema(tool.args_model)}. "
                f"Calls left: {budget.left(tool.kind)}."
            )
        return "\n".join(lines)
