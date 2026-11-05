"""The only way Lantern opens web pages.

Every hop is checked: http(s) on standard ports, every resolved address public, the
connection pinned to the checked address (no DNS rebinding), robots.txt obeyed, the
bot identified, per-host pacing, timeouts and a size cap.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

Resolver = Callable[[str, int], Awaitable[list[str]]]
ALLOWED_PORTS = {80, 443}
MAX_REDIRECTS = 5
TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
ROBOTS_TTL = 24 * 3600.0
HOST_INTERVAL = 1.0


class FetchError(Exception):
    """A page could not be fetched; the message says why in plain words."""


@dataclass(frozen=True)
class Page:
    url: str
    content_type: str
    body: bytes


def is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.teredo:
            return False
        ip = ip.ipv4_mapped or ip.sixtofour or ip
    return ip.is_global and not ip.is_multicast


async def system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


class Fetcher:
    def __init__(  # noqa: PLR0913  # transport, resolver and limits are injectable for tests
        self,
        user_agent: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver = system_resolver,
        max_bytes: int = 5_000_000,
        total_timeout: float = 25.0,
        host_interval: float = HOST_INTERVAL,
        blocked: Callable[[str], str | None] | None = None,
    ) -> None:
        self._agent = user_agent
        self._token = user_agent.split("/", maxsplit=1)[0]
        self._resolver = resolver
        self._max_bytes = max_bytes
        self._total_timeout = total_timeout
        self._interval = host_interval
        self._blocked = blocked
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(15.0, connect=10.0),
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(max_keepalive_connections=0),
        )
        self._robots: dict[str, tuple[float, RobotFileParser]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, float] = {}

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch(self, url: str) -> Page:
        """Fetch a page that robots.txt allows; only text and HTML are accepted."""
        status, headers, body, final = await self._follow(url, robots=True)
        if status != 200:
            raise FetchError(f"The page returned HTTP {status}.")
        content_type = headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type not in TEXT_TYPES:
            shown = content_type or "unknown"
            raise FetchError(f"Lantern reads web pages and plain text only, not {shown}.")
        return Page(url=final, content_type=content_type, body=body)

    async def _follow(self, url: str, *, robots: bool) -> tuple[int, httpx.Headers, bytes, str]:
        for _ in range(MAX_REDIRECTS + 1):
            reason = self._blocked(url) if self._blocked else None
            if reason:
                raise FetchError(reason)
            await self._target(url)
            if robots and not await self._allowed(url):
                raise FetchError("The site's robots.txt does not allow automated reading.")
            status, headers, body = await self._once(url)
            location = headers.get("location")
            if status in {301, 302, 303, 307, 308} and location:
                url = urljoin(url, location)
                continue
            return status, headers, body, url
        raise FetchError(f"The page redirected more than {MAX_REDIRECTS} times.")

    async def _target(self, url: str) -> tuple[str, str, int, str]:
        """Validate a URL and return (pinned url, host, port, checked address)."""
        parts = urlsplit(url)
        host = parts.hostname
        if parts.scheme not in {"http", "https"} or not host:
            raise FetchError("Only http and https web addresses can be fetched.")
        if parts.username or parts.password:
            raise FetchError("Web addresses with embedded credentials are refused.")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if port not in ALLOWED_PORTS:
            raise FetchError("Only the standard web ports (80 and 443) are allowed.")
        try:
            addresses = await self._resolver(host, port)
        except OSError as error:
            raise FetchError(f"The site {host} could not be found.") from error
        if not addresses or not all(is_public(address) for address in addresses):
            raise FetchError(f"{host} points to a private or internal address; refused.")
        address = addresses[0]
        netloc = f"[{address}]:{port}" if ":" in address else f"{address}:{port}"
        pinned = urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))
        return pinned, host, port, address

    async def _once(self, url: str) -> tuple[int, httpx.Headers, bytes]:
        pinned, host, port, _ = await self._target(url)
        parts = urlsplit(url)
        headers = {
            "Host": host if parts.port is None else f"{host}:{port}",
            "User-Agent": self._agent,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
        }
        extensions = {"sni_hostname": host} if parts.scheme == "https" else {}
        await self._pace(host)
        try:
            async with asyncio.timeout(self._total_timeout):
                return await self._read(pinned, headers, extensions)
        except TimeoutError as error:
            raise FetchError("The site took too long to answer.") from error
        except httpx.HTTPError as error:
            raise FetchError(f"Could not connect to {host}: {type(error).__name__}.") from error

    async def _read(
        self, url: str, headers: dict[str, str], extensions: dict[str, str]
    ) -> tuple[int, httpx.Headers, bytes]:
        request = self._client.build_request("GET", url, headers=headers, extensions=extensions)
        response = await self._client.send(request, stream=True)
        try:
            body = bytearray()
            async for piece in response.aiter_bytes():
                body.extend(piece)
                if len(body) > self._max_bytes:
                    limit = self._max_bytes // 1_000_000
                    raise FetchError(f"The page is larger than {limit} MB; skipped.")
            return response.status_code, response.headers, bytes(body)
        finally:
            await response.aclose()

    async def _pace(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            loop = asyncio.get_running_loop()
            wait = self._last.get(host, -self._interval) + self._interval - loop.time()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last[host] = loop.time()

    async def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        key = f"{parts.scheme}://{parts.netloc}"
        now = asyncio.get_running_loop().time()
        cached = self._robots.get(key)
        if cached is None or now - cached[0] > ROBOTS_TTL:
            parser = RobotFileParser()
            try:
                status, _, body, _ = await self._follow(f"{key}/robots.txt", robots=False)
            except FetchError as error:
                msg = f"Could not check the site's robots.txt ({error}); skipped."
                raise FetchError(msg) from error
            if status >= 500:
                return False
            parser.parse(body.decode("utf-8", "replace").splitlines() if status == 200 else [])
            cached = (now, parser)
            self._robots[key] = cached
        return cached[1].can_fetch(self._token, url)
