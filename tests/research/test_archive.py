"""Wayback Machine copies stand in for pages that refused Lantern, never for robots.txt "no"."""

import asyncio
import json
import socket
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from lantern import egress
from lantern.archive import Copy, Wayback
from lantern.config import AppSettings
from lantern.egress import Fetcher, FetchError, Page
from lantern.models import Investigation
from lantern.pipeline import Investigator, Limits, Tools
from lantern.report import to_markdown
from lantern.store import Store
from lantern.web.app import create_app

from . import fakes
from .fakes import FakeModel, FakeSearch

ARTICLE = "https://apnews.com/floods"


def wayback(routes):
    seen = []

    def handler(request):
        seen.append(request)
        key = (request.headers["host"], request.url.path)
        status, headers, body = routes.get(key, (404, {}, b""))
        return httpx.Response(status, headers=headers, content=body)

    async def resolver(host, port):
        return ["93.184.215.14"]

    fetcher = Fetcher(
        "TestBot/1.0", transport=httpx.MockTransport(handler), resolver=resolver, host_interval=0
    )
    return Wayback(fetcher), seen


def available(stamp="20260515032128", status="200", ok=True):
    snapshot = {"available": ok, "status": status, "timestamp": stamp, "url": "http://x"}
    body = json.dumps({"archived_snapshots": {"closest": snapshot}}).encode()
    return (200, {"content-type": "application/json"}, body)


async def test_the_latest_copy_is_fetched_as_originally_served():
    raw = f"/web/20260515032128id_/{ARTICLE}"
    archive, seen = wayback(
        {
            ("archive.org", "/wayback/available"): available(),
            ("web.archive.org", raw): (200, {"content-type": "text/html"}, b"<html>copy</html>"),
        }
    )
    copy = await archive.copy(ARTICLE)
    assert copy is not None
    assert copy.archive_url == f"https://web.archive.org{raw}"
    assert copy.archived_at == datetime(2026, 5, 15, 3, 21, 28, tzinfo=UTC)
    assert copy.page.body == b"<html>copy</html>"
    lookup = next(r for r in seen if r.url.path == "/wayback/available")
    assert lookup.url.query.decode() == "url=https%3A%2F%2Fapnews.com%2Ffloods"
    assert all(r.headers["user-agent"] == "TestBot/1.0" for r in seen)


@pytest.mark.parametrize(
    "lookup",
    [
        available(ok=False),
        available(status="404"),
        available(stamp="not-a-stamp"),
        (200, {"content-type": "application/json"}, b"not json"),
        (503, {}, b""),
    ],
)
async def test_no_usable_copy_means_none(lookup):
    archive, _ = wayback({("archive.org", "/wayback/available"): lookup})
    assert await archive.copy(ARTICLE) is None


async def test_fetch_errors_say_what_kind_of_failure_they_are():
    def handler(request):
        if request.url.path == "/robots.txt":
            body = b"User-agent: *\nDisallow: /private\n"
            return httpx.Response(200, content=body)
        if request.url.path == "/slow":
            raise httpx.ConnectTimeout("slow")
        return httpx.Response(403)

    async def resolver(host, port):
        return ["93.184.215.14"]

    fetcher = Fetcher(
        "TestBot/1.0", transport=httpx.MockTransport(handler), resolver=resolver, host_interval=0
    )
    for path, kind in [("/blocked", "refused"), ("/private/x", "robots"), ("/slow", "unreachable")]:
        with pytest.raises(FetchError) as caught:
            await fetcher.fetch(f"https://example.com{path}")
        assert caught.value.kind == kind


class Failing(fakes.FakeFetcher):
    """apnews.com refuses (403); reuters.com's robots.txt says no."""

    def __init__(self):
        self.urls = []

    async def fetch(self, url):
        self.urls.append(url)
        if "apnews.com" in url:
            raise FetchError("The page returned HTTP 403.", "refused")
        if "reuters.com" in url:
            raise FetchError("The site's robots.txt does not allow automated reading.", "robots")
        return await super().fetch(url)


class FakeArchive:
    def __init__(self, has_copy=True):
        self.has_copy = has_copy
        self.asked = []

    async def copy(self, url):
        self.asked.append(url)
        if not self.has_copy:
            return None
        page = Page(
            url=f"https://web.archive.org/web/20260515032128id_/{url}",
            content_type="text/html",
            body=fakes.html(fakes.PAGES[url]),
        )
        stamp = datetime(2026, 5, 15, tzinfo=UTC)
        return Copy(page=page, archive_url=page.url, archived_at=stamp)


def investigate(tmp_path, archive, searcher=None):
    store = Store(tmp_path)
    fetcher = Failing()
    tools = Tools(
        model=FakeModel(), searcher=searcher or FakeSearch(), fetcher=fetcher, archive=archive
    )
    inv = Investigation(id=store.new_id(), brief="What happened in the district floods?")
    return Investigator(inv, tools, store, Limits()).run(), fetcher


