"""Plain-language notes for the evidence board: what each card is and what each string
says, how sure the evidence is, and where it comes from, written by code from the
investigation's entities, links, claims and sources. No model writes these notes."""

import re
from collections import Counter, deque
from dataclasses import dataclass, field

from lantern.core.graph import name_key
from lantern.models import Entity, Investigation, Link, Source
from lantern.text import name_words

KIND_WORDS = {
    "organisation": "an organisation",
    "person_public_role": "a person in a public role",
    "place": "a place",
    "event": "an event",
}
KIND_TITLES = {
    "organisation": "Organisation",
    "person_public_role": "Person (public role)",
    "place": "Place",
    "event": "Event",
}
SENTENCES = {
    "member_of": "{a} is a member of {b}.",
    "leader_of": "{a} leads {b}.",
    "founded": "{a} founded {b}.",
    "designated_by": "{a} is on a sanctions list kept by {b}.",
    "linked_to": "{a} is linked to {b}.",
    "alias_of": "{a} is another name for {b}.",
    "killed_in": "{a} was killed in {b}.",
    "located_in": "{a} happened in, or is located in, {b}.",
    "reported_by": "{a} was reported by {b}.",
    "subsidiary_of": "{a} is owned by {b}: it is a subsidiary of it.",
}
# Codes that appear in official records, explained once in plain words.
GLOSSARY = {
    "OFAC": "the US Treasury's sanctions office",
    "SDN": "Specially Designated Nationals, the US Treasury's main sanctions list",
    "FTO": "Foreign Terrorist Organization",
    "SDGT": "Specially Designated Global Terrorist",
    "LEI": "Legal Entity Identifier, a worldwide company ID",
    "GLEIF": "the worldwide register of company IDs",
    "GLIDE": "a worldwide disaster ID number",
    "GDACS": "the UN and European Commission disaster alert system",
    "RDAP": "the official domain registration records",
    "DNSSEC": "a security setting for website addresses",
    "VIIRS": "a NASA weather satellite camera",
    "MODIS": "a NASA satellite camera",
}


@dataclass(frozen=True)
class Fact:
    ref: str  # the link's ref, for the board's string
    sentence: str  # what the string says, in plain words
    strength: str  # how sure the evidence is, in plain words
    status: str
    sources: list[str]  # where it comes from, by name
    said: list[str]  # what the sources say, in their claims' words with codes explained
    claims: list[str]  # claim refs, for the quote buttons
    against: list[str] = field(default_factory=list)
    label: str = ""  # how sure the evidence is, in two or three words


@dataclass(frozen=True)
class Story:
    ref: str
    name: str
    kind: str  # e.g. "Organisation"
    summary: str
    facts: list[Fact]
    aliases: list[str]
    ids: list[str]
    caution: str = ""  # a warning about people who share a name
    why: str = ""  # why the card is on the board: the key questions whose evidence names it
    connection: str = ""  # how it connects to the investigation's subject, in plain words
    steps: int | None = None  # strings between it and the subject; None when not connected
    tag: str = ""  # the short line at the foot of the card


def gloss(text: str) -> str:
    """The text with each known code explained in brackets the first time it appears."""
    seen: set[str] = set()

    def explain(match: re.Match[str]) -> str:
        code = match.group(0)
        if code in seen:
            return code
        seen.add(code)
        return f"{code} ({GLOSSARY[code]})"

    return re.sub(r"\b(" + "|".join(GLOSSARY) + r")\b", explain, text)


def source_name(source: Source) -> str:
    """A source's everyday name: the list or register for records, the website otherwise."""
    if source.kind in {"record", "image"} and source.title:
        return source.title.split(":", 1)[0].strip()
    return source.domain


def strength(link: Link, sources: list[str], official: bool = True) -> str:
    if link.status == "record" and not official:
        return (
            f"A reference work says this ({', '.join(sources)}): it is edited by volunteers, so "
            "it is useful background but not proof on its own."
        )
    if link.status == "record":
        return f"An official record says this ({', '.join(sources) or 'a record'})."
    if link.status == "corroborated":
        return f"{len(link.origins)} independent sources report this: {', '.join(sources)}."
    if link.status == "assessment":
        return (
            "This is Lantern's own inference from several reports, not something a source "
            "says directly. Read the evidence for and against before relying on it."
        )
    named = ", ".join(sources) or "one source"
    return f"Only one source reports this ({named}), so treat it with caution."


