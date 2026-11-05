"""Citation checks for the drafted report, and Markdown export."""

import re

from lantern.assessment import CONFIDENCE_WORDS, LIKELIHOOD, RELIABILITY, TERMS
from lantern.models import Finding, Investigation, Removed, Report, Section, Sentence
from lantern.prompts import ReportOut, SentenceOut

_INLINE = re.compile(r"\s*[\[(]\s*((?:C\d+\s*[,;]?\s*)+)[\])]")
_REF = re.compile(r"C\d+")


def strip_refs(text: str) -> str:
    """Remove inline claim refs such as "(C1, C2)" from model prose."""
    return _INLINE.sub("", text).strip()


def _mixes_scales(text: str) -> bool:
    lowered = text.lower()
    has_term = any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in TERMS)
    return has_term and any(word in lowered for word in CONFIDENCE_WORDS)


def _check(sentence: SentenceOut, valid: set[str], removed: list[Removed]) -> Sentence | None:
    cites = list(sentence.cites)
    for match in _INLINE.finditer(sentence.text):
        cites += _REF.findall(match.group(1))
    text = _INLINE.sub("", sentence.text).strip()
    cites = list(dict.fromkeys(ref.strip().upper() for ref in cites))
    unknown = [ref for ref in cites if ref not in valid]
    if not cites:
        removed.append(Removed(text=text, reason="It cites no claim."))
    elif unknown:
        removed.append(Removed(text=text, reason=f"It cites unknown claims: {', '.join(unknown)}."))
    elif _mixes_scales(text):
        removed.append(Removed(text=text, reason="It mixes likelihood and confidence."))
    else:
        return Sentence(text=text, cites=cites)
    return None


def verify(draft: ReportOut, investigation: Investigation) -> Report:
    """Keep only sentences that cite existing claims; list everything removed."""
    valid = {claim.ref for claim in investigation.claims}
    answered = {item.question_ref for item in investigation.findings if item.status == "answered"}
    removed: list[Removed] = []
    bottom = [item for s in draft.bottom_line if (item := _check(s, valid, removed))]
    sections: dict[str, Section] = {}
    for section in draft.sections:
        if section.question_ref not in answered:
            continue
        target = sections.setdefault(
            section.question_ref, Section(question_ref=section.question_ref)
        )
        target.sentences += [item for s in section.sentences if (item := _check(s, valid, removed))]
    gaps = [gap.strip() for gap in draft.gaps if gap.strip()]
    for finding in investigation.findings:
        question = investigation.question(finding.question_ref)
        if finding.status == "unanswerable" and question:
            gaps.append(f"{question.ref} — {question.text} {finding.answer}")
    ordered = [sections[q.ref] for q in investigation.questions if q.ref in sections]
    return Report(bottom_line=bottom, sections=ordered, gaps=gaps, removed=removed)


def _cited(sentence: Sentence) -> str:
    return f"{sentence.text} [{', '.join(sentence.cites)}]"


def to_markdown(investigation: Investigation) -> str:
    """The report as Markdown, with the claims and sources it relies on."""
    report = investigation.report or Report()
    lines = [f"# {investigation.brief}", "", f"Status: {investigation.status}.", ""]
    if investigation.status == "refused":
        return "\n".join([*lines, f"Refused: {investigation.safety}", ""])
    lines += ["## Bottom line", "", *(_cited(s) for s in report.bottom_line), ""]
    for finding in investigation.findings:
        lines += _finding_lines(investigation, report, finding)
    if report.gaps:
        lines += ["## What could not be determined", "", *(f"- {gap}" for gap in report.gaps), ""]
    lines += _link_lines(investigation)
    lines += _method_lines(investigation)
    lines += ["## Claims", ""]
    for claim in investigation.claims:
        lines.append(
            f"- **{claim.ref}** ({claim.source_ref}, credibility {claim.credibility}): "
            f"{claim.statement} — “{claim.quote}”"
        )
    lines += ["", "## Sources", ""]
    for source in investigation.sources:
        grade = RELIABILITY.get(source.reliability, "")
        if source.kind == "post":
            # Post addresses can contain usernames; the app links to the original instead.
            lines.append(
                f"- **{source.ref}** {source.title} (ground report, posted "
                f"{source.published or 'unknown'}) — grade {source.reliability} ({grade}); "
                f"sha256 `{source.sha256}`"
            )
            continue
        lines.append(
            f"- **{source.ref}** [{source.title or source.domain}]({source.url}) — "
            f"grade {source.reliability} ({grade}); "
            f"saved {source.fetched_at:%Y-%m-%d %H:%M} UTC; sha256 `{source.sha256}`"
            + (
                f"; read from the [Wayback Machine copy]({source.archive_url}) of "
                f"{source.archived_at:%Y-%m-%d}"
                if source.archive_url and source.archived_at
                else ""
            )
        )
    posts = [lead for lead in investigation.leads if lead.kind == "post"]
    pages = [lead for lead in investigation.leads if lead.kind == "page"]
    if posts or pages:
        lines += ["", "## Leads to check yourself", ""]
    if posts:
        platforms = ", ".join(sorted({lead.platform for lead in posts}))
        lines.append(
            f"{len(posts)} posts on {platforms} appeared in search results. Lantern does not "
            "open these sites and they are not evidence here; open them from the web app."
        )
    if pages:
        lines += ["", "Pages Lantern could not read (not evidence):", ""]
        lines += [f"- <{lead.url}> — {lead.reason}" for lead in pages]
    lines += [
        "",
        (
            "Produced with automated assistance from public sources. Review it before "
            "publishing or acting on it."
        ),
        "",
    ]
    return "\n".join(lines)


