"""Company records from GLEIF and domain records over RDAP.

The sample answers are abridged copies of the real GLEIF and RDAP responses fetched on
2026-11-05 (Jaguar Land Rover Limited and its parents; dawn.com from Verisign). The sole
proprietor and the registrant contact in them are invented.
"""

import json

import httpx
import pytest

from lantern.agent.loop import Agent
from lantern.egress import Fetcher, FetchError, Page
from lantern.models import Investigation
from lantern.pipeline import Limits, Tools
from lantern.store import Store
from lantern.tools.adapters.companies import GLEIF, CompanyLookup
from lantern.tools.adapters.domains import BOOTSTRAP, DomainArgs, DomainLookup
from lantern.tools.base import ToolContext, ToolError

from .fakes import FakeFetcher, FakeSearch
from .test_agent import DONE, Researcher

CTX = ToolContext()
JLR, AUTOMOTIVE, TATA = "213800WSGIIZCXF1P572", "529900L73GEWN1O5NH84", "335800BO2LHWJJ8TZI32"


def record(lei, name, *, other=(), category="GENERAL", parents=()):
    links = {
        which: {"links": {"lei-record": f"{GLEIF}/{lei}/{which}"}}
        if which in parents
        else {"links": {"reporting-exception": f"{GLEIF}/{lei}/{which}-reporting-exception"}}
        for which in ("direct-parent", "ultimate-parent")
    }
    entity = {
        "legalName": {"name": name, "language": "en"},
        "otherNames": [{"name": n, "language": "en", "type": "PREVIOUS_LEGAL_NAME"} for n in other],
        "legalAddress": {
            "addressLines": ["Abbey Road, Whitley"],
            "city": "COVENTRY",
            "country": "GB",
        },
        "jurisdiction": "GB",
        "category": category,
        "status": "ACTIVE",
    }
    registration = {"initialRegistrationDate": "2013-08-21T10:49:00Z", "status": "ISSUED"}
    return {
        "type": "lei-records",
        "id": lei,
        "relationships": links,
        "attributes": {"lei": lei, "entity": entity, "registration": registration},
    }


SEARCH = {
    "data": [
        record(
            JLR,
            "JAGUAR LAND ROVER LIMITED",
            other=["JAGUAR CARS LIMITED"],
            parents=("direct-parent", "ultimate-parent"),
        ),
        record("213800AAAAAAAAAAAA01", "JAGUAR LAND ROVER LIMITED SERVICES"),  # a near match
        record("213800BBBBBBBBBBBB02", "JAGUAR LAND ROVER LIMITED", category="SOLE_PROPRIETOR"),
    ]
}


class Data:
    def __init__(self, routes):
        self.routes, self.urls, self.accepts = routes, [], []

    async def fetch_data(self, url, accept, *, max_bytes, seconds=60.0):
        self.urls.append(url)
        self.accepts.append(accept)
        for prefix, answer in self.routes.items():
            if url.startswith(prefix):
                if isinstance(answer, Exception):
                    raise answer
                return Page(url=url, content_type=accept[0], body=json.dumps(answer).encode())
        raise FetchError("The data service answered HTTP 404.", "refused")


def gleif(**extra):
    return Data(
        {
            f"{GLEIF}?": SEARCH,
            f"{GLEIF}/{JLR}/direct-parent": {
                "data": record(AUTOMOTIVE, "JAGUAR LAND ROVER AUTOMOTIVE PLC")
            },
            f"{GLEIF}/{JLR}/ultimate-parent": {
                "data": record(TATA, "TATA MOTORS PASSENGER VEHICLES LIMITED")
            },
            **extra,
        }
    )


# ---- GLEIF --------------------------------------------------------------------------


