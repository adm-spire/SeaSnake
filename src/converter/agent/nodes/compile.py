"""Compile the generated C project in the sandbox."""

from __future__ import annotations

from ...core.errors import ConverterError
from ...sandbox.c_runner import build, cleanup_workdir, create_workdir
from ..services import Services
from ..state import ConverterState, Diagnostic


def compile_node(state: ConverterState, services: Services) -> dict:
    if not state.c_code:
        raise ConverterError("compile requested before C code was translated")

    cleanup_workdir(state.workdir)
    workdir = create_workdir()
    try:
        result = build(
            services.executor,
            c_code=state.c_code,
            workdir=workdir,
            timeout_s=services.settings.compile_timeout_s,
        )
    except Exception:
        cleanup_workdir(workdir)
        raise

    diagnostics = list(state.diagnostics)
    if not result.ok:
        cleanup_workdir(workdir)
        diagnostics.append(
            Diagnostic(
                stage="compile",
                severity="error",
                message="C compilation failed",
                raw=result.diagnostics,
            )
        )
        return {
            "workdir": None,
            "compile_ok": False,
            "compile_diagnostics": result.diagnostics,
            "translated_results": {},
            "failures": [],
            "score": None,
            "pass_failures": [],
            "diagnostics": diagnostics,
        }

    diagnostics.append(
        Diagnostic(
            stage="compile",
            severity="info",
            message=f"make succeeded in {result.duration_ms} ms",
        )
    )
    return {
        "workdir": workdir,
        "compile_ok": True,
        "compile_diagnostics": "",
        "translated_results": {},
        "failures": [],
        "score": None,
        "pass_failures": [],
        "status": "compiled",
        "diagnostics": diagnostics,
    }
