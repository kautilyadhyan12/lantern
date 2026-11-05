"""Entities and links built by code from relations in anchored claims and records.

Who is who follows fixed rules (03 §8.8, invariant 4):
- Organisations, places and events with a shared identifier, name or alias are one entity
  (for organisations, one-letter joining words are ignored: "Lashkar-e-Taiba" and
  "Lashkar-i-Taiba").
- People are never merged on a name alone. Two mentions of the same name are one person
  only with an anchor: the same identifier (a record or Wikidata ID), an explicit "also
  known as" claim, the same source, or the same role towards the same organisation.
- A link's status follows the independence rules: two or more independent origins make it
  corroborated; a record link is rated as its record; a link the assessor proposed is an
  assessment, shown with the claims for and against it.
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from lantern.models import KINDS, RELATIONS, Entity, Link, Party, Triple
from lantern.text import name_words

PERSON = "person_public_role"
ROLES = {"member_of", "leader_of", "founded", "linked_to"}  # relations that anchor a person


def name_key(name: str, *, loose: bool = False) -> str:
    """A name's words in sorted order, so word order, case, accents and punctuation never
    matter. `loose` also drops one-letter joining words (organisations only)."""
    return " ".join(sorted(word for word in name_words(name) if not loose or len(word) > 1))


def name_keys(party: Party) -> set[str]:
    names = (party.name, *party.aliases)
    keys = {name_key(name) for name in names}
    if party.kind == "organisation":
        keys |= {name_key(name, loose=True) for name in names}
    return {key for key in keys if key}


@dataclass
class _Parties:
    """Every party occurrence, joined by union-find."""

    parties: list[Party] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)  # the source each occurrence came from
    parent: list[int] = field(default_factory=list)

    def add(self, party: Party, source: str) -> int:
        self.parties.append(party)
        self.sources.append(source)
        self.parent.append(len(self.parent))
        return len(self.parent) - 1

    def root(self, index: int) -> int:
        while self.parent[index] != index:
            self.parent[index] = self.parent[self.parent[index]]
            index = self.parent[index]
        return index

    def join(self, first: int, second: int) -> bool:
        a, b = self.root(first), self.root(second)
        if a == b:
            return False
        self.parent[max(a, b)] = min(a, b)
        return True


def _pairs(groups: Mapping[str, list[int]]) -> Iterator[tuple[int, int]]:
    for members in groups.values():
        for index, first in enumerate(members):
            for second in members[index + 1 :]:
                yield first, second


def resolve(
    triples: Sequence[Triple], source_of: Mapping[str, str]
) -> tuple[_Parties, list[tuple[int, int]]]:
    """Every stated or record party, joined into entities by the rules above, and for each
    triple the indexes of its subject and object."""
    found = _Parties()
    sides = []
    for triple in triples:
        source = source_of.get(triple.claim_refs[0], "") if triple.claim_refs else ""
        sides.append((found.add(triple.subject, source), found.add(triple.object, source)))
    for first, second in _pairs(_shared_names(found)):
        found.join(first, second)
    for triple, (subject, other) in zip(triples, sides, strict=True):
        if triple.relation == "alias_of" and triple.subject.kind == triple.object.kind:
            found.join(subject, other)  # an explicit "also known as" is an anchor
    _join_people(triples, sides, found)
    return found, sides


def _shared_names(found: _Parties) -> dict[str, list[int]]:
    """Occurrences sharing an identifier, or (not people) a name or alias of the same kind."""
    groups: dict[str, list[int]] = {}
    for index, party in enumerate(found.parties):
        for identifier in party.ids:
            groups.setdefault(f"id {identifier}", []).append(index)
        if party.kind != PERSON:
            for key in name_keys(party):
                groups.setdefault(f"{party.kind} {key}", []).append(index)
    return groups


def _join_people(triples: Sequence[Triple], sides: list[tuple[int, int]], found: _Parties) -> None:
    """People with the same name join only with an anchor: the same source or a shared role."""
    people: dict[str, list[int]] = {}
    for index, party in enumerate(found.parties):
        if party.kind == PERSON:
            for key in name_keys(party):
                people.setdefault(key, []).append(index)
    changed = True
    while changed:  # a new merge can create a shared role anchor, so repeat until stable
        anchors = _anchors(triples, sides, found)
        changed = False
        for first, second in _pairs(people):
            same_source = found.sources[first] and found.sources[first] == found.sources[second]
            shared = anchors.get(found.root(first), set()) & anchors.get(found.root(second), set())
            if (same_source or shared) and found.join(first, second):
                changed = True


def _anchors(
    triples: Sequence[Triple], sides: list[tuple[int, int]], found: _Parties
) -> dict[int, set[tuple[str, int]]]:
    """Each person's roles: (relation, organisation entity) pairs."""
    anchors: dict[int, set[tuple[str, int]]] = {}
    for triple, (subject, other) in zip(triples, sides, strict=True):
        if triple.relation in ROLES and triple.subject.kind == PERSON:
            role = (triple.relation, found.root(other))
            anchors.setdefault(found.root(subject), set()).add(role)
    return anchors


