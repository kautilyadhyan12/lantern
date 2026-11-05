"""The investigator agent (03 §2). Each round, every open key question gets one researcher
step: the model reads the case file and proposes up to four tool calls with a reason, the
gateway vets and runs them, the most promising search results are read, claims are
anchored, and a fact question is re-assessed when its evidence changed. Code decides when
a question is closed and when research stops; then the existing assessment and report run.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from lantern import prompts
from lantern.agent import views
from lantern.agent.researcher import next_actions
from lantern.assessment import registrable_domain
from lantern.core.loop_rules import (
    DEEP,
    MAX_READS,
    Budget,
    LoopState,
    StopReason,
    close_question,
    explain,
    pages_per_step,
    select_questions,
    should_stop,
)
from lantern.llm import BudgetError, ModelError, QuotaError
from lantern.models import Claim, Finding, Investigation, Question, Source, now
from lantern.pipeline import TRIAGE_WINDOW, Candidate, Investigator, Limits, Tools
from lantern.search import Hit
from lantern.sites import canonical, readable
from lantern.store import Store
from lantern.text import find_quote
from lantern.tools.base import RunBudget, SourceDraft, ToolCall, ToolResult
from lantern.tools.gateway import Outcome, describe

SEARCHES = {"web_search", "news_search"}
LEADS_ONLY = {"post_links"}
SWEEP = 8  # calls the opening sweep may make (post links and social posts), on top of the budget


@dataclass
class Progress:
    """What the loop knows about one key question during this pass."""

    planned: list[str]
    attempts: int = 0
    tools: set[str] = field(default_factory=set)
    finding: Finding | None = None
    stale: int = 0  # steps in a row that added no claims
    done: bool = False  # the researcher said so
    feedback: list[str] = field(default_factory=list)  # refusals and failures of its last step


class Agent(Investigator):
    def __init__(  # noqa: PLR0913  # the budget and clock are injectable for tests
        self,
        investigation: Investigation,
        tools: Tools,
        store: Store,
        limits: Limits,
        on_change: Callable[[Investigation], None] | None = None,
        *,
        budget: Budget = DEEP,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.budget = budget  # set first: the gateway's budget is built from it
        super().__init__(investigation, tools, store, limits, on_change)
        self._clock = clock
        self._progress: dict[str, Progress] = {}
        self._searches: list[str] = []  # this pass: one line per search, with its count
        self._assessed: dict[str, Finding] = {}  # evidence → the finding assessed from it
        self._listed: dict[str, int] = {}  # list question → claims at its last item list
        self._calls = 0
        # Where this pass started: clock, saved pages, tokens used and searches made.
        self._t0, self._pages0, self._tokens0, self._searched0 = 0.0, 0, 0, 0
        # Links in mentions came from searches, so a continued run may read them too.
        self.gateway.known_urls |= {url for m in investigation.mentions for url in m.urls}

    def _budget(self) -> RunBudget:
        reads = 2 * self.budget.pages  # read attempts: many sites refuse or fail
        calls = self.budget.tool_calls
        searches = calls + SWEEP
        return RunBudget(calls + reads + SWEEP, searches=searches, pages=reads, records=calls)

    async def run(self) -> Investigation:
        async def work() -> None:
            if await self._allowed():
                await self._plan()
                await self._research(sweep=True)
                await self._conclude()

        self._begin()
        return await self._guarded(work)

    async def resume(self, rounds: int = 2, pages: int = 16) -> Investigation:
        """Continue a finished investigation with a fresh, smaller budget: every key question
        is reopened, nothing already searched or read is repeated."""
        self.budget = replace(self.budget, rounds=rounds, pages=pages)
        self.gateway.budget = self._budget()

        async def work() -> None:
            self.note(
                f"Continuing the investigation: up to {rounds} more rounds, {pages} more pages "
                f"and {self.budget.tool_calls} tool calls, building on everything found so far."
            )
            for question in self.inv.questions:
                question.status = "open"
            await self._research()
            await self._conclude()

        self.inv.error = None
        self._begin()
        return await self._guarded(work)

    def _begin(self) -> None:
        self._t0, self._pages0 = self._clock(), self._saved()
        self._tokens0 = self.inv.usage.tokens_in + self.inv.usage.tokens_out
        self._searched0 = len(self.inv.searched)

    # ---- the loop ---------------------------------------------------------------------

    async def _research(self, *, sweep: bool = False) -> None:
        rounds = stale = 0
        try:
            if sweep:
                await self._sweep()
            while (reason := should_stop(self._state(rounds, stale))) is None:
                before = self._mark()
                if (reason := await self._question_round(rounds, stale)) is not None:
                    break
                rounds += 1
                stale = 0 if self._mark() != before else stale + 1
        except BudgetError:
            reason = "budget_tokens"
        if self.tools.tokens is not None:
            self.tools.tokens.researching = False  # the reserve is for the assessment and report
        self.inv.stopped_by = explain(reason, self._state(rounds, stale))
        self.note(self.inv.stopped_by)

    async def _sweep(self) -> None:
        """The standing first moves, before the researcher's first step: links to posts on
        sites Lantern does not read, and public posts as ground reports, from the planned
        phrases and hashtags. They use searches, not AI tokens, apart from reading the posts."""
        await self._find_leads()
        posts = await self._social()
        if posts:
            await self._extract(posts)
            await self._relist()

    async def _question_round(self, rounds: int, stale: int) -> StopReason | None:
        """One researcher step for each open key question, fewest attempts first; stops
        early when a budget runs low or every question is closed."""
        self.inv.usage.rounds += 1
        for ref in select_questions(self.inv.questions, self._attempts(), len(self.inv.questions)):
            await self._step(ref)
            if (reason := should_stop(self._state(rounds, stale))) is not None:
                return reason
        return None

    def _state(self, rounds: int, stale: int) -> LoopState:
        usage = self.inv.usage
        return LoopState(
            budget=self.budget,
            rounds=rounds,
            statuses=tuple(question.status for question in self.inv.questions),
            stale_rounds=stale,
            pages=self._saved() - self._pages0,
            tool_calls=self._calls,
            seconds=self._clock() - self._t0,
            tokens=usage.tokens_in + usage.tokens_out - self._tokens0,
        )

    def _mark(self) -> tuple[int, int, tuple[str, ...]]:
        """Progress: claims, items and question statuses."""
        statuses = tuple(question.status for question in self.inv.questions)
        return len(self.inv.claims), len(self.inv.items), statuses

    def _saved(self) -> int:
        return sum(1 for source in self.inv.sources if source.kind == "page")

    def _attempts(self) -> dict[str, int]:
        return {ref: progress.attempts for ref, progress in self._progress.items()}

    def _claims(self, ref: str) -> list[Claim]:
        return [claim for claim in self.inv.claims if ref in claim.question_refs]

    # ---- one researcher step ----------------------------------------------------------

    async def _step(self, ref: str) -> None:
        question = next(q for q in self.inv.questions if q.ref == ref)
        progress = self._progress.setdefault(ref, Progress(planned=self._planned.get(ref, [])))
        before = len(self._claims(ref))
        label = f"{ref} · step {progress.attempts + 1}"
        step = await self._propose(question, progress, label)
        progress.attempts += 1
        self.inv.usage.research_steps += 1
        if step is not None and step.done:
            progress.done = True
            self.note(f"{label}: done. {step.done_reason or step.note}")
        elif step is not None:
            if step.note:
                self.note(f"{label}: {step.note}")
            for call in step.calls:
                target = next((v for v in call.args.values() if isinstance(v, str)), "")
                shown = f" “{target[:100]}”" if target else ""
                self.note(f"{label} · {call.tool}{shown}: {call.why or 'no reason given'}")
            await self._act(question, step, progress)
        await self._settle(question, progress, before)

    async def _propose(
        self, question: Question, progress: Progress, label: str
    ) -> prompts.ResearchStep | None:
        allowed = [name for name in self.gateway.registry.names() if name in self.gateway.allowed]
        earlier = [f"“{text}”" for text in self.inv.searched[: self._searched0]]
        user = "\n\n".join(
            [
                views.brief_view(self.inv, self._phrases, self._hashtags),
                views.question_view(
                    question,
                    progress.attempts,
                    progress.tools,
                    progress.finding,
                    progress.planned,
                    single=[
                        item.name
                        for item in self.inv.items
                        if item.question_ref == question.ref
                        and item.status == "single source"
                        and item.in_period
                    ],
                ),
                views.evidence_digest(
                    self.inv,
                    question.ref,
                    searched=[*earlier, *self._searches],
                    unconfirmed=self._unconfirmed(),
                    unread=self._unread,
                    feedback=progress.feedback,
                ),
                "Tool menu:\n" + self.gateway.registry.menu(allowed, self.gateway.budget),
            ]
        )
        try:
            step, wrong = await next_actions(
                self._model("think"),
                self._dated(prompts.RESEARCH),
                user,
                self.gateway.registry,
                allowed,
            )
        except QuotaError:
            raise
        except ModelError as error:
            self.note(f"{label}: the researcher step failed ({error}); moving on.")
            return None
        if step is None:
            self.note(f"{label}: skipped, because its calls were invalid twice: {wrong}")
        return step

    async def _act(
        self, question: Question, step: prompts.ResearchStep, progress: Progress
    ) -> None:
        """Run the proposed calls, read the most promising results, and anchor claims."""
        progress.feedback = []
        candidates: dict[str, Candidate] = {}
        found: list[Source] = []
        for proposed in step.calls:
            call = ToolCall(
                tool=proposed.tool,
                args=proposed.args,
                question_ref=question.ref,
                why=proposed.why or step.note,
            )
            if reason := self._repeat(call):
                progress.feedback.append(describe(Outcome(call, "duplicate", reason)))
                continue
            outcome = await self._run_call(call)
            if outcome.status in {"ok", "failed"}:
                self._calls += 1
            if outcome.result is None:
                progress.feedback.append(describe(outcome))
                self._failed_read(outcome, question.ref)
                continue
            progress.tools.add(call.tool)
            found += self._take(outcome, question.ref, candidates)
        found += await self._read(question, list(candidates.items()))
        if found:
            await self._extract(found)
        await self._relist()

    async def _relist(self) -> None:
        """Rebuild the item list of each list question that gained claims since its last list."""
        lists = {q.ref for q in self.inv.questions if q.kind == "list"}
        grown = {ref for ref in lists if len(self._claims(ref)) > self._listed.get(ref, 0)}
        if grown:
            await self._inventory(grown)
            self._listed.update({ref: len(self._claims(ref)) for ref in grown})

    def _repeat(self, call: ToolCall) -> str:
        """Why a call repeats work from an earlier pass of this investigation, or ""."""
        if call.tool in SEARCHES:
            query = str(call.args.get("query", "")).strip().casefold()
            return "This search was made earlier in the investigation." * (
                query in self._searched_keys
            )
        if call.tool == "read_page":
            url = canonical(str(call.args.get("url", "")))
            return "This page was read or tried earlier in the investigation." * (
                url in self._attempted
            )
        return ""

    def _failed_read(self, outcome: Outcome, ref: str) -> None:
        """A page the researcher asked for that could not be read becomes a lead."""
        if outcome.call.tool != "read_page" or outcome.status != "failed":
            return
        url = canonical(str(outcome.call.args.get("url", "")))
        self._attempted.add(url)
        self.inv.usage.pages_skipped += 1
        self._page_lead(url, {ref}, outcome.reason)

    def _take(self, outcome: Outcome, ref: str, candidates: dict[str, Candidate]) -> list[Source]:
        """Keep what one successful call returned: hits become candidates or leads, posts
        and pages are saved."""
        call, result = outcome.call, outcome.result or ToolResult()
        if call.tool in SEARCHES:
            query = str(call.args.get("query", "")).strip()
            self._searched.append(query)
            self._searched_keys.add(query.casefold())
        if call.tool in SEARCHES | LEADS_ONLY:
            self.inv.usage.searches += 1
        if call.tool != "read_page":
            self._searches.append(result.summary)
        for hit in result.hits:
            url = canonical(hit.url)
            if call.tool in LEADS_ONLY or not readable(url):
                self._post_lead(url, ref)
            elif url in candidates:
                candidates[url].refs.add(ref)
            elif url not in self._attempted:
                candidates[url] = Candidate(hit=hit, refs={ref})
        posts = [draft for draft in result.sources if draft.kind == "post"]
        saved = self._keep_posts(posts, [ref]) if posts else []
        if posts:
            self.note(f"Saved {len(saved)} new posts as ground reports.")
        saved += [
            self._save_record(draft, ref) for draft in result.sources if draft.kind == "record"
        ]
        for draft in result.sources:
            if draft.kind != "page":
                continue
            self._attempted.add(canonical(draft.url))
            source = self._page_source(
                draft, Candidate(Hit(url=draft.url, title="", rank=0), {ref})
            )
            source.ref = f"S{len(self.inv.sources) + 1}"
            self.inv.sources.append(source)
            self.inv.usage.pages_fetched += 1
            saved.append(source)
        return saved

    def _save_record(self, draft: SourceDraft, ref: str) -> Source:
        """Save a record source and its statements as claims. They are generated by code from
        official data, so no model reads them; each is anchored in the saved text."""
        grade, why = draft.grade or ("C", "Reference record")
        source = Source(
            ref=f"S{len(self.inv.sources) + 1}",
            url=draft.url,
            domain=registrable_domain(draft.url),
            kind="record",
            origin=draft.origin,
            title=draft.title,
            published=draft.published,
            fetched_at=now(),
            sha256=self.store.put_blob(draft.body),
            text_sha256=self.store.put_text(draft.text),
            size=len(draft.body),
            reliability=grade,
            reliability_reason=why,
            question_refs=[ref],
        )
        self.inv.sources.append(source)
        for statement in draft.record_claims:
            span = find_quote(draft.text, statement)
            if span is None:
                continue
            self.inv.claims.append(
                Claim(
                    ref=f"C{len(self.inv.claims) + 1}",
                    source_ref=source.ref,
                    question_refs=[ref],
                    statement=statement,
                    quote=draft.text[span[0] : span[1]],
                    start=span[0],
                    end=span[1],
                )
            )
        return source

    async def _read(
        self, question: Question, candidates: list[tuple[str, Candidate]]
    ) -> list[Source]:
        """Triage this step's search results in one call, then read the picks."""
        left = self.budget.pages - (self._saved() - self._pages0)
        budget = pages_per_step(self.budget, left, len(self.inv.questions))
        eligible = self._eligible(candidates)[:TRIAGE_WINDOW]
        if budget <= 0 or not eligible:
            return []
        user = (
            f"Key questions:\n{self._menu()}\n\nFound so far:\n{self._found_so_far()}\n\n"
            f"Search results:\n{views.hits_view([cand.hit for _, cand in eligible])}"
        )
        system = prompts.STEP_TRIAGE.format(ref=question.ref, count=budget)
        index = {f"H{number}": pair for number, pair in enumerate(eligible, start=1)}
        try:
            out = await self._ask(system, user, prompts.TriageStep, role="fast")
        except QuotaError:
            raise
        except ModelError as error:
            self.note(f"Could not rank the search results ({error}); using search order.")
            return await self._fetch(self._capped(eligible, budget))
        self._spot(out.spotted, {ref: url for ref, (url, _) in index.items()})
        refs = dict.fromkeys(ref.strip().upper() for ref in out.read)
        picks = [index[ref] for ref in refs if ref in index][:MAX_READS] or eligible
        chosen = self._capped(picks, budget)
        self.note(f"Chose {len(chosen)} of {len(eligible)} results to read for {question.ref}.")
        return await self._fetch(chosen)

    async def _settle(self, question: Question, progress: Progress, before: int) -> None:
        """Re-assess a fact question whose evidence changed, then decide if it is closed."""
        claims = self._claims(question.ref)
        progress.stale = 0 if len(claims) > before else progress.stale + 1
        if question.kind == "fact" and len(claims) > before:
            fresh = await self._assess_one(question, claims[: self.limits.claims_per_question])
            progress.finding = fresh
            level = f", {fresh.confidence} confidence" if fresh.confidence else ""
            self.note(f"{question.ref} assessed from {len(claims)} claims: {fresh.status}{level}.")
        finding = progress.finding
        if question.kind == "list":
            answered = bool(claims)
        else:
            answered = finding is not None and finding.status == "answered"
        status = close_question(
            question.kind,
            attempts=progress.attempts,
            answered=answered,
            confident=finding is not None and finding.confidence == "high",
            done=progress.done,
            stale_steps=progress.stale,
        )
        if status is not None:
            question.status = status
            self.note(f"{question.ref}: research closed ({status}).")

    async def _assess_one(self, question: Question, claims: list[Claim]) -> Finding:
        """An answer assessed from exactly the same evidence is reused, not asked again."""
        key = " ".join([question.ref, *(c.ref for c in claims), self._items_text(question.ref)])
        if (cached := self._assessed.get(key)) is not None:
            self._rate(cached, claims)
            return cached.model_copy(deep=True)
        finding = await super()._assess_one(question, claims)
        if finding.status == "answered":
            self._assessed[key] = finding.model_copy(deep=True)
        return finding
