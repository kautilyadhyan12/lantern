"""Entities and links: built only from anchored claims and records, people never merged on
a name alone, link status from the independence rules, and the links map."""

import pytest
from fastapi.testclient import TestClient

from lantern import prompts
from lantern.agent.loop import Agent
from lantern.config import AppSettings
from lantern.core import graph
from lantern.models import (
    RELATIONS,
    Claim,
    Entity,
    Investigation,
    Link,
    Question,
    Report,
    Source,
    Triple,
    now,
)
from lantern.pipeline import Investigator, Limits, Tools
from lantern.report import to_markdown
from lantern.store import Store
from lantern.tools.adapters.sanctions import SanctionsSearch
from lantern.tools.adapters.wiki import SUMMARY, WIKIDATA, WikiLookup
from lantern.web import board, linkmap
from lantern.web.app import create_app

from . import fakes
from .fakes import FakeFetcher, FakeModel, FakeSearch
from .test_agent import DONE, Researcher
from .test_records import LET_ENTITY, LET_SUMMARY, Wiki, lists

PERSON, ORG = "person_public_role", "organisation"


def triple(subject, relation, obj, claim, *, kinds=(PERSON, ORG), basis="stated", ids=((), ())):
    return Triple.model_validate(
        {
            "subject": {"name": subject, "kind": kinds[0], "ids": list(ids[0])},
            "relation": relation,
            "object": {"name": obj, "kind": kinds[1], "ids": list(ids[1])},
            "claim_refs": [claim],
            "basis": basis,
        }
    )


def build(triples, sources=None, origins=None):
    claims = {ref for t in triples for ref in t.claim_refs}
    source_of = sources or {ref: f"S-{ref}" for ref in claims}  # each claim its own source
    origin_of = origins or {ref: f"site-{ref}.example" for ref in claims}
    return graph.build(triples, source_of, origin_of)


def people(entities):
    return sorted(entity.name for entity in entities if entity.kind == PERSON)


# ---- AG3-AC1: only anchored claims and records -----------------------------------


@pytest.mark.ac("AG3-AC1")
def test_relations_use_the_vocabulary_and_names_written_in_the_quote():
    quote = "Abu Qatal, a commander of Lashkar-e-Taiba, was shot dead in Jhelum."
    keep = graph.stated(
        quote,
        subject="Abu Qatal",
        subject_kind=PERSON,
        relation="leader_of",
        obj="Lashkar-e-Taiba",
        object_kind=ORG,
    )
    assert keep is not None
    assert (keep.subject.name, keep.relation, keep.object.name) == (
        "Abu Qatal",
        "leader_of",
        "Lashkar-e-Taiba",
    )
    for wrong in (
        {"relation": "religion_of"},  # not in the vocabulary
        {"relation": "member_of_party"},
        {"subject_kind": "person"},  # not a known kind
        {"obj": "Jaish-e-Mohammed"},  # not written in the quote
        {"subject": ""},
    ):
        parts = {"subject": "Abu Qatal", "subject_kind": PERSON, "relation": "member_of"}
        parts |= {"obj": "Lashkar-e-Taiba", "object_kind": ORG, **wrong}
        assert graph.stated(quote, **parts) is None


@pytest.mark.ac("AG3-AC1")
def test_the_vocabulary_has_no_protected_trait_relations():
    banned = ("religion", "ethnic", "caste", "health", "sexual", "party", "union", "political")
    assert not [relation for relation in RELATIONS if any(word in relation for word in banned)]
    assert "relation" not in prompts.PostClaimDraft.model_fields  # posts never state relations


class Relating(FakeModel):
    """The fake reader tags each river claim with a relation; one tag uses an unknown name."""

    async def structured(self, system, user, output):
        out = await super().structured(system, user, output)
        if output is prompts.ExtractOut:
            # Only Reuters' page has this sentence, so the claim anchors there alone.
            out.claims[0].quote = "Floods in the district. Officials said the river rose"
            out.claims[0].relation = prompts.RelationDraft(
                subject="river",
                subject_kind="place",
                relation="located_in",
                object="district",
                object_kind="place",
            )
            out.claims[1].relation = prompts.RelationDraft(
                subject="Ghost Group",
                subject_kind=ORG,
                relation="linked_to",
                object="families",
                object_kind=ORG,
            )
        return out


