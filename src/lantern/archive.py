"""Archived copies from the Internet Archive's Wayback Machine.

`copy`: the latest copy of a page Lantern could not read. Used only when a site answered
with an HTTP error or could not be reached, never when its robots.txt says no, never for
sites whose terms forbid automated reading, and never for unsafe addresses.

`first`: the earliest capture of a link, which shows it existed no later than that day. For
posts on sites whose terms forbid automated reading, only the capture date is read from the
archive's index; the copy itself is read only when the site's robots.txt allows it.

The lookups and the copies go through the same safe fetcher as any page. Checked
2026-11-06: the CDX index returns the oldest capture first with `limit=1`; posts from
before 2023 are archived under twitter.com, later ones under x.com.
"""

import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import quote

from lantern.assessment import registrable_domain
from lantern.egress import FailureKind, Fetcher, FetchError, Page

ARCHIVABLE: frozenset[FailureKind] = frozenset({"refused", "unreachable"})
AVAILABILITY = "https://archive.org/wayback/available?url="
CDX = (
    "https://web.archive.org/cdx/search/cdx"
    "?output=json&limit=-1&filter=statuscode:200&fl=timestamp,original&url="
)
FIRST = CDX.replace("limit=-1", "limit=1")
SAME_POSTS = {"x.com": "twitter.com", "twitter.com": "x.com"}  # one post, two addresses
_TIMESTAMP = re.compile(r"^\d{14}$")


@dataclass(frozen=True)
class Copy:
    page: Page
    archive_url: str
    archived_at: datetime


@dataclass(frozen=True)
class First:
    """The earliest capture of a link that was served with HTTP 200."""

    url: str  # the link as captured: http or https, twitter.com for an older X post
    archived_at: datetime
    archive_url: str  # the capture as the archive shows it to a person
    page: Page | None = None  # the capture as originally served, when it may be read

    @property
    def raw_url(self) -> str:
        """The capture exactly as originally served, without the archive's toolbar."""
        return f"https://web.archive.org/web/{self.archived_at:%Y%m%d%H%M%S}id_/{self.url}"


class Archive(Protocol):
    async def copy(self, url: str) -> Copy | None: ...

    async def first(self, url: str, *, read: bool) -> First | None: ...


def _stamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=UTC)


def _forms(url: str) -> list[str]:
    """The addresses one link may be archived under: an X post also as a Twitter post."""
    domain = registrable_domain(url)
    if (other := SAME_POSTS.get(domain)) is None:
        return [url]
    scheme, _, rest = url.partition("://")
    host, _, path = rest.partition("/")
    return [url, f"{scheme}://{other}/{path}"] if host.endswith(domain) else [url]


def _capture(rows: Any) -> tuple[str, str] | None:
    """The (timestamp, original) of the one capture row in a CDX answer, if any."""
    if not isinstance(rows, list) or len(rows) < 2 or not isinstance(rows[-1], list):
        return None
    if len(rows[-1]) < 2:
        return None
    stamp, original = str(rows[-1][0]), str(rows[-1][1])
    if not _TIMESTAMP.match(stamp) or not original.startswith(("http://", "https://")):
        return None
    return stamp, original


class Wayback:
    def __init__(self, fetcher: Fetcher) -> None:
        self._fetcher = fetcher

    async def copy(self, url: str) -> Copy | None:
        """The latest archived copy of `url`, as originally served, or None."""
        found = await self._available(url) or await self._indexed(url)
        if found is None:
            return None
        stamp, original = found
        # "id_" asks for the page exactly as captured, without the archive's toolbar.
        archive_url = f"https://web.archive.org/web/{stamp}id_/{original}"
        page = await self._raw(archive_url)
        if page is None:
            return None
        return Copy(page=page, archive_url=archive_url, archived_at=_stamp(stamp))

    async def first(self, url: str, *, read: bool) -> First | None:
        """The earliest capture of `url` (or of the same X post under twitter.com), or None
        when the archive holds none. With `read`, the capture itself is fetched too, as
        originally served, when the site's robots.txt allows Lantern to read the page.
        Raises FetchError when the archive's index cannot be reached."""
        found = []
        for form in _forms(url):
            try:
                answer = await self._fetcher.fetch(
                    FIRST + quote(form, safe=""), ("application/json",)
                )
                rows = json.loads(answer.body)
            except ValueError as error:
                raise FetchError(
                    "The Wayback Machine's index sent an unreadable answer."
                ) from error
            if (capture := _capture(rows)) is not None:
                found.append(capture)
        if not found:
            return None
        stamp, original = min(found)
        first = First(original, _stamp(stamp), f"https://web.archive.org/web/{stamp}/{original}")
        if read and await self._fetcher.allowed(original):
            first = replace(first, page=await self._raw(first.raw_url))
        return first

    async def _raw(self, archive_url: str) -> Page | None:
        """One capture as originally served; the archive is often slow, so one retry."""
        for _attempt in range(2):
            try:
                return await self._fetcher.fetch(archive_url)
            except FetchError as error:
                if error.kind != "unreachable":
                    return None
        return None

    async def _json(self, url: str) -> Any:
        try:
            found = await self._fetcher.fetch(url, accept=("application/json",))
            return json.loads(found.body)
        except (FetchError, ValueError):
            return None

    async def _available(self, url: str) -> tuple[str, str] | None:
        """The quick availability service; it sometimes answers "none" when busy."""
        data = await self._json(AVAILABILITY + quote(url, safe=""))
        if not isinstance(data, dict):
            return None
        closest = (data.get("archived_snapshots") or {}).get("closest") or {}
        stamp = str(closest.get("timestamp") or "")
        if closest.get("available") is True and str(closest.get("status")) == "200":
            return (stamp, url) if _TIMESTAMP.match(stamp) else None
        return None

    async def _indexed(self, url: str) -> tuple[str, str] | None:
        """The CDX capture index: the last capture that was served with HTTP 200."""
        return _capture(await self._json(CDX + quote(url, safe="")))
