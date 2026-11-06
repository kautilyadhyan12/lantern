"""The records toolbox: official sanctions lists and Wikipedia/Wikidata background.

The sample responses are abridged copies of the real files and API answers fetched on
2026-11-05 (OFAC SDN.CSV and ALT.CSV, the UN consolidated.xml, the Wikipedia page summary
and Wikidata entities). The individuals in them are invented, so no real person's details
sit in this public repository.
"""

import hashlib
import json
from datetime import date

import httpx
import pytest

from lantern import prompts
from lantern.agent.loop import Agent
from lantern.config import AppSettings
from lantern.egress import Fetcher, FetchError, Page
from lantern.models import Investigation
from lantern.pipeline import Limits, Tools
from lantern.runtime import record_tools
from lantern.store import Store
from lantern.tools.adapters.sanctions import OFAC, UN, SanctionsSearch, un_entries
from lantern.tools.adapters.wiki import SUMMARY, WIKIDATA, WikiLookup
from lantern.tools.base import ToolContext, ToolError

from .fakes import FakeFetcher, FakeSearch
from .test_agent import DONE, Researcher

CTX = ToolContext()
SDN = (
    b'7140,"LASHKAR E-TAYYIBA",-0- ,"FTO] [SDGT",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,"Secondary '
    b"sanctions risk: section 1(b) of Executive Order 13224; a.k.a. 'JUD'; a.k.a. 'THE "
    b"RESISTANCE FRONT'.\"\r\n"
    b'90001,"DOE, Example","individual","SDGT",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,"DOB 01 Jan '
    b"1970; POB Sampletown; Passport X1234567 (Nowhere); National ID No. 9999999999; a.k.a. "
    b"'EXAMPLE DOE'; Linked To: LASHKAR E-TAYYIBA.\"\r\n"
    b"\x1a"
)
ALT = (
    b'7140,5059,"aka","LASHKAR E-TOIBA",-0- \r\n'
    b'7140,5060,"aka","LASHKAR-I-TAIBA",-0- \r\n'
    b'7140,9248,"aka","JAMAAT-UD-DAWA",-0- \r\n'
    b'7140,38439,"aka","MILLI MUSLIM LEAGUE",-0- \r\n'
)
XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<CONSOLIDATED_LIST dateGenerated="2026-11-05T05:09:49.640Z">
  <INDIVIDUALS>
    <INDIVIDUAL>
      <DATAID>1</DATAID><FIRST_NAME>EXAMPLE</FIRST_NAME><SECOND_NAME>PERSON</SECOND_NAME>
      <UN_LIST_TYPE>Al-Qaida</UN_LIST_TYPE><REFERENCE_NUMBER>QDi.999</REFERENCE_NUMBER>
      <LISTED_ON>2012-03-14</LISTED_ON>
      <COMMENTS1>Father's name is Sample Parent. Mother's name is Sample Mother.</COMMENTS1>
      <INDIVIDUAL_ALIAS><QUALITY>Good</QUALITY><ALIAS_NAME>E. Person</ALIAS_NAME></INDIVIDUAL_ALIAS>
      <INDIVIDUAL_DATE_OF_BIRTH><DATE>1970-01-01</DATE></INDIVIDUAL_DATE_OF_BIRTH>
      <INDIVIDUAL_DOCUMENT><NUMBER>P0000001</NUMBER></INDIVIDUAL_DOCUMENT>
    </INDIVIDUAL>
  </INDIVIDUALS>
  <ENTITIES>
    <ENTITY>
      <DATAID>114076</DATAID><FIRST_NAME>LASHKAR-E-TAYYIBA</FIRST_NAME>
      <UN_LIST_TYPE>Al-Qaida</UN_LIST_TYPE><REFERENCE_NUMBER>QDe.118</REFERENCE_NUMBER>
      <LISTED_ON>2005-05-02</LISTED_ON>
      <COMMENTS1>Associated with Hafiz Muhammad Saeed (QDi.263) who is the leader of
        Lashkar-e-Tayyiba INTERPOL-UN Security Council Special Notice:https://www.interpol.int/
      </COMMENTS1>
      <ENTITY_ALIAS><QUALITY>a.k.a.</QUALITY><ALIAS_NAME>Lashkar-i-Taiba</ALIAS_NAME></ENTITY_ALIAS>
      <ENTITY_ALIAS><QUALITY>a.k.a.</QUALITY><ALIAS_NAME>Army of the Pure</ALIAS_NAME>
      </ENTITY_ALIAS>
    </ENTITY>
  </ENTITIES>
