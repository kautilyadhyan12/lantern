"""The tool layer: registry and menu, the gateway's checks in order, and the wrapped tools."""

import asyncio
import json
from contextvars import ContextVar
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from lantern.archive import Copy
from lantern.egress import FetchError, Page
from lantern.models import Investigation
from lantern.pipeline import Investigator, Limits, Tools
from lantern.search import Hit, SearchError
from lantern.store import Store
from lantern.tools.adapters.social import SocialPosts
from lantern.tools.adapters.web import NewsArgs, NewsSearch, PostLinks, ReadPage, UrlArgs, WebSearch
from lantern.tools.base import RunBudget, ToolArgs, ToolCall, ToolContext, ToolError, ToolResult
from lantern.tools.gateway import PROVENANCE, ToolGateway
from lantern.tools.registry import Registry, args_schema

from . import fakes
from .fakes import FakeFetcher, FakeModel, FakeSearch, FakeSocial


class QueryArgs(ToolArgs):
    query: str


class FakeTool:
    description = "Find things."

    def __init__(
        self,
        name="find",
        kind="search",
        *,
        args_model=QueryArgs,
        rate_key="fake",
        min_interval=0.0,
        hits=(),
        error=None,
        summary=None,
    ):
        self.name, self.kind, self.args_model = name, kind, args_model
        self.rate_key, self.min_interval = rate_key, min_interval
        self.hits, self.error, self.summary = list(hits), error, summary
        self.runs = []

    async def run(self, args, ctx):
        self.runs.append(args)
        if self.error:
            raise ToolError(self.error)
        hits = [Hit(url=url, title="t", rank=rank) for rank, url in enumerate(self.hits, 1)]
        summary = f"{len(hits)} results." if self.summary is None else self.summary
        return ToolResult(hits=hits, summary=summary)


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.waits = []

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


def gateway(*tools, budget=None, known=(), allowed=None, clock=None):
    lines = []
    clock = clock or FakeClock()
    found = ToolGateway(
        Registry(tools),
        budget or RunBudget(tool_calls=20, searches=10, pages=10, records=10),
        set(known),
        lines.append,
        allowed=allowed,
        clock=clock,
        sleep=clock.sleep,
    )
    return found, lines


def call(tool, **args):
    return ToolCall(tool=tool, args=args, question_ref="Q1", why="testing")


CTX = ToolContext()


# ---- registry -----------------------------------------------------------------------


@pytest.mark.ac("AG1a-AC1")
def test_the_menu_is_built_from_each_tools_args_model():
    news = FakeTool("news", args_model=NewsArgs)
    page = FakeTool("page", kind="read", args_model=UrlArgs)
    registry = Registry([news, page, FakeTool("hidden")])
    budget = RunBudget(tool_calls=9, searches=3, pages=12, records=0)
    assert registry.menu(["news", "page", "missing"], budget).splitlines() == [
        (
            '- news: Find things. Args: {"query":"string","time_range?":["day","week","month",'
            '"year"]}. Calls left: 3.'
        ),
        '- page: Find things. Args: {"url":"string"}. Calls left: 9.',
    ]


@pytest.mark.ac("AG1a-AC1")
def test_the_args_outline_shows_alternatives_and_untyped_fields():
    class Mixed(BaseModel):
        amount: int | str
        anything: object = None

    assert args_schema(Mixed) == '{"amount":["integer","string"],"anything?":"any"}'


@pytest.mark.ac("AG1a-AC1")
def test_tool_names_must_be_unique():
    registry = Registry([FakeTool("find")])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeTool("find"))
    assert registry.names() == ["find"]
    assert registry.get("find") is not None
    assert registry.get("other") is None


# ---- gateway checks, in order -------------------------------------------------------