async def test_a_company_record_keeps_its_identifier_parents_and_city_only():
    data = gleif()
    tool = CompanyLookup(data)
    result = await tool.run(tool.args_model(name="Jaguar Land Rover Limited"), CTX)
    [draft] = result.sources  # the near match and the sole proprietor are left out
    assert (draft.kind, draft.grade[0], draft.origin) == ("record", "A", "gleif.org")
    assert draft.url == f"https://search.gleif.org/#/record/{JLR}"
    assert draft.record_claims == (
        (
            f"JAGUAR LAND ROVER LIMITED has the Legal Entity Identifier {JLR} in the GLEIF "
            "register: registered in GB, entity status ACTIVE, LEI ISSUED since 2013-08-21."
        ),
        "GLEIF gives the legal address of JAGUAR LAND ROVER LIMITED in COVENTRY, GB.",
        "GLEIF also lists JAGUAR LAND ROVER LIMITED as: JAGUAR CARS LIMITED.",
        (
            f"GLEIF records JAGUAR LAND ROVER AUTOMOTIVE PLC (LEI {AUTOMOTIVE}) as the direct "
            "parent of JAGUAR LAND ROVER LIMITED."
        ),
        (
            f"GLEIF records TATA MOTORS PASSENGER VEHICLES LIMITED (LEI {TATA}) as the ultimate "
            "parent of JAGUAR LAND ROVER LIMITED."
        ),
    )
    assert b"Abbey Road" not in draft.body
    assert "Abbey Road" not in draft.text
    relations = [(i, t.subject.ids, t.relation, t.object.name) for i, t in draft.relations]
    assert relations == [
        (3, [f"lei:{JLR}"], "subsidiary_of", "JAGUAR LAND ROVER AUTOMOTIVE PLC"),
        (4, [f"lei:{JLR}"], "subsidiary_of", "TATA MOTORS PASSENGER VEHICLES LIMITED"),
    ]
    assert "filter%5Bentity.legalName%5D=Jaguar+Land+Rover+Limited" in data.urls[0]
    assert data.accepts[0][0] == "application/vnd.api+json"
    assert result.summary.startswith("GLEIF: 1 legal entity (")


async def test_no_company_reported_parents_and_failures_are_plain():
    none = CompanyLookup(gleif(**{f"{GLEIF}?": {"data": []}}))
    out = await none.run(none.args_model(name="Lashkar-e-Taiba"), CTX)
    assert (out.sources, out.summary) == ([], "GLEIF: no legal entity named “Lashkar-e-Taiba”.")
    lone = CompanyLookup(gleif(**{f"{GLEIF}?": {"data": [record(TATA, "TATA STEEL LIMITED")]}}))
    [draft] = (await lone.run(lone.args_model(name="Tata Steel Limited"), CTX)).sources
    assert draft.relations == ()
    assert len(draft.record_claims) == 2
    down = CompanyLookup(gleif(**{f"{GLEIF}?": FetchError("Could not connect.", "unreachable")}))
    with pytest.raises(ToolError, match="The GLEIF register could not be reached"):
        await down.run(down.args_model(name="Tata Steel Limited"), CTX)


# ---- RDAP ---------------------------------------------------------------------------

IANA = {
    "services": [
        [["com", "net"], ["https://rdap.verisign.com/com/v1/"]],
        [["uk"], ["https://rdap.nominet.uk/uk/"]],
    ]
}
DAWN = {
    "objectClassName": "domain",
    "ldhName": "DAWN.COM",
    "status": ["client transfer prohibited"],
    "events": [
        {"eventAction": "registration", "eventDate": "1997-04-14T04:00:00Z"},
        {"eventAction": "expiration", "eventDate": "2034-04-15T04:00:00Z"},
        {"eventAction": "last changed", "eventDate": "2024-04-15T04:05:54Z"},
        {"eventAction": "last update of RDAP database", "eventDate": "2026-11-05T15:39:33Z"},
    ],
    "nameservers": [{"ldhName": "ANDY.NS.CLOUDFLARE.COM."}, {"ldhName": "EMMA.NS.CLOUDFLARE.COM"}],
    "secureDNS": {"delegationSigned": False},
    "entities": [
        {
            "roles": ["registrar"],
            "publicIds": [{"type": "IANA Registrar ID", "identifier": "2"}],
            "vcardArray": [
                "vcard",
                [["version", {}, "text", "4.0"], ["fn", {}, "text", "Network Solutions, LLC"]],
            ],
        },
        {
            "roles": ["registrant"],
            "vcardArray": [
                "vcard",
                [["fn", {}, "text", "Example Owner"], ["email", {}, "text", "owner@example.org"]],
            ],
        },
    ],
}


@pytest.mark.parametrize(
    ("given", "domain"),
    [
        ("https://www.dawn.com/news/123", "dawn.com"),
        ("DAWN.COM", "dawn.com"),
        ("news.bbc.co.uk", "bbc.co.uk"),
    ],
)
def test_a_web_address_becomes_its_registered_domain(given, domain):
    assert DomainArgs(domain=given).domain == domain


@pytest.mark.parametrize("bad", ["localhost", "dawn com", "exa_mple.com", "'; drop.com"])
def test_anything_but_a_domain_name_is_refused(bad):
    with pytest.raises(ValueError, match="domain name"):
        DomainArgs(domain=bad)


