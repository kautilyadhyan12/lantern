"""Model gateway: OpenAI-compatible providers, fallback on limits, validated JSON output.

The model proposes; code decides. Every reply must be one JSON object that validates
against a Pydantic model. An invalid reply gets one retry with the error, then fails.
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError

from lantern.models import Usage

MAX_WAIT = 65.0


class ModelError(Exception):
    """A model step failed; the message says why and what to do."""


@dataclass
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str
    available_at: float = 0.0
    extra: dict[str, str] = field(default_factory=dict)
    problem: str | None = None


class _TooLargeError(Exception):
    """This request is too large for one provider; another may accept it."""


class Model(Protocol):
    async def structured[T: BaseModel](self, system: str, user: str, output: type[T]) -> T: ...


class Gateway:
    def __init__(
        self,
        providers: list[Provider],
        usage: Usage,
        max_calls: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not providers:
            msg = "No AI model is configured. Set LANTERN_GROQ_API_KEY or LANTERN_CEREBRAS_API_KEY."
            raise ModelError(msg)
        self._providers = providers
        self._usage = usage
        self._max_calls = max_calls
        self._client = httpx.AsyncClient(
            transport=transport, timeout=httpx.Timeout(120.0, connect=10.0)
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def structured[T: BaseModel](self, system: str, user: str, output: type[T]) -> T:
        schema = json.dumps(output.model_json_schema())
        messages = [
            {
                "role": "system",
                "content": f"{system}\n\nReply with one JSON object matching "
                f"this JSON schema, and nothing else:\n{schema}",
            },
            {"role": "user", "content": user},
        ]
        reply = await self._complete(messages)
        try:
            return output.model_validate_json(reply)
        except ValidationError as error:
            problem = error.errors(include_url=False, include_input=False)[:5]
            messages += [
                {"role": "assistant", "content": reply[:4000]},
                {
                    "role": "user",
                    "content": f"That reply was invalid: {problem}. "
                    "Reply again with one valid JSON object only.",
                },
            ]
        reply = await self._complete(messages)
        try:
            return output.model_validate_json(reply)
        except ValidationError as error:
            msg = f"The AI model gave an invalid answer twice ({output.__name__})."
            raise ModelError(msg) from error

    async def _complete(self, messages: list[dict[str, str]]) -> str:
        if self._usage.llm_calls >= self._max_calls:
            msg = f"The investigation reached its limit of {self._max_calls} AI calls."
            raise ModelError(msg)
        loop = asyncio.get_running_loop()
        too_large: set[str] = set()
        for _attempt in range(8):
            usable = [
                item for item in self._providers if not item.problem and item.name not in too_large
            ]
            if not usable:
                problems = [
                    f"{item.name} {item.problem}" for item in self._providers if item.problem
                ]
                problems += [f"{name} said the request was too large" for name in sorted(too_large)]
                msg = f"No AI provider could take this step: {'; '.join(problems)}."
                raise ModelError(msg)
            provider = min(usable, key=lambda item: item.available_at)
            wait = provider.available_at - loop.time()
            if wait > MAX_WAIT:
                names = ", ".join(item.name for item in usable)
                msg = f"All AI providers ({names}) are at their free limits. Try again later."
                raise ModelError(msg)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                result = await self._call(provider, messages)
            except _TooLargeError:
                too_large.add(provider.name)
                continue
            if result is not None:
                return result
        msg = "The AI providers kept failing. Try again in a few minutes."
        raise ModelError(msg)

    async def _call(self, provider: Provider, messages: list[dict[str, str]]) -> str | None:
        loop = asyncio.get_running_loop()
        body: dict[str, object] = {
            "model": provider.model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            **provider.extra,
        }
        try:
            response = await self._client.post(
                f"{provider.base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {provider.api_key}"},
            )
        except httpx.HTTPError:
            provider.available_at = loop.time() + 5
            return None
        if response.status_code == 429 or response.status_code >= 500:
            retry = _retry_after(response)
            provider.available_at = loop.time() + (retry if retry is not None else 10.0)
            return None
        if response.status_code in {401, 403}:
            key = f"LANTERN_{provider.name.upper()}_API_KEY"
            provider.problem = f"rejected its API key (check {key})"
            return None
        too_large = "too large" in response.text.lower() or "context" in response.text.lower()
        if response.status_code == 413 or (response.status_code == 400 and too_large):
            raise _TooLargeError
        if response.status_code != 200:
            detail = response.text[:300]
            msg = f"The AI provider {provider.name} refused the request ({detail})."
            raise ModelError(msg)
        data = response.json()
        self._usage.llm_calls += 1
        usage = data.get("usage") or {}
        self._usage.tokens_in += int(usage.get("prompt_tokens") or 0)
        self._usage.tokens_out += int(usage.get("completion_tokens") or 0)
        label = f"{provider.name}:{provider.model}"
        if label not in self._usage.providers:
            self._usage.providers.append(label)
        content = data["choices"][0]["message"].get("content") or ""
        return _strip_fences(str(content))


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return max(0.5, float(value)) if value else None
    except ValueError:
        return None


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.removesuffix("```").strip()
    return text
