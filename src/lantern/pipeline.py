"""The investigation: safety check, key questions, research rounds, findings, report.

Each research round searches the web and the news, chooses the most promising results,
reads and preserves pages, and pulls out quote-anchored claims. Later rounds follow up on
what earlier rounds found: single-source items, missing items, other names, other
languages and primary sources. The model proposes searches, picks pages and drafts
claims; code checks every quote, counts independent origins and sets confidence.
"""

import asyncio
import logging
import re
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel

from lantern import assessment, prompts
from lantern.archive import Archive
from lantern.core import graph, verdict
from lantern.llm import BudgetError, Model, ModelError, QuotaError, TokenBudget
from lantern.models import (
    Claim,
    Finding,
    Investigation,
    Item,
    Lead,
    Mention,
    Question,
    Removed,
    Report,
    Sentence,
    Source,
    Triple,
    Verdict,
    now,
)
from lantern.report import check_sentence, likelihood_terms, strip_refs, verify
from lantern.safety import check_brief
from lantern.search import Hit, Searcher, SearchError, TimeRange
from lantern.sites import canonical, post_lead, readable
from lantern.social import SocialSearch
from lantern.store import Store
from lantern.text import find_quote, name_words, normalise, relevant_chunks, topic_words
from lantern.tools.adapters.claims import ARCHIVE_ORIGIN, EarliestCopy, FactChecks
from lantern.tools.adapters.social import SocialArgs, SocialPosts
from lantern.tools.adapters.web import NewsSearch, PageFetcher, PostLinks, ReadPage, WebSearch
from lantern.tools.base import RunBudget, SourceDraft, Tool, ToolCall, ToolContext
from lantern.tools.gateway import Outcome, ToolGateway
from lantern.tools.registry import Registry

log = logging.getLogger(__name__)

PER_DOMAIN = 3  # pages per site in one investigation, so corroboration stays independent
MAX_POST_LEADS = 12
MAX_PAGE_LEADS = 15
TRIAGE_WINDOW = 40
DISCOVER_WINDOW = 60
MAX_MENTIONS = 40
CLAIMS_PER_PAGE = 12
ROUND_SEARCHES = 100  # a backstop for the gateway: the rounds' own limits always bind first
TIME_RANGES: dict[str, TimeRange] = {"day": "day", "week": "week", "month": "month", "year": "year"}
Role = Literal["think", "read", "fast"]


@dataclass
class Limits:
    max_questions: int = 4
    rounds: int = 1
    max_pages: int = 10
    first_round_pages: int = 10
    round_pages: int = 8
    queries_per_question: int = 2
    followup_queries: int = 6
    results_per_query: int = 6
    claims_per_question: int = 60
    max_posts: int = 8
    posts_per_query: int = 20
    posts_per_account: int = 2
    chunks_per_page: int = 1

    @classmethod
    def for_depth(cls, depth: str, *, max_questions: int = 4, max_posts: int = 8) -> "Limits":
        """`quick` is one round of about 10 pages; `deep` is up to 3 rounds and 30 pages."""
        if depth == "quick":
            return cls(max_questions=max_questions, max_posts=max_posts)
        return cls(
            max_questions=max_questions,
            max_posts=max_posts,
            rounds=3,
            max_pages=30,
            first_round_pages=14,
            round_pages=8,
            queries_per_question=3,
            results_per_query=8,
            chunks_per_page=2,
        )


@dataclass
class Tools:
    model: Model
    searcher: Searcher
    fetcher: PageFetcher
    social: SocialSearch | None = None
    reader: Model | None = None  # bulk page reading; defaults to `model`
    archive: Archive | None = None  # archived copies of pages a site refused
    fast: Model | None = None  # triage and item lists, on a separate free quota
    records: tuple[Tool, ...] = ()  # official records and reference tools (the agent's)
    tokens: TokenBudget | None = None  # the model gateways' shared token budget


@dataclass(frozen=True)
class Query:
    text: str
    refs: tuple[str, ...]
    news: bool = False


@dataclass
class Candidate:
    """A search hit that might be worth reading. Lives only for one round, in memory."""

    hit: Hit
    refs: set[str]


def same_item(first: str, second: str) -> bool:
    """Whether two names probably mean the same item: one contains the other's words, or
    they share two or more words (spellings and middle names vary)."""

    def words(name: str) -> set[str]:
        return {word for word in normalise(name)[0].replace("-", " ").split() if len(word) > 2}

    a, b = words(first), words(second)
    return bool(a and b) and (a <= b or b <= a or len(a & b) >= 2)


