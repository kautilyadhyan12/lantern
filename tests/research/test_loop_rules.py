"""The loop's pure rules: when research stops, which questions go next, when one closes."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lantern.core.loop_rules import (
    CONTINUE,
    DEEP,
    QUICK,
    SOFT_STOP,
    STALE,
    TERMINAL,
    Budget,
    LoopState,
    close_question,
    explain,
    pages_per_step,
    select_questions,
    should_stop,
)
from lantern.models import Question

STATUSES = st.sampled_from(["open", "answered", "unanswerable"])
BUDGET = Budget("Test", rounds=6, pages=30, tool_calls=60, seconds=900, tokens=200_000)


def state(**changes):
    values = {
        "budget": BUDGET,
        "rounds": 0,
        "statuses": ("open", "open"),
        "stale_rounds": 0,
        "pages": 0,
        "tool_calls": 0,
        "seconds": 0.0,
        "tokens": 0,
    }
    return LoopState(**{**values, **changes})


states = st.builds(
    LoopState,
    budget=st.just(BUDGET),
    rounds=st.integers(0, 10),
    statuses=st.lists(STATUSES, min_size=1, max_size=4).map(tuple),
    stale_rounds=st.integers(0, 4),
    pages=st.integers(0, 40),
    tool_calls=st.integers(0, 80),
    seconds=st.floats(0, 2000),
    tokens=st.integers(0, 300_000),
)


@pytest.mark.ac("AG1b-AC2")
@given(states)
def test_should_stop_follows_the_stop_table_in_order(s):
    reason = should_stop(s)
    budgets = [
        ("budget_tokens", s.tokens, BUDGET.tokens),
        ("budget_calls", s.tool_calls, BUDGET.tool_calls),
        ("budget_pages", s.pages, BUDGET.pages),
        ("wall_clock", s.seconds, BUDGET.seconds),
    ]
    for name, used, limit in budgets:
        if used >= SOFT_STOP * limit:
            assert reason == name
            return
    if all(status in TERMINAL for status in s.statuses):
        assert reason == "all_closed"
    elif s.rounds >= BUDGET.rounds:
        assert reason == "rounds"
    elif s.stale_rounds >= STALE:
        assert reason == "stale"
    else:
        assert reason is None
    if reason is not None:
        assert explain(reason, s)


@pytest.mark.ac("AG1b-AC2")
@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"tokens": 170_000}, "budget_tokens"),
        ({"tokens": 169_999}, None),
        ({"tool_calls": 51}, "budget_calls"),
        ({"pages": 26}, "budget_pages"),
        ({"seconds": 765.0}, "wall_clock"),
        ({"statuses": ("answered", "unanswerable")}, "all_closed"),
        ({"rounds": 6}, "rounds"),
        ({"stale_rounds": 2}, "stale"),
        ({"stale_rounds": 1, "rounds": 5}, None),
        ({"tokens": 190_000, "statuses": ("answered",)}, "budget_tokens"),  # first match wins
    ],
)
def test_each_stop_condition_at_its_threshold(changes, reason):
    assert should_stop(state(**changes)) == reason


def test_stop_reasons_are_plain_words():
    assert "85% of its AI token budget (170,000 of 200,000 tokens)" in explain(
        "budget_tokens", state(tokens=170_000)
    )
    assert "15-minute time limit" in explain("wall_clock", state())
    assert explain("rounds", state()) == "Research used all 6 of its rounds."


questions = st.lists(
    st.tuples(st.sampled_from(["fact", "list"]), STATUSES), min_size=1, max_size=6
).map(
    lambda rows: [
        Question(ref=f"Q{n}", text="What happened here?", kind=kind, status=status)
        for n, (kind, status) in enumerate(rows, start=1)
    ]
)


@pytest.mark.ac("AG1b-AC2")
@given(
    questions,
    st.dictionaries(st.sampled_from(["Q1", "Q2", "Q3"]), st.integers(0, 5)),
    st.integers(0, 6),
)
def test_select_questions_picks_open_ones_with_fewest_attempts_first(items, attempts, k):
    chosen = select_questions(items, attempts, k)
    open_refs = [q.ref for q in items if q.status == "open"]
    assert len(chosen) == min(k, len(open_refs))
    assert len(set(chosen)) == len(chosen)
    assert set(chosen) <= set(open_refs)
    keys = [(attempts.get(ref, 0), open_refs.index(ref)) for ref in chosen]
    assert keys == sorted(keys)
    left_out = set(open_refs) - set(chosen)
    if chosen and left_out:
        assert max(keys) <= min((attempts.get(r, 0), open_refs.index(r)) for r in left_out)


def test_select_questions_goes_in_plan_order_when_attempts_are_equal():
    items = [Question(ref=f"Q{n}", text="What happened here?") for n in (1, 2, 3)]
    assert select_questions(items, {}, 2) == ["Q1", "Q2"]
    assert select_questions(items, {"Q1": 1}, 3) == ["Q2", "Q3", "Q1"]


@pytest.mark.parametrize(
    ("kind", "facts", "status"),
    [
        ("fact", {"confident": True, "answered": True}, "answered"),
        ("fact", {"attempts": 3}, "unanswerable"),
        ("fact", {"attempts": 3, "answered": True}, "answered"),
        ("fact", {"attempts": 2, "answered": True}, None),
        ("fact", {"done": True}, "unanswerable"),
        ("list", {"attempts": 5, "answered": True}, None),  # lists have no attempt cap
        ("list", {"stale_steps": 2, "answered": True}, "answered"),
        ("list", {"done": True, "answered": True}, "answered"),
    ],
)
def test_when_a_question_is_closed(kind, facts, status):
    values = {"attempts": 1, "answered": False, "confident": False, "done": False}
    assert close_question(kind, **{"stale_steps": 0, **values, **facts}) == status


def test_pages_are_shared_across_steps():
    assert pages_per_step(QUICK, 10, 2) == 5
    assert pages_per_step(QUICK, 10, 4) == 3
    assert pages_per_step(DEEP, 30, 2) == 5
    assert pages_per_step(DEEP, 30, 1) == 8  # never more than 8 in one step
    assert pages_per_step(DEEP, 2, 4) == 2  # never more than are left
    assert pages_per_step(CONTINUE, 0, 2) == 0


def test_depth_budgets_match_the_plan():
    assert (QUICK.rounds, QUICK.pages, QUICK.tool_calls, QUICK.seconds, QUICK.tokens) == (
        1,
        10,
        15,
        300,
        60_000,
    )
    assert (DEEP.rounds, DEEP.pages, DEEP.tool_calls, DEEP.seconds, DEEP.tokens) == (
        6,
        30,
        60,
        900,
        200_000,
    )
    assert (CONTINUE.rounds, CONTINUE.pages, CONTINUE.tool_calls, CONTINUE.tokens) == (
        2,
        16,
        25,
        100_000,
    )
