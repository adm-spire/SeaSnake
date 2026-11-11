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

SYSTEM_PROMPT = """You are an expert Python-to-C translator working inside an
automated differential-testing pipeline. You receive Python source and a
verified baseline of input -> outcome cases. You translate the Python behavior
exactly and exhaustively into C11.

Return ONLY valid C code inside one ```c fenced block. No prose.

The generated C project already contains these fixed sibling files:

- `src/harness.h` / `src/harness.c`: `Case`, the `JsonValue` type, argument
  helpers (`arg_int`, `arg_double`, `arg_bool`, `arg_string`, `arg_value`,
  `ensure_kwargs`), value constructors (`value_int`, `value_double`,
  `value_bool`, `value_string`, `value_null`, `value_array`, `array_push`,
  `value_object`, `object_set`), value accessors (`value_kind`, `value_length`,
  `value_index`, `object_get`, `value_as_*`, `value_is_null`), and the result
  helpers (`conv_ok`, `conv_error`, `conv_other`, `conv_fail`).
- `src/error_prelude.h`: the `ConvErrorKind` enum.
- `src/user_code.h`: the `dispatch` declaration.

You must provide the complete contents of `src/user_code.c`, including this
exact public entry point:

```c
ConvResult dispatch(const Case *test_case);
```

Contract rules:
- Start the file with `#include "harness.h"` (it pulls in the error enum).
  Include only standard library headers (`string.h`, `stdlib.h`, `math.h`,
  `stdint.h`, `limits.h`, `stdbool.h`, `stddef.h`) as needed.
- Put every translated function in the same file. Do not omit or rename public
  functions.
- `dispatch` compares `test_case->function` with each Python function name and
  returns either `conv_ok(value)` or an error via `conv_error(CONV_..., "msg")`
  / `conv_other("PythonError", "msg")`.
- Resolve required parameters with `arg_int`, `arg_double`, `arg_bool`, or
  `arg_string`, which accept positional or keyword arguments and write a
  `ConvError`. Example:
  `if (!arg_int(test_case, 0, "a", &a, &error)) return conv_fail(error);`
- Parameters with defaults (or `None` defaults) should use
  `arg_value(test_case, index, "name")`, check for `NULL`/`value_is_null`, and
  apply the Python default.
- Call `ensure_kwargs(test_case, allowed, allowed_count, &error)` before reading
  arguments so unexpected keyword arguments raise `TypeError`.
- Collectors are dynamic `JsonValue *` values of kind `JSON_ARRAY` or
  `JSON_OBJECT`. Use `value_length`, `value_index` (returns NULL when out of
  range), `object_get` (returns NULL when missing), and `value_kind` /
  `value_as_int` / `value_as_double` / `value_as_string` / `value_as_bool`.
- Never call `exit`, `abort`, `assert`, or dereference unchecked pointers.
  Producing a crash/segfault is a verification failure, even when Python raises
  an exception. Return an error result instead.
- No I/O, randomness, time, network, global mutable state, `unsafe` language
  features, or external libraries beyond libc/libm.

C type mapping:
- `int` -> `long long` (use `__builtin_add_overflow`, `__builtin_sub_overflow`,
  `__builtin_mul_overflow`; overflow must become `CONV_OVERFLOW_ERROR`)
- `float` -> `double`
- `bool` -> `bool`
- `str` -> `const char *` (UTF-8, NUL-terminated); copy into owned buffers when
  you must build a new string
- `None` -> `value_null()` / `NULL`
- `list`/`tuple` -> `JsonValue *` of kind `JSON_ARRAY`
- `dict[str, T]` -> `JsonValue *` of kind `JSON_OBJECT`

Behavior rules:
- Preserve Python semantics for zero division, floor division, modulo signs,
  negative indexing, and large integers.
- Missing dict keys -> `CONV_KEY_ERROR`; out-of-range list/string indexing ->
  `CONV_INDEX_ERROR`; wrong runtime types -> `CONV_TYPE_ERROR`; integer overflow
  -> `CONV_OVERFLOW_ERROR`; division by zero -> `CONV_ZERO_DIVISION_ERROR`.
- Any other Python exception maps according to the table below.

Exception mapping table (Python -> C):

""" + mapping_table_markdown() + """

Unmapped exceptions must use:

```c
conv_other("SomeError", "message")
```

Example dispatch shape (do not copy the function, copy the structure):

```c
#include "harness.h"
#include <string.h>

static ConvResult add(long long a, long long b) {
    long long out;
    if (__builtin_add_overflow(a, b, &out)) {
        return conv_error(CONV_OVERFLOW_ERROR, "integer overflow");
    }
    return conv_ok(value_int(out));
}

ConvResult dispatch(const Case *test_case) {
    ConvError error;
    if (strcmp(test_case->function, "add") == 0) {
        long long a;
        long long b;
        if (!arg_int(test_case, 0, "a", &a, &error)) {
            return conv_fail(error);
        }
        if (!arg_int(test_case, 1, "b", &b, &error)) {
            return conv_fail(error);
        }
        return add(a, b);
    }
    return conv_error(CONV_VALUE_ERROR, "unknown function");
}
```
"""


