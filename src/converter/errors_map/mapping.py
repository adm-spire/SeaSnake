"""The error-mapping convention, defined in exactly one place.

Translation prompts embed this table, and verification uses the same functions
to decide which C error variant an expected Python exception must produce.
Keeping both sides on one implementation prevents the prompt and the checker
from drifting apart.

Convention
----------
* A Python exception maps to the C ``ConvErrorKind`` with the same name.
* If the exact class is not listed, the exception's MRO is consulted so a
  subclass of a mapped exception (for example UnicodeDecodeError ->
  ValueError) still maps correctly.
* Anything unmapped becomes ``CONV_OTHER`` and carries the original Python
  exception name.
* The comparison is variant-first. Message text is only checked when a test
  explicitly supplies a message pattern.
"""

from __future__ import annotations

from collections.abc import Sequence

OTHER_VARIANT = "Other"

# Python class name -> variant name emitted by the C harness for that error.
MAPPING_TABLE: dict[str, str] = {
    "ValueError": "ValueError",
    "TypeError": "TypeError",
    "KeyError": "KeyError",
    "IndexError": "IndexError",
    "ZeroDivisionError": "ZeroDivisionError",
    "OverflowError": "OverflowError",
    "ArithmeticError": "ArithmeticError",
    "AssertionError": "AssertionError",
    "RuntimeError": "RuntimeError",
}

# Variant name -> C enum constant from errors_map/c_prelude.h.
C_CONSTANTS: dict[str, str] = {
    "ValueError": "CONV_VALUE_ERROR",
    "TypeError": "CONV_TYPE_ERROR",
    "KeyError": "CONV_KEY_ERROR",
    "IndexError": "CONV_INDEX_ERROR",
    "ZeroDivisionError": "CONV_ZERO_DIVISION_ERROR",
    "OverflowError": "CONV_OVERFLOW_ERROR",
    "ArithmeticError": "CONV_ARITHMETIC_ERROR",
    "AssertionError": "CONV_ASSERTION_ERROR",
    "RuntimeError": "CONV_RUNTIME_ERROR",
    "Other": "CONV_OTHER",
}

# Base classes that should never be selected by the MRO fallback.
_NON_MAPPABLE = {"Exception", "BaseException", "object"}


def variant_name_for_python_exception(
    python_type: str,
    mro: Sequence[str] | None = None,
) -> str:
    """Return the C error variant name for a Python exception class.

    ``mro`` should be the exception's ``type(exc).__mro__`` names, most specific
    first. It is optional; exact-name lookups work without it.
    """
    if python_type in MAPPING_TABLE:
        return MAPPING_TABLE[python_type]

    for candidate in mro or ():
        if candidate in _NON_MAPPABLE:
            continue
        if candidate in MAPPING_TABLE:
            return MAPPING_TABLE[candidate]

    return OTHER_VARIANT


def c_constant_for_variant(variant: str) -> str:
    """Return the C enum constant for a variant name (``Other`` by default)."""
    return C_CONSTANTS.get(variant, "CONV_OTHER")


def mapping_table_markdown() -> str:
    """Render the table for prompts and documentation."""
    rows = ["| Python exception | C error (ConvErrorKind) |", "|---|---|"]
    for python_name, variant in MAPPING_TABLE.items():
        constant = c_constant_for_variant(variant)
        rows.append(f"| `{python_name}` | `{constant}` (reports `{variant}`) |")
    rows.append(
        "| anything else | `CONV_OTHER` (reports `Other` with the Python type name) |"
    )
    return "\n".join(rows)
