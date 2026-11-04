"""The investigation: safety check → key questions → search → fetch → claims → findings → report."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

from lantern import assessment, prompts
from lantern.capture import extract
from lantern.egress import FetchError, Page
from lantern.llm import Model, ModelError
from lantern.models import Claim, Finding, Investigation, Question, Report, Source, now
from lantern.report import verify
from lantern.safety import check_brief
from lantern.search import Searcher, SearchError
from lantern.store import Store
from lantern.text import chunks, find_quote

log = logging.getLogger(__name__)

# Sites whose terms forbid automated reading, or which need an account.
SKIP_DOMAINS = {
    "x.com",
    "twitter.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "tiktok.com",
    "reddit.com",
    "threads.net",
    "t.me",
    "telegram.org",
    "pinterest.com",
}


class PageFetcher(Protocol):
    async def fetch(self, url: str) -> Page: ...


@dataclass
class Limits:
    max_questions: int = 4
    max_pages: int = 10
    queries_per_question: int = 2
    results_per_query: int = 5
    claims_per_question: int = 30


@dataclass
class Tools:
    model: Model
    searcher: Searcher
    fetcher: PageFetcher


def canonical(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme, (parts.hostname or "").lower(), path, parts.query, ""))


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
        self.store = store
        self.limits = limits
        self.on_change = on_change
        self._queries: dict[str, list[str]] = {}

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
                urls = await self._search()
                await self._fetch(urls)
                await self._extract()
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
        self.note("Planning key questions.")
        count = f"2 to {self.limits.max_questions}"
        plan = await self.tools.model.structured(
            prompts.PLAN.format(count=count),
            f"Research question: {self.inv.brief}",
            prompts.PlanOut,
        )
        for number, item in enumerate(plan.questions[: self.limits.max_questions], start=1):
            question = Question(ref=f"Q{number}", text=item.text.strip())
            self.inv.questions.append(question)
            self._queries[question.ref] = [q.strip() for q in item.queries if q.strip()][
                : self.limits.queries_per_question
            ]
        self.note(f"Planned {len(self.inv.questions)} key questions.")

    async def _search(self) -> list[tuple[str, set[str]]]:
        queues: dict[str, list[str]] = {}
        wanted: dict[str, set[str]] = {}
        for question in self.inv.questions:
            queue = queues.setdefault(question.ref, [])
            for query in self._queries.get(question.ref) or [question.text]:
                hits = await self.tools.searcher.search(query, self.limits.results_per_query)
                self.inv.usage.searches += 1
                self.note(f"{question.ref}: searched “{query}” ({len(hits)} results).")
                for hit in hits:
                    url = canonical(hit.url)
                    if assessment.registrable_domain(url) in SKIP_DOMAINS:
                        continue
                    wanted.setdefault(url, set()).add(question.ref)
                    if url not in queue:
                        queue.append(url)
        chosen: list[str] = []
        while len(chosen) < self.limits.max_pages and any(queues.values()):
            for queue in queues.values():
                while queue and queue[0] in chosen:
                    queue.pop(0)
                if queue and len(chosen) < self.limits.max_pages:
                    chosen.append(queue.pop(0))
        return [(url, wanted[url]) for url in chosen]

    async def _fetch(self, urls: list[tuple[str, set[str]]]) -> None:
        self.note(f"Reading {len(urls)} pages.")
        limit = asyncio.Semaphore(4)

        async def one(url: str) -> tuple[Page, str, str | None, str | None] | None:
            domain = assessment.registrable_domain(url)
            async with limit:
                try:
                    page = await self.tools.fetcher.fetch(url)
                except FetchError as error:
                    self.inv.usage.pages_skipped += 1
                    self.note(f"Skipped {domain}: {error}")
                    return None
            extracted = await asyncio.to_thread(extract, page)
            if extracted is None:
                self.inv.usage.pages_skipped += 1
                self.note(f"Skipped {domain}: no readable text.")
                return None
            return page, extracted.text, extracted.title, extracted.published

        results = await asyncio.gather(*(one(url) for url, _ in urls))
        for (_, refs), result in zip(urls, results, strict=True):
            if result is None:
                continue
            page, text, title, published = result
            grade, why = assessment.rate_source(page.url)
            source = Source(
                ref=f"S{len(self.inv.sources) + 1}",
                url=page.url,
                domain=assessment.registrable_domain(page.url),
                title=title,
                published=published,
                fetched_at=now(),
                sha256=self.store.put_blob(page.body),
                text_sha256=self.store.put_text(text),
                size=len(page.body),
                reliability=grade,
                reliability_reason=why,
                question_refs=sorted(refs),
            )
            self.inv.sources.append(source)
            self.inv.usage.pages_fetched += 1
        self.note(f"Saved {len(self.inv.sources)} pages with their sha256 fingerprints.")

    async def _extract(self) -> None:
        self.note("Pulling out claims with exact quotes.")
        refs = {question.ref for question in self.inv.questions}
        menu = "\n".join(f"{q.ref}: {q.text}" for q in self.inv.questions)
        limit = asyncio.Semaphore(2)

        async def one(source: Source) -> list[Claim]:
            text = self.store.text(source.text_sha256) or ""
            found: dict[tuple[int, int], Claim] = {}
            for part in chunks(text):
                user = (
                    f'Key questions:\n{menu}\n\n<page url="{source.url}" '
                    f'title="{source.title or ""}">\n{part}\n</page>'
                )
                async with limit:
                    try:
                        out = await self.tools.model.structured(
                            prompts.EXTRACT, user, prompts.ExtractOut
                        )
                    except ModelError as error:
                        self.note(f"Could not read claims from {source.ref}: {error}")
                        return list(found.values())
                for draft in out.claims[:8]:
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

        results = await asyncio.gather(*(one(source) for source in self.inv.sources))
        for claims in results:
            for claim in claims:
                claim.ref = f"C{len(self.inv.claims) + 1}"
                self.inv.claims.append(claim)
        dropped = self.inv.usage.claims_dropped
        self.note(
            f"Anchored {len(self.inv.claims)} claims; dropped {dropped} without exact quotes."
        )

    async def _assess(self) -> None:
        for question in self.inv.questions:
            self.note(f"Assessing {question.ref}.")
            claims = [c for c in self.inv.claims if question.ref in c.question_refs]
            claims = claims[: self.limits.claims_per_question]
            finding = await self._assess_one(question, claims)
            question.status = finding.status
            self.inv.findings.append(finding)

    async def _assess_one(self, question: Question, claims: list[Claim]) -> Finding:
        if not claims:
            return Finding(
                question_ref=question.ref,
                status="unanswerable",
                answer="No usable evidence was found in the pages read.",
            )
        lines = []
        for claim in claims:
            source = self.inv.source(claim.source_ref)
            where = f"{source.domain}, grade {source.reliability}" if source else ""
            lines.append(
                f"{claim.ref} [{claim.source_ref} {where}]: {claim.statement} "
                f"Quote: “{claim.quote}”"
            )
        user = f"Key question {question.ref}: {question.text}\n\nClaims:\n" + "\n".join(lines)
        try:
            out = await self.tools.model.structured(prompts.ASSESS, user, prompts.AssessOut)
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
        urls = [s.url for s in sources if s]
        domains = assessment.independent_domains(urls)
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
            answer=out.answer,
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
                f"{claims}"
            )
        user = f"Research question: {self.inv.brief}\n\nFindings:\n" + "\n\n".join(parts)
        draft = await self.tools.model.structured(prompts.WRITE, user, prompts.ReportOut)
        report: Report = verify(draft, self.inv)
        self.inv.report = report
        self.note(f"Checked every sentence: kept the cited ones, removed {len(report.removed)}.")
