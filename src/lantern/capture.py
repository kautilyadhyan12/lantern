"""Turn fetched bytes into readable text and metadata."""

from dataclasses import dataclass

import trafilatura

from lantern.egress import Page


@dataclass(frozen=True)
class Extracted:
    title: str | None
    published: str | None
    text: str


def extract(page: Page) -> Extracted | None:
    """Main text of a page, or None when nothing readable was found."""
    if page.content_type == "text/plain":
        text = page.body.decode("utf-8", "replace").strip()
        return Extracted(None, None, text) if text else None
    document = trafilatura.bare_extraction(
        page.body, url=page.url, with_metadata=True, include_comments=False, favor_recall=True
    )
    if document is None:
        return None
    data = document.as_dict() if hasattr(document, "as_dict") else dict(document)
    text = str(data.get("text") or "").strip()
    if len(text) < 200:
        return None
    title = data.get("title")
    date = data.get("date")
    return Extracted(str(title) if title else None, str(date) if date else None, text)
