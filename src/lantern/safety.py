"""Fixed rules that refuse harmful briefs before any model call."""

import re

_RULES: tuple[tuple[str, str], ...] = (
    (
        (
            r"\b(home|house|residential|current|personal)\s+address(es)?\b"
            r"|\bwhere\s+(does|do|did)\s+[\w .'-]{1,40}\s+live\b|\bwhereabouts\b"
            r"|\blive\s+location\b|\bdaily\s+routine\b"
        ),
        "Lantern does not locate people or track where they live or go.",
    ),
    (
        (
            r"\b(track|trace|locate|follow|monitor|stalk|spy\s+on|watch)\s+(my\s+)?"
            r"(ex|wife|husband|girlfriend|boyfriend|partner|spouse|neighbou?r|colleague|"
            r"co-?worker|boss|employee|mother|father|sister|brother|son|daughter|"
            r"person|someone|him|her|them)\b"
        ),
        "Lantern does not monitor or track individuals.",
    ),
    (
        (
            r"\b(phone|mobile|cell)\s+(number|no\.?)\b|\bpersonal\s+e-?mail\b"
            r"|\b(family|relatives|children)\s+of\s+(my|this|that)\b"
        ),
        "Lantern does not look up personal contact details or family members.",
    ),
    (
        r"\bdox+(ing|ed)?\b|\bharass\w*\b|\bintimidat\w*\b|\bhumiliat\w*\b|\brevenge\b",
        "Lantern does not help harass, shame or expose anyone.",
    ),
    (
        (
            r"\bpasswords?\b|\bprivate\s+(messages|chats|photos)\b|\bmedical\s+records?\b"
            r"|\bbank\s+(account|details|statements?)\b|\bsocial\s+security\s+number\b"
            r"|\b(aadhaar|passport)\s+(number|card|details)\b|\bleaked\s+data(base)?\b"
        ),
        "Lantern does not obtain private data or use leaked data.",
    ),
    (
        (
            r"\b(face|facial)\s+(recognition|match\w*|search)\b|\bidentify\s+(this|the)\s+"
            r"(person|man|woman|girl|boy|face)\b|\bwho\s+is\s+(in|this\s+person\s+in)\s+"
            r"(this|the)\s+(photo|picture|image|video)\b"
        ),
        "Lantern does not identify people from their faces.",
    ),
    (
        (
            r"\bunmask\w*\b|\b(real|true)\s+(name|identity)\s+(of|behind)\b"
            r"|\bwho\s+(is|runs)\s+behind\s+(the\s+)?(account|username|handle|profile)\b"
        ),
        "Lantern does not unmask anonymous accounts.",
    ),
    (
        r"\b(evade|avoid|escape)\s+(the\s+)?(police|law\s+enforcement|arrest|detection)\b",
        "Lantern does not help evade law enforcement.",
    ),
)
_COMPILED = tuple((re.compile(pattern, re.IGNORECASE), reason) for pattern, reason in _RULES)
MAX_BRIEF = 600


def check_brief(brief: str) -> str | None:
    """Return a refusal reason when a fixed rule matches, else None."""
    if len(brief.strip()) < 10:
        return "Please write a full question of at least 10 characters."
    if len(brief) > MAX_BRIEF:
        return f"Please keep the question under {MAX_BRIEF} characters."
    for pattern, reason in _COMPILED:
        if pattern.search(brief):
            return f"{reason} Ask about events, organisations, places or public figures instead."
    return None
