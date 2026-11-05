"""The only way to run a tool: every call is vetted, budgeted, paced, run and logged here.

Checks run in a fixed order, and nothing reaches the network until all of them pass:
the tool exists and is allowed, the arguments are valid, the call is not a repeat, a page
to read is a link the investigation already knows, and the budget has calls left.
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ValidationError

from lantern.sites import canonical
from lantern.tools.base import RunBudget, Tool, ToolCall, ToolContext, ToolError, ToolResult
from lantern.tools.registry import Registry

Status = Literal["ok", "refused", "duplicate", "failed"]
SHOWN: dict[Status, str] = {"refused": "not run", "duplicate": "already done", "failed": "failed"}
PROVENANCE = (
    "Lantern reads only links given in the question, returned by a search or linked from a "
    "saved page, and this link is none of these. Search for it first."
)


@dataclass(frozen=True)
class Outcome:
    call: ToolCall
    status: Status
    reason: str  # plain words, shown to the next researcher step
    result: ToolResult | None = None


def plain_errors(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or 'arguments'}: {item['msg']}"
        for item in error.errors(include_input=False, include_url=False)
    )


class ToolGateway:
    def __init__(  # noqa: PLR0913  # clock and sleep are injectable so tests need no real waits
        self,
        registry: Registry,
        budget: RunBudget,
        known_urls: set[str],
        on_step: Callable[[str], None],
        *,
        allowed: Iterable[str] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.registry = registry
        self.budget = budget
        self.known_urls = known_urls  # canonical links the investigation may read
        self.allowed = set(registry.names() if allowed is None else allowed)
        self._on_step = on_step
        self._clock = clock
        self._sleep = sleep
        self._done: dict[str, str] = {}  # canonical call → summary of its successful run
        self._next: dict[str, float] = {}  # rate key → earliest time of its next call
        self._pacing: dict[str, asyncio.Lock] = {}

    async def run(self, call: ToolCall, ctx: ToolContext) -> Outcome:
        outcome = await self._run(call, ctx)
        self._on_step(self._line(outcome))
        return outcome

    async def _run(self, call: ToolCall, ctx: ToolContext) -> Outcome:
        vetted = self._vet(call)
        if isinstance(vetted, Outcome):
            return vetted
        tool, args, key = vetted
        self.budget.spend(tool.kind)
        self._done[key] = "it is still running."
        await self._pace(tool)
        try:
            result = await tool.run(args, ctx)
        except ToolError as error:
            del self._done[key]  # a failed call may be tried again
            return Outcome(call, "failed", str(error))
        self._done[key] = result.summary
        self.known_urls.update(canonical(hit.url) for hit in result.hits)
        return Outcome(call, "ok", result.summary, result)

    def _vet(self, call: ToolCall) -> Outcome | tuple[Tool, BaseModel, str]:
        """The tool, its validated arguments and the call's key, or why it may not run."""
        tool = self.registry.get(call.tool)
        if tool is None or call.tool not in self.allowed:
            offered = ", ".join(sorted(self.allowed)) or "none"
            reason = f"There is no tool called {call.tool[:60]} in this run. Use one of: {offered}."
            return Outcome(call, "refused", reason)
        try:
            args = tool.args_model.model_validate(call.args)
        except ValidationError as error:
            return Outcome(call, "refused", f"The arguments are not valid: {plain_errors(error)}.")
        key = f"{tool.name} {json.dumps(args.model_dump(mode='json'), sort_keys=True)}"
        if key in self._done:
            return Outcome(call, "duplicate", f"The same call was made before: {self._done[key]}")
        if tool.kind == "read" and canonical(str(getattr(args, "url", ""))) not in self.known_urls:
            return Outcome(call, "refused", PROVENANCE)
        if self.budget.left(tool.kind) <= 0:
            reason = f"This run has no {tool.kind} calls left in its budget."
            return Outcome(call, "refused", reason)
        return tool, args, key

    async def _pace(self, tool: Tool) -> None:
        """Wait until `min_interval` has passed since the last call with the same rate key."""
        if tool.min_interval <= 0:
            return
        async with self._pacing.setdefault(tool.rate_key, asyncio.Lock()):
            wait = self._next.get(tool.rate_key, 0.0) - self._clock()
            if wait > 0:
                await self._sleep(wait)
            self._next[tool.rate_key] = self._clock() + tool.min_interval

    @staticmethod
    def _line(outcome: Outcome) -> str:
        """One plain line for the investigation log."""
        call = outcome.call
        if outcome.status == "ok":
            return outcome.reason or f"{call.tool}: done."
        target = next((value for value in call.args.values() if isinstance(value, str)), "")
        shown = f" “{target[:100]}”" if target else ""
        return f"{call.tool}{shown}: {SHOWN[outcome.status]}. {outcome.reason}"
