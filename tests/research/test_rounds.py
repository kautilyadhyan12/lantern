"""Investigative behaviour: follow-up rounds, full item lists, result triage, reading routing."""

from fastapi.testclient import TestClient

from lantern.config import AppSettings
from lantern.llm import ModelError, Provider
from lantern.models import Investigation
from lantern.pipeline import Investigator, Limits, Tools
from lantern.report import to_markdown
from lantern.runtime import reading_order
from lantern.store import Store
from lantern.web.app import create_app

from . import fakes
from .fakes import FakeFetcher, FakeModel, FakeSearch

NEW_PAGE = "https://www.thehindu.com/news/second-incident"
NEW_TEXT = (
    "A second resident was found dead near the embankment on Tuesday, police said. "
    "Officials said the river rose by four metres on Monday before the embankment failed."
)


class DeepSearch(FakeSearch):
    async def search(self, query, limit, domains=None, *, news=False, time_range=None):
        if query == "second incident found dead":
            self.options.append((query, news, time_range))
            return [fakes.Hit(url=NEW_PAGE, title=fakes.HIT_TITLE, rank=1)]
        return await super().search(query, limit, domains, news=news, time_range=time_range)


def investigate(tmp_path, model, limits, searcher=None, reader=None):
    store = Store(tmp_path)
    tools = Tools(
        model=model, searcher=searcher or FakeSearch(), fetcher=FakeFetcher(), reader=reader
    )
    inv = Investigation(id=store.new_id(), brief="What happened in the district floods?")
    return Investigator(inv, tools, store, limits).run(), store


async def test_deep_runs_follow_up_on_what_they_found(tmp_path, monkeypatch):
    monkeypatch.setattr(fakes, "PAGES", {**fakes.PAGES, NEW_PAGE: NEW_TEXT})
    searcher = DeepSearch()
    model = FakeModel(followups=[["second incident found dead"]])
    run, _ = investigate(tmp_path, model, Limits.for_depth("deep"), searcher)
    inv = await run
    assert inv.status == "done", inv.error
    assert inv.usage.rounds == 2
    assert NEW_PAGE in [source.url for source in inv.sources]
    # Opening round: the first query per key question searches the web, the others the news
    # within the planned period; the follow-up searched the news too.
    assert ("river rise floods", False, None) in searcher.options
    assert ("river gauge news", True, "week") in searcher.options
    assert ("second incident found dead", True, "week") in searcher.options
    assert model.calls.count("FollowupOut") == 2
    follow_up_prompt = model.prompts["FollowupOut"][0]
    assert "river rise floods" in follow_up_prompt  # it is told what was already searched
    assert any("following up with 1 searches" in step.message for step in inv.steps)


async def test_quick_runs_have_one_round_and_no_follow_up(tmp_path):
    model = FakeModel(followups=[["never asked"]])
    run, _ = investigate(tmp_path, model, Limits.for_depth("quick"))
    inv = await run
    assert inv.usage.rounds == 1
    assert "FollowupOut" not in model.calls


def test_depth_limits():
    quick, deep = Limits.for_depth("quick"), Limits.for_depth("deep")
    assert (quick.rounds, quick.max_pages) == (1, 10)
    assert (deep.rounds, deep.max_pages, deep.queries_per_question) == (3, 30, 3)


async def test_list_questions_get_every_item_with_its_evidence_status(tmp_path):
    run, _ = investigate(tmp_path, FakeModel(kinds=("fact", "list")), Limits())
    inv = await run
    assert inv.status == "done", inv.error
    items = [item for item in inv.items if item.question_ref == "Q2"]
    assert items, "the list question has items"
    assert all(item.name != "Ghost" for item in items)  # items citing no real claim are dropped
    families = next(item for item in items if "12,000 families" in item.summary)
    assert families.status == "corroborated"
    assert families.origins == ["apnews.com", "ndma.gov.in", "reuters.com"]
    assert families.best_grade == "B"
    assert not [item for item in inv.items if item.question_ref == "Q1"]  # fact question
    assert "### Everything found" in to_markdown(inv)
    settings = AppSettings(data_dir=str(tmp_path), tavily_api_key="t", groq_api_key="g")
    page = TestClient(create_app(settings)).get(f"/investigations/{inv.id}").text
    assert "Everything found" in page
    assert "corroborated" in page


async def test_an_item_from_one_site_is_listed_as_single_source(tmp_path, monkeypatch):
    only = "https://www.reuters.com/floods"
    monkeypatch.setattr(fakes, "PAGES", {only: fakes.PAGES[only]})
    run, _ = investigate(tmp_path, FakeModel(kinds=("fact", "list")), Limits())
    inv = await run
    assert inv.items
    assert {item.status for item in inv.items} == {"single source"}


async def test_triage_chooses_what_to_read_within_the_budget(tmp_path):
    model = FakeModel()
    run, _ = investigate(tmp_path, model, Limits(first_round_pages=2))
    inv = await run
    assert "TriageOut" in model.calls
    reading = next(step.message for step in inv.steps if step.message.startswith("Reading"))
    assert reading == "Reading 2 pages."
    # The fake triage prefers the last results: the unreadable page and ndma.gov.in.
    assert [source.domain for source in inv.sources] == ["ndma.gov.in"]
    assert [lead.platform for lead in inv.leads if lead.kind == "page"] == ["blocked.example"]


async def test_failed_triage_falls_back_to_search_order(tmp_path):
    class NoTriage(FakeModel):
        async def structured(self, system, user, output):
            if output.__name__ == "TriageOut":
                raise ModelError("bad answer twice")
            return await super().structured(system, user, output)

    run, _ = investigate(tmp_path, NoTriage(), Limits(first_round_pages=2))
    inv = await run
    assert inv.status == "done", inv.error
    assert [source.domain for source in inv.sources] == ["reuters.com", "apnews.com"]


async def test_page_reading_goes_to_the_reader_model(tmp_path):
    thinker, reader = FakeModel(), FakeModel()
    run, _ = investigate(tmp_path, thinker, Limits(), reader=reader)
    inv = await run
    assert inv.status == "done", inv.error
    assert "ExtractOut" in reader.calls
    assert "ExtractOut" not in thinker.calls
    assert "AssessOut" in thinker.calls


def test_reading_order_puts_gemini_first_and_shares_provider_state():
    groq = Provider("groq", "https://groq.test", "k", "m")
    gemini = Provider("gemini", "https://gemini.test", "k", "m")
    order = reading_order([groq, gemini])
    assert [item.name for item in order] == ["gemini", "groq"]
    assert order[1] is groq


def test_the_web_form_sends_the_chosen_depth(tmp_path):
    seen = []

    async def runner(inv, config, store):
        seen.append(inv.depth)
        return inv

    settings = AppSettings(data_dir=str(tmp_path), tavily_api_key="t", groq_api_key="g")
    client = TestClient(create_app(settings, runner=runner))
    assert 'value="deep" checked' in client.get("/").text
    client.post(
        "/api/investigations", json={"brief": "What happened in the floods?", "depth": "quick"}
    )
    client.post("/api/investigations", json={"brief": "What happened in the floods?"})
    assert seen == ["quick", "deep"]
