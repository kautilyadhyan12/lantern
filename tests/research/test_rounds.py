"""Investigative behaviour: follow-up rounds, full item lists, result triage, reading routing."""

from fastapi.testclient import TestClient

from lantern.config import AppSettings
from lantern.llm import ModelError, Provider
from lantern.models import Investigation, Item, now
from lantern.pipeline import Investigator, Limits, Tools, same_item
from lantern.report import to_markdown
from lantern.runtime import reading_order
from lantern.store import Store
from lantern.text import relevant_chunks
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


async def test_every_model_call_is_told_todays_date(tmp_path):
    model = FakeModel()
    run, _ = investigate(tmp_path, model, Limits())
    await run
    today = now().date().isoformat()
    for name in ("GateOut", "PlanOut", "ExtractOut", "AssessOut", "ReportOut"):
        assert all(today in system for system in model.systems[name]), name


async def test_the_list_of_items_never_shrinks_between_rounds(tmp_path, monkeypatch):
    monkeypatch.setattr(fakes, "PAGES", {**fakes.PAGES, NEW_PAGE: NEW_TEXT})

    class Forgetful(FakeModel):
        async def structured(self, system, user, output):
            out = await super().structured(system, user, output)
            if output.__name__ == "InventoryOut" and self.calls.count("InventoryOut") > 1:
                out.items = out.items[:1]  # a later answer forgets most items
            return out

    model = Forgetful(kinds=("fact", "list"), followups=[["second incident found dead"]])
    run, _ = investigate(tmp_path, model, Limits.for_depth("deep"), DeepSearch())
    inv = await run
    first = model.prompts["InventoryOut"][0]
    first_claims = {
        line.split(" ")[0] for line in first.splitlines() if line[:1] == "C" and line[1:2].isdigit()
    }
    kept = {ref for item in inv.items for ref in item.claim_refs}
    assert first_claims <= kept


def test_long_pages_are_read_where_they_mention_the_question():
    filler = "\n".join("Unrelated history paragraph about something else." for _ in range(400))
    target = "The commander was found dead in Lahore, police said."
    text = f"{filler}\n{target}\n{filler}"
    parts = relevant_chunks(text, ["Which commanders were found dead in Lahore?"], size=3000)
    assert len(parts) == 1
    assert target in parts[0]


async def test_a_site_that_refuses_once_is_not_asked_again(tmp_path):
    class Refusing(FakeFetcher):
        def __init__(self):
            self.urls = []

        async def fetch(self, url):
            self.urls.append(url)
            if "apnews.com" in url:
                raise fakes.FetchError("The page returned HTTP 403.")
            return await super().fetch(url)

    class TwoAp(DeepSearch):
        async def search(self, query, limit, domains=None, *, news=False, time_range=None):
            if query == "second incident found dead":
                self.options.append((query, news, time_range))
                return [fakes.Hit(url="https://apnews.com/other", title="t", rank=1)]
            return await super().search(query, limit, domains, news=news, time_range=time_range)

    store = Store(tmp_path)
    fetcher = Refusing()
    tools = Tools(
        model=FakeModel(followups=[["second incident found dead"]]),
        searcher=TwoAp(),
        fetcher=fetcher,
    )
    inv = Investigation(id=store.new_id(), brief="What happened in the district floods?")
    await Investigator(inv, tools, store, Limits.for_depth("deep")).run()
    assert [url for url in fetcher.urls if "apnews.com" in url] == ["https://apnews.com/floods"]


async def test_a_cautious_triage_still_reads_half_the_budget(tmp_path, monkeypatch):
    many = {
        f"https://site{i}.example/report": fakes.PAGES["https://apnews.com/floods"]
        for i in range(8)
    }
    monkeypatch.setattr(fakes, "PAGES", many)

    class Cautious(FakeModel):
        async def structured(self, system, user, output):
            if output.__name__ == "TriageOut":
                return output.model_validate({"read": ["H1"]})
            return await super().structured(system, user, output)

    run, _ = investigate(tmp_path, Cautious(), Limits(first_round_pages=6))
    inv = await run
    reading = next(step.message for step in inv.steps if step.message.startswith("Reading"))
    assert reading == "Reading 3 pages."


