"""Domain records of an investigation, stored as one JSON document."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field


def now() -> datetime:
    return datetime.now(UTC)


Status = Literal["queued", "running", "done", "failed", "refused"]


class Step(BaseModel):
    at: AwareDatetime = Field(default_factory=now)
    message: str


class Question(BaseModel):
    ref: str
    text: str
    kind: Literal["fact", "list"] = "fact"
    status: Literal["open", "answered", "unanswerable"] = "open"


class Source(BaseModel):
    ref: str
    url: str
    domain: str
    kind: Literal["page", "post", "record"] = "page"  # record: an official list or reference entry
    origin: str = ""
    title: str | None = None
    published: str | None = None
    fetched_at: AwareDatetime
    sha256: str
    text_sha256: str
    size: int
    reliability: str
    reliability_reason: str
    question_refs: list[str] = Field(default_factory=list)
    archive_url: str | None = None  # set when read from a Wayback Machine copy
    archived_at: AwareDatetime | None = None


class Lead(BaseModel):
    """A link Lantern did not read: listed for a person to check, never evidence.

    `post` is a post on a site whose terms forbid automated reading; `page` is a page
    Lantern tried to read but could not (blocked, error, no readable text).
    """

    platform: str
    url: str
    question_refs: list[str] = Field(default_factory=list)
    kind: Literal["post", "page"] = "post"
    reason: str = ""


class Mention(BaseModel):
    """A possible item named in search results that no page Lantern read has confirmed.

    Only the name, the period as reported and the result links are kept, never the
    results' titles or snippets. Mentions are leads, not evidence."""

    question_ref: str
    name: str
    when: str = ""
    urls: list[str] = Field(default_factory=list)


class Item(BaseModel):
    """One thing found for a list question (a person, incident or event), with its evidence."""

    question_ref: str
    name: str
    summary: str
    when: str = ""
    claim_refs: list[str]
    origins: list[str]
    best_grade: str
    status: Literal["corroborated", "single source"]
    in_period: bool = True


class Claim(BaseModel):
    ref: str
    source_ref: str
    question_refs: list[str]
    statement: str
    quote: str
    start: int
    end: int
    credibility: int = 6


class Finding(BaseModel):
    question_ref: str
    status: Literal["answered", "unanswerable"]
    answer: str
    likelihood_proposed: str | None = None
    likelihood: str | None = None
    confidence: Literal["low", "moderate", "high"] | None = None
    confidence_reason: str = ""
    supporting: list[str] = Field(default_factory=list)
    contradicting: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    rationale: str = ""


class Sentence(BaseModel):
    text: str
    cites: list[str] = Field(default_factory=list)


class Section(BaseModel):
    question_ref: str
    sentences: list[Sentence] = Field(default_factory=list)


class Removed(BaseModel):
    text: str
    reason: str


class Report(BaseModel):
    bottom_line: list[Sentence] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    removed: list[Removed] = Field(default_factory=list)


class Usage(BaseModel):
    searches: int = 0
    pages_fetched: int = 0
    pages_skipped: int = 0
    posts_saved: int = 0
    archived: int = 0
    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    claims_dropped: int = 0
    rounds: int = 0
    research_steps: int = 0  # researcher steps taken by the agent
    tools: dict[str, int] = Field(default_factory=dict)  # tool name → calls that ran
    providers: list[str] = Field(default_factory=list)


class Investigation(BaseModel):
    id: str
    brief: str
    created_at: AwareDatetime = Field(default_factory=now)
    finished_at: AwareDatetime | None = None
    status: Status = "queued"
    depth: Literal["quick", "deep"] = "deep"
    news: bool = False
    time_range: str | None = None
    searched: list[str] = Field(default_factory=list)  # queries made, never their results
    continued_at: list[AwareDatetime] = Field(default_factory=list)
    safety: str = "Not checked yet."
    error: str | None = None
    stopped_by: str = ""  # what ended the last pass of research, in plain words
    steps: list[Step] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    leads: list[Lead] = Field(default_factory=list)
    items: list[Item] = Field(default_factory=list)
    mentions: list[Mention] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    report: Report | None = None
    usage: Usage = Field(default_factory=Usage)

    def log(self, message: str) -> None:
        self.steps.append(Step(message=message))

    def claim(self, ref: str) -> Claim | None:
        return next((item for item in self.claims if item.ref == ref), None)

    def source(self, ref: str) -> Source | None:
        return next((item for item in self.sources if item.ref == ref), None)

    def question(self, ref: str) -> Question | None:
        return next((item for item in self.questions if item.ref == ref), None)
