"""Text normalisation with an offset map, so quotes can be found in the original text."""

import unicodedata

# Written as code points so no ambiguous or invisible characters sit in the source.
_QUOTES = {chr(c): "'" for c in (0x2018, 0x2019, 0x201A, 0x201B)} | {
    chr(c): '"' for c in (0x201C, 0x201D, 0x201E, 0x201F)
}
_DASHES = {chr(c): "-" for c in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212)}
_INVISIBLE = {chr(c) for c in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD)}
MIN_QUOTE = 12


def normalise(text: str) -> tuple[str, list[int]]:
    """Return the normalised text and, for each of its characters, the original offset."""
    out: list[str] = []
    offsets: list[int] = []
    for index, char in enumerate(text):
        if char in _INVISIBLE:
            continue
        for piece in unicodedata.normalize("NFKC", char):
            mapped = _QUOTES.get(piece) or _DASHES.get(piece) or piece
            for folded in mapped.casefold():
                item = " " if folded.isspace() else folded
                if item == " " and (not out or out[-1] == " "):
                    continue
                out.append(item)
                offsets.append(index)
    if out and out[-1] == " ":
        out.pop()
        offsets.pop()
    return "".join(out), offsets


def find_quote(text: str, quote: str) -> tuple[int, int] | None:
    """Find `quote` in `text` after normalisation; return its span in the original text."""
    needle, _ = normalise(quote)
    needle = needle.strip(" .\"'")
    if len(needle) < MIN_QUOTE:
        return None
    haystack, offsets = normalise(text)
    position = haystack.find(needle)
    if position < 0:
        return None
    return offsets[position], offsets[position + len(needle) - 1] + 1


def chunks(text: str, size: int = 10000, overlap: int = 400, limit: int = 1) -> list[str]:
    """Split text on paragraph boundaries into at most `limit` chunks of about `size` chars."""
    parts: list[str] = []
    start = 0
    while start < len(text) and len(parts) < limit:
        end = min(len(text), start + size)
        if end < len(text):
            cut = text.rfind("\n", start + size // 2, end)
            end = cut if cut > 0 else end
        parts.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return parts


_STOPWORDS = {
    "which",
    "what",
    "when",
    "where",
    "who",
    "whom",
    "have",
    "been",
    "with",
    "from",
    "that",
    "this",
    "were",
    "their",
    "there",
    "about",
    "into",
    "after",
    "before",
    "year",
    "years",
    "past",
    "publicly",
    "known",
    "reported",
    "they",
    "them",
    "these",
    "those",
    "does",
}


def relevant_chunks(text: str, terms: list[str], size: int = 10000, limit: int = 1) -> list[str]:
    """The `limit` chunks of a long text that mention the given terms most, in page order."""
    parts = chunks(text, size=size, limit=200)
    if len(parts) <= limit:
        return parts
    words = {
        word
        for term in terms
        for word in normalise(term)[0].split()
        if len(word) > 3 and word not in _STOPWORDS
    }

    def score(part: str) -> int:
        lowered = normalise(part)[0]
        return sum(lowered.count(word) for word in words)

    best = sorted(range(len(parts)), key=lambda index: (-score(parts[index]), index))[:limit]
    return [parts[index] for index in sorted(best)]
