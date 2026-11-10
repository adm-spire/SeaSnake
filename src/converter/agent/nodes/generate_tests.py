"""PATH B (and augment mode): generate categorized tests to fill gaps."""

from __future__ import annotations

from ...testing.analysis import analyze_public_functions, enforce_source_limit
from ...testing.coverage import compute_coverage_gaps
from ...testing.generation import generate_tests as generate_cases
from ..services import Services
from ..state import ConverterState, Diagnostic


def generate_tests_node(state: ConverterState, services: Services) -> dict:
    enforce_source_limit(state.python_src, services.settings.max_source_lines)

    functions = analyze_public_functions(state.python_src)
    round_index = state.generation_round + 1
    gaps = compute_coverage_gaps(state.test_cases, functions)

    result = generate_cases(
        python_src=state.python_src,
        functions=functions,
        existing_tests=state.test_cases,
        gaps=gaps,
        generation_round=round_index,
        llm=services.llm,
    )

    diagnostics = list(state.diagnostics)
    diagnostics.append(
        Diagnostic(
            stage="generate",
            severity="info",
            message=(
                f"generation round {round_index}: produced {len(result.tests)} "
                f"case(s), rejected {result.rejected} before validation"
            ),
        )
    )

    return {
        "test_cases": [*state.test_cases, *result.tests],
        "generation_round": round_index,
        "coverage_gaps": gaps,
        "generation_rejections": state.generation_rejections + result.rejected,
        "diagnostics": diagnostics,
    }
