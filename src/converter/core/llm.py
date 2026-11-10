"""Provider-agnostic LLM client.

The contract is an OpenAI-compatible ``/chat/completions`` endpoint, which
DeepSeek exposes. Swapping providers is a config change (base URL + model +
key), not a code change. Retries happen only at this boundary, so the rest of
the system sees either a response or a typed LLMError.

``TrackedLLM`` wraps a raw client and records token/latency/cost usage into the
per-run UsageTracker.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .config import Settings
from .errors import LLMError
from .logging import get_logger
from .usage import UsageTracker

logger = get_logger(__name__)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    model: str
    latency_ms: int


class LLMClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse: ...


class OpenAICompatibleLLM:
    """Minimal synchronous client with retry/backoff on transient failures."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.Client(timeout=httpx.Timeout(settings.llm_timeout_s))

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenAICompatibleLLM:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        if not self._settings.llm_api_key:
            raise LLMError("LLM_API_KEY is not configured")

        url = self._settings.llm_base_url.rstrip("/") + "/chat/completions"
        payload: dict[str, Any] = {
            "model": self._settings.llm_model,
            "messages": messages,
            "temperature": (
                self._settings.llm_temperature if temperature is None else temperature
            ),
        }
        if response_format is not None:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self._settings.llm_api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        attempts = self._settings.llm_max_retries + 1

        for attempt in range(attempts):
            started = time.perf_counter()
            try:
                response = self._client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("LLM transport error (attempt %s/%s): %s", attempt + 1, attempts, exc)
            else:
                latency_ms = int((time.perf_counter() - started) * 1000)
                if response.status_code == 200:
                    return self._parse_response(response.json(), latency_ms)
                if response.status_code in {429, 500, 502, 503, 504}:
                    last_error = LLMError(
                        f"LLM transient HTTP {response.status_code}: {response.text[:300]}"
                    )
                    logger.warning(
                        "LLM transient HTTP %s (attempt %s/%s)",
                        response.status_code,
                        attempt + 1,
                        attempts,
                    )
                else:
                    raise LLMError(
                        f"LLM HTTP {response.status_code}: {response.text[:500]}"
                    )

            if attempt < attempts - 1:
                time.sleep(min(2**attempt, 8))

        raise LLMError(f"LLM request failed after {attempts} attempts: {last_error}")

    def _parse_response(self, data: dict[str, Any], latency_ms: int) -> LLMResponse:
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM response shape: {data}") from exc

        if not isinstance(text, str):
            raise LLMError("LLM response content was not text")

        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            model=str(data.get("model", self._settings.llm_model)),
            latency_ms=latency_ms,
        )


class TrackedLLM:
    """Decorator that records every call into a per-run UsageTracker."""

    def __init__(self, client: LLMClient, tracker: UsageTracker) -> None:
        self._client = client
        self._tracker = tracker

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        response = self._client.complete(
            messages, temperature=temperature, response_format=response_format
        )
        self._tracker.record(
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            latency_ms=response.latency_ms,
        )
        return response


def build_llm(settings: Settings, tracker: UsageTracker) -> TrackedLLM:
    return TrackedLLM(OpenAICompatibleLLM(settings), tracker)