@pytest.mark.ac("AG1a-AC2")
async def test_unknown_and_disallowed_tools_are_refused_before_running():
    find, other = FakeTool("find"), FakeTool("other")
    gate, lines = gateway(find, other, allowed=["find"])
    for name in ("teleport", "other"):
        outcome = await gate.run(call(name, query="x"), CTX)
        assert outcome.status == "refused"
        assert outcome.reason == f"There is no tool called {name} in this run. Use one of: find."
    assert find.runs == other.runs == []
    assert lines[0] == (
        "teleport “x”: not run. There is no tool called teleport in this run. Use one of: find."
    )


@pytest.mark.ac("AG1a-AC2")
async def test_invalid_arguments_are_refused_with_the_validation_error():
    find = FakeTool("find")
    gate, _ = gateway(find)
    missing = await gate.run(call("find"), CTX)
    extra = await gate.run(call("find", query="x", colour="blue"), CTX)
    assert missing.status == extra.status == "refused"
    assert missing.reason == "The arguments are not valid: query: Field required."
    assert extra.reason == "The arguments are not valid: colour: Extra inputs are not permitted."
    assert find.runs == []


@pytest.mark.ac("AG1a-AC2")
async def test_a_repeated_call_returns_the_earlier_summary_without_running():
    find = FakeTool("find", hits=["https://a.example/1"])
    gate, lines = gateway(find)
    first = await gate.run(call("find", query="floods"), CTX)
    again = await gate.run(call("find", query="  floods "), CTX)  # the same once trimmed
    assert first.status == "ok"
    assert first.reason == "1 results."
    assert again.status == "duplicate"
    assert again.result is None  # search results are never kept for later
    assert again.reason == "The same call was made before: 1 results."
    assert len(find.runs) == 1
    assert lines == ["1 results.", "find “  floods ”: already done. " + again.reason]


@pytest.mark.ac("AG1a-AC2")
async def test_pages_are_read_only_from_links_the_investigation_knows():
    search = FakeTool("find", hits=["https://news.example/story/"])
    page = FakeTool("page", kind="read", args_model=UrlArgs)
    gate, lines = gateway(search, page, known={"https://given.example/brief"})
    evil = await gate.run(call("page", url="https://evil.example/?data=secret"), CTX)
    assert evil.status == "refused"
    assert evil.reason == PROVENANCE
    assert lines[0].startswith("page “https://evil.example/?data=secret”: not run. Lantern reads")
    assert (await gate.run(call("page", url="https://given.example/brief"), CTX)).status == "ok"
    early = await gate.run(call("page", url="https://news.example/story"), CTX)
    assert early.status == "refused"
    await gate.run(call("find", query="story"), CTX)
    later = await gate.run(call("page", url="https://NEWS.example/story/"), CTX)
    assert later.status == "ok"  # known once a search returned it, in canonical form
    assert [args.url for args in page.runs] == [
        "https://given.example/brief",
        "https://news.example/story",
    ]


@pytest.mark.ac("AG1a-AC2")
async def test_an_exhausted_budget_refuses_calls_of_that_kind():
    find = FakeTool("find")
    page = FakeTool("page", kind="read", args_model=UrlArgs)
    known = {f"https://a.example/{n}" for n in (1, 2, 3)}
    budget = RunBudget(tool_calls=3, searches=1, pages=5, records=0)
    gate, _ = gateway(find, page, budget=budget, known=known)
    assert (await gate.run(call("find", query="one"), CTX)).status == "ok"
    over = await gate.run(call("find", query="two"), CTX)
    assert over.status == "refused"
    assert over.reason == "This run has no search calls left in its budget."
    assert (await gate.run(call("page", url="https://a.example/1"), CTX)).status == "ok"
    assert (await gate.run(call("page", url="https://a.example/2"), CTX)).status == "ok"
    total = await gate.run(call("page", url="https://a.example/3"), CTX)
    assert total.reason == "This run has no read calls left in its budget."
    assert len(find.runs) == 1
    assert len(page.runs) == 2
    assert budget == RunBudget(tool_calls=0, searches=0, pages=3, records=0)
    assert budget.left("record") == 0


