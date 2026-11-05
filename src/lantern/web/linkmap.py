"""The links map: positions computed by code with a small deterministic force layout, so
the same investigation always draws the same map. No JavaScript library is needed."""

import math
from collections import Counter
from dataclasses import dataclass

from lantern.models import Entity, Investigation, Link

WIDTH, HEIGHT, MARGIN = 960, 560, 60
MAX_NODES = 40
STEPS = 200


@dataclass(frozen=True)
class Node:
    entity: Entity
    x: float
    y: float


@dataclass(frozen=True)
class Edge:
    link: Link
    kinds: str  # the kinds of both ends, for the filters
    x1: float
    y1: float
    x2: float
    y2: float


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
            length = max(math.hypot(*move[ref]), 0.01)
            step = min(length, heat)
            pos[ref][0] += move[ref][0] / length * step
            pos[ref][1] += move[ref][1] / length * step
        heat *= 0.97
    xs, ys = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
    width, height = max(max(xs) - min(xs), 1e-6), max(max(ys) - min(ys), 1e-6)
    return {
        ref: (
            round(MARGIN + (x - min(xs)) / width * (WIDTH - 2 * MARGIN), 1),
            round(MARGIN + (y - min(ys)) / height * (HEIGHT - 2 * MARGIN), 1),
        )
        for ref, (x, y) in pos.items()
    }


def view(inv: Investigation) -> tuple[list[Node], list[Edge]]:
    """What the page draws: nodes with positions, and a line for each link between them."""
    entities, links = shown(inv.entities, inv.links)
    if not entities:
        return [], []
    places = layout([entity.ref for entity in entities], links)
    kind = {entity.ref: entity.kind for entity in entities}
    nodes = [Node(entity, *places[entity.ref]) for entity in entities]
    edges = [
        Edge(
            link,
            f"{kind[link.subject]} {kind[link.object]}",
            *places[link.subject],
            *places[link.object],
        )
        for link in links
    ]
    return nodes, edges
