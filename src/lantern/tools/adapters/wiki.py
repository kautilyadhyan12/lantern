"""Background from Wikipedia and Wikidata, graded C: what something is, its other names in
several languages, and a fixed set of facts.

The English Wikipedia page summary resolves the name (a disambiguation page means no single
subject is chosen); otherwise a Wikidata entry whose label or alias is exactly the name.
Only these Wikidata properties are ever read: instance of, founded by, member of, position
held, date of death and place of death. Properties for religion, ethnicity, sexuality,
political party, health and the like are never read (invariant 5). For people, the
description and the Wikipedia summary are not kept either, because they often mention
such traits.

Checked 2026-11-05: Wikimedia asks for a User-Agent with contact details (Lantern's gives
its project URL) and limits anonymous API use; Lantern makes 2 to 4 requests per lookup,
one per second. Content is CC BY-SA, cited with a link.
"""

import json
from typing import Any, ClassVar
from urllib.parse import quote, urlencode

from pydantic import BaseModel, Field

from lantern.egress import FetchError
from lantern.text import name_words
from lantern.tools.adapters.sanctions import DataFetcher
from lantern.tools.base import SourceDraft, ToolArgs, ToolContext, ToolError, ToolKind, ToolResult

SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
WIKIDATA = "https://www.wikidata.org/w/api.php"
JSON = ("application/json",)
LANGUAGES = "en|ur|hi|ar|bn|as|fa|ps|pa|ta|ne|ru|fr|es|zh"
HUMAN = "Q5"
GRADE = ("C", "Wikipedia and Wikidata: crowd-edited reference works, background only")
# The only properties ever read, with the sentence each becomes.
FACTS = {
    "P31": "Wikidata records {name} as an instance of: {value}.",
    "P112": "Wikidata records {name} as founded by: {value}.",
    "P463": "Wikidata records {name} as a member of: {value}.",
    "P39": "Wikidata records {name} as having held the position: {value}.",
    "P570": "Wikidata records the date of death of {name} as {value}.",
    "P20": "Wikidata records the place of death of {name} as {value}.",
}
MAX_VALUES = 8
MAX_NAMES = 25


class QueryArgs(ToolArgs):
    query: str = Field(min_length=2, max_length=200)


def _values(claims: dict[str, Any], prop: str) -> list[Any]:
    found = []
    for claim in claims.get(prop, [])[:MAX_VALUES]:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if value is not None:
            found.append(value)
    return found


def _date(value: dict[str, Any]) -> str:
    """A Wikidata time at its stated precision: year, month or day."""
    stamp = str(value.get("time", "")).lstrip("+")[:10]
    precision = int(value.get("precision", 11))
    return stamp[:4] if precision <= 9 else stamp[:7] if precision == 10 else stamp


