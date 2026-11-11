"""Project-wide exception types.

These are intentionally small. They make it easy for the API layer to return
the right status code and for the agent runner to distinguish expected failures
(bad input) from infrastructure failures (sandbox/LLM).
"""

from __future__ import annotations


class ConverterError(Exception):
    """Base class for all converter failures."""


class InputValidationError(ConverterError):
    """The request is invalid before any conversion work starts."""


class LLMError(ConverterError):
    """The LLM provider failed after retries, or returned unusable output."""


class SandboxError(ConverterError):
    """The sandbox could not start or execute a command."""


class CompileError(ConverterError):
    """C compilation failed (kept for callers that want a typed signal)."""