@pytest.mark.ac("AG3-AC1")
async def test_a_run_maps_relations_from_its_anchored_claims(tmp_path):
    store = Store(tmp_path)
    inv = Investigation(id=store.new_id(), brief="What happened in the district floods?")
    tools = Tools(model=Relating(), searcher=FakeSearch(), fetcher=FakeFetcher())
    inv = await Investigator(inv, tools, store, Limits()).run()
    assert inv.status == "done", inv.error
    assert {(t.subject.name, t.relation, t.object.name) for t in inv.relations} == {
        ("river", "located_in", "district")
    }  # "Ghost Group" is not in its quote, so it was dropped
    assert [(e.name, e.kind) for e in inv.entities] == [("river", "place"), ("district", "place")]
    [link] = inv.links
    assert (link.status, link.origins) == ("single source", ["reuters.com"])
    assert any(step.message == "Mapped 2 entities and 1 links between them." for step in inv.steps)


# ---- AG3-AC2: people merge only on anchors --------------------------------------------


@pytest.mark.ac("AG3-AC2")
@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Muhammad Sarwar", "Muhammad Sarwar Khan"),
        ("Abu Qatal", "Abu Qital"),
        ("Bilal Arif Sarafi", "Bilal Arif Salafi"),
        ("A. Khan", "B. Khan"),
        ("Saeed", "Hafiz Saeed"),
    ],
)
def test_near_miss_names_are_never_one_person_even_in_the_same_group(first, second):
    entities, _ = build(
        [
            triple(first, "member_of", "Lashkar-e-Taiba", "C1"),
            triple(second, "member_of", "Lashkar-e-Taiba", "C2"),
        ]
    )
    assert people(entities) == sorted([first, second])


@pytest.mark.ac("AG3-AC2")
def test_the_same_name_is_one_person_only_with_an_anchor():
    same = [
        triple("Abu Qatal", "killed_in", "Jhelum attack", "C1", kinds=(PERSON, "event")),
        triple("Abu Qatal", "killed_in", "Lahore shooting", "C2", kinds=(PERSON, "event")),
    ]
    assert people(build(same)[0]) == ["Abu Qatal", "Abu Qatal"]  # no anchor: two candidates
    same_source = build(same, sources={"C1": "S1", "C2": "S1"})[0]
    assert people(same_source) == ["Abu Qatal"]
    role = [
        triple("Abu Qatal", "member_of", "Lashkar-e-Taiba", "C1"),
        triple("Qatal, Abu", "member_of", "Lashkar-i-Taiba", "C2"),
    ]
    assert people(build(role)[0]) == ["Abu Qatal"]  # same role, same organisation
    other_role = [
        triple("Muhammad Iqbal", "member_of", "Lashkar-e-Taiba", "C1"),
        triple("IQBAL, Muhammad", "linked_to", "Lashkar-e-Taiba", "C2"),
    ]
    assert len(people(build(other_role)[0])) == 2  # a different role is not an anchor
    record = [
        triple("Hafiz Saeed", "founded", "Lashkar-e-Taiba", "C1", ids=(["wikidata:Q2"], [])),
        triple(
            "Hafiz Muhammad Saeed",
            "designated_by",
            "UN Security Council",
            "C2",
            ids=(["wikidata:Q2"], []),
        ),
    ]
    assert len(people(build(record)[0])) == 1  # one identifier, two names
    alias = [*same, triple("Abu Qatal", "alias_of", "Qatal Sindhi", "C3", kinds=(PERSON, PERSON))]
    merged = build(alias, sources={"C1": "S1", "C2": "S2", "C3": "S1"})[0]
    assert people(merged) == ["Abu Qatal", "Abu Qatal"]
    assert any("Qatal Sindhi" in entity.aliases for entity in merged)


