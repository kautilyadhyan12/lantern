"""Web search. Hits are transient: they pick pages to read and are never stored."""

from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class Hit:
    url: str
    title: str
    rank: int


class Searcher(Protocol):
    async def search(self, query: str, limit: int) -> list[Hit]: ...


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

    async def search(self, query: str, limit: int) -> list[Hit]:
        body = {"query": query, "max_results": limit, "search_depth": "basic"}
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
                hits.append(Hit(url=url, title=str(item.get("title") or ""), rank=rank))
        return hits[:limit]