@pytest.mark.ac("AG1a-AC2")
async def test_the_checks_run_in_their_fixed_order():
    find = FakeTool("find")
    page = FakeTool("page", kind="read", args_model=UrlArgs)
    gate, _ = gateway(find, page, budget=RunBudget(tool_calls=1, searches=1, pages=0, records=0))
    ghost = await gate.run(call("ghost", url="ftp://x"), CTX)
    assert ghost.reason.startswith("There is no tool called ghost")  # tool before arguments
    bad = await gate.run(call("page", url="ftp://x"), CTX)
    assert (
        bad.reason
        == "The arguments are not valid: url: Value error, must be an http or https link."
    )
    unknown = await gate.run(call("page", url="https://evil.example/"), CTX)
    assert unknown.reason == PROVENANCE  # provenance before budget
    await gate.run(call("find", query="once"), CTX)
    repeat = await gate.run(call("find", query="once"), CTX)
    assert repeat.status == "duplicate"  # a repeat is answered even with no budget left
    assert page.runs == []
    assert len(find.runs) == 1


async def test_a_tools_policy_check_refuses_before_it_runs_or_spends_budget():
    find = FakeTool("find")
    budget = RunBudget(tool_calls=5, searches=5, pages=0, records=0)
    lines = []
    gate = ToolGateway(
        Registry([find]),
        budget,
        set(),
        lines.append,
        checks={"find": lambda args: "Off topic." if "private" in args.query else None},
    )
    refused = await gate.run(call("find", query="a private person"), CTX)
    assert (refused.status, refused.reason) == ("refused", "Off topic.")
    assert lines == ["find “a private person”: not run. Off topic."]
    assert (await gate.run(call("find", query="floods"), CTX)).status == "ok"
    assert len(find.runs) == 1
    assert budget.searches == 4


@pytest.mark.ac("AG1a-AC2")
async def test_calls_are_paced_per_rate_key():
    clock = FakeClock()
    slow = FakeTool("slow", rate_key="gdelt", min_interval=5.0)
    also = FakeTool("also", rate_key="gdelt", min_interval=5.0)
    other = FakeTool("other", rate_key="tavily", min_interval=5.0)
    gate, _ = gateway(slow, also, other, clock=clock)
    await gate.run(call("slow", query="a"), CTX)
    clock.now += 2
    await gate.run(call("also", query="b"), CTX)
    await gate.run(call("other", query="c"), CTX)
    assert clock.waits == [3.0]
    await asyncio.gather(
        gate.run(call("slow", query="d"), CTX), gate.run(call("also", query="e"), CTX)
    )
    assert clock.waits == [3.0, 5.0, 5.0]


@pytest.mark.ac("AG1a-AC2")
async def test_a_failed_call_is_reported_in_plain_words_and_may_be_tried_again():
    message = "The search service could not be reached. Try again later."
    find = FakeTool("find", error=message)
    quiet = FakeTool("quiet", summary="")
    gate, lines = gateway(find, quiet)
    first = await gate.run(call("find", query="x"), CTX)
    second = await gate.run(call("find", query="x"), CTX)
    assert first.status == second.status == "failed"
    assert first.reason == message
    assert len(find.runs) == 2
    await gate.run(call("quiet", query="x"), CTX)
    assert lines == [f"find “x”: failed. {message}"] * 2 + ["quiet: done."]


# ---- the wrapped capabilities ---------------------------------------------------------


def toolbox(searcher=None, fetcher=None, social=None, known=()):
    searcher = searcher or FakeSearch()
    tools = [
        WebSearch(searcher, 5),
        NewsSearch(searcher, 5),
        PostLinks(searcher),
        ReadPage(fetcher or FakeFetcher(), None),
    ]
    if social:
        tools.append(SocialPosts(social, 20))
    return gateway(*tools, known=known)[0]


