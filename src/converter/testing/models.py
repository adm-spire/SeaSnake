"""The normalized test-case model shared by every path.

A normalized test is a function name plus JSON arguments plus one expected
outcome (a value or a Python exception). The same shape is used for user tests,
generated tests, and baseline entries, which is what lets both test paths
converge on one verification pipeline.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Category(StrEnum):
    HAPPY_PATH = "happy_path"
    EDGE_CASE = "edge_case"
    ERROR_CONDITION = "error_condition"


class Source(StrEnum):
    USER = "user"
    GENERATED = "generated"


class ExpectedKind(StrEnum):
    VALUE = "value"
    ERROR = "error"


class ExpectedOutcome(BaseModel):
    kind: ExpectedKind
    value: Any | None = None
    exception_type: str | None = None
    exception_mro: list[str] = Field(default_factory=list)
    message_pattern: str | None = None
    approx: bool = False


class NormalizedTest(BaseModel):
    id: str
    name: str
    function: str
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    category: Category
    source: Source
    expected: ExpectedOutcome
    raw_source: str | None = None


class InvalidUserTest(BaseModel):
    name: str
    reason: str
    raw_source: str | None = None


class PythonOutcome(BaseModel):
    kind: Literal["value", "error", "timeout", "unsupported", "crash"]
    value: Any | None = None
    exception_type: str | None = None
    exception_mro: list[str] = Field(default_factory=list)
    message: str | None = None


class BaselineCase(BaseModel):
    """A confirmed input -> outcome row. This is the differential oracle."""

    test_id: str
    name: str
    function: str
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    category: Category
    source: Source
    expected: ExpectedOutcome
