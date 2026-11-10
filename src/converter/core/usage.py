"""Per-run token, latency, and cost accounting.

A UsageTracker is created per conversion run. LLM calls report into it, and the
final Report includes a snapshot. Keeping the tracker per-run (rather than
global) makes concurrent API requests account independently.
"""

from __future__ import annotations

import threading

from pydantic import BaseModel


class Usage(BaseModel):
    """Serializable usage snapshot included in the final report."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    llm_calls: int = 0


class UsageTracker:
    def __init__(
        self,
        *,
        prompt_cost_per_1k: float = 0.0,
        completion_cost_per_1k: float = 0.0,
    ) -> None:
        self._prompt_cost = prompt_cost_per_1k
        self._completion_cost = completion_cost_per_1k
        self._lock = threading.Lock()
        self._usage = Usage()

    def record(
        self,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
    ) -> None:
        with self._lock:
            self._usage.prompt_tokens += prompt_tokens
            self._usage.completion_tokens += completion_tokens
            self._usage.total_tokens += prompt_tokens + completion_tokens
            self._usage.latency_ms += latency_ms
            self._usage.llm_calls += 1
            self._usage.cost_usd += (
                prompt_tokens / 1000.0 * self._prompt_cost
                + completion_tokens / 1000.0 * self._completion_cost
            )

    def snapshot(self) -> Usage:
        with self._lock:
            return self._usage.model_copy(deep=True)
