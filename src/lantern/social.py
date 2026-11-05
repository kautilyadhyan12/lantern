"""Public social media posts as ground reports: Mastodon hashtags and Bluesky search.

Only event-centred searches, never an account's timeline. Posts whose authors opted out
of discovery, or that carry opt-out or adult-content labels, are skipped. Author
identity is never stored: each account becomes an opaque origin used only to count
independent reports.
"""

import hashlib
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import quote

import httpx

SKIP_LABELS = {"!no-unauthenticated", "porn", "sexual", "nudity", "graphic-media", "gore"}
MIN_TEXT = 40


@dataclass(frozen=True)
class Post:
    platform: str
    url: str
    origin: str
    posted_at: str
    language: str | None
    text: str


class SocialSearch(Protocol):
    async def hashtag(self, tag: str, limit: int) -> list[Post]: ...

    async def search(self, query: str, limit: int) -> list[Post]: ...


def origin(platform: str, account: str) -> str:
    """An opaque, stable id for an account; the account itself is not kept."""
    digest = hashlib.sha256(f"{platform}:{account}".encode()).hexdigest()[:12]
    return f"{platform}:{digest}"


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "p":
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(markup: str) -> str:
    parser = _Text()
    parser.feed(markup)
    parser.close()
    return "".join(parser.parts).strip()


class PublicSocial:
    """Mastodon public hashtag timelines and Bluesky public post search; no accounts."""

    def __init__(
        self,
        user_agent: str,
        mastodon: str = "https://mastodon.social",
        bluesky: str = "https://api.bsky.app",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._mastodon = mastodon.rstrip("/")
        self._bluesky = bluesky.rstrip("/")
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(15.0, connect=5.0),
            headers={"User-Agent": user_agent, "Accept": "application/json"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, url: str, params: dict[str, str]) -> Any:
        try:
            response = await self._client.get(url, params=params)
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    async def hashtag(self, tag: str, limit: int) -> list[Post]:
        tag = "".join(ch for ch in tag.lstrip("#") if ch.isalnum() or ch == "_")
        if not tag:
            return []
        url = f"{self._mastodon}/api/v1/timelines/tag/{quote(tag)}"
        data = await self._get(url, {"limit": str(min(limit, 40))})
        posts = []
        for item in data if isinstance(data, list) else []:
            account = item.get("account") or {}
            if item.get("reblog") or item.get("visibility") != "public":
                continue
            if account.get("discoverable") is False or account.get("noindex") is True:
                continue
            text = html_to_text(str(item.get("content") or ""))
            if item.get("spoiler_text"):
                text = f"{item['spoiler_text']}\n\n{text}"
            if len(text) < MIN_TEXT or not item.get("url"):
                continue
            posts.append(
                Post(
                    platform="mastodon",
                    url=str(item["url"]),
                    origin=origin("mastodon", str(account.get("url") or account.get("acct"))),
                    posted_at=str(item.get("created_at") or ""),
                    language=item.get("language"),
                    text=text,
                )
            )
        return posts

    async def search(self, query: str, limit: int) -> list[Post]:
        url = f"{self._bluesky}/xrpc/app.bsky.feed.searchPosts"
        data = await self._get(url, {"q": query, "limit": str(min(limit, 50)), "sort": "top"})
        posts = []
        for item in (data or {}).get("posts") or [] if isinstance(data, dict) else []:
            author = item.get("author") or {}
            labels = {label.get("val") for label in author.get("labels") or []}
            labels |= {label.get("val") for label in item.get("labels") or []}
            record = item.get("record") or {}
            text = str(record.get("text") or "").strip()
            did = str(author.get("did") or "")
            rkey = str(item.get("uri") or "").rsplit("/", 1)[-1]
            if labels & SKIP_LABELS or len(text) < MIN_TEXT or not did or not rkey:
                continue
            langs = record.get("langs") or []
            posts.append(
                Post(
                    platform="bluesky",
                    url=f"https://bsky.app/profile/{did}/post/{rkey}",
                    origin=origin("bluesky", did),
                    posted_at=str(record.get("createdAt") or ""),
                    language=langs[0] if langs else None,
                    text=text,
                )
            )
        return posts