async def test_a_refused_page_is_read_from_its_archived_copy(tmp_path):
    archive = FakeArchive()
    run, _ = investigate(tmp_path, archive)
    inv = await run
    assert inv.status == "done", inv.error
    copy = next(source for source in inv.sources if source.archive_url)
    assert copy.url == ARTICLE  # cited as the original page
    assert copy.domain == "apnews.com"
    assert copy.reliability == "B"  # graded as the original outlet
    assert "Wayback Machine" in copy.reliability_reason
    assert inv.usage.archived == 1
    assert any("Read the Wayback Machine copy from 15 May 2026" in s.message for s in inv.steps)


async def test_robots_txt_no_is_never_worked_around(tmp_path):
    archive = FakeArchive()
    run, _ = investigate(tmp_path, archive)
    inv = await run
    assert not any("reuters.com" in url for url in archive.asked)
    assert "reuters.com" not in [source.domain for source in inv.sources]
    lead = next(lead for lead in inv.leads if lead.platform == "reuters.com")
    assert "robots.txt" in lead.reason


async def test_without_a_copy_the_page_stays_a_lead(tmp_path):
    run, _ = investigate(tmp_path, FakeArchive(has_copy=False))
    inv = await run
    lead = next(lead for lead in inv.leads if lead.platform == "apnews.com")
    assert lead.reason.endswith("No archived copy was found.")


async def test_a_site_that_refused_goes_straight_to_the_archive(tmp_path, monkeypatch):
    second = "https://apnews.com/second"
    monkeypatch.setattr(fakes, "PAGES", {**fakes.PAGES, second: fakes.PAGES[ARTICLE]})

    class TwoRounds(FakeSearch):
        calls = 0

        async def search(self, query, limit, domains=None, *, news=False, time_range=None):
            if domains:
                return []
            urls = [ARTICLE] if TwoRounds.calls == 0 else [second]
            TwoRounds.calls += 1
            return [fakes.Hit(url=u, title="t", rank=1) for u in urls]

    store = Store(tmp_path)
    fetcher, archive = Failing(), FakeArchive()
    model = FakeModel(followups=[["second apnews page"]])
    tools = Tools(model=model, searcher=TwoRounds(), fetcher=fetcher, archive=archive)
    inv = Investigation(id=store.new_id(), brief="What happened in the district floods?")
    inv = await Investigator(inv, tools, store, Limits.for_depth("deep")).run()
    assert [url for url in fetcher.urls if "apnews.com" in url] == [ARTICLE]
    assert archive.asked == [ARTICLE, second]


async def test_archived_copies_are_labelled_in_the_report(tmp_path):
    run, _ = investigate(tmp_path, FakeArchive())
    inv = await run
    settings = AppSettings(data_dir=str(tmp_path), tavily_api_key="t", groq_api_key="g")
    page = TestClient(create_app(settings)).get(f"/investigations/{inv.id}").text
    assert "archived copy" in page
    assert "Wayback copy, 15 May 2026" in page
    assert "Wayback Machine copy" in to_markdown(inv)


async def test_the_capture_index_is_asked_when_the_quick_service_says_none():
    original = f"{ARTICLE}/"
    rows = [["timestamp", "original"], ["20260322073003", original]]
    raw = f"/web/20260322073003id_/{original}"
    archive, seen = wayback(
        {
            ("archive.org", "/wayback/available"): available(ok=False),
            ("web.archive.org", "/cdx/search/cdx"): (
                200,
                {"content-type": "application/json"},
                json.dumps(rows).encode(),
            ),
            ("web.archive.org", raw): (200, {"content-type": "text/html"}, b"<html>copy</html>"),
        }
    )
    copy = await archive.copy(ARTICLE)
    assert copy is not None
    assert copy.archive_url == f"https://web.archive.org{raw}"
    cdx = next(r for r in seen if r.url.path == "/cdx/search/cdx")
    assert b"filter=statuscode:200" in cdx.url.query


async def test_a_slow_archive_gets_one_retry():
    raw = f"/web/20260515032128id_/{ARTICLE}"
    attempts = []

    def handler(request):
        key = (request.headers["host"], request.url.path)
        if key == ("archive.org", "/wayback/available"):
            body = available()[2]
            return httpx.Response(200, headers={"content-type": "application/json"}, content=body)
        if key == ("web.archive.org", raw):
            attempts.append(1)
            if len(attempts) == 1:
                raise httpx.ConnectTimeout("busy")
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"ok")
        return httpx.Response(404)

    async def resolver(host, port):
        return ["93.184.215.14"]

    fetcher = Fetcher(
        "TestBot/1.0", transport=httpx.MockTransport(handler), resolver=resolver, host_interval=0
    )
    copy = await Wayback(fetcher).copy(ARTICLE)
    assert copy is not None
    assert len(attempts) == 2


async def test_ipv4_addresses_are_tried_first(monkeypatch):
    async def fake_getaddrinfo(host, port, type=0):  # noqa: A002  # mirrors the asyncio name
        return [
            (socket.AF_INET6, 1, 6, "", ("2001:db8::1", port)),
            (socket.AF_INET, 1, 6, "", ("23.222.31.162", port)),
        ]

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
    assert await egress.system_resolver("example.com", 443) == ["23.222.31.162", "2001:db8::1"]