class Investigator:
    def __init__(
        self,
        investigation: Investigation,
        tools: Tools,
        store: Store,
        limits: Limits,
        on_change: Callable[[Investigation], None] | None = None,
    ) -> None:
        self.inv = investigation
        self.tools = tools
        self.reader = tools.reader or tools.model
        self.store = store
        self.limits = limits
        self.on_change = on_change
        self._planned: dict[str, list[str]] = {}
        # Restored from the investigation, so a continued run picks up where it stopped.
        self._news = investigation.news
        self._time_range: TimeRange | None = TIME_RANGES.get(investigation.time_range or "")
        self._hashtags: list[str] = []
        self._phrases: list[str] = []
        self._searched = investigation.searched
        self._searched_keys = {text.casefold() for text in self._searched}
        self._attempted = {canonical(s.url) for s in investigation.sources if s.kind == "page"}
        self._attempted |= {lead.url for lead in investigation.leads if lead.kind == "page"}
        # Every search, page, post and lead is reached through the tool gateway.
        self._ctx = ToolContext()
        self.gateway = ToolGateway(
            self._registry(),
            self._budget(),
            self._given(),
            self.note,
            checks={
                "social_search": self._on_topic,
                **{tool.name: self._in_evidence for tool in tools.records},
            },
        )
        # Headlines of results that could not be read, kept in memory only for follow-ups.
        self._unread: list[str] = []
        self._post_texts: set[str] = set()  # normalised post texts saved in this run
        self._reading = asyncio.Semaphore(3)
        self._today = now().date().isoformat()

    def _registry(self) -> Registry:
        tools, limit = self.tools, self.limits.results_per_query
        registry = Registry(
            [
                WebSearch(tools.searcher, limit),
                NewsSearch(tools.searcher, limit),
                PostLinks(tools.searcher),
                ReadPage(tools.fetcher, tools.archive),
            ]
        )
        if tools.social is not None:
            registry.register(SocialPosts(tools.social, self.limits.posts_per_query))
        for tool in tools.records:
            registry.register(tool)
        if self.inv.mode == "claim":
            registry.register(FactChecks(tools.searcher, limit))
            if tools.archive is not None:
                registry.register(EarliestCopy(tools.archive))
        return registry

    def _budget(self) -> RunBudget:
        pages = 2 * self.limits.max_pages  # the rounds stop after this many attempts anyway
        return RunBudget(ROUND_SEARCHES + pages, ROUND_SEARCHES, pages, records=0)

    def _on_topic(self, args: SocialArgs) -> str | None:
        """Social media is searched only for the subject of the research question (words of
        the question or of the plan made from it), never for a person or account met along
        the way."""
        planned = [query for queries in self._planned.values() for query in queries]
        words = topic_words(self.inv.brief, *self._phrases, *self._hashtags, *planned)
        text = (args.phrase or args.hashtag or "").casefold()
        if any(word in text for word in words):
            return None
        example = f" such as “{self._phrases[0]}”" if self._phrases else ""
        return (
            "Lantern searches social media only for the subject of the research question. Use "
            f"a phrase with its place or subject name{example}."
        )

    def _in_evidence(self, args: BaseModel) -> str | None:
        """Records are looked up only for a name written in the research question or in the
        evidence found so far, never for a name the model brings itself."""
        fields = args.model_dump()
        asked = next((fields[k] for k in ("name", "query", "domain", "place") if fields.get(k)), "")
        wanted = " ".join(name_words(str(asked)))
        texts = [self.inv.brief, *(q.text for q in self.inv.questions)]
        texts += [text for c in self.inv.claims for text in (c.statement, c.quote)]
        texts += [i.name for i in self.inv.items] + [m.name for m in self.inv.mentions]
        texts += [text for s in self.inv.sources for text in (s.title or "", s.url)]
        if wanted and any(f" {wanted} " in f" {' '.join(name_words(t))} " for t in texts):
            return None
        return (
            "Lantern looks up records only for names that appear in the research question or "
            "in the evidence found so far. Use the name exactly as the case file writes it."
        )

    def _given(self) -> set[str]:
        """Links written in the question itself, which Lantern may read."""
        links = re.findall(r"https?://[^\s<>\"']+", self.inv.brief)
        return {canonical(link.rstrip(".,;:!?)]}")) for link in links}

    async def _call(
        self, tool: str, args: dict[str, object], refs: Iterable[str], why: str
    ) -> Outcome:
        call = ToolCall(tool=tool, args=args, question_ref=min(refs, default=""), why=why)
        return await self._run_call(call)

    async def _run_call(self, call: ToolCall) -> Outcome:
        outcome = await self.gateway.run(call, self._ctx)
        if outcome.status in {"ok", "failed"}:
            counts = self.inv.usage.tools
            counts[call.tool] = counts.get(call.tool, 0) + 1
        return outcome

    def _dated(self, system: str) -> str:
        """Every model call is told today's date, so "the past year" and dates in searches
        mean what the user means, not the model's training year."""
        return (
            f"{system}\nToday's date is {self._today}. Interpret all periods and dates "
            "relative to it, and never assume an earlier year."
        )

    def _model(self, role: Role) -> Model:
        if role == "read":
            return self.reader
        return (self.tools.fast if role == "fast" else None) or self.tools.model

    async def _ask[T: BaseModel](
        self, system: str, user: str, output: type[T], *, role: Role = "think"
    ) -> T:
        """One model call, routed by role: thinking, bulk reading, or fast triage."""
        return await self._model(role).structured(self._dated(system), user, output)

    def note(self, message: str) -> None:
        self.inv.log(message)
        self.store.save(self.inv)
        if self.on_change:
            self.on_change(self.inv)

    async def run(self) -> Investigation:
        async def work() -> None:
            if await self._allowed():
                await self._plan()
                await self._find_leads()
                for number in range(1, self.limits.rounds + 1):
                    queries = self._opening() if number == 1 else await self._follow_up(number)
                    if not queries:
                        break
                    await self._round(number, queries)
                    if self._pages_left() <= 0:
                        break
                await self._conclude()

        return await self._guarded(work)

    async def resume(self, rounds: int = 2, pages: int = 16) -> Investigation:
        """Continue a finished investigation: more follow-up rounds on everything found so
        far, without repeating searches or pages, then a fresh assessment and report."""
        saved = sum(1 for source in self.inv.sources if source.kind == "page")
        self.limits.max_pages = saved + pages
        self.gateway.budget = self._budget()
        start = self.inv.usage.rounds + 1

        async def work() -> None:
            self.note(
                f"Continuing the investigation: up to {rounds} more rounds and {pages} more "
                "pages, building on everything found so far."
            )
            for number in range(start, start + rounds):
                queries = await self._follow_up(number)
                if not queries:
                    break
                await self._round(number, queries)
                if self._pages_left() <= 0:
                    break
            await self._conclude()

        self.inv.error = None
        return await self._guarded(work)

    async def _conclude(self) -> None:
        """Assess every key question afresh from all claims, and write the report."""
        self._settle_mentions()
        self.inv.findings = []
        for claim in self.inv.claims:
            claim.credibility = 6
        for question in self.inv.questions:
            question.status = "open"
        await self._assess()
        self._map()
        await self._write()
        if self.inv.mode == "claim":
            await self._verdict()
        self.inv.status = "done"
        self.note("Finished.")

    def _map(self) -> None:
        """Entities and links, rebuilt by code from every relation and assessed connection."""
        assessed = [triple for finding in self.inv.findings for triple in finding.links]
        source_of = {claim.ref: claim.source_ref for claim in self.inv.claims}
        origin_of = {
            claim.ref: source.origin or source.domain
            for claim in self.inv.claims
            if (source := self.inv.source(claim.source_ref))
        }
        built = graph.build([*self.inv.relations, *assessed], source_of, origin_of)
        self.inv.entities, self.inv.links = built
        if self.inv.entities:
            self.note(f"Mapped {len(built[0])} entities and {len(built[1])} links between them.")

    async def _guarded(self, work: Callable[[], Awaitable[None]]) -> Investigation:
        self.inv.status = "running"
        try:
            await work()
        except (ModelError, SearchError) as error:
            self.inv.status, self.inv.error = "failed", str(error)
            self.note(f"Stopped: {error}")
        except Exception:
            log.exception("investigation %s crashed", self.inv.id)
            self.inv.status = "failed"
            self.inv.error = "An unexpected error stopped the investigation. Try again."
            self.note("Stopped by an unexpected error.")
        self.inv.finished_at = now()
        self.store.save(self.inv)
        return self.inv

    # ---- safety and planning -------------------------------------------------------

    async def _allowed(self) -> bool:
        self.note("Checking the question against the safety rules.")
        reason = check_brief(self.inv.brief)
        if reason is None:
            gate = await self._ask(
                prompts.GATE, f"Research question: {self.inv.brief}", prompts.GateOut
            )
            if not gate.allowed:
                reason = gate.reason or "This question is outside what Lantern may research."
        if reason:
            self.inv.status, self.inv.safety = "refused", reason
            self.note(f"Refused: {reason}")
            return False
        self.inv.safety = "Allowed: passed the fixed safety rules and the AI safety check."
        return True

    async def _plan(self) -> None:
        if self.inv.mode == "claim":
            await self._plan_claim()
            return
        self.note("Planning key questions and searches.")
        system = prompts.PLAN.format(
            count=f"2 to {self.limits.max_questions}", queries=self.limits.queries_per_question
        )
        plan = await self._ask(system, f"Research question: {self.inv.brief}", prompts.PlanOut)
        for number, item in enumerate(plan.questions[: self.limits.max_questions], start=1):
            question = Question(ref=f"Q{number}", text=item.text.strip(), kind=item.kind)
            self.inv.questions.append(question)
            queries = [query.strip() for query in item.queries if query.strip()]
            self._planned[question.ref] = queries[: self.limits.queries_per_question]
        self._news = self.inv.news = plan.news
        self._time_range = TIME_RANGES.get((plan.time_range or "").strip().lower())
        self.inv.time_range = self._time_range
        self._hashtags = [tag.strip().lstrip("#") for tag in plan.hashtags if tag.strip()][:3]
        self._phrases = [phrase.strip() for phrase in plan.social_phrases if phrase.strip()][:3]
        lists = sum(question.kind == "list" for question in self.inv.questions)
        window = f", news from the past {self._time_range}" if self._time_range else ""
        self.note(
            f"Planned {len(self.inv.questions)} key questions ({lists} asking for a full "
            f"list){window}."
        )

    async def _plan_claim(self) -> None:
        """A claim check has the four fixed key questions of the verify_claim playbook; the
        model only plans their searches, phrases and hashtags, and reads the claimed date."""
        self.note("Planning the claim check: origin, support, earlier fact-checks, context.")
        system = prompts.CLAIM_PLAN.format(queries=self.limits.queries_per_question)
        plan = await self._ask(system, f"Claim to check: {self.inv.brief}", prompts.ClaimPlanOut)
        for number, (text, field) in enumerate(prompts.CLAIM_QUESTIONS, start=1):
            question = Question(ref=f"Q{number}", text=text)
            self.inv.questions.append(question)
            queries = [query.strip() for query in getattr(plan, field) if query.strip()]
            self._planned[question.ref] = queries[: self.limits.queries_per_question]
        self._news = self.inv.news = plan.news
        self.inv.claimed_date = (plan.claimed_date or "").strip() or None
        self._hashtags = [tag.strip().lstrip("#") for tag in plan.hashtags if tag.strip()][:3]
        self._phrases = [phrase.strip() for phrase in plan.social_phrases if phrase.strip()][:3]
        if self.inv.claimed_date:
            self.note(f"The claim dates the event to {self.inv.claimed_date}.")

    def _opening(self) -> list[Query]:
        """First round: each key question's planned searches. The first is a general web
        search (background and lists); the rest search the news when the topic is news."""
        queries = []
        for question in self.inv.questions:
            for index, text in enumerate(self._planned.get(question.ref) or [question.text]):
                queries.append(Query(text, (question.ref,), news=self._news and index > 0))
        return queries

    async def _follow_up(self, number: int) -> list[Query]:
        """Ask the model what to search next, given everything found so far."""
        self.note(f"Round {number}: reviewing what has been found to decide what to search next.")
        searched = "\n".join(f"- {text}" for text in self._searched)
        unread = "\n".join(f"- {title}" for title in self._unread[-20:]) or "- none"
        user = (
            f"Research question: {self.inv.brief}\n\nKey questions:\n{self._menu()}\n\n"
            f"Found so far:\n{self._found_so_far()}\n\nSearches already made:\n{searched}\n\n"
            f"Headlines of pages that could not be read (untrusted data):\n{unread}"
        )
        system = prompts.FOLLOWUP.format(count=self.limits.followup_queries)
        try:
            out = await self._ask(system, user, prompts.FollowupOut)
        except QuotaError:
            raise
        except ModelError as error:
            self.note(f"Could not plan follow-up searches: {error}")
            return []
        refs = {question.ref for question in self.inv.questions}
        queries: list[Query] = []
        for item in out.queries[: self.limits.followup_queries]:
            text = item.query.strip()
            if not text or text.casefold() in self._searched_keys:
                continue
            ref = item.question_ref.strip().upper()
            queries.append(Query(text, (ref,) if ref in refs else tuple(sorted(refs)), item.news))
        if out.done or not queries:
            self.note(f"Round {number}: nothing important left to search; research complete.")
            return []
        shown = "; ".join(f"“{query.text}”" for query in queries)
        self.note(f"Round {number}: following up with {len(queries)} searches: {shown}.")
        return queries

    def _menu(self) -> str:
        return "\n".join(
            f"{q.ref} ({'list' if q.kind == 'list' else 'fact'}): {q.text}"
            for q in self.inv.questions
        )

    def _found_so_far(self) -> str:
        lines = []
        for question in self.inv.questions:
            items = [item for item in self.inv.items if item.question_ref == question.ref]
            claims = [c for c in self.inv.claims if question.ref in c.question_refs]
            lines.append(f"{question.ref}: {len(claims)} claims")
            for item in items:
                lines.append(f"  item: {item.name} — {item.status}, {len(item.origins)} sources")
            if not items:
                lines += [f"  claim: {claim.statement[:160]}" for claim in claims[:12]]
            for mention in [m for m in self._unconfirmed() if m.question_ref == question.ref]:
                when = f" ({mention.when})" if mention.when else ""
                lines.append(f"  seen only in search results, not confirmed: {mention.name}{when}")
        return "\n".join(lines)

    # ---- one research round -------------------------------------------------------

    def _pages_left(self) -> int:
        saved = sum(1 for source in self.inv.sources if source.kind == "page")
        if len(self._attempted) >= 2 * self.limits.max_pages:
            return 0
        return self.limits.max_pages - saved

    async def _round(self, number: int, queries: list[Query]) -> None:
        self.inv.usage.rounds = number
        candidates = await self._search(queries)
        await self._discover(candidates)
        size = self.limits.first_round_pages if number == 1 else self.limits.round_pages
        chosen = await self._choose(candidates, min(size, self._pages_left()))
        sources = await self._fetch(chosen)
        if number == 1:
            await self._social()
            sources += [source for source in self.inv.sources if source.kind == "post"]
        await self._extract(sources)
        await self._inventory()

    async def _search(self, queries: list[Query]) -> list[tuple[str, Candidate]]:
        candidates: dict[str, Candidate] = {}
        groups: list[list[str]] = []
        for query in queries:
            key = query.text.casefold()
            if key in self._searched_keys:
                continue
            args: dict[str, object] = {"query": query.text}
            if query.news:
                args["time_range"] = self._time_range
            tool = "news_search" if query.news else "web_search"
            outcome = await self._call(tool, args, query.refs, "a search planned for this round")
            if outcome.result is None:  # never a repeat: those were skipped above
                if outcome.status == "failed" and not self._searched:
                    raise SearchError(outcome.reason)
                break  # search is failing or out of budget: read what was found
            self._searched_keys.add(key)
            self._searched.append(query.text)
            self.inv.usage.searches += 1
            group = []
            for hit in outcome.result.hits:
                url = canonical(hit.url)
                if not readable(url):
                    for ref in query.refs:
                        self._post_lead(url, ref)
                    continue
                if url in self._attempted:
                    continue
                if url in candidates:
                    candidates[url].refs.update(query.refs)
                else:
                    candidates[url] = Candidate(hit=hit, refs=set(query.refs))
                    group.append(url)
            groups.append(group)
        # Interleave results from different searches so no single search dominates.
        ordered = [
            group[index]
            for index in range(max((len(group) for group in groups), default=0))
            for group in groups
            if index < len(group)
        ]
        return [(url, candidates[url]) for url in ordered]

    async def _discover(self, candidates: list[tuple[str, Candidate]]) -> None:
        """Note every item the search results name, so later rounds can chase each one."""
        lists = [question.ref for question in self.inv.questions if question.kind == "list"]
        if not lists or not candidates:
            return
        window = candidates[:DISCOVER_WINDOW]
        lines = []
        for number, (url, cand) in enumerate(window, start=1):
            when = f", {cand.hit.published}" if cand.hit.published else ""
            lines.append(
                f"H{number} [{assessment.registrable_domain(url)}{when}] "
                f"{cand.hit.title[:150]} — {cand.hit.snippet[:220]}"
            )
        user = f"Key questions:\n{self._menu()}\n\nSearch results:\n" + "\n".join(lines)
        try:
            out = await self._ask(prompts.DISCOVER, user, prompts.DiscoverOut)
        except QuotaError:
            raise
        except ModelError as error:
            self.note(f"Could not scan the search results for names: {error}")
            return
        self._spot(out.items, {f"H{n}": url for n, (url, _) in enumerate(window, start=1)})

    def _spot(self, entries: list[prompts.Spotted], index: dict[str, str]) -> None:
        """Keep each name the search results mention as an unconfirmed mention."""
        lists = [question.ref for question in self.inv.questions if question.kind == "list"]
        spotted = []
        for entry in entries if lists else []:
            name = entry.name.strip()
            urls = [index[r] for r in (x.strip().upper() for x in entry.results) if r in index]
            if not name or not urls:
                continue  # a name no result actually mentions is not kept
            ref = entry.question_ref.strip().upper()
            self._mention(name, ref if ref in lists else lists[0], entry.when.strip(), urls)
            spotted.append(name)
        if spotted:
            shown = ", ".join(spotted[:12]) + ("…" if len(spotted) > 12 else "")
            self.note(f"Spotted {len(spotted)} possible items in the search results: {shown}.")

    def _mention(self, name: str, ref: str, when: str, urls: list[str]) -> None:
        for mention in self.inv.mentions:
            if mention.question_ref == ref and same_item(mention.name, name):
                mention.urls = list(dict.fromkeys(mention.urls + urls))[:5]
                mention.when = mention.when or when
                return
        if len(self.inv.mentions) < MAX_MENTIONS:
            self.inv.mentions.append(Mention(question_ref=ref, name=name, when=when, urls=urls[:5]))

    def _unconfirmed(self) -> list[Mention]:
        return [
            mention
            for mention in self.inv.mentions
            if not any(same_item(item.name, mention.name) for item in self.inv.items)
        ]

    def _settle_mentions(self) -> None:
        """Keep only mentions no read page confirmed; the confirmed ones are items now."""
        self.inv.mentions = self._unconfirmed()

    async def _choose(
        self, candidates: list[tuple[str, Candidate]], budget: int
    ) -> list[tuple[str, Candidate]]:
        """Pick up to `budget` pages to read: the model triages, code enforces site caps."""
        if budget <= 0 or not candidates:
            return []
        eligible = self._eligible(candidates)
        ranked = eligible
        if len(eligible) > budget:
            picked = await self._triage(eligible[:TRIAGE_WINDOW], budget) or []
            # Read at least half the budget: top up with the search order if the model
            # picked too few, so one cautious answer cannot starve a round.
            minimum = (budget + 1) // 2
            extra = [pair for pair in eligible if pair not in picked]
            ranked = picked + extra[: max(0, minimum - len(picked))] if picked else eligible
        return self._capped(ranked, budget)

    def _eligible(self, candidates: list[tuple[str, Candidate]]) -> list[tuple[str, Candidate]]:
        """Results on sites still worth trying and below the per-site cap."""
        per_site = Counter(assessment.registrable_domain(url) for url in self._attempted)
        return [
            (url, cand)
            for url, cand in candidates
            if per_site[assessment.registrable_domain(url)] < PER_DOMAIN
            and self._worth_trying(assessment.registrable_domain(url))
        ]

    def _capped(
        self, ranked: list[tuple[str, Candidate]], budget: int
    ) -> list[tuple[str, Candidate]]:
        """The first `budget` results in order, at most PER_DOMAIN per site overall."""
        per_site = Counter(assessment.registrable_domain(url) for url in self._attempted)
        chosen = []
        for url, cand in ranked:
            site = assessment.registrable_domain(url)
            if per_site[site] >= PER_DOMAIN:
                continue
            per_site[site] += 1
            chosen.append((url, cand))
            if len(chosen) >= budget:
                break
        return chosen

    def _worth_trying(self, domain: str) -> bool:
        """A site that refused is tried again only through its archived copies."""
        if domain in self._ctx.robots_no:
            return False
        return domain not in self._ctx.refusing or self.tools.archive is not None

    async def _triage(
        self, window: list[tuple[str, Candidate]], budget: int
    ) -> list[tuple[str, Candidate]] | None:
        lines = []
        for number, (url, cand) in enumerate(window, start=1):
            hit = cand.hit
            when = f", {hit.published}" if hit.published else ""
            lines.append(
                f"H{number} [{assessment.registrable_domain(url)}{when}] {hit.title[:150]} — "
                f"{hit.snippet[:200]}"
            )
        found = self._found_so_far() if self.inv.claims else "Nothing yet."
        user = (
            f"Key questions:\n{self._menu()}\n\nFound so far:\n{found}\n\n"
            f"Search results:\n" + "\n".join(lines)
        )
        try:
            out = await self._ask(prompts.TRIAGE.format(count=budget), user, prompts.TriageOut)
        except QuotaError:
            raise
        except ModelError as error:
            self.note(f"Could not rank the search results ({error}); using search order.")
            return None
        index = {f"H{number}": pair for number, pair in enumerate(window, start=1)}
        picks = [
            index[ref] for ref in dict.fromkeys(r.strip().upper() for r in out.read) if ref in index
        ]
        if picks:
            self.note(f"Chose {len(picks)} of {len(window)} results as most promising to read.")
        return picks or None

    async def _fetch(self, chosen: list[tuple[str, Candidate]]) -> list[Source]:
        if not chosen:
            return []
        self.note(f"Reading {len(chosen)} pages.")
        limit = asyncio.Semaphore(4)

        async def one(url: str, cand: Candidate) -> Source | None:
            self._attempted.add(url)
            async with limit:
                outcome = await self._call(
                    "read_page", {"url": url}, cand.refs, "chosen from the search results"
                )
            drafts = outcome.result.sources if outcome.result else []
            if not drafts:
                self.inv.usage.pages_skipped += 1
                if outcome.status == "failed":
                    self._page_lead(url, cand.refs, outcome.reason)
                domain = assessment.registrable_domain(url)
                self._unread.append(f"{cand.hit.title[:160]} ({domain})")
                return None
            return self._page_source(drafts[0], cand)

        results = await asyncio.gather(*(one(url, cand) for url, cand in chosen))
        saved = []
        for source in results:
            if source is None:
                continue
            source.ref = f"S{len(self.inv.sources) + 1}"
            self.inv.sources.append(source)
            self.inv.usage.pages_fetched += 1
            saved.append(source)
        self.note(f"Saved {len(saved)} pages with their sha256 fingerprints.")
        return saved

    def _page_source(self, draft: SourceDraft, cand: Candidate) -> Source:
        grade, why = assessment.rate_source(draft.url)
        if draft.archive_url:
            why += "; read from a Wayback Machine copy"
            self.inv.usage.archived += 1
        return Source(
            ref="",
            url=draft.url,
            domain=assessment.registrable_domain(draft.url),
            origin=draft.origin,
            title=draft.title,
            published=draft.published or cand.hit.published,
            fetched_at=now(),
            sha256=self.store.put_blob(draft.body),
            text_sha256=self.store.put_text(draft.text),
            size=len(draft.body),
            reliability=grade,
            reliability_reason=why,
            question_refs=sorted(cand.refs),
            archive_url=draft.archive_url,
            archived_at=draft.archived_at,
        )

    # ---- links Lantern lists but does not read -------------------------------------

    async def _find_leads(self) -> None:
        """Ask the search engine for posts on sites Lantern may not read; never open them."""
        refs = [question.ref for question in self.inv.questions]
        phrases = self._phrases[:2] or [self.inv.brief[:120]]
        for phrase in phrases:
            outcome = await self._call(
                "post_links", {"phrase": phrase}, refs, "posts on sites Lantern may not read"
            )
            if outcome.result is None:
                return
            self.inv.usage.searches += 1
            for hit in outcome.result.hits:
                for ref in refs:
                    self._post_lead(canonical(hit.url), ref)

    def _post_lead(self, url: str, ref: str) -> None:
        # Only the post link and platform are kept, never the hit's title or snippet.
        platform = post_lead(url)
        if platform is None:
            return
        for lead in self.inv.leads:
            if lead.url == url:
                if ref not in lead.question_refs:
                    lead.question_refs.append(ref)
                return
        if sum(lead.kind == "post" for lead in self.inv.leads) < MAX_POST_LEADS:
            self.inv.leads.append(Lead(platform=platform, url=url, question_refs=[ref]))

    def _page_lead(self, url: str, refs: set[str], reason: str) -> None:
        if any(lead.url == url for lead in self.inv.leads):
            return
        if sum(lead.kind == "page" for lead in self.inv.leads) >= MAX_PAGE_LEADS:
            return
        lead = Lead(
            platform=assessment.registrable_domain(url),
            url=url,
            question_refs=sorted(refs),
            kind="page",
            reason=reason,
        )
        self.inv.leads.append(lead)

    # ---- social media ground reports ------------------------------------------------

    async def _social(self) -> list[Source]:
        """Collect public posts about the event as ground reports (never account timelines)."""
        if self.tools.social is None:
            return []
        self.note("Looking for ground reports in public social media posts.")
        everything = [question.ref for question in self.inv.questions]
        phrases = self._phrases[:2] or [
            (self._planned.get(q.ref) or [q.text])[0] for q in self.inv.questions
        ]
        phrases += [f"#{tag}" for tag in self._hashtags[:1]]
        searches = [{"phrase": phrase} for phrase in phrases]
        searches += [{"hashtag": tag} for tag in self._hashtags]
        found: list[SourceDraft] = []
        for args in searches:
            outcome = await self._call("social_search", dict(args), everything, "ground reports")
            found += outcome.result.sources if outcome.result else []
        saved = self._keep_posts(found, everything)
        self.note(f"Saved {len(saved)} posts as ground reports, with sha256 fingerprints.")
        return saved

    def _keep_posts(self, found: list[SourceDraft], refs: list[str]) -> list[Source]:
        """Save new posts as ground reports: no repeated text, at most `posts_per_account`
        per account and `max_posts` in the whole investigation."""
        posts = [source for source in self.inv.sources if source.kind == "post"]
        per_origin = Counter(source.origin for source in posts)
        known = {source.url for source in posts}
        saved: list[Source] = []
        for post in found:
            key = normalise(post.text)[0][:200]
            if len(posts) + len(saved) >= self.limits.max_posts:
                break
            if key in self._post_texts or post.url in known:
                continue
            if per_origin[post.origin] >= self.limits.posts_per_account:
                continue
            self._post_texts.add(key)
            per_origin[post.origin] += 1
            saved.append(self._save_post(post, refs))
        self.inv.usage.posts_saved += len(saved)
        return saved

    def _save_post(self, post: SourceDraft, refs: list[str]) -> Source:
        # The saved copy keeps the post itself, not who wrote it.
        platform = post.origin.split(":", 1)[0]
        source = Source(
            ref=f"S{len(self.inv.sources) + 1}",
            url=post.url,
            domain=urlsplit(post.url).hostname or platform,
            kind="post",
            origin=post.origin,
            title=post.title,
            published=post.published,
            fetched_at=now(),
            sha256=self.store.put_blob(post.body),
            text_sha256=self.store.put_text(post.text),
            size=len(post.body),
            reliability="D",
            reliability_reason="Social media post: an unverified ground report",
            question_refs=sorted(refs),
        )
        self.inv.sources.append(source)
        return source

    # ---- claims ---------------------------------------------------------------------

    async def _extract(self, sources: list[Source]) -> None:
        pages = [source for source in sources if source.kind == "page"]
        posts = [source for source in sources if source.kind == "post"]
        if not pages and not posts:
            return
        self.note("Pulling out claims with exact quotes.")
        before = len(self.inv.claims)
        page_results, post_claims = await asyncio.gather(
            asyncio.gather(*(self._extract_page(source) for source in pages)),
            self._extract_posts(posts),
        )
        pairs = [pair for result in page_results for pair in result]
        for claim, triple in [*pairs, *((claim, None) for claim in post_claims)]:
            claim.ref = f"C{len(self.inv.claims) + 1}"
            self.inv.claims.append(claim)
            if triple is not None:  # a relation the claim states, kept with its claim ref
                triple.claim_refs = [claim.ref]
                self.inv.relations.append(triple)
        added = len(self.inv.claims) - before
        dropped = self.inv.usage.claims_dropped
        self.note(
            f"Anchored {added} new claims ({len(self.inv.claims)} in total); "
            f"{dropped} dropped so far because their quote was not found."
        )

    async def _extract_page(self, source: Source) -> list[tuple[Claim, Triple | None]]:
        refs = {question.ref for question in self.inv.questions}
        text = self.store.text(source.text_sha256) or ""
        found: dict[tuple[int, int], tuple[Claim, Triple | None]] = {}
        terms = [self.inv.brief, *(q.text for q in self.inv.questions)]
        terms += [item.name for item in self.inv.items]
        for part in relevant_chunks(text, terms, limit=self.limits.chunks_per_page):
            user = (
                f'Key questions:\n{self._menu()}\n\n<page url="{source.url}" '
                f'title="{source.title or ""}" published="{source.published or ""}">\n'
                f"{part}\n</page>"
            )
            async with self._reading:
                try:
                    out = await self._ask(prompts.EXTRACT, user, prompts.ExtractOut, role="read")
                except QuotaError:
                    raise
                except ModelError as error:
                    self.note(f"Could not read claims from {source.ref}: {error}")
                    return list(found.values())
            for draft in out.claims[:CLAIMS_PER_PAGE]:
                span = find_quote(text, draft.quote)
                linked = sorted({r.strip().upper() for r in draft.question_refs} & refs)
                if span is None or not linked or span in found:
                    self.inv.usage.claims_dropped += 1
                    continue
                quote = text[span[0] : span[1]]
                claim = Claim(
                    ref="",
                    source_ref=source.ref,
                    question_refs=linked,
                    statement=draft.statement.strip(),
                    quote=quote,
                    start=span[0],
                    end=span[1],
                )
                relation = draft.relation
                triple = relation and graph.stated(
                    quote,
                    subject=relation.subject,
                    subject_kind=relation.subject_kind,
                    relation=relation.relation,
                    obj=relation.object,
                    object_kind=relation.object_kind,
                )
                found[span] = (claim, triple or None)
        self.note(f"{source.ref} ({source.domain}): {len(found)} claims anchored.")
        return list(found.values())

    async def _extract_posts(self, posts: list[Source]) -> list[Claim]:
        refs = {question.ref for question in self.inv.questions}
        claims: list[Claim] = []
        spans: set[tuple[str, int, int]] = set()
        for start in range(0, len(posts), 8):
            batch = posts[start : start + 8]
            texts = {source.ref: self.store.text(source.text_sha256) or "" for source in batch}
            body = "\n\n".join(
                f'<post ref="{s.ref}" posted="{s.published or ""}">\n{texts[s.ref]}\n</post>'
                for s in batch
            )
            user = f"Key questions:\n{self._menu()}\n\n{body}"
            async with self._reading:
                try:
                    out = await self._ask(
                        prompts.EXTRACT_POSTS, user, prompts.ExtractPostsOut, role="read"
                    )
                except QuotaError:
                    raise
                except ModelError as error:
                    self.note(f"Could not read claims from posts: {error}")
                    continue
            for draft in out.claims[:8]:
                ref = draft.post_ref.strip().upper()
                text = texts.get(ref)
                span = find_quote(text, draft.quote) if text else None
                linked = sorted({r.strip().upper() for r in draft.question_refs} & refs)
                if text is None or span is None or not linked or (ref, *span) in spans:
                    self.inv.usage.claims_dropped += 1
                    continue
                spans.add((ref, *span))
                statement = draft.statement.strip()
                if not statement.lower().startswith("a social media post"):
                    statement = f"A social media post reported: {statement}"
                claims.append(
                    Claim(
                        ref="",
                        source_ref=ref,
                        question_refs=linked,
                        statement=statement,
                        quote=text[span[0] : span[1]],
                        start=span[0],
                        end=span[1],
                    )
                )
        if posts:
            self.note(f"Posts: {len(claims)} ground-report claims anchored.")
        return claims

    # ---- everything found for list questions -----------------------------------------

    async def _inventory(self, refs: Iterable[str] | None = None) -> None:
        """Rebuild the list of every item found for each list question (or only those in
        `refs`), weak sources included."""
        wanted = None if refs is None else set(refs)
        for question in self.inv.questions:
            if question.kind != "list" or (wanted is not None and question.ref not in wanted):
                continue
            claims = [c for c in self.inv.claims if question.ref in c.question_refs][:80]
            if not claims:
                continue
            user = f"List-type key question {question.ref}: {question.text}\n\nClaims:\n"
            user += "\n".join(self._claim_line(claim) for claim in claims)
            drafted = await self._draft_items(question, claims, user)
            if drafted is None:
                continue
            items = drafted
            # Never lose an item: keep any earlier item whose claims the new list left out.
            covered = {ref for item in items for ref in item.claim_refs}
            for old in [i for i in self.inv.items if i.question_ref == question.ref]:
                if not covered & set(old.claim_refs):
                    items.append(old)
                    covered |= set(old.claim_refs)
            items = self._merge_same_names(items)
            for item in items:
                item.in_period = not assessment.outside_period(
                    item.when, now().date(), self._time_range
                )
            self.inv.items = [i for i in self.inv.items if i.question_ref != question.ref] + items
            current = [item for item in items if item.in_period]
            corroborated = sum(item.status == "corroborated" for item in current)
            older = len(items) - len(current)
            note = f"; {older} more outside the period" if older else ""
            self.note(
                f"{question.ref}: {len(current)} items found so far ({corroborated} corroborated, "
                f"{len(current) - corroborated} from a single source{note})."
            )

    async def _draft_items(
        self, question: Question, claims: list[Claim], user: str
    ) -> list[Item] | None:
        """The items the claims describe, drafted by the fast model. When it fails or lists
        nothing usable, the main model is asked once. None when no model could answer."""
        roles: list[Role] = ["fast", "think"] if self.tools.fast is not None else ["think"]
        drafted: list[Item] | None = None
        problem = ""
        for role in roles:
            try:
                out = await self._ask(prompts.INVENTORY, user, prompts.InventoryOut, role=role)
            except QuotaError:
                raise
            except ModelError as error:
                problem = str(error)
                continue
            drafted = self._items(question, claims, out)
            if drafted:
                break
            if role == "fast":
                self.note(f"{question.ref}: the fast model listed no usable items; asking again.")
        if drafted is None:
            self.note(f"Could not update the list for {question.ref}: {problem}")
        return drafted

    def _items(
        self, question: Question, claims: list[Claim], out: prompts.InventoryOut
    ) -> list[Item]:
        valid = {claim.ref for claim in claims}
        items = []
        for draft in out.items:
            refs = list(dict.fromkeys(r.strip().upper() for r in draft.claims))
            refs = [ref for ref in refs if ref in valid]
            if not refs:
                continue
            sources = [self.inv.source(c.source_ref) for r in refs if (c := self.inv.claim(r))]
            known = [source for source in sources if source]
            origins = sorted({source.origin or source.domain for source in known})
            items.append(
                Item(
                    question_ref=question.ref,
                    name=draft.name.strip(),
                    summary=strip_refs(draft.summary),
                    when=draft.when.strip(),
                    claim_refs=refs,
                    origins=origins,
                    best_grade=assessment.best_grade(source.reliability for source in known),
                    status=assessment.item_status(len(origins)),
                )
            )
        return sorted(items, key=lambda item: (-len(item.origins), item.name.casefold()))

    def _merge_same_names(self, items: list[Item]) -> list[Item]:
        """One row per name: items with the same name (ignoring case and spacing) merge,
        and their status is recomputed from the combined evidence."""
        merged: dict[str, Item] = {}
        for item in items:
            key = " ".join(normalise(item.name)[0].split())
            if key not in merged:
                merged[key] = item
                continue
            first = merged[key]
            refs = list(dict.fromkeys(first.claim_refs + item.claim_refs))
            origins = sorted(set(first.origins) | set(item.origins))
            merged[key] = first.model_copy(
                update={
                    "claim_refs": refs,
                    "origins": origins,
                    "when": first.when or item.when,
                    "best_grade": assessment.best_grade([first.best_grade, item.best_grade]),
                    "status": assessment.item_status(len(origins)),
                }
            )
        return sorted(merged.values(), key=lambda item: (-len(item.origins), item.name.casefold()))

    def _claim_line(self, claim: Claim) -> str:
        source = self.inv.source(claim.source_ref)
        if source is None:
            return f"{claim.ref}: {claim.statement}"
        where = "social media post" if source.kind == "post" else source.domain
        when = f", published {source.published}" if source.published else ""
        return (
            f"{claim.ref} [{claim.source_ref} {where}, grade {source.reliability}{when}]: "
            f"{claim.statement} Quote: “{claim.quote}”"
        )

    # ---- findings and report ---------------------------------------------------------

    async def _assess(self) -> None:
        for question in self.inv.questions:
            self.note(f"Assessing {question.ref}.")
            claims = [c for c in self.inv.claims if question.ref in c.question_refs]
            claims = claims[: self.limits.claims_per_question]
            finding = await self._assess_one(question, claims)
            question.status = finding.status
            self.inv.findings.append(finding)

    def _items_text(self, question_ref: str) -> str:
        items = [item for item in self.inv.items if item.question_ref == question_ref]
        if not items:
            return ""
        lines = [
            f"- {item.name}: {item.summary} [{item.status}, {len(item.origins)} sources; "
            f"{', '.join(item.claim_refs)}]"
            for item in items
        ]
        return "Items found:\n" + "\n".join(lines) + "\n\n"

    async def _assess_one(self, question: Question, claims: list[Claim]) -> Finding:
        if not claims:
            return Finding(
                question_ref=question.ref,
                status="unanswerable",
                answer="No usable evidence was found in the pages read.",
            )
        user = (
            f"Key question {question.ref}: {question.text}\n\n{self._items_text(question.ref)}"
            "Claims:\n" + "\n".join(self._claim_line(claim) for claim in claims)
        )
        try:
            out = await self._ask(prompts.ASSESS, user, prompts.AssessOut)
        except QuotaError:
            raise
        except ModelError as error:
            return Finding(
                question_ref=question.ref,
                status="unanswerable",
                answer=f"The assessment step failed: {error}",
            )
        valid = {claim.ref for claim in claims}
        supporting = list(dict.fromkeys(r for r in out.supporting if r in valid))
        contradicting = [r for r in dict.fromkeys(out.contradicting) if r in valid]
        contradicting = [r for r in contradicting if r not in supporting]
        if out.status == "unanswerable" or not supporting:
            return Finding(question_ref=question.ref, status="unanswerable", answer=out.answer)
        sources = [self.inv.source(c.source_ref) for c in claims if c.ref in supporting]
        domains = sorted({s.origin or s.domain for s in sources if s})
        best = min((s.reliability for s in sources if s), default=None)
        level, why = assessment.confidence(len(domains), best, bool(contradicting))
        likelihood = assessment.clamp_likelihood(out.likelihood or "", len(domains))
        links = [
            triple
            for draft in out.links
            if (
                triple := graph.assessed(
                    draft.subject,
                    draft.relation,
                    draft.object,
                    [ref for ref in dict.fromkeys(draft.supporting) if ref in valid],
                    [ref for ref in dict.fromkeys(draft.contradicting) if ref in valid],
                )
            )
        ]
        finding = Finding(
            question_ref=question.ref,
            links=links,
            status="answered",
            answer=strip_refs(out.answer),
            likelihood_proposed=out.likelihood,
            likelihood=likelihood,
            confidence=level,
            confidence_reason=why,
            supporting=supporting,
            contradicting=contradicting,
            domains=domains,
            rationale=out.rationale,
        )
        self._rate(finding, claims)
        return finding

    @staticmethod
    def _rate(finding: Finding, claims: list[Claim]) -> None:
        """Set the credibility of the claims a finding cites, from its corroboration."""
        cited = set(finding.supporting) | set(finding.contradicting)
        for claim in claims:
            if claim.ref in cited:
                claim.credibility = assessment.credibility(
                    len(finding.domains),
                    bool(finding.contradicting),
                    claim.ref in finding.supporting,
                )

    async def _verdict(self) -> None:
        """The verdict of a claim check: proposed by the model from the findings, decided
        by the rules of core/verdict.py, and its sentence checked like any report sentence."""
        answered = [f for f in self.inv.findings if f.status == "answered"]
        if not answered:
            reason = verdict.NEEDS["unproven"]
            self.inv.verdict = Verdict(label="unproven", label_proposed="unproven", reason=reason)
            return
        self.note("Weighing the verdict.")
        parts = []
        for finding in answered:
            question = self.inv.question(finding.question_ref)
            parts.append(
                f"{finding.question_ref}: {question.text if question else ''}\n"
                f"  Answer: {finding.answer}\n  Likelihood: {finding.likelihood}"
            )
        refs = {ref for f in answered for ref in f.supporting + f.contradicting}
        claims = [self._claim_line(c) for c in self.inv.claims if c.ref in refs]
        user = (
            f"Claim to check: {self.inv.brief}\nClaimed date: {self.inv.claimed_date or 'none'}"
            "\n\nFindings:\n" + "\n".join(parts) + "\n\nClaims:\n" + "\n".join(claims)
        )
        try:
            out = await self._ask(prompts.VERDICT, user, prompts.VerdictOut)
        except BudgetError as error:  # this run's own limit: the findings and report stand
            reason = f"No verdict was weighed: {error}"
            self.inv.verdict = Verdict(label="unproven", label_proposed="unproven", reason=reason)
            return
        except QuotaError:
            raise
        except ModelError as error:
            reason = f"The verdict step failed: {error}"
            self.inv.verdict = Verdict(label="unproven", label_proposed="unproven", reason=reason)
            return
        valid = {claim.ref for claim in self.inv.claims}
        cites = [r for r in dict.fromkeys(c.strip().upper() for c in out.cites) if r in valid]
        against = [r for r in dict.fromkeys(c.strip().upper() for c in out.against) if r in valid]
        against = [ref for ref in against if ref not in cites]
        context = any(f.question_ref == "Q4" for f in answered)
        ruling = verdict.decide(
            out.label,
            out.likelihood,
            [self._cited(ref) for ref in cites],
            [self._cited(ref) for ref in against],
            context=context,
        )
        self.inv.verdict = Verdict(
            label=ruling.label,
            label_proposed=out.label,
            reason=ruling.reason,
            likelihood=ruling.likelihood,
            likelihood_proposed=out.likelihood or None,
            confidence=ruling.confidence,
            confidence_reason=ruling.confidence_reason,
            cites=cites if ruling.label != "unproven" else [],
            sentence=self._verdict_sentence(out, ruling, cites, valid),
        )
        self.note(f"Verdict: {ruling.label}. {ruling.reason}")

    def _verdict_sentence(
        self, out: prompts.VerdictOut, ruling: verdict.Ruling, cites: list[str], valid: set[str]
    ) -> Sentence | None:
        """The verdict sentence when it states the decided label, uses no likelihood but the
        allowed one (shown on its own beside the label anyway), and passes the citation
        check; otherwise None, and it is listed as removed."""
        text = strip_refs(out.sentence)
        if not text:
            return None
        report = self.inv.report or Report()
        reason = ""
        if ruling.label != out.label:
            reason = f"It states “{out.label}”, which the evidence does not carry."
        elif (used := likelihood_terms(text)) and used != {ruling.likelihood}:
            reason = (
                f"It uses a likelihood the evidence does not allow ({ruling.likelihood})."
                if ruling.likelihood
                else "An unproven verdict has no likelihood, but the sentence uses one."
            )
        if reason:
            report.removed.append(Removed(text=text, reason=reason))
            return None
        return check_sentence(prompts.SentenceOut(text=text, cites=cites), valid, report.removed)

    def _cited(self, ref: str) -> verdict.Cited:
        claim = self.inv.claim(ref)
        source = self.inv.source(claim.source_ref) if claim else None
        if source is None:
            return verdict.Cited(ref=ref, origin=ref, grade="F")
        return verdict.Cited(
            ref=ref,
            origin=source.origin or source.domain,
            grade=source.reliability,
            fact_check=source.kind == "page" and assessment.fact_checker(source.url),
            archive=source.origin == ARCHIVE_ORIGIN,
        )

    async def _write(self) -> None:
        answered = [f for f in self.inv.findings if f.status == "answered"]
        if not answered:
            self.inv.report = verify(prompts.ReportOut(bottom_line=[], sections=[]), self.inv)
            self.note("No key question could be answered from the pages read.")
            return
        self.note("Writing the report.")
        parts = []
        for finding in answered:
            question = self.inv.question(finding.question_ref)
            cited = [
                c for c in self.inv.claims if c.ref in finding.supporting + finding.contradicting
            ]
            claims = "\n".join(f"  {c.ref}: {c.statement}" for c in cited)
            parts.append(
                f"{finding.question_ref}: {question.text if question else ''}\n"
                f"  Answer: {finding.answer}\n  Likelihood: {finding.likelihood}\n"
                f"  Supporting: {', '.join(finding.supporting)}\n"
                f"  Contradicting: {', '.join(finding.contradicting) or 'none'}\n"
                f"{self._items_text(finding.question_ref)}{claims}"
            )
        user = f"Research question: {self.inv.brief}\n\nFindings:\n" + "\n\n".join(parts)
        draft = await self._ask(prompts.WRITE, user, prompts.ReportOut)
        report: Report = verify(draft, self.inv)
        self.inv.report = report
        self.note(f"Checked every sentence: kept the cited ones, removed {len(report.removed)}.")
