"""Which verdict the evidence of a claim check allows. The model proposes a label and a
likelihood; these rules decide whether the claims it cites carry them. A label the evidence
does not carry becomes "unproven", with the reason in plain words. Pure, so the rules can be
tested exhaustively."""

from collections.abc import Sequence
from dataclasses import dataclass

from lantern.assessment import Level, best_grade, clamp_likelihood, confidence
from lantern.models import VerdictLabel

USABLE = {"A", "B", "C"}  # grades that count towards corroboration
GOOD = {"A", "B"}
NEEDS: dict[VerdictLabel, str] = {
    "supported": (
        "Supported needs at least two independent sources rated C or better, with no "
        "equally good source against it."
    ),
    "false": (
        "False needs a published fact-check, or at least two independent sources rated B or "
        "better, against the claim."
    ),
    "misleading": (
        "Misleading needs the material's original time, place or event to be established, "
        "from an archive record, a fact-check or two independent sources."
    ),
    "unproven": "The evidence found does not settle the claim.",
}


@dataclass(frozen=True)
class Cited:
    """One claim a proposed verdict rests on, or goes against it."""

    ref: str
    origin: str
    grade: str  # the Admiralty grade of its source
    fact_check: bool = False  # from an established fact-checker's page
    archive: bool = False  # an archive capture record


@dataclass(frozen=True)
class Ruling:
    label: VerdictLabel
    reason: str
    likelihood: str | None = None
    confidence: Level | None = None
    confidence_reason: str = ""


def independent(cited: Sequence[Cited], grades: set[str] = USABLE) -> list[str]:
    """Distinct origins among the claims whose source has one of `grades`."""
    return sorted({item.origin for item in cited if item.grade in grades})


def contested(cited: Sequence[Cited], against: Sequence[Cited]) -> bool:
    """A source against the verdict rated at least as high as its best source."""
    if not against:
        return False
    return best_grade(i.grade for i in against) <= best_grade(i.grade for i in cited)


def carries(
    label: VerdictLabel, cited: Sequence[Cited], against: Sequence[Cited], *, context: bool
) -> bool:
    """Whether the cited claims carry `label`. `context` is whether the question about the
    material's original time, place or event was answered."""
    origins = independent(cited)
    if label == "supported":
        return len(origins) >= 2 and not contested(cited, against)
    if label == "false":
        fact_checked = any(item.fact_check for item in cited)
        return fact_checked or len(independent(cited, GOOD)) >= 2
    if label == "misleading":
        dated = any(item.archive or item.fact_check for item in cited)
        return context and (dated or len(origins) >= 2)
    return True


def decide(
    proposed: VerdictLabel,
    likelihood: str,
    cited: Sequence[Cited],
    against: Sequence[Cited] = (),
    *,
    context: bool,
) -> Ruling:
    """The verdict the evidence allows, with its likelihood clamped by corroboration and a
    confidence computed by the standard rules. "Unproven" has neither."""
    if (
        proposed == "unproven"
        or not cited
        or not carries(proposed, cited, against, context=context)
    ):
        reason = NEEDS["unproven"] if proposed == "unproven" else NEEDS[proposed]
        if proposed != "unproven":
            reason = f"Proposed “{proposed}”, but the evidence does not carry it. {reason}"
        return Ruling("unproven", reason)
    origins = independent(cited)
    level, why = confidence(
        len(origins), best_grade(i.grade for i in cited), contested(cited, against)
    )
    kept = clamp_likelihood(likelihood, len(origins))
    reason = f"The cited evidence carries “{proposed}”: {why}."
    return Ruling(proposed, reason, kept, level, why)
