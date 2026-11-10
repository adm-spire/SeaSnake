"""Orchestration entry point for a single conversion run.

Streaming ``values`` lets us keep the last successful state if a node raises, so
the error report can still include partial results and clean up the Rust
workdir. The runner never swallows input errors: those propagate to the API as
4xx responses.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel

from ..core.config import Settings
from ..core.errors import InputValidationError
from ..testing.analysis import enforce_source_limit
from ..testing.models import Category
from ..verification.scoring import PassCriteria
from .graph import build_graph
from .nodes.report import build_error_report
from .services import Services, build_services
from .state import ConverterState


class ConversionRequest(BaseModel):
    python_src: str
    user_tests: str | None = None
    test_mode: Literal["user", "generate", "augment"] | None = None
    max_attempts: int | None = None
    pass_criteria: PassCriteria | None = None


def run_conversion(
    request: ConversionRequest,
    *,
    services: Services | None = None,
    settings: Settings | None = None,
) -> ConverterState:
    if services is None:
        services = build_services(settings)
    settings = services.settings

    if not request.python_src.strip():
        raise InputValidationError("python_src cannot be empty")
    enforce_source_limit(request.python_src, settings.max_source_lines)

    test_mode = _select_mode(request)
    if test_mode in {"user", "augment"} and not (
        request.user_tests and request.user_tests.strip()
    ):
        raise InputValidationError(
            f"test_mode={test_mode!r} requires user tests "
            "(omit test_mode to auto-select generate)"
        )

    max_attempts = (
        request.max_attempts
        if request.max_attempts is not None
        else settings.max_attempts
    )
    if max_attempts < 0:
        raise InputValidationError("max_attempts cannot be negative")

    pass_criteria = request.pass_criteria or PassCriteria(
        overall=1.0,
        by_category={
            Category.HAPPY_PATH: settings.strict_threshold,
            Category.ERROR_CONDITION: settings.strict_threshold,
            Category.EDGE_CASE: settings.edge_case_threshold,
        },
    )

    state = ConverterState(
        run_id=uuid.uuid4().hex,
        python_src=request.python_src,
        user_tests=request.user_tests,
        test_mode=test_mode,
        max_generation_rounds=settings.max_generation_rounds,
        max_attempts=max_attempts,
        pass_criteria=pass_criteria,
        status="running",
    )

    graph = build_graph(services)
    last = state

    try:
        for value in graph.stream(
            state,
            stream_mode="values",
            config={"recursion_limit": 80},
        ):
            last = _coerce_state(value)
    except Exception as exc:
        last.last_error = f"{type(exc).__name__}: {exc}"
        last.usage = services.tracker.snapshot()
        last.report = build_error_report(last, exc, last.usage)
        last.status = "error"
        services.tracer.flush()
        return last

    last.usage = services.tracker.snapshot()
    if last.report is not None:
        last.report.usage = last.usage
    services.tracer.flush()
    return last


def _select_mode(request: ConversionRequest) -> Literal["user", "generate", "augment"]:
    if request.test_mode is not None:
        return request.test_mode
    if request.user_tests and request.user_tests.strip():
        return "user"
    return "generate"


def _coerce_state(value: object) -> ConverterState:
    if isinstance(value, ConverterState):
        return value
    return ConverterState.model_validate(value)