@pytest.mark.ac("AG3-AC2")
def test_organisations_merge_on_shared_names_and_aliases():
    record = Triple.model_validate(
        {
            "subject": {
                "name": "LASHKAR E-TAYYIBA",
                "kind": ORG,
                "ids": ["ofac:7140"],
                "aliases": ["LASHKAR-I-TAIBA", "JAMAAT-UD-DAWA"],
            },
            "relation": "designated_by",
            "object": {"name": "US Treasury OFAC", "kind": ORG, "ids": ["OFAC"]},
            "claim_refs": ["C1"],
            "basis": "record",
        }
    )
    entities, _ = build(
        [
            record,
            triple("Abu Qatal", "member_of", "Lashkar-e-Taiba", "C2"),
            triple("Hafiz Saeed", "leader_of", "Jamaat-ud-Dawa", "C3"),
        ]
    )
    orgs = [entity for entity in entities if entity.kind == ORG]
    assert sorted(e.name for e in orgs) == ["LASHKAR E-TAYYIBA", "US Treasury OFAC"]
    let = next(e for e in orgs if e.ids == ["ofac:7140"])
    assert {"Lashkar-e-Taiba", "Jamaat-ud-Dawa"} <= set(let.aliases)


# ---- AG3-AC3: status follows the independence rules ---------------------------------


@pytest.mark.ac("AG3-AC3")
def test_link_status_follows_independent_origins_records_and_assessments():
    triples = [
        triple("Abu Qatal", "member_of", "Lashkar-e-Taiba", "C1"),
        triple("Abu Qatal", "member_of", "Lashkar-e-Taiba", "C2"),
        triple("Abu Qatal", "killed_in", "Jhelum attack", "C3", kinds=(PERSON, "event")),
        triple(
            "Lashkar-e-Taiba",
            "designated_by",
            "UN Security Council",
            "C4",
            kinds=(ORG, ORG),
            basis="record",
        ),
    ]
    sources = {"C1": "S1", "C2": "S2", "C3": "S1", "C4": "S9"}
    origins = {"C1": "dawn.com", "C2": "thehindu.com", "C3": "dawn.com", "C4": "un.org"}
    same_site = {**origins, "C2": "dawn.com"}
    _, links = build(triples, sources, origins)
    status = {(link.relation, link.status) for link in links}
    assert status == {
        ("member_of", "corroborated"),
        ("killed_in", "single source"),
        ("designated_by", "record"),
    }
    _, again = build(triples, sources, same_site)  # two pages of one site are one origin
    assert ("member_of", "single source") in {(link.relation, link.status) for link in again}
    hunch = graph.assessed("Jhelum attack", "linked_to", "Lashkar-e-Taiba", ["C3"], ["C5", "C3"])
    unknown = graph.assessed("Nobody Known", "linked_to", "Lashkar-e-Taiba", ["C3"], [])
    repeat = graph.assessed("Abu Qatal", "member_of", "Lashkar-e-Taiba", ["C1"], [])
    _, links = build([*triples, hunch, unknown, repeat], sources, origins)
    assessed = [link for link in links if link.basis == "assessed"]
    assert len(assessed) == 1  # unknown names and repeats of stated links are dropped
    assert (assessed[0].status, assessed[0].claim_refs, assessed[0].against) == (
        "assessment",
        ["C3"],
        ["C5"],
    )
    assert graph.assessed("A", "alias_of", "B", ["C1"], []) is None
    assert graph.assessed("A", "linked_to", "B", [], []) is None  # needs claims for it


# ---- records add links by code ----------------------------------------------------


async def test_records_add_designation_founder_and_link_relations(tmp_path):
    def script(ref, step, user):
        if ref == "Q1" and step == 1:
            return {
                "calls": [
                    {"tool": "sanctions_search", "args": {"name": "Lashkar-e-Taiba"}},
                    {"tool": "wiki_lookup", "args": {"query": "Lashkar-e-Taiba"}},
                ]
            }
        return DONE

    store = Store(tmp_path)
    model = Researcher(script=script)
    records = (
        SanctionsSearch(lists(**{SUMMARY: LET_SUMMARY, WIKIDATA: LET_ENTITY}), tmp_path / "lists"),
        WikiLookup(Wiki(summary=LET_SUMMARY)),
    )
    inv = Investigation(id=store.new_id(), brief="Is Lashkar-e-Taiba under sanctions?")
    model.usage = inv.usage
    tools = Tools(model=model, searcher=FakeSearch(), fetcher=FakeFetcher(), records=records)
    inv = await Agent(inv, tools, store, Limits()).run()
    assert inv.status == "done", inv.error
    name = {entity.ref: entity.name for entity in inv.entities}
    let = next(e for e in inv.entities if "ofac:7140" in e.ids)
    assert {"un:QDe.118", "wikidata:Q736955"} <= set(let.ids)  # one organisation
    name[let.ref] = "LET"  # whichever spelling the card shows
    found = {(name[k.subject], k.relation, name[k.object], k.status) for k in inv.links}
    assert ("LET", "designated_by", "US Treasury OFAC", "record") in found
    assert ("LET", "designated_by", "UN Security Council", "record") in found
    assert ("Hafiz Muhammad Saeed", "founded", "LET", "record") in found
    # the UN note "Associated with Hafiz Muhammad Saeed (QDi.263)" links him by his UN number
    assert ("Hafiz Muhammad Saeed", "linked_to", "LET", "record") in found
    for link in inv.links:
        for ref in link.claim_refs:  # every link rests on an anchored claim
            claim = inv.claim(ref)
            text = store.text(inv.source(claim.source_ref).text_sha256)
            assert text[claim.start : claim.end] == claim.quote


