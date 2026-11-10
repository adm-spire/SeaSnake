"""Conditional-edge functions.

Keeping routing in one module makes the two loops easy to reason about and
easy to unit test without invoking any real node work.
"""

from __future__ import annotations

from .state import ConverterState


def route_test_mode(state: ConverterState) -> str:
    if state.test_mode == "generate":
        return "generate_tests"
    return "ingest_tests"


def route_after_validate(state: ConverterState) -> str:
    if (
        state.test_mode != "user"
        and state.coverage_gaps
        and state.generation_round < state.max_generation_rounds
    ):
        return "generate_tests"
    return "capture_baseline"


def route_after_compile(state: ConverterState) -> str:
    if state.compile_ok:
        return "verify"
    if state.attempt >= state.max_attempts:
        return "report"
    return "repair"


def route_after_verify(state: ConverterState) -> str:
    if not state.pass_failures:
        return "report"
    if state.attempt < state.max_attempts:
        return "repair"
    return "report"
