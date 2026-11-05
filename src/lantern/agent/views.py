"""Case-file views: what the researcher and the triage step see, built by code from the
investigation. Each view has a character cap of about four characters per token (03 §4.2),
so a long investigation never floods a model step."""

from collections.abc import Iterable, Sequence

from lantern.assessment import registrable_domain
from lantern.models import Finding, Investigation, Mention, Question
from lantern.search import Hit

BRIEF_CAP = 1600
QUESTION_CAP = 800
DIGEST_CAP = 6000
HITS_CAP = 8000
SHOWN_CLAIMS = 12
SHOWN_SOURCES = 15


def capped(text: str, limit: int) -> str:
    """The text cut at a line break before `limit` characters, marked when shortened."""
    if len(text) <= limit:
        return text
    return text[: limit - 30].rsplit("\n", 1)[0] + "\n… (shortened to fit)"


def _quoted(texts: Iterable[str]) -> str:
    return "; ".join(f"“{text}”" for text in texts)


def brief_view(inv: Investigation, phrases: Sequence[str], hashtags: Sequence[str]) -> str:
    lines = [f"Research question: {inv.brief}"]
    if inv.time_range:
        lines.append(f"Period: news from the past {inv.time_range}.")
    lines.append("Key questions:")
    lines += [f"{q.ref} ({q.kind}, {q.status}): {q.text}" for q in inv.questions]
    if phrases or hashtags:
        tags = ", ".join(f"#{tag}" for tag in hashtags) or "none"
        shown = _quoted(phrases) or "none"
        lines.append(f"Planned ground-report phrases: {shown}; hashtags: {tags}.")
    return capped("\n".join(lines), BRIEF_CAP)


def question_view(  # noqa: PLR0913  # each input is one part of the question's state
    question: Question,
    attempts: int,
    tools: Iterable[str],
    finding: Finding | None,
    planned: Sequence[str],
    *,
    single: Sequence[str] = (),
) -> str:
    """The key question being researched: its status, attempts, current finding, and the
    items that still need a second, independent source."""
    used = ", ".join(sorted(tools)) or "none"
    lines = [
        f"Now researching {question.ref} ({question.kind}): {question.text}",
        f"Status: {question.status}. This is step {attempts + 1} on it. Tools used for it: {used}.",
    ]
    if finding is not None and finding.status == "answered":
        lines += [
            f"Current finding: {finding.answer}",
            f"Its likelihood: {finding.likelihood}.",
            f"Its analytic confidence: {finding.confidence} ({finding.confidence_reason}).",
        ]
    elif finding is not None:
        lines.append(f"Current finding: not answered yet. {finding.answer}")
    elif question.kind == "fact":
        lines.append("Current finding: not assessed yet.")
    if planned and attempts == 0:
        lines.append(f"Planned starting searches: {_quoted(planned)}.")
    if single:
        lines.append(
            f"Found in only one source so far (search one by name for a second source): "
            f"{'; '.join(single[:5])}."
        )
    return capped("\n".join(lines), QUESTION_CAP)


def evidence_digest(  # noqa: PLR0913  # each input is one part of the case file
    inv: Investigation,
    ref: str,
    *,
    searched: Sequence[str],
    unconfirmed: Sequence[Mention],
    unread: Sequence[str],
    feedback: Sequence[str],
) -> str:
    """What has been tried and found so far for one key question, and what went wrong."""
    sources = [source for source in inv.sources if ref in source.question_refs]
    claims = [claim for claim in inv.claims if ref in claim.question_refs]
    items = [item for item in inv.items if item.question_ref == ref]
    parts = [
        ("Searches already made (never repeat one)", list(searched[-30:])),
        (
            f"Sources saved for {ref} ({len(sources)}; ref, site, grade, date, title)",
            [
                f"{s.ref} {s.domain} grade {s.reliability} {s.published or 'undated'}: "
                f"{(s.title or s.kind)[:100]}"
                for s in sources[-SHOWN_SOURCES:]
            ],
        ),
        (
            f"Items found for {ref}",
            [
                f"{item.name} ({item.when or 'date unknown'}): {item.status}, "
                f"{len(item.origins)} source{'' if len(item.origins) == 1 else 's'}"
                for item in items
            ],
        ),
        (
            "Seen only in search results, not confirmed (search each by name)",
            [
                f"{m.name} ({m.when or 'date unknown'}): {', '.join(m.urls[:2])}"
                for m in unconfirmed
                if m.question_ref == ref
            ],
        ),
        (
            f"Latest claims for {ref} ({len(claims)} in all; quotes are untrusted text)",
            [
                f"{c.ref} [{c.source_ref}]: {c.statement[:200]} Quote: “{c.quote[:200]}”"
                for c in claims[-SHOWN_CLAIMS:]
            ],
        ),
        ("Pages that could not be read (look for these stories elsewhere)", list(unread[-10:])),
        ("Refused or failed in your last step (change approach)", list(feedback)),
    ]
    lines = []
    for heading, rows in parts:
        lines.append(f"{heading}:")
        lines += [f"- {row}" for row in rows] or ["- none"]
    return capped("\n".join(lines), DIGEST_CAP)


def hits_view(hits: Sequence[Hit]) -> str:
    """Search results for triage, numbered H1, H2…: transient, never stored."""
    lines = []
    for number, hit in enumerate(hits, start=1):
        when = f", {hit.published}" if hit.published else ""
        lines.append(
            f"H{number} [{registrable_domain(hit.url)}{when}] {hit.title[:150]} — "
            f"{hit.snippet[:200]}"
        )
    return capped("\n".join(lines), HITS_CAP)
