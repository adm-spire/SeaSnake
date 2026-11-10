"""Capture the confirmed input -> outcome oracle.

Baseline values are the *actual* Python outcomes, not the test author's guesses.
A user test only reaches this point after validation confirmed that its guess
matches Python; a generated test only reaches it after the same check.
"""

from __future__ import annotations

from .models import (
    BaselineCase,
    ExpectedKind,
    ExpectedOutcome,
    NormalizedTest,
    PythonOutcome,
)


def build_baseline(
    tests: list[NormalizedTest],
    outcomes: dict[str, PythonOutcome],
) -> list[BaselineCase]:
    baseline: list[BaselineCase] = []
    for test in tests:
        outcome = outcomes.get(test.id)
        if outcome is None:
            continue
        expected = _expected_from_outcome(test, outcome)
        if expected is None:
            continue
        baseline.append(
            BaselineCase(
                test_id=test.id,
                name=test.name,
                function=test.function,
                args=test.args,
                kwargs=test.kwargs,
                category=test.category,
                source=test.source,
                expected=expected,
            )
        )
    return baseline


def _expected_from_outcome(
    test: NormalizedTest,
    outcome: PythonOutcome,
) -> ExpectedOutcome | None:
    if outcome.kind == "value":
        return ExpectedOutcome(
            kind=ExpectedKind.VALUE,
            value=outcome.value,
            approx=False,
        )
    if outcome.kind == "error":
        return ExpectedOutcome(
            kind=ExpectedKind.ERROR,
            exception_type=outcome.exception_type,
            exception_mro=outcome.exception_mro,
            message_pattern=test.expected.message_pattern,
        )
    return None