class WikiLookup:
    name: ClassVar[str] = "wiki_lookup"
    description: ClassVar[str] = (
        "Background from Wikipedia and Wikidata on an organisation, place, event or public "
        "figure named in the case file: what it is, its other names and spellings in several "
        "languages, founders, memberships, positions held, date and place of death. Graded C: "
        "background, never proof on its own. Useful before searching other names or spellings."
    )
    args_model: ClassVar[type[BaseModel]] = QueryArgs
    kind: ClassVar[ToolKind] = "record"
    rate_key: ClassVar[str] = "wikimedia"
    min_interval: ClassVar[float] = 1.0

    def __init__(self, fetcher: DataFetcher) -> None:
        self._fetcher = fetcher

    async def _json(self, url: str) -> Any:
        try:
            page = await self._fetcher.fetch_data(url, JSON, max_bytes=2_000_000, seconds=20)
        except FetchError as error:
            if "HTTP 404" in str(error):
                return None
            raise ToolError(f"Wikipedia or Wikidata could not be reached: {error}") from error
        try:
            return json.loads(page.body)
        except ValueError as error:
            raise ToolError("Wikipedia or Wikidata sent an unreadable answer.") from error

    async def run(self, args: QueryArgs, _ctx: ToolContext) -> ToolResult:
        summary = await self._json(SUMMARY + quote(args.query.replace(" ", "_"), safe=""))
        if isinstance(summary, dict) and summary.get("type") == "disambiguation":
            text = f"Wikipedia has several subjects called “{args.query}”; none was chosen."
            return ToolResult([], [], f"{text} Use a more specific name.")
        qid = summary.get("wikibase_item") if isinstance(summary, dict) else None
        qid = qid or await self._exact_match(args.query)
        if not qid:
            return ToolResult([], [], f"No Wikipedia or Wikidata entry for “{args.query}”.")
        entity = (await self._entities([qid], "labels|aliases|descriptions|claims", LANGUAGES)).get(
            qid
        )
        if not isinstance(entity, dict) or "missing" in entity:
            return ToolResult([], [], f"No Wikidata entry {qid} for “{args.query}”.")
        claims = entity.get("claims", {})
        ids = [v["id"] for p in FACTS if p != "P570" for v in _values(claims, p) if "id" in v]
        labels = await self._labels(ids)
        draft = self._draft(qid, entity, labels, summary if isinstance(summary, dict) else {})
        return ToolResult([], [draft], f"{draft.title} ({draft.url}).")

    async def _exact_match(self, query: str) -> str | None:
        """A Wikidata entry whose label or alias is exactly the name, never a near match."""
        params = {"action": "wbsearchentities", "search": query, "language": "en", "limit": 5}
        found = await self._json(f"{WIKIDATA}?{urlencode({**params, 'format': 'json'})}")
        wanted = name_words(query)
        for item in (found or {}).get("search", []):
            if name_words(str(item.get("match", {}).get("text", ""))) == wanted:
                return str(item.get("id"))
        return None

    async def _entities(self, ids: list[str], props: str, languages: str) -> dict[str, Any]:
        """Wikidata entries by id: only the parts named in `props`, in `languages`."""
        params = {"action": "wbgetentities", "ids": "|".join(ids), "props": props}
        params |= {"languages": languages, "format": "json"}
        data = await self._json(f"{WIKIDATA}?{urlencode(params)}")
        entities = (data or {}).get("entities") if isinstance(data, dict) else None
        return entities if isinstance(entities, dict) else {}

    async def _labels(self, ids: list[str]) -> dict[str, str]:
        if not ids:
            return {}
        entities = await self._entities(list(dict.fromkeys(ids))[:50], "labels", "en")
        return {
            qid: str(item.get("labels", {}).get("en", {}).get("value", qid))
            for qid, item in entities.items()
        }

    def _draft(
        self, qid: str, entity: dict[str, Any], labels: dict[str, str], summary: dict[str, Any]
    ) -> SourceDraft:
        claims = entity.get("claims", {})
        own = entity.get("labels", {})
        english = own.get("en") or next(iter(own.values()), None) or {}
        name = str(english.get("value") or qid)
        human = any(v.get("id") == HUMAN for v in _values(claims, "P31"))
        names = [str(item.get("value")) for item in own.values()]
        names += [
            str(a.get("value")) for group in entity.get("aliases", {}).values() for a in group
        ]
        others = [n for n in dict.fromkeys(names) if n and n != name][:MAX_NAMES]
        lines = []
        description = str(entity.get("descriptions", {}).get("en", {}).get("value", ""))
        if human:
            lines.append(
                f"Wikidata entry {qid} is a person named {name}. A matching name alone does not "
                "show that this is the same person as in the evidence."
            )
        elif description:
            lines.append(f"Wikidata describes {name} ({qid}) as: {description}.")
        if others:
            lines.append(f"Wikidata lists these other names for {name}: {'; '.join(others)}.")
        for prop, sentence in FACTS.items():
            if human and prop == "P31":
                continue
            values = _values(claims, prop)
            shown = [_date(v) if prop == "P570" else labels.get(v.get("id"), "") for v in values]
            if shown := [item for item in shown if item]:
                lines.append(sentence.format(name=name, value="; ".join(shown)))
        extract = "" if human else " ".join(str(summary.get("extract", "")).split())
        page = summary.get("content_urls", {}).get("desktop", {}).get("page", "")
        text = "\n".join(lines + ([f"Wikipedia summary ({page}): {extract}"] if extract else []))
        kept = {"qid": qid, "name": name, "facts": lines, "wikipedia": page, "summary": extract}
        return SourceDraft(
            url=f"https://www.wikidata.org/wiki/{qid}",
            title=f"Wikidata: {name}",
            published=None,
            body=json.dumps(kept, ensure_ascii=False, sort_keys=True).encode(),
            text=text,
            kind="record",
            origin="wikidata.org",
            record_claims=tuple(lines),
            grade=GRADE,
        )
