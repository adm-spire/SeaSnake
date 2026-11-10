"""Generate categorized tests when the user supplies none (or to fill gaps).

The LLM returns structured JSON, not pytest source. That keeps generation
deterministic to parse and makes it impossible for the model to invent a
test-runner side effect. Every generated case is still only a hypothesis until
it is validated against the original Python.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from ..core.errors import LLMError
from ..core.llm import LLMClient
from ..core.parsing import parse_json
from .analysis import FunctionInfo
from .models import (
    Category,
    ExpectedKind,
    ExpectedOutcome,
    NormalizedTest,
    Source,
)


class GeneratedExpected(BaseModel):
    kind: Literal["value", "error"]
    value: Any = None
    exception_type: str | None = None
    message_pattern: str | None = None


class GeneratedCase(BaseModel):
    function: str
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    category: Category
    expected: GeneratedExpected
    name: str | None = None


@dataclass(frozen=True)
class GenerationResult:
    tests: list[NormalizedTest]
    raw_text: str
    rejected: int
    attempts: int


def generate_tests(
    *,
    python_src: str,
    functions: list[FunctionInfo],
    existing_tests: list[NormalizedTest],
    gaps: list[str],
    generation_round: int,
    llm: LLMClient,
    max_cases: int = 80,
) -> GenerationResult:
    if not functions:
        return GenerationResult(tests=[], raw_text="", rejected=0, attempts=0)

    messages = _build_messages(
        python_src=python_src,
        functions=functions,
        existing_tests=existing_tests,
        gaps=gaps,
        generation_round=generation_round,
        max_cases=max_cases,
    )

    raw_text = ""
    rejected = 0
    last_error: str | None = None

    for attempt in range(1, 3):
        response = llm.complete(
            messages,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw_text = response.text
        try:
            raw_cases = _extract_case_dicts(parse_json(response.text))
        except LLMError as exc:
            last_error = str(exc)
            messages = _build_messages(
                python_src=python_src,
                functions=functions,
                existing_tests=existing_tests,
                gaps=gaps,
                generation_round=generation_round,
                max_cases=max_cases,
            ) + [
                {"role": "assistant", "content": response.text},
                {
                    "role": "user",
                    "content": (
                        "That response could not be parsed as JSON. "
                        f"Error: {last_error}. Return valid JSON only."
                    ),
                },
            ]
            continue

        tests, rejected = _normalize_cases(
            raw_cases,
            functions=functions,
            existing_tests=existing_tests,
            generation_round=generation_round,
            max_cases=max_cases,
        )
        if tests or not raw_cases:
            return GenerationResult(
                tests=tests,
                raw_text=raw_text,
                rejected=rejected,
                attempts=attempt,
            )

        last_error = "every generated case was invalid or duplicated"
        messages = _build_messages(
            python_src=python_src,
            functions=functions,
            existing_tests=existing_tests,
            gaps=gaps,
            generation_round=generation_round,
            max_cases=max_cases,
        ) + [
            {"role": "assistant", "content": response.text},
            {
                "role": "user",
                "content": (
                    "No usable cases were produced. Use only the listed public "
                    "functions, unique arguments, and valid JSON. Try again."
                ),
            },
        ]

    raise LLMError(f"test generation failed after 2 attempts: {last_error}")


def _extract_case_dicts(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        cases = payload.get("cases")
    elif isinstance(payload, list):
        cases = payload
    else:
        cases = None
    if not isinstance(cases, list):
        raise LLMError("generated test payload must be a list or {\"cases\": [...]}")
    return [case for case in cases if isinstance(case, dict)]


def _normalize_cases(
    raw_cases: list[dict[str, Any]],
    *,
    functions: list[FunctionInfo],
    existing_tests: list[NormalizedTest],
    generation_round: int,
    max_cases: int,
) -> tuple[list[NormalizedTest], int]:
    function_names = {function.name for function in functions}
    seen = {
        _dedupe_key(test.function, test.args, test.kwargs)
        for test in existing_tests
    }
    tests: list[NormalizedTest] = []
    rejected = 0

    for raw_case in raw_cases:
        if len(tests) >= max_cases:
            break
        try:
            case = GeneratedCase.model_validate(raw_case)
        except ValidationError:
            rejected += 1
            continue

        if case.function not in function_names:
            rejected += 1
            continue

        key = _dedupe_key(case.function, case.args, case.kwargs)
        if key in seen:
            rejected += 1
            continue

        expected = _to_expected(case)
        if expected is None:
            rejected += 1
            continue

        seen.add(key)
        tests.append(
            NormalizedTest(
                id=f"gen-{generation_round}-{uuid.uuid4().hex[:10]}",
                name=case.name or f"{case.function}_generated_{len(tests) + 1}",
                function=case.function,
                args=case.args,
                kwargs=case.kwargs,
                category=case.category,
                source=Source.GENERATED,
                expected=expected,
            )
        )

    return tests, rejected


def _to_expected(case: GeneratedCase) -> ExpectedOutcome | None:
    expected = case.expected
    if expected.kind == "value":
        if "value" not in expected.model_fields_set:
            return None
        return ExpectedOutcome(kind=ExpectedKind.VALUE, value=expected.value)
    if not expected.exception_type:
        return None
    return ExpectedOutcome(
        kind=ExpectedKind.ERROR,
        exception_type=expected.exception_type,
        message_pattern=expected.message_pattern,
    )


def _dedupe_key(function: str, args: list[Any], kwargs: dict[str, Any]) -> str:
    return json.dumps(
        [function, args, kwargs],
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )


def _build_messages(
    *,
    python_src: str,
    functions: list[FunctionInfo],
    existing_tests: list[NormalizedTest],
    gaps: list[str],
    generation_round: int,
    max_cases: int,
) -> list[dict[str, str]]:
    signatures = "\n".join(f"- {function.signature}" for function in functions)
    gap_text = "\n".join(f"- {gap}" for gap in gaps) or "- none"
    existing = _summarize_existing(existing_tests)

    system = """You write differential test cases for a Python-to-Rust converter.
