"""Snapshot the validated input -> outcome oracle."""

from __future__ import annotations

from ...core.errors import InputValidationError
from ...testing.baseline import build_baseline
from ..services import Services
from ..state import ConverterState


def capture_baseline_node(state: ConverterState, services: Services) -> dict:
    del services
    baseline = build_baseline(state.test_cases, state.python_outcomes)
    if not baseline:
        raise InputValidationError(
            "no validated tests remain, so there is no oracle to verify against. "
            "Check the invalid user tests in the report."
        )
    return {"baseline": baseline, "status": "validated"}
