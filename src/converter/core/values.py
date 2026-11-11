"""JSON-value comparison rules shared by validation and verification.

The Python baseline and the translated outcome are both normalized to JSON-compatible
values. This module defines exactly what "equal" means so both sides agree.

Rules
-----
* ``bool`` is never equal to a number (Python's True == 1 quirk is not wanted).
* ``int`` and ``float`` compare numerically.
* Floats use a relative/absolute tolerance, with NaN equal to NaN.
* Lists are order-sensitive; dicts are order-insensitive and keys are strings.
* ``None`` equals only ``None``.
"""

from __future__ import annotations

import math
from typing import Any


def values_equal(
    left: Any,
    right: Any,
    *,
    rel_tol: float = 1e-9,
    abs_tol: float = 1e-12,
) -> bool:
    if left is None or right is None:
        return left is None and right is None

    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right

    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return _numbers_equal(float(left), float(right), rel_tol=rel_tol, abs_tol=abs_tol)

    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right

    if isinstance(left, (list, tuple)) or isinstance(right, (list, tuple)):
        if not isinstance(left, (list, tuple)) or not isinstance(right, (list, tuple)):
            return False
        if len(left) != len(right):
            return False
        return all(
            values_equal(a, b, rel_tol=rel_tol, abs_tol=abs_tol)
            for a, b in zip(left, right, strict=True)
        )

    if isinstance(left, dict) or isinstance(right, dict):
        if not isinstance(left, dict) or not isinstance(right, dict):
            return False
        if set(left) != set(right):
            return False
        if not all(isinstance(key, str) for key in left):
            return False
        return all(
            values_equal(left[key], right[key], rel_tol=rel_tol, abs_tol=abs_tol)
            for key in left
        )

    return left == right


def _numbers_equal(
    left: float,
    right: float,
    *,
    rel_tol: float,
    abs_tol: float,
) -> bool:
    if math.isnan(left) or math.isnan(right):
        return math.isnan(left) and math.isnan(right)
    if math.isinf(left) or math.isinf(right):
        return left == right
    return math.isclose(left, right, rel_tol=rel_tol, abs_tol=abs_tol)


def approx_equal(
    left: Any,
    right: Any,
    *,
    rel_tol: float = 1e-6,
    abs_tol: float = 1e-9,
) -> bool:
    """More permissive comparison used to validate pytest.approx expectations."""
    return values_equal(left, right, rel_tol=rel_tol, abs_tol=abs_tol)
