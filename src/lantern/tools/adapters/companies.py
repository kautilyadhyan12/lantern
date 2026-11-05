"""Company records from the GLEIF register of Legal Entity Identifiers (LEI), graded A:
the legal name, jurisdiction, status, the city and country of the legal address, and the
direct and ultimate parents when they are reported.

GLEIF's name filter also returns similar names, so only records whose legal name or a
listed other name has exactly the same words are kept. Records of sole proprietors (natural
persons trading under their own name) are never kept, and full street addresses are not.

Checked 2026-11-05: `api.gleif.org/api/v1/lei-records` answers JSON:API without a key; the
data is CC0; the documented limit is 60 requests a minute. Lantern makes 1 to 7 requests
per lookup, one per second. Parents come from the `direct-parent` and `ultimate-parent`
relationships when GLEIF links a `lei-record`, otherwise a reporting exception applies.
"""

import json
from typing import Any, ClassVar
from urllib.parse import urlencode

from pydantic import BaseModel

from lantern.core.graph import name_key
from lantern.egress import FetchError
from lantern.models import Triple
from lantern.tools.adapters.sanctions import DataFetcher, NameArgs
from lantern.tools.base import SourceDraft, ToolContext, ToolError, ToolKind, ToolResult

GLEIF = "https://api.gleif.org/api/v1/lei-records"
TYPES = ("application/vnd.api+json", "application/json")
GRADE = ("A", "Official register of legal entities (GLEIF)")
MAX_MATCHES = 3


def _names(entity: dict[str, Any]) -> list[str]:
    names = [str(entity.get("legalName", {}).get("name", ""))]
    for group in ("otherNames", "transliteratedOtherNames"):
        names += [str(item.get("name", "")) for item in entity.get(group) or []]
    return [name for name in dict.fromkeys(names) if name]


class CompanyLookup:
    name: ClassVar[str] = "company_lookup"
    description: ClassVar[str] = (
        "Look up a company or other legal entity named in the case file in the official "
        "GLEIF register of Legal Entity Identifiers: legal name, jurisdiction, status, city "
        "and country, and its direct and ultimate parent companies. Exact names only."
    )
    args_model: ClassVar[type[BaseModel]] = NameArgs
    kind: ClassVar[ToolKind] = "record"
    rate_key: ClassVar[str] = "gleif"
    min_interval: ClassVar[float] = 1.0

    def __init__(self, fetcher: DataFetcher) -> None:
        self._fetcher = fetcher

    async def _json(self, url: str) -> Any:
        try:
            page = await self._fetcher.fetch_data(url, TYPES, max_bytes=2_000_000, seconds=20)
        except FetchError as error:
            if "HTTP 404" in str(error):
                return None
            raise ToolError(f"The GLEIF register could not be reached: {error}") from error
        try:
            return json.loads(page.body)
        except ValueError as error:
            raise ToolError("The GLEIF register sent an unreadable answer.") from error

    async def run(self, args: NameArgs, _ctx: ToolContext) -> ToolResult:
        query = urlencode({"filter[entity.legalName]": args.name, "page[size]": 10})
        found = await self._json(f"{GLEIF}?{query}") or {}
        wanted = name_key(args.name)
        records = [
            record
            for record in found.get("data") or []
            if record.get("attributes", {}).get("entity", {}).get("category") != "SOLE_PROPRIETOR"
            and wanted in {name_key(n) for n in _names(record["attributes"]["entity"])}
        ][:MAX_MATCHES]
        drafts = [await self._draft(record) for record in records]
        if not drafts:
            return ToolResult([], [], f"GLEIF: no legal entity named “{args.name}”.")
        shown = "; ".join(f"{draft.title} {draft.url}" for draft in drafts)
        count = f"{len(drafts)} legal entit{'y' if len(drafts) == 1 else 'ies'}"
        return ToolResult([], drafts, f"GLEIF: {count} ({shown}).")

    async def _parent(self, record: dict[str, Any], which: str) -> tuple[str, str] | None:
        link = record.get("relationships", {}).get(which, {}).get("links", {}).get("lei-record")
        if not isinstance(link, str) or not link.startswith(GLEIF):
            return None  # GLEIF reports no parent, or an exception to reporting one
        data = (await self._json(link) or {}).get("data") or {}
        name = data.get("attributes", {}).get("entity", {}).get("legalName", {}).get("name")
        return (str(name), str(data.get("id"))) if name and data.get("id") else None

    async def _draft(self, record: dict[str, Any]) -> SourceDraft:
        lei = str(record["id"])
        attributes = record["attributes"]
        entity, registration = attributes["entity"], attributes.get("registration", {})
        names = _names(entity)
        name, others = names[0], names[1:]
        since = str(registration.get("initialRegistrationDate", ""))[:10]
        lines = [
            f"{name} has the Legal Entity Identifier {lei} in the GLEIF register: registered "
            f"in {entity.get('jurisdiction') or 'an unstated jurisdiction'}, entity status "
            f"{entity.get('status', 'unknown')}, LEI {registration.get('status', 'unknown')}"
            + (f" since {since}." if since else ".")
        ]
        address = entity.get("legalAddress") or {}
        if address.get("city") or address.get("country"):
            place = ", ".join(str(p) for p in (address.get("city"), address.get("country")) if p)
            lines.append(f"GLEIF gives the legal address of {name} in {place}.")
        if others:
            lines.append(f"GLEIF also lists {name} as: {'; '.join(others)}.")
        me = {"name": name, "kind": "organisation", "ids": [f"lei:{lei}"], "aliases": others}
        relations = []
        parents: list[str] = []
        for which, label in (("direct-parent", "direct"), ("ultimate-parent", "ultimate")):
            parent = await self._parent(record, which)
            if parent is None or parent[1] in parents:
                continue
            parents.append(parent[1])
            lines.append(
                f"GLEIF records {parent[0]} (LEI {parent[1]}) as the {label} parent of {name}."
            )
            other = {"name": parent[0], "kind": "organisation", "ids": [f"lei:{parent[1]}"]}
            data = {"subject": me, "relation": "subsidiary_of", "object": other}
            data |= {"claim_refs": [], "basis": "record"}
            relations.append((len(lines) - 1, Triple.model_validate(data)))
        kept = {"lei": lei, "name": name, "other_names": others, "facts": lines}
        return SourceDraft(
            url=f"https://search.gleif.org/#/record/{lei}",
            title=f"GLEIF: {name}",
            published=since or None,
            body=json.dumps(kept, ensure_ascii=False, sort_keys=True).encode(),
            text="\n".join(lines),
            kind="record",
            origin="gleif.org",
            record_claims=tuple(lines),
            grade=GRADE,
            relations=tuple(relations),
        )
