"""Models for differential verification results."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..testing.models import Category, ExpectedOutcome, Source


class RustActual(BaseModel):
    kind: Literal["value", "error", "panic", "timeout", "crash"]
    value: Any | None = None
    error_variant: str | None = None
    message: str | None = None


class MatchResult(BaseModel):
    ok: bool
    reason: str = ""


class FailureCase(BaseModel):
    test_id: str
    name: str
    function: str
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    category: Category
    source: Source
    expected: ExpectedOutcome
    actual: RustActual
    reason: str
