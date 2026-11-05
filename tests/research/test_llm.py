"""The model gateway validates JSON, retries once, and falls back on rate limits."""

import json

import httpx
import pytest

from lantern.config import AppSettings
from lantern.llm import Gateway, ModelError, Provider, QuotaError
from lantern.models import Usage
from lantern.prompts import GateOut
from lantern.runtime import missing_keys, providers


def reply(content, tokens=10):
    body = {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": tokens, "completion_tokens": tokens},
    }
    return httpx.Response(200, json=body)


def gateway(responses, providers=("a",), max_calls=10):
    seen = []

    def handler(request):
        seen.append((request.url.host, json.loads(request.content)))
        return responses.pop(0)

    usage = Usage()
    items = [Provider(name, f"https://{name}.test/v1", "key", "m") for name in providers]
    return Gateway(items, usage, max_calls, transport=httpx.MockTransport(handler)), usage, seen


async def test_valid_json_is_parsed_and_usage_counted():
    model, usage, seen = gateway([reply('{"allowed": true, "reason": ""}')])
    out = await model.structured("system", "user", GateOut)
    assert out.allowed is True
    assert usage.llm_calls == 1
    assert usage.tokens_in == 10
    assert seen[0][1]["response_format"] == {"type": "json_object"}


async def test_an_invalid_reply_gets_one_retry_with_the_error():
    model, _, seen = gateway([reply("not json"), reply('```json\n{"allowed": false}\n```')])
    out = await model.structured("system", "user", GateOut)
    assert out.allowed is False
    assert "invalid" in seen[1][1]["messages"][-1]["content"]


async def test_two_invalid_replies_fail_the_step():
    model, _, _ = gateway([reply("{}"), reply('{"allowed": "maybe"}')])
    with pytest.raises(ModelError, match="invalid answer twice"):
        await model.structured("system", "user", GateOut)


async def test_a_rate_limited_provider_falls_back_to_the_next():
    limited = httpx.Response(429, headers={"retry-after": "30"})
    model, usage, seen = gateway([limited, reply('{"allowed": true}')], providers=("a", "b"))
    assert (await model.structured("s", "u", GateOut)).allowed
    assert [host for host, _ in seen] == ["a.test", "b.test"]
    assert usage.providers == ["b:m"]


async def test_the_call_cap_stops_the_investigation():
    model, _, _ = gateway([reply('{"allowed": true}')], max_calls=1)
    await model.structured("s", "u", GateOut)
    with pytest.raises(ModelError, match="limit of 1 AI calls"):
        await model.structured("s", "u", GateOut)


def test_no_provider_gives_a_clear_message():
    with pytest.raises(ModelError, match="LANTERN_GROQ_API_KEY"):
        Gateway([], Usage(), 5)


async def test_a_rejected_key_is_named_in_the_error():
    model, _, _ = gateway([httpx.Response(401)])
    with pytest.raises(ModelError, match="LANTERN_A_API_KEY"):
        await model.structured("s", "u", GateOut)


async def test_a_request_too_large_for_one_provider_goes_to_the_next():
    too_big = httpx.Response(413, text="Request too large for model")
    model, _, seen = gateway([too_big, reply('{"allowed": true}')], providers=("a", "b"))
    assert (await model.structured("s", "u", GateOut)).allowed
    assert [host for host, _ in seen] == ["a.test", "b.test"]


async def test_exhausted_free_limits_raise_a_quota_error():
    limited = httpx.Response(429, headers={"retry-after": "3600"})
    model, _, _ = gateway([limited])
    with pytest.raises(QuotaError, match="used up"):
        await model.structured("s", "u", GateOut)


def test_gemini_is_used_only_after_the_other_providers():
    settings = AppSettings(groq_api_key="g", gemini_api_key="m", tavily_api_key="t")
    assert [item.name for item in providers(settings)] == ["groq", "gemini"]
    assert providers(settings)[1].base_url.startswith("https://generativelanguage.googleapis.com")
    only_gemini = AppSettings(gemini_api_key="m", tavily_api_key="t")
    assert missing_keys(only_gemini) == []


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds


def patient(responses, providers=("a", "b")):
    """A gateway whose clock is fake: waits take no real time."""
    clock, seen = Clock(), []

    def handler(request):
        seen.append(request.url.host)
        return responses[request.url.host].pop(0)

    items = [Provider(name, f"https://{name}.test/v1", "key", "m") for name in providers]
    transport = httpx.MockTransport(handler)
    model = Gateway(items, Usage(), 50, transport=transport, clock=clock, sleep=clock.sleep)
    return model, clock, seen


async def test_busy_providers_are_retried_until_one_answers():
    busy = [httpx.Response(429, headers={"retry-after": "40"}) for _ in range(3)]
    down = [httpx.Response(503) for _ in range(20)]
    model, clock, seen = patient({"a.test": [*busy, reply('{"allowed": true}')], "b.test": down})
    assert (await model.structured("s", "u", GateOut)).allowed
    assert seen.count("a.test") == 4  # more than the old limit of 8 attempts in all
    assert len(seen) > 8
    assert clock.now < 180


async def test_providers_failing_for_three_minutes_give_a_plain_reason():
    busy = [httpx.Response(429, headers={"retry-after": "30"}) for _ in range(30)]
    down = [httpx.Response(503) for _ in range(30)]
    model, clock, _ = patient({"a.test": busy, "b.test": down})
    with pytest.raises(ModelError) as caught:
        await model.structured("s", "u", GateOut)
    message = str(caught.value)
    assert message.startswith("The AI providers kept failing for 3 minutes")
    assert "a:m: HTTP 429, busy or rate-limited" in message
    assert "b:m: HTTP 503, server error" in message
    assert 150 <= clock.now <= 180
