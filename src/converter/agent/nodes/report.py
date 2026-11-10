"""Terminal node: build the final report and clean up the Rust workdir."""

from __future__ import annotations

from typing import Literal

from ...core.usage import Usage
from ...sandbox.rust_runner import cleanup_workdir
from ...testing.models import Source
from ...verification.scoring import (
    ScoreSummary,
    evaluate_pass_criteria,
    score_results,
)
from ..services import Services
from ..state import ConverterState, Diagnostic, Report


def report_node(state: ConverterState, services: Services) -> dict:
    summary = _summary(state)
    passed, reasons = evaluate_pass_criteria(summary, state.pass_criteria)
    usage = services.tracker.snapshot()

    status: Literal["passed", "failed", "error"]
    if state.status == "error" or state.last_error:
        status = "error"
    elif passed:
        status = "passed"
    else:
        status = "failed"

    diagnostics = list(state.diagnostics)
    diagnostics.append(
        Diagnostic(
            stage="report",
            severity="info" if passed else "warning",
            message=(
                f"final status {status}: {summary.overall_passed}/"
                f"{summary.overall_total} differential cases passed"
            ),
        )
    )

    report = Report(
        run_id=state.run_id,
        status=status,
        total_tests=summary.overall_total,
        per_category=summary.per_category,
        source_breakdown=_source_breakdown(state),
        invalid_user_tests=state.invalid_user_tests,
        repair_iterations=state.attempt,
        generation_rounds=state.generation_round,
        compile_ok=state.compile_ok,
        pass_criteria_failures=reasons,
        failed_tests=summary.failures,
        rust_code=state.rust_code,
        usage=usage,
        diagnostics=diagnostics,
        last_error=state.last_error,
    )

    cleanup_workdir(state.rust_workdir)

    return {
        "report": report,
        "status": status,
        "pass_failures": reasons,
        "rust_workdir": None,
        "usage": usage,
        "diagnostics": diagnostics,
    }


def build_error_report(
    state: ConverterState,
    error: BaseException,
    usage: Usage,
) -> Report:
    """Build a report for a failure that aborted the graph."""
    cleanup_workdir(state.rust_workdir)
    summary = _summary(state)
    _, reasons = evaluate_pass_criteria(summary, state.pass_criteria)
    message = f"{type(error).__name__}: {error}"
    diagnostics = [
        *state.diagnostics,
        Diagnostic(
            stage="report",
            severity="error",
            message=message,
        ),
    ]
    return Report(
        run_id=state.run_id,
        status="error",
        total_tests=summary.overall_total,
        per_category=summary.per_category,
        source_breakdown=_source_breakdown(state),
        invalid_user_tests=state.invalid_user_tests,
        repair_iterations=state.attempt,
        generation_rounds=state.generation_round,
        compile_ok=state.compile_ok,
        pass_criteria_failures=reasons,
        failed_tests=state.failures,
        rust_code=state.rust_code,
        usage=usage,
        diagnostics=diagnostics,
        last_error=message,
    )


def _summary(state: ConverterState) -> ScoreSummary:
    if state.score is not None:
        return state.score
    if state.baseline:
        return score_results(state.baseline, state.rust_results)
    return ScoreSummary(
        overall_total=0,
        overall_passed=0,
        overall_rate=1.0,
        per_category={},
        failures=[],
    )


def _source_breakdown(state: ConverterState) -> dict[str, int]:
    breakdown = {Source.USER.value: 0, Source.GENERATED.value: 0}
    for case in state.baseline:
        breakdown[case.source.value] = breakdown.get(case.source.value, 0) + 1
    return breakdown


__all__ = ["build_error_report", "report_node"]