# ---- AG3-AC4: the links map ---------------------------------------------------------


def mapped(tmp_path):
    store = Store(tmp_path)
    inv = Investigation(id=store.new_id(), brief="Who leads the group?", status="done")
    inv.questions = [Question(ref="Q1", text="Who leads the group?")]
    inv.report = Report()
    inv.entities = [
        Entity(ref="E1", kind=PERSON, name="<script>alert(1)</script>"),
        Entity(ref="E2", kind=ORG, name="Lashkar-e-Taiba"),
        Entity(ref="E3", kind="event", name="Jhelum attack"),
    ]
    inv.links = [
        Link(
            ref="L1",
            subject="E1",
            relation="leader_of",
            object="E2",
            claim_refs=["C1"],
            basis="stated",
            status="corroborated",
            origins=["a.example", "b.example"],
        ),
        Link(
            ref="L2",
            subject="E3",
            relation="linked_to",
            object="E2",
            claim_refs=["C2"],
            against=["C3"],
            basis="assessed",
            status="assessment",
        ),
    ]
    store.save(inv)
    return inv


@pytest.mark.ac("AG3-AC4")
def test_the_map_renders_every_link_with_its_evidence_and_escapes_text(tmp_path):
    inv = mapped(tmp_path)
    settings = AppSettings(data_dir=str(tmp_path), tavily_api_key="t", groq_api_key="g")
    page = TestClient(create_app(settings)).get(f"/investigations/{inv.id}").text
    assert '<svg class="board"' in page
    assert "Evidence board" in page
    for link in inv.links:
        # each string opens its evidence: in the case notes, or as a link without scripts
        assert f'<a href="#{link.ref}" data-ref="{link.ref}" data-linked=' in page
        assert f'<template id="note-{link.ref}">' in page
        assert f'<tr id="{link.ref}"' in page
    assert 'data-ref="C1"' in page
    assert "Against: " in page
    assert "Lantern's assessment, not a fact stated by a source." in page
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert 'data-kind="event"' in page
    assert 'data-status="assessment"' in page
    markdown = to_markdown(inv)
    assert "## Links" in markdown
    assert "**L2** Jhelum attack — linked to → Lashkar-e-Taiba *(Lantern's assessment" in markdown


@pytest.mark.ac("AG3-AC4")
def test_the_layout_is_deterministic_and_inside_the_drawing(tmp_path):
    inv = mapped(tmp_path)
    nodes, edges = linkmap.view(inv)
    again, _ = linkmap.view(inv)
    assert [(n.x, n.y) for n in nodes] == [(n.x, n.y) for n in again]
    assert all(linkmap.MARGIN <= n.x <= linkmap.WIDTH - linkmap.MARGIN for n in nodes)
    assert all(linkmap.MARGIN <= n.y <= linkmap.HEIGHT - linkmap.MARGIN for n in nodes)
    assert len(edges) == 2
    assert edges[0].kinds == f"{PERSON} {ORG}"
    assert linkmap.view(Investigation(id="x", brief="y")) == ([], [])


