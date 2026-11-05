"""Fake model, search and fetcher for offline end-to-end runs."""

from pydantic import BaseModel

from lantern import prompts
from lantern.egress import FetchError, Page
from lantern.search import Hit
from lantern.social import Post, origin

PAGES = {
    "https://www.reuters.com/floods": (
        "Floods in the district. Officials said the river rose by four metres on Monday. "
        "More than 12,000 families were moved to relief camps, the state disaster agency said."
    ),
    "https://apnews.com/floods": (
        "Heavy rain caused flooding. The river rose by four metres on Monday according to "
        "the water commission. Relief camps housed about 12,000 families by Tuesday."
    ),
    "https://ndma.gov.in/update": (
        "Situation report. The river rose by four metres on Monday at the main gauge. "
        "A total of 12,000 families were sheltered in relief camps across the district."
    ),
}


def html(text: str) -> bytes:
    filler = " ".join(["Background paragraph about the region and its rivers."] * 6)
    body = f"<article><p>{text}</p><p>{filler}</p></article>"
    return f"<html><head><title>Report</title></head><body>{body}</body></html>".encode()


HIT_TITLE = "Transient hit title 7f3a"
HIT_SNIPPET = "Transient hit snippet 9c1e"


class FakeSearch:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.domain_calls: list[list[str]] = []
        self.options: list[tuple[str, bool, str | None]] = []

    async def search(
        self,
        query: str,
        limit: int,
        domains: list[str] | None = None,
        *,
        news: bool = False,
        time_range: str | None = None,
    ) -> list[Hit]:
        if domains:
            self.domain_calls.append(domains)
            urls = ["https://x.com/witness/status/999", "https://x.com/witness"]
            return [Hit(url=url, title="hit", rank=i) for i, url in enumerate(urls, start=1)]
        self.queries.append(query)
        self.options.append((query, news, time_range))
        urls = [*PAGES, "https://www.facebook.com/post/1", "https://blocked.example/page"]
        return [
            Hit(url=url, title=HIT_TITLE, rank=i, snippet=HIT_SNIPPET)
            for i, url in enumerate(urls, start=1)
        ]


class FakeFetcher:
    async def fetch(self, url: str) -> Page:
        if url not in PAGES:
            raise FetchError("The site's robots.txt does not allow automated reading.")
        return Page(url=url, content_type="text/html", body=html(PAGES[url]))


