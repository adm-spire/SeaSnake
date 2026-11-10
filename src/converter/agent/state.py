"""Typed state shared across every LangGraph node."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..core.usage import Usage
from ..testing.models import (
    BaselineCase,
    InvalidUserTest,
    NormalizedTest,
    PythonOutcome,
)
from ..verification.models import FailureCase, RustActual
from ..verification.scoring import CategoryScore, PassCriteria, ScoreSummary


class Diagnostic(BaseModel):
    stage: Literal[
        "input",
        "ingest",
        "generate",
        "validate",
        "capture",
        "translate",
        "compile",
        "verify",
        "repair",
        "report",
    ]
    severity: Literal["info", "warning", "error"]
    message: str
    raw: str | None = None


class Report(BaseModel):
    run_id: str
    status: Literal["passed", "failed", "error"]
    total_tests: int = 0
    per_category: dict[str, CategoryScore] = Field(default_factory=dict)
    source_breakdown: dict[str, int] = Field(default_factory=dict)
    invalid_user_tests: list[InvalidUserTest] = Field(default_factory=list)
    repair_iterations: int = 0
    generation_rounds: int = 0
    compile_ok: bool | None = None
    pass_criteria_failures: list[str] = Field(default_factory=list)
    failed_tests: list[FailureCase] = Field(default_factory=list)
    rust_code: str | None = None
    usage: Usage = Field(default_factory=Usage)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    last_error: str | None = None


class ConverterState(BaseModel):
    # Input and routing.
    run_id: str
    python_src: str
    user_tests: str | None = None
    test_mode: Literal["user", "generate", "augment"]

    # Test generation loop.
    max_generation_rounds: int = 2
    generation_round: int = 0
    coverage_gaps: list[str] = Field(default_factory=list)
    generation_rejections: int = 0
    validation_rejections: int = 0

    # Normalized tests and the verified oracle.
    test_cases: list[NormalizedTest] = Field(default_factory=list)
    validated_test_ids: set[str] = Field(default_factory=set)
    invalid_user_tests: list[InvalidUserTest] = Field(default_factory=list)
    python_outcomes: dict[str, PythonOutcome] = Field(default_factory=dict)
    baseline: list[BaselineCase] = Field(default_factory=list)

    # Translation / compilation.
    rust_code: str | None = None
    rust_workdir: str | None = None
    compile_ok: bool | None = None
    compile_diagnostics: str = ""

    # Verification.
    rust_results: dict[str, RustActual] = Field(default_factory=dict)
    failures: list[FailureCase] = Field(default_factory=list)
    score: ScoreSummary | None = None
    pass_failures: list[str] = Field(default_factory=list)

    # Repair loop.
    attempt: int = 0
    max_attempts: int = 3
    pass_criteria: PassCriteria = Field(default_factory=PassCriteria)

    # Outcome.
    status: Literal[
        "pending",
        "running",
        "validated",
        "translated",
        "compiled",
        "verified",
        "passed",
        "failed",
        "error",
    ] = "pending"
    report: Report | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    last_error: str | None = None
