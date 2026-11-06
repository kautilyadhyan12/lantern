"""Earth observation without accounts: reading previews by code, GDACS alerts, and the
clearest NASA images before and after an event.

The GDACS and Nominatim samples are abridged copies of real answers fetched on 2026-11-06;
the image previews are built here, so the tests need no network.
"""

import json
import struct
import zlib
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from lantern.agent.loop import Agent
from lantern.config import AppSettings
from lantern.core.imagery import clear_share, pixels, survey
from lantern.egress import FetchError, Page
from lantern.models import Investigation, Question, Report, Source, now
from lantern.pipeline import Limits, Tools
from lantern.store import Store
from lantern.tools.adapters.earth import (
    GDACS,
    GIBS,
    NOMINATIM,
    Area,
    DisasterEvents,
    Places,
    SatelliteViews,
)
from lantern.tools.base import ToolContext, ToolError
from lantern.web import earthview
from lantern.web.app import asset_urls, create_app

from .fakes import FakeFetcher, FakeSearch
from .test_agent import DONE, Researcher

CTX = ToolContext()
CLOUD, GROUND, GAP = (240, 240, 240, 255), (40, 90, 50, 255), (0, 0, 0, 0)
JPEG = b"\xff\xd8\xff\xe0fake jpeg bytes"


def png(rows, *, filters=(0,)):
    """A real RGBA PNG of the given pixel rows, each row encoded with one PNG filter."""
    width, raw, previous = len(rows[0]), bytearray(), bytes(len(rows[0]) * 4)
    for y, row in enumerate(rows):
        line = bytes(value for pixel in row for value in pixel)
        kind = filters[y % len(filters)]
        out = bytearray()
        for i, value in enumerate(line):
            left = line[i - 4] if i >= 4 else 0
            up, corner = previous[i], previous[i - 4] if i >= 4 else 0
            guess = left + up - corner
            paeth = min(
                (abs(guess - left), 0, left),
                (abs(guess - up), 1, up),
                (abs(guess - corner), 2, corner),
            )[2]
            base = {0: 0, 1: left, 2: up, 3: (left + up) // 2, 4: paeth}[kind]
            out.append((value - base) & 0xFF)
        raw += bytes([kind]) + out
        previous = line

    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", width, len(rows), 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw)))
        + chunk(b"IEND", b"")
    )


def preview(cloud=0.0, gap=0.0, size=(20, 10)):
    width, height = size
    count = width * height
    gaps, clouds = round(count * gap), round(count * (1 - gap) * cloud)
    flat = [GAP] * gaps + [CLOUD] * clouds + [GROUND] * (count - gaps - clouds)
    return png([flat[y * width : (y + 1) * width] for y in range(height)])


# ---- reading previews by code -------------------------------------------------------


def test_the_decoder_undoes_every_png_filter():
    rows = [
        [(x * 13 % 256, y * 29 % 256, (x + y) * 7 % 256, 255) for x in range(9)] for y in range(6)
    ]
    decoded = pixels(png(rows, filters=(0, 1, 2, 3, 4)))
    assert decoded is not None
    assert decoded[:2] == (9, 6)
    assert decoded[2] == [pixel for row in rows for pixel in row]


def test_cloud_and_gaps_are_measured_and_unreadable_images_refused():
    assert survey(preview(cloud=1.0)) == (1.0, 1.0)
    covered, cloud = survey(preview(cloud=0.5, gap=0.25))
    assert (covered, round(cloud, 2)) == (0.75, 0.5)
    assert clear_share(covered, cloud) == pytest.approx(0.375, abs=0.01)
    assert survey(preview(gap=0.9)) is None  # mostly no data: no satellite pass
    assert survey(b"not a png") is None
    assert survey(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20) is None


# ---- places and GDACS alerts -------------------------------------------------------

ASSAM = [
    {
        "display_name": "Assam, India",
        "boundingbox": ["24.1360", "27.9712", "89.6986", "96.0124"],
        "addresstype": "state",
        "address": {"state": "Assam", "country": "India"},
    }
]
INDIA = [
    {
        "display_name": "India",
        "boundingbox": ["6.5", "35.7", "68.1", "97.4"],
        "addresstype": "country",
        "address": {"country": "India"},
    }
]


