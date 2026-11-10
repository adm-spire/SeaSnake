"""Dependency injection for graph nodes.

Services are built once per run: a sandbox executor, a tracked LLM client, a
tracer, and the shared usage tracker. Nodes receive them through closures, so
there are no global singletons and concurrent API requests stay isolated.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.config import Settings
from ..core.llm import LLMClient, build_llm
from ..core.usage import UsageTracker
from ..observability.tracing import Tracer
from ..sandbox.executor import SandboxExecutor, build_executor


@dataclass
class Services:
    settings: Settings
    executor: SandboxExecutor
    llm: LLMClient
    tracker: UsageTracker
    tracer: Tracer


def build_services(settings: Settings | None = None) -> Services:
    settings = settings or Settings()
    tracker = UsageTracker(
        prompt_cost_per_1k=settings.prompt_cost_per_1k,
        completion_cost_per_1k=settings.completion_cost_per_1k,
    )
    return Services(
        settings=settings,
        executor=build_executor(settings),
        llm=build_llm(settings, tracker),
        tracker=tracker,
        tracer=Tracer(settings),
    )
