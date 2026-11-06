"""Earth observation without accounts: places from OpenStreetMap, disaster alerts from
GDACS, and before/after daily satellite images from NASA GIBS.

- A place becomes an area through OpenStreetMap's Nominatim (one request per place per run;
  the safe fetcher paces each host to one request a second, as Nominatim's policy asks).
- `disaster_events` lists GDACS alerts (floods, cyclones, earthquakes, droughts, volcanoes,
  wildfires) for the place's country and period, and keeps only those centred inside the
  area unless the place is a whole country. Graded B: automated alerts.
- `satellite_views` takes NASA's daily true-colour imagery of the area before and after an
  event. For each date it looks at tiny previews of the nearest days, measures by code how
  much is cloud, and keeps the clearest full image. No model reads the images; the claims
  say only when each image was taken and how cloudy it is.

Checked 2026-11-06, no keys: Nominatim `search?format=jsonv2` (ODbL, "© OpenStreetMap
contributors"; at most one request a second, identified client). GDACS
`gdacsapi/api/events/geteventlist/SEARCH` (`eventlist` joined with ";", 204 when nothing
matches; cite GDACS). NASA GIBS WMS `wms/epsg4326/best/wms.cgi` (no stated limit;
acknowledge NASA EOSDIS); MODIS Terra may retire late 2026, so VIIRS NOAA-20 and MODIS Aqua
are tried when a day has no MODIS Terra image.
"""

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, ClassVar, Self
from urllib.parse import urlencode

from pydantic import BaseModel, Field, model_validator

from lantern.core.imagery import clear_share, survey
from lantern.egress import FetchError
from lantern.models import Triple, now
from lantern.tools.adapters.sanctions import DataFetcher
from lantern.tools.base import SourceDraft, ToolArgs, ToolContext, ToolError, ToolKind, ToolResult

NOMINATIM = "https://nominatim.openstreetmap.org/search"
GDACS = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
GIBS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
KINDS = {"FL": "flood", "TC": "tropical cyclone", "EQ": "earthquake", "DR": "drought"}
KINDS |= {"VO": "volcanic eruption", "WF": "wildfire"}
LAYERS = {
    "MODIS_Terra_CorrectedReflectance_TrueColor": "MODIS Terra",
    "VIIRS_NOAA20_CorrectedReflectance_TrueColor": "VIIRS NOAA-20",
    "MODIS_Aqua_CorrectedReflectance_TrueColor": "MODIS Aqua",
}
NEARBY = (0, -1, 1, -2, 2)  # days around each date whose previews are compared
MIN_SPAN, MAX_SPAN = 1.0, 12.0  # degrees: the drawn area is at least 1° and at most 12° wide
MAX_EVENTS = 5
CLEAR_ENOUGH = 0.85  # share of clear ground at which the search for a better day stops


@dataclass(frozen=True)
class Area:
    name: str
    south: float
    north: float
    west: float
    east: float
    country: str
    whole_country: bool

    def contains(self, lat: float, lon: float, margin: float = 0.5) -> bool:
        return (
            self.south - margin <= lat <= self.north + margin
            and self.west - margin <= lon <= self.east + margin
        )

    def framed(self) -> tuple[float, float, float, float]:
        """South, north, west, east of the area to draw: at least 1° and at most 12° wide."""
        lat, lon = (self.south + self.north) / 2, (self.west + self.east) / 2
        half_lat = min(max(self.north - self.south, MIN_SPAN), MAX_SPAN) / 2
        half_lon = min(max(self.east - self.west, MIN_SPAN), MAX_SPAN) / 2
        return lat - half_lat, lat + half_lat, lon - half_lon, lon + half_lon


class Places:
    """Place names resolved through OpenStreetMap, once per run."""

    def __init__(self, fetcher: DataFetcher) -> None:
        self._fetcher, self._found = fetcher, dict[str, Area | None]()

    async def area(self, place: str) -> Area | None:
        key = place.casefold().strip()
        if key not in self._found:
            query = {"q": place, "format": "jsonv2", "limit": 1, "addressdetails": 1}
            query |= {"accept-language": "en"}
            found = await _json(self._fetcher, f"{NOMINATIM}?{urlencode(query)}", "OpenStreetMap")
            self._found[key] = _area(found[0]) if isinstance(found, list) and found else None
        return self._found[key]


def _area(item: dict[str, Any]) -> Area | None:
    try:
        south, north, west, east = (float(v) for v in item["boundingbox"])
    except (KeyError, TypeError, ValueError):
        return None
    address = item.get("address") or {}
    return Area(
        name=str(item.get("display_name") or item.get("name") or ""),
        south=south,
        north=north,
        west=west,
        east=east,
        country=str(address.get("country") or ""),
        whole_country=item.get("addresstype") == "country" or item.get("type") == "country",
    )


async def _json(fetcher: DataFetcher, url: str, what: str) -> Any:
    try:
        page = await fetcher.fetch_data(url, ("application/json",), max_bytes=3_000_000, seconds=30)
    except FetchError as error:
        if "HTTP 204" in str(error) or "HTTP 404" in str(error):
            return None
        raise ToolError(f"{what} could not be reached: {error}") from error
    try:
        return json.loads(page.body)
    except ValueError as error:
        raise ToolError(f"{what} sent an unreadable answer.") from error


