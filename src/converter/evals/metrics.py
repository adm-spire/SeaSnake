"""Eval metrics: compile rate, per-category match rate, repairs, rejections, cost."""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from ..agent.state import ConverterState


@dataclass
class ProgramResult:
    name: str
    status: str
    compile_ok: bool
    overall_rate: float
    per_category: dict[str, float] = field(default_factory=dict)
    repair_iterations: int = 0
    generation_rounds: int = 0
    validation_rejection_rate: float = 0.0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    invalid_user_tests: int = 0
    error: str | None = None


def result_from_state(
    name: str,
    state: ConverterState,
    *,
    latency_s: float,
) -> ProgramResult:
    score = state.score
    per_category = (
        {category: value.rate for category, value in score.per_category.items()}
        if score is not None
        else {}
    )
    overall_rate = score.overall_rate if score is not None else 0.0

    attempted = (
        len(state.test_cases)
        + state.validation_rejections
        + state.generation_rejections
    )
    rejection_rate = (
        (state.validation_rejections + state.generation_rejections) / attempted
        if attempted
        else 0.0
    )

    return ProgramResult(
        name=name,
        status=state.status,
        compile_ok=bool(state.compile_ok),
        overall_rate=overall_rate,
        per_category=per_category,
        repair_iterations=state.attempt,
        generation_rounds=state.generation_round,
        validation_rejection_rate=rejection_rate,
        cost_usd=state.usage.cost_usd,
        latency_s=latency_s,
        invalid_user_tests=len(state.invalid_user_tests),
        error=state.last_error,
    )


def aggregate(results: list[ProgramResult]) -> dict[str, Any]:
    if not results:
        return {"programs": 0}

    categories = sorted(
        {category for result in results for category in result.per_category}
    )
    category_averages = {
        category: statistics.mean(
            result.per_category.get(category, 0.0) for result in results
        )
        for category in categories
    }
    statuses = Counter(result.status for result in results)

    return {
        "programs": len(results),
        "statuses": dict(statuses),
        "compile_rate": statistics.mean(1.0 if r.compile_ok else 0.0 for r in results),
        "avg_overall_match_rate": statistics.mean(r.overall_rate for r in results),
        "per_category_avg": category_averages,
        "avg_repair_iterations": statistics.mean(r.repair_iterations for r in results),
        "avg_generation_rounds": statistics.mean(r.generation_rounds for r in results),
        "avg_validation_rejection_rate": statistics.mean(
            r.validation_rejection_rate for r in results
        ),
        "total_cost_usd": sum(r.cost_usd for r in results),
        "avg_latency_s": statistics.mean(r.latency_s for r in results),
    }


def results_as_dicts(results: list[ProgramResult]) -> list[dict[str, Any]]:
    return [asdict(result) for result in results]
