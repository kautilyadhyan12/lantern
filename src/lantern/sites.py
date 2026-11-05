"""Which sites Lantern may open, and which links it may only list for a person to check."""

import re
from urllib.parse import urlsplit, urlunsplit

from lantern.assessment import registrable_domain

# Sites whose terms forbid automated reading, or which need an account.
SKIP_DOMAINS = {
    "x.com",
    "twitter.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "tiktok.com",
    "reddit.com",
    "threads.net",
    "t.me",
    "telegram.org",
    "pinterest.com",
    "t.co",
    "fxtwitter.com",
    "vxtwitter.com",
    "fixupx.com",
    "nitter.net",
    "xcancel.com",
    "fb.com",
    "fb.watch",
    "instagr.am",
}
# Video and audio pages have no readable text to quote.
NO_TEXT_DOMAINS = {"youtube.com", "youtu.be", "vimeo.com", "spotify.com", "soundcloud.com"}

# Individual posts only (never profile pages), on sites Lantern must not read itself.
POST_LINKS = {
    "x.com": ("X", r"^/[^/]+/status/\d+"),
    "twitter.com": ("X", r"^/[^/]+/status/\d+"),
    "facebook.com": ("Facebook", r"^/(?:[^/]+/(?:posts|videos)/|permalink\.php|story\.php|watch)"),
    "instagram.com": ("Instagram", r"^/(?:p|reel)/[^/]+"),
    "threads.net": ("Threads", r"^/@[^/]+/post/[^/]+"),
    "reddit.com": ("Reddit", r"^/r/[^/]+/comments/[^/]+"),
    "tiktok.com": ("TikTok", r"^/@[^/]+/video/\d+"),
    "linkedin.com": ("LinkedIn", r"^/(?:posts|feed/update)/[^/]+"),
    "t.me": ("Telegram", r"^/[^/]+/\d+$"),
}


def post_lead(url: str) -> str | None:
    """The platform name when `url` is one post on a never-open site, else None."""
    entry = POST_LINKS.get(registrable_domain(url))
    if entry and re.match(entry[1], urlsplit(url).path):
        return entry[0]
    return None


def blocked_site(url: str) -> str | None:
    """Why a URL must never be opened, also checked on every redirect hop."""
    domain = registrable_domain(url)
    if domain in SKIP_DOMAINS:
        return f"{domain} does not allow automated reading, so Lantern never opens it."
    return None


def readable(url: str) -> bool:
    """Whether Lantern may try to read this page itself."""
    return registrable_domain(url) not in SKIP_DOMAINS | NO_TEXT_DOMAINS


def canonical(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme, (parts.hostname or "").lower(), path, parts.query, ""))