def label(link: Link, official: bool = True) -> str:
    """How sure the evidence is, in two or three words, for the tag on a note."""
    if link.status == "record":
        return "Official record" if official else "Reference work"
    if link.status == "corroborated":
        return f"{len(link.origins)} independent sources"
    if link.status == "assessment":
        return "Lantern's inference"
    return "One source only"


def fact(inv: Investigation, link: Link, names: dict[str, str]) -> Fact:
    claims = [claim for ref in link.claim_refs if (claim := inv.claim(ref))]
    sources = [source for claim in claims if (source := inv.source(claim.source_ref))]
    named = list(dict.fromkeys(source_name(source) for source in sources))
    sentence = SENTENCES[link.relation].format(a=names[link.subject], b=names[link.object])
    official = any(s.reliability in {"A", "B"} for s in sources)
    return Fact(
        ref=link.ref,
        sentence=sentence,
        strength=strength(link, named, official),
        status=link.status,
        sources=named,
        said=list(dict.fromkeys(gloss(claim.statement) for claim in claims))[:4],
        claims=link.claim_refs,
        against=link.against,
        label=label(link, official),
    )


def subject(inv: Investigation) -> str | None:
    """The card the investigation is about: one whose name or alias is written in the
    research question (the best connected if several), else the best connected card."""
    degree = Counter(ref for link in inv.links for ref in (link.subject, link.object))
    asked = set(name_words(inv.brief))
    named = [
        entity
        for entity in inv.entities
        if any(
            (words := set(name_words(name))) and words <= asked
            for name in (entity.name, *entity.aliases)
        )
    ]
    pool = named or [entity for entity in inv.entities if degree[entity.ref]]
    if not pool:
        return None
    return max(pool, key=lambda entity: (degree[entity.ref], -int(entity.ref[1:]))).ref


# Being on the same sanctions list or reported by the same outlet is not a connection
# between two things, so a chain may end at a list keeper or an outlet but not pass through.
DEAD_ENDS = {"designated_by", "reported_by"}


def paths(links: list[Link], start: str) -> dict[str, list[Link]]:
    """The shortest chain of strings from `start` to every card it connects to."""
    found: dict[str, list[Link]] = {start: []}
    hubs = {link.object for link in links if link.relation in DEAD_ENDS}
    queue = deque([start])
    while queue:
        here = queue.popleft()
        if here in hubs and here != start:
            continue
        for link in links:
            if here not in (link.subject, link.object):
                continue
            there = link.object if link.subject == here else link.subject
            if there not in found:
                found[there] = [*found[here], link]
                queue.append(there)
    return found


def stories(inv: Investigation) -> tuple[dict[str, Story], dict[str, Fact]]:
    """The note for every card (by entity ref) and every string (by link ref)."""
    names = {entity.ref: entity.name for entity in inv.entities}
    facts = {link.ref: fact(inv, link, names) for link in inv.links}
    namesakes = _namesakes(inv.entities)
    focus = subject(inv)
    chains = paths(inv.links, focus) if focus else {}
    notes = {}
    for entity in inv.entities:
        mine = [facts[link.ref] for link in inv.links if entity.ref in (link.subject, link.object)]
        chain = chains.get(entity.ref)
        steps = len(chain) if chain is not None else None
        notes[entity.ref] = Story(
            ref=entity.ref,
            name=entity.name,
            kind=KIND_TITLES[entity.kind],
            summary=_summary(entity, mine),
            facts=mine,
            aliases=entity.aliases,
            ids=entity.ids,
            caution=_caution(entity, namesakes),
            why=_why(inv, entity),
            connection=_connection(chain, names, focus, facts),
            steps=steps,
            tag=_tag(steps),
        )
    return notes, facts


