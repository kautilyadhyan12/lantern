"""Tools for checking a claim: what established fact-checkers have published about it, and
the earliest saved copy of a link.

Fact-checker results are search hits like any other: transient, and evidence only once
Lantern reads and saves the page. The sites are listed in `assessment.FACT_CHECKERS`.

The earliest copy is a record from the Wayback Machine: an archive capture shows that a link
existed no later than that day, never when it was first published (03 §8.7).
"""

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import ClassVar

from pydantic import BaseModel

from lantern.archive import Archive, First
from lantern.assessment import FACT_CHECKERS, fact_checker, registrable_domain
from lantern.capture import extract
from lantern.egress import FetchError, Page
from lantern.search import Searcher, SearchError
from lantern.sites import post_lead, readable
from lantern.tools.adapters.web import QueryArgs, UrlArgs
from lantern.tools.base import SourceDraft, ToolContext, ToolError, ToolKind, ToolResult

ARCHIVE_GRADE = ("A", "Archive capture: the link existed no later than this date")
ARCHIVE_ORIGIN = "wayback:archive.org"


def _day(when: datetime) -> str:
    return f"{when.day} {when:%B %Y}"


class FactChecks:
    name: ClassVar[str] = "fact_checks"
    description: ClassVar[str] = (
        "Search the published articles of established fact-checkers (Alt News, BOOM, Factly, "
        "AFP Fact Check, Snopes, PolitiFact, Full Fact and others) for the claim or a close "
        "variant. Optional after and before dates (YYYY-MM-DD). Results are leads to read, "
        "not evidence."
    )
    args_model: ClassVar[type[BaseModel]] = QueryArgs
    kind: ClassVar[ToolKind] = "search"
    rate_key: ClassVar[str] = "tavily"
    min_interval: ClassVar[float] = 0.0

    def __init__(self, searcher: Searcher, limit: int) -> None:
        self._searcher, self._limit = searcher, limit

    async def run(self, args: QueryArgs, _ctx: ToolContext) -> ToolResult:
        try:
            hits = await self._searcher.search(
                args.query, self._limit, domains=list(FACT_CHECKERS), **args.dates()
            )
        except SearchError as error:
            raise ToolError(str(error)) from error
        hits = [hit for hit in hits if fact_checker(hit.url)]
        summary = f"Searched fact-checkers: “{args.query}” ({len(hits)} results)."
        return ToolResult(hits, [], summary)


class EarliestCopy:
    name: ClassVar[str] = "earliest_copy"
    description: ClassVar[str] = (
        "Find the Wayback Machine's earliest saved copy of a link already in the case file "
        "(a page, or a post on X, Facebook and similar sites). It shows the link existed no "
        "later than that day, which tests whether material is older than claimed. For posts, "
        "only the date is read."
    )
    args_model: ClassVar[type[BaseModel]] = UrlArgs
    kind: ClassVar[ToolKind] = "read"
    rate_key: ClassVar[str] = "wayback"
    min_interval: ClassVar[float] = 1.0

    def __init__(self, archive: Archive, clock: Callable[[], datetime] | None = None) -> None:
        self._archive = archive
        self._clock = clock or (lambda: datetime.now(UTC))

    async def run(self, args: UrlArgs, ctx: ToolContext) -> ToolResult:
        domain = registrable_domain(args.url)
        read = readable(args.url) and domain not in ctx.robots_no
        try:
            first = await self._archive.first(args.url, read=read)
        except FetchError as error:
            raise ToolError(f"The Wayback Machine's index could not be checked: {error}") from error
        if first is None:
            checked = f"{self._clock():%Y-%m-%d}"
            return ToolResult(
                [],
                [],
                f"The Wayback Machine had no saved copy of this link when Lantern checked on "
                f"{checked}. That says nothing about when it was first published.",
            )
        drafts = [self._record(first)]
        if first.page is not None and (page := await self._page(first, first.page)):
            drafts.append(page)
        summary = f"Wayback Machine: the earliest saved copy is from {_day(first.archived_at)}."
        return ToolResult([], drafts, summary)

    @staticmethod
    def _record(first: First) -> SourceDraft:
        platform = post_lead(first.url)
        what = f"this {platform} post" if platform else first.url
        statement = (
            f"The Wayback Machine's earliest saved copy of {what} is from "
            f"{_day(first.archived_at)}, {first.archived_at:%H:%M} UTC."
        )
        caveat = (
            "An archive capture shows that the link existed no later than this time. It does "
            "not show when the material was first published."
        )
        kept = {"archive_url": first.archive_url, "captured": first.archived_at.isoformat()}
        shown = f"a post on {platform}" if platform else registrable_domain(first.url)
        return SourceDraft(
            url=first.archive_url,
            title=f"Wayback Machine: earliest copy of {shown}",
            published=first.archived_at.date().isoformat(),
            body=json.dumps(kept, sort_keys=True).encode(),
            text=f"{statement}\n{caveat}",
            kind="record",
            origin=ARCHIVE_ORIGIN,
            record_claims=(statement,),
            grade=ARCHIVE_GRADE,
        )

    @staticmethod
    async def _page(first: First, page: Page) -> SourceDraft | None:
        extracted = await asyncio.to_thread(extract, page)
        if extracted is None:
            return None
        return SourceDraft(
            url=first.url,
            title=extracted.title,
            published=extracted.published,
            body=page.body,
            text=extracted.text,
            kind="page",
            origin=registrable_domain(first.url),
            archive_url=first.raw_url,
            archived_at=first.archived_at,
        )
