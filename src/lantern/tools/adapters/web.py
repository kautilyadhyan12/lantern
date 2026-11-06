"""Web and news search, links to social media posts, and reading one page.

Search hits are transient: they go back to the current step only. A page is read through
the safe fetcher; when a site refused or could not be reached, its Wayback Machine copy is
read instead, but never when robots.txt says no.
"""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import ClassVar, Protocol, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from lantern.archive import ARCHIVABLE, Archive, Copy
from lantern.assessment import registrable_domain
from lantern.capture import extract
from lantern.egress import FetchError, Page
from lantern.search import Searcher, SearchError, TimeRange, Window
from lantern.sites import POST_LINKS, canonical, post_lead, readable
from lantern.tools.base import (
    SourceDraft,
    ToolArgs,
    ToolContext,
    ToolError,
    ToolKind,
    ToolResult,
)

REFUSALS = ("HTTP 401", "HTTP 403", "HTTP 429", "robots.txt")  # the site said no: stop asking
POST_LINK_RESULTS = 10


class PageFetcher(Protocol):
    async def fetch(self, url: str) -> Page: ...


class QueryArgs(ToolArgs):
    query: str = Field(min_length=1, max_length=500)
    after: date | None = None  # only results published on or after this day
    before: date | None = None  # only results published on or before this day

    @model_validator(mode="after")
    def _in_order(self) -> Self:
        if self.after and self.before and self.after > self.before:
            msg = "after must be a day on or before before"
            raise ValueError(msg)
        return self

    def dates(self) -> Window:
        """The date window as search options; empty when none was given."""
        window = Window()
        if self.after:
            window["after"] = self.after.isoformat()
        if self.before:
            window["before"] = self.before.isoformat()
        return window


class NewsArgs(QueryArgs):
    time_range: TimeRange | None = None

    @model_validator(mode="after")
    def _one_window(self) -> Self:
        if self.time_range and (self.after or self.before):
            msg = "give either time_range or the after and before dates, not both"
            raise ValueError(msg)
        return self


class PhraseArgs(ToolArgs):
    phrase: str = Field(min_length=1, max_length=500)