def _tag(steps: int | None) -> str:
    if steps is None:
        return "no link to the subject yet"
    if steps == 0:
        return "★ subject of this case"
    return f"{steps} step{'s' if steps != 1 else ''} from the subject"


def _why(inv: Investigation, entity: Entity) -> str:
    """Which key questions' evidence names this card, and in how many claims."""
    refs = [
        ref
        for link in inv.links
        if entity.ref in (link.subject, link.object)
        for ref in [*link.claim_refs, *link.against]
    ]
    claims = [claim for ref in dict.fromkeys(refs) if (claim := inv.claim(ref))]
    if not claims:
        return ""
    asked = list(dict.fromkeys(q for claim in claims for q in claim.question_refs))
    questions = [q for ref in asked if (q := inv.question(ref))]
    shown = " and ".join(f"{q.ref} “{q.text}”" for q in questions) or "this investigation"
    count = f"{len(claims)} claim{'s' if len(claims) != 1 else ''}"
    return f"Named in {count} gathered for {shown}."


def _connection(
    chain: list[Link] | None,
    names: dict[str, str],
    focus: str | None,
    facts: dict[str, Fact],
) -> str:
    """How the card connects to the investigation's subject, as a chain of plain sentences."""
    if focus is None:
        return ""
    if chain is None:
        return (
            f"No string connects it to {names[focus]}, the subject of this investigation. It "
            "came up in the evidence for the reason above, but how it relates to the subject "
            "is not shown yet: treat its relevance as unconfirmed."
        )
    if not chain:
        return "This is what the investigation is about: its name is in the research question."
    sentences = " ".join(facts[link.ref].sentence for link in reversed(chain))
    hops = f"{len(chain)} string{'s' if len(chain) != 1 else ''}"
    return (
        f"{sentences} That is how it connects to {names[focus]}, the subject of this case "
        f"({hops} away)."
    )


def _summary(entity: Entity, facts: list[Fact]) -> str:
    parts = [f"{entity.name} is {KIND_WORDS[entity.kind]}."]
    if entity.aliases:
        shown = " and ".join(entity.aliases[:2])
        more = len(entity.aliases) - 2
        extra = f" and {more} other name{'s' if more != 1 else ''}" if more > 0 else ""
        parts.append(f"It is also known as {shown}{extra}.")
    if facts:
        records = sum(f.strength.startswith("An official record") for f in facts)
        references = sum(f.strength.startswith("A reference work") for f in facts)
        confirmed = sum(f.status == "corroborated" for f in facts)
        single = sum(f.status == "single source" for f in facts)
        guesses = sum(f.status == "assessment" for f in facts)
        counted = [
            (records, "from official records"),
            (references, "from reference works (background only)"),
            (confirmed, "confirmed by two or more independent sources"),
            (single, "from a single source"),
            (guesses, "Lantern's own inference"),
        ]
        detail = "; ".join(f"{n} {words}" for n, words in counted if n)
        total = len(facts)
        found = f"{total} connection{'s' if total != 1 else ''}"
        parts.append(f"Lantern found {found} for {entity.name}: {detail}.")
    return " ".join(parts)


def _namesakes(entities: list[Entity]) -> dict[str, set[str]]:
    holders: dict[str, set[str]] = {}
    for entity in entities:
        if entity.kind == "person_public_role":
            for name in (entity.name, *entity.aliases):
                holders.setdefault(name_key(name), set()).add(entity.ref)
    return holders


def _caution(entity: Entity, holders: dict[str, set[str]]) -> str:
    if entity.kind != "person_public_role":
        return ""
    others: set[str] = set()
    for name in (entity.name, *entity.aliases):
        others |= holders.get(name_key(name), set())
    others.discard(entity.ref)
    if not others:
        return ""
    count = len(others)
    cards = f"{count} other card{'s' if count != 1 else ''}"
    verb = "share" if count != 1 else "shares"
    return (
        f"Careful: {cards} on this board {verb} this name. Nothing in the evidence shows they "
        "are the same person, so Lantern keeps them apart."
    )
