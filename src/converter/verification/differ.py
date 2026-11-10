"""Differential comparison: Python baseline outcome vs Rust outcome.

The error side uses the shared mapping in ``errors_map``. A panic never
satisfies any expectation, including an expected error; a timeout or crash
always fails.
"""

from __future__ import annotations

import re
from typing import Any

from ..core.values import values_equal
from ..errors_map.mapping import variant_name_for_python_exception
from ..testing.models import ExpectedKind, ExpectedOutcome
from .models import MatchResult, RustActual


def compare_outcome(expected: ExpectedOutcome, actual: RustActual) -> MatchResult:
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
            if actual.kind == "panic":
                return MatchResult(
                    ok=False,
                    reason=(
                        "expected Err("
                        f"{_expected_variant(expected)}) but the Rust code panicked"
                    ),
                )
            return MatchResult(
                ok=False,
                reason=(
                    f"expected Err({_expected_variant(expected)}), got {actual.kind}"
                    + (f" ({actual.message})" if actual.message else "")
                ),
            )

        expected_variant = _expected_variant(expected)
        if actual.error_variant != expected_variant:
            return MatchResult(
                ok=False,
                reason=(
                    f"expected Err({expected_variant}) "
                    f"({expected.exception_type}), got Err({actual.error_variant})"
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
    detail = f"Err({variant})"
    if expected.exception_type and expected.exception_type != variant:
        detail += f" for {expected.exception_type}"
    if expected.message_pattern:
        detail += f" matching {expected.message_pattern!r}"
    return detail


def rust_actual_from_raw(raw: dict[str, Any]) -> RustActual:
    kind = raw.get("kind")
    if kind == "value":
        return RustActual(kind="value", value=raw.get("value"))
    if kind == "error":
        return RustActual(
            kind="error",
            error_variant=raw.get("error_variant"),
            message=raw.get("message"),
        )
    if kind in {"panic", "timeout", "crash"}:
        return RustActual(kind=kind, message=raw.get("message"))
    return RustActual(kind="crash", message=f"unknown outcome kind: {kind!r}")


def describe_actual(actual: RustActual) -> str:
    if actual.kind == "value":
        return f"value {actual.value!r}"
    if actual.kind == "error":
        detail = f"Err({actual.error_variant})"
        if actual.message:
            detail += f": {actual.message}"
        return detail
    return actual.kind + (f" ({actual.message})" if actual.message else "")
