"""Posts on never-open sites are listed as leads: never fetched, never evidence, no profiles."""

import pytest
from fastapi.testclient import TestClient

from lantern.config import AppSettings
from lantern.models import Investigation
from lantern.pipeline import Investigator, Limits, Tools, post_lead
from lantern.report import to_markdown
from lantern.store import Store
from lantern.web.app import create_app

from . import fakes
from .fakes import FakeFetcher, FakeModel, FakeSearch


@pytest.mark.parametrize(
    ("url", "platform"),
    [
        ("https://x.com/someone/status/1234567890", "X"),
        ("https://mobile.twitter.com/someone/status/42", "X"),
        ("https://www.facebook.com/somepage/posts/pfbid0abc", "Facebook"),
        ("https://www.instagram.com/p/Cxyz123/", "Instagram"),
        ("https://www.reddit.com/r/assam/comments/abc123/flood/", "Reddit"),
        ("https://t.me/somechannel/1234", "Telegram"),
        ("https://x.com/someone", None),
        ("https://www.facebook.com/some.person", None),
        ("https://www.instagram.com/some.person/", None),
        ("https://www.reddit.com/user/someone", None),
        ("https://t.me/somechannel", None),
        ("https://www.reuters.com/world/x", None),
    ],
)
def test_only_individual_posts_become_leads_never_profiles(url, platform):
    assert post_lead(url) == platform


class Fetched(FakeFetcher):
    def __init__(self):
        self.urls = []

    async def fetch(self, url):
        self.urls.append(url)
        return await super().fetch(url)


async def test_leads_are_listed_not_fetched_and_shown_without_usernames(tmp_path, monkeypatch):
    urls = [
        "https://x.com/reporter/status/111",
        "https://x.com/reporter/status/111",
        "https://x.com/reporter",
        "https://www.facebook.com/townpage/posts/pfbid0abc",
        *fakes.PAGES,
    ]

    async def search(self, query, limit, domains=None):
        if domains:
            return []
        return [fakes.Hit(url=url, title="hit", rank=i) for i, url in enumerate(urls, start=1)]

    monkeypatch.setattr(FakeSearch, "search", search)
    store = Store(tmp_path)
    fetcher = Fetched()
    tools = Tools(model=FakeModel(), searcher=FakeSearch(), fetcher=fetcher)
    inv = Investigation(id=store.new_id(), brief="What happened in the district floods?")
    inv = await Investigator(inv, tools, store, Limits()).run()
    assert inv.status == "done", inv.error
    assert [(lead.platform, lead.url) for lead in inv.leads] == [
        ("X", "https://x.com/reporter/status/111"),
        ("Facebook", "https://www.facebook.com/townpage/posts/pfbid0abc"),
    ]
    assert inv.leads[0].question_refs == ["Q1", "Q2"]
    assert not any("x.com" in url or "facebook.com" in url for url in fetcher.urls)
    assert all(not s.url.startswith(("https://x.com", "https://www.facebook")) for s in inv.sources)
    markdown = to_markdown(inv)
    assert "## Leads to check yourself" in markdown
    assert "reporter" not in markdown
    settings = AppSettings(data_dir=str(tmp_path), tavily_api_key="t", groq_api_key="g")
    page = TestClient(create_app(settings)).get(f"/investigations/{inv.id}").text
    assert "Open on X" in page
    assert "not evidence" in page
    assert ">https://x.com" not in page


async def test_social_sites_are_searched_on_purpose_for_leads(tmp_path):
    store = Store(tmp_path)
    searcher = FakeSearch()
    fetcher = Fetched()
    tools = Tools(model=FakeModel(), searcher=searcher, fetcher=fetcher)
    inv = Investigation(id=store.new_id(), brief="What happened in the district floods?")
    inv = await Investigator(inv, tools, store, Limits()).run()
    assert searcher.domain_calls
    assert {"x.com", "facebook.com", "reddit.com"} <= set(searcher.domain_calls[0])
    assert [lead.url for lead in inv.leads] == ["https://x.com/witness/status/999"]
    assert not any("x.com" in url for url in fetcher.urls)