def event(kind, lat, lon, *, level="Orange", name="Flood in India", glide="FL-2026-000165-IND"):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "eventtype": kind,
            "eventid": 1104121,
            "name": name,
            "alertlevel": level,
            "country": "India",
            "fromdate": "2026-08-09T01:00:00",
            "todate": "2026-10-07T01:00:00",
            "glide": glide,
            "severitydata": {"severitytext": "Magnitude 0 "},
            "url": {"report": "https://www.gdacs.org/report.aspx?eventid=1104121"},
        },
    }


EVENTS = {
    "features": [
        event("FL", 26.2, 91.7),  # Guwahati, inside Assam
        event("FL", 11.33, 78.61),  # Tamil Nadu
        event("TC", 16.4, 81.8, level="Red", name="Tropical Cyclone ARNAB-26", glide=""),
    ]
}


class Data:
    """A fake data service: answers by URL prefix (a value, or a function of the URL)."""

    def __init__(self, routes):
        self.routes, self.urls = routes, []

    async def fetch_data(self, url, accept, *, max_bytes, seconds=60.0):
        self.urls.append(url)
        for prefix, answer in self.routes.items():
            if url.startswith(prefix):
                found = answer(url) if callable(answer) else answer
                if isinstance(found, Exception):
                    raise found
                body = found if isinstance(found, bytes) else json.dumps(found).encode()
                return Page(url=url, content_type=accept[0], body=body)
        raise FetchError("The data service answered HTTP 404.", "refused")


def place_for(url):
    return INDIA if "q=India" in url else ASSAM if "q=Assam" in url else []


async def test_alerts_inside_the_area_become_code_claims_with_a_place_link():
    data = Data({NOMINATIM: place_for, GDACS: EVENTS})
    tool = DisasterEvents(data, Places(data))
    result = await tool.run(
        tool.args_model(place="Assam", start="2026-05-01", end="2026-10-31"), CTX
    )
    [draft] = result.sources
    assert (
        result.summary
        == "GDACS: 1 alerts in Assam, 2026-05-01 to 2026-10-31; 2 more elsewhere in India."
    )
    assert (draft.kind, draft.grade[0], draft.origin) == ("record", "B", "gdacs.org")
    assert draft.record_claims == (
        (
            "GDACS recorded an Orange alert flood (Flood in India) from 2026-08-09 to 2026-10-07, "
            "centred near 26.20°N, 91.70°E."
        ),
        "The GLIDE disaster number of Flood in India is FL-2026-000165-IND.",
    )  # "Magnitude 0" says nothing, so it is left out
    [(index, link)] = draft.relations
    assert (index, link.subject.kind, link.relation, link.object.name) == (
        0,
        "event",
        "located_in",
        "Assam",
    )
    query = parse_qs(urlsplit(data.urls[-1]).query)
    assert query["eventlist"] == ["FL;TC;EQ;DR;VO;WF"]
    assert query["country"] == ["India"]


async def test_a_whole_country_keeps_every_alert_and_unknown_places_say_so():
    data = Data({NOMINATIM: place_for, GDACS: EVENTS})
    tool = DisasterEvents(data, Places(data))
    found = await tool.run(
        tool.args_model(place="India", start="2026-05-01", end="2026-10-31"), CTX
    )
    assert len(found.sources) == 3
    assert (
        found.sources[2].record_claims[0].startswith("GDACS recorded a Red alert tropical cyclone")
    )
    nowhere = await tool.run(
        tool.args_model(place="Atlantis", start="2026-05-01", end="2026-10-31"), CTX
    )
    assert nowhere.summary == "OpenStreetMap has no place called “Atlantis”."
    nothing = DisasterEvents(
        Data({NOMINATIM: place_for, GDACS: FetchError("answered HTTP 204", "refused")}),
        Places(Data({NOMINATIM: place_for})),
    )
    empty = await nothing.run(
        nothing.args_model(place="Assam", start="2026-01-01", end="2026-01-02"), CTX
    )
    assert empty.sources == []
    down = Data({NOMINATIM: FetchError("Could not connect.", "unreachable")})
    broken = DisasterEvents(down, Places(down))
    with pytest.raises(ToolError, match="OpenStreetMap could not be reached"):
        await broken.run(
            broken.args_model(place="Assam", start="2026-01-01", end="2026-01-02"), CTX
        )


