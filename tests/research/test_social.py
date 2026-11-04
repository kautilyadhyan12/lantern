"""Social posts are event-centred ground reports; authors are never stored or shown."""

import json

import httpx

from lantern.models import Investigation
from lantern.pipeline import Investigator, Limits, Tools
from lantern.report import to_markdown
from lantern.social import PublicSocial, html_to_text
from lantern.store import Store

from .fakes import FakeFetcher, FakeModel, FakeSearch, FakeSocial

LONG = "The river has flooded the main road and the bridge near the market is closed."


def status(**overrides):
    item = {
        "url": "https://mastodon.example/@someone/1",
        "created_at": "2026-11-01T08:00:00.000Z",
        "language": "en",
        "visibility": "public",
        "reblog": None,
        "spoiler_text": "",
        "content": f"<p>{LONG}</p>",
        "account": {
            "acct": "someone",
            "url": "https://mastodon.example/@someone",
            "discoverable": True,
        },
    }
    item.update(overrides)
    return item


def client(payload, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, json=payload)

    return PublicSocial("TestBot/1.0", transport=httpx.MockTransport(handler))


async def test_mastodon_hashtag_skips_opted_out_reblogged_private_and_short_posts():
    payload = [
        status(),
        status(account={"acct": "quiet", "discoverable": False}),
        status(reblog={"id": "1"}),
        status(visibility="unlisted"),
        status(content="<p>too short</p>"),
    ]
    seen = []
    posts = await client(payload, seen).hashtag("#Assam Floods!", 20)
    assert [post.text for post in posts] == [LONG]
    assert seen[0].url.path == "/api/v1/timelines/tag/AssamFloods"
    assert seen[0].headers["user-agent"] == "TestBot/1.0"
    assert "someone" not in posts[0].origin


async def test_bluesky_search_skips_labelled_posts_and_links_without_handles():
    def post(did, labels=()):
        return {
            "uri": f"at://{did}/app.bsky.feed.post/abc",
            "author": {
                "did": did,
                "handle": "person.bsky.social",
                "labels": [{"val": v} for v in labels],
            },
            "labels": [],
            "record": {"text": LONG, "createdAt": "2026-11-01T08:00:00Z", "langs": ["en"]},
        }

    payload = {"posts": [post("did:plc:one"), post("did:plc:two", ["!no-unauthenticated"])]}
    posts = await client(payload).search("flood market road", 20)
    assert len(posts) == 1
    assert posts[0].url == "https://bsky.app/profile/did:plc:one/post/abc"
    assert "person" not in posts[0].url


async def test_failures_return_no_posts():
    def handler(request):
        return httpx.Response(503)

    social = PublicSocial("TestBot/1.0", transport=httpx.MockTransport(handler))
    assert await social.search("x", 5) == []
    assert await social.hashtag("x", 5) == []


def test_html_to_text_keeps_text_and_breaks():
    assert html_to_text("<p>A &amp; B<br>C</p><p>D</p>") == "A & B\nC\n\nD"


async def test_posts_become_ground_reports_without_author_identity(tmp_path):
    store = Store(tmp_path)
    social = FakeSocial()
    tools = Tools(model=FakeModel(), searcher=FakeSearch(), fetcher=FakeFetcher(), social=social)
    inv = Investigation(id=store.new_id(), brief="What happened in the district floods?")
    inv = await Investigator(inv, tools, store, Limits()).run()
    assert inv.status == "done", inv.error
    assert social.hashtags == ["DistrictFloods"]
    posts = [source for source in inv.sources if source.kind == "post"]
    # Two search calls return the same five posts: duplicates and a third post by one
    # account are dropped, leaving alice, bob twice and carol.
    assert len(posts) == 4
    assert {post.reliability for post in posts} == {"D"}
    assert len({post.origin for post in posts}) == 3
    for post in posts:
        saved = json.loads((store.root / "blobs" / f"{post.sha256}.bin").read_text())
        assert set(saved) == {"platform", "url", "posted_at", "language", "text"}
    claims = [c for c in inv.claims if inv.source(c.source_ref).kind == "post"]
    assert claims
    assert all(c.statement.startswith("A social media post reported") for c in claims)
    stored = (store.root / "investigations" / f"{inv.id}.json").read_text()
    assert "alice" not in stored.replace("did:plc:alice", "")


async def test_markdown_export_does_not_print_post_addresses(tmp_path):
    store = Store(tmp_path)
    tools = Tools(
        model=FakeModel(), searcher=FakeSearch(), fetcher=FakeFetcher(), social=FakeSocial()
    )
    inv = Investigation(id=store.new_id(), brief="What happened in the district floods?")
    inv = await Investigator(inv, tools, store, Limits()).run()
    markdown = to_markdown(inv)
    assert "Bluesky post (ground report" in markdown
    assert "bsky.app/profile" not in markdown
