"""The investigation: safety check, key questions, research rounds, findings, report.

Each research round searches the web and the news, chooses the most promising results,
reads and preserves pages, and pulls out quote-anchored claims. Later rounds follow up on
what earlier rounds found: single-source items, missing items, other names, other
languages and primary sources. The model proposes searches, picks pages and drafts
claims; code checks every quote, counts independent origins and sets confidence.
"""

import asyncio
import json
import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from lantern import assessment, prompts
from lantern.capture import extract
from lantern.egress import FetchError, Page
from lantern.llm import Model, ModelError, QuotaError
from lantern.models import Claim, Finding, Investigation, Item, Lead, Question, Report, Source, now
from lantern.report import strip_refs, verify
from lantern.safety import check_brief
from lantern.search import Hit, Searcher, SearchError, TimeRange
from lantern.sites import POST_LINKS, canonical, post_lead, readable
from lantern.social import Post, SocialSearch
from lantern.store import Store
from lantern.text import chunks, find_quote, normalise

log = logging.getLogger(__name__)

PER_DOMAIN = 3  # pages per site in one investigation, so corroboration stays independent
MAX_POST_LEADS = 12
MAX_PAGE_LEADS = 15
TRIAGE_WINDOW = 40
CLAIMS_PER_PAGE = 12
TIME_RANGES: dict[str, TimeRange] = {"day": "day", "week": "week", "month": "month", "year": "year"}


class PageFetcher(Protocol):
    async def fetch(self, url: str) -> Page: ...


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
        )


