"""Settings for the interactive satellite viewer on the report page: the area and the two
dates, read from the investigation's saved NASA images (their Worldview links)."""

from dataclasses import dataclass
from datetime import date
from urllib.parse import parse_qs, urlsplit

from lantern.models import Investigation, now

GIBS_TILES = "https://gibs.earthdata.nasa.gov"  # allowed as an image source by the page's CSP


@dataclass(frozen=True)
class EarthView:
    west: float
    south: float
    east: float
    north: float
    before: str  # YYYY-MM-DD
    after: str
    today: str
    name: str  # the place, as the images name it


def view(inv: Investigation) -> EarthView | None:
    """The area and dates of the first and last saved satellite images, or None."""
    found = []
    for source in inv.sources:
        if source.kind != "image":
            continue
        query = parse_qs(urlsplit(source.url).query)
        try:
            west, south, east, north = (float(v) for v in query["v"][0].split(","))
            day = date.fromisoformat(query["t"][0]).isoformat()
        except (KeyError, IndexError, ValueError):
            continue
        name = (source.title or "").split(" image of ", 1)[-1].rsplit(", ", 1)[0]
        found.append((west, south, east, north, day, name))
    if not found:
        return None
    west, south, east, north, before, name = found[0]
    after = found[-1][4]
    today = now().date().isoformat()
    return EarthView(west, south, east, north, before, after, today, name or "the area")
