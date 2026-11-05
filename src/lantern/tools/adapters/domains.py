"""Domain registration records over RDAP, graded A: when a domain was registered, when it
expires and last changed, its status, name servers, DNSSEC, and its registrar.

The registry for each top-level domain comes from IANA's RDAP bootstrap file (RFC 9224).
Only registry facts and the registrar's name and IANA ID are kept: registrant,
administrative and technical contacts are never kept, even when a registry shows them.

Checked 2026-11-05: `data.iana.org/rdap/dns.json` lists 592 RDAP services (`.com` is
`rdap.verisign.com/com/v1/`); registry answers are `application/rdap+json`, without a key.
Registries set their own limits and terms (Verisign's notice asks for lawful, low-volume
use); Lantern makes one bootstrap request per run and one request per lookup.
"""

import json
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator

from lantern.assessment import registrable_domain
from lantern.egress import FetchError
from lantern.tools.adapters.sanctions import DataFetcher
from lantern.tools.base import SourceDraft, ToolArgs, ToolContext, ToolError, ToolKind, ToolResult

BOOTSTRAP = "https://data.iana.org/rdap/dns.json"
TYPES = ("application/rdap+json", "application/json")
GRADE = ("A", "Domain registry record (RDAP)")
DATES = {"registration": "registered on", "expiration": "due to expire on"}
DATES |= {"last changed": "last changed on"}


class DomainArgs(ToolArgs):
    domain: str = Field(min_length=3, max_length=253)

    @field_validator("domain")
    @classmethod
    def _registered_domain(cls, value: str) -> str:
        """A web address or host becomes its registered domain: `https://www.dawn.com/x`
        → `dawn.com`."""
        host = registrable_domain(value.strip().lower())
        labels = host.split(".")
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
        if len(labels) < 2 or not all(label and set(label) <= allowed for label in labels):
            msg = "must be a domain name such as example.com"
            raise ValueError(msg)
        return host


class DomainLookup:
    name: ClassVar[str] = "domain_lookup"
    description: ClassVar[str] = (
        "Look up the registry record of a website's domain named in the case file (RDAP): "
        "when it was registered, its expiry, status, name servers and registrar. Useful to "
        "check how old a site is or whether two sites share infrastructure. Never shows who "
        "registered it."
    )
    args_model: ClassVar[type[BaseModel]] = DomainArgs
    kind: ClassVar[ToolKind] = "record"
    rate_key: ClassVar[str] = "rdap"
    min_interval: ClassVar[float] = 1.0

    def __init__(self, fetcher: DataFetcher) -> None:
        self._fetcher = fetcher
        self._registries: dict[str, str] | None = None

    async def _json(self, url: str, what: str) -> Any:
        try:
            page = await self._fetcher.fetch_data(url, TYPES, max_bytes=1_000_000, seconds=20)
        except FetchError as error:
            if "HTTP 404" in str(error):
                return None
            raise ToolError(f"The {what} could not be reached: {error}") from error
        try:
            return json.loads(page.body)
        except ValueError as error:
            raise ToolError(f"The {what} sent an unreadable answer.") from error

    async def _registry(self, domain: str) -> str | None:
        if self._registries is None:
            data = await self._json(BOOTSTRAP, "IANA RDAP bootstrap file") or {}
            self._registries = {
                tld.lower(): str(urls[0])
                for tlds, urls in data.get("services", [])
                for tld in tlds
                if urls and str(urls[0]).startswith("https://")
            }
        return self._registries.get(domain.rsplit(".", 1)[-1])

    async def run(self, args: DomainArgs, _ctx: ToolContext) -> ToolResult:
        base = await self._registry(args.domain)
        if base is None:
            return ToolResult([], [], f"RDAP: no registry service is listed for {args.domain}.")
        url = f"{base.rstrip('/')}/domain/{args.domain}"
        record = await self._json(url, "domain registry")
        if not isinstance(record, dict):
            return ToolResult([], [], f"RDAP: the registry has no record of {args.domain}.")
        draft = self._draft(args.domain, url, record)
        return ToolResult([], [draft], f"RDAP: {args.domain} ({len(draft.record_claims)} facts).")

    def _draft(self, domain: str, url: str, record: dict[str, Any]) -> SourceDraft:
        lines = []
        for event in record.get("events") or []:
            action, when = str(event.get("eventAction", "")), str(event.get("eventDate", ""))
            if action in DATES and when:
                lines.append(
                    f"The registry's RDAP record says {domain} was {DATES[action]} {when[:10]}."
                )
        if statuses := [str(item) for item in record.get("status") or []]:
            lines.append(f"The registry lists the status of {domain} as: {'; '.join(statuses)}.")
        servers = [
            str(n.get("ldhName", "")).lower().rstrip(".") for n in record.get("nameservers") or []
        ]
        if servers := [server for server in servers if server]:
            lines.append(f"{domain} uses the name servers {'; '.join(servers)}.")
        signed = (record.get("secureDNS") or {}).get("delegationSigned")
        if isinstance(signed, bool):
            lines.append(f"{domain} is {'' if signed else 'not '}signed with DNSSEC.")
        for entity in record.get("entities") or []:
            if "registrar" not in (entity.get("roles") or []):
                continue  # registrant and other contacts are never kept
            card = entity.get("vcardArray") or [None, []]
            names = [item[3] for item in card[1] if isinstance(item, list) and item[0] == "fn"]
            ids = [i.get("identifier") for i in entity.get("publicIds") or []]
            if names:
                iana = f" (IANA registrar ID {ids[0]})" if ids and ids[0] else ""
                lines.append(f"{domain} is registered through the registrar {names[0]}{iana}.")
        kept = {"domain": domain, "rdap": url, "facts": lines}
        return SourceDraft(
            url=url,
            title=f"RDAP: {domain}",
            published=None,
            body=json.dumps(kept, ensure_ascii=False, sort_keys=True).encode(),
            text="\n".join(lines),
            kind="record",
            origin=f"rdap:{registrable_domain(url)}",
            record_claims=tuple(lines),
            grade=GRADE,
        )
