"""Continuing an investigation builds on it: no repeated searches or pages, nothing lost."""

from fastapi.testclient import TestClient

from lantern.config import AppSettings
from lantern.models import Investigation, Question, now
from lantern.pipeline import Investigator, Limits, Tools
from lantern.store import Store
from lantern.web.app import create_app

from . import fakes
from .fakes import FakeFetcher, FakeModel
from .test_rounds import NEW_PAGE, NEW_TEXT, DeepSearch


class Counting(FakeFetcher):
    def __init__(self):
        self.urls = []

    async def fetch(self, url):
        self.urls.append(url)
        return await super().fetch(url)


async def test_continuing_adds_rounds_without_repeating_work(tmp_path, monkeypatch):
    monkeypatch.setattr(fakes, "PAGES", {**fakes.PAGES, NEW_PAGE: NEW_TEXT})
    store = Store(tmp_path)
    # The first pass stops after round 1 (no follow-up); the continuation follows up once.
    model = FakeModel(kinds=("fact", "list"), followups=[[], ["second incident found dead"]])
    searcher, fetcher = DeepSearch(), Counting()
    tools = Tools(model=model, searcher=searcher, fetcher=fetcher)
    first = Investigation(id=store.new_id(), brief="What happened in the district floods?")
    first = await Investigator(first, tools, store, Limits.for_depth("deep")).run()
    assert first.status == "done", first.error
    assert first.usage.rounds == 1
    read_first = list(fetcher.urls)
    items_first = {item.name for item in first.items}
    searched_first = list(first.searched)
    assert searched_first

    # Continue from what was saved, as the web app does after a restart.
    saved = store.load(first.id)
    assert saved is not None
    again = await Investigator(saved, tools, store, Limits.for_depth("deep")).resume()
    assert again.status == "done", again.error
    assert again.usage.rounds == 2
    assert NEW_PAGE in [source.url for source in again.sources]
    assert not set(read_first) & set(fetcher.urls[len(read_first) :])  # no page read twice
    assert again.searched[: len(searched_first)] == searched_first
    assert "second incident found dead" in again.searched
    follow_up = model.prompts["FollowupOut"][-1]
    assert searched_first[0] in follow_up  # told what was already searched
    assert items_first <= {item.name for item in again.items}
    assert len(again.findings) == len(again.questions)  # rebuilt, not appended
    assert any("Continuing the investigation" in step.message for step in again.steps)


def settings(tmp_path, **extra):
    return AppSettings(data_dir=str(tmp_path), tavily_api_key="t", groq_api_key="g", **extra)


def test_the_continue_endpoint_queues_a_finished_investigation(tmp_path):
    store = Store(tmp_path)
    done = Investigation(id="abcdefabcdef", brief="Floods?", status="done")
    done.questions = [Question(ref="Q1", text="What happened?")]
    store.save(done)
    continued = []

    async def continuer(inv, config, store):
        continued.append(inv.id)
        return inv

    client = TestClient(create_app(settings(tmp_path), continuer=continuer))
    page = client.get("/investigations/abcdefabcdef").text
    assert "Continue investigating" in page
    response = client.post("/api/investigations/abcdefabcdef/continue")
    assert response.status_code == 202
    assert continued == ["abcdefabcdef"]
    saved = Store(tmp_path).load("abcdefabcdef")
    assert saved is not None
    assert len(saved.continued_at) == 1


def test_running_or_refused_investigations_cannot_be_continued(tmp_path):
    store = Store(tmp_path)
    running = Investigation(id="aaaaaaaaaaaa", brief="x", status="done")
    running.questions = [Question(ref="Q1", text="What happened?")]
    store.save(running)
    store.save(Investigation(id="bbbbbbbbbbbb", brief="x", status="refused"))
    client = TestClient(create_app(settings(tmp_path), continuer=lambda *a: None))
    running.status = "running"
    store.save(running)
    assert client.post("/api/investigations/aaaaaaaaaaaa/continue").status_code == 409
    assert client.post("/api/investigations/bbbbbbbbbbbb/continue").status_code == 409
    assert client.post("/api/investigations/cccccccccccc/continue").status_code == 404


def test_each_continuation_counts_towards_the_daily_limit(tmp_path):
    store = Store(tmp_path)
    done = Investigation(id="abcdefabcdef", brief="x", status="done")
    done.questions = [Question(ref="Q1", text="What happened?")]
    done.continued_at = [now()]
    store.save(done)
    assert store.started_today() == 2
    client = TestClient(create_app(settings(tmp_path, daily_run_limit=2)))
    assert client.post("/api/investigations/abcdefabcdef/continue").status_code == 429
