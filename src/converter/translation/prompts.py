"""Prompts for initial translation and structured repair.

Both prompts embed the error-mapping convention and the fixed harness contract,
so the model always sees the same interface the verifier expects.
"""

from __future__ import annotations

from ..errors_map.mapping import mapping_table_markdown
from ..testing.analysis import FunctionInfo
from ..testing.models import BaselineCase, ExpectedKind
from ..verification.differ import describe_actual, describe_expected
from ..verification.models import FailureCase

SYSTEM_PROMPT = """You are an expert Python-to-Rust translator working inside an
automated differential-testing pipeline. You receive Python source and a
verified baseline of input -> outcome cases. You translate the Python behavior
exactly and exhaustively into Rust.

Return ONLY valid Rust code inside one ```rust fenced block. No prose.

The generated crate already contains these fixed sibling modules:

- `crate::harness` with `Case`, `arg`, `opt_arg`, `req_arg`, `opt_named_arg`,
  `kwarg`, `opt_kwarg`, `ensure_kwargs`, and `json`.
- `crate::error_prelude` with the `ConvError` enum.

You must provide the complete contents of `src/user_code.rs`, including this
exact public entry point (the harness calls it):

```rust
pub fn dispatch(
    case: &crate::harness::Case,
) -> Result<serde_json::Value, crate::error_prelude::ConvError>
```

Contract rules:
- Put every translated function in the same file.
- Every translated function should return `Result<T, ConvError>` unless it is
  truly infallible, in which case returning `T` is fine; if you mix styles, make
  the dispatch layer adapt.
- `dispatch` matches on `case.function` and returns `json(result?)` for value
  outcomes, or propagates an `Err(ConvError::...)` for error outcomes.
- Resolve required parameters with `req_arg(case, index, "name")`; resolve
  parameters with defaults (or `None` defaults) with
  `opt_named_arg(case, index, "name")` and then apply the Python default.
- Call `ensure_kwargs(case, &["name1", "name2", ...])` before reading arguments
  so unexpected keyword arguments raise `TypeError`, as in Python.
- Never use `unwrap`, `expect`, `panic!`, unchecked indexing, or anything that
  can panic on valid input. A Rust panic is treated as a verification failure,
  even when Python raises an exception.
- Never use `unsafe`, I/O, randomness, time, network, global mutable state, or
  external crates other than `serde_json` (and the fixed `serde` dependency).
- Do not omit functions. Do not rename public functions.
- `serde_json::Value` is available for dynamic/heterogeneous data.

Python type mapping:
- `int` -> `i64` (use checked arithmetic; overflow must become OverflowError)
- `float` -> `f64`
- `bool` -> `bool`
- `str` -> `String` (index by Unicode scalar with `.chars().nth(i)`)
- `None` -> `Option<T>` / `()` depending on context
- `list`/`tuple` -> `Vec<T>` (the JSON contract represents both as arrays)
- `dict[str, T]` -> `std::collections::BTreeMap<String, T>`

Behavior rules:
- Preserve Python semantics for zero division, floor division, modulo signs,
  negative indexing, and large integers.
- Missing dict keys -> `ConvError::KeyError`.
- Out-of-range list/string indexing -> `ConvError::IndexError`.
- Wrong runtime types -> `ConvError::TypeError`.
- Integer overflow -> `ConvError::OverflowError`.
- Any other Python exception maps according to the table below.

Exception mapping table (Python -> Rust):

""" + mapping_table_markdown() + """

Unmapped exceptions must use:

```rust
ConvError::Other { python_type: "SomeError".to_string(), message: "...".to_string() }
```

Example dispatch shape (do not copy the function, copy the structure):

```rust
use crate::error_prelude::ConvError;

pub fn add(a: i64, b: i64) -> Result<i64, ConvError> {
    a.checked_add(b)
        .ok_or_else(|| ConvError::OverflowError("integer overflow".to_string()))
}

pub fn dispatch(
    case: &crate::harness::Case,
) -> Result<serde_json::Value, ConvError> {
    match case.function.as_str() {
        "add" => {
            crate::harness::ensure_kwargs(case, &["a", "b"])?;
            let a: i64 = crate::harness::req_arg(case, 0, "a")?;
            let b: i64 = crate::harness::req_arg(case, 1, "b")?;
            crate::harness::json(add(a, b)?)
        }
        other => Err(ConvError::ValueError(format!(
            "unknown function '{}'", other
        ))),
    }
}
```
"""


