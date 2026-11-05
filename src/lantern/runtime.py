"""Build the real tools from settings, and run or continue one investigation."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

from lantern.agent.loop import Agent
from lantern.archive import Wayback
from lantern.config import AppSettings
from lantern.core.loop_rules import CONTINUE, DEEP, QUICK, Budget
from lantern.egress import Fetcher
from lantern.llm import Gateway, ModelError, Provider, TokenBudget
from lantern.models import Investigation
from lantern.pipeline import Investigator, Limits, Tools
from lantern.search import SearchError, TavilySearch
from lantern.sites import blocked_site
from lantern.social import PublicSocial
from lantern.store import Store
from lantern.tools.adapters.sanctions import SanctionsSearch
from lantern.tools.adapters.wiki import WikiLookup
from lantern.tools.base import Tool

GROQ = "https://api.groq.com/openai/v1"


def providers(settings: AppSettings) -> list[Provider]:
    """Configured providers in order of use for planning, judging and writing.

    Gemini comes last here: its free tier may use prompts to improve Google's products.
    Lantern sends only public pages, public posts and its own working notes to any provider.
    """
    found = []
    if settings.cerebras_api_key:
        found.append(
            Provider(
                "cerebras",
                "https://api.cerebras.ai/v1",
                settings.cerebras_api_key.get_secret_value(),
                settings.cerebras_model,
                extra={"reasoning_effort": "low"},
            )
        )
    if settings.groq_api_key:
        found.append(
            Provider(
                "groq",
                GROQ,
                settings.groq_api_key.get_secret_value(),
                settings.groq_model,
                extra={"reasoning_effort": "low"},
            )
        )
    if settings.gemini_api_key:
        found.append(
            Provider(
                "gemini",
                "https://generativelanguage.googleapis.com/v1beta/openai",
                settings.gemini_api_key.get_secret_value(),
                settings.gemini_model,
                extra={"reasoning_effort": "low"},
            )
        )
    return found


def reading_order(found: list[Provider]) -> list[Provider]:
    """For bulk page reading, Gemini goes first when configured: its free tier allows far
    more tokens per minute than the others, and pages are public material. The same
    Provider objects are shared, so rate-limit waits apply across both orders."""
    return sorted(found, key=lambda provider: provider.name != "gemini")


def fast_order(found: list[Provider], settings: AppSettings) -> list[Provider]:
    """For triage and item lists: Groq's smaller model first, which has its own free daily
    quota, then the same providers as for thinking (shared, so their waits apply)."""
    if not settings.groq_api_key:
        return found
    key = settings.groq_api_key.get_secret_value()
    fast = Provider("groq", GROQ, key, settings.fast_model, extra={"reasoning_effort": "low"})
    return [fast, *found]


def record_tools(settings: AppSettings, fetcher: Fetcher) -> tuple[Tool, ...]:
    """The agent's official-record tools: sanctions lists (cached a day under the data
    folder) and Wikipedia/Wikidata background."""
    if not settings.records_enabled:
        return ()
    lists = Path(settings.data_dir) / "cache" / "lists"
    return (SanctionsSearch(fetcher, lists), WikiLookup(fetcher))


def budget_for(investigation: Investigation, settings: AppSettings, *, resume: bool) -> Budget:
    """The agent's budget: a continuation gets its own; otherwise by the chosen depth. The
    token limits come from settings."""
    if resume:
        return replace(CONTINUE, tokens=settings.continue_tokens)
    if investigation.depth == "quick":
        return replace(QUICK, tokens=settings.quick_tokens)
    return replace(DEEP, tokens=settings.deep_tokens)


def missing_keys(settings: AppSettings) -> list[str]:
    missing = []
    if not settings.tavily_api_key:
        missing.append("LANTERN_TAVILY_API_KEY")
    if not (settings.groq_api_key or settings.cerebras_api_key or settings.gemini_api_key):
        missing.append("LANTERN_GROQ_API_KEY (or LANTERN_GEMINI_API_KEY)")
    return missing


@asynccontextmanager
async def open_tools(
    settings: AppSettings, investigation: Investigation, tokens: TokenBudget | None = None
) -> AsyncIterator[Tools]:
    """The real model gateways, search, fetcher, social search and archive, closed after.
    With a token budget (the agent), every gateway shares it, and triage and item lists go
    to a fast model of their own."""
    if settings.tavily_api_key is None:
        raise SearchError("Web search has no key. Set LANTERN_TAVILY_API_KEY.")
    found, usage, calls = providers(settings), investigation.usage, settings.max_llm_calls
    model = Gateway(found, usage, calls, tokens=tokens)
    reader = Gateway(reading_order(found), usage, calls, tokens=tokens)
    fast = Gateway(fast_order(found, settings), usage, calls, tokens=tokens) if tokens else None
    searcher = TavilySearch(settings.tavily_api_key.get_secret_value())
    fetcher = Fetcher(settings.user_agent, blocked=blocked_site)
    social = (
        PublicSocial(settings.user_agent, mastodon=settings.mastodon_instance)
        if settings.social_enabled
        else None
    )
    try:
        yield Tools(
            model=model,
            searcher=searcher,
            fetcher=fetcher,
            social=social,
            reader=reader,
            archive=Wayback(fetcher) if settings.archive_enabled else None,
            fast=fast,
            tokens=tokens,
            records=record_tools(settings, fetcher) if tokens else (),
        )
    finally:
        await model.close()
        await reader.close()
        if fast:
            await fast.close()
        await searcher.close()
        await fetcher.close()
        if social:
            await social.close()


async def run_investigation(
    investigation: Investigation,
    settings: AppSettings,
    store: Store,
    on_change: Callable[[Investigation], None] | None = None,
    *,
    resume: bool = False,
) -> Investigation:
    """Run a new investigation, or continue a finished one when `resume` is true."""
    if missing := missing_keys(settings):
        investigation.status = "failed"
        investigation.error = f"Missing keys: {', '.join(missing)}. Add them as Codespaces secrets."
        store.save(investigation)
        return investigation
    # A continuation always digs deep, whatever the first pass was.
    limits = Limits.for_depth(
        "deep" if resume else investigation.depth,
        max_questions=settings.max_questions,
        max_posts=settings.max_posts,
    )
    budget = budget_for(investigation, settings, resume=resume)
    used = investigation.usage.tokens_in + investigation.usage.tokens_out
    tokens = TokenBudget(budget.tokens, start=used) if settings.agent else None
    try:
        async with open_tools(settings, investigation, tokens) as tools:
            investigator = (
                Agent(investigation, tools, store, limits, on_change, budget=budget)
                if settings.agent
                else Investigator(investigation, tools, store, limits, on_change)
            )
            return await (investigator.resume() if resume else investigator.run())
    except (ModelError, SearchError) as error:
        investigation.status, investigation.error = "failed", str(error)
        store.save(investigation)
        return investigation


async def continue_investigation(
    investigation: Investigation,
    settings: AppSettings,
    store: Store,
    on_change: Callable[[Investigation], None] | None = None,
) -> Investigation:
    """More rounds on a finished investigation; see Investigator.resume."""
    return await run_investigation(investigation, settings, store, on_change, resume=True)