def test_periods_must_be_ordered_and_bounded():
    with pytest.raises(ValidationError, match="end must be on or after start"):
        DisasterEvents.args_model(place="Assam", start="2026-05-01", end="2026-04-01")
    with pytest.raises(ValidationError):
        DisasterEvents.args_model(place="Assam", start="2024-01-01", end="2026-01-01")


def test_places_resolve_once_and_areas_are_framed_for_drawing():
    city = Area("Guwahati", 26.1, 26.2, 91.6, 91.8, "India", whole_country=False)
    assert city.framed() == pytest.approx((25.65, 26.65, 91.2, 92.2))  # at least 1° wide
    huge = Area("India", 6.5, 35.7, 68.1, 97.4, "India", whole_country=True)
    south, north, west, east = huge.framed()
    assert (north - south, east - west) == pytest.approx((12.0, 12.0))  # at most 12° wide


async def test_a_place_is_looked_up_once_per_run():
    data = Data({NOMINATIM: place_for})
    places = Places(data)
    assert (await places.area("Assam")).country == "India"
    assert (await places.area(" assam ")).country == "India"
    assert len(data.urls) == 1


# ---- the clearest NASA images --------------------------------------------------------


def gibs(scene):
    """NASA GIBS: previews built from `scene[(day, layer)] = (cloud, gap)`; JPEG for images."""

    def answer(url):
        query = parse_qs(urlsplit(url).query)
        key = (query["TIME"][0], query["LAYERS"][0][:4])
        if query["FORMAT"][0] == "image/jpeg":
            return JPEG
        cloud, gap = scene.get(key, (0.0, 1.0))  # no entry: no pass that day
        return preview(cloud=cloud, gap=gap)

    return answer


async def test_the_clearest_day_and_satellite_near_each_date_is_kept():
    scene = {
        ("2026-05-20", "MODI"): (0.4, 0.2),
        ("2026-05-20", "VIIR"): (0.3, 0.0),
        ("2026-05-19", "MODI"): (0.9, 0.0),
        ("2026-05-21", "VIIR"): (0.05, 0.0),  # the clearest: chosen even though a day off
        ("2026-10-25", "MODI"): (0.02, 0.0),  # clear at once: nothing more is asked
    }
    data = Data({NOMINATIM: place_for, GIBS: gibs(scene)})
    tool = SatelliteViews(data, Places(data))
    result = await tool.run(
        tool.args_model(place="Assam", before="2026-05-20", after="2026-10-25"), CTX
    )
    before, after = result.sources
    assert (before.kind, before.published, after.published) == ("image", "2026-05-21", "2026-10-25")
    assert before.body == JPEG
    assert before.record_claims == (
        (
            "A NASA VIIRS NOAA-20 true-colour satellite image of Assam taken on 2026-05-21 (the "
            "clearest day near 2026-05-20, before the event) shows about 5% of the imaged area "
            "under cloud, as measured by code."
        ),
    )
    assert "l=VIIRS_NOAA20_CorrectedReflectance_TrueColor" in before.url
    assert "worldview.earthdata.nasa.gov" in before.url
    assert "© OpenStreetMap contributors" in before.text
    assert result.summary == (
        "NASA satellite views of Assam: before: 2026-05-21, about 5% cloud; after: "
        "2026-10-25, about 2% cloud."
    )
    asked = [parse_qs(urlsplit(u).query)["TIME"][0] for u in data.urls if "2026-10" in u]
    assert asked == ["2026-10-25", "2026-10-25"]  # one preview, then the image


