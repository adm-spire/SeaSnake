"""The error-mapping convention, defined in exactly one place.

Translation prompts embed this table, and verification uses the same functions
to decide which Rust variant an expected Python exception must produce. Keeping
both sides on one implementation prevents the prompt and the checker from
drifting apart.

Convention
----------
* A Python exception maps to the Rust variant with the same name.
* If the exact class is not listed, the exception's MRO is consulted so a
  subclass of a mapped exception (for example UnicodeDecodeError ->
  ValueError) still maps correctly.
* Anything unmapped becomes ``ConvError::Other { python_type, message }``.
* The comparison is variant-first. Message text is only checked when a test
  explicitly supplies a message pattern.
"""

from __future__ import annotations

from collections.abc import Sequence

OTHER_VARIANT = "Other"

# Python class name -> Rust ConvError variant name.
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

# Base classes that should never be selected by the MRO fallback.
_NON_MAPPABLE = {"Exception", "BaseException", "object"}


def variant_name_for_python_exception(
    python_type: str,
    mro: Sequence[str] | None = None,
) -> str:
    """Return the Rust ConvError variant name for a Python exception class.

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


def mapping_table_markdown() -> str:
    """Render the table for prompts and documentation."""
    rows = ["| Python exception | Rust ConvError variant |", "|---|---|"]
    for python_name, rust_name in MAPPING_TABLE.items():
        rows.append(f"| `{python_name}` | `ConvError::{rust_name}(String)` |")
    rows.append(
        "| anything else | `ConvError::Other { python_type: String, message: String }` |"
    )
    return "\n".join(rows)