@dataclass
class Tools:
    model: Model
    searcher: Searcher
    fetcher: PageFetcher
    social: SocialSearch | None = None
    reader: Model | None = None  # bulk page reading; defaults to `model`


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
        self._news = False
        self._time_range: TimeRange | None = None
        self._hashtags: list[str] = []
        self._phrases: list[str] = []
        self._searched: list[str] = []
        self._searched_keys: set[str] = set()
        self._attempted: set[str] = set()
        self._reading = asyncio.Semaphore(3)

    def note(self, message: str) -> None:
        self.inv.log(message)
        self.store.save(self.inv)
        if self.on_change:
            self.on_change(self.inv)

    async def run(self) -> Investigation:
        self.inv.status = "running"
        try:
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
                await self._assess()
                await self._write()
                self.inv.status = "done"
                self.note("Finished.")
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
            gate = await self.tools.model.structured(
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
        self.note("Planning key questions and searches.")
        system = prompts.PLAN.format(
            count=f"2 to {self.limits.max_questions}", queries=self.limits.queries_per_question
        )
        plan = await self.tools.model.structured(
            system, f"Research question: {self.inv.brief}", prompts.PlanOut
        )
        for number, item in enumerate(plan.questions[: self.limits.max_questions], start=1):
            question = Question(ref=f"Q{number}", text=item.text.strip(), kind=item.kind)
            self.inv.questions.append(question)
            queries = [query.strip() for query in item.queries if query.strip()]
            self._planned[question.ref] = queries[: self.limits.queries_per_question]
        self._news = plan.news
        self._time_range = TIME_RANGES.get((plan.time_range or "").strip().lower())
        self._hashtags = [tag.strip().lstrip("#") for tag in plan.hashtags if tag.strip()][:3]
        self._phrases = [phrase.strip() for phrase in plan.social_phrases if phrase.strip()][:3]
        lists = sum(question.kind == "list" for question in self.inv.questions)
        window = f", news from the past {self._time_range}" if self._time_range else ""
        self.note(
            f"Planned {len(self.inv.questions)} key questions ({lists} asking for a full "
            f"list){window}."
        )

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
        user = (
            f"Research question: {self.inv.brief}\n\nKey questions:\n{self._menu()}\n\n"
            f"Found so far:\n{self._found_so_far()}\n\nSearches already made:\n{searched}"
        )
        system = prompts.FOLLOWUP.format(count=self.limits.followup_queries)
        try:
            out = await self.tools.model.structured(system, user, prompts.FollowupOut)
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
            try:
                hits = await self.tools.searcher.search(
                    query.text,
                    self.limits.results_per_query,
                    news=query.news,
                    time_range=self._time_range if query.news else None,
                )
            except SearchError as error:
                if not self._searched:
                    raise
                self.note(f"Search stopped early: {error}")
                break
            self._searched_keys.add(key)
            self._searched.append(query.text)
            self.inv.usage.searches += 1
            label = "news" if query.news else "web"
            self.note(f"Searched the {label}: “{query.text}” ({len(hits)} results).")
            group = []
            for hit in hits:
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

    async def _choose(
        self, candidates: list[tuple[str, Candidate]], budget: int
    ) -> list[tuple[str, Candidate]]:
        """Pick up to `budget` pages to read: the model triages, code enforces site caps."""
        if budget <= 0 or not candidates:
            return []
        per_site = Counter(assessment.registrable_domain(url) for url in self._attempted)
        eligible = [
            (url, cand)
            for url, cand in candidates
            if per_site[assessment.registrable_domain(url)] < PER_DOMAIN
        ]
        ranked = eligible
        if len(eligible) > budget:
            picked = await self._triage(eligible[:TRIAGE_WINDOW], budget)
            ranked = picked if picked else eligible
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
            out = await self.tools.model.structured(
                prompts.TRIAGE.format(count=budget), user, prompts.TriageOut
            )
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
            domain = assessment.registrable_domain(url)
            async with limit:
                try:
                    page = await self.tools.fetcher.fetch(url)
                except FetchError as error:
                    self.inv.usage.pages_skipped += 1
                    self.note(f"Skipped {domain}: {error}")
                    self._page_lead(url, cand.refs, str(error))
                    return None
            extracted = await asyncio.to_thread(extract, page)
            if extracted is None:
                self.inv.usage.pages_skipped += 1
                self.note(f"Skipped {domain}: no readable text.")
                self._page_lead(url, cand.refs, "Lantern found no readable text on the page.")
                return None
            grade, why = assessment.rate_source(page.url)
            return Source(
                ref="",
                url=page.url,
                domain=assessment.registrable_domain(page.url),
                origin=assessment.registrable_domain(page.url),
                title=extracted.title,
                published=extracted.published or cand.hit.published,
                fetched_at=now(),
                sha256=self.store.put_blob(page.body),
                text_sha256=self.store.put_text(extracted.text),
                size=len(page.body),
                reliability=grade,
                reliability_reason=why,
                question_refs=sorted(cand.refs),
            )

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

    # ---- links Lantern lists but does not read -------------------------------------

    async def _find_leads(self) -> None:
        """Ask the search engine for posts on sites Lantern may not read; never open them."""
        refs = [question.ref for question in self.inv.questions]
        phrases = self._phrases[:2] or [self.inv.brief[:120]]
        domains = sorted(POST_LINKS)
        before = len(self.inv.leads)
        for phrase in phrases:
            try:
                hits = await self.tools.searcher.search(phrase, 10, domains=domains)
            except SearchError as error:
                self.note(f"Could not search social media sites for leads: {error}")
                return
            self.inv.usage.searches += 1
            for hit in hits:
                for ref in refs:
                    self._post_lead(canonical(hit.url), ref)
        found = len(self.inv.leads) - before
        self.note(f"Searched X, Facebook, Instagram, Reddit and others for posts: {found} leads.")

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

    async def _social(self) -> None:
        """Collect public posts about the event as ground reports (never account timelines)."""
        social = self.tools.social
        if social is None:
            return
        self.note("Looking for ground reports in public social media posts.")
        found: list[tuple[Post, list[str]]] = []
        everything = [question.ref for question in self.inv.questions]
        phrases = self._phrases[:2] or [
            (self._planned.get(q.ref) or [q.text])[0] for q in self.inv.questions
        ]
        phrases += [f"#{tag}" for tag in self._hashtags[:1]]
        for phrase in phrases:
            posts = await social.search(phrase, self.limits.posts_per_query)
            self.note(f"Bluesky: searched “{phrase}” ({len(posts)} posts).")
            found += [(post, everything) for post in posts]
        for tag in self._hashtags:
            posts = await social.hashtag(tag, self.limits.posts_per_query)
            self.note(f"Mastodon: #{tag} ({len(posts)} public posts).")
            found += [(post, everything) for post in posts]
        seen: set[str] = set()
        per_origin: dict[str, int] = {}
        saved = 0
        for post, refs in found:
            key = normalise(post.text)[0][:200]
            if key in seen or per_origin.get(post.origin, 0) >= self.limits.posts_per_account:
                continue
            seen.add(key)
            per_origin[post.origin] = per_origin.get(post.origin, 0) + 1
            self._save_post(post, refs)
            saved += 1
            if saved >= self.limits.max_posts:
                break
        self.inv.usage.posts_saved = saved
        self.note(f"Saved {saved} posts as ground reports, with sha256 fingerprints.")

    def _save_post(self, post: Post, refs: list[str]) -> None:
        # The saved copy keeps the post itself, not who wrote it.
        record = {
            "platform": post.platform,
            "url": post.url,
            "posted_at": post.posted_at,
            "language": post.language,
            "text": post.text,
        }
        body = json.dumps(record, ensure_ascii=False, sort_keys=True).encode()
        self.inv.sources.append(
            Source(
                ref=f"S{len(self.inv.sources) + 1}",
                url=post.url,
                domain=urlsplit(post.url).hostname or post.platform,
                kind="post",
                origin=post.origin,
                title=f"{post.platform.capitalize()} post",
                published=post.posted_at or None,
                fetched_at=now(),
                sha256=self.store.put_blob(body),
                text_sha256=self.store.put_text(post.text),
                size=len(body),
                reliability="D",
                reliability_reason="Social media post: an unverified ground report",
                question_refs=sorted(refs),
            )
        )

    # ---- claims ---------------------------------------------------------------------

    async def _extract(self, sources: list[Source]) -> None:
        pages = [source for source in sources if source.kind == "page"]
        posts = [source for source in sources if source.kind == "post"]
        if not pages and not posts:
            return
        self.note("Pulling out claims with exact quotes.")
        before = len(self.inv.claims)
        results = await asyncio.gather(
            *(self._extract_page(source) for source in pages), self._extract_posts(posts)
        )
        for claims in results:
            for claim in claims:
                claim.ref = f"C{len(self.inv.claims) + 1}"
                self.inv.claims.append(claim)
        added = len(self.inv.claims) - before
        dropped = self.inv.usage.claims_dropped
        self.note(
            f"Anchored {added} new claims ({len(self.inv.claims)} in total); "
            f"{dropped} dropped so far because their quote was not found."
        )

    async def _extract_page(self, source: Source) -> list[Claim]:
        refs = {question.ref for question in self.inv.questions}
        text = self.store.text(source.text_sha256) or ""
        found: dict[tuple[int, int], Claim] = {}
        for part in chunks(text):
            user = (
                f'Key questions:\n{self._menu()}\n\n<page url="{source.url}" '
                f'title="{source.title or ""}" published="{source.published or ""}">\n'
                f"{part}\n</page>"
            )
            async with self._reading:
                try:
                    out = await self.reader.structured(prompts.EXTRACT, user, prompts.ExtractOut)
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
                found[span] = Claim(
                    ref="",
                    source_ref=source.ref,
                    question_refs=linked,
                    statement=draft.statement.strip(),
                    quote=text[span[0] : span[1]],
                    start=span[0],
                    end=span[1],
                )
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
                    out = await self.reader.structured(
                        prompts.EXTRACT_POSTS, user, prompts.ExtractPostsOut
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

    async def _inventory(self) -> None:
        """Rebuild the list of every item found for each list question, weak sources included."""
        for question in self.inv.questions:
            if question.kind != "list":
                continue
            claims = [c for c in self.inv.claims if question.ref in c.question_refs][:80]
            if not claims:
                continue
            user = f"List-type key question {question.ref}: {question.text}\n\nClaims:\n"
            user += "\n".join(self._claim_line(claim) for claim in claims)
            try:
                out = await self.tools.model.structured(
                    prompts.INVENTORY, user, prompts.InventoryOut
                )
            except QuotaError:
                raise
            except ModelError as error:
                self.note(f"Could not update the list for {question.ref}: {error}")
                continue
            items = self._items(question, claims, out)
            self.inv.items = [i for i in self.inv.items if i.question_ref != question.ref] + items
            corroborated = sum(item.status == "corroborated" for item in items)
            self.note(
                f"{question.ref}: {len(items)} items found so far ({corroborated} corroborated, "
                f"{len(items) - corroborated} from a single source)."
            )

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
                    claim_refs=refs,
                    origins=origins,
                    best_grade=assessment.best_grade(source.reliability for source in known),
                    status=assessment.item_status(len(origins)),
                )
            )
        return sorted(items, key=lambda item: (-len(item.origins), item.name.casefold()))

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
            out = await self.tools.model.structured(prompts.ASSESS, user, prompts.AssessOut)
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
        for claim in claims:
            if claim.ref in supporting or claim.ref in contradicting:
                claim.credibility = assessment.credibility(
                    len(domains), bool(contradicting), claim.ref in supporting
                )
        return Finding(
            question_ref=question.ref,
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
        draft = await self.tools.model.structured(prompts.WRITE, user, prompts.ReportOut)
        report: Report = verify(draft, self.inv)
        self.inv.report = report
        self.note(f"Checked every sentence: kept the cited ones, removed {len(report.removed)}.")
