"""Web pages render reports safely and starting a run respects keys and limits."""

from fastapi.testclient import TestClient

from lantern.config import AppSettings
from lantern.models import Claim, Investigation
from lantern.pipeline import Investigator, Limits, Tools
from lantern.store import Store
from lantern.web.app import create_app, segments

from .fakes import FakeFetcher, FakeModel, FakeSearch


def settings(tmp_path, **extra):
    return AppSettings(data_dir=str(tmp_path), tavily_api_key="t", groq_api_key="g", **extra)


async def finished(tmp_path):
    store = Store(tmp_path)
    tools = Tools(model=FakeModel(), searcher=FakeSearch(), fetcher=FakeFetcher())
    inv = Investigation(id=store.new_id(), brief="What happened in the floods this week?")
    return await Investigator(inv, tools, store, Limits()).run()


async def test_report_page_shows_citations_grades_and_downloads(tmp_path):
    inv = await finished(tmp_path)
    client = TestClient(create_app(settings(tmp_path)))
    page = client.get(f"/investigations/{inv.id}")
    assert page.status_code == 200
    assert 'data-ref="C1"' in page.text
    assert 'id="card-C1"' in page.text
    assert "almost certain" in page.text
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert client.get(f"/investigations/{inv.id}/report.md").text.startswith("# What happened")
    assert client.get(f"/investigations/{inv.id}/investigation.json").json()["id"] == inv.id
    saved = client.get(f"/investigations/{inv.id}/sources/S1")
    assert '<mark id="C1"' in saved.text


async def test_saved_copies_are_escaped(tmp_path):
    inv = await finished(tmp_path)
    store = Store(tmp_path)
    source = inv.sources[0]
    source.text_sha256 = store.put_text("<script>alert(1)</script> and more text")
    store.save(inv)
    client = TestClient(create_app(settings(tmp_path)))
    body = client.get(f"/investigations/{inv.id}/sources/S1").text
    assert "<script>alert(1)" not in body
    assert "&lt;script&gt;" in body


def test_start_runs_in_the_background_and_reports_progress(tmp_path):
    started = []

    async def runner(inv, config, store):
        started.append(inv.brief)
        inv.status = "done"
        store.save(inv)
        return inv

    client = TestClient(create_app(settings(tmp_path), runner=runner))
    response = client.post("/api/investigations", json={"brief": "What is known about the floods?"})
    assert response.status_code == 201
    progress = client.get(f"/api/investigations/{response.json()['id']}").json()
    assert progress["status"] in {"queued", "done"}
    assert client.get("/").status_code == 200


def test_missing_keys_and_daily_limit_block_new_runs(tmp_path):
    client = TestClient(create_app(AppSettings(data_dir=str(tmp_path))))
    blocked = client.post("/api/investigations", json={"brief": "What is known about the floods?"})
    assert blocked.status_code == 503
    assert "LANTERN_TAVILY_API_KEY" in blocked.json()["error"]
    Store(tmp_path).save(Investigation(id="abcdefabcdef", brief="earlier", status="done"))
    client = TestClient(create_app(settings(tmp_path, daily_run_limit=1)))
    limited = client.post("/api/investigations", json={"brief": "What is known about the floods?"})
    assert limited.status_code == 429


def test_unknown_or_malformed_ids_are_not_found(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))
    assert client.get("/investigations/../../etc/passwd").status_code == 404
    assert client.get("/investigations/abcdefabcdef").status_code == 404


def test_interrupted_runs_are_marked_failed_on_start(tmp_path):
    Store(tmp_path).save(Investigation(id="abcdefabcdef", brief="x", status="running"))
    create_app(settings(tmp_path))
    assert Store(tmp_path).load("abcdefabcdef").status == "failed"


def test_highlight_segments_skip_overlaps():
    claims = [
        Claim(
            ref="C1", source_ref="S1", question_refs=["Q1"], statement="s", quote="", start=0, end=5
        ),
        Claim(
            ref="C2", source_ref="S1", question_refs=["Q1"], statement="s", quote="", start=3, end=8
        ),
    ]
    assert segments("Hello world", claims) == [("Hello", "C1"), (" world", None)]
