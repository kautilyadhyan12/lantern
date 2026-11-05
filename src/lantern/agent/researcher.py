"""The researcher step: the model proposes up to four tool calls for one key question, or
says it is done. Code checks every proposed call against the tool registry before anything
runs; the gateway checks it again when it runs."""

from collections.abc import Collection

from pydantic import ValidationError

from lantern.llm import Model
from lantern.prompts import ResearchStep
from lantern.tools.gateway import plain_errors
from lantern.tools.registry import Registry


def problems(step: ResearchStep, registry: Registry, allowed: Collection[str]) -> str:
    """What is wrong with a proposed step, in plain words, or "" when it can run."""
    if step.done:
        return ""
    if not step.calls:
        return "It proposes no calls and does not say the question is done."
    found = []
    for number, call in enumerate(step.calls, start=1):
        tool = registry.get(call.tool)
        if tool is None or call.tool not in allowed:
            found.append(f"call {number}: there is no tool called {call.tool[:60]}")
            continue
        try:
            tool.args_model.model_validate(call.args)
        except ValidationError as error:
            found.append(f"call {number} ({call.tool}): {plain_errors(error)}")
    return "; ".join(found) + "." if found else ""


async def next_actions(
    model: Model, system: str, user: str, registry: Registry, allowed: Collection[str]
) -> tuple[ResearchStep | None, str]:
    """The researcher's next step, or None with the reason when its calls were invalid twice.
    An invalid step gets one retry that is told exactly what was wrong."""
    step = await model.structured(system, user, ResearchStep)
    wrong = problems(step, registry, allowed)
    if not wrong:
        return step, ""
    retry = (
        f"{user}\n\nYour previous answer could not be used: {wrong} Answer again with calls "
        "from the tool menu and their arguments exactly as listed, or set done."
    )
    step = await model.structured(system, retry, ResearchStep)
    wrong = problems(step, registry, allowed)
    return (None, wrong) if wrong else (step, "")
