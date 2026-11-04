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


class FakeSearch:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query: str, limit: int) -> list[Hit]:
        self.queries.append(query)
        urls = [*PAGES, "https://www.facebook.com/post/1", "https://blocked.example/page"]
        return [Hit(url=url, title="hit", rank=i) for i, url in enumerate(urls, start=1)]


class FakeFetcher:
    async def fetch(self, url: str) -> Page:
        if url not in PAGES:
            raise FetchError("The site's robots.txt does not allow automated reading.")
        return Page(url=url, content_type="text/html", body=html(PAGES[url]))


class FakeModel:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.calls: list[str] = []

    async def structured[T: BaseModel](self, system: str, user: str, output: type[T]) -> T:
        self.calls.append(output.__name__)
        data: object
        if output is prompts.GateOut:
            data = {"allowed": self.allowed, "reason": "The subject is a private individual."}
        elif output is prompts.PlanOut:
            data = {
                "questions": [
                    {"text": "How high did the river rise?", "queries": ["river rise floods"]},
                    {"text": "How many families were moved?", "queries": ["relief camps families"]},
                ],
                "hashtags": ["#DistrictFloods"],
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