class PeriodArgs(ToolArgs):
    place: str = Field(min_length=2, max_length=200)
    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end < self.start or (self.end - self.start).days > 400:
            msg = "end must be on or after start, at most 400 days later"
            raise ValueError(msg)
        return self


class DisasterEvents:
    name: ClassVar[str] = "disaster_events"
    description: ClassVar[str] = (
        "Official automated disaster alerts from GDACS (floods, cyclones, earthquakes, "
        "droughts, volcanoes, wildfires) for a place in the case file and a period (dates as "
        "YYYY-MM-DD): alert level, dates and location. Graded B."
    )
    args_model: ClassVar[type[BaseModel]] = PeriodArgs
    kind: ClassVar[ToolKind] = "record"
    rate_key: ClassVar[str] = "gdacs"
    min_interval: ClassVar[float] = 1.0

    def __init__(self, fetcher: DataFetcher, places: Places) -> None:
        self._fetcher, self._places = fetcher, places

    async def run(self, args: PeriodArgs, _ctx: ToolContext) -> ToolResult:
        area = await self._places.area(args.place)
        if area is None or not area.country:
            return ToolResult([], [], f"OpenStreetMap has no place called “{args.place}”.")
        query = {"eventlist": ";".join(KINDS), "fromDate": args.start.isoformat()}
        query |= {"toDate": args.end.isoformat(), "country": area.country}
        found = await _json(self._fetcher, f"{GDACS}?{urlencode(query)}", "GDACS") or {}
        events = [
            feature
            for feature in found.get("features") or []
            if area.whole_country or area.contains(*_point(feature))
        ][:MAX_EVENTS]
        drafts = [_event(feature, area, args.place) for feature in events]
        others = len(found.get("features") or []) - len(events)
        elsewhere = f"; {others} more elsewhere in {area.country}" if others > 0 else ""
        summary = f"GDACS: {len(drafts)} alerts in {args.place}, {args.start} to {args.end}"
        return ToolResult([], drafts, f"{summary}{elsewhere}.")


def _point(feature: dict[str, Any]) -> tuple[float, float]:
    coordinates = (feature.get("geometry") or {}).get("coordinates") or [999.0, 999.0]
    try:
        return float(coordinates[1]), float(coordinates[0])
    except (IndexError, TypeError, ValueError):
        return 999.0, 999.0


def _event(feature: dict[str, Any], area: Area, place: str) -> SourceDraft:
    p = feature.get("properties") or {}
    kind = KINDS.get(str(p.get("eventtype")), "disaster")
    level = str(p.get("alertlevel") or "unrated")
    lat, lon = _point(feature)
    start, end = str(p.get("fromdate", ""))[:10], str(p.get("todate", ""))[:10]
    name = str(p.get("name") or f"{kind.capitalize()} in {area.country}")
    lines = [
        (
            f"GDACS recorded {'an' if level[0] in 'AEIOU' else 'a'} {level} alert {kind} "
            f"({name}) from {start} to {end}, centred near {lat:.2f}°N, {lon:.2f}°E."
        )
    ]
    if p.get("glide"):
        lines.append(f"The GLIDE disaster number of {name} is {p['glide']}.")
    severity = str((p.get("severitydata") or {}).get("severitytext") or "").strip()
    if severity and not severity.startswith("Magnitude 0"):
        lines.append(f"GDACS gives the severity of {name} as {severity}.")
    event_id = f"gdacs:{p.get('eventtype')}-{p.get('eventid')}"
    relation = Triple.model_validate(
        {
            "subject": {"name": name, "kind": "event", "ids": [event_id]},
            "relation": "located_in",
            "object": {"name": place, "kind": "place"},
            "claim_refs": [],
            "basis": "record",
        }
    )
    report = (p.get("url") or {}).get("report") or "https://www.gdacs.org/"
    body = {
        "event": event_id,
        "properties": {
            k: p.get(k) for k in ("name", "alertlevel", "fromdate", "todate", "glide", "country")
        },
    }
    return SourceDraft(
        url=str(report),
        title=f"GDACS: {name} ({level})",
        published=start or None,
        body=json.dumps(body, ensure_ascii=False, sort_keys=True).encode(),
        text="\n".join(lines),
        kind="record",
        origin="gdacs.org",
        record_claims=tuple(lines),
        grade=("B", "GDACS automated disaster alert (UN and European Commission)"),
        relations=((0, relation),),
    )


class ViewArgs(ToolArgs):
    place: str = Field(min_length=2, max_length=200)
    before: date
    after: date

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not self.before < self.after <= now().date():
            msg = "before must come before after, and after cannot be in the future"
            raise ValueError(msg)
        return self


