"""Heuristic coverage gaps used to decide whether to regenerate tests.

Phase 1 does not try to measure line/branch coverage. Instead it checks that
every public function has at least one happy-path test and that the suite as a
whole contains an edge case and an error-condition test. If a function simply
has no error behavior, generated error tests will be rejected by Python
validation and the regeneration loop will stop at its attempt cap.
"""

from __future__ import annotations

from .analysis import FunctionInfo
from .models import Category, NormalizedTest


def compute_coverage_gaps(
    tests: list[NormalizedTest],
    functions: list[FunctionInfo],
) -> list[str]:
    gaps: list[str] = []

    covered_functions = {
        test.function for test in tests if test.category == Category.HAPPY_PATH
    }
    for function in functions:
        if function.name not in covered_functions:
            gaps.append(f"function `{function.name}` has no happy_path test")

    if functions and not any(test.category == Category.EDGE_CASE for test in tests):
        gaps.append("suite has no edge_case test")

    if functions and not any(
        test.category == Category.ERROR_CONDITION for test in tests
    ):
        gaps.append("suite has no error_condition test")

    return gaps


def has_gaps(gaps: list[str]) -> bool:
    return bool(gaps)
