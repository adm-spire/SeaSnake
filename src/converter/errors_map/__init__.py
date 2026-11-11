"""Python-exception -> C-error-variant convention (single source of truth)."""

from .mapping import (
    C_CONSTANTS,
    MAPPING_TABLE,
    OTHER_VARIANT,
    c_constant_for_variant,
    variant_name_for_python_exception,
)

__all__ = [
    "C_CONSTANTS",
    "MAPPING_TABLE",
    "OTHER_VARIANT",
    "c_constant_for_variant",
    "variant_name_for_python_exception",
]
