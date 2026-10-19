"""LLM access behind a small interface, so agents don't depend on a specific provider."""

import asyncio
import json
import logging
import re
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """The model could not be reached or returned an unusable answer."""


class LLMClient(Protocol):
    async def complete(self, system: str, user: str, *, json_mode: bool = False) -> str: ...


async def complete_structured[T: BaseModel](
    llm: LLMClient,
    system: str,
    user: str,
    schema: type[T],
    *,
    context: dict[str, Any] | None = None,
    attempts: int = 2,
) -> T:
    """Ask for JSON and validate it against `schema`, re-asking once with the error if invalid.

    `context` is passed to Pydantic validators (e.g. the list of valid column names).
    """
    prompt = user
    last_error = ""
    for _ in range(attempts):
        raw = await llm.complete(system, prompt, json_mode=True)
        try:
            return schema.model_validate(_extract_json(raw), context=context)
        except (ValueError, ValidationError) as e:
            last_error = str(e)
            logger.info("Invalid structured output from LLM, retrying: %s", last_error)
            prompt = (
                f"{user}\n\nYour previous reply was not valid. Error:\n{last_error}\n"
                "Reply again with ONLY a JSON object that matches the required format."
            )
    raise LLMError(f"Model did not return valid {schema.__name__}: {last_error}")


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _extract_json(raw: str) -> Any:
    text = _FENCE.sub("", raw.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Some models wrap JSON in prose; fall back to the outermost object.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


class GeminiClient:
    """Minimal async client for the Gemini generateContent REST API."""

    _BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    _RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_s: float = 30.0,
        max_retries: int = 2,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._model = model
        self._max_retries = max_retries
        # The key goes in a header, never in the URL, so it can't end up in access logs.
        self._http = http or httpx.AsyncClient(
            timeout=timeout_s, headers={"x-goog-api-key": api_key}
        )

    async def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 2048},
        }
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"

        url = f"{self._BASE_URL}/{self._model}:generateContent"
        for attempt in range(self._max_retries + 1):
            try:
                resp = await self._http.post(url, json=body)
            except httpx.HTTPError as e:
                if attempt == self._max_retries:
                    raise LLMError(f"Could not reach the LLM provider: {e}") from e
            else:
                if resp.status_code not in self._RETRY_STATUSES or attempt == self._max_retries:
                    break
                logger.info("LLM returned %s, retrying", resp.status_code)
            await asyncio.sleep(0.5 * 2**attempt)

        if resp.status_code != 200:
            raise LLMError(f"LLM provider returned HTTP {resp.status_code}")
        try:
            data = resp.json()
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError("LLM provider returned an unexpected response shape") from e

    async def aclose(self) -> None:
        await self._http.aclose()
