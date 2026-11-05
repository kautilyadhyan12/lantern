"""A full investigation runs offline with fakes; every check holds on the result."""

import hashlib

import pytest

from lantern.llm import QuotaError
from lantern.models import Investigation
from lantern.pipeline import Investigator, Limits, Tools
from lantern.report import to_markdown
from lantern.store import Store

from . import fakes
from .fakes import FakeFetcher, FakeModel, FakeSearch


def run(tmp_path, brief="What happened in the district floods this week?", model=None):
    store = Store(tmp_path)
    model = model or FakeModel()
    tools = Tools(model=model, searcher=FakeSearch(), fetcher=FakeFetcher())
    investigation = Investigation(id=store.new_id(), brief=brief)
    return Investigator(investigation, tools, store, Limits()).run, store, model


async def test_full_run_produces_a_verified_cited_report(tmp_path):
    start, store, _ = run(tmp_path)
    inv = await start()
    assert inv.status == "done", inv.error
    assert [q.ref for q in inv.questions] == ["Q1", "Q2"]
    assert {s.domain for s in inv.sources} == {"reuters.com", "apnews.com", "ndma.gov.in"}
    assert inv.usage.pages_skipped == 1  # blocked.example; facebook.com is never fetched
    for source in inv.sources:
        text = store.text(source.text_sha256)
        assert text is not None
        assert hashlib.sha256(text.encode()).hexdigest() == source.text_sha256
        assert (store.root / "blobs" / f"{source.sha256}.bin").exists()
    for claim in inv.claims:
        text = store.text(inv.source(claim.source_ref).text_sha256)
        assert text[claim.start : claim.end] == claim.quote
        assert "Q9" not in claim.question_refs
    assert inv.usage.claims_dropped >= 3  # the invented quote, once per page
    finding = inv.findings[0]
    assert finding.status == "answered"
    assert finding.likelihood == "almost certain"
    assert finding.confidence == "high"
    assert finding.domains == ["apnews.com", "ndma.gov.in", "reuters.com"]
    report = inv.report
    assert [s.text for s in report.bottom_line] == ["The river rose about four metres on Monday."]
    assert report.sections[0].sentences[0].cites == ["C1", "C3"]
    assert "[C1" not in report.sections[0].sentences[0].text
    assert {r.reason for r in report.removed} == {
        "It cites no claim.",
        "It cites unknown claims: C99.",
    }
    assert store.load(inv.id).status == "done"
    assert "## Sources" in to_markdown(inv)


async def test_search_results_are_not_stored(tmp_path):
    start, store, _ = run(tmp_path)
    inv = await start()
    saved = (store.root / "investigations" / f"{inv.id}.json").read_text()
    stored = saved + "".join(path.read_text("utf-8", "replace") for path in store.root.rglob("*.*"))
    assert fakes.HIT_TITLE not in stored
    assert fakes.HIT_SNIPPET not in stored
    # A non-post facebook link is neither read nor listed; an unreadable page is a lead.
    assert "facebook.com/post/1" not in saved
    assert [(lead.kind, lead.platform) for lead in inv.leads if lead.kind == "page"] == [
        ("page", "blocked.example")
    ]


async def test_fixed_rules_refuse_without_any_model_call(tmp_path):
    start, _, model = run(tmp_path, brief="Find the home address of this reporter please")
    inv = await start()
    assert inv.status == "refused"
    assert "locate people" in inv.safety
    assert model.calls == []


async def test_the_ai_safety_check_can_refuse(tmp_path):
    start, _, model = run(
        tmp_path,
        brief="Tell me everything about Ravi Kumar from Pune",
        model=FakeModel(allowed=False),
    )
    inv = await start()
    assert inv.status == "refused"
    assert model.calls == ["GateOut"]


@pytest.mark.parametrize("domains", [1])
async def test_one_site_cannot_reach_high_confidence(tmp_path, domains, monkeypatch):
    monkeypatch.setattr(
        fakes,
        "PAGES",
        {"https://www.reuters.com/floods": fakes.PAGES["https://www.reuters.com/floods"]},
    )
    start, _, _ = run(tmp_path)
    inv = await start()
    finding = inv.findings[0]
    assert finding.confidence == "low"
    assert finding.likelihood == "likely"
    assert finding.likelihood_proposed == "almost certain"


async def test_page_choice_skips_video_sites_and_caps_pages_per_site(tmp_path, monkeypatch):
    urls = [f"https://en.wikipedia.org/wiki/Page{i}" for i in range(4)]
    urls += ["https://www.youtube.com/watch?v=1", "https://apnews.com/floods"]

    async def search(self, query, limit, domains=None, **options):
        return [fakes.Hit(url=url, title="hit", rank=i) for i, url in enumerate(urls, start=1)]

    monkeypatch.setattr(fakes.FakeSearch, "search", search)
    start, _, _ = run(tmp_path)
    inv = await start()
    reading = next(step.message for step in inv.steps if step.message.startswith("Reading"))
    assert reading == "Reading 4 pages."  # three Wikipedia pages (the cap) and AP; no YouTube


async def test_running_out_of_free_ai_stops_the_run_with_a_clear_message(tmp_path):
    class OutOfQuota(FakeModel):
        async def structured(self, system, user, output):
            if output.__name__ == "ExtractOut":
                raise QuotaError("The free AI allowance (groq) is used up for now.")
            return await super().structured(system, user, output)

    start, _, _ = run(tmp_path, model=OutOfQuota())
    inv = await start()
    assert inv.status == "failed"
    assert "used up" in inv.error
