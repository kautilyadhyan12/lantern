"""Web search. Hits are transient: they pick pages to read and are never stored."""

from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict

import httpx

TimeRange = Literal["day", "week", "month", "year"]


class Window(TypedDict, total=False):
    """A publication date window for one search, as YYYY-MM-DD days."""

    after: str
    before: str


@dataclass(frozen=True)
class Hit:
    """One search result. Kept in memory only, to choose pages; never stored."""

    url: str
    title: str
    rank: int
    snippet: str = ""
    published: str | None = None


class Searcher(Protocol):
    async def search(  # noqa: PLR0913  # keyword-only filters mirror the search options
        self,
        query: str,
        limit: int,
        domains: list[str] | None = None,
        *,
        news: bool = False,
        time_range: TimeRange | None = None,
        after: str | None = None,
        before: str | None = None,
    ) -> list[Hit]: ...


class SearchError(Exception):
    """Search failed; the message says what to do."""


class TavilySearch:
    endpoint = "https://api.tavily.com/search"

    def __init__(self, api_key: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(20.0, connect=5.0),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def search(  # noqa: PLR0913  # keyword-only filters mirror the search options
        self,
        query: str,
        limit: int,
        domains: list[str] | None = None,
        *,
        news: bool = False,
        time_range: TimeRange | None = None,
        after: str | None = None,
        before: str | None = None,
    ) -> list[Hit]:
        """`after` and `before` are YYYY-MM-DD dates (Tavily's `start_date` and `end_date`,
        checked 2026-11-06); Tavily refuses them together with `time_range`."""
        body: dict[str, object] = {"query": query, "max_results": limit, "search_depth": "basic"}
        if domains:
            body["include_domains"] = domains
        if news:
            body["topic"] = "news"
        if time_range:
            body["time_range"] = time_range
        if after:
            body["start_date"] = after
        if before:
            body["end_date"] = before
        try:
            response = await self._client.post(self.endpoint, json=body)
        except httpx.HTTPError as error:
            raise SearchError("Web search could not be reached. Try again later.") from error
        if response.status_code in {401, 403}:
            raise SearchError("Web search rejected the key. Check LANTERN_TAVILY_API_KEY.")
        if response.status_code in {429, 432}:
            raise SearchError("The web search quota is used up. Try again later.")
        if response.status_code != 200:
            raise SearchError(f"Web search failed with HTTP {response.status_code}.")
        results = response.json().get("results") or []
        hits = []
        for rank, item in enumerate(results, start=1):
            url = item.get("url") if isinstance(item, dict) else None
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                published = item.get("published_date")
                hits.append(
                    Hit(
                        url=url,
                        title=str(item.get("title") or ""),
                        rank=rank,
                        snippet=str(item.get("content") or "")[:300],
                        published=str(published) if published else None,
                    )
                )
        return hits[:limit]
