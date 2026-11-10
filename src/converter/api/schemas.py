"""Request/response schemas for the submit endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..agent.state import Report
from ..verification.scoring import PassCriteria


class ConvertRequest(BaseModel):
    python_code: str = Field(..., description="Python source, at most 500 lines")
    tests: str | None = Field(
        default=None,
        description="Optional pytest source. Omit to auto-select generate mode.",
    )
    test_mode: Literal["user", "generate", "augment"] | None = Field(
        default=None,
        description=(
            "user = only provided tests; generate = no user tests; augment = "
            "provided tests plus generated gaps. Omit to auto-select."
        ),
    )
    max_attempts: int | None = Field(default=None, ge=0, le=10)
    pass_criteria: PassCriteria | None = None


class ConvertResponse(BaseModel):
    run_id: str
    status: str
    rust_code: str | None = None
    report: Report | None = None