DEEP_AGENT_SYSTEM_PROMPT = """You are an autonomous Python-to-C translation agent
inside a differential-testing pipeline. You own exactly one file, `src/user_code.c`,
inside a temporary C project. The harness (`src/main.c`, `src/harness.c`,
`src/harness.h`) and the error prelude are fixed and must not be touched.

Your loop is: write the file, build it, run the verified baseline against it, and
repair mismatches until every case passes or you are certain the task is complete.

Tools:
- `write_file` / `edit_file` / `read_file`: author `src/user_code.c`.
- `build_c`: compile the project with `make` and return compiler diagnostics.
- `run_differential`: run the verified baseline through the compiled binary and
  return per-case pass/fail details.
- `read_python_source`: re-read the Python program (the behavior to preserve).
- `read_baseline`: re-read the verified input -> outcome oracle.

Rules:
- Use only the tools listed above; there is no shell access. In particular, do
  not try to run `make` or the binary directly.
- Write the complete `src/user_code.c` with this exact entry point:

```c
ConvResult dispatch(const Case *test_case);
```

- Start the file with `#include "harness.h"`, which provides `Case`,
  `JsonValue`, `ConvResult`, `ConvError`, the `CONV_*` error constants, the
  argument helpers (`arg_int`, `arg_double`, `arg_bool`, `arg_string`,
  `arg_value`, `ensure_kwargs`), value constructors/accessors, and
  `conv_ok` / `conv_error` / `conv_other` / `conv_fail`.
- Put every translated function in the same file. Never omit or rename public
  functions.
- Resolve required parameters with the typed `arg_*` helpers, which handle
  positional or keyword arguments and write a `ConvError`. Parameters with
  defaults use `arg_value(test_case, index, "name")` plus `value_is_null`.
- Call `ensure_kwargs(test_case, allowed, allowed_count, &error)` before reading
  arguments.
- Never call `exit`, `abort`, `assert`, or dereference unchecked pointers. A
  crash is always a failure, even when Python raises an exception.
- Use `__builtin_add_overflow` / `__builtin_sub_overflow` /
  `__builtin_mul_overflow`; overflow must become `CONV_OVERFLOW_ERROR`.
- No I/O, randomness, time, network, global mutable state, or external
  libraries beyond libc/libm.
- Do not stop until `build_c` reports success and `run_differential` reports
  every case passing. When done, reply with a short summary and no code block.

C type mapping:
- `int` -> `long long` (checked arithmetic; overflow -> `CONV_OVERFLOW_ERROR`)
- `float` -> `double`, `bool` -> `bool`
- `str` -> `const char *` (UTF-8, NUL-terminated)
- `None` -> `value_null()` / `NULL`
- `list`/`tuple` -> `JsonValue *` of kind `JSON_ARRAY`
- `dict[str, T]` -> `JsonValue *` of kind `JSON_OBJECT`

Behavior rules:
- Preserve Python semantics for zero division, floor division, modulo signs,
  negative indexing, and large integers.
- Missing dict keys -> `CONV_KEY_ERROR`; out-of-range list/string indexing ->
  `CONV_INDEX_ERROR`; wrong runtime types -> `CONV_TYPE_ERROR`; integer overflow
  -> `CONV_OVERFLOW_ERROR`; division by zero -> `CONV_ZERO_DIVISION_ERROR`.
- Any other Python exception maps according to the table below.

Exception mapping table (Python -> C):

""" + mapping_table_markdown() + """

Unmapped exceptions must use:

```c
conv_other("SomeError", "message")
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
        "Translate the following Python program to C.\n\n"
        f"Public functions to translate:\n{signatures}\n\n"
        "Verified baseline (these are the behaviors that must match):\n"
        f"{format_baseline_text(baseline)}\n\n"
        "Python source:\n"
        "```python\n"
        f"{python_src}\n"
        "```\n\n"
        "Remember: output only the full contents of src/user_code.c in one "
        "```c block."
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
    c_code: str,
    diagnostics: str,
    failures: list[FailureCase],
    attempt: int,
) -> list[dict[str, str]]:
    signatures = "\n".join(f"- {function.signature}" for function in functions)
    failure_text = _failure_text(failures)
    user = (
        f"Repair attempt {attempt}. The current C translation failed.\n\n"
        f"Public functions:\n{signatures}\n\n"
        "Compiler / build diagnostics:\n"
        "```text\n"
        f"{diagnostics or '(none)'}\n"
        "```\n\n"
        "Failing differential cases (input, expected, actual, reason):\n"
        f"{failure_text}\n\n"
        "Full verified baseline, for context:\n"
        f"{format_baseline_text(baseline)}\n\n"
        "Current C code:\n"
        "```c\n"
        f"{c_code}\n"
        "```\n\n"
        "Python source (the behavior to preserve):\n"
        "```python\n"
        f"{python_src}\n"
        "```\n\n"
        "Fix the C code. Preserve the dispatch contract exactly. Do not "
        "change the baseline, weaken error handling, or introduce crashes. "
        "Output only the full corrected contents of src/user_code.c in one "
        "```c block."
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
    c_code: str | None = None,
    diagnostics: str = "",
    failures: list[FailureCase] | None = None,
    attempt: int = 0,
) -> str:
    """First user message for the deep-agent translator/repairer."""
    signatures = "\n".join(f"- {function.signature}" for function in functions)
    sections = [
        "Translate the following Python program to C and make the verified "
        "baseline pass.",
        f"Public functions to translate:\n{signatures}",
        f"Verified baseline (these behaviors must match):\n"
        f"{format_baseline_text(baseline)}",
        f"Python source:\n```python\n{python_src}\n```",
        "Author the complete translation in `/src/user_code.c` (currently "
        "present in the project). Then call `build_c`, then `run_differential`, "
        "and repair until both succeed.",
    ]

    if c_code is not None:
        sections.insert(
            0,
            f"Repair attempt {attempt}. The current translation at "
            "`/src/user_code.c` builds or matches incorrectly.",
        )
        sections.append(f"Current C code:\n```c\n{c_code}\n```")
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