def test_people_sharing_a_name_without_an_anchor_are_explained():
    entities = [
        Entity(ref="E1", kind=PERSON, name="HAFIZ MUHAMMAD SAEED", ids=["un:QDi.263"]),
        Entity(ref="E2", kind=PERSON, name="Hafiz Muhammad Saeed", ids=["wikidata:Q2735272"]),
        Entity(ref="E3", kind=PERSON, name="SAEED, Muhammad", aliases=["SAEED, Hafiz Muhammad"]),
        Entity(ref="E4", kind=PERSON, name="KHAN, Hafiz Saeed"),
        Entity(ref="E5", kind=ORG, name="Saeed Trust"),
    ]
    assert linkmap.namesakes(entities) == [("HAFIZ MUHAMMAD SAEED", 3)]


def test_a_page_without_links_has_no_map(tmp_path):
    store = Store(tmp_path)
    inv = Investigation(id=store.new_id(), brief="Floods?", status="done")
    store.save(inv)
    settings = AppSettings(data_dir=str(tmp_path), tavily_api_key="t", groq_api_key="g")
    assert "Links map" not in TestClient(create_app(settings)).get(f"/investigations/{inv.id}").text
    assert "## Links" not in to_markdown(inv)
    assert fakes.PAGES  # the shared fakes stay importable here


def test_cards_wrap_names_tilt_slightly_and_strings_sag():
    assert linkmap.card_lines("Lashkar-e-Taiba") == ("Lashkar-e-Taiba",)
    assert linkmap.card_lines("TATA MOTORS PASSENGER VEHICLES LIMITED") == (
        "TATA MOTORS PASSENGER",
        "VEHICLES LIMITED",
    )
    assert linkmap.card_lines("HAFIZ MUHAMMAD SAEED", 16) == ("HAFIZ MUHAMMAD", "SAEED")
    assert all(len(line) <= 22 for line in linkmap.card_lines("A" * 40 + " B " + "C" * 40))
    assert {linkmap.tilt(f"E{n}") for n in range(1, 50)} <= set(range(-4, 5))
    path, (_, my) = linkmap.string((100.0, 100.0), (300.0, 100.0))
    assert path.startswith("M100.0,100.0 Q200.0,")
    assert my > 100  # the string hangs below its pins


def test_cards_never_overlap_and_stay_on_the_board():
    refs = [f"E{n}" for n in range(1, 13)]
    crowded = {ref: [600.0, 380.0] for ref in refs}  # every card on the same spot
    placed = linkmap.separate(refs, crowded)
    for i, a in enumerate(refs):
        for b in refs[i + 1 :]:
            (ax, ay), (bx, by) = placed[a], placed[b]
            assert abs(ax - bx) >= linkmap.CARD_W or abs(ay - by) >= linkmap.CARD_H
    assert all(
        linkmap.MARGIN <= x <= linkmap.WIDTH - linkmap.MARGIN
        and linkmap.MARGIN <= y <= linkmap.HEIGHT - linkmap.MARGIN
        for x, y in placed.values()
    )


def test_overlapping_namesake_groups_are_listed_once():
    entities = [
        Entity(ref="E4", kind=PERSON, name="SAEED, Muhammad", aliases=["SAEED, Hafiz Muhammad"]),
        Entity(ref="E5", kind=PERSON, name="HAFIZ MUHAMMAD SAEED"),
        Entity(ref="E6", kind=PERSON, name="Muhammad Saeed"),
    ]
    assert linkmap.namesakes(entities) == [("SAEED, Muhammad", 3)]


