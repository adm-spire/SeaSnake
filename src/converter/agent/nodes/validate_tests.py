"""Validate every unvalidated test against the original Python."""

from __future__ import annotations

from ...testing.analysis import analyze_public_functions
from ...testing.coverage import compute_coverage_gaps
from ...testing.validation import validate_cases
from ..services import Services
from ..state import ConverterState, Diagnostic


def validate_tests_node(state: ConverterState, services: Services) -> dict:
    unvalidated = [
        test for test in state.test_cases if test.id not in state.validated_test_ids
    ]
    unvalidated_ids = {test.id for test in unvalidated}

    result = validate_cases(
        unvalidated,
        python_src=state.python_src,
        executor=services.executor,
        settings=services.settings,
    )

    retained = [
        test for test in state.test_cases if test.id not in unvalidated_ids
    ] + result.valid_tests

    outcomes = {**state.python_outcomes, **result.python_outcomes}
    gaps = compute_coverage_gaps(
        retained, analyze_public_functions(state.python_src)
    )

    diagnostics = list(state.diagnostics)
    diagnostics.append(
        Diagnostic(
            stage="validate",
            severity="info",
            message=(
                f"validated {len(unvalidated)} case(s): {len(result.valid_tests)} kept, "
                f"{len(result.invalid_user_tests)} user test(s) failed on original code, "
                f"{result.rejected_generated} generated case(s) rejected"
            ),
        )
    )
    if result.invalid_user_tests:
        diagnostics.append(
            Diagnostic(
                stage="validate",
                severity="warning",
                message=(
                    f"{len(result.invalid_user_tests)} user test(s) fail on the "
                    "original Python and were excluded from the baseline"
                ),
            )
        )

    return {
        "test_cases": retained,
        "validated_test_ids": state.validated_test_ids | unvalidated_ids,
        "invalid_user_tests": [
            *state.invalid_user_tests,
            *result.invalid_user_tests,
        ],
        "python_outcomes": outcomes,
        "coverage_gaps": gaps,
        "validation_rejections": state.validation_rejections + result.rejected_generated,
        "diagnostics": diagnostics,
    }