def build(
    triples: Sequence[Triple], source_of: Mapping[str, str], origin_of: Mapping[str, str]
) -> tuple[list[Entity], list[Link]]:
    """Entities and links from stated, record and assessed triples. Assessed triples never
    create entities: they only join entities that already exist, matched by exact name."""
    evidence = [t for t in triples if t.basis != "assessed"]
    found, sides = resolve(evidence, source_of)
    entities, ref_of = _entities(found)
    links: dict[tuple[str, str, str], Link] = {}
    for triple, (subject, other) in zip(evidence, sides, strict=True):
        key = (ref_of[found.root(subject)], triple.relation, ref_of[found.root(other)])
        if triple.relation == "alias_of" or key[0] == key[2]:
            continue
        link = links.setdefault(
            key,
            Link(
                ref="",
                subject=key[0],
                relation=triple.relation,
                object=key[2],
                claim_refs=[],
                basis="stated",
                status="single source",
            ),
        )
        link.claim_refs = list(dict.fromkeys(link.claim_refs + triple.claim_refs))
        if triple.basis == "record":
            link.basis = "record"
    for link in links.values():
        link.origins = sorted({origin_of[c] for c in link.claim_refs if c in origin_of})
        if link.basis == "record":
            link.status = "record"
        elif len(link.origins) >= 2:
            link.status = "corroborated"
    for triple in (t for t in triples if t.basis == "assessed"):
        first = _named(entities, triple.subject.name)
        second = _named(entities, triple.object.name)
        if not first or not second or first == second:
            continue
        if (first, triple.relation, second) in links:
            continue
        links[(first, triple.relation, second)] = Link(
            ref="",
            subject=first,
            relation=triple.relation,
            object=second,
            claim_refs=triple.claim_refs,
            against=triple.against,
            basis="assessed",
            status="assessment",
            origins=[],
        )
    ordered = list(links.values())
    for number, link in enumerate(ordered, start=1):
        link.ref = f"L{number}"
    return entities, ordered


def _entities(found: _Parties) -> tuple[list[Entity], dict[int, str]]:
    members: dict[int, list[Party]] = {}
    for index, party in enumerate(found.parties):
        members.setdefault(found.root(index), []).append(party)
    entities, ref_of = [], {}
    for number, (root, parties) in enumerate(members.items(), start=1):
        # A name from a record or Wikidata (one with an identifier) is preferred.
        named = sorted(
            parties, key=lambda p: (not p.ids, -len([q for q in parties if q.name == p.name]))
        )
        names = list(dict.fromkeys(n for p in parties for n in (p.name, *p.aliases)))
        kinds = [p.kind for p in parties]
        ref_of[root] = f"E{number}"
        entities.append(
            Entity(
                ref=f"E{number}",
                kind=max(set(kinds), key=kinds.count),
                name=named[0].name,
                aliases=[n for n in names if n != named[0].name][:20],
                ids=sorted({i for p in parties for i in p.ids}),
            )
        )
    return entities, ref_of


def _named(entities: Sequence[Entity], name: str) -> str | None:
    """The one entity with exactly this name or alias; None when none or several match."""
    key = name_key(name)
    matches = [
        entity.ref
        for entity in entities
        if key and key in {name_key(n) for n in (entity.name, *entity.aliases)}
    ]
    return matches[0] if len(matches) == 1 else None


ASSESSED = ("member_of", "leader_of", "founded", "linked_to", "killed_in", "located_in")


def stated(  # noqa: PLR0913  # the parts of one proposed relation
    quote: str, *, subject: str, subject_kind: str, relation: str, obj: str, object_kind: str
) -> Triple | None:
    """A relation one claim states, kept only when it uses the fixed vocabulary and kinds
    and both names are written in the claim's anchored quote."""
    relation, kinds = relation.strip().lower(), (subject_kind.strip(), object_kind.strip())
    names = (subject.strip(), obj.strip())
    words = set(name_words(quote))
    if relation not in RELATIONS or not all(kind in KINDS for kind in kinds):
        return None
    if not all(name_words(name) and set(name_words(name)) <= words for name in names):
        return None
    return Triple.model_validate(
        {
            "subject": {"name": names[0], "kind": kinds[0]},
            "relation": relation,
            "object": {"name": names[1], "kind": kinds[1]},
            "claim_refs": [],
            "basis": "stated",
        }
    )


def assessed(
    subject: str, relation: str, obj: str, supporting: list[str], against: list[str]
) -> Triple | None:
    """A connection the assessor proposes from several claims; it needs claims for it."""
    relation = relation.strip().lower()
    if relation not in ASSESSED or not supporting or not subject.strip() or not obj.strip():
        return None
    party = {"kind": "organisation"}  # assessed triples only join existing entities by name
    return Triple.model_validate(
        {
            "subject": {**party, "name": subject.strip()},
            "relation": relation,
            "object": {**party, "name": obj.strip()},
            "claim_refs": supporting,
            "against": [ref for ref in against if ref not in supporting],
            "basis": "assessed",
        }
    )
