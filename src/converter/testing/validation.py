"""Validate normalized tests against the original Python implementation.

A test is only useful as an oracle if Python actually behaves the way the test
claims. User tests that fail on the original code are reported (not dropped
silently) and excluded from the baseline. Generated tests that do not match
Python are discarded; the generator will be asked to fill the gaps again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..core.config import Settings
from ..core.values import approx_equal, values_equal
from ..sandbox.executor import SandboxExecutor
from ..sandbox.python_runner import run_python_cases
from .models import (
    ExpectedKind,
    ExpectedOutcome,
    InvalidUserTest,
    NormalizedTest,
    PythonOutcome,
    Source,
)


@dataclass(frozen=True)
class ValidationResult:
    valid_tests: list[NormalizedTest]
    invalid_user_tests: list[InvalidUserTest]
    rejected_generated: int
    python_outcomes: dict[str, PythonOutcome]
    duration_ms: int


def validate_cases(
    tests: list[NormalizedTest],
    *,
    python_src: str,
    executor: SandboxExecutor,
    settings: Settings,
) -> ValidationResult:
    if not tests:
        return ValidationResult(
            valid_tests=[],
            invalid_user_tests=[],
            rejected_generated=0,
            python_outcomes={},
            duration_ms=0,
        )

    cases = [
        {
            "test_id": test.id,
            "function": test.function,
            "args": test.args,
            "kwargs": test.kwargs,
        }
        for test in tests
    ]
    batch_timeout = max(15, min(180, settings.test_timeout_s * len(cases) + 10))
    run = run_python_cases(
        executor,
        python_src=python_src,
        cases=cases,
        per_case_timeout_s=settings.test_timeout_s,
        batch_timeout_s=batch_timeout,
    )

    valid_tests: list[NormalizedTest] = []
    invalid_user_tests: list[InvalidUserTest] = []
    rejected_generated = 0
    outcomes: dict[str, PythonOutcome] = {}

    for test in tests:
        raw = run.outcomes.get(test.id, {"kind": "crash", "message": "no outcome"})
        actual = _to_python_outcome(raw)
        matched, reason = _matches(test.expected, actual)
        if matched:
            valid_tests.append(test)
            outcomes[test.id] = actual
        elif test.source == Source.USER:
            invalid_user_tests.append(
                InvalidUserTest(
                    name=test.name,
                    reason=f"fails on original code: {reason}",
                    raw_source=test.raw_source,
                )
            )
        else:
            rejected_generated += 1

    return ValidationResult(
        valid_tests=valid_tests,
        invalid_user_tests=invalid_user_tests,
        rejected_generated=rejected_generated,
        python_outcomes=outcomes,
        duration_ms=run.duration_ms,
    )


def _to_python_outcome(raw: dict[str, Any]) -> PythonOutcome:
    kind = raw.get("kind")
    if kind == "value":
        return PythonOutcome(kind="value", value=raw.get("value"))
    if kind == "error":
        return PythonOutcome(
            kind="error",
            exception_type=raw.get("exception_type"),
            exception_mro=list(raw.get("exception_mro") or []),
            message=raw.get("message"),
        )
    if kind in {"timeout", "unsupported", "crash"}:
        return PythonOutcome(kind=kind, message=raw.get("message"))
    return PythonOutcome(kind="crash", message=f"unknown outcome kind: {kind!r}")


def _matches(
    expected: ExpectedOutcome,
    actual: PythonOutcome,
) -> tuple[bool, str]:
    if actual.kind == "value":
        if expected.kind != ExpectedKind.VALUE:
            return False, f"expected an error, got value {actual.value!r}"
        if expected.approx:
            matched = approx_equal(expected.value, actual.value)
            if not matched:
                return False, f"expected approx {expected.value!r}, got {actual.value!r}"
            return True, ""
        if not values_equal(expected.value, actual.value):
            return False, f"expected {expected.value!r}, got {actual.value!r}"
        return True, ""

    if actual.kind == "error":
        if expected.kind != ExpectedKind.ERROR:
            return (
                False,
                f"expected value {expected.value!r}, got {actual.exception_type}: {actual.message}",
            )
        expected_type = expected.exception_type or ""
        actual_mro = actual.exception_mro or [actual.exception_type or ""]
        if expected_type != actual.exception_type and expected_type not in actual_mro:
            return False, f"expected {expected_type}, got {actual.exception_type}"
        if expected.message_pattern:
            try:
                if re.search(expected.message_pattern, actual.message or "") is None:
                    return (
                        False,
                        f"message {actual.message!r} does not match "
                        f"{expected.message_pattern!r}",
                    )
            except re.error:
                return False, f"invalid message pattern: {expected.message_pattern!r}"
        return True, ""

    detail = f" ({actual.message})" if actual.message else ""
    return False, f"outcome was {actual.kind}{detail}"