</CONSOLIDATED_LIST>"""


class Data:
    """A fake official data service: answers by URL prefix and records every download."""

    def __init__(self, routes):
        self.routes, self.urls = routes, []

    async def fetch_data(self, url, accept, *, max_bytes, seconds=60.0):
        self.urls.append(url)
        for prefix, answer in self.routes.items():
            if url.startswith(prefix):
                if isinstance(answer, Exception):
                    raise answer
                body = answer if isinstance(answer, bytes) else json.dumps(answer).encode()
                return Page(url=url, content_type=accept[0], body=body)
        raise FetchError("The data service answered HTTP 404.", "refused")


def lists(**changes):
    return Data({f"{OFAC}/SDN.CSV": SDN, f"{OFAC}/ALT.CSV": ALT, UN: XML, **changes})


# ---- sanctions lists ----------------------------------------------------------------


@pytest.mark.ac("AG2-AC1")
@pytest.mark.parametrize("name", ["Lashkar-e-Tayyiba", "Jamaat-ud-Dawa", "Lashkar-e-Taiba"])
async def test_an_organisation_is_found_by_name_or_alias_in_both_lists(tmp_path, name):
    tool = SanctionsSearch(lists(), tmp_path, today=lambda: date(2026, 11, 5))
    result = await tool.run(tool.args_model(name=name), CTX)
    by_origin = {draft.origin: draft for draft in result.sources}
    if name == "Jamaat-ud-Dawa":  # an alias on the OFAC list only
        assert set(by_origin) == {"ofac.treas.gov"}
    else:
        assert set(by_origin) == {"ofac.treas.gov", "un.org"}
    ofac = by_origin["ofac.treas.gov"]
    assert ofac.kind == "record"
    assert ofac.grade == ("A", "Official sanctions list")
    assert ofac.url == "https://sanctionssearch.ofac.treas.gov/Details.aspx?id=7140"
    assert ofac.record_claims[0] == (
        "LASHKAR E-TAYYIBA is on the US Treasury OFAC SDN list (entry 7140) as an entity "
        "under FTO, SDGT."
    )
    assert "JAMAAT-UD-DAWA; MILLI MUSLIM LEAGUE; JUD; THE RESISTANCE FRONT" in ofac.record_claims[1]
    assert all(claim in ofac.text for claim in ofac.record_claims)


@pytest.mark.ac("AG2-AC1")
async def test_the_un_listing_note_is_kept_for_organisations_without_the_notice_link(tmp_path):
    tool = SanctionsSearch(lists(), tmp_path, today=lambda: date(2026, 11, 5))
    result = await tool.run(tool.args_model(name="Army of the Pure"), CTX)
    un = next(draft for draft in result.sources if draft.origin == "un.org")
    assert un.url == f"{UN}#QDe.118"
    assert un.published == "2005-05-02"
    assert un.record_claims[-1] == (
        "The UN listing of LASHKAR-E-TAYYIBA notes: Associated with Hafiz Muhammad Saeed "
        "(QDi.263) who is the leader of Lashkar-e-Tayyiba"
    )


@pytest.mark.ac("AG2-AC1")
async def test_people_match_exactly_and_keep_no_personal_details(tmp_path):
    tool = SanctionsSearch(lists(), tmp_path, today=lambda: date(2026, 11, 5))
    found = await tool.run(tool.args_model(name="Example Doe"), CTX)  # word order ignored
    [ofac] = found.sources
    assert ofac.record_claims[0].startswith("An individual named DOE, Example is on the US")
    assert "A matching name alone does not show that this is the same person" in ofac.text
    assert "The list links DOE, Example to LASHKAR E-TAYYIBA." in ofac.record_claims
    un = await tool.run(tool.args_model(name="Example Person"), CTX)
    kept = (
        b"".join(d.body for d in (ofac, *un.sources))
        + "".join(d.text for d in (ofac, *un.sources)).encode()
    )
    for detail in (b"1970", b"Sampletown", b"X1234567", b"9999999999", b"P0000001", b"Sample"):
        assert detail not in kept
    # Initials still count for people: "E Person" is a listed alias, "Person" alone is not.
    assert (await tool.run(tool.args_model(name="E. Person"), CTX)).sources
    assert not (await tool.run(tool.args_model(name="Person"), CTX)).sources


@pytest.mark.ac("AG2-AC1")
async def test_each_list_is_downloaded_once_a_day_and_kept_with_its_sha256(tmp_path):
    data = lists()
    day = [date(2026, 11, 5)]
    tool = SanctionsSearch(data, tmp_path, today=lambda: day[0])
    first = await tool.run(tool.args_model(name="Lashkar-e-Tayyiba"), CTX)
    assert len(data.urls) == 3
    assert hashlib.sha256(SDN).hexdigest() in first.sources[0].text
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "OFAC-ALT-2026-11-05",
        "OFAC-SDN-2026-11-05",
        "UN-2026-11-05",
    ]
    again = SanctionsSearch(data, tmp_path, today=lambda: day[0])  # a later run, same day
    await again.run(again.args_model(name="Lashkar-e-Tayyiba"), CTX)
    assert len(data.urls) == 3
    day[0] = date(2026, 11, 6)
    tomorrow = SanctionsSearch(data, tmp_path, today=lambda: day[0])
    await tomorrow.run(tomorrow.args_model(name="Lashkar-e-Tayyiba"), CTX)
    assert len(data.urls) == 6
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "OFAC-ALT-2026-11-06",
        "OFAC-SDN-2026-11-06",
        "UN-2026-11-06",
    ]


@pytest.mark.ac("AG2-AC4")
async def test_no_match_and_failures_are_plain(tmp_path):
    tool = SanctionsSearch(lists(), tmp_path, today=lambda: date(2026, 11, 5))
    none = await tool.run(tool.args_model(name="Assam State Disaster Management"), CTX)
    assert none.sources == []
    assert none.summary.startswith("Sanctions lists: no entry named “Assam State Disaster")
    down = SanctionsSearch(
        lists(**{UN: FetchError("The data service answered HTTP 503.", "refused")}),
        tmp_path / "other",
    )
    with pytest.raises(ToolError, match=r"The UN list could not be downloaded: .*HTTP 503"):
        await down.run(down.args_model(name="Lashkar-e-Tayyiba"), CTX)
    with pytest.raises(ToolError, match="document type declaration"):
        un_entries(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>')
    with pytest.raises(ToolError, match="not valid XML"):
        un_entries(b"<CONSOLIDATED_LIST><broken")


# ---- Wikipedia and Wikidata ---------------------------------------------------------

LET_SUMMARY = {
    "type": "standard",
    "title": "Lashkar-e-Taiba",
    "wikibase_item": "Q736955",
    "extract": "Lashkar-e-Taiba (LeT) is a Pakistani militant organisation founded in 1985.",
    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Lashkar-e-Taiba"}},
}


def claim(prop, value):
    data = value if isinstance(value, dict) else {"entity-type": "item", "id": value}
    return {prop: [{"mainsnak": {"datavalue": {"value": data}}}]}


LET_ENTITY = {
    "entities": {
        "Q736955": {
            "labels": {"en": {"value": "Lashkar-e-Taiba"}, "ur": {"value": "لشکر طیبہ"}},
            "aliases": {"en": [{"value": "LeT"}, {"value": "Lashkar-e-Tayyiba"}]},
            "descriptions": {"en": {"value": "Pakistani militant organisation"}},
            "claims": {**claim("P31", "Q17127659"), **claim("P112", "Q2735272")},
        }
    }
}
PERSON = {
    "entities": {
        "Q90001": {
            "labels": {"en": {"value": "Example Leader"}},
            "aliases": {},
            "descriptions": {"en": {"value": "a description that may mention protected traits"}},
            "claims": {
                **claim("P31", "Q5"),
                **claim("P140", "Q432"),  # religion: never read
                **claim("P172", "Q90009"),  # ethnic group: never read
                **claim("P39", "Q90002"),
                **claim("P570", {"time": "+2026-03-15T00:00:00Z", "precision": 11}),
                **claim("P20", "Q1445"),
            },
        }
    }
}
LABELS = {
    "entities": {
        qid: {"labels": {"en": {"value": label}}}
        for qid, label in {
            "Q17127659": "terrorist organization",
            "Q2735272": "Hafiz Muhammad Saeed",
            "Q90002": "commander",
            "Q1445": "Lahore",
            "Q432": "Islam",
        }.items()
    }
}


class Wiki(Data):
    """Answers the summary, search and entity calls; `labels_asked` keeps the ids whose
    labels were requested, to prove which properties were read."""

    def __init__(self, summary=None, entity=LET_ENTITY, search=None):
        super().__init__({})
        self.summary, self.entity, self.search, self.labels_asked = summary, entity, search, []

    async def fetch_data(self, url, accept, *, max_bytes, seconds=60.0):
        self.urls.append(url)
        if url.startswith(SUMMARY):
            answer = self.summary
        elif "wbsearchentities" in url:
            answer = self.search
        elif "props=labels&" in url:
            self.labels_asked += url.split("ids=")[1].split("&")[0].split("%7C")
            answer = LABELS
        else:
            answer = self.entity
        if answer is None:
            raise FetchError("The data service answered HTTP 404.", "refused")
        return Page(url=url, content_type="application/json", body=json.dumps(answer).encode())


@pytest.mark.ac("AG2-AC2")
async def test_wiki_lookup_gives_background_with_code_generated_facts():
    tool = WikiLookup(Wiki(summary=LET_SUMMARY))
    result = await tool.run(tool.args_model(query="Lashkar-e-Taiba"), CTX)
    [draft] = result.sources
    assert (draft.kind, draft.grade[0], draft.origin) == ("record", "C", "wikidata.org")
    assert draft.url == "https://www.wikidata.org/wiki/Q736955"
    assert draft.record_claims == (
        "Wikidata describes Lashkar-e-Taiba (Q736955) as: Pakistani militant organisation.",
        "Wikidata lists these other names for Lashkar-e-Taiba: لشکر طیبہ; LeT; Lashkar-e-Tayyiba.",
        "Wikidata records Lashkar-e-Taiba as an instance of: terrorist organization.",
        "Wikidata records Lashkar-e-Taiba as founded by: Hafiz Muhammad Saeed.",
    )
    assert "Wikipedia summary (https://en.wikipedia.org/wiki/Lashkar-e-Taiba)" in draft.text
    assert result.summary == "Wikidata: Lashkar-e-Taiba (https://www.wikidata.org/wiki/Q736955)."


@pytest.mark.ac("AG2-AC2")
async def test_protected_traits_are_never_read_and_people_keep_only_listed_facts():
    data = Wiki(
        summary=None,
        entity=PERSON,
        search={
            "search": [
                {"id": "Q90001", "match": {"text": "Example Leader"}},
            ]
        },
    )
    tool = WikiLookup(data)
    [draft] = (await tool.run(tool.args_model(query="Example Leader"), CTX)).sources
    assert "Q432" not in data.labels_asked  # religion
    assert "Q90009" not in data.labels_asked  # ethnic group
    assert "Islam" not in draft.text
    assert "protected traits" not in draft.text  # no description for people
    assert "Wikipedia summary" not in draft.text
    assert draft.record_claims == (
        (
            "Wikidata entry Q90001 is a person named Example Leader. A matching name alone "
            "does not show that this is the same person as in the evidence."
        ),
        "Wikidata records Example Leader as having held the position: commander.",
        "Wikidata records the date of death of Example Leader as 2026-03-15.",
        "Wikidata records the place of death of Example Leader as Lahore.",
    )


@pytest.mark.ac("AG2-AC4")
async def test_ambiguous_missing_and_near_matches_give_no_entry():
    ambiguous = WikiLookup(Wiki(summary={"type": "disambiguation", "title": "Saeed"}))
    out = await ambiguous.run(ambiguous.args_model(query="Saeed"), CTX)
    assert (out.sources, out.summary.startswith("Wikipedia has several subjects")) == ([], True)
    near = Wiki(search={"search": [{"id": "Q1", "match": {"text": "Example Leaders Club"}}]})
    tool = WikiLookup(near)
    out = await tool.run(tool.args_model(query="Example Leader"), CTX)
    assert out.sources == []
    assert out.summary == "No Wikipedia or Wikidata entry for “Example Leader”."
    broken = WikiLookup(Data({SUMMARY: FetchError("Could not connect.", "unreachable")}))
    with pytest.raises(ToolError, match="Wikipedia or Wikidata could not be reached"):
        await broken.run(broken.args_model(query="Lashkar-e-Taiba"), CTX)


@pytest.mark.ac("AG2-AC2")
async def test_official_data_is_fetched_safely_with_lanterns_contact_and_no_robots_check():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=json.dumps(LET_SUMMARY).encode(),
        )

    async def resolver(host, port):
        return ["93.184.215.14"]

    agent = AppSettings().user_agent
    fetcher = Fetcher(
        agent, transport=httpx.MockTransport(handler), resolver=resolver, host_interval=0
    )
    page = await fetcher.fetch_data(
        f"{SUMMARY}Lashkar-e-Taiba", ("application/json",), max_bytes=10_000
    )
    assert json.loads(page.body)["wikibase_item"] == "Q736955"
    assert [request.url.path for request in seen] == ["/api/rest_v1/page/summary/Lashkar-e-Taiba"]
    assert "(+https://github.com/" in seen[0].headers["user-agent"]  # contact, per Wikimedia
    with pytest.raises(FetchError, match="larger than 0 MB"):
        await fetcher.fetch_data(f"{SUMMARY}x", ("application/json",), max_bytes=10)

    async def private(host, port):
        return ["10.0.0.5"]

    inside = Fetcher(agent, transport=httpx.MockTransport(handler), resolver=private)
    with pytest.raises(FetchError, match="private or internal"):
        await inside.fetch_data(f"{WIKIDATA}?x", ("application/json",), max_bytes=10_000)


# ---- the agent uses the records -----------------------------------------------------


async def test_the_agent_saves_records_with_code_claims_only_for_names_in_evidence(tmp_path):
    def script(ref, step, user):
        if ref == "Q1" and step == 1:
            return {
                "calls": [
                    {"tool": "sanctions_search", "args": {"name": "Lashkar-e-Taiba"}},
                    {"tool": "sanctions_search", "args": {"name": "Hafiz Saeed"}},
                    {"tool": "wiki_lookup", "args": {"query": "Lashkar-e-Taiba"}},
                ]
            }
        return DONE

    store = Store(tmp_path)
    model = Researcher(script=script)
    data = lists(**{SUMMARY: LET_SUMMARY, WIKIDATA: LET_ENTITY})
    records = (SanctionsSearch(data, tmp_path / "lists"), WikiLookup(Wiki(summary=LET_SUMMARY)))
    brief = "Is Lashkar-e-Taiba under sanctions, and who leads it?"
    inv = Investigation(id=store.new_id(), brief=brief)
    model.usage = inv.usage
    tools = Tools(model=model, searcher=FakeSearch(), fetcher=FakeFetcher(), records=records)
    inv = await Agent(inv, tools, store, Limits()).run()
    assert inv.status == "done", inv.error
    found = [source for source in inv.sources if source.kind == "record"]
    assert [(s.origin, s.reliability) for s in found] == [
        ("ofac.treas.gov", "A"),
        ("un.org", "A"),
        ("wikidata.org", "C"),
    ]
    claims = [claim for claim in inv.claims if inv.source(claim.source_ref).kind == "record"]
    assert len(claims) == 2 + 3 + 4
    for item in claims:  # anchored in the saved record text, like every other claim
        assert (
            store.text(inv.source(item.source_ref).text_sha256)[item.start : item.end] == item.quote
        )
    assert "ExtractOut" not in model.calls  # records are never read by a model
    messages = [step.message for step in inv.steps]
    refusal = "not run. Lantern looks up records only for names that appear in the research"
    assert any(m.startswith(f"sanctions_search “Hafiz Saeed”: {refusal}") for m in messages)
    assert inv.usage.tools["sanctions_search"] == 1
    assert "sanctions_search" in model.prompts["ResearchStep"][0]  # offered in the menu


def test_record_tools_are_built_only_when_enabled(tmp_path):
    on = record_tools(AppSettings(data_dir=str(tmp_path)), fetcher=None)
    assert [tool.name for tool in on] == [
        "sanctions_search",
        "wiki_lookup",
        "company_lookup",
        "domain_lookup",
        "disaster_events",
        "satellite_views",
    ]
    assert record_tools(AppSettings(records_enabled=False), fetcher=None) == ()
    assert "sanctions_search" in prompts.RESEARCH


async def test_official_data_errors_say_what_the_service_answered():
    answers = {
        "/down": httpx.Response(503),
        "/page": httpx.Response(200, headers={"content-type": "text/html"}, content=b"<p>hi</p>"),
    }

    async def resolver(host, port):
        return ["93.184.215.14"]

    fetcher = Fetcher(
        "TestBot/1.0",
        transport=httpx.MockTransport(lambda request: answers[request.url.path]),
        resolver=resolver,
        host_interval=0,
    )
    with pytest.raises(FetchError, match=r"The data service answered HTTP 503\."):
        await fetcher.fetch_data("https://data.example/down", ("application/json",), max_bytes=99)
    with pytest.raises(FetchError, match="sent text/html, not the expected data"):
        await fetcher.fetch_data("https://data.example/page", ("application/json",), max_bytes=99)