async def test_news_search_passes_the_period_and_post_links_keep_only_posts():
    searcher = FakeSearch()
    gate = toolbox(searcher)
    news = await gate.run(call("news_search", query="floods", time_range="week"), CTX)
    assert searcher.options[-1] == ("floods", True, "week")
    assert news.reason == "Searched the news: “floods” (5 results)."
    links = await gate.run(call("post_links", phrase="floods"), CTX)
    assert [hit.url for hit in links.result.hits] == ["https://x.com/witness/status/999"]
    assert links.reason.endswith("“floods”: 1 post links.")


async def test_search_failures_become_plain_tool_failures():
    class Down:
        async def search(self, query, limit, domains=None, *, news=False, time_range=None):
            raise SearchError("The web search quota is used up. Try again later.")

    gate = toolbox(Down())
    for name, args in [("web_search", "query"), ("news_search", "query"), ("post_links", "phrase")]:
        outcome = await gate.run(call(name, **{args: "floods"}), CTX)
        assert outcome.status == "failed"
        assert outcome.reason == "The web search quota is used up. Try again later."


async def test_read_page_never_opens_sites_lantern_may_not_read():
    class Watching(FakeFetcher):
        def __init__(self):
            self.urls = []

        async def fetch(self, url):
            self.urls.append(url)
            return await super().fetch(url)

    fetcher = Watching()
    url = "https://www.youtube.com/watch?v=1"
    outcome = await toolbox(fetcher=fetcher, known={url}).run(call("read_page", url=url), CTX)
    assert outcome.status == "failed"
    assert outcome.reason.startswith("Lantern does not read youtube.com")
    assert fetcher.urls == []


async def test_read_page_saves_the_page_it_read():
    url = "https://apnews.com/floods"
    outcome = await toolbox(known={url}).run(call("read_page", url=url), CTX)
    draft = outcome.result.sources[0]
    assert (draft.url, draft.kind, draft.origin, draft.archive_url) == (
        url,
        "page",
        "apnews.com",
        None,
    )
    assert "four metres" in draft.text
    assert outcome.reason == "Read apnews.com."


async def test_read_page_reports_pages_without_text_and_refusals_without_copies():
    class NoCopy:
        async def copy(self, url):
            return None

    class Bare(FakeFetcher):
        async def fetch(self, url):
            if "apnews.com" in url:
                raise FetchError("The page returned HTTP 403.", "refused")
            return Page(url=url, content_type="text/html", body=b"<html><p>Too short.</p></html>")

    urls = ["https://ndma.gov.in/update", "https://apnews.com/floods", "https://apnews.com/other"]
    gate = gateway(ReadPage(Bare(), NoCopy()), known=urls)[0]
    ctx = ToolContext()
    empty, refused, again = [await gate.run(call("read_page", url=url), ctx) for url in urls]
    assert empty.reason == "Lantern found no readable text on the page."
    assert refused.reason == "The page returned HTTP 403. No archived copy was found."
    assert ctx.refusing == {"apnews.com"}
    assert again.reason == (
        "The site refused Lantern earlier in this run; no archived copy was found."
    )


async def test_social_search_takes_a_phrase_or_a_hashtag():
    social = FakeSocial()
    gate = toolbox(social=social)
    both = await gate.run(call("social_search", phrase="flood", hashtag="flood"), CTX)
    neither = await gate.run(call("social_search"), CTX)
    assert both.status == neither.status == "refused"
    assert "give either a phrase or a hashtag" in both.reason
    tag = await gate.run(call("social_search", hashtag="#DistrictFloods"), CTX)
    assert social.hashtags == ["DistrictFloods"]
    assert tag.reason == "Mastodon: #DistrictFloods (0 public posts)."
    posts = await gate.run(call("social_search", phrase="market road"), CTX)
    draft = posts.result.sources[0]
    assert (draft.kind, draft.title, draft.published) == (
        "post",
        "Bluesky post",
        "2026-11-01T08:00:00Z",
    )
    assert set(json.loads(draft.body)) == {"platform", "url", "posted_at", "language", "text"}