class FakeModel:
    def __init__(
        self,
        allowed: bool = True,
        kinds: tuple[str, str] = ("fact", "fact"),
        followups: list[list[str]] | None = None,
    ) -> None:
        self.allowed = allowed
        self.kinds = kinds
        self.followups = list(followups or [])
        self.calls: list[str] = []
        self.prompts: dict[str, list[str]] = {}
        self.systems: dict[str, list[str]] = {}

    async def structured[T: BaseModel](self, system: str, user: str, output: type[T]) -> T:
        self.calls.append(output.__name__)
        self.prompts.setdefault(output.__name__, []).append(user)
        self.systems.setdefault(output.__name__, []).append(system)
        data: object
        if output is prompts.GateOut:
            data = {"allowed": self.allowed, "reason": "The subject is a private individual."}
        elif output is prompts.PlanOut:
            data = {
                "questions": [
                    {
                        "text": "How high did the river rise?",
                        "kind": self.kinds[0],
                        "queries": ["river rise floods", "river gauge news"],
                    },
                    {
                        "text": "How many families were moved?",
                        "kind": self.kinds[1],
                        "queries": ["relief camps families"],
                    },
                ],
                "news": True,
                "time_range": "Week",
                "hashtags": ["#DistrictFloods"],
            }
        elif output is prompts.TriageOut:
            refs = [line.split(" ")[0] for line in user.splitlines() if line.startswith("H")]
            data = {"read": list(reversed(refs))}
        elif output is prompts.FollowupOut:
            queries = self.followups.pop(0) if self.followups else []
            data = {
                "queries": [{"query": q, "question_ref": "Q2", "news": True} for q in queries],
                "done": not queries,
            }
        elif output is prompts.DiscoverOut:
            data = {
                "items": [
                    {"name": "Embankment collapse", "question_ref": "Q2", "results": ["H1"]},
                    {"name": "Invented from memory", "question_ref": "Q2", "results": []},
                ]
            }
        elif output is prompts.InventoryOut:
            groups: dict[str, list[str]] = {}
            for line in user.splitlines():
                if line.startswith("C") and "]: " in line:
                    ref = line.split(" ")[0]
                    statement = line.split("]: ", 1)[1].split(" Quote:")[0]
                    groups.setdefault(statement, []).append(ref)
            data = {
                "items": [
                    {"name": statement[:40], "summary": statement, "claims": refs}
                    for statement, refs in groups.items()
                ]
                + [{"name": "Ghost", "summary": "Cites nothing real.", "claims": ["C999"]}]
            }
        elif output is prompts.ExtractOut:
            data = {
                "claims": [
                    {
                        "statement": "The river rose four metres on Monday.",
                        "quote": "the river rose by four metres on Monday",
                        "question_refs": ["Q1"],
                    },
                    {
                        "statement": "About 12,000 families were moved.",
                        "quote": "12,000 families",
                        "question_refs": ["Q2", "Q9"],
                    },
                    {
                        "statement": "Invented claim.",
                        "quote": "the dam burst at midnight; nobody was warned",
                        "question_refs": ["Q1"],
                    },
                ]
            }
        elif output is prompts.ExtractPostsOut:
            refs = [part.split('"')[1] for part in user.split("<post ref=")[1:]]
            data = {
                "claims": [
                    {
                        "post_ref": ref,
                        "statement": "Water reached the market road.",
                        "quote": "water is up to the market road",
                        "question_refs": ["Q1"],
                    }
                    for ref in refs
                ]
                + [
                    {
                        "post_ref": "S99",
                        "statement": "A post that does not exist.",
                        "quote": "water is up to the market road",
                        "question_refs": ["Q1"],
                    }
                ]
            }
        elif output is prompts.AssessOut:
            refs = [line.split(" ")[0] for line in user.splitlines() if line.startswith("C")]
            data = {
                "status": "answered",
                "answer": "The river rose by about four metres.",
                "likelihood": "almost certain",
                "supporting": refs,
                "contradicting": [],
                "rationale": "Three outlets agree.",
            }
        elif output is prompts.ReportOut:
            data = {
                "bottom_line": [
                    {"text": "The river rose about four metres on Monday.", "cites": ["C1"]},
                    {"text": "An uncited sentence.", "cites": []},
                    {"text": "A sentence citing a ghost claim.", "cites": ["C99"]},
                ],
                "sections": [
                    {
                        "question_ref": "Q1",
                        "sentences": [
                            {
                                "text": "Three sources report a four-metre rise [C1, C3].",
                                "cites": [],
                            },
                        ],
                    }
                ],
                "gaps": ["Casualty figures were not checked."],
            }
        else:
            raise AssertionError(output)
        return output.model_validate(data)


class FakeSocial:
    """Three accounts; one posts three times; Mastodon offers one more."""

    def __init__(self) -> None:
        self.hashtags: list[str] = []

    async def search(self, query: str, limit: int) -> list[Post]:
        posts = []
        for number, account in enumerate(["alice", "bob", "bob", "bob", "carol"]):
            text = f"Report {number}: the water is up to the market road near the school."
            posts.append(
                Post(
                    platform="bluesky",
                    url=f"https://bsky.app/profile/did:plc:{account}/post/{number}",
                    origin=origin("bluesky", account),
                    posted_at="2026-11-01T08:00:00Z",
                    language="en",
                    text=text,
                )
            )
        return posts

    async def hashtag(self, tag: str, limit: int) -> list[Post]:
        self.hashtags.append(tag)
        return []