async def test_gaps_between_passes_are_reported_and_missing_days_say_so():
    scene = {("2026-05-20", "MODI"): (0.1, 0.3)}
    data = Data({NOMINATIM: place_for, GIBS: gibs(scene)})
    tool = SatelliteViews(data, Places(data))
    result = await tool.run(
        tool.args_model(place="Assam", before="2026-05-20", after="2026-06-20"), CTX
    )
    [image] = result.sources
    assert "the satellite did not cover about 30% of it that day" in image.record_claims[0]
    assert result.summary.endswith("; no image near 2026-06-20.")


def test_views_need_ordered_dates_in_the_past():
    tomorrow = (now().date() + timedelta(days=1)).isoformat()
    with pytest.raises(ValidationError, match="cannot be in the future"):
        SatelliteViews.args_model(place="Assam", before="2026-05-01", after=tomorrow)
    with pytest.raises(ValidationError, match="before must come before after"):
        SatelliteViews.args_model(place="Assam", before="2026-06-01", after="2026-05-01")


# ---- the report and the agent --------------------------------------------------------


def test_saved_images_are_shown_and_served_only_as_jpeg(tmp_path):
    store = Store(tmp_path)
    inv = Investigation(id=store.new_id(), brief="Floods in Assam?", status="done")
    inv.questions = [Question(ref="Q1", text="What happened?")]
    inv.report = Report()
    common = {
        "domain": "nasa.gov",
        "fetched_at": now(),
        "size": 1,
        "reliability": "A",
        "reliability_reason": "r",
        "text_sha256": store.put_text("about"),
    }
    inv.sources = [
        Source(
            ref="S1",
            url="https://worldview.earthdata.nasa.gov/?t=2026-05-21",
            kind="image",
            title="NASA VIIRS NOAA-20 image of Assam, 2026-05-21 (before)",
            sha256=store.put_blob(JPEG),
            **common,
        ),
        Source(
            ref="S2",
            url="https://example.org/page",
            kind="page",
            sha256=store.put_blob(b"<html>page</html>"),
            **common,
        ),
    ]
    store.save(inv)
    client = TestClient(
        create_app(AppSettings(data_dir=str(tmp_path), tavily_api_key="t", groq_api_key="g"))
    )
    page = client.get(f"/investigations/{inv.id}").text
    assert "Satellite views" in page
    assert f'src="/investigations/{inv.id}/sources/S1/image"' in page
    served = client.get(f"/investigations/{inv.id}/sources/S1/image")
    assert (served.status_code, served.headers["content-type"], served.content) == (
        200,
        "image/jpeg",
        JPEG,
    )
    assert client.get(f"/investigations/{inv.id}/sources/S2/image").status_code == 404
    assert client.get(f"/investigations/{inv.id}/sources/S9/image").status_code == 404
    assert (
        "Satellite image, saved as received from NASA"
        in client.get(f"/investigations/{inv.id}/sources/S1").text
    )


async def test_the_agent_saves_views_and_alerts_only_for_places_in_the_evidence(tmp_path):
    def script(ref, step, user):
        if ref == "Q1" and step == 1:
            return {
                "calls": [
                    {
                        "tool": "disaster_events",
                        "args": {"place": "Assam", "start": "2026-05-01", "end": "2026-10-31"},
                    },
                    {
                        "tool": "satellite_views",
                        "args": {"place": "Assam", "before": "2026-05-20", "after": "2026-10-25"},
                    },
                    {
                        "tool": "satellite_views",
                        "args": {"place": "Gaza", "before": "2026-05-20", "after": "2026-10-25"},
                    },
                ]
            }
        return DONE

    data = Data(
        {
            NOMINATIM: place_for,
            GDACS: EVENTS,
            GIBS: gibs({("2026-05-20", "MODI"): (0.0, 0.0), ("2026-10-25", "MODI"): (0.0, 0.0)}),
        }
    )
    places = Places(data)
    store = Store(tmp_path)
    model = Researcher(script=script)
    inv = Investigation(id=store.new_id(), brief="What happened in the Assam floods of 2026?")
    model.usage = inv.usage
    tools = Tools(
        model=model,
        searcher=FakeSearch(),
        fetcher=FakeFetcher(),
        records=(DisasterEvents(data, places), SatelliteViews(data, places)),
    )
    inv = await Agent(inv, tools, store, Limits()).run()
    assert inv.status == "done", inv.error
    images = [s for s in inv.sources if s.kind == "image"]
    assert [s.published for s in images] == ["2026-05-20", "2026-10-25"]
    assert store.blob(images[0].sha256) == JPEG
    claims = [c for c in inv.claims if c.source_ref in {s.ref for s in images}]
    assert len(claims) == 2
    assert any(s.origin == "gdacs.org" for s in inv.sources)
    messages = [step.message for step in inv.steps]
    assert any(
        m.startswith("satellite_views “Gaza”: not run. Lantern looks up records") for m in messages
    )
    assert "ExtractOut" not in model.calls  # no model reads images or alerts