def test_card_notes_say_what_the_evidence_means_in_plain_words(tmp_path):
    store = Store(tmp_path)
    inv = Investigation(id=store.new_id(), brief="Who leads the group?")
    common = {
        "fetched_at": now(),
        "size": 1,
        "reliability": "A",
        "reliability_reason": "r",
        "sha256": "x",
        "text_sha256": "y",
    }
    inv.sources = [
        Source(
            ref="S1",
            url="https://sanctionssearch.ofac.treas.gov/x",
            domain="treas.gov",
            kind="record",
            title="US Treasury OFAC SDN list: LASHKAR E-TAYYIBA",
            **common,
        ),
        Source(ref="S2", url="https://dawn.com/a", domain="dawn.com", **common),
        Source(ref="S3", url="https://thehindu.com/b", domain="thehindu.com", **common),
    ]
    claim = {"question_refs": ["Q1"], "quote": "q", "start": 0, "end": 1}
    inv.claims = [
        Claim(
            ref="C1",
            source_ref="S1",
            statement="LASHKAR E-TAYYIBA is on the OFAC SDN list as an entity under FTO, SDGT.",
            **claim,
        ),
        Claim(
            ref="C2", source_ref="S2", statement="Abu Qatal was a commander of the group.", **claim
        ),
        Claim(
            ref="C3", source_ref="S3", statement="Abu Qatal led fighters for the group.", **claim
        ),
    ]
    inv.entities = [
        Entity(
            ref="E1", kind=ORG, name="LASHKAR E-TAYYIBA", aliases=["LeT", "Army of the Pure", "JuD"]
        ),
        Entity(ref="E2", kind=ORG, name="US Treasury OFAC"),
        Entity(ref="E3", kind=PERSON, name="Abu Qatal"),
        Entity(ref="E4", kind=PERSON, name="Qatal, Abu"),
    ]
    inv.links = [
        Link(
            ref="L1",
            subject="E1",
            relation="designated_by",
            object="E2",
            claim_refs=["C1"],
            basis="record",
            status="record",
            origins=["ofac.treas.gov"],
        ),
        Link(
            ref="L2",
            subject="E3",
            relation="leader_of",
            object="E1",
            claim_refs=["C2", "C3"],
            basis="stated",
            status="corroborated",
            origins=["dawn.com", "thehindu.com"],
        ),
        Link(
            ref="L3",
            subject="E4",
            relation="member_of",
            object="E1",
            claim_refs=["C2"],
            basis="stated",
            status="single source",
            origins=["dawn.com"],
        ),
    ]
    notes, facts = board.stories(inv)
    let = notes["E1"]
    assert let.kind == "Organisation"
    assert let.summary == (
        "LASHKAR E-TAYYIBA is an organisation. It is also known as LeT and Army of the Pure and "
        "1 other name. Lantern found 3 connections for LASHKAR E-TAYYIBA: 1 from official "
        "records; 1 confirmed by two or more independent sources; 1 from a single source."
    )
    assert (
        facts["L1"].sentence == "LASHKAR E-TAYYIBA is on a sanctions list kept by US Treasury OFAC."
    )
    assert facts["L1"].strength == "An official record says this (US Treasury OFAC SDN list)."
    assert facts["L1"].said == [
        (
            "LASHKAR E-TAYYIBA is on the OFAC (the US Treasury's sanctions office) SDN (Specially "
            "Designated Nationals, the US Treasury's main sanctions list) list as an entity under "
            "FTO (Foreign Terrorist Organization), SDGT (Specially Designated Global Terrorist)."
        )
    ]
    assert facts["L2"].sentence == "Abu Qatal leads LASHKAR E-TAYYIBA."
    assert facts["L2"].strength == "2 independent sources report this: dawn.com, thehindu.com."
    assert (
        facts["L3"].strength == "Only one source reports this (dawn.com), so treat it with caution."
    )
    assert notes["E3"].caution.startswith("Careful: 1 other card on this board shares this name.")
    assert notes["E2"].caution == ""
    assert board.gloss("SDGT and SDGT") == "SDGT (Specially Designated Global Terrorist) and SDGT"


