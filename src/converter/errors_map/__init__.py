"""Python-exception -> Rust-error-variant convention (single source of truth)."""

from .mapping import (
    MAPPING_TABLE,
    OTHER_VARIANT,
    variant_name_for_python_exception,
)

__all__ = ["MAPPING_TABLE", "OTHER_VARIANT", "variant_name_for_python_exception"]
