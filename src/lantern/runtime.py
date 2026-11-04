"""Build the real tools from settings, and run one investigation."""

from collections.abc import Callable

from lantern.config import AppSettings
from lantern.egress import Fetcher
from lantern.llm import Gateway, ModelError, Provider
from lantern.models import Investigation
from lantern.pipeline import Investigator, Limits, Tools
from lantern.search import SearchError, TavilySearch
from lantern.social import PublicSocial
from lantern.store import Store


def providers(settings: AppSettings) -> list[Provider]:
    """Configured model providers; Cerebras first because its free tier allows more tokens."""
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
    return found


def missing_keys(settings: AppSettings) -> list[str]:
    missing = []
    if not settings.tavily_api_key:
        missing.append("LANTERN_TAVILY_API_KEY")
    if not (settings.groq_api_key or settings.cerebras_api_key):
        missing.append("LANTERN_GROQ_API_KEY (or LANTERN_CEREBRAS_API_KEY)")
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
    limits = Limits(
        max_questions=settings.max_questions,
        max_pages=settings.max_pages,
        max_posts=settings.max_posts,
    )
    try:
        model = Gateway(providers(settings), investigation.usage, settings.max_llm_calls)
    except ModelError as error:
        investigation.status, investigation.error = "failed", str(error)
        store.save(investigation)
        return investigation
    searcher = TavilySearch(settings.tavily_api_key.get_secret_value())
    fetcher = Fetcher(settings.user_agent)
    social = (
        PublicSocial(settings.user_agent, mastodon=settings.mastodon_instance)
        if settings.social_enabled
        else None
    )
    try:
        tools = Tools(model=model, searcher=searcher, fetcher=fetcher, social=social)
        return await Investigator(investigation, tools, store, limits, on_change).run()
    except SearchError as error:
        investigation.status, investigation.error = "failed", str(error)
        store.save(investigation)
        return investigation
    finally:
        await model.close()
        await searcher.close()
        await fetcher.close()
        if social:
            await social.close()