def _finding_lines(investigation: Investigation, report: Report, finding: Finding) -> list[str]:
    """One key question's section: sentences, assessment, items and unconfirmed mentions."""
    ranges = dict(LIKELIHOOD)
    lines: list[str] = []
    question = investigation.question(finding.question_ref)
    lines += [f"## {finding.question_ref}. {question.text if question else ''}", ""]
    if finding.status == "answered":
        section = next((s for s in report.sections if s.question_ref == finding.question_ref), None)
        lines += [_cited(s) for s in section.sentences] if section else []
        likelihood = finding.likelihood or ""
        lines += [
            "",
            f"- Answer: {finding.answer}",
            f"- Likelihood: {likelihood} ({ranges.get(likelihood, '')})",
            f"- Analytic confidence: {finding.confidence} — {finding.confidence_reason}.",
        ]
    else:
        lines.append(f"Could not be determined. {finding.answer}")
    items = [i for i in investigation.items if i.question_ref == finding.question_ref]
    for heading, rows in (
        ("Everything found", [item for item in items if item.in_period]),
        ("Also found, dated before the period asked about", [i for i in items if not i.in_period]),
    ):
        if rows:
            lines += ["", f"### {heading} ({len(rows)})", ""]
            lines += [
                f"- **{item.name}** ({item.when or 'date unknown'}) — {item.summary} "
                f"*({item.status}; {len(item.origins)} "
                f"source{'' if len(item.origins) == 1 else 's'}; best grade {item.best_grade}; "
                f"{', '.join(item.claim_refs)})*"
                for item in rows
            ]
    mentions = [m for m in investigation.mentions if m.question_ref == finding.question_ref]
    if mentions:
        lines += ["", f"### Also seen in search results, not confirmed ({len(mentions)})", ""]
        lines += [
            f"- {mention.name} ({mention.when or 'date unknown'}): "
            + ", ".join(f"<{url}>" for url in mention.urls)
            for mention in mentions
        ]
    lines.append("")
    return lines


def _method_lines(investigation: Investigation) -> list[str]:
    """How the research was done: the agent's steps, the tools it used, what ended it."""
    usage = investigation.usage
    if not usage.research_steps:
        return []
    tools = ", ".join(f"{name} ({count})" for name, count in sorted(usage.tools.items()))
    lines = [
        "## Method",
        "",
        (
            f"- A researcher agent took {_count(usage.research_steps, 'step')} over "
            f"{_count(usage.rounds, 'round')}, choosing its own tool calls; code checked every "
            "call before it ran."
        ),
        f"- Tools used: {tools or 'none'}.",
    ]
    if investigation.stopped_by:
        lines.append(f"- What ended research: {investigation.stopped_by}")
    return [*lines, ""]


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


def _link_lines(investigation: Investigation) -> list[str]:
    """The links between entities, each with its status and evidence."""
    if not investigation.links:
        return []
    name = {entity.ref: entity.name for entity in investigation.entities}
    lines = ["## Links", ""]
    for link in investigation.links:
        relation = link.relation.replace("_", " ")
        if link.status == "assessment":
            against = f"; against {', '.join(link.against)}" if link.against else ""
            evidence = f"Lantern's assessment, not a stated fact: for {', '.join(link.claim_refs)}"
            evidence += against
        else:
            count = _count(len(link.origins), "independent source")
            evidence = f"{link.status}; {count}; {', '.join(link.claim_refs)}"
        lines.append(
            f"- **{link.ref}** {name.get(link.subject, link.subject)} — {relation} → "
            f"{name.get(link.object, link.object)} *({evidence})*"
        )
    return [*lines, ""]
