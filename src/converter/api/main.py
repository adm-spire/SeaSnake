"""FastAPI app.

``POST /convert`` is synchronous and runs in FastAPI's threadpool. Long
conversions should eventually move to a job queue, but Phase 1 keeps the API
small and observable.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..agent.runner import ConversionRequest, run_conversion
from ..core.config import Settings, get_settings
from ..core.errors import (
    ConverterError,
    InputValidationError,
    LLMError,
    SandboxError,
)
from ..core.logging import configure_logging
from .schemas import ConvertRequest, ConvertResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Agentic Python-to-C Converter",
        version="0.1.0",
        description=(
            "Converts a constrained Python program to C, using a verified "
            "differential test baseline and a bounded repair loop."
        ),
    )

    # Allow the Vite dev server to call the API directly during development.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/convert", response_model=ConvertResponse)
    def convert(payload: ConvertRequest) -> ConvertResponse:
        request = ConversionRequest(
            python_src=payload.python_code,
            user_tests=payload.tests,
            test_mode=payload.test_mode,
            max_attempts=payload.max_attempts,
            pass_criteria=payload.pass_criteria,
        )
        try:
            state = run_conversion(request, settings=settings)
        except InputValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (LLMError, SandboxError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ConverterError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return ConvertResponse(
            run_id=state.run_id,
            status=state.status,
            c_code=state.c_code,
            report=state.report,
        )

    # Serve the production frontend build when it exists (after API routes so
    # /health, /convert, and /docs keep priority).
    frontend_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    return app


app = create_app()
