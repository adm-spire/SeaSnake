"""PATH A: parse user pytest code into normalized tests."""

from __future__ import annotations

from ...core.errors import InputValidationError
from ...testing.analysis import enforce_source_limit
from ...testing.pytest_ingest import ingest_pytest_source
from ..services import Services
from ..state import ConverterState, Diagnostic


def ingest_tests_node(state: ConverterState, services: Services) -> dict:
    enforce_source_limit(state.python_src, services.settings.max_source_lines)

    if not state.user_tests or not state.user_tests.strip():
        raise InputValidationError(
            f"test_mode={state.test_mode!r} requires user-provided pytest tests"
        )

    result = ingest_pytest_source(state.user_tests)
    diagnostics = list(state.diagnostics)
    diagnostics.append(
        Diagnostic(
            stage="ingest",
            severity="info",
            message=(
                f"normalized {len(result.tests)} user test(s); "
                f"{len(result.invalid)} could not be normalized"
            ),
        )
    )
    for invalid in result.invalid:
        diagnostics.append(
            Diagnostic(
                stage="ingest",
                severity="warning",
                message=f"{invalid.name}: {invalid.reason}",
                raw=invalid.raw_source,
            )
        )

    return {
        "test_cases": result.tests,
        "invalid_user_tests": result.invalid,
        "diagnostics": diagnostics,
    }