Return JSON only, with this exact shape:

{
  "cases": [
    {
      "name": "short descriptive name",
      "function": "public_function_name",
      "args": [1, 2],
      "kwargs": {"key": "value"},
      "category": "happy_path" | "edge_case" | "error_condition",
      "expected": {"kind": "value", "value": 3}
    },
    {
      "name": "raises on bad input",
      "function": "public_function_name",
      "args": ["bad"],
      "kwargs": {},
      "category": "error_condition",
      "expected": {
        "kind": "error",
        "exception_type": "ValueError",
        "message_pattern": null
      }
    }
  ]
}

Rules:
- Only call functions from the provided signature list.
- Values and arguments must be JSON-compatible: null, bool, number, string,
  list, or object with string keys. Do not use tuples, sets, NaN, or infinity.
- Cover happy_path, edge_case, and error_condition when the function behavior
  allows it. Edge cases include empty inputs, zero/negative numbers, large
  values, single-element collections, and unicode strings.
- For error_condition, exception_type must be the exact Python exception class
  name you expect (for example ValueError, TypeError, KeyError, IndexError,
  ZeroDivisionError). Do not guess a message unless it is meaningful; use null.
- Do not use randomness, time, I/O, network, classes, or external packages.
- Every case must be deterministic and self-contained.
- Do not duplicate existing tests.
- Return no more than the requested number of cases.
"""

    user = (
        f"Generation round: {generation_round}\n"
        f"Return at most {max_cases} cases.\n\n"
        f"Public functions:\n{signatures}\n\n"
        f"Coverage gaps to fill:\n{gap_text}\n\n"
        f"Existing normalized tests (do not duplicate these argument sets):\n{existing}\n\n"
        "Python source under test:\n"
        "```python\n"
        f"{python_src}\n"
        "```\n"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _summarize_existing(tests: list[NormalizedTest]) -> str:
    if not tests:
        return "- none"
    lines = []
    for test in tests[:60]:
        lines.append(
            f"- {test.function}(args={test.args!r}, kwargs={test.kwargs!r}) "
            f"[{test.category.value}]"
        )
    if len(tests) > 60:
        lines.append(f"- ... {len(tests) - 60} more")
    return "\n".join(lines)
