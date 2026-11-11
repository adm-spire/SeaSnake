"""Per-category scoring and configurable pass criteria."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..testing.models import BaselineCase, Category
from .differ import compare_outcome
from .models import ActualOutcome, FailureCase


class PassCriteria(BaseModel):
    """All configured thresholds must be met.

    ``overall`` may be None to disable the overall check. A category with no
    tests is treated as vacuously passing, which keeps per-category thresholds
    useful even when a suite happens not to contain that category.
    """

    overall: float | None = 1.0
    by_category: dict[Category, float] = Field(
        default_factory=lambda: {
            Category.HAPPY_PATH: 1.0,
            Category.ERROR_CONDITION: 1.0,
            Category.EDGE_CASE: 0.95,
        }
    )


class CategoryScore(BaseModel):
    total: int
    passed: int
    rate: float


class ScoreSummary(BaseModel):
    overall_total: int
    overall_passed: int
    overall_rate: float
    per_category: dict[str, CategoryScore]
    failures: list[FailureCase]


def score_results(
    baseline: list[BaselineCase],
    actuals: dict[str, ActualOutcome],
) -> ScoreSummary:
    totals: dict[str, int] = {category.value: 0 for category in Category}
    passed_counts: dict[str, int] = {category.value: 0 for category in Category}
    failures: list[FailureCase] = []

    for case in baseline:
        category = case.category.value
        totals.setdefault(category, 0)
        passed_counts.setdefault(category, 0)
        totals[category] += 1

        actual = actuals.get(
            case.test_id,
            ActualOutcome(kind="crash", message="missing translated result"),
        )
        result = compare_outcome(case.expected, actual)
        if result.ok:
            passed_counts[category] += 1
        else:
            failures.append(
                FailureCase(
                    test_id=case.test_id,
                    name=case.name,
                    function=case.function,
                    args=case.args,
                    kwargs=case.kwargs,
                    category=case.category,
                    source=case.source,
                    expected=case.expected,
                    actual=actual,
                    reason=result.reason,
                )
            )

    overall_total = len(baseline)
    overall_passed = overall_total - len(failures)
    overall_rate = _rate(overall_passed, overall_total)

    per_category: dict[str, CategoryScore] = {}
    for category, total in totals.items():
        per_category[category] = CategoryScore(
            total=total,
            passed=passed_counts[category],
            rate=_rate(passed_counts[category], total),
        )

    return ScoreSummary(
        overall_total=overall_total,
        overall_passed=overall_passed,
        overall_rate=overall_rate,
        per_category=per_category,
        failures=failures,
    )


def evaluate_pass_criteria(
    summary: ScoreSummary,
    criteria: PassCriteria,
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    epsilon = 1e-9

    if criteria.overall is not None and summary.overall_rate + epsilon < criteria.overall:
        failures.append(
            f"overall pass rate {summary.overall_rate:.2%} is below "
            f"the required {criteria.overall:.2%}"
        )

    for category, threshold in criteria.by_category.items():
        score = summary.per_category.get(category.value)
        if score is None or score.total == 0:
            continue
        if score.rate + epsilon < threshold:
            failures.append(
                f"{category.value} pass rate {score.rate:.2%} is below "
                f"the required {threshold:.2%}"
            )

    return not failures, failures


def _rate(passed: int, total: int) -> float:
    return 1.0 if total == 0 else passed / total
