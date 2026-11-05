"""Public social media posts as ground reports: a Bluesky phrase search or a Mastodon hashtag.

Only event-centred searches, never an account's timeline. Each post becomes a draft
source that keeps the post itself, never who wrote it.
"""

import json
from typing import ClassVar, Self

from pydantic import BaseModel, Field, model_validator

from lantern.social import Post, SocialSearch
from lantern.tools.base import SourceDraft, ToolArgs, ToolContext, ToolKind, ToolResult


class SocialArgs(ToolArgs):
    phrase: str | None = Field(default=None, max_length=500)
    hashtag: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _one_of(self) -> Self:
        if bool(self.phrase) == bool(self.hashtag):
            msg = "give either a phrase or a hashtag"
            raise ValueError(msg)
        return self


def post_draft(post: Post) -> SourceDraft:
    record = {
        "platform": post.platform,
        "url": post.url,
        "posted_at": post.posted_at,
        "language": post.language,
        "text": post.text,
    }
    return SourceDraft(
        url=post.url,
        title=f"{post.platform.capitalize()} post",
        published=post.posted_at or None,
        body=json.dumps(record, ensure_ascii=False, sort_keys=True).encode(),
        text=post.text,
        kind="post",
        origin=post.origin,
    )


class SocialPosts:
    name: ClassVar[str] = "social_search"
    description: ClassVar[str] = (
        "Public posts as unverified ground reports: Bluesky posts matching a phrase, or public "
        "Mastodon posts with a hashtag. Never an account's timeline."
    )
    args_model: ClassVar[type[BaseModel]] = SocialArgs
    kind: ClassVar[ToolKind] = "search"
    rate_key: ClassVar[str] = "social"
    min_interval: ClassVar[float] = 0.0

    def __init__(self, social: SocialSearch, limit: int) -> None:
        self._social, self._limit = social, limit

    async def run(self, args: SocialArgs, _ctx: ToolContext) -> ToolResult:
        if args.hashtag:
            tag = args.hashtag.lstrip("#")
            posts = await self._social.hashtag(tag, self._limit)
            summary = f"Mastodon: #{tag} ({len(posts)} public posts)."
        else:
            phrase = args.phrase or ""
            posts = await self._social.search(phrase, self._limit)
            summary = f"Bluesky: searched “{phrase}” ({len(posts)} posts)."
        return ToolResult([], [post_draft(post) for post in posts], summary)