def test_every_card_says_why_it_is_here_and_how_it_reaches_the_subject(tmp_path):
    store = Store(tmp_path)
    inv = Investigation(
        id=store.new_id(), brief="Is Lashkar-e-Taiba under sanctions, and who founded it?"
    )
    inv.questions = [
        Question(ref="Q1", text="Is Lashkar-e-Taiba under sanctions?"),
        Question(ref="Q2", text="Who founded it?"),
    ]
    common = {
        "fetched_at": now(),
        "size": 1,
        "reliability": "A",
        "reliability_reason": "r",
        "sha256": "x",
        "text_sha256": "y",
    }
    inv.sources = [
        Source(
            ref="S1",
            url="https://un.org/x",
            domain="un.org",
            kind="record",
            title="UN Security Council Consolidated List: LASHKAR-E-TAYYIBA",
            **common,
        ),
        Source(
            ref="S2",
            url="https://www.wikidata.org/wiki/Q1",
            domain="wikidata.org",
            kind="record",
            title="Wikidata: Lashkar-e-Taiba",
            **common,
        ),
        Source(ref="S3", url="https://dawn.com/c", domain="dawn.com", **common),
    ]
    claim = {"quote": "q", "start": 0, "end": 1}
    inv.claims = [
        Claim(ref="C1", source_ref="S1", question_refs=["Q1"], statement="Listed.", **claim),
        Claim(ref="C2", source_ref="S2", question_refs=["Q2"], statement="Founded by.", **claim),
        Claim(ref="C3", source_ref="S3", question_refs=["Q2"], statement="A rally.", **claim),
    ]
    inv.entities = [
        Entity(ref="E1", kind=ORG, name="LASHKAR-E-TAYYIBA", aliases=["Lashkar-e-Taiba"]),
        Entity(ref="E2", kind=ORG, name="UN Security Council"),
        Entity(ref="E3", kind=PERSON, name="Hafiz Muhammad Saeed"),
        Entity(ref="E4", kind="event", name="Lahore rally"),
        Entity(ref="E5", kind="place", name="Lahore"),
    ]
    inv.links = [
        Link(
            ref="L1",
            subject="E1",
            relation="designated_by",
            object="E2",
            claim_refs=["C1"],
            basis="record",
            status="record",
        ),
        Link(
            ref="L2",
            subject="E3",
            relation="founded",
            object="E1",
            claim_refs=["C2"],
            basis="record",
            status="record",
        ),
        Link(
            ref="L3",
            subject="E4",
            relation="located_in",
            object="E5",
            claim_refs=["C3"],
            basis="stated",
            status="single source",
            origins=["dawn.com"],
        ),
    ]
    assert board.subject(inv) == "E1"  # its alias is written in the research question
    notes, _ = board.stories(inv)
    assert (notes["E1"].steps, notes["E1"].tag) == (0, "★ subject of this case")
    assert notes["E1"].connection.startswith("This is what the investigation is about")
    assert notes["E3"].tag == "1 step from the subject"
    assert notes["E3"].why == (
        "The evidence gathered for Q2, “Who founded it?” mentions it: 1 claim, from Wikidata."
    )
    assert notes["E3"].connection == (
        "Hafiz Muhammad Saeed founded LASHKAR-E-TAYYIBA. That is how it connects to "
        "LASHKAR-E-TAYYIBA, the subject of this case (1 string away)."
    )
    assert (notes["E5"].steps, notes["E5"].tag) == (None, "no link to the subject yet")
    assert "treat its relevance as unconfirmed" in notes["E5"].connection
    nodes, _ = linkmap.view(inv)
    centre = next(node for node in nodes if node.entity.ref == "E1")
    assert abs(centre.x - linkmap.WIDTH / 2) < linkmap.WIDTH / 3  # the subject sits near the middle
    inv.status = "done"
    inv.report = Report()
    store.save(inv)
    settings = AppSettings(data_dir=str(tmp_path), tavily_api_key="t", groq_api_key="g")
    page = TestClient(create_app(settings)).get(f"/investigations/{inv.id}").text
    assert "THE CASE" in page
    assert "card subject" in page or 'k-organisation subject"' in page
    assert 'data-linked="no"' in page
    assert "only what is linked to the subject" in page
    assert "Why it is on the board" in page
    assert "How it connects to what you searched" in page


def test_sharing_a_sanctions_list_is_not_a_connection_and_wikidata_is_background():
    links = [
        Link(
            ref="L1",
            subject="E1",
            relation="designated_by",
            object="E2",
            claim_refs=["C1"],
            basis="record",
            status="record",
        ),
        Link(
            ref="L2",
            subject="E3",
            relation="designated_by",
            object="E2",
            claim_refs=["C2"],
            basis="record",
            status="record",
        ),
        Link(
            ref="L3",
            subject="E4",
            relation="founded",
            object="E1",
            claim_refs=["C3"],
            basis="record",
            status="record",
        ),
    ]
    reach = board.paths(links, "E1")
    assert set(reach) == {"E1", "E2", "E4"}  # E3 shares only the list keeper E2 with E1
    assert board.strength(links[2], ["Wikidata"], official=False).startswith(
        "A reference work says this (Wikidata): it is edited by volunteers"
    )
    assert board.strength(links[0], ["UN Security Council Consolidated List"]) == (
        "An official record says this (UN Security Council Consolidated List)."
    )