def test_items_with_the_same_name_merge_and_are_re_rated():
    store_less = Investigator.__new__(Investigator)
    one = Item(
        question_ref="Q1",
        name="Muhammad Sarwar",
        summary="a",
        claim_refs=["C1"],
        origins=["thehindu.com"],
        best_grade="B",
        status="single source",
    )
    two = Item(
        question_ref="Q1",
        name="muhammad  sarwar",
        summary="b",
        when="18 Oct",
        claim_refs=["C2"],
        origins=["news18.com"],
        best_grade="F",
        status="single source",
    )
    merged = store_less._merge_same_names([one, two])
    assert len(merged) == 1
    assert merged[0].claim_refs == ["C1", "C2"]
    assert merged[0].status == "corroborated"
    assert merged[0].when == "18 Oct"


async def test_blocked_headlines_guide_follow_ups_but_are_never_saved(tmp_path):
    model = FakeModel(followups=[["second incident found dead"]])
    run, store = investigate(tmp_path, model, Limits.for_depth("deep"), DeepSearch())
    inv = await run
    follow_up = model.prompts["FollowupOut"][0]
    assert f"{fakes.HIT_TITLE} (blocked.example)" in follow_up
    saved = "".join(path.read_text("utf-8", "replace") for path in store.root.rglob("*.*"))
    assert fakes.HIT_TITLE not in saved
    assert inv.status == "done"


def test_same_item_matches_spelling_variants_but_not_different_people():
    assert same_item("Muhammad Sarwar", "Chaudhry Muhammad Sarwar")
    assert same_item("Bilal Arif Sarafi", "Bilal Arif Salafi")
    assert not same_item("Muhammad Sarwar", "Muhammad Hanif")
    assert not same_item("", "Anyone")


async def test_names_in_search_results_become_unconfirmed_mentions(tmp_path):
    model = FakeModel(kinds=("fact", "list"))
    run, store = investigate(tmp_path, model, Limits())
    inv = await run
    assert [m.name for m in inv.mentions] == ["Embankment collapse"]  # the invented one is dropped
    assert inv.mentions[0].urls == ["https://www.reuters.com/floods"]
    saved = (store.root / "investigations" / f"{inv.id}.json").read_text()
    assert fakes.HIT_TITLE not in saved
    assert fakes.HIT_SNIPPET not in saved
    settings = AppSettings(data_dir=str(tmp_path), tavily_api_key="t", groq_api_key="g")
    page = TestClient(create_app(settings)).get(f"/investigations/{inv.id}").text
    assert "Only in search headlines: 1" in page
    assert "leads, not evidence" in page
    assert "### Also seen in search results" in to_markdown(inv)


async def test_unconfirmed_mentions_are_chased_and_confirmed_ones_become_items(tmp_path):
    class Confirms(FakeModel):
        async def structured(self, system, user, output):
            out = await super().structured(system, user, output)
            if output.__name__ == "InventoryOut":
                out.items[0].name = "Embankment collapse"
            return out

    model = Confirms(kinds=("fact", "list"), followups=[["second incident found dead"]])
    run, _ = investigate(tmp_path, model, Limits.for_depth("deep"), DeepSearch())
    inv = await run
    follow_up = model.prompts["FollowupOut"][0]
    assert "item: Embankment collapse" in follow_up
    assert "not confirmed: Embankment collapse" not in follow_up
    assert any(item.name == "Embankment collapse" for item in inv.items)
    assert inv.mentions == []


async def test_follow_ups_are_told_about_unconfirmed_mentions(tmp_path):
    model = FakeModel(kinds=("fact", "list"), followups=[["second incident found dead"]])
    run, _ = investigate(tmp_path, model, Limits.for_depth("deep"), DeepSearch())
    await run
    follow_up = model.prompts["FollowupOut"][0]
    assert "seen only in search results, not confirmed: Embankment collapse" in follow_up
