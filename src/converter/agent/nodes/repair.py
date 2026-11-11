"""Repair loop entry: feed failures back to the translator."""

from __future__ import annotations

from ...testing.analysis import analyze_public_functions
from ...translation.translator import repair_c
from ..deepagent import run_deep_agent
from ..services import Services
from ..state import ConverterState, Diagnostic


def repair_node(state: ConverterState, services: Services) -> dict:
    attempt = state.attempt + 1
    functions = analyze_public_functions(state.python_src)
    diagnostics_text = state.compile_diagnostics or (
        "C compiled successfully, but differential verification found mismatches."
    )

    if services.settings.deep_agent_enabled:
        c_code = run_deep_agent(
            services,
            python_src=state.python_src,
            functions=functions,
            baseline=state.baseline,
            c_code=state.c_code or "",
            diagnostics=diagnostics_text,
            failures=state.failures,
            attempt=attempt,
        )
        mode = "deep agent"
    else:
        c_code = repair_c(
            python_src=state.python_src,
            functions=functions,
            baseline=state.baseline,
            c_code=state.c_code or "",
            diagnostics=diagnostics_text,
            failures=state.failures,
            attempt=attempt,
            llm=services.llm,
        )
        mode = "single-shot"

    diagnostics = list(state.diagnostics)
    diagnostics.append(
        Diagnostic(
            stage="repair",
            severity="info",
            message=(
                f"repair attempt {attempt}/{state.max_attempts} produced new C code "
                f"with the {mode} "
                f"({len(state.failures)} failing case(s) reported)"
            ),
        )
    )

    return {
        "c_code": c_code,
        "attempt": attempt,
        "compile_ok": None,
        "status": "translated",
        "diagnostics": diagnostics,
    }
