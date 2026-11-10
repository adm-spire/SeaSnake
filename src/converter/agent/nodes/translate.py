"""Translate the verified baseline's Python behavior into Rust."""

from __future__ import annotations

from ...testing.analysis import analyze_public_functions
from ...translation.translator import translate_to_rust
from ..deepagent import run_deep_agent
from ..services import Services
from ..state import ConverterState, Diagnostic


def translate_node(state: ConverterState, services: Services) -> dict:
    functions = analyze_public_functions(state.python_src)
    if services.settings.deep_agent_enabled:
        rust_code = run_deep_agent(
            services,
            python_src=state.python_src,
            functions=functions,
            baseline=state.baseline,
        )
        mode = "deep agent"
    else:
        rust_code = translate_to_rust(
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
                f"translated {len(functions)} public function(s) to Rust "
                f"with the {mode}"
            ),
        )
    )
    return {
        "rust_code": rust_code,
        "status": "translated",
        "diagnostics": diagnostics,
    }
