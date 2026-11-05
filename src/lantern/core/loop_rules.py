"""When the investigation loop stops, which key questions it works on next, and when one is
closed. Pure functions of the loop's state, so they can be tested exhaustively."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import ceil
from typing import Literal

from lantern.models import Question

SOFT_STOP = 0.85  # research stops here; the rest of each budget is kept for the report
ATTEMPTS = 3  # researcher steps on a fact question before it is closed
STALE = 2  # steps (per list question) or rounds (overall) without anything new
MAX_READS = 8  # pages read in one step
TERMINAL = {"answered", "unanswerable"}

StopReason = Literal[
    "budget_tokens", "budget_calls", "budget_pages", "wall_clock", "all_closed", "rounds", "stale"
]


@dataclass(frozen=True)
class Budget:
    """What one pass of research may use. A continuation gets its own, smaller budget."""

    name: str
    rounds: int
    pages: int
    tool_calls: int
    seconds: float
    tokens: int


QUICK = Budget("Quick look", rounds=1, pages=10, tool_calls=15, seconds=300, tokens=60_000)
DEEP = Budget("Deep investigation", rounds=6, pages=30, tool_calls=60, seconds=900, tokens=200_000)
CONTINUE = Budget("Continuation", rounds=2, pages=16, tool_calls=25, seconds=480, tokens=100_000)


@dataclass(frozen=True)
class LoopState:
    """What this pass has used so far, and where the key questions stand."""

    budget: Budget
    rounds: int  # rounds completed
    statuses: tuple[str, ...]
    stale_rounds: int  # consecutive rounds with no new claims or items
    pages: int
    tool_calls: int
    seconds: float
    tokens: int


def should_stop(state: LoopState) -> StopReason | None:
    """Why research must stop now, or None. Checked between steps; the first match wins
    (03 §2.1): any budget at 85 %, every question closed, the round limit, no progress."""
    budget = state.budget
    used: list[tuple[StopReason, float, float]] = [
        ("budget_tokens", state.tokens, budget.tokens),
        ("budget_calls", state.tool_calls, budget.tool_calls),
        ("budget_pages", state.pages, budget.pages),
        ("wall_clock", state.seconds, budget.seconds),
    ]
    for reason, spent, limit in used:
        if spent >= SOFT_STOP * limit:
            return reason
    if all(status in TERMINAL for status in state.statuses):
        return "all_closed"
    if state.rounds >= budget.rounds:
        return "rounds"
    if state.stale_rounds >= STALE:
        return "stale"
    return None


def explain(reason: StopReason, state: LoopState) -> str:
    """What stopped research, in plain words for the log and the report."""
    budget = state.budget
    share = f"{SOFT_STOP:.0%}"
    return {
        "budget_tokens": (
            f"Research stopped at {share} of its AI token budget ({state.tokens:,} of "
            f"{budget.tokens:,} tokens); the rest was kept for the assessment and the report."
        ),
        "budget_calls": f"Research used {share} of its {budget.tool_calls} tool calls.",
        "budget_pages": f"Research saved {state.pages} pages, {share} of its {budget.pages}.",
        "wall_clock": (
            f"Research stopped at {share} of its {budget.seconds / 60:g}-minute time limit."
        ),
        "all_closed": "Every key question was answered or closed.",
        "rounds": f"Research used all {budget.rounds} of its rounds.",
        "stale": f"{STALE} rounds in a row found nothing new.",
    }[reason]


def select_questions(
    questions: Sequence[Question], attempts: Mapping[str, int], k: int
) -> list[str]:
    """The open key questions to research next, at most `k`: fewest attempts first, then
    the planner's order, which is its priority (03 §2.2)."""
    order = {question.ref: index for index, question in enumerate(questions)}
    open_refs = [question.ref for question in questions if question.status not in TERMINAL]
    return sorted(open_refs, key=lambda ref: (attempts.get(ref, 0), order[ref]))[: max(0, k)]


def close_question(  # noqa: PLR0913  # each input is one fact the rule needs
    kind: str,
    *,
    attempts: int,
    answered: bool,
    confident: bool,
    done: bool,
    stale_steps: int,
) -> Literal["answered", "unanswerable"] | None:
    """Whether a key question is finished after a step: the researcher said so, a fact
    question is answered with high confidence or reached its attempts, or a list question
    found nothing new for two steps. List questions have no attempt cap."""
    finished = (
        done
        or (kind == "fact" and (confident or attempts >= ATTEMPTS))
        or (kind == "list" and stale_steps >= STALE)
    )
    if not finished:
        return None
    return "answered" if answered else "unanswerable"


def pages_per_step(budget: Budget, pages_left: int, questions: int) -> int:
    """Pages one step may read: an even share of the budget over the first three rounds,
    at least 3 and at most 8, never more than are left."""
    share = ceil(budget.pages / max(1, questions * min(budget.rounds, 3)))
    return max(0, min(MAX_READS, pages_left, max(3, share)))
