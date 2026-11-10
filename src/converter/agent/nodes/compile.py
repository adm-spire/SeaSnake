"""Compile the generated Rust crate in the sandbox."""

from __future__ import annotations

from ...core.errors import ConverterError
from ...sandbox.rust_runner import build, cleanup_workdir, create_workdir
from ..services import Services
from ..state import ConverterState, Diagnostic


def compile_node(state: ConverterState, services: Services) -> dict:
    if not state.rust_code:
        raise ConverterError("compile requested before Rust code was translated")

    cleanup_workdir(state.rust_workdir)
    workdir = create_workdir()
    try:
        result = build(
            services.executor,
            rust_code=state.rust_code,
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
                message="Rust compilation failed",
                raw=result.diagnostics,
            )
        )
        return {
            "rust_workdir": None,
            "compile_ok": False,
            "compile_diagnostics": result.diagnostics,
            "rust_results": {},
            "failures": [],
            "score": None,
            "pass_failures": [],
            "diagnostics": diagnostics,
        }

    diagnostics.append(
        Diagnostic(
            stage="compile",
            severity="info",
            message=f"cargo build succeeded in {result.duration_ms} ms",
        )
    )
    return {
        "rust_workdir": workdir,
        "compile_ok": True,
        "compile_diagnostics": "",
        "rust_results": {},
        "failures": [],
        "score": None,
        "pass_failures": [],
        "status": "compiled",
        "diagnostics": diagnostics,
    }