async def test_a_domain_record_keeps_registry_facts_and_never_the_registrant():
    data = Data({BOOTSTRAP: IANA, "https://rdap.verisign.com/com/v1/domain/dawn.com": DAWN})
    tool = DomainLookup(data)
    result = await tool.run(tool.args_model(domain="https://www.dawn.com/news/1"), CTX)
    [draft] = result.sources
    assert (draft.grade[0], draft.origin) == ("A", "rdap:verisign.com")
    assert draft.record_claims == (
        "The registry's RDAP record says dawn.com was registered on 1997-04-14.",
        "The registry's RDAP record says dawn.com was due to expire on 2034-04-15.",
        "The registry's RDAP record says dawn.com was last changed on 2024-04-15.",
        "The registry lists the status of dawn.com as: client transfer prohibited.",
        "dawn.com uses the name servers andy.ns.cloudflare.com; emma.ns.cloudflare.com.",
        "dawn.com is not signed with DNSSEC.",
        (
            "dawn.com is registered through the registrar Network Solutions, LLC (IANA "
            "registrar ID 2)."
        ),
    )
    kept = draft.text.encode() + draft.body
    assert b"Example Owner" not in kept
    assert b"owner@example.org" not in kept
    await tool.run(tool.args_model(domain="dawn.com"), CTX)
    assert data.urls.count(BOOTSTRAP) == 1  # the bootstrap file is read once per run
    assert data.accepts[-1][0] == "application/rdap+json"


async def test_unknown_domains_and_registries_are_plain():
    data = Data({BOOTSTRAP: IANA})
    tool = DomainLookup(data)
    missing = await tool.run(tool.args_model(domain="nothing-here-4721.com"), CTX)
    assert missing.summary == "RDAP: the registry has no record of nothing-here-4721.com."
    unlisted = await tool.run(tool.args_model(domain="example.zz"), CTX)
    assert unlisted.summary == "RDAP: no registry service is listed for example.zz."
    down = DomainLookup(Data({BOOTSTRAP: FetchError("Could not connect.", "unreachable")}))
    with pytest.raises(ToolError, match="IANA RDAP bootstrap file could not be reached"):
        await down.run(down.args_model(domain="dawn.com"), CTX)


async def test_the_real_fetcher_asks_for_the_data_type_it_expects():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/rdap+json"},
            content=json.dumps(DAWN).encode(),
        )

    async def resolver(host, port):
        return ["93.184.215.14"]

    fetcher = Fetcher(
        "TestBot/1.0", transport=httpx.MockTransport(handler), resolver=resolver, host_interval=0
    )
    await fetcher.fetch_data(
        "https://rdap.example/domain/dawn.com", ("application/rdap+json",), max_bytes=100_000
    )
    assert seen[0].headers["accept"] == "application/rdap+json, */*;q=0.1"


# ---- the agent ----------------------------------------------------------------------


async def test_the_agent_maps_parent_companies_and_reads_domains_from_the_evidence(tmp_path):
    def script(ref, step, user):
        if ref == "Q1" and step == 1:
            return {
                "calls": [
                    {"tool": "company_lookup", "args": {"name": "Jaguar Land Rover Limited"}},
                    {"tool": "domain_lookup", "args": {"domain": "reuters.com"}},  # a saved site
                    {"tool": "domain_lookup", "args": {"domain": "unrelated-site.com"}},
                    {"tool": "web_search", "args": {"query": "Q1 district floods"}},
                ]
            }
        if ref == "Q1" and step == 2:
            return {"calls": [{"tool": "domain_lookup", "args": {"domain": "reuters.com"}}]}
        return DONE

    store = Store(tmp_path)
    model = Researcher(script=script, kinds=("list", "fact"))
    rdap = {BOOTSTRAP: IANA, "https://rdap.verisign.com/com/v1/domain/reuters.com": DAWN}
    records = (CompanyLookup(gleif()), DomainLookup(Data(rdap)))
    inv = Investigation(id=store.new_id(), brief="Who owns Jaguar Land Rover Limited?")
    model.usage = inv.usage
    tools = Tools(model=model, searcher=FakeSearch(), fetcher=FakeFetcher(), records=records)
    inv = await Agent(inv, tools, store, Limits()).run()
    assert inv.status == "done", inv.error
    name = {entity.ref: entity.name for entity in inv.entities}
    found = {(name[k.subject], k.relation, name[k.object], k.status) for k in inv.links}
    assert (
        "JAGUAR LAND ROVER LIMITED",
        "subsidiary_of",
        "TATA MOTORS PASSENGER VEHICLES LIMITED",
        "record",
    ) in found
    messages = [step.message for step in inv.steps]
    assert any(
        m.startswith("domain_lookup “unrelated-site.com”: not run. Lantern looks up records")
        for m in messages
    )
    assert "RDAP: reuters.com (7 facts)." in messages  # reuters.com is a saved source by then
    assert inv.usage.tools["company_lookup"] == 1