def test_links_in_the_question_are_known_to_the_gateway(tmp_path):
    store = Store(tmp_path)
    brief = "Is the claim in https://News.example/a/ (and http://b.example/x?y=1) true?"
    inv = Investigation(id=store.new_id(), brief=brief)
    tools = Tools(model=FakeModel(), searcher=FakeSearch(), fetcher=FakeFetcher())
    investigator = Investigator(inv, tools, store, Limits())
    assert investigator.gateway.known_urls == {"https://news.example/a", "http://b.example/x?y=1"}


async def test_a_failed_search_stops_the_run_only_when_nothing_was_searched(tmp_path):
    class Flaky(FakeSearch):
        def __init__(self, works):
            super().__init__()
            self.works = works

        async def search(self, query, limit, domains=None, *, news=False, time_range=None):
            if not domains and len(self.queries) >= self.works:
                raise SearchError("The web search quota is used up. Try again later.")
            return await super().search(query, limit, domains, news=news, time_range=time_range)

    async def run(works):
        store = Store(tmp_path)
        tools = Tools(model=FakeModel(), searcher=Flaky(works), fetcher=FakeFetcher())
        inv = Investigation(id=store.new_id(), brief="What happened in the district floods?")
        return await Investigator(inv, tools, store, Limits()).run()

    failed = await run(0)
    assert failed.status == "failed"
    assert failed.error == "The web search quota is used up. Try again later."
    partial = await run(1)
    assert partial.status == "done", partial.error
    assert partial.searched == ["river rise floods"]  # the round read what it had found
    assert any(
        step.message.startswith("news_search “river gauge news”: failed.") for step in partial.steps
    )


# ---- the rounds use only the gateway ------------------------------------------------

inside = ContextVar("inside_the_gateway", default=False)


@pytest.mark.ac("AG1a-AC3")
async def test_the_rounds_reach_every_capability_only_through_the_gateway(tmp_path, monkeypatch):
    original = ToolGateway.run

    async def watched(self, tool_call, ctx):
        token = inside.set(True)
        try:
            return await original(self, tool_call, ctx)
        finally:
            inside.reset(token)

    monkeypatch.setattr(ToolGateway, "run", watched)
    seen = []

    class Search(FakeSearch):
        async def search(self, query, limit, domains=None, *, news=False, time_range=None):
            seen.append(("search", inside.get()))
            return await super().search(query, limit, domains, news=news, time_range=time_range)

    class Fetch(FakeFetcher):
        async def fetch(self, url):
            seen.append(("fetch", inside.get()))
            if "apnews.com" in url:
                raise FetchError("The page returned HTTP 403.", "refused")
            return await super().fetch(url)

    class Social(FakeSocial):
        async def search(self, query, limit):
            seen.append(("social", inside.get()))
            return await super().search(query, limit)

        async def hashtag(self, tag, limit):
            seen.append(("hashtag", inside.get()))
            return await super().hashtag(tag, limit)

    class Archive:
        async def copy(self, url):
            seen.append(("archive", inside.get()))
            body = fakes.html(fakes.PAGES[url])
            page = Page(f"https://web.archive.org/web/20260515000000id_/{url}", "text/html", body)
            return Copy(
                page=page, archive_url=page.url, archived_at=datetime(2026, 5, 15, tzinfo=UTC)
            )

    store = Store(tmp_path)
    tools = Tools(
        model=FakeModel(followups=[["second incident found dead"]]),
        searcher=Search(),
        fetcher=Fetch(),
        social=Social(),
        archive=Archive(),
    )
    inv = Investigation(id=store.new_id(), brief="What happened in the district floods?")
    inv = await Investigator(inv, tools, store, Limits.for_depth("deep")).run()
    assert inv.status == "done", inv.error
    assert {what for what, _ in seen} == {"search", "fetch", "social", "hashtag", "archive"}
    assert all(through for _, through in seen)
    assert inv.usage.archived == 1
    assert any(step.message.startswith("Searched the web: ") for step in inv.steps)
