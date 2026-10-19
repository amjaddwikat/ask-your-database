import json

import httpx
import pytest
from pydantic import BaseModel

from app.llm.client import GeminiClient, LLMError, complete_structured
from tests.fakes import FakeLLM

ROUTER_SYSTEM = "You are the Router Agent"


class Decision(BaseModel):
    action: str


async def test_structured_output_strips_code_fences() -> None:
    llm = FakeLLM().reply("router", '```json\n{"action": "plot"}\n```')
    result = await complete_structured(llm, ROUTER_SYSTEM, "q", Decision)
    assert result.action == "plot"


async def test_structured_output_retries_with_the_error() -> None:
    llm = FakeLLM().reply("router", "Sure! Here you go", {"action": "analysis"})

    result = await complete_structured(llm, ROUTER_SYSTEM, "q", Decision)

    assert result.action == "analysis"
    assert "previous reply was not valid" in llm.calls_to("router")[1]


async def test_structured_output_gives_up() -> None:
    llm = FakeLLM().reply("router", "nope", "nope again")
    with pytest.raises(LLMError):
        await complete_structured(llm, ROUTER_SYSTEM, "q", Decision)


def _gemini_reply(text: str) -> httpx.Response:
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


async def test_gemini_sends_key_in_header_not_url() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _gemini_reply('{"ok": true}')

    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers={"x-goog-api-key": "secret"}
    )
    client = GeminiClient("secret", "gemini-test", http=http)

    text = await client.complete("system", "user", json_mode=True)

    assert text == '{"ok": true}'
    assert "secret" not in str(seen[0].url)
    assert seen[0].headers["x-goog-api-key"] == "secret"
    body = json.loads(seen[0].content)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["systemInstruction"]["parts"][0]["text"] == "system"


async def test_gemini_retries_on_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.client.asyncio.sleep", _no_sleep)
    responses = iter([httpx.Response(503), _gemini_reply("hello")])
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: next(responses)))

    assert await GeminiClient("k", "m", http=http).complete("s", "u") == "hello"


async def test_gemini_raises_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.client.asyncio.sleep", _no_sleep)
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(429)))

    with pytest.raises(LLMError, match="429"):
        await GeminiClient("k", "m", http=http, max_retries=1).complete("s", "u")


async def _no_sleep(_: float) -> None:
    return None