DEEP_AGENT_SYSTEM_PROMPT = """You are an autonomous Python-to-Rust translation agent
inside a differential-testing pipeline. You own exactly one file, `src/user_code.rs`,
inside a temporary Rust crate. The harness (`src/main.rs`, `src/harness.rs`) and the
error prelude are fixed and must not be touched.

Your loop is: write the file, build it, run the verified baseline against it, and
repair mismatches until every case passes or you are certain the task is complete.

Tools:
- `write_file` / `edit_file` / `read_file`: author `src/user_code.rs`.
- `build_rust`: compile the crate and return cargo diagnostics.
- `run_differential`: run the verified baseline through the compiled binary and
  return per-case pass/fail details.
- `read_python_source`: re-read the Python program (the behavior to preserve).
- `read_baseline`: re-read the verified input -> outcome oracle.

Rules:
- Use only the tools listed above; there is no shell access. In particular, do
  not try to run `cargo` or the binary directly.
- Write the complete `src/user_code.rs` with this exact entry point:

```rust
pub fn dispatch(
    case: &crate::harness::Case,
) -> Result<serde_json::Value, crate::error_prelude::ConvError>
```

- `crate::harness` provides `Case`, `arg`, `opt_arg`, `req_arg`, `opt_named_arg`,
  `kwarg`, `opt_kwarg`, `ensure_kwargs`, and `json`.
- `crate::error_prelude` provides `ConvError`.
- Put every translated function in the same file. Never omit or rename public
  functions.
- Resolve required parameters with `req_arg(case, index, "name")`; resolve
  parameters with defaults with `opt_named_arg(case, index, "name")` and apply the
  Python default.
- Call `ensure_kwargs(case, &["name1", "name2", ...])` before reading arguments.
- Never use `unwrap`, `expect`, `panic!`, `unsafe`, unchecked indexing, I/O,
  randomness, time, network, global mutable state, or external crates other than
  `serde_json` (and the fixed `serde` dependency). A panic is always a failure,
  even when Python raises an exception.
- Use checked integer arithmetic; overflow must become `OverflowError`.
- Do not stop until `build_rust` reports success and `run_differential` reports
  every case passing. When done, reply with a short summary and no code block.

Python type mapping:
- `int` -> `i64` (checked arithmetic; overflow -> `OverflowError`)
- `float` -> `f64`, `bool` -> `bool`
- `str` -> `String` (index by Unicode scalar with `.chars().nth(i)`)
- `None` -> `Option<T>` / `()` depending on context
- `list`/`tuple` -> `Vec<T>`, `dict[str, T]` -> `std::collections::BTreeMap<String, T>`

Behavior rules:
- Preserve Python semantics for zero division, floor division, modulo signs,
  negative indexing, and large integers.
- Missing dict keys -> `ConvError::KeyError`; out-of-range list/string indexing ->
  `ConvError::IndexError`; wrong runtime types -> `ConvError::TypeError`;
  integer overflow -> `ConvError::OverflowError`.
- Any other Python exception maps according to the table below.

Exception mapping table (Python -> Rust):

""" + mapping_table_markdown() + """

Unmapped exceptions must use:

```rust
ConvError::Other { python_type: "SomeError".to_string(), message: "...".to_string() }
```
"""


