"""Differential verification: baseline outcomes vs Rust outcomes."""

from __future__ import annotations

from ...core.errors import ConverterError
from ...sandbox.rust_runner import run_cases
from ...verification.differ import rust_actual_from_raw
from ...verification.scoring import evaluate_pass_criteria, score_results
from ..services import Services
from ..state import ConverterState, Diagnostic


def verify_node(state: ConverterState, services: Services) -> dict:
    if not state.rust_workdir:
        raise ConverterError("verify requested without a compiled Rust build")

    cases = [
        {
            "test_id": case.test_id,
            "function": case.function,
            "args": case.args,
            "kwargs": case.kwargs,
        }
        for case in state.baseline
    ]
    raw = run_cases(
        services.executor,
        workdir=state.rust_workdir,
        cases=cases,
        timeout_s=services.settings.run_timeout_s,
    )
    actuals = {
        test_id: rust_actual_from_raw(outcome) for test_id, outcome in raw.items()
    }

    summary = score_results(state.baseline, actuals)
    passed, reasons = evaluate_pass_criteria(summary, state.pass_criteria)

    diagnostics = list(state.diagnostics)
    diagnostics.append(
        Diagnostic(
            stage="verify",
            severity="info" if passed else "warning",
            message=(
                f"differential verification: {summary.overall_passed}/"
                f"{summary.overall_total} passed "
                f"({summary.overall_rate:.1%})"
            ),
        )
    )

    return {
        "rust_results": actuals,
        "score": summary,
        "failures": summary.failures,
        "pass_failures": reasons,
        "status": "verified",
        "diagnostics": diagnostics,
    }