class UrlArgs(ToolArgs):
    url: str = Field(max_length=2000)

    @field_validator("url")
    @classmethod
    def _web_link(cls, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            msg = "must be an http or https link"
            raise ValueError(msg)
        return canonical(url)


@contextmanager
def _search_errors() -> Iterator[None]:
    """A failed search becomes a tool failure with the search's own plain message."""
    try:
        yield
    except SearchError as error:
        raise ToolError(str(error)) from error


def _window(args: QueryArgs) -> str:
    """The date window of a search in words, for the log: " (before 2024-08-01)"."""
    parts = [f"{name} {day}" for name, day in args.dates().items()]
    return f" ({' and '.join(parts)})" if parts else ""


class WebSearch:
    name: ClassVar[str] = "web_search"
    description: ClassVar[str] = (
        "Search the web for background, official pages and lists. Optional after and before "
        "dates (YYYY-MM-DD) keep only results published in that window. Results are leads to "
        "read, not evidence."
    )
    args_model: ClassVar[type[BaseModel]] = QueryArgs
    kind: ClassVar[ToolKind] = "search"
    rate_key: ClassVar[str] = "tavily"
    min_interval: ClassVar[float] = 0.0

    def __init__(self, searcher: Searcher, limit: int) -> None:
        self._searcher, self._limit = searcher, limit

    async def run(self, args: QueryArgs, _ctx: ToolContext) -> ToolResult:
        with _search_errors():
            hits = await self._searcher.search(args.query, self._limit, **args.dates())
        summary = f"Searched the web: “{args.query}”{_window(args)} ({len(hits)} results)."
        return ToolResult(hits, [], summary)


class NewsSearch:
    name: ClassVar[str] = "news_search"
    description: ClassVar[str] = (
        "Search news reports, optionally within the past day, week, month or year, or between "
        "after and before dates (YYYY-MM-DD). Results are leads to read, not evidence."
    )
    args_model: ClassVar[type[BaseModel]] = NewsArgs
    kind: ClassVar[ToolKind] = "search"
    rate_key: ClassVar[str] = "tavily"
    min_interval: ClassVar[float] = 0.0

    def __init__(self, searcher: Searcher, limit: int) -> None:
        self._searcher, self._limit = searcher, limit

    async def run(self, args: NewsArgs, _ctx: ToolContext) -> ToolResult:
        with _search_errors():
            hits = await self._searcher.search(
                args.query, self._limit, news=True, time_range=args.time_range, **args.dates()
            )
        summary = f"Searched the news: “{args.query}”{_window(args)} ({len(hits)} results)."
        return ToolResult(hits, [], summary)


class PostLinks:
    name: ClassVar[str] = "post_links"
    description: ClassVar[str] = (
        "Find links to single public posts on X, Facebook, Instagram, Reddit and similar sites. "
        "Lantern never opens them: they are listed as leads for a person to check."
    )
    args_model: ClassVar[type[BaseModel]] = PhraseArgs
    kind: ClassVar[ToolKind] = "search"
    rate_key: ClassVar[str] = "tavily"
    min_interval: ClassVar[float] = 0.0

    def __init__(self, searcher: Searcher) -> None:
        self._searcher = searcher

    async def run(self, args: PhraseArgs, _ctx: ToolContext) -> ToolResult:
        with _search_errors():
            found = await self._searcher.search(
                args.phrase, POST_LINK_RESULTS, domains=sorted(POST_LINKS)
            )
        posts = [hit for hit in found if post_lead(canonical(hit.url))]
        summary = (
            "Searched X, Facebook, Instagram, Reddit and others for posts about "
            f"“{args.phrase}”: {len(posts)} post links."
        )
        return ToolResult(posts, [], summary)


class ReadPage:
    name: ClassVar[str] = "read_page"
    description: ClassVar[str] = (
        "Read and save one page whose link came from a search or a saved page. A site that "
        "refused is read from its Wayback Machine copy, never when its robots.txt says no."
    )
    args_model: ClassVar[type[BaseModel]] = UrlArgs
    kind: ClassVar[ToolKind] = "read"
    rate_key: ClassVar[str] = "per-host"  # the safe fetcher paces each host itself
    min_interval: ClassVar[float] = 0.0

    def __init__(self, fetcher: PageFetcher, archive: Archive | None) -> None:
        self._fetcher, self._archive = fetcher, archive

    async def run(self, args: UrlArgs, ctx: ToolContext) -> ToolResult:
        domain = registrable_domain(args.url)
        if not readable(args.url):
            msg = f"Lantern does not read {domain}: its terms forbid it, or it has no text."
            raise ToolError(msg)
        try:
            page, copy, note = await self._read(args.url, domain, ctx)
        except FetchError as error:
            raise ToolError(str(error)) from error
        extracted = await asyncio.to_thread(extract, page)
        if extracted is None:
            raise ToolError("Lantern found no readable text on the page.")
        # An archived copy is cited as the original page, read through the archive.
        original = args.url if copy else page.url
        draft = SourceDraft(
            url=original,
            title=extracted.title,
            published=extracted.published,
            body=page.body,
            text=extracted.text,
            kind="page",
            origin=registrable_domain(original),
            archive_url=copy.archive_url if copy else None,
            archived_at=copy.archived_at if copy else None,
        )
        return ToolResult([], [draft], note or f"Read {registrable_domain(original)}.")

    async def _read(self, url: str, domain: str, ctx: ToolContext) -> tuple[Page, Copy | None, str]:
        """The page itself, or its Wayback Machine copy when the site refused or could not
        be reached, with a note saying so. Never an archive copy when robots.txt said no."""
        archive = self._archive
        if domain in ctx.refusing and archive is not None:
            copy = await archive.copy(url)
            if copy is None:
                msg = "The site refused Lantern earlier in this run; no archived copy was found."
                raise FetchError(msg, "refused")
            when = f"{copy.archived_at:%d %b %Y}"
            return copy.page, copy, f"{domain}: read the Wayback Machine copy from {when}."
        try:
            return await self._fetcher.fetch(url), None, ""
        except FetchError as error:
            if error.kind == "robots":
                ctx.robots_no.add(domain)
            if any(sign in str(error) for sign in REFUSALS):
                ctx.refusing.add(domain)
            if archive is None or error.kind not in ARCHIVABLE:
                raise
            copy = await archive.copy(url)
            if copy is None:
                raise FetchError(f"{error} No archived copy was found.", error.kind) from error
            when = f"{copy.archived_at:%d %b %Y}"
            note = f"{domain}: {error} Read the Wayback Machine copy from {when} instead."
            return copy.page, copy, note