def build_translate_messages(
    *,
    python_src: str,
    functions: list[FunctionInfo],
    baseline: list[BaselineCase],
) -> list[dict[str, str]]:
    signatures = "\n".join(f"- {function.signature}" for function in functions)
    user = (
        "Translate the following Python program to Rust.\n\n"
        f"Public functions to translate:\n{signatures}\n\n"
        "Verified baseline (these are the behaviors that must match):\n"
        f"{format_baseline_text(baseline)}\n\n"
        "Python source:\n"
        "```python\n"
        f"{python_src}\n"
        "```\n\n"
        "Remember: output only the full contents of src/user_code.rs in one "
        "```rust block."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_repair_messages(
    *,
    python_src: str,
    functions: list[FunctionInfo],
    baseline: list[BaselineCase],
    rust_code: str,
    diagnostics: str,
    failures: list[FailureCase],
    attempt: int,
) -> list[dict[str, str]]:
    signatures = "\n".join(f"- {function.signature}" for function in functions)
    failure_text = _failure_text(failures)
    user = (
        f"Repair attempt {attempt}. The current Rust translation failed.\n\n"
        f"Public functions:\n{signatures}\n\n"
        "Compiler / build diagnostics:\n"
        "```text\n"
        f"{diagnostics or '(none)'}\n"
        "```\n\n"
        "Failing differential cases (input, expected, actual, reason):\n"
        f"{failure_text}\n\n"
        "Full verified baseline, for context:\n"
        f"{format_baseline_text(baseline)}\n\n"
        "Current Rust code:\n"
        "```rust\n"
        f"{rust_code}\n"
        "```\n\n"
        "Python source (the behavior to preserve):\n"
        "```python\n"
        f"{python_src}\n"
        "```\n\n"
        "Fix the Rust code. Preserve the dispatch contract exactly. Do not "
        "change the baseline, weaken error handling, or introduce panics. "
        "Output only the full corrected contents of src/user_code.rs in one "
        "```rust block."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_deep_task_text(
    *,
    python_src: str,
    functions: list[FunctionInfo],
    baseline: list[BaselineCase],
    rust_code: str | None = None,
    diagnostics: str = "",
    failures: list[FailureCase] | None = None,
    attempt: int = 0,
) -> str:
    """First user message for the deep-agent translator/repairer."""
    signatures = "\n".join(f"- {function.signature}" for function in functions)
    sections = [
        "Translate the following Python program to Rust and make the verified "
        "baseline pass.",
        f"Public functions to translate:\n{signatures}",
        f"Verified baseline (these behaviors must match):\n"
        f"{format_baseline_text(baseline)}",
        f"Python source:\n```python\n{python_src}\n```",
        "Author the complete translation in `/src/user_code.rs` (currently "
        "present in the crate). Then call `build_rust`, then `run_differential`, "
        "and repair until both succeed.",
    ]

    if rust_code is not None:
        sections.insert(
            0,
            f"Repair attempt {attempt}. The current translation at "
            "`/src/user_code.rs` builds or matches incorrectly.",
        )
        sections.append(f"Current Rust code:\n```rust\n{rust_code}\n```")
        sections.append(
            "Compiler / build diagnostics:\n"
            f"```text\n{diagnostics or '(none)'}\n```"
        )
        sections.append(
            "Failing differential cases:\n"
            f"{_failure_text(failures or [])}"
        )

    return "\n\n".join(sections)


def format_baseline_text(baseline: list[BaselineCase]) -> str:
    if not baseline:
        return "- (no verified tests)"
    lines = []
    for case in baseline[:120]:
        lines.append(
            f"- {case.function}(args={case.args!r}, kwargs={case.kwargs!r}) "
            f"-> {_expected_text(case)} "
            f"[{case.category.value}, {case.source.value}]"
        )
    if len(baseline) > 120:
        lines.append(f"- ... {len(baseline) - 120} more cases omitted")
    return "\n".join(lines)


def _expected_text(case: BaselineCase) -> str:
    expected = case.expected
    if expected.kind == ExpectedKind.VALUE:
        return f"value {expected.value!r}"
    return f"raise {expected.exception_type}" + (
        f" matching {expected.message_pattern!r}"
        if expected.message_pattern
        else ""
    )


def _failure_text(failures: list[FailureCase]) -> str:
    if not failures:
        return "- (compilation failed; no differential cases ran)"
    lines = []
    for failure in failures[:40]:
        lines.append(
            f"- {failure.name}: call {failure.function}("
            f"args={failure.args!r}, kwargs={failure.kwargs!r}) "
            f"[{failure.category.value}, {failure.source.value}]\n"
            f"  expected: {describe_expected(failure.expected)}\n"
            f"  actual:   {describe_actual(failure.actual)}\n"
            f"  reason:   {failure.reason}"
        )
    if len(failures) > 40:
        lines.append(f"- ... {len(failures) - 40} more failures omitted")
    return "\n".join(lines)
