"""LLM-facing translation and repair operations."""

from __future__ import annotations

from ..core.errors import LLMError
from ..core.llm import LLMClient
from ..core.parsing import extract_code_block
from ..testing.analysis import FunctionInfo
from ..testing.models import BaselineCase
from ..verification.models import FailureCase
from .prompts import build_repair_messages, build_translate_messages


def translate_to_rust(
    *,
    python_src: str,
    functions: list[FunctionInfo],
    baseline: list[BaselineCase],
    llm: LLMClient,
) -> str:
    response = llm.complete(
        build_translate_messages(
            python_src=python_src,
            functions=functions,
            baseline=baseline,
        ),
        temperature=0.0,
    )
    return _validated_code(response.text, stage="translation")


def repair_rust(
    *,
    python_src: str,
    functions: list[FunctionInfo],
    baseline: list[BaselineCase],
    rust_code: str,
    diagnostics: str,
    failures: list[FailureCase],
    attempt: int,
    llm: LLMClient,
) -> str:
    response = llm.complete(
        build_repair_messages(
            python_src=python_src,
            functions=functions,
            baseline=baseline,
            rust_code=rust_code,
            diagnostics=diagnostics,
            failures=failures,
            attempt=attempt,
        ),
        temperature=0.0,
    )
    return _validated_code(response.text, stage="repair")


def _validated_code(text: str, *, stage: str) -> str:
    code = extract_code_block(text, "rust").strip()
    if not code:
        raise LLMError(f"{stage} returned empty Rust code")
    if "fn dispatch" not in code:
        raise LLMError(f"{stage} response does not define `fn dispatch`")
    return code + "\n"
