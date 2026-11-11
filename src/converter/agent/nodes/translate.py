"""Translate the verified baseline's Python behavior into C."""

from __future__ import annotations

from ...testing.analysis import analyze_public_functions
from ...translation.translator import translate_to_c
from ..deepagent import run_deep_agent
from ..services import Services
from ..state import ConverterState, Diagnostic


def translate_node(state: ConverterState, services: Services) -> dict:
    functions = analyze_public_functions(state.python_src)
    if services.settings.deep_agent_enabled:
        c_code = run_deep_agent(
            services,
            python_src=state.python_src,
            functions=functions,
            baseline=state.baseline,
        )
        mode = "deep agent"
    else:
        c_code = translate_to_c(
            python_src=state.python_src,
            functions=functions,
            baseline=state.baseline,
            llm=services.llm,
        )
        mode = "single-shot"
    diagnostics = list(state.diagnostics)
    diagnostics.append(
        Diagnostic(
            stage="translate",
            severity="info",
            message=(
                f"translated {len(functions)} public function(s) to C "
                f"with the {mode}"
            ),
        )
    )
    return {
        "c_code": c_code,
        "status": "translated",
        "diagnostics": diagnostics,
    }
