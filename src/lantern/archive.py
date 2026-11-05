"""Archived copies from the Internet Archive's Wayback Machine, for pages Lantern could not read.

Used only when a site answered with an HTTP error or could not be reached, never when its
robots.txt says no, never for sites whose terms forbid automated reading, and never for
unsafe addresses. The lookups and the copy go through the same safe fetcher as any page.
"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import quote

from lantern.egress import FailureKind, Fetcher, FetchError, Page

ARCHIVABLE: frozenset[FailureKind] = frozenset({"refused", "unreachable"})
AVAILABILITY = "https://archive.org/wayback/available?url="
CDX = (
    "https://web.archive.org/cdx/search/cdx"
    "?output=json&limit=-1&filter=statuscode:200&fl=timestamp,original&url="
)
_TIMESTAMP = re.compile(r"^\d{14}$")


@dataclass(frozen=True)
class Copy:
    page: Page
    archive_url: str
    archived_at: datetime


class Archive(Protocol):
    async def copy(self, url: str) -> Copy | None: ...


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
        page = None
        for _attempt in range(2):  # the archive is often slow; one retry when unreachable
            try:
                page = await self._fetcher.fetch(archive_url)
                break
            except FetchError as error:
                if error.kind != "unreachable":
                    return None
        if page is None:
            return None
        archived_at = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        return Copy(page=page, archive_url=archive_url, archived_at=archived_at)

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
        rows = await self._json(CDX + quote(url, safe=""))
        if not isinstance(rows, list) or len(rows) < 2:
            return None
        last = rows[-1]
        if not isinstance(last, list) or len(last) < 2:
            return None
        stamp, original = str(last[0]), str(last[1])
        if not _TIMESTAMP.match(stamp) or not original.startswith(("http://", "https://")):
            return None
        return stamp, original
