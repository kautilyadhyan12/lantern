"""Rule-based ratings: source reliability, independence, confidence and likelihood limits.

The model may propose a likelihood; these rules decide what the evidence allows.
"""

from collections.abc import Iterable
from typing import Literal
from urllib.parse import urlsplit

LIKELIHOOD: tuple[tuple[str, str], ...] = (
    ("almost no chance", "01-05%"),
    ("very unlikely", "05-20%"),
    ("unlikely", "20-45%"),
    ("roughly even chance", "45-55%"),
    ("likely", "55-80%"),
    ("very likely", "80-95%"),
    ("almost certain", "95-99%"),
)
TERMS = tuple(term for term, _ in LIKELIHOOD)
CONFIDENCE_WORDS = ("confidence", "confident")

RELIABILITY = {
    "A": "Completely reliable",
    "B": "Usually reliable",
    "C": "Fairly reliable",
    "D": "Not usually reliable",
    "E": "Unreliable",
    "F": "Reliability cannot be judged",
}
CREDIBILITY = {
    1: "Confirmed by other sources",
    2: "Probably true",
    3: "Possibly true",
    4: "Doubtful",
    5: "Improbable",
    6: "Truth cannot be judged",
}

_SECOND_LEVEL = {"co", "com", "org", "net", "gov", "ac", "edu", "nic", "gob", "go", "or", "ne"}
_OFFICIAL_SUFFIXES = (".gov", ".mil", ".int", ".gouv.fr", ".gc.ca", ".nic.in", ".europa.eu")
_ESTABLISHED = {
    "reuters.com",
    "apnews.com",
    "afp.com",
    "bbc.co.uk",
    "bbc.com",
    "theguardian.com",
    "nytimes.com",
    "washingtonpost.com",
    "ft.com",
    "economist.com",
    "bloomberg.com",
    "wsj.com",
    "npr.org",
    "aljazeera.com",
    "dw.com",
    "france24.com",
    "thehindu.com",
    "indianexpress.com",
    "hindustantimes.com",
    "nature.com",
    "science.org",
    "un.org",
    "who.int",
    "worldbank.org",
    "imf.org",
    "oecd.org",
    "reliefweb.int",
}
_BACKGROUND = {"wikipedia.org", "britannica.com"}
_USER_CONTENT = {
    "reddit.com",
    "medium.com",
    "substack.com",
    "blogspot.com",
    "wordpress.com",
    "quora.com",
    "x.com",
    "twitter.com",
    "facebook.com",
    "youtube.com",
    "tiktok.com",
    "instagram.com",
}


def registrable_domain(url_or_host: str) -> str:
    """Approximate registrable domain: `news.bbc.co.uk` → `bbc.co.uk`. No network."""
    host = urlsplit(url_or_host).hostname if "//" in url_or_host else url_or_host
    labels = (host or "").lower().rstrip(".").split(".")
    labels = [label for label in labels if label]
    if len(labels) <= 2:
        return ".".join(labels)
    if labels[-2] in _SECOND_LEVEL and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def rate_source(url: str) -> tuple[str, str]:
    """Return an Admiralty reliability grade and the rule that produced it."""
    host = (urlsplit(url).hostname or "").lower()
    domain = registrable_domain(host)
    labels = host.split(".")
    if host.endswith(_OFFICIAL_SUFFIXES) or "gov" in labels[-3:-1] or "mil" in labels[-3:-1]:
        return "B", "Official government or intergovernmental website"
    if domain in _ESTABLISHED:
        return "B", "Established news organisation or international body"
    if host.endswith(".edu") or "ac" in labels[-3:-1] or "edu" in labels[-3:-1]:
        return "B", "Academic institution"
    if domain in _BACKGROUND:
        return "C", "Reference work; used as background"
    if domain in _USER_CONTENT:
        return "D", "User-generated content platform"
    return "F", "No track record known to Lantern"


def independent_domains(urls: Iterable[str]) -> list[str]:
    """Distinct registrable domains: copies on one site count once."""
    return sorted({registrable_domain(url) for url in urls})


Level = Literal["low", "moderate", "high"]


def confidence(domains: int, best_grade: str | None, contradicted: bool) -> tuple[Level, str]:
    """Analytic confidence from independent corroboration, source quality and conflicts."""
    good = best_grade in {"A", "B"}
    level: Level
    if domains >= 3 and good and not contradicted:
        level = "high"
    elif domains >= 2 and (good or best_grade == "C"):
        level = "moderate"
    else:
        level = "low"
    parts = [f"{domains} independent source{'s' if domains != 1 else ''}"]
    if best_grade:
        parts.append(f"best source grade {best_grade}")
    if contradicted:
        parts.append("some sources disagree")
    return level, ", ".join(parts)


def clamp_likelihood(proposed: str, domains: int) -> str:
    """Thin evidence cannot support extreme likelihoods: 1 site → unlikely…likely."""
    index = TERMS.index(proposed) if proposed in TERMS else 3
    spread = {0: 0, 1: 1, 2: 2}.get(domains, 3)
    return TERMS[min(max(index, 3 - spread), 3 + spread)]


def item_status(origins: int) -> Literal["corroborated", "single source"]:
    """An item counts as corroborated once two independent origins report it."""
    return "corroborated" if origins >= 2 else "single source"


def best_grade(grades: Iterable[str]) -> str:
    """The best Admiralty grade (A is best); F when nothing is known."""
    return min(grades, default="F")


def credibility(domains: int, contradicted: bool, supporting: bool) -> int:
    """Admiralty credibility of a claim from how its finding is corroborated."""
    if not supporting:
        return 4 if contradicted else 6
    if domains >= 3:
        return 1 if not contradicted else 2
    if domains == 2:
        return 2 if not contradicted else 3
    return 3
