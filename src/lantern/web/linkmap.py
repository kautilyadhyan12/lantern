"""The links map, drawn as an evidence board: index cards pinned to cork and joined by
red string. Positions come from a small deterministic force layout, so the same
investigation always draws the same board; the reader can then drag cards around."""

import math
from collections import Counter
from dataclasses import dataclass

from lantern.core.graph import name_key
from lantern.models import Entity, Investigation, Link

WIDTH, HEIGHT, MARGIN = 1200, 760, 110
CARD_W, CARD_H = 168, 66
PIN = CARD_H / 2 - 7  # the pin sits this far above a card's centre
MAX_NODES = 30
STEPS = 200
LINE = 22  # characters per line on a card
PHOTO_LINE = 16  # on a person's card, beside the photo
GRAVITY = 0.6  # pulls separate groups towards the middle so they do not drift to the corners


@dataclass(frozen=True)
class Node:
    entity: Entity
    x: float
    y: float
    tilt: int  # degrees, so cards look pinned by hand
    lines: tuple[str, ...]  # the name, wrapped to fit the card

    @property
    def pin(self) -> tuple[float, float]:
        return self.x, round(self.y - PIN, 1)


@dataclass(frozen=True)
class Edge:
    link: Link
    kinds: str  # the kinds of both ends, for the filters
    path: str  # the string from pin to pin, sagging a little
    label: tuple[float, float]  # where the relation is written on the string


def card_lines(name: str, width: int = LINE) -> tuple[str, ...]:
    """A name wrapped into at most two lines of about `width` characters."""
    lines: list[str] = []
    for word in name.split():
        if lines and len(lines[-1]) + 1 + len(word) <= width:
            lines[-1] += f" {word}"
        else:
            lines.append(word)
    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]
    return tuple(line if len(line) <= width else f"{line[: width - 1]}…" for line in lines)


def tilt(ref: str) -> int:
    """A small, fixed tilt for each card, from -4° to 4°."""
    return (int(ref[1:]) * 37) % 9 - 4


def string(
    first: tuple[float, float], second: tuple[float, float]
) -> tuple[str, tuple[float, float]]:
    """A string between two pins that sags under its own weight, and its midpoint."""
    (x1, y1), (x2, y2) = first, second
    mx = (x1 + x2) / 2
    my = (y1 + y2) / 2 + 0.12 * math.hypot(x2 - x1, y2 - y1) + 8
    path = f"M{x1:.1f},{y1:.1f} Q{mx:.1f},{my:.1f} {x2:.1f},{y2:.1f}"
    middle = (
        round(0.25 * x1 + 0.5 * mx + 0.25 * x2, 1),
        round(0.25 * y1 + 0.5 * my + 0.25 * y2, 1),
    )
    return path, middle


def shown(entities: list[Entity], links: list[Link]) -> tuple[list[Entity], list[Link]]:
    """The best-connected entities (at most MAX_NODES) and the links between them."""
    degree = Counter(ref for link in links for ref in (link.subject, link.object))
    keep = sorted(
        (entity for entity in entities if degree[entity.ref]),
        key=lambda entity: (-degree[entity.ref], int(entity.ref[1:])),
    )[:MAX_NODES]
    refs = {entity.ref for entity in keep}
    return keep, [link for link in links if link.subject in refs and link.object in refs]