class SatelliteViews:
    name: ClassVar[str] = "satellite_views"
    description: ClassVar[str] = (
        "Before and after daily satellite images (NASA true colour, about 250 m detail) of a "
        "place in the case file, for two dates (YYYY-MM-DD); the clearest day within two days "
        "of each date is chosen by code. Shows smoke, burn scars, large floods and dry-season "
        "changes; during monsoons and storms the images are often mostly cloud."
    )
    args_model: ClassVar[type[BaseModel]] = ViewArgs
    kind: ClassVar[ToolKind] = "record"
    rate_key: ClassVar[str] = "gibs"
    min_interval: ClassVar[float] = 0.0

    def __init__(self, fetcher: DataFetcher, places: Places) -> None:
        self._fetcher, self._places = fetcher, places

    async def run(self, args: ViewArgs, _ctx: ToolContext) -> ToolResult:
        area = await self._places.area(args.place)
        if area is None:
            return ToolResult([], [], f"OpenStreetMap has no place called “{args.place}”.")
        drafts, notes = [], []
        for label, target in (("before", args.before), ("after", args.after)):
            best = await self._clearest(area, target)
            if best is None:
                notes.append(f"no image near {target}")
                continue
            day, layer, covered, cloud = best
            drafts.append(
                await self._image(
                    area,
                    args.place,
                    label=label,
                    target=target,
                    day=day,
                    layer=layer,
                    seen=(covered, cloud),
                )
            )
            notes.append(f"{label}: {day}, about {cloud:.0%} cloud")
        summary = f"NASA satellite views of {args.place}: {'; '.join(notes)}."
        return ToolResult([], drafts, summary)

    def _url(
        self,
        frame: tuple[float, float, float, float],
        day: date,
        layer: str,
        size: tuple[int, int],
        form: str,
    ) -> str:
        south, north, west, east = frame
        query = {
            "SERVICE": "WMS",
            "REQUEST": "GetMap",
            "VERSION": "1.3.0",
            "LAYERS": layer,
            "CRS": "EPSG:4326",
            "BBOX": f"{south:.4f},{west:.4f},{north:.4f},{east:.4f}",
            "WIDTH": size[0],
            "HEIGHT": size[1],
            "FORMAT": form,
            "TIME": day.isoformat(),
        }
        return f"{GIBS}?{urlencode(query)}"

    async def _clearest(self, area: Area, target: date) -> tuple[date, str, float, float] | None:
        """The day and layer near `target` whose preview shows the most clear ground: its
        covered share and cloud share. MODIS Aqua is asked only when the others have none."""
        frame, best, score = area.framed(), None, -1.0
        layers = list(LAYERS)
        for offset in NEARBY:
            day = target + timedelta(days=offset)
            if day > now().date():
                continue
            found = False
            for layer in layers:
                if found and layer == layers[-1]:
                    break  # the backup layer only fills days the main ones miss
                url = self._url(frame, day, layer, (80, 40), "image/png")
                try:
                    preview = await self._fetcher.fetch_data(url, ("image/png",), max_bytes=200_000)
                except FetchError:
                    continue
                measured = survey(preview.body)
                if measured is None:
                    continue
                found = True
                if clear_share(*measured) > score:
                    best, score = (day, layer, *measured), clear_share(*measured)
                if score >= CLEAR_ENOUGH:
                    break
            if score >= CLEAR_ENOUGH:
                break  # clear enough: no need to look further
        return best

    async def _image(  # noqa: PLR0913  # one image's place, dates, layer and cloud share
        self,
        area: Area,
        place: str,
        *,
        label: str,
        target: date,
        day: date,
        layer: str,
        seen: tuple[float, float],
    ) -> SourceDraft:
        frame = area.framed()
        south, north, west, east = frame
        width = 800
        height = max(200, min(800, round(width * (north - south) / (east - west))))
        url = self._url(frame, day, layer, (width, height), "image/jpeg")
        try:
            image = await self._fetcher.fetch_data(url, ("image/jpeg",), max_bytes=3_000_000)
        except FetchError as error:
            raise ToolError(f"NASA GIBS could not send the image: {error}") from error
        sensor, (covered, cloud) = LAYERS[layer], seen
        missing = f"; the satellite did not cover about {1 - covered:.0%} of it that day" * (
            covered < 0.98
        )
        claim = (
            f"A NASA {sensor} true-colour satellite image of {place} taken on {day} "
            f"(the clearest day near {target}, {label} the event) shows about {cloud:.0%} of "
            f"the imaged area under cloud{missing}, as measured by code."
        )
        text = (
            f"{claim}\nArea drawn: {south:.2f}°N to {north:.2f}°N, {west:.2f}°E to {east:.2f}°E "
            f"({area.name}; place data © OpenStreetMap contributors). Imagery: NASA EOSDIS GIBS, "
            f"layer {layer}."
        )
        viewer = (
            "https://worldview.earthdata.nasa.gov/?"
            f"v={west:.3f},{south:.3f},{east:.3f},{north:.3f}&t={day}&l={layer}"
        )
        return SourceDraft(
            url=viewer,
            title=f"NASA {sensor} image of {place}, {day} ({label})",
            published=day.isoformat(),
            body=image.body,
            text=text,
            kind="image",
            origin="nasa.gov",
            record_claims=(claim,),
            grade=("A", "NASA satellite imagery (GIBS)"),
        )
