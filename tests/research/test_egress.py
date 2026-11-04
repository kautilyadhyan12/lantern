"""Page fetching never reaches internal addresses and obeys robots.txt and limits."""

import httpx
import pytest

from lantern.egress import Fetcher, FetchError, is_public

HTML = b"<html><body><p>" + b"Public page text. " * 30 + b"</p></body></html>"


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("8.8.8.8", True),
        ("2606:4700:4700::1111", True),
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("192.168.0.10", False),
        ("172.16.5.4", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),  # noqa: S104  # an address under test, not a bind
        ("224.0.0.1", False),
        ("::1", False),
        ("fd00::1", False),
        ("::ffff:127.0.0.1", False),
        ("2002:7f00:1::", False),
        ("192.0.2.1", False),
    ],
)
def test_address_classes(address, public):
    assert is_public(address) is public


def make(routes, resolve=None):
    seen = []

    def handler(request):
        seen.append(request)
        key = (request.headers["host"], request.url.path)
        status, headers, body = routes.get(key, (404, {}, b""))
        return httpx.Response(status, headers=headers, content=body)

    async def resolver(host, port):
        return (resolve or {}).get(host, ["93.184.215.14"])

    return Fetcher(
        "TestBot/1.0",
        transport=httpx.MockTransport(handler),
        resolver=resolver,
        host_interval=0,
    ), seen


async def test_fetch_pins_the_checked_address_and_identifies_itself():
    fetcher, seen = make(
        {
            ("example.com", "/robots.txt"): (404, {}, b""),
            ("example.com", "/page"): (200, {"content-type": "text/html"}, HTML),
        }
    )
    page = await fetcher.fetch("https://example.com/page")
    assert page.url == "https://example.com/page"
    request = seen[-1]
    assert request.url.host == "93.184.215.14"
    assert request.headers["host"] == "example.com"
    assert request.headers["user-agent"] == "TestBot/1.0"
    assert request.extensions["sni_hostname"] == "example.com"


async def test_private_addresses_are_refused_before_any_request():
    fetcher, seen = make({}, resolve={"internal.example": ["10.0.0.5"]})
    with pytest.raises(FetchError, match="private or internal"):
        await fetcher.fetch("http://internal.example/admin")
    assert seen == []


async def test_a_redirect_to_an_internal_address_is_refused():
    fetcher, seen = make(
        {
            ("example.com", "/robots.txt"): (404, {}, b""),
            ("example.com", "/go"): (302, {"location": "http://metadata.example/latest"}, b""),
        },
        resolve={"metadata.example": ["169.254.169.254"]},
    )
    with pytest.raises(FetchError):
        await fetcher.fetch("https://example.com/go")
    assert all(request.url.host != "169.254.169.254" for request in seen)


async def test_robots_txt_disallow_is_obeyed():
    robots = b"User-agent: *\nDisallow: /private\n"
    fetcher, seen = make({("example.com", "/robots.txt"): (200, {}, robots)})
    with pytest.raises(FetchError, match=r"robots\.txt"):
        await fetcher.fetch("https://example.com/private/page")
    assert [request.url.path for request in seen] == ["/robots.txt"]


async def test_robots_server_error_means_not_allowed():
    fetcher, _ = make({("example.com", "/robots.txt"): (503, {}, b"")})
    with pytest.raises(FetchError, match=r"robots\.txt"):
        await fetcher.fetch("https://example.com/page")


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("ftp://example.com/file", "http and https"),
        ("https://example.com:8443/page", "standard web ports"),
        # A fake credential URL that must be refused, not a real secret.
        ("https://user:pw@example.com/page", "credentials"),  # pragma: allowlist secret
    ],
)
async def test_unsafe_addresses_are_refused(url, message):
    fetcher, _ = make({})
    with pytest.raises(FetchError, match=message):
        await fetcher.fetch(url)


async def test_oversized_and_non_text_pages_are_refused():
    big = (200, {"content-type": "text/html"}, b"x" * 2_000)
    pdf = (200, {"content-type": "application/pdf"}, b"%PDF")
    routes = {
        ("example.com", "/robots.txt"): (404, {}, b""),
        ("example.com", "/big"): big,
        ("example.com", "/doc"): pdf,
    }
    fetcher, _ = make(routes)
    fetcher._max_bytes = 1_000
    with pytest.raises(FetchError, match="larger than"):
        await fetcher.fetch("https://example.com/big")
    with pytest.raises(FetchError, match="not application/pdf"):
        await fetcher.fetch("https://example.com/doc")