def layout(refs: list[str], links: list[Link]) -> dict[str, tuple[float, float]]:
    """Fruchterman-Reingold from evenly spaced starting points, scaled to the drawing."""
    count = len(refs)
    pos = {
        ref: [math.cos(2 * math.pi * i / count), math.sin(2 * math.pi * i / count)]
        for i, ref in enumerate(refs)
    }
    spread, heat = math.sqrt(4.0 / max(count, 1)), 0.2
    for _ in range(STEPS):
        move = {ref: [0.0, 0.0] for ref in refs}
        for i, first in enumerate(refs):
            for second in refs[i + 1 :]:
                dx, dy = pos[first][0] - pos[second][0], pos[first][1] - pos[second][1]
                gap = max(math.hypot(dx, dy), 0.01)
                push = spread * spread / gap
                for ref, sign in ((first, 1), (second, -1)):
                    move[ref][0] += sign * dx / gap * push
                    move[ref][1] += sign * dy / gap * push
        for link in links:
            a, b = pos[link.subject], pos[link.object]
            dx, dy = a[0] - b[0], a[1] - b[1]
            gap = max(math.hypot(dx, dy), 0.01)
            pull = gap * gap / spread
            for ref, sign in ((link.subject, -1), (link.object, 1)):
                move[ref][0] += sign * dx / gap * pull
                move[ref][1] += sign * dy / gap * pull
        for ref in refs:
            move[ref][0] -= GRAVITY * spread * pos[ref][0] * count
            move[ref][1] -= GRAVITY * spread * pos[ref][1] * count
            length = max(math.hypot(*move[ref]), 0.01)
            step = min(length, heat)
            pos[ref][0] += move[ref][0] / length * step
            pos[ref][1] += move[ref][1] / length * step
        heat *= 0.97
    xs, ys = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
    width, height = max(max(xs) - min(xs), 1e-6), max(max(ys) - min(ys), 1e-6)
    scaled = {
        ref: [
            MARGIN + (x - min(xs)) / width * (WIDTH - 2 * MARGIN),
            MARGIN + (y - min(ys)) / height * (HEIGHT - 2 * MARGIN),
        ]
        for ref, (x, y) in pos.items()
    }
    return {ref: (round(x, 1), round(y, 1)) for ref, (x, y) in separate(refs, scaled).items()}


def separate(refs: list[str], pos: dict[str, list[float]]) -> dict[str, list[float]]:
    """Push overlapping cards apart, then keep every card on the board."""
    gap_x, gap_y = CARD_W + 24, CARD_H + 36
    for index, ref in enumerate(refs):  # tiny fixed offsets, so cards on one spot can part
        pos[ref][0] += index * 7 % 11 - 5
        pos[ref][1] += index * 5 % 7 - 3
    for _ in range(200):
        moved = False
        for i, first in enumerate(refs):
            for second in refs[i + 1 :]:
                a, b = pos[first], pos[second]
                dx, dy = b[0] - a[0], b[1] - a[1]
                over_x, over_y = gap_x - abs(dx), gap_y - abs(dy)
                if over_x <= 0 or over_y <= 0:
                    continue
                moved = True
                if over_x / gap_x <= over_y / gap_y:  # the smaller push; sideways on a tie
                    shift = (over_x / 2) * (1 if dx >= 0 else -1)
                    a[0], b[0] = a[0] - shift, b[0] + shift
                else:
                    shift = (over_y / 2) * (1 if dy >= 0 else -1)
                    a[1], b[1] = a[1] - shift, b[1] + shift
        for x_y in pos.values():
            x_y[0] = min(max(x_y[0], MARGIN), WIDTH - MARGIN)
            x_y[1] = min(max(x_y[1], MARGIN), HEIGHT - MARGIN)
        if not moved:
            break
    return pos


def view(inv: Investigation) -> tuple[list[Node], list[Edge]]:
    """What the page draws: nodes with positions, and a line for each link between them."""
    entities, links = shown(inv.entities, inv.links)
    if not entities:
        return [], []
    places = layout([entity.ref for entity in entities], links)
    kind = {entity.ref: entity.kind for entity in entities}
    nodes = [
        Node(
            entity,
            *places[entity.ref],
            tilt(entity.ref),
            card_lines(entity.name, PHOTO_LINE if entity.kind == "person_public_role" else LINE),
        )
        for entity in entities
    ]
    pins = {node.entity.ref: node.pin for node in nodes}
    edges = [
        Edge(
            link,
            f"{kind[link.subject]} {kind[link.object]}",
            *string(pins[link.subject], pins[link.object]),
        )
        for link in links
    ]
    return nodes, edges


def namesakes(entities: list[Entity]) -> list[tuple[str, int]]:
    """Names shared by several people who stay apart because nothing anchors them together,
    with how many separate people carry each."""
    holders: dict[str, set[str]] = {}
    for entity in entities:
        if entity.kind == "person_public_role":
            for name in (entity.name, *entity.aliases):
                holders.setdefault(name_key(name), set()).add(entity.ref)
    groups: list[set[str]] = []
    for refs in holders.values():  # names that overlap make one group, listed once
        if len(refs) < 2:
            continue
        touching = [group for group in groups if group & refs]
        merged = set(refs).union(*touching)
        groups = [group for group in groups if not group & refs] + [merged]
    shown = {entity.ref: entity.name for entity in entities}
    return sorted((shown[min(group, key=lambda ref: int(ref[1:]))], len(group)) for group in groups)