def test_the_interactive_viewer_takes_its_area_and_dates_from_the_saved_images(tmp_path):
    store = Store(tmp_path)
    inv = Investigation(id=store.new_id(), brief="Floods in Assam?", status="done")
    inv.questions = [Question(ref="Q1", text="What happened?")]
    inv.report = Report()
    common = {
        "domain": "nasa.gov",
        "fetched_at": now(),
        "size": 1,
        "reliability": "A",
        "reliability_reason": "r",
        "text_sha256": store.put_text("about"),
        "sha256": store.put_blob(JPEG),
        "kind": "image",
    }
    viewer = "https://worldview.earthdata.nasa.gov/?v=89.699,24.136,96.012,27.971&l=X&t="
    titled = {"title": "NASA VIIRS NOAA-20 image of Assam, 2026-05-21 (before)"}
    inv.sources = [
        Source(ref="S1", url=f"{viewer}2026-05-21", **titled, **common),
        Source(ref="S2", url="https://worldview.earthdata.nasa.gov/?broken", **common),
        Source(ref="S3", url=f"{viewer}2026-10-25", **common),
    ]
    store.save(inv)
    view = earthview.view(inv)
    assert (view.west, view.south, view.east, view.north) == (89.699, 24.136, 96.012, 27.971)
    assert (view.before, view.after, view.name) == ("2026-05-21", "2026-10-25", "Assam")
    assert earthview.view(Investigation(id="x", brief="y")) is None
    client = TestClient(
        create_app(AppSettings(data_dir=str(tmp_path), tavily_api_key="t", groq_api_key="g"))
    )
    response = client.get(f"/investigations/{inv.id}")
    page = response.text
    assert 'id="eo"' in page
    assert 'data-west="89.699"' in page
    assert 'id="eo-before" value="2026-05-21"' in page
    assert 'id="eo-after" value="2026-10-25"' in page
    assert 'data-name="Assam"' in page
    assert "Outline of Assam" in page
    assert '<script src="/static/vendor/leaflet-1.9.4/leaflet.js?v=' in page
    assert (
        "img-src 'self' data: https://gibs.earthdata.nasa.gov;"
        in response.headers["content-security-policy"]
    )
    assert "script-src 'self';" in response.headers["content-security-policy"]  # still local only
    assert client.get("/static/vendor/leaflet-1.9.4/leaflet.js").status_code == 200
    assert client.get("/static/earth.js").status_code == 200


def test_static_files_are_versioned_by_content_and_always_rechecked(tmp_path):
    folder = tmp_path / "static"
    (folder / "vendor").mkdir(parents=True)
    (folder / "app.js").write_text("one")
    (folder / "vendor" / "lib.js").write_text("lib")
    first = asset_urls(folder)
    assert first("app.js").startswith("/static/app.js?v=")
    assert first("vendor/lib.js").startswith("/static/vendor/lib.js?v=")
    (folder / "app.js").write_text("two")
    assert asset_urls(folder)("app.js") != first("app.js")  # a changed file gets a new URL
    client = TestClient(
        create_app(AppSettings(data_dir=str(tmp_path), tavily_api_key="t", groq_api_key="g"))
    )
    home = client.get("/").text
    assert '<script src="/static/app.js?v=' in home
    assert client.get("/static/app.js").headers["cache-control"] == "no-cache"
