"""Differential comparison: Python baseline outcome vs C outcome.

The error side uses the shared mapping in ``errors_map``. A crash never
satisfies any expectation, including an expected error; a timeout or crash
always fails.
"""

from __future__ import annotations

import re
from typing import Any

from ..core.values import values_equal
from ..errors_map.mapping import variant_name_for_python_exception
from ..testing.models import ExpectedKind, ExpectedOutcome
from .models import ActualOutcome, MatchResult


def compare_outcome(expected: ExpectedOutcome, actual: ActualOutcome) -> MatchResult:
    if expected.kind == ExpectedKind.VALUE:
        if actual.kind != "value":
            return MatchResult(
                ok=False,
                reason=(
                    f"expected value {expected.value!r}, got {actual.kind}"
                    + (f" ({actual.message})" if actual.message else "")
                ),
            )
        if not values_equal(expected.value, actual.value):
            return MatchResult(
                ok=False,
                reason=f"expected value {expected.value!r}, got {actual.value!r}",
            )
        return MatchResult(ok=True)

    if expected.kind == ExpectedKind.ERROR:
        if actual.kind != "error":
            return MatchResult(
                ok=False,
                reason=(
                    f"expected {_expected_variant(expected)} error, got {actual.kind}"
                    + (f" ({actual.message})" if actual.message else "")
                ),
            )

        expected_variant = _expected_variant(expected)
        if actual.error_variant != expected_variant:
            return MatchResult(
                ok=False,
                reason=(
                    f"expected {expected_variant} "
                    f"({expected.exception_type}), got {actual.error_variant}"
                ),
            )

        if expected.message_pattern:
            try:
                matched = (
                    re.search(expected.message_pattern, actual.message or "") is not None
                )
            except re.error:
                return MatchResult(
                    ok=False,
                    reason=f"invalid message pattern: {expected.message_pattern!r}",
                )
            if not matched:
                return MatchResult(
                    ok=False,
                    reason=(
                        f"message {actual.message!r} does not match "
                        f"{expected.message_pattern!r}"
                    ),
                )
        return MatchResult(ok=True)

    return MatchResult(ok=False, reason=f"unsupported expected kind: {expected.kind}")


def _expected_variant(expected: ExpectedOutcome) -> str:
    return variant_name_for_python_exception(
        expected.exception_type or "",
        expected.exception_mro,
    )


def describe_expected(expected: ExpectedOutcome) -> str:
    if expected.kind == ExpectedKind.VALUE:
        return f"value {expected.value!r}"
    variant = _expected_variant(expected)
    detail = variant
    if expected.exception_type and expected.exception_type != variant:
        detail += f" for {expected.exception_type}"
    if expected.message_pattern:
        detail += f" matching {expected.message_pattern!r}"
    return detail


def actual_from_raw(raw: dict[str, Any]) -> ActualOutcome:
    kind = raw.get("kind")
    if kind == "value":
        return ActualOutcome(kind="value", value=raw.get("value"))
    if kind == "error":
        return ActualOutcome(
            kind="error",
            error_variant=raw.get("error_variant"),
            message=raw.get("message"),
        )
    if kind in {"timeout", "crash"}:
        return ActualOutcome(kind=kind, message=raw.get("message"))
    return ActualOutcome(kind="crash", message=f"unknown outcome kind: {kind!r}")


def describe_actual(actual: ActualOutcome) -> str:
    if actual.kind == "value":
        return f"value {actual.value!r}"
    if actual.kind == "error":
        detail = f"{actual.error_variant}"
        if actual.message:
            detail += f": {actual.message}"
        return detail
    return actual.kind + (f" ({actual.message})" if actual.message else "")
