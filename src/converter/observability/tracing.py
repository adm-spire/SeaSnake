"""Local MLflow tracing wrapper.

MLflow tracing is free, runs entirely on this machine, and needs no account,
server, or hosted backend. Traces are written to the configured tracking URI
(``sqlite:///mlflow.db`` by default) and can be inspected with:

    mlflow ui --backend-store-uri sqlite:///mlflow.db

Tracing is optional: if MLflow is not installed or configuration fails, every
span becomes a no-op. Tracing failures are logged and swallowed so observability
can never take down a conversion.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from ..core.config import Settings
from ..core.logging import get_logger

logger = get_logger(__name__)


class Tracer:
    def __init__(self, settings: Settings) -> None:
        self._mlflow: Any | None = None
        if not settings.mlflow_enabled:
            return
        try:
            os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
            import mlflow

            mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
            mlflow.set_experiment(settings.mlflow_experiment_name)
        except Exception as exc:  # pragma: no cover - depends on optional SDK
            logger.warning(
                "MLflow tracing disabled (install `mlflow` or set "
                "MLFLOW_ENABLED=false): %s",
                exc,
            )
            return
        self._mlflow = mlflow

    @property
    def enabled(self) -> bool:
        return self._mlflow is not None

    @contextmanager
    def span(
        self,
        name: str,
        *,
        input: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[Any | None]:
        if self._mlflow is None:
            yield None
            return

        try:
            manager = self._mlflow.start_span(name=name)
            span = manager.__enter__()
        except Exception as exc:  # pragma: no cover
            logger.debug("could not start MLflow span %s: %s", name, exc)
            yield None
            return

        if input is not None:
            _safe_call(span, "set_inputs", input)
        if metadata:
            _safe_call(span, "set_attributes", {str(key): value for key, value in metadata.items()})

        try:
            yield span
        except BaseException as exc:
            try:
                manager.__exit__(type(exc), exc, exc.__traceback__)
            except Exception:  # pragma: no cover
                logger.debug("MLflow span exit failed", exc_info=True)
            raise
        else:
            try:
                manager.__exit__(None, None, None)
            except Exception:  # pragma: no cover
                logger.debug("MLflow span exit failed", exc_info=True)

    def set_outputs(self, span: Any | None, outputs: Any) -> None:
        """Attach node outputs to a span. Safe to call with a no-op span."""
        if span is not None:
            _safe_call(span, "set_outputs", outputs)

    def flush(self) -> None:
        if self._mlflow is None:
            return
        flush = getattr(self._mlflow, "flush_trace_async_logging", None)
        if callable(flush):
            try:
                flush()
            except Exception as exc:  # pragma: no cover
                logger.debug("MLflow trace flush failed: %s", exc)


def _safe_call(target: Any, method: str, *args: Any) -> None:
    function = getattr(target, method, None)
    if not callable(function):
        return
    try:
        function(*args)
    except Exception as exc:  # pragma: no cover - tracing must never break a run
        logger.debug("MLflow span %s failed: %s", method, exc)
