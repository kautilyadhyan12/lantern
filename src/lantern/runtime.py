"""Build the real tools from settings, and run one investigation."""

from collections.abc import Callable

from lantern.config import AppSettings
from lantern.egress import Fetcher
from lantern.llm import Gateway, ModelError, Provider
from lantern.models import Investigation
from lantern.pipeline import Investigator, Limits, Tools
from lantern.search import SearchError, TavilySearch
from lantern.sites import blocked_site
from lantern.social import PublicSocial
from lantern.store import Store


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
                "https://api.groq.com/openai/v1",
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


def missing_keys(settings: AppSettings) -> list[str]:
    missing = []
    if not settings.tavily_api_key:
        missing.append("LANTERN_TAVILY_API_KEY")
    if not (settings.groq_api_key or settings.cerebras_api_key or settings.gemini_api_key):
        missing.append("LANTERN_GROQ_API_KEY (or LANTERN_GEMINI_API_KEY)")
    return missing


async def run_investigation(
    investigation: Investigation,
    settings: AppSettings,
    store: Store,
    on_change: Callable[[Investigation], None] | None = None,
) -> Investigation:
    if missing := missing_keys(settings):
        investigation.status = "failed"
        investigation.error = f"Missing keys: {', '.join(missing)}. Add them as Codespaces secrets."
        store.save(investigation)
        return investigation
    assert settings.tavily_api_key is not None  # noqa: S101  # checked by missing_keys above
    limits = Limits.for_depth(
        investigation.depth, max_questions=settings.max_questions, max_posts=settings.max_posts
    )
    found = providers(settings)
    try:
        model = Gateway(found, investigation.usage, settings.max_llm_calls)
        reader = Gateway(reading_order(found), investigation.usage, settings.max_llm_calls)
    except ModelError as error:
        investigation.status, investigation.error = "failed", str(error)
        store.save(investigation)
        return investigation
    searcher = TavilySearch(settings.tavily_api_key.get_secret_value())
    fetcher = Fetcher(settings.user_agent, blocked=blocked_site)
    social = (
        PublicSocial(settings.user_agent, mastodon=settings.mastodon_instance)
        if settings.social_enabled
        else None
    )
    try:
        tools = Tools(model=model, searcher=searcher, fetcher=fetcher, social=social, reader=reader)
        return await Investigator(investigation, tools, store, limits, on_change).run()
    except SearchError as error:
        investigation.status, investigation.error = "failed", str(error)
        store.save(investigation)
        return investigation
    finally:
        await model.close()
        await reader.close()
        await searcher.close()
        await fetcher.close()
        if social:
            await social.close()
