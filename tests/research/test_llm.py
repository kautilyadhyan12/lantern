"""The model gateway validates JSON, retries once, and falls back on rate limits."""

import json

import httpx
import pytest

from lantern.llm import Gateway, ModelError, Provider
from lantern.models import Usage
from lantern.prompts import GateOut


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
